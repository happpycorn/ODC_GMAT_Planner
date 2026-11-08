"""模擬主辦（會反應的對手版）：照你們交過的 Δv 從頭推演到目前回合，對手每回合由我們的 agent 即時決定。

跟 mock_drill_20261108 的 organizer 不同：那份對手是事先錄好的推力，不看你出招；這份對手每回合看當下狀態出手
（你選躲方 → 對手是 capture_pursuer；你選追方 → 對手是 safe_evader），固定種子，所以同樣的提交序列結果一樣。
對手出過的推力記在 --log（預設 --out 同資料夾的 organizer_log.json），重跑時前面回合沿用紀錄，不會因為 BLAS 噪音改招。

在 medal/ 底下用金牌賽的 venv 跑，每回合交出後跑一次，把到目前為止**所有**回合你們交的 Δv 依序列出：
    .venv/bin/python ../docs/final/mock_drill_close_20261107/organizer.py --role evader \
        --our-dv=<第1回合X,Y,Z> --our-dv=<第2回合> --out <day 資料夾>/round2_end.csv
改了前面某回合的 Δv（例如想重來），從那回合起對手會重新算、紀錄跟著截斷。
"""
import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.getcwd())

from runtime_threads import limit_blas_threads  # noqa: E402

limit_blas_threads()

import numpy as np  # noqa: E402

from agents import make_agent  # noqa: E402
from final_copilot import _parse_state, _rv  # noqa: E402
from game.core import Game, round_view  # noqa: E402
from game.rules import Rules  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RULES = {"turn_mode": "simultaneous", "rounds": 6, "window_sec": 900.0, "burns_per_turn": 1,
         "max_dv_pursuer_mps": 200.0, "max_dv_evader_mps": 200.0, "fuel_pursuer_mps": None, "fuel_evader_mps": None,
         "capture_radius_km": 8.0, "capture_mode": "continuous", "safe_sma_km": [9648.137, 9678.137],
         "t_max_sec": 0.0, "gravity_degree": 0, "crash_altitude_km": 0.0}
OPP_AGENT = {"pursuer": "capture_pursuer", "evader": "safe_evader"}
NAMES = {"pursuer": "SC_Alpha", "evader": "SC_Beta"}
START = dt.datetime(2026, 11, 9, 7, 0, 0)


def _vec(text):
    parts = [float(x) for x in text.replace(" ", "").split(",")]
    if len(parts) != 3:
        raise SystemExit(f"--our-dv 要三個數字（X,Y,Z，m/s），收到 {text!r}")
    return np.array(parts)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--role", choices=("pursuer", "evader"), required=True, help="你們的角色")
    ap.add_argument("--our-dv", action="append", required=True, help="每回合你們交的 Δv，依回合順序重複這個參數")
    ap.add_argument("--out", help="下一回合起點的官方狀態檔（CSV）")
    ap.add_argument("--log", help="對手出招紀錄（預設 --out 同資料夾的 organizer_log.json）")
    ap.add_argument("--opp-seed", type=int, default=1, help="對手種子（預設 1；換種子＝換一個對手）")
    args = ap.parse_args()
    ours = [_vec(x) for x in args.our_dv]
    if len(ours) > 6:
        raise SystemExit("最多 6 回合")
    opp_side = "pursuer" if args.role == "evader" else "evader"
    log_path = args.log or os.path.join(os.path.dirname(os.path.abspath(args.out)) if args.out else HERE,
                                        "organizer_log.json")
    try:
        log = json.load(open(log_path, encoding="utf-8"))
        if log.get("role") != args.role or log.get("opp_seed") != args.opp_seed:
            log = None
    except (OSError, ValueError):
        log = None
    log = log or {"role": args.role, "opp_seed": args.opp_seed, "rounds": []}

    state, _ = _parse_state(os.path.join(HERE, "usb/initial_state.csv"),
                            names={"pursuer": [NAMES["pursuer"]], "evader": [NAMES["evader"]]})
    rp, vp = _rv(state, "pursuer")
    re, ve = _rv(state, "evader")
    g = Game(Rules.from_dict(dict(RULES)), rp, vp, re, ve)
    opp = make_agent(OPP_AGENT[opp_side])
    opp.reset(seed=args.opp_seed)
    rec, new_rounds, recomputed = None, [], None
    for i, our in enumerate(ours):
        if g.done:
            raise SystemExit(f"比賽在第 {i} 回合已結束（{g.outcome}），後面的 Δv 不會執行")
        opp_dv = np.asarray(opp.act(round_view(g, opp, opp_side), opp_side), dtype=float)  # 每回合都叫，維持對手內部亂數狀態
        old = log["rounds"][i] if i < len(log["rounds"]) and recomputed is None else None
        if old is not None and np.allclose(old["our_dv"], our, atol=1e-6):
            opp_dv = np.array(old["opp_dv"])
        elif recomputed is None:
            recomputed = i + 1
        new_rounds.append({"our_dv": our.tolist(), "opp_dv": opp_dv.tolist()})
        dv = {args.role: our, opp_side: opp_dv}
        rec = g.play_round(dv["pursuer"], dv["evader"])
    log["rounds"] = new_rounds
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=1)
    if recomputed is not None and recomputed <= len(ours) - 1:
        print(f"注意：第 {recomputed} 回合起你們的 Δv 跟紀錄不同，對手從那回合起重新出招")

    n = rec["round"]
    t0 = START + dt.timedelta(seconds=rec["t"])
    print(f"===== 主辦公告：第 {n} 回合結果 =====")
    for b in rec["burns"]:
        side = b["side"]
        note = f"（提交 {np.round(b['dv_submitted_mps'], 4).tolist()} 超過上限，已等比例縮放）" if b["scaled"] else ""
        print(f"{NAMES[side]}（{'追方' if side == 'pursuer' else '逃方'}）實際 Δv："
              f"{', '.join(f'{x:.4f}' for x in b['dv_eci_mps'])} m/s{note}")
    t_min = START + dt.timedelta(seconds=rec["t_window_min"])
    print(f"本回合最近距離：{rec['window_min_dist_km']:.3f} km，發生在 {t_min:%d %b %Y %H:%M:%S}（回合開始後 "
          f"{rec['t_window_min'] - rec['t']:.1f} s）")
    print(f"是否攔截：{'是' if rec['outcome'] == 'capture' else '否'}")
    print(f"逃方半長軸 a：{rec['sma_evader_km']:.3f} km（安全空域 {RULES['safe_sma_km']}）")
    t_end = START + dt.timedelta(seconds=g.t)
    print(f"回合起訖：{t0:%H:%M:%S} → {t_end:%H:%M:%S}")
    if g.done:
        winner = g.summary()["winner"]
        print(f"比賽結束：{g.outcome}，{'追方' if winner == 'pursuer' else '逃方'}獲勝")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write("name,epoch,x,y,z,vx,vy,vz\n")
            for side, r, v in (("pursuer", rec["rp_after"], rec["vp_after"]), ("evader", rec["re_after"], rec["ve_after"])):
                f.write(f"{NAMES[side]},{t_end:%d %b %Y %H:%M:%S}.000," + ",".join(f"{x:.6f}" for x in r) + ","
                        + ",".join(f"{x:.9f}" for x in v) + "\n")
        print(f"已寫出第 {n} 回合結束（第 {n + 1} 回合起點）狀態檔：{args.out}")
        print(f"  .venv/bin/python copilot.py final announce <day>/session.json --state {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
