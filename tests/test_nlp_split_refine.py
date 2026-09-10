"""`_generate_nlp_refined_seed_candidates`（HAP-47）的驗證（不需要 pytest，直接
`uv run python tests/test_nlp_split_refine.py`）。

背景見 HAP47_SPLIT_ALGORITHM_RESEARCH.md：對既有 relay/ladder/pcsplit 三家族種子再做一次
帶顯式不等式約束的 SLSQP 局部聯合優化。這裡驗的是「介面規範」（形狀/bounds/絕不讓種子池
變差）跟「開關生效」，不是驗物理正確性——物理正確性靠 `mission_metrics`/
`reconstruct_mission_logs` 本身（那兩個已經有別的測試/PoC 的 GMAT 驗證覆蓋），這裡只信任
它們、不重複驗證。
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.optimizer import MissionOptimizer, decision_variable_dims

FAILS = []


def check(name, cond):
    print(("  ✅ " if cond else "  ❌ ") + name)
    if not cond:
        FAILS.append(name)


# 平面夾角夠大 (INC 120 vs 40，跟 configs/contest_pcsplit.json 同一組初賽參數)，
# 確保 relay/ladder/pcsplit 三家族真的會產出非空的 base_candidates 給這個測試用。
CFG = {
    "orbit_A": {"SMA": 7100.0, "ECC": 0.0, "INC": 120.0, "RAAN": 30.0, "AOP": 0.0, "TA": 305.349},
    "orbit_B": {"SMA": 6800.0, "ECC": 0.0, "INC": 40.0, "RAAN": 60.0, "AOP": 0.0, "TA": 179.686},
    "rules": {"MAX_DV_MPS": 1500.0, "MIN_MANEUVER_INTERVAL_SEC": 100.0,
              "T_MAX_PERIOD_MULTIPLE": 4.0,
              "k_t": 0.003982, "C_t": 6505.65, "k_v": 0.0011862, "C_v": 9064.3},
    "strategy": {"GRAVITY_DEGREE": 0, "MISS_TOLERANCE_KM": 5.0},
    "optimization": {"MAX_BURNS": [5], "MAXITER": 10, "POPSIZE": 5,
                     "NUM_THREADS": 1, "MAX_EARLY_STOP": 5, "TOL": 0.001},
}


def base_candidates_for(opt, num_burns, n_seeds):
    relay = opt._generate_multiburn_seed_candidates(num_burns, n_seeds)
    ladder = opt._generate_ladder_seed_candidates(num_burns, n_seeds)
    pcsplit = opt._generate_planechange_split_seed_candidates(num_burns, n_seeds)
    return relay + ladder + pcsplit


print("── 邊界情況：該回傳空清單的都要回傳空清單 ──")

opt = MissionOptimizer(CFG)
base = base_candidates_for(opt, 5, 8)
check("真的產出了非空 base_candidates 供後面測試用（前提條件）", len(base) > 0)

check("num_burns<2 時回傳 []",
      opt._generate_nlp_refined_seed_candidates(1, 8, base) == [])
check("n_seeds<=0 時回傳 []",
      opt._generate_nlp_refined_seed_candidates(5, 0, base) == [])
check("base_candidates 空時回傳 []",
      opt._generate_nlp_refined_seed_candidates(5, 8, []) == [])

opt_off = MissionOptimizer({**CFG, "strategy": {**CFG["strategy"], "ENABLE_NLP_SPLIT_REFINE": False}})
check("ENABLE_NLP_SPLIT_REFINE=False 時回傳 []",
      opt_off._generate_nlp_refined_seed_candidates(5, 8, base) == [])


print("\n── 正常情況：形狀/bounds/絕不讓種子池變差 ──")

num_burns, n_seeds = 5, 8
refined = opt._generate_nlp_refined_seed_candidates(num_burns, n_seeds, base)
check("有產出至少一個精修候選（前提：這個情境的 base_candidates 有改善空間）",
      len(refined) > 0)

lb, ub = opt._generate_bounds(num_burns)
lb_arr, ub_arr = np.array(lb), np.array(ub)
dims_ok = all(x.shape == (decision_variable_dims(num_burns),) for x in refined)
check("每個候選的維度都對", dims_ok)

bounds_ok = all(np.all(x >= lb_arr - 1e-9) and np.all(x <= ub_arr + 1e-9) for x in refined)
check("每個候選都落在 _generate_bounds 範圍內", bounds_ok)

# 絕不讓種子池變差：拿 base_candidates 裡分數最高的 3 個 (跟函式內部選 warm start 的
# 邏輯一致) 的最低分當下限，任何精修後的候選都不該低於這個下限 (見函式 docstring：
# 每個 warm start 各自的精修結果都必須 >= 它自己的起點分數，起點又是「前三高」之一)。
scored_base = sorted((opt.mission_metrics(x, num_burns)["score"] for x in base), reverse=True)
worst_of_top3 = scored_base[:min(len(scored_base), 3)][-1]
never_worse = all(opt.mission_metrics(x, num_burns)["score"] >= worst_of_top3 - 1e-6 for x in refined)
check(f"沒有任何候選比它自己的 warm start 差（下限 {worst_of_top3:.4f} 分）", never_worse)

all_safe = all(
    opt.mission_metrics(x, num_burns)["earth_safe"] and opt.mission_metrics(x, num_burns)["dc_converged"]
    for x in refined
)
check("每個候選都 Earth-safe 且 Lambert DC 收斂", all_safe)


print()
if FAILS:
    print(f"❌ {len(FAILS)} 項失敗：" + "、".join(FAILS))
    sys.exit(1)
print("✅ 全部通過")
