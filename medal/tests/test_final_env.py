"""GmatFinalEnv（gym 包裝）測試：sb3 合規、回合語意、終局標記、獎勵方向、Δv 合法性。"""
import numpy as np
import pytest
from stable_baselines3.common.env_checker import check_env

from envs.final_env import GmatFinalEnv


@pytest.mark.parametrize("role", ["pursuer", "evader", "random"])
def test_check_env(role):
    check_env(GmatFinalEnv({"role": role, "rule_ranges": True, "scenario": "mixed"}), warn=True)


def test_timeout_is_terminated_not_truncated():
    env = GmatFinalEnv({"role": "evader", "rules": {"t_max_sec": 1500.0, "window_sec": 300.0}})
    env.reset(seed=0)
    done = False
    while not done:
        obs, r, term, trunc, info = env.step(np.zeros(3))
        assert not trunc
        done = term
    assert info["outcome"] == "timeout" and info["agent_won"] is True
    assert r > 0


def test_opponent_moves_first_when_rules_say_so():
    env = GmatFinalEnv({"role": "pursuer", "opponent": "random",
                        "rules": {"first_mover": "evader"}})
    env.reset(seed=3)
    assert env.game.turn == 1 and env.game.mover == "pursuer"


def test_action_never_exceeds_cap_and_random_play_terminates():
    rng = np.random.default_rng(0)
    outcomes = {}
    for ep in range(12):
        env = GmatFinalEnv({"role": "random", "opponent": "random", "rule_ranges": True,
                            "scenario": "mixed", "use_intercept_obs": False, "reward": {"shape": 0.0}})
        obs, _ = env.reset(seed=ep)
        done = False
        while not done:
            obs, r, term, trunc, info = env.step(rng.uniform(-1, 1, 3))
            assert env.observation_space.contains(obs) and np.isfinite(r)
            for rec in env.game.history:
                assert rec["dv_mps"] <= env.game.rules.max_dv(rec["side"]) + 1e-6
            done = term or trunc
        assert info["outcome"] in ("capture", "timeout", "crash_pursuer", "crash_evader")
        assert env.game.used["pursuer"] <= env.game.rules.fuel_pursuer_mps + 1e-6
        outcomes[info["outcome"]] = outcomes.get(info["outcome"], 0) + 1
    assert sum(outcomes.values()) == 12


def test_guided_pursuer_default_action_captures_passive_target():
    """guided 模式下固定的預設 action = LambertPursuer 預設行為 → 對被動目標要抓得到。"""
    from game.actions import GUIDED_DEFAULT_ACTION, guided_params
    w, f, h = guided_params(GUIDED_DEFAULT_ACTION)
    assert abs(w - 10.0) < 1e-9 and f == 1.0 and h == 1.0
    env = GmatFinalEnv({"role": "pursuer", "opponent": "coast", "action_mode": "guided",
                        "scenario": "near_coplanar", "use_intercept_obs": False, "reward": {"shape": 0.0}})
    env.reset(seed=11)
    done = False
    while not done:
        _, r, done, _, info = env.step(GUIDED_DEFAULT_ACTION)
    assert info["outcome"] == "capture"
    assert r > 0


def test_guided_mode_ignored_for_evader():
    env = GmatFinalEnv({"role": "evader", "action_mode": "guided", "opponent": "coast"})
    env.reset(seed=0)
    env.step(np.array([0.0, 1.0, 0.0]))
    evader_recs = [r for r in env.game.history if r["side"] == "evader"]
    assert evader_recs, "躲者的回合沒被執行"
    # direct 模式：|a| = 1 → 推滿單次上限（guided 設定對躲者無效）
    assert abs(evader_recs[0]["dv_mps"] - env.game.rules.max_dv_evader_mps) < 1e-6


def test_shaping_rewards_pursuer_for_reducing_need():
    """追者推一發完整的短程攔截解（進入碰撞航線，need→0）的塑形獎勵應 > 什麼都不做。"""
    from agents.analytic import LambertPursuer
    from physics.frames import rsw_basis
    cfg = {"role": "pursuer", "opponent": "coast", "scenario": "near_coplanar",
           "rules": {"max_dv_pursuer_mps": 1500.0, "fuel_pursuer_mps": 3000.0, "window_sec": 300.0,
                     "t_max_sec": 20000.0}}
    env = GmatFinalEnv(cfg)
    env.reset(seed=5)
    g0 = env.game.clone()
    dv = LambertPursuer(time_weight_mps=200.0, coast_if_captures=False).act(env.game, "pursuer")
    assert np.linalg.norm(dv) < 1500.0
    a = rsw_basis(env.game.r("pursuer"), env.game.v("pursuer")) @ dv / 1500.0
    _, r_burn, *_ = env.step(a)
    env.reset(seed=5)
    assert np.allclose(env.game.r("pursuer"), g0.r("pursuer"))
    _, r_idle, *_ = env.step(np.zeros(3))
    assert r_burn > r_idle
