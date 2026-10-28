"""排位賽硬性限制的驗證（`uv run python tests/test_ranking_rules.py`）。

規則見 docs/RANKING_ROUND_RULES_20261006.md：
  * 單棒 Δv > MAX_DV_MPS + 1e-5 m/s → 失格（初賽是每次扣 10 分）
  * 總 Δv > MAX_TOTAL_DV_MPS → 失格（選填；沒填 = 沒有上限，初賽行為）
  * 機動間隔 < 100 s → 每次扣 10 分（不變，penalty_count 只剩這個）

分五塊：
  1. src.scorer：assess_legality（最終判定）/ ranked_search_score（搜尋失格層）/ calculate_score 不變
  2. config_validator：MAX_TOTAL_DV_MPS 選填驗證、ranking_round.json 範本
  3. fast_fitness_evaluator：沒設總上限時跟舊 19 格 scalars 逐位元相同；設了才進失格層
（失格層的數學保證與報告反例見 tests/test_ranking_penalty_v2.py）
  4. mission_metrics / _replay_mission：搜尋用分數跟舊算法一致，另外標失格、官方分數
  5. main：失格解一律排在合法解後面、拆棒只看單棒超標、舊存檔相容

決策向量取自 docs/solutions/checkpoints/ 的 contest 拆棒前存檔（3 棒、終端 4,691 m/s ≈ 3.13× cap）。
"""

import copy
import json
import os
import sys
from unittest.mock import patch

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.optimizer import (MissionOptimizer, fast_fitness_evaluator, reconstruct_mission_logs,
                           is_disqualified, over_dv_count)
from src.scorer import (calculate_score, assess_legality, ranked_search_score,
                        DV_LIMIT_TOL_MPS)
from src.config_validator import validate_config, ConfigValidationError
import main as app

FAILS = []


def check(name, cond):
    print(("  ✅ " if cond else "  ❌ ") + name)
    if not cond:
        FAILS.append(name)


def rejected(cfg):
    try:
        validate_config(cfg)
        return False
    except ConfigValidationError:
        return True


CKPT = os.path.join(ROOT, "docs", "solutions", "checkpoints", "contest_route88.32_seed0_presplit.json")
with open(CKPT, encoding="utf-8") as f:
    _ck = json.load(f)
BASE = _ck["config"]
# 這支是跟「舊算法」逐位元比對，舊算法沒有星曆快取；快取本身的精度由 test_ephem_cache.py 驗。
BASE.setdefault("strategy", {})["EPHEM_CACHE"] = False
X = np.asarray(_ck["mission_info"]["x"], dtype=np.float64)
N = int(_ck["mission_info"]["num_burns"])


def make_opt(**rules):
    cfg = copy.deepcopy(BASE)
    cfg["rules"].update(rules)
    return MissionOptimizer(cfg)


print("── 1. scorer ──")
leg = assess_legality([100.0, 250.0 + 0.9 * DV_LIMIT_TOL_MPS], [0.0, 100.0], 250.0, 100.0)
check("恰在 250 + 1e-5 m/s 以內不算超標", not leg["disqualified"] and leg["over_dv_count"] == 0)
leg = assess_legality([100.0, 250.00002], [0.0, 100.0], 250.0, 100.0)
check("超過 250 + 1e-5 m/s → 失格，不算進 penalty_count",
      leg["disqualified"] and leg["over_dv_legs"] == [1] and leg["penalty_count"] == 0)
