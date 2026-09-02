"""HAP-33 / CP7（只量一半）：量「硬懲罰牆現在還絆不絆得住搜尋」——不改搜尋端。

背景：計分對每次違規（單棒 ΔV > ΔV_lim=1500 m/s）硬扣 10 分，這在計分地形上是一道
**懸崖**。HAP-33 的提案（decision-needed，我不碰）是搜尋用平滑懲罰、回報用官方硬懲罰。
這支只做「量」的一半：用**現行、未改動的**搜尋，量硬懲罰牆對結果的實際影響。

怎麼在不改核心下量：挑**邊界活躍**的幾何（單棒能量門檻落在 1500 m/s 附近或之上），
對每個幾何跑 `MAX_BURNS=[1]` 跟 `[1,2]`，看：
  1. 單棒多常被罰（final burn > 1500）；
  2. 單棒 ΔV 堆在牆的哪一側（貼著 1500 下方 = 牆是活躍上限）；
  3. **允許兩棒能不能回收**被罰的單棒——拆棒（1500 + 其餘）是繞 ΔV_lim 的標準手法，
     只要總 ΔV < 3000 理論上就有合法兩棒解。

判讀：
  - 單棒常被罰、但兩棒穩定回收成合法且更高分 → 牆**沒有**絆住搜尋（多給一棒就跨過去了）；
  - 兩棒**也**回收不了（明明存在合法拆解卻找不到）→ 牆**正在**絆搜尋，平滑懲罰（HAP-33 的改）
    才真的有價值。

跑法：uv run python scratch_overnight/penalty_wall_probe.py --n 16
結果附加到 scratch_overnight/penalty_wall_results.json
"""

import argparse
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import warnings
warnings.filterwarnings("ignore")
import numpy as np

from src.optimizer import MissionOptimizer

RESULTS = os.path.join(REPO, "scratch_overnight", "penalty_wall_results.json")
MAX_DV_MPS = 1500.0


def build_config(A, B, burns, seed):
    return {
        "orbit_A": A, "orbit_B": B,
        "rules": {"MAX_DV_MPS": MAX_DV_MPS, "MIN_MANEUVER_INTERVAL_SEC": 100.0,
                  "T_MAX_PERIOD_MULTIPLE": 4.0,
                  "k_t": 0.0002, "C_t": 20000.0, "k_v": 0.003, "C_v": 1500.0},
        "strategy": {"GRAVITY_DEGREE": 2, "MISS_TOLERANCE_KM": 5.0, "LAMBERT_MAX_REVS": 4},
        "optimization": {"MAX_BURNS": burns, "MAXITER": 150, "POPSIZE": 15,
                         "NUM_THREADS": -1, "MAX_EARLY_STOP": 150, "TOL": 0.01, "SEED": seed},
    }


def run(A, B, burns, seed):
    _b, _t, mi = MissionOptimizer(build_config(A, B, burns, seed)).run_study()
    if mi is None:
        return None
    burns_vnb = _b
    max_burn_dv = max((float(np.linalg.norm(np.asarray(v, dtype=float))) for v in burns_vnb),
                      default=0.0) * 1000.0
    return {"score": round(float(mi["score"]), 3),
            "penalty": int(mi["penalty_count"]),
            "max_burn_dv_mps": round(max_burn_dv, 1),
            "num_burns": int(mi["num_burns"])}


def random_boundary_geometry(rng):
    """刻意做大高度差，讓單棒 ΔV 常落在 1500 m/s 牆附近或之上。"""
    A = {"SMA": round(rng.uniform(10000.0, 17000.0), 1), "ECC": round(rng.uniform(0.0, 0.3), 3),
         "INC": round(rng.uniform(0.0, 60.0), 2), "RAAN": round(rng.uniform(0, 360), 2),
         "AOP": round(rng.uniform(0, 360), 2), "TA": round(rng.uniform(0, 360), 2)}
    B = {"SMA": round(rng.uniform(6700.0, 7200.0), 1), "ECC": 0.01,
         "INC": round(rng.uniform(0.0, 20.0), 2), "RAAN": 0.0, "AOP": 0.0,
         "TA": round(rng.uniform(0, 360), 2)}
    return A, B


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--seed", type=int, default=424242)
    ap.add_argument("--out", default=RESULTS)
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    print(f"=== HAP-33 懲罰牆探針：{args.n} 組邊界幾何（seed {args.seed}，牆 = {MAX_DV_MPS:.0f} m/s）===\n")
    print(f"{'idx':>3} {'1棒dv':>8} {'1棒罰':>5} {'1棒分':>7} | {'2棒maxdv':>9} {'2棒罰':>5} {'2棒分':>7} | {'回收':>7}")

    out = []
    for i in range(args.n):
        A, B = random_boundary_geometry(rng)
        s1 = run(A, B, [1], args.seed + i)
        s2 = run(A, B, [1, 2], args.seed + i)
        if s1 is None or s2 is None:
            print(f"{i:>3}  (回 None，略過)")
            continue
        recovery = round(s2["score"] - s1["score"], 3)
        out.append({"idx": i, "A": A, "B": B, "single": s1, "two": s2, "recovery": recovery})
        print(f"{i:>3} {s1['max_burn_dv_mps']:>8.0f} {s1['penalty']:>5} {s1['score']:>7.2f} | "
              f"{s2['max_burn_dv_mps']:>9.0f} {s2['penalty']:>5} {s2['score']:>7.2f} | {recovery:>+7.2f}")

    with open(args.out, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # 彙整
    n = len(out)
    single_pen = [r for r in out if r["single"]["penalty"] > 0]
    # 被罰的單棒裡，兩棒有沒有回收成「合法（0 違規）且分數更高」
    recovered = [r for r in single_pen if r["two"]["penalty"] == 0 and r["recovery"] > 0.5]
    stuck = [r for r in single_pen if r["two"]["penalty"] > 0]      # 兩棒也還在違規
    print(f"\n{'─'*60}")
    print(f"  可比 {n} 組；單棒被罰 {len(single_pen)} 組")
    if single_pen:
        print(f"    ├ 兩棒回收成合法且更高分：{len(recovered)}/{len(single_pen)}"
              f"（牆被『多一棒』跨過，沒絆住搜尋）")
        print(f"    └ 兩棒仍違規（沒找到合法拆解）：{len(stuck)}/{len(single_pen)}"
              f"（這些才是牆可能絆住搜尋的候選）")
        if stuck:
            for r in stuck:
                print(f"        idx {r['idx']}: 單棒 dv {r['single']['max_burn_dv_mps']:.0f} 分 "
                      f"{r['single']['score']:.1f} → 兩棒 maxdv {r['two']['max_burn_dv_mps']:.0f} "
                      f"仍罰 {r['two']['penalty']} 分 {r['two']['score']:.1f}")
    print(f"  已寫入 {os.path.basename(args.out)}")


if __name__ == "__main__":
    main()
