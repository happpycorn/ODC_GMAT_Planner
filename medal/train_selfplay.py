"""Self-play 訓練管線（HAP-54）：行為複製暖啟動 → 對解析對手 curriculum → 追/躲交替 self-play league。

METHODOLOGY §6 的配方落地：
  1. **BC 暖啟動**：追者模仿 LambertPursuer、躲者模仿 DvEvader（最大化專家 action 的
     log-likelihood），不從噪音冷啟。
  2. **Curriculum**：追者先打「coast / random / dv_evader_fast」混合池，躲者先打 LambertPursuer。
  3. **League self-play**：每輪追者對「躲者歷代快照 + 解析躲者」池訓練、存快照；躲者再對
     「追者歷代快照 + 解析追者」池訓練。解析 agent 一直留在池裡防止策略循環/遺忘。
  4. 每輪結束跑小型對打評測（vs 固定解析基準），寫進 metrics.jsonl。

規則未公告：預設 `--rules ranges` 每局抽規則、規則參數在觀測裡（rule-conditioned）。

例：
    uv run python train_selfplay.py --name sp1 --envs 12 --bc-episodes 400 \
        --curriculum-steps 300000 --iters 10 --iter-steps 200000
"""
import argparse
import datetime
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROLES = ("pursuer", "evader")
EXPERT = {"pursuer": "lambert_pursuer", "evader": "dv_evader"}
CURRICULUM_OPP = {
    "pursuer": {"name": "pool", "specs": ["coast", "random", "dv_evader_fast"], "probs": [0.3, 0.3, 0.4]},
    # 訓練時用快速版解析追者（env 一步 20 ms → ~5 ms）；評測仍用完整版
    "evader": {"name": "pool", "specs": ["lambert_pursuer_fast",
                                         {"name": "lambert_pursuer_fast", "time_weight_mps": 60.0}]},
}
EVAL_OPPONENTS = {
    "pursuer": ["coast", "dv_evader_fast", "dv_evader"],
    "evader": ["lambert_pursuer", {"name": "lambert_pursuer", "time_weight_mps": 60.0}],
}


# ---------------------------------------------------------------------------- env
ACTION_MODE = {"pursuer": "guided", "evader": "direct"}


def env_config(role, opponent, args):
    return {
        "role": role, "opponent": opponent, "action_mode": ACTION_MODE[role],
        "rule_ranges": args.rules == "ranges",
        "rules": {} if args.rules in ("ranges", "default") else json.load(open(args.rules)),
        "scenario": args.scenario,
        "reward": {"win": 10.0, "shape": args.shape, "fuel": args.fuel_cost, "gamma": args.gamma},
    }


def _make_env(cfg, seed):
    def _f():
        from envs.final_env import GmatFinalEnv
        from stable_baselines3.common.monitor import Monitor
        env = Monitor(GmatFinalEnv(cfg), info_keywords=("agent_won",))
        env.reset(seed=seed)
        return env
    return _f


def make_vec(role, opponent, args, seed):
    from stable_baselines3.common.vec_env import SubprocVecEnv
    cfg = env_config(role, opponent, args)
    return SubprocVecEnv([_make_env(cfg, seed + i) for i in range(args.envs)])


# ---------------------------------------------------------------------------- BC
def _bc_worker(job):
    role, expert_spec, opp_spec, rules_mode, scenario, seed, n_episodes = job
    from agents import make_agent
    from game.actions import GUIDED_DEFAULT_ACTION, dv_to_action
    from game.core import Game
    from game.obs import build_obs
    from game.rules import RuleRanges, Rules
    from game.scenarios import sample_scenario
    expert, opp = make_agent(expert_spec), make_agent(opp_spec)
    rng = np.random.default_rng(seed)
    X, Y = [], []
    for _ in range(n_episodes):
        R = RuleRanges().sample(rng) if rules_mode == "ranges" else Rules()
        sc = sample_scenario(rng, scenario)
        g = Game.from_elements(R, sc.orbit_pursuer, sc.orbit_evader)
        opp.reset(seed=int(rng.integers(2 ** 31)))
        while not g.done:
            side = g.mover
            if side == role:
                dv = expert.act(g, side)
                X.append(build_obs(g, side))
                # guided 追者的專家 = LambertPursuer 預設參數 → BC 目標是固定的預設 action
                Y.append(GUIDED_DEFAULT_ACTION if ACTION_MODE[role] == "guided" else dv_to_action(g, side, dv))
            else:
                dv = opp.act(g, side)
            g.play_turn(dv)
    return np.array(X, dtype=np.float32), np.array(Y, dtype=np.float32)