leg = assess_legality([100.0, 100.0, 100.0], [0.0, 99.0, 300.0], 250.0, 100.0)
check("機動間隔 99 s → penalty_count=1、不失格", leg["penalty_count"] == 1 and not leg["disqualified"])
leg = assess_legality([100.0, 100.0], [0.0, 100.0 - 1e-9], 250.0, 100.0)
check("間隔差浮點雜訊等級不算違規", leg["penalty_count"] == 0)
leg = assess_legality([1400.0] * 4, [0.0, 100.0, 200.0, 300.0], 1500.0, 100.0)
check("沒設總 Δv 上限（初賽）→ 總 5,600 m/s 也不失格", not leg["disqualified"] and not leg["total_dv_over"])
leg = assess_legality([240.0] * 13, [100.0 * i for i in range(13)], 250.0, 100.0, 3000.0)
check("總 Δv 3,120 > 3,000 → 失格", leg["disqualified"] and leg["total_dv_over"] and leg["over_dv_count"] == 0)
leg = assess_legality([250.0] * 12, [100.0 * i for i in range(12)], 250.0, 100.0, 3000.0)
check("總 Δv 剛好 3,000 → 不失格", not leg["disqualified"])
check("失格層：沒上限 / 上限內 → 分數原樣",
      ranked_search_score(77.0, 5000.0, 0.0, 0.0) == 77.0 and ranked_search_score(77.0, 3000.0, 3000.0, 0.0) == 77.0)
check("失格層：總 Δv 超 100 m/s → 分數落在 [−20, −10)",
      -20.0 < ranked_search_score(77.0, 3100.0, 3000.0, 0.0) < -10.0)
base = calculate_score(1.0, 5000.0, 1000.0, 0, 1e-4, 11000.0, 5e-3, 1200.0)
check("calculate_score 舊行為不變：penalty_count 每次 −10",
      abs(calculate_score(1.0, 5000.0, 1000.0, 2, 1e-4, 11000.0, 5e-3, 1200.0) - (base - 20.0)) < 1e-9)

print("\n── 2. config_validator ──")
ok = copy.deepcopy(BASE)
check("沒有 MAX_TOTAL_DV_MPS（初賽 config）照樣通過", not rejected(ok))
ok["rules"]["MAX_TOTAL_DV_MPS"] = None
check("MAX_TOTAL_DV_MPS = null 通過（= 沒有上限）", not rejected(ok))
for bad in (0, -1.0, "3000", True):
    b = copy.deepcopy(BASE)
    b["rules"]["MAX_TOTAL_DV_MPS"] = bad
    check(f"MAX_TOTAL_DV_MPS = {bad!r} 會被擋", rejected(b))
with open(os.path.join(ROOT, "configs", "shared", "ranking_round.json"), encoding="utf-8") as f:
    rr = json.load(f)
check("configs/shared/ranking_round.json 通過驗證、規則數字是 250 / 3000",
      not rejected(rr) and rr["rules"]["MAX_DV_MPS"] == 250.0 and rr["rules"]["MAX_TOTAL_DV_MPS"] == 3000.0)
rr_opt = MissionOptimizer(rr)
check("ranking_round 的 optimizer 讀到總 Δv 上限", rr_opt.MAX_TOTAL_DV_MPS == 3000.0)

print("\n── 3. fast_fitness_evaluator ──")
pre = make_opt()
check("初賽 config：MAX_TOTAL_DV_MPS = None、scalars[19] = 0",
      pre.MAX_TOTAL_DV_MPS is None and pre._scalar_params()[19] == 0.0)
vec = np.vstack([pre.A_r0, pre.A_v0, pre.B_r0, pre.B_v0])
sc = pre._scalar_params()
f20 = fast_fitness_evaluator(X, N, sc, vec)
f19 = fast_fitness_evaluator(X, N, sc[:19].copy(), vec)
check("沒設總上限時跟舊 19 格 scalars 逐位元相同", f20 == f19)
check("沒設總上限時跟 20 格 scalars（1cd196d）逐位元相同",
      fast_fitness_evaluator(X, N, sc[:20].copy(), vec) == f20)
check("基準解的搜尋分數 > 0（測試前提）", f20 < 0.0)
cap = make_opt(MAX_TOTAL_DV_MPS=3000.0)
fcap = fast_fitness_evaluator(X, N, cap._scalar_params(), vec)
check("總 Δv ~6,200 m/s、上限 3,000 → 搜尋分數進失格層 [−20, −10)", -20.0 < -fcap < -10.0)
loose = make_opt(MAX_TOTAL_DV_MPS=1e6)
check("上限遠大於總 Δv → 分數跟沒設一樣",
      fast_fitness_evaluator(X, N, loose._scalar_params(), vec) == f20)

