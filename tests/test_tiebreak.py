"""規則第 6 節平手判定的驗證（不需要 pytest，直接 `uv run python tests/test_tiebreak.py`）。

為什麼要獨立測：平手那條路徑在真實搜尋裡不保證跑得到——要剛好兩個燃燒次數案例的
分數在浮點數等級一模一樣。真的跑一次最佳化來碰運氣測不到，只能餵假資料。

官方規則 Regulations_PrelimRound §6 Tie-Breaking Rules：
    1. Minimum Relative Distance   小者排前面
    2. Total Velocity Increment    少者排前面
    3. Mission Completion Time     短者排前面
    4. Design Theory（上台報告，程式管不到）
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.optimizer import (MissionOptimizer, tiebreak_rank_key,
                           decision_variable_dims, pick_best_across_revs)

FAILS = []


def check(name, cond):
    print(("  ✅ " if cond else "  ❌ ") + name)
    if not cond:
        FAILS.append(name)


def rank(cands, floor_miss=False):
    """把 {標籤: (score, miss_km, dv_mps, t_team)} 照規則排序，第一名在前。"""
    return sorted(cands, key=lambda k: tiebreak_rank_key(*cands[k], floor_miss=floor_miss))


print("── tiebreak_rank_key：優先序 ──")

# 分數不同時，平手判定完全不該介入：分數高的贏，就算它三項全部比較差。
check("分數高者勝，平手判定不介入",
      rank({"高分但各項都差": (95.1, 4.9, 3000.0, 9000.0),
            "低分但各項都好": (95.0, 0.1, 100.0, 100.0)})[0] == "高分但各項都差")

# 同分 → 優先序 1：Δr_min 小者勝（即使 Δv 比較多、時間比較久）
check("同分時 Δr_min 小者勝（勝過 ΔV 與時間）",
      rank({"近但費油又慢": (90.0, 0.3, 2000.0, 9000.0),
            "遠但省油又快": (90.0, 3.4, 1500.0, 3000.0)})[0] == "近但費油又慢")

# 同分且 Δr 相同 → 優先序 2：ΔV_team 少者勝
check("同分且 Δr 相同時 ΔV_team 少者勝",
      rank({"省油但慢": (90.0, 1.0, 1500.0, 9000.0),
            "費油但快": (90.0, 1.0, 2000.0, 3000.0)})[0] == "省油但慢")

# 同分、Δr、ΔV 都相同 → 優先序 3：T_team 短者勝
check("同分且 Δr/ΔV 都相同時 T_team 短者勝",
      rank({"快": (90.0, 1.0, 1500.0, 3000.0),
            "慢": (90.0, 1.0, 1500.0, 9000.0)})[0] == "快")

# 浮點數尾巴的雜訊不該被當成真實分數差距（SCORE_TIE_EPS 之下算打平）
check("分數只差 1e-12 視為打平，改由 Δr 決定",
      rank({"分數低 1e-12 但近": (90.0 - 1e-12, 0.2, 2000.0, 9000.0),
            "分數高 1e-12 但遠": (90.0, 4.0, 1500.0, 3000.0)})[0] == "分數低 1e-12 但近")


print("\n── floor_miss：規則第 6 節優先序 1 的兩種讀法 ──")
# 規則沒有定義 d_min,team 這個符號。兩種讀法會選出不同贏家，工具的責任是講白不是隱瞞。
amb = {"近但費油": (90.0, 0.3, 2000.0, 5000.0),
       "遠但省油": (90.0, 3.4, 1990.0, 4900.0)}
check("原始距離讀法 → 近的那個勝", rank(amb, floor_miss=False)[0] == "近但費油")
check("max(Δr,5) 地板讀法 → 兩者都是 5，落到優先序 2，省油的勝",
      rank(amb, floor_miss=True)[0] == "遠但省油")


print("\n── MissionOptimizer._pick_best_case：平手時挑哪個案例 ──")

CFG = {
    "orbit_A": {"SMA": 9000.0, "ECC": 0.0, "INC": 0.0, "RAAN": 0.0, "AOP": 0.0, "TA": 0.0},
    "orbit_B": {"SMA": 7500.0, "ECC": 0.0, "INC": 0.0, "RAAN": 0.0, "AOP": 0.0, "TA": 0.0},
    "rules": {"MAX_DV_MPS": 1500.0, "MIN_MANEUVER_INTERVAL_SEC": 100.0,
              "T_MAX_PERIOD_MULTIPLE": 4.0,
              "k_t": 0.0001, "C_t": 11000.0, "k_v": 0.005, "C_v": 1200.0},
    "strategy": {"GRAVITY_DEGREE": 2, "MISS_TOLERANCE_KM": 5.0},
    "optimization": {"MAX_BURNS": [1, 2, 3], "MAXITER": 10, "POPSIZE": 5,
                     "NUM_THREADS": 1, "MAX_EARLY_STOP": 5, "TOL": 0.001},
}


def pick(fake_metrics, fitness=None):
    """用假的 mission_metrics 跑一次挑選，回傳選中的燃燒次數。"""
    opt = MissionOptimizer(CFG)
    opt.burn_case_results = {
        b: {"fitness": (fitness or {}).get(b, -m[0]),
            "best_x": [0.0] * decision_variable_dims(b), "epochs_run": 1, "note": ""}
        for b, m in fake_metrics.items()
    }
    opt.mission_metrics = lambda x, b: dict(
        zip(("score", "miss_km", "dv_mps", "t_team"), fake_metrics[b]),
        penalty_count=0, dc_converged=True)
    out = opt._pick_best_case()
    return None if out is None else out[0]

# 分數有差 → 選分數高的，跟平手判定無關
check("分數有差時選分數高的",
      pick({1: (80.0, 0.1, 100.0, 100.0), 2: (90.0, 4.9, 3000.0, 9000.0)}) == 2)

# 完全打平 → 優先序 1 決定（3 棒的 Δr 最小）
check("完全打平時由 Δr_min 決定",
      pick({1: (90.0, 3.0, 1000.0, 5000.0),
            2: (90.0, 2.0, 1000.0, 5000.0),
            3: (90.0, 1.0, 1000.0, 5000.0)}) == 3)

# 三項全同 → 規則管不到，工具選棒數少的（可重現，而且 GMAT 腳本好收斂）
check("三項全同時選棒數最少的（規則外的可重現性保證）",
      pick({1: (90.0, 1.0, 1000.0, 5000.0),
            2: (90.0, 1.0, 1000.0, 5000.0),
            3: (90.0, 1.0, 1000.0, 5000.0)}) == 1)

# 全軍覆沒（fitness >= 0 代表撞毀/無效）
check("全部無效時回傳 None",
      pick({1: (0.0, 9.0, 0.0, 0.0)}, fitness={1: 0.0}) is None)


# ────────────────────────────────────────────────────────────────────────
# _tiebreak_polish：規則 §6 優先序 1 的收尾微調
# 這一段用真的軌道跑，因為它驗的是「壓小 Δr 到底要不要付分數的代價」，
# 那是計分函式跟 Lambert 幾何的真實性質，假資料驗不出來。
# ────────────────────────────────────────────────────────────────────────
import copy

import numpy as np

from src.optimizer import fast_fitness_evaluator


def polish_case(cfg, forced_offset_km=3.0):
    """把一組解的瞄準偏移硬設成 forced_offset_km，跑收尾微調，回傳前後的偏移與分數。"""
    opt = MissionOptimizer(cfg)
    sp = np.array([opt.MIN_COAST_TIME, opt.T_max, opt.MU, opt.J2_VAL, opt.J3_VAL,
                   opt.J4_VAL, opt.RE_VAL, opt.MIN_PERIAPSIS, opt.MAX_DV_SOFT,
                   opt.k_t, opt.C_t, opt.k_v, opt.C_v])
    vp = np.vstack([opt.A_r0, opt.A_v0, opt.B_r0, opt.B_v0])

    def f(v):
        return fast_fitness_evaluator(np.asarray(v, dtype=np.float64), 1, sp, vp)

    x = np.asarray(opt._generate_seed_candidates(1, 5)[0], dtype=np.float64).copy()
    x[-3] = forced_offset_km
    lb, ub = opt._generate_bounds(1)
    out = opt._tiebreak_polish(x, 1, f, opt._narrow_tolerance_bounds(x, lb, ub))
    return {"before_km": float(x[-3]), "after_km": float(out[-3]),
            "score_before": -float(f(x)), "score_after": -float(f(out)),
            "miss_after_m": opt.mission_metrics(out, 1)["miss_km"] * 1000.0}


print("\n── _tiebreak_polish：分數飽和時 Δr 是免費的 ──")
SAT = copy.deepcopy(CFG)
# 燃料與時間項都推到飽和：分數只剩距離項，而距離項在 Δr ≤ 5km 內是常數。
# 這時 fast_fitness_evaluator 對 offset_r 完全沒有梯度，搜尋會把它留在任意位置。
SAT["rules"].update({"C_v": 50000.0, "k_v": 0.05, "C_t": 1.0e9})
r = polish_case(SAT)
check(f"飽和情境：偏移 {r['before_km']*1000:,.0f} m 被壓到 {r['after_km']*1000:,.1f} m",
      r["after_km"] < 0.01)
check("飽和情境：分數沒有變差", r["score_after"] >= r["score_before"] - 1e-9)
check(f"飽和情境：真實 Δr_min 降到 {r['miss_after_m']:.3f} m", r["miss_after_m"] < 10.0)

print("\n── _tiebreak_polish：分數沒飽和時不准拿分數換名次 ──")
r2 = polish_case(copy.deepcopy(CFG))
check("未飽和情境：分數沒有變差（這是硬性條件）",
      r2["score_after"] >= r2["score_before"] - 1e-9)

print("\n── TIEBREAK_SCORE_EPS：允許用有上限的分數換名次 ──")
# 未飽和情境預設什麼都不做（上一段驗過）。把打平門檻放寬到 0.005 分後，就允許
# 「掉 0.005 分以內、換掉幾公里的 Δr」——這是賭官方比分數時會四捨五入。
EPSCFG = copy.deepcopy(CFG)
EPSCFG["strategy"]["TIEBREAK_SCORE_EPS"] = 0.005
r4 = polish_case(EPSCFG)
loss = r4["score_before"] - r4["score_after"]
check(f"門檻放寬後偏移被壓小（{r4['before_km']*1000:,.0f} m → {r4['after_km']*1000:,.1f} m）",
      r4["after_km"] < r4["before_km"] - 1e-4)
check(f"分數變化 {-loss:+.6f} 分，損失不超過設定的門檻 0.005", loss <= 0.005 + 1e-9)


print("\n── Δr 量化：低於 GMAT 打靶解析度的差距不算優勢 ──")
# 兩個方案的 Δr 差 1 公分。GMAT DifferentialCorrector 的 Achieve Tolerance 是每軸
# 10 公尺，這種差距傳不到交出去的腳本裡，不該拿來決定名次——尤其不該為此選一個
# 棒數比較多的方案。
check("Δr 差 10 公分（遠低於 10 m 解析度）時不翻盤，改由棒數少的勝",
      pick({1: (90.0, 0.1000, 1000.0, 5000.0),
            2: (90.0, 0.0999, 1000.0, 5000.0)}) == 1)
check("Δr 差 50 公尺（超過解析度）時照規則翻盤",
      pick({1: (90.0, 0.100, 1000.0, 5000.0),
            2: (90.0, 0.050, 1000.0, 5000.0)}) == 2)


print("\n── TIEBREAK_POLISH=false 時整步跳過 ──")
OFF = copy.deepcopy(SAT)
OFF["strategy"]["TIEBREAK_POLISH"] = False
r3 = polish_case(OFF)
check("關掉後偏移原封不動", abs(r3["after_km"] - r3["before_km"]) < 1e-12)

print("\n── pick_best_across_revs：REVS 集成挑哪一趟（決策 3）──")
# 各跑一趟 REVS 太貴，這裡餵假的 mission_info 驗「兩趟成績誰勝出」。
# candidate 格式：(revs, burns, times, mission_info)；失敗那趟是 (revs, None, None, (None, None))。


def _mi(score, miss_km, dv, t):
    return {"score": score, "miss_km": miss_km, "total_dv_mps": dv, "T_team": t}


def revs_pick(cands):
    """cands: [(revs, mission_info 或 None)]，回傳 (勝出的 revs, floor 讀法是否翻盤)。"""
    full = [(r, ([0.0] if m else None), ([0.0] if m else None), (m if m else (None, None)))
            for r, m in cands]
    i, fd = pick_best_across_revs(full)
    return full[i][0], fd


check("分數高的那趟勝（REVS=4 高分）",
      revs_pick([(0, _mi(89.0, 0.1, 100.0, 100.0)),
                 (4, _mi(90.5, 3.0, 3000.0, 9000.0))])[0] == 4)

check("同分時 Δr_min 小的那趟勝（REVS=0 較近）",
      revs_pick([(0, _mi(90.0, 0.1, 2000.0, 9000.0)),
                 (4, _mi(90.0, 3.0, 1500.0, 3000.0))])[0] == 0)

check("一趟全軍覆沒時採用另一趟",
      revs_pick([(0, _mi(88.0, 0.2, 500.0, 4000.0)), (4, None)])[0] == 0)

check("兩趟都全軍覆沒時回傳最後一趟（讓呼叫端照樣回傳失敗結果）",
      revs_pick([(0, None), (4, None)])[0] == 4)

# floor_miss 兩種讀法翻盤時要回報 True（呼叫端負責講白，不偷偷選）
_amb = revs_pick([(0, _mi(90.0, 0.3, 2000.0, 5000.0)),
                  (4, _mi(90.0, 3.4, 1990.0, 4900.0))])
check("原始距離讀法選近的（REVS=0）", _amb[0] == 0)
check("floor 讀法會翻盤時 floor_disagrees=True", _amb[1] is True)
check("兩種讀法一致時 floor_disagrees=False",
      revs_pick([(0, _mi(90.0, 0.1, 100.0, 100.0)),
                 (4, _mi(90.5, 3.0, 3000.0, 9000.0))])[1] is False)


print()
if FAILS:
    print(f"❌ {len(FAILS)} 項失敗：" + "、".join(FAILS))
    sys.exit(1)
print("✅ 全部通過")
