"""HAP-31 / CP5：放寬單調性 harness——抓「搜尋沒找到明明存在的解」。

性質：**放寬旋鈕（更大的搜尋空間 / 更多搜尋努力）不該讓分數變差。** 兩條鏈：

  REVS 0→2→4：最乾淨的 dominance。`pop_size = n_dims × POPSIZE` 不隨 REVS 改變，所以
      固定 seed 下三級的**起始族群完全一樣**，只有適應度地形因為多圈 Lambert 變便宜。
      每個點的分數都 ≥（min over 更多分支），L-SHADE 又是精英保留，所以 score 幾乎一定
      單調不減。這裡出現明顯回退 = 真訊號（多圈分支沒被正確納入，或搜尋脆弱）。

  MAX_BURNS [1]→[1,2]→[1,2,3]：**放寬版**。k 棒解可以把多出來的棒設成 0 退化回少棒
      （superset，理論上不會更差），但 pop_size 隨維度變、等於換了隨機起點，雜訊較大。
      所以用「同一條鏈跨 seed 的散布」當容忍帶，只有超出雜訊帶的回退才算違反。

「放寬」的意思就在這：不是要求逐點嚴格單調（隨機搜尋做不到），是要求**回退不超過雜訊帶**；
超出的就是「較大的搜尋反而輸給較小的」，代表搜尋沒找到明明存在（較小搜尋都找得到）的解。

一次跑完整條鏈（每級一個 MissionOptimizer），用中等預算 + 便宜場景控制時間。

跑法：
  uv run python scratch_overnight/monotonicity_harness.py --scenario official_sample --seed 1
結果附加到 scratch_overnight/monotonicity_results.json
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import warnings
warnings.filterwarnings("ignore")

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "monotonicity_results.json")

SCENARIOS = {
    "official_sample": {
        "A": {"SMA": 6978.0, "ECC": 0.0, "INC": 45.0, "RAAN": 0.0, "AOP": 0.0, "TA": 0.0},
        "B": {"SMA": 6878.0, "ECC": 0.0, "INC": 135.0, "RAAN": 30.0, "AOP": 0.0, "TA": 60.0},
    },
    "playground": {
        "A": {"SMA": 13000.0, "ECC": 0.3, "INC": 28.0, "RAAN": 60.0, "AOP": 40.0, "TA": 150.0},
        "B": {"SMA": 7200.0, "ECC": 0.02, "INC": 0.0, "RAAN": 0.0, "AOP": 0.0, "TA": 0.0},
    },
}

# 中等預算：夠讓搜尋收斂到有意義的分數，又不會像完整旋鈕那麼慢。
BASE_OPT = {"POPSIZE": 10, "MAXITER": 150, "NUM_THREADS": -1, "MAX_EARLY_STOP": 150, "TOL": 0.01}
RULES = {"MAX_DV_MPS": 1500.0, "MIN_MANEUVER_INTERVAL_SEC": 100.0, "T_MAX_PERIOD_MULTIPLE": 4.0,
         "k_t": 0.0005, "C_t": 3212.0, "k_v": 0.002, "C_v": 2241.0}


def run_one(scenario, seed, burns, revs):
    from src.optimizer import MissionOptimizer
    g = SCENARIOS[scenario]
    opt = dict(BASE_OPT); opt["MAX_BURNS"] = burns; opt["SEED"] = seed
    cfg = {"orbit_A": g["A"], "orbit_B": g["B"], "rules": RULES,
           "strategy": {"GRAVITY_DEGREE": 2, "MISS_TOLERANCE_KM": 5.0, "LAMBERT_MAX_REVS": revs},
           "optimization": opt}
    _b, _t, mi = MissionOptimizer(cfg).run_study()
    return None if mi is None else float(mi["score"])


def chain_verdict(levels, scores, tol):
    """levels/scores 已按「放寬程度遞增」排好。回傳 (最大回退, 是否違反)。"""
    worst_drop = 0.0
    for i in range(1, len(scores)):
        if scores[i] is None or scores[i - 1] is None:
            continue
        drop = scores[i - 1] - scores[i]        # >0 = 放寬後反而變差
        worst_drop = max(worst_drop, drop)
    return round(worst_drop, 3), bool(worst_drop > tol)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", required=True, choices=list(SCENARIOS))
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--tol", type=float, default=0.5,
                    help="放寬容忍帶（分）：回退超過這個值才算違反單調性")
    ap.add_argument("--out", default=RESULTS)
    args = ap.parse_args()

    print(f"\n{'='*60}\nHAP-31 單調性：{args.scenario}  seed={args.seed}  tol={args.tol}\n{'='*60}")

    # 鏈 A：REVS 0→2→4（固定 BURNS=[1,2]）——最乾淨的 dominance
    revs_levels = [0, 2, 4]
    revs_scores = [run_one(args.scenario, args.seed, [1, 2], r) for r in revs_levels]
    revs_drop, revs_bad = chain_verdict(revs_levels, revs_scores, args.tol)
    print(f"  REVS   {revs_levels} -> {[None if s is None else round(s,2) for s in revs_scores]}"
          f"   最大回退 {revs_drop}  {'❌ 違反' if revs_bad else '✅'}")

    # 鏈 B：MAX_BURNS [1]→[1,2]→[1,2,3]（固定 REVS=4）——放寬版
    burn_levels = [[1], [1, 2], [1, 2, 3]]
    burn_scores = [run_one(args.scenario, args.seed, b, 4) for b in burn_levels]
    burn_drop, burn_bad = chain_verdict(burn_levels, burn_scores, args.tol)
    print(f"  BURNS  {burn_levels} -> {[None if s is None else round(s,2) for s in burn_scores]}"
          f"   最大回退 {burn_drop}  {'❌ 違反' if burn_bad else '✅'}")

    rec = {
        "scenario": args.scenario, "seed": args.seed, "tol": args.tol,
        "revs_levels": revs_levels, "revs_scores": [None if s is None else round(s, 3) for s in revs_scores],
        "revs_worst_drop": revs_drop, "revs_violation": revs_bad,
        "burn_levels": [str(b) for b in burn_levels],
        "burn_scores": [None if s is None else round(s, 3) for s in burn_scores],
        "burn_worst_drop": burn_drop, "burn_violation": burn_bad,
    }
    data = []
    if os.path.exists(args.out):
        try:
            with open(args.out) as f:
                data = json.load(f)
        except Exception:
            data = []
    data.append(rec)
    with open(args.out, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  已寫入 {os.path.basename(args.out)}")


if __name__ == "__main__":
    main()