print("\n── 4. mission_metrics / _replay_mission ──")
logs, times, miss, *_ = reconstruct_mission_logs(
    X, N, pre.MIN_COAST_TIME, pre.T_max, pre.A_r0, pre.A_v0, pre.B_r0, pre.B_v0,
    pre.MU, pre.J2_VAL, pre.J3_VAL, pre.J4_VAL, pre.RE_VAL, pre.LAMBERT_MAX_REVS, pre.MIN_PERIAPSIS)
old_pen = sum(1 for bl in logs if bl["dv_mag"] > pre.MAX_DV)
old_score = calculate_score(miss, float(times[-1]), sum(bl["dv_mag"] for bl in logs) * 1000.0, old_pen,
                            pre.k_t, pre.C_t, pre.k_v, pre.C_v)
m = pre.mission_metrics(X, N)
check("初賽 config：搜尋用分數跟舊算法（超標每棒 −10）完全相同", m["score"] == float(old_score))
check("超標棒 → over_dv_count、失格、沒有官方分數；penalty_count 只算間隔（0）",
      m["over_dv_count"] == old_pen >= 1 and m["disqualified"] and m["official_score"] is None
      and m["penalty_count"] == 0 and not m["total_dv_over"])
mc = cap.mission_metrics(X, N)
check("加總 Δv 上限 → 兩個失格原因、搜尋用分數進失格層",
      mc["total_dv_over"] and len(mc["dq_reasons"]) == 2 and -20.0 < mc["score"] < -10.0)
check("拆後估計也在失格層（不把 −10 加回來）",
      mc["score_split_est"] == mc["score"] and mc["split_terminal_count"] == 1)

wide = make_opt(MAX_DV_MPS=1e5)   # 單棒上限放到 100 km/s → 這組解變合法
mw = wide.mission_metrics(X, N)
check("合法解：不失格、official_score == score",
      not mw["disqualified"] and mw["official_score"] == mw["score"] and mw["over_dv_count"] == 0)
with patch.object(pre, "_report_level", 10):
    _, _, mi = pre._replay_mission(X, N)
check("_replay_mission 報表標失格、不印成正常分數",
      mi["disqualified"] and "失格" in mi["report_text"] and "搜尋用分數" in mi["report_text"])
check("_replay_mission 的搜尋用分數跟 mission_metrics 一致", mi["score"] == m["score"])
with patch.object(wide, "_report_level", 10):
    _, _, miw = wide._replay_mission(X, N)
check("_replay_mission 合法解照常印分數", not miw["disqualified"] and "失格" not in miw["report_text"])

print("\n── 5. main ──")
legal = {"score": 50.0, "miss_km": 0.1, "total_dv_mps": 2000.0, "T_team": 9000.0,
         "disqualified": False, "over_dv_count": 0, "penalty_count": 0}
dq = dict(legal, score=95.0, disqualified=True, over_dv_count=1)
check("_final_rank_key：失格解分數再高也排在合法解後面",
      app._final_rank_key(legal) < app._final_rank_key(dq))
check("舊存檔（只有 penalty_count）相容：penalty_count>0 視為單棒超標失格",
      is_disqualified({"penalty_count": 1}) and over_dv_count({"penalty_count": 1}) == 1
      and not is_disqualified({"penalty_count": 0}))
interval_only = dict(legal, penalty_count=1, x=X, num_burns=N)
check("只有間隔違規（沒超標）→ 不進拆棒器",
      app.legalize_violating_winner(BASE, None, None, interval_only, pre) is None)

warned = []
with patch.object(app.log, "warning", side_effect=lambda msg, *a, **k: warned.append(msg)), \
     patch.object(app.log, "info"):
    app.print_score_breakdown(mi, pre)
    app.print_score_breakdown(mc | {"total_dv_mps": mc["dv_mps"], "T_team": mc["t_team"]}, cap)
check("分數拆解（失格解、含失格層）加總跟記錄的搜尋用分數一致", not warned)

print()
if FAILS:
    print(f"❌ {len(FAILS)} 項失敗：" + "、".join(FAILS))
    sys.exit(1)
print("✅ 全部通過")
