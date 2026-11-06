"""金／銅牌賽當天流程彩排：GMAT 二體當「真實世界」，我方走 `copilot.py final` 的完整 CLI 流程。

每回合：
  1. 把 GMAT 的回合起點狀態寫成「官方公告格式」的檔案（輪流用 GMAT 報表／CSV／純文字／JSON，模擬 USB 檔格式未知）
  2. 我方：`final_copilot.py advise session.json --state <檔>`，只從終端機最後一行 `提交：...` 抄數字（同手寫）
  3. 對手：agent 從同一個官方狀態決策（超過 ΔV_lim 照規則等比例縮放）
  4. GmatConsole 從回合起點施加雙方的一發、二體滑行 T_round（密集報表判定捕獲／撞地）
  5. `final_copilot.py announce --opponent-dv ... --our-dv ... --state <回合末檔>`（主辦公告雙方實際 Δv 與新狀態）
結束時用 GMAT 狀態判 escape／sma_out，並用引擎重播同一串 Δv 對照勝負。

例：
    uv run python tools/final_rehearsal.py --role evader --opponent capture_pursuer --seed 0
    uv run python tools/final_rehearsal.py --role pursuer --opponent heuristic_evader --scenario final_adv_cover --fast
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from runtime_threads import limit_blas_threads  # noqa: E402

limit_blas_threads()

from agents import make_agent  # noqa: E402
from game.core import Game, round_view, sma_official  # noqa: E402
from game.rules import Rules, other  # noqa: E402
from game.scenarios import sample_adversarial_scenario, sample_final_rules, sample_final_scenario  # noqa: E402
from physics import get_r0_v0  # noqa: E402
from tools.gmat_verify import GMAT_CONSOLE, gmat_step  # noqa: E402

FORMATS = ("gmat", "csv", "text", "json")
_STATE = ("X", "Y", "Z", "VX", "VY", "VZ")


def write_official(path, state, fmt, t_sec):
    """把雙方狀態寫成某種「官方公告格式」；位置 km、速度 km/s、EarthMJ2000Eq。"""
    vals = {s: [*map(float, state[s][0]), *map(float, state[s][1])] for s in ("pursuer", "evader")}
    f17 = lambda x: format(x, ".15f")  # noqa: E731
    if fmt == "gmat":
        cols = ["ShipP.ElapsedSecs"] + [f"ShipP.EarthMJ2000Eq.{k}" for k in _STATE] + \
               [f"ShipE.EarthMJ2000Eq.{k}" for k in _STATE]
        text = "  ".join(cols) + "\n" + "  ".join(f17(x) for x in [t_sec, *vals["pursuer"], *vals["evader"]]) + "\n"
    elif fmt == "csv":
        text = "side,x,y,z,vx,vy,vz\n" + "".join(
            f"{s},{','.join(f17(x) for x in vals[s])}\n" for s in ("pursuer", "evader"))
    elif fmt == "text":
        text = f"# 官方狀態 t = {t_sec:.3f} s（EarthMJ2000Eq，km、km/s）\n" + "".join(
            f"{s} {' '.join(f17(x) for x in vals[s])}\n" for s in ("pursuer", "evader"))
    else:
        text = json.dumps({s: {"r_km": vals[s][:3], "v_kms": vals[s][3:]} for s in ("pursuer", "evader")},
                          indent=2)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _cli(*args):
    """跑真正的 CLI（跟隊員當天一樣），失敗就把輸出丟出來。"""
    cmd = [sys.executable, os.path.join(ROOT, "final_copilot.py"), *map(str, args)]
    res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=600)
    out = res.stdout + res.stderr
    if res.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[2:3])} 失敗：\n{out}")
    return out


def parse_submission(out):
    """只從最後一行 `提交：角色, 回合, X, Y, Z` 讀數字（手抄的就是這行）。"""
    last = [ln for ln in out.splitlines() if ln.startswith("提交：")]
    if not last:
        raise RuntimeError(f"advise 沒有印提交行：\n{out}")
    fields = [x.strip() for x in last[-1].removeprefix("提交：").split(",")]
    return np.array([float(x) for x in fields[-3:]]), last[-1]


def _problem(args):
    rng = np.random.default_rng([args.seed, 2026])
    if args.rules == "final_ranges":
        R = sample_final_rules(rng)
    else:
        with open(args.rules, encoding="utf-8") as f:
            R = Rules.from_dict(json.load(f))
    if args.scenario == "final":
        R, sc = sample_final_scenario(rng, R)
    else:
        R, sc = sample_adversarial_scenario(rng, R, args.scenario.removeprefix("final_adv_"))
    return R, {"pursuer": get_r0_v0(**sc.orbit_pursuer), "evader": get_r0_v0(**sc.orbit_evader)}, sc


def rehearse(args, log=print):
    R, truth, sc = _problem(args)
    work = args.workdir or tempfile.mkdtemp(prefix="final_rehearsal_")
    os.makedirs(work, exist_ok=True)
    me, opp = args.role, other(args.role)
    opp_spec = args.opponent or ("capture_pursuer" if me == "evader" else "safe_evader")
    opponent = make_agent(opp_spec)
    opponent.reset(seed=args.seed + 7)
    rules_path = os.path.join(work, "announced.json")
    d = R.to_dict()
    d.update(fuel_pursuer_mps=None, fuel_evader_mps=None,
             safe_sma_km=list(d["safe_sma_km"]) if d["safe_sma_km"] is not None else None)
    with open(rules_path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    session = os.path.join(work, "session.json")
    init_path = write_official(os.path.join(work, "round01_start.gmat.txt"), truth, "gmat", 0.0)
    _cli("new", "--rules", rules_path, "--initial", init_path, "--role", me, "--out", session)
    log(f"題目：{sc.family}；ΔV_lim {R.max_dv_pursuer_mps:.1f} m/s、R_cap {R.capture_radius_km:.2f} km、"
        f"T_round {R.window_sec:.0f} s、安全空域 {R.safe_sma_km}；我方 {me}、對手 {opp_spec}；工作目錄 {work}")

    T = float(R.window_sec)
    rows, dvs, outcome, t_end = [], [], None, 0.0
    start_path = init_path
    for k in range(1, R.rounds + 1):
        t0 = (k - 1) * T
        tic = time.perf_counter()
        out = _cli("advise", session, "--state", start_path, *(["--fast"] if args.fast else []))
        advise_sec = time.perf_counter() - tic
        my_dv, line = parse_submission(out)
        consistency = next((ln for ln in out.splitlines() if ln.startswith("一致性檢查")), "")
        g = Game.from_snapshot(R, *truth["pursuer"], *truth["evader"], t=t0, round_index=k - 1)
        opp_dv = g.clip_dv(opp, opponent.act(round_view(g, opponent, opp), opp))   # 主辦等比例縮放
        dv = {me: my_dv, opp: opp_dv}
        rec = {"t": t0, "side": "both", "coast_sec": T,
               "burns": [{"side": s, "t": t0, "dv_eci_mps": dv[s], "dv_mps": float(np.linalg.norm(dv[s]))}
                         for s in ("pursuer", "evader")]}
        truth_next, ana = gmat_step(R, truth, rec, force_model="zonal", console=args.gmat_console, with_analysis=True)
        dvs.append(dv)
        rows.append({"round": k, "advise_sec": advise_sec, "line": line, "consistency": consistency,
                     "d_min_km": ana["d_min_km"], "event": ana["first_event"],
                     "dist_end_km": float(np.linalg.norm(truth_next["pursuer"][0] - truth_next["evader"][0]))})
        log(f"第 {k} 回合：{line}；對手 |Δv| {np.linalg.norm(opp_dv):.2f} m/s；GMAT 最近 {ana['d_min_km']:.3f} km；"
            f"advise {advise_sec:.1f} s；{consistency or '（第 1 回合無預測可比）'}")
        if ana["first_event"] is not None:
            outcome, t_end = ana["first_event"], float(ana["t_event_sec"])
            break
        truth = truth_next
        start_path = write_official(os.path.join(work, f"round{k + 1:02d}_start.{FORMATS[k % 4]}.txt"),
                                    truth, FORMATS[k % 4], k * T)
        _cli("announce", session, "--opponent-dv", *opp_dv, "--our-dv", *my_dv, "--state", start_path)
        t_end = k * T
    if outcome is None:
        a = sma_official(*truth["evader"])
        lo, hi = R.safe_sma_km if R.safe_sma_km is not None else (-np.inf, np.inf)
        outcome = "escape" if lo <= a <= hi else "sma_out"

    eng = Game(R, *_problem(args)[1]["pursuer"], *_problem(args)[1]["evader"])
    for dv in dvs:
        if eng.done:
            break
        eng.play_round(dv["pursuer"], dv["evader"])
    winner = {"capture": "pursuer", "crash_evader": "pursuer", "sma_out": "pursuer",
              "escape": "evader", "timeout": "evader", "crash_pursuer": "evader"}[outcome]
    summary = {"family": sc.family, "rules": d, "role": me, "opponent": opp_spec, "outcome_gmat": outcome,
               "winner_gmat": winner, "we_won": winner == me, "outcome_engine": eng.outcome, "t_end": t_end,
               "rounds": rows, "max_advise_sec": max(r["advise_sec"] for r in rows), "workdir": work}
    log(f"結局（GMAT）：{outcome}（{'我方勝' if winner == me else '我方敗'}）；引擎重播：{eng.outcome}；"
        f"advise 最長 {summary['max_advise_sec']:.1f} s")
    with open(os.path.join(work, "rehearsal.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=float)
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--role", choices=("pursuer", "evader"), required=True)
    ap.add_argument("--opponent", default=None, help="對手 agent（預設：最強的 capture_pursuer／safe_evader）")
    ap.add_argument("--rules", default="configs/rulesets/final_official.json", help="規則 JSON 或 final_ranges")
    ap.add_argument("--scenario", default="final", help="final 或 final_adv_<kind>")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--gmat-console", default=GMAT_CONSOLE)
    args = ap.parse_args(argv)
    rehearse(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
