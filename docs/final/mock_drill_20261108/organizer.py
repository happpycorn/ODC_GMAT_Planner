"""模擬主辦：照你們交過的 Δv 推演到目前回合，印出最後一回合的公告，並寫出下一回合起點的官方狀態檔（CSV）。

在 medal/ 底下用金牌賽的 venv 跑，每回合交出後跑一次，把到目前為止**所有**回合你們交的 Δv 依序列出：
    .venv/bin/python ../docs/final/mock_drill_20261108/organizer.py --role evader \
        --our-dv -2.6180,178.8761,-89.3110 --our-dv <第 2 回合>,... --out day/round2_end.csv
寫出的狀態檔用 SC_Red／SC_Blue 船名，session 在 new 時記住 --names 後就認得。
對手每回合的 Δv 取自 OPPONENT_MOVES.md；傳播用金牌賽引擎的二體（主辦用 GMAT 二體，兩者差 < 0.1 m）。
"""
import argparse
import datetime as dt
import os
import sys

import numpy as np

sys.path.insert(0, os.getcwd())

from final_copilot import _parse_state, _rv  # noqa: E402
from game.core import Game  # noqa: E402
from game.rules import Rules  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RULES = {"turn_mode": "simultaneous", "rounds": 6, "window_sec": 900.0, "burns_per_turn": 1,
         "max_dv_pursuer_mps": 200.0, "max_dv_evader_mps": 200.0, "fuel_pursuer_mps": None, "fuel_evader_mps": None,
         "capture_radius_km": 8.0, "capture_mode": "continuous", "safe_sma_km": [7428.137, 7488.137],
         "t_max_sec": 0.0, "gravity_degree": 0, "crash_altitude_km": 0.0}
OPPONENT = {  # OPPONENT_MOVES.md
    "pursuer": [(-63.28, 162.25, -98.34), (-110.15, 91.97, -119.23), (48.83, -165.58, 17.18),
                (-84.47, -39.62, -140.12), (136.25, 141.74, -36.71), (154.36, 90.00, 89.86)],
    "evader": [(-2.62, 178.92, -89.33), (-71.28, -4.34, -70.00), (-25.62, -103.30, -169.33),
               (2.30, 63.09, -79.55), (36.76, 64.15, 67.33), (-65.86, -51.00, 55.33)],
}
NAMES = {"pursuer": "SC_Red", "evader": "SC_Blue"}
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
    args = ap.parse_args()
    ours = [_vec(x) for x in args.our_dv]
    if len(ours) > 6:
        raise SystemExit("最多 6 回合")
    opp_side = "pursuer" if args.role == "evader" else "evader"

    state, _ = _parse_state(os.path.join(HERE, "usb/medal/initial_state.csv"),
                            names={"pursuer": [NAMES["pursuer"]], "evader": [NAMES["evader"]]})
    rp, vp = _rv(state, "pursuer")
    re, ve = _rv(state, "evader")
    g = Game(Rules.from_dict(dict(RULES)), rp, vp, re, ve)
    rec = None
    for i, our in enumerate(ours):
        if g.done:
            raise SystemExit(f"比賽在第 {i} 回合已結束（{g.outcome}），後面的 Δv 不會執行")
        dv = {args.role: our, opp_side: np.array(OPPONENT[opp_side][i])}
        rec = g.play_round(dv["pursuer"], dv["evader"])

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
        if g.done:
            print("比賽已結束；仍寫出結束時刻的狀態檔，給 announce 反推最後一回合用")
        with open(args.out, "w", encoding="utf-8") as f:
            f.write("name,epoch,x,y,z,vx,vy,vz\n")
            for side, r, v in (("pursuer", rec["rp_after"], rec["vp_after"]), ("evader", rec["re_after"], rec["ve_after"])):
                f.write(f"{NAMES[side]},{t_end:%d %b %Y %H:%M:%S}.000," + ",".join(f"{x:.6f}" for x in r) + ","
                        + ",".join(f"{x:.9f}" for x in v) + "\n")
        print(f"已寫出第 {n} 回合結束（第 {n + 1} 回合起點）狀態檔：{args.out}")
        print("把這份檔拖進 GUI「每回合」頁（不用手打對手 Δv）；CLI 用：")
        print(f"  .venv/bin/python copilot.py final announce <day>/session.json --state {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