def collect_bc(role, args, seed):
    per = max(1, args.bc_episodes // args.envs)
    jobs = [(role, EXPERT[role], CURRICULUM_OPP[role], args.rules, args.scenario, seed + i, per)
            for i in range(args.envs)]
    with ProcessPoolExecutor(args.envs) as ex:
        parts = list(ex.map(_bc_worker, jobs))
    X = np.concatenate([p[0] for p in parts if len(p[0])])
    Y = np.concatenate([p[1] for p in parts if len(p[1])])
    return X, Y


def bc_pretrain(model, X, Y, epochs, batch=512, lr=1e-3, log=print, log_std_reset=-1.0):
    import torch
    policy = model.policy
    opt = torch.optim.Adam(policy.parameters(), lr=lr)
    X_t = torch.as_tensor(X, device=policy.device)
    Y_t = torch.as_tensor(Y, device=policy.device)
    n = len(X_t)
    for ep in range(epochs):
        perm = torch.randperm(n, device=policy.device)
        tot, mse_tot = 0.0, 0.0
        for i in range(0, n, batch):
            idx = perm[i:i + batch]
            dist = policy.get_distribution(X_t[idx])
            nll = -dist.log_prob(Y_t[idx]).mean()
            mse = ((dist.distribution.mean - Y_t[idx]) ** 2).mean()
            loss = nll + 10.0 * mse
            opt.zero_grad()
            loss.backward()
            opt.step()
            tot += float(nll.detach()) * len(idx)
            mse_tot += float(mse.detach()) * len(idx)
        if ep % max(1, epochs // 5) == 0 or ep == epochs - 1:
            log(f"    BC epoch {ep:3d}  nll={tot / n:.3f}  mse={mse_tot / n:.4f}")
    # NLL 會把 log_std 一路壓到很小（目標是常數時 std→0），PPO 接手後幾乎不探索。
    # BC 只該決定「平均動作」，探索幅度重設回初始值（sp2 第一次跑時 nll 掉到 -4.4 才發現）。
    if hasattr(policy, "log_std"):
        with torch.no_grad():
            policy.log_std.fill_(log_std_reset)
        log(f"    BC 後 log_std 重設為 {log_std_reset}")


# ---------------------------------------------------------------------------- eval
def evaluate_role(role, model_path, args, n_games, seed):
    from evaluation.tournament import make_games, run_tournament, summarize
    games = make_games(n_games, args.rules if args.rules in ("ranges", "default") else json.load(open(args.rules)),
                       args.scenario, seed=seed)
    me = "sb3:" + model_path
    if role == "pursuer":
        res = run_tournament([me], EVAL_OPPONENTS["pursuer"], games, workers=args.envs, progress=False)
    else:
        res = run_tournament(EVAL_OPPONENTS["evader"], [me], games, workers=args.envs, progress=False)
    _, _, cell = summarize(res)
    out = {}
    for (p, e), c in cell.items():
        opp = e if role == "pursuer" else p
        out[opp] = c["rate"] if role == "pursuer" else 1.0 - c["rate"]
    return out


# ---------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", default=datetime.datetime.now().strftime("sp_%Y%m%d_%H%M"))
    ap.add_argument("--envs", type=int, default=12)
    ap.add_argument("--rules", default="ranges")
    ap.add_argument("--scenario", default="mixed")
    ap.add_argument("--bc-episodes", type=int, default=400)
    ap.add_argument("--bc-epochs", type=int, default=30)
    ap.add_argument("--curriculum-steps", type=int, default=300_000)
    ap.add_argument("--iters", type=int, default=10)
    ap.add_argument("--iter-steps", type=int, default=200_000)
    ap.add_argument("--eval-games", type=int, default=24)
    ap.add_argument("--pool-size", type=int, default=4, help="池裡保留最近幾個對手快照")
    ap.add_argument("--analytic-prob", type=float, default=0.35, help="self-play 池中解析對手的總機率")
    ap.add_argument("--gamma", type=float, default=0.99)
    ap.add_argument("--shape", type=float, default=1.0)
    ap.add_argument("--fuel-cost", type=float, default=0.0)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--n-steps", type=int, default=256)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--skip-bc", action="store_true")
    args = ap.parse_args()

    import torch
    torch.set_num_threads(4)
    from stable_baselines3 import PPO
    from agents.rl import write_meta

    run = os.path.join("runs", args.name)
    os.makedirs(run, exist_ok=True)
    with open(os.path.join(run, "config.json"), "w") as f:
        json.dump(vars(args), f, indent=2)
    logf = open(os.path.join(run, "train.log"), "a")
    metrics = open(os.path.join(run, "metrics.jsonl"), "a")

    def log(msg):
        line = f"[{datetime.datetime.now():%H:%M:%S}] {msg}"
        print(line, flush=True)
        logf.write(line + "\n")
        logf.flush()

    def save(model, role, tag):
        path = os.path.join(run, f"{role}_{tag}.zip")
        model.save(path)
        write_meta(path, {"algo": "PPO", "role": role, "action_power": 1.0, "use_intercept_obs": True,
                          "action_mode": ACTION_MODE[role], "run": args.name, "tag": tag})
        return path

    def record(stage, role, path, steps):
        t0 = time.time()
        ev = evaluate_role(role, path, args, args.eval_games, seed=10_000)
        rec = {"time": datetime.datetime.now().isoformat(timespec="seconds"), "stage": stage, "role": role,
               "model": path, "steps": steps, "win_rate_vs": ev, "eval_sec": round(time.time() - t0, 1)}
        metrics.write(json.dumps(rec) + "\n")
        metrics.flush()
        log(f"  EVAL {role} {stage}: " + ", ".join(f"{k if isinstance(k, str) else json.dumps(k)}={100 * v:.0f}%"
                                                  for k, v in ev.items()))

    policy_kwargs = dict(net_arch=dict(pi=[256, 256], vf=[256, 256]), log_std_init=-0.7)
    models, snapshots, steps = {}, {"pursuer": [], "evader": []}, {"pursuer": 0, "evader": 0}

    # ---- 1. 建模型 + BC 暖啟動 ----
    for i, role in enumerate(ROLES):
        venv = make_vec(role, CURRICULUM_OPP[role], args, seed=args.seed + 1000 * (i + 1))
        models[role] = PPO("MlpPolicy", venv, learning_rate=args.lr, n_steps=args.n_steps,
                           batch_size=max(64, args.n_steps * args.envs // 4),
                           n_epochs=10, gamma=args.gamma, gae_lambda=0.95, clip_range=0.2, ent_coef=0.0,
                           policy_kwargs=policy_kwargs, tensorboard_log=os.path.join(run, "tb"),
                           seed=args.seed + i, verbose=0, device="cpu")
        if not args.skip_bc:
            t0 = time.time()
            X, Y = collect_bc(role, args, seed=args.seed + 500 + i)
            log(f"BC {role}: {len(X)} 筆專家資料（{EXPERT[role]}），收集 {time.time() - t0:.0f}s")
            bc_pretrain(models[role], X, Y, args.bc_epochs, log=log)
        path = save(models[role], role, "bc")
        snapshots[role].append(path)
        record("bc", role, path, 0)

    # ---- 2. curriculum：對解析對手 ----
    for role in ROLES:
        if args.curriculum_steps <= 0:
            continue
        t0 = time.time()
        models[role].learn(args.curriculum_steps, reset_num_timesteps=False, tb_log_name=f"{role}")
        steps[role] += args.curriculum_steps
        log(f"curriculum {role}: {args.curriculum_steps} steps, {time.time() - t0:.0f}s "
            f"({args.curriculum_steps / (time.time() - t0):.0f} sps)")
        path = save(models[role], role, "cur")
        snapshots[role].append(path)
        record("curriculum", role, path, steps[role])

    # ---- 3. league self-play ----
    analytic = {"pursuer": CURRICULUM_OPP["evader"]["specs"],          # 追者當對手時用的解析追者
                "evader": ["dv_evader_fast", "dv_evader"]}
    for it in range(1, args.iters + 1):
        for role in ROLES:
            opp_role = "evader" if role == "pursuer" else "pursuer"
            recent = ["sb3:" + p for p in snapshots[opp_role][-args.pool_size:]]
            ana = analytic[opp_role]
            specs = recent + ana
            probs = [(1 - args.analytic_prob) / len(recent)] * len(recent) + [args.analytic_prob / len(ana)] * len(ana)
            models[role].get_env().env_method("set_opponent", {"name": "pool", "specs": specs, "probs": probs})
            t0 = time.time()
            models[role].learn(args.iter_steps, reset_num_timesteps=False, tb_log_name=f"{role}")
            steps[role] += args.iter_steps
            log(f"iter {it} {role}: {args.iter_steps} steps, {time.time() - t0:.0f}s vs {len(recent)} 快照 + {len(ana)} 解析")
            path = save(models[role], role, f"it{it:02d}")
            snapshots[role].append(path)
            record(f"it{it}", role, path, steps[role])

    for role in ROLES:
        save(models[role], role, "final")
        models[role].get_env().close()
    log("done")


if __name__ == "__main__":
    main()
