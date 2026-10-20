"""排位賽搜尋懲罰 v2（失格層）的驗證（`uv run python tests/test_ranking_penalty_v2.py`）。

起因見 docs/RANKING_MC_20261019.md：1cd196d 的總 Δv 軟懲罰「−10 − 0.01×超出量」比陡的時間項
便宜，搜尋會選總 Δv 超標的路線。v2 的修法與結果見 docs/RANKING_PENALTY_V2_20261019.md。

分六塊：
  1. 數學保證：任何合法層分數（≥ 0）> 任何失格層分數（< −10）> 排位賽模式的搜尋失敗（−30），
     跟計分參數無關；失格層對違規量嚴格單調下降。
  2. 報告的兩個反例：舊算法選超標那條、v2 選合法那條。
  3. 單棒超標分類：終端棒在拆棒範圍內維持 −10（或 C4 拆後估計），超出範圍 / 前導棒超標進失格層。
  4. C4 可拆倍數 K 由拆棒器最大段數推出（排位賽），初賽維持 5 倍。
  5. fast_fitness_evaluator：同一個決策向量在排位賽模式的分層；撞地球回 −30（低於失格層）。
  6. config_validator：MAX_DV_MPS ≤ 250 沒填 MAX_TOTAL_DV_MPS 直接擋。
  7. 找不到合法路線：記下最接近的失格候選、存 no_legal_route.json（--from-mission 讀不進去、
     不產生腳本）、NoLegalRouteError / 結束碼 3。真的跑一次 main.py 的 e2e 見
     tests/test_no_legal_route_e2e.py（SLOW）。
"""

import copy
import inspect
import json
import math
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.optimizer import (MissionOptimizer, fast_fitness_evaluator, SPLITTER_MAX_SEG,
                           PRELIM_TERMINAL_MAX_FACTOR)
from src.scorer import (calculate_score, ranked_search_score, assess_legality,
                        DQ_TIER_TOP, DQ_TIER_SPAN, SEARCH_FAIL_SCORE_RANKED)
from src.burn_splitter import legalize_route
from src.config_validator import validate_config, ConfigValidationError
from src.pipeline_artifacts import load_mission
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


def old_search_score(miss_km, t, dv, n_soft, kt, ct, kv, cv, cap_total):
    """1cd196d 的搜尋分數（對照組）：calculate_score − (10 + 0.01 × 超出量)，地板 0。"""
    sc = calculate_score(miss_km, t, dv, n_soft, kt, ct, kv, cv)
    excess = dv - cap_total
    if excess > 1e-5:
        sc = max(sc - (10.0 + 0.01 * excess), 0.0)
    return sc


CKPT = os.path.join(ROOT, "docs", "solutions", "checkpoints", "contest_route88.32_seed0_presplit.json")
with open(CKPT, encoding="utf-8") as f:
    _ck = json.load(f)
BASE = _ck["config"]                     # contest：cap 1500、沒設總 Δv 上限
X = np.asarray(_ck["mission_info"]["x"], dtype=np.float64)   # 3 棒、終端 4,691 m/s
N = int(_ck["mission_info"]["num_burns"])
with open(os.path.join(ROOT, "configs", "shared", "hyperbolic_test.json"), encoding="utf-8") as f:
    HYP = json.load(f)                   # 初賽式計分參數（C_v = 9,064 m/s）


def make(cfg_base, rules=None, strategy=None):
    cfg = copy.deepcopy(cfg_base)
    cfg["rules"].update(rules or {})
    cfg.setdefault("strategy", {}).update(strategy or {})
    return MissionOptimizer(cfg)


RANK = {"MAX_DV_MPS": 250.0, "MAX_TOTAL_DV_MPS": 3000.0}

print("── 1. 數學保證 ──")
check("失格層上界 < 0（合法層地板）", DQ_TIER_TOP < 0.0)
check("搜尋失敗 < 失格層下界", SEARCH_FAIL_SCORE_RANKED < DQ_TIER_TOP - DQ_TIER_SPAN)
rng = np.random.default_rng(0)
worst_legal, best_dq = math.inf, -math.inf
for _ in range(20000):
    kt, kv = 10 ** rng.uniform(-5, -1), 10 ** rng.uniform(-5, -1)
    ct, cv = rng.uniform(0, 1e5), rng.uniform(0, 2e4)
    miss, t, dv = rng.uniform(0, 500), rng.uniform(0, 1e5), rng.uniform(0, 3000)
    n_soft = int(rng.integers(0, 3))
    worst_legal = min(worst_legal, ranked_search_score(
        calculate_score(miss, t, dv, n_soft, kt, ct, kv, cv), dv, 3000.0, 0.0))
    dv_bad = 3000.0 + 10 ** rng.uniform(-4, 6)
    best_dq = max(best_dq, ranked_search_score(
        calculate_score(rng.uniform(0, 5), 0.0, dv_bad, 0, kt, ct, kv, cv), dv_bad, 3000.0,
        float(rng.uniform(0, 1) < 0.5) * 10 ** rng.uniform(-3, 5)))
check(f"隨機計分參數 20,000 組：最差合法 {worst_legal:.4f} > 最好失格 {best_dq:.4f}", worst_legal > best_dq)
vs = [1e-4, 1e-2, 1.0, 10.0, 100.0, 1e3, 1e4, 3.2e5, 1e7]
tier = [ranked_search_score(99.0, 3000.0 + v, 3000.0, 0.0) for v in vs]
check("失格層對總 Δv 超出量嚴格單調下降（1e-4 … 1e7 m/s）",
      all(a > b for a, b in zip(tier, tier[1:])))
tier_s = [ranked_search_score(99.0, 1000.0, 3000.0, v) for v in vs]
check("失格層對單棒超出量嚴格單調下降", all(a > b for a, b in zip(tier_s, tier_s[1:])))
check("失格層只看違規量，不看時間/燃料項（Deb 可行性法則）",
      ranked_search_score(99.0, 3500.0, 3000.0, 0.0) == ranked_search_score(1.0, 3500.0, 3000.0, 0.0))
check("沒有上限（初賽，cap ≤ 0）→ 分數原樣", ranked_search_score(42.0, 1e6, 0.0, 0.0) == 42.0)

print("\n── 2. 報告反例 ──")
# 反例 A：hyperbolic_test_fuel 的佔位參數（k_v=0.002、C_v=2,500），距離都 3.49 km。
fuel = make(HYP, dict(RANK, k_v=0.002, C_v=2500.0))
kA = (fuel.k_t, fuel.C_t, fuel.k_v, fuel.C_v)
old_fast = old_search_score(3.49, 2000.0, 3500.0, 0, *kA, 3000.0)
old_slow = old_search_score(3.49, 7000.0, 2800.0, 0, *kA, 3000.0)
check(f"A 對照：舊算法選超標（快 {old_fast:.2f} > 慢 {old_slow:.2f}，報告 62.98 / 61.92）",
      old_fast > old_slow and abs(old_fast - 62.98) < 0.01 and abs(old_slow - 61.92) < 0.01)
new_fast = fuel.ranking_score(3.49, 2000.0, 3500.0, 0)
new_slow = fuel.ranking_score(3.49, 7000.0, 2800.0, 0)
check(f"A：v2 選合法（慢、合法 2,800 m/s @ 7,000 s {new_slow:.2f} > 快、超標 3,500 m/s @ 2,000 s {new_fast:.2f}）",
      new_slow > new_fast and new_slow == old_slow)
# 反例 B：初賽式參數（C_v = 9,064 m/s，燃料項在 3 km/s 以內幾乎是平的）。
pre_style = make(HYP, RANK)
kB = (pre_style.k_t, pre_style.C_t, pre_style.k_v, pre_style.C_v)
old_fast = old_search_score(3.49, 3000.0, 4000.0, 0, *kB, 3000.0)
old_slow = old_search_score(3.49, 7000.0, 2900.0, 0, *kB, 3000.0)
check(f"B 對照：舊算法選超標（快 {old_fast:.2f} > 慢 {old_slow:.2f}，報告 79.94 / 78.05）",
      old_fast > old_slow and abs(old_fast - 79.94) < 0.01 and abs(old_slow - 78.05) < 0.01)
new_fast = pre_style.ranking_score(3.49, 3000.0, 4000.0, 0)
new_slow = pre_style.ranking_score(3.49, 7000.0, 2900.0, 0)
check(f"B：v2 選合法（2,900 m/s @ 7,000 s {new_slow:.2f} > 4,000 m/s @ 3,000 s {new_fast:.2f}）",
      new_slow > new_fast)
# 合法層再差（時間、燃料都飽和到 0 附近）也贏超標 1 m/s 的路線。
check("合法層幾乎 0 分（T、Δv 都很差、Δr 300 km）仍勝過超標 0.01 m/s",
      pre_style.ranking_score(300.0, 1e5, 2999.0, 0) > pre_style.ranking_score(3.49, 0.0, 3000.01, 0))

print("\n── 3. 單棒超標分類（排位賽模式）──")
r = make(BASE, RANK)                         # cap 250 → MAX_DV_SOFT 248，K = 14 → 3,472 m/s
lim = r.SPLIT_LIMIT * 1000.0
check(f"拆棒範圍 = 最大段數 × (cap − margin) = {SPLITTER_MAX_SEG} × 248 = {lim:,.0f} m/s",
      abs(lim - SPLITTER_MAX_SEG * 248.0) < 1e-6)


def terms(opt, dvs_mps):
    leg = assess_legality(dvs_mps, [100.0 * i for i in range(len(dvs_mps))], opt.MAX_DV * 1000.0,
                          opt.MIN_COAST_TIME, opt.MAX_TOTAL_DV_MPS)
    return opt._search_score_terms(leg, [d / 1000.0 for d in dvs_mps])


check("終端 1,000 m/s（範圍內）→ 軟懲罰 1 次、不進失格層", terms(r, [200.0, 1000.0]) == (1, 0.0))
n_s, v = terms(r, [200.0, 3600.0])
check(f"終端 3,600 m/s（超出範圍）→ 失格量 = 3,600 − {lim:,.0f} = {v:.3f}",
      n_s == 0 and abs(v - (3600.0 - lim)) < 1e-6)
n_s, v = terms(r, [300.0, 200.0])
check("前導棒 300 m/s（拆棒器只拆終端）→ 失格量 = 300 − 248", n_s == 0 and abs(v - 52.0) < 1e-6)
legal_low = r.ranking_score(3.49, 7900.0, 2900.0, 0)           # 合法、很晚
split_ok = r.ranking_score(3.49, 2000.0, 1000.0, 1)            # 終端可拆，−10 軟懲罰
split_far = r.ranking_score(3.49, 2000.0, 2000.0, 0, 3600.0 - lim)
check(f"範圍內的超標仍是合法層、照分數比（可拆 {split_ok:.2f} 可以贏合法 {legal_low:.2f}）",
      split_ok >= 0.0 and split_ok > legal_low)
check(f"超出範圍 → 排在任何合法候選後面（{split_far:.2f} < {legal_low:.2f}）", split_far < 0.0 < legal_low)
check("超出範圍的分數隨超標量單調下降",
      r.ranking_score(3.49, 2000.0, 2000.0, 0, 10.0) > r.ranking_score(3.49, 2000.0, 2000.0, 0, 100.0))
nosplit = make(BASE, RANK, {"AUTO_SPLIT_LEGALIZE": False})
check("不拆棒（AUTO_SPLIT_LEGALIZE 關）→ 任何超標都拆不掉，終端 300 m/s 也進失格層",
      nosplit.SPLIT_LIMIT == nosplit.MAX_DV_SOFT and terms(nosplit, [100.0, 300.0])[1] > 0.0)
pre = make(BASE)
check("初賽模式：單棒超標照舊每棒 −10，不進失格層", terms(pre, [1600.0, 9000.0]) == (2, 0.0))

print("\n── 4. C4 可拆倍數 K ──")
check(f"拆棒器最大段數讀自 legalize_route 預設值（{SPLITTER_MAX_SEG}）",
      SPLITTER_MAX_SEG == inspect.signature(legalize_route).parameters["max_seg"].default)
check(f"排位賽模式 K = 拆棒器最大段數（{r.SPLIT_AWARE_TERMINAL_MAX_FACTOR:g}，不是固定 5）",
      r.SPLIT_AWARE_TERMINAL_MAX_FACTOR == float(SPLITTER_MAX_SEG))
check("250 m/s 時可拆到 ~3,470 m/s（舊 5 倍只有 1,240）", 3400.0 < lim < 3500.0)
check(f"初賽模式 K 維持 {PRELIM_TERMINAL_MAX_FACTOR:g}（逐位元同舊行為）",
      pre.SPLIT_AWARE_TERMINAL_MAX_FACTOR == PRELIM_TERMINAL_MAX_FACTOR)
check("config 有寫 K 就照 config",
      make(BASE, RANK, {"SPLIT_AWARE_TERMINAL_MAX_FACTOR": 3.0}).SPLIT_AWARE_TERMINAL_MAX_FACTOR == 3.0)

print("\n── 5. fast_fitness_evaluator ──")
vec = np.vstack([pre.A_r0, pre.A_v0, pre.B_r0, pre.B_v0])


def fit(opt, x=X, n=N):
    return -float(fast_fitness_evaluator(np.asarray(x, dtype=np.float64), n, opt._scalar_params(), vec))


s_pre = fit(pre)
s_1500 = fit(make(BASE, {"MAX_TOTAL_DV_MPS": 1e6}))    # 排位賽模式、cap 1500：終端 3.13× 在範圍內
check(f"排位賽模式、終端在範圍內、總 Δv 沒超 → 合法層，跟初賽同分（{s_1500:.4f}）", s_1500 == s_pre)
s_far = fit(make(BASE, {"MAX_DV_MPS": 250.0, "MAX_TOTAL_DV_MPS": 1e6}))   # 終端 4,691 > 3,472
check(f"cap 250：終端 4,691 m/s 超出拆棒範圍 → 失格層（{s_far:.4f}）", -20.0 < s_far < -10.0)
s_tot = fit(make(BASE, {"MAX_TOTAL_DV_MPS": 3000.0}))
check(f"總 Δv ~6,200 > 3,000 → 失格層（{s_tot:.4f}）", -20.0 < s_tot < -10.0)
check("失格層比較：總 Δv 超 3,200 m/s 比終端超 1,220 m/s 更低（v 越大越低）", s_tot < s_far)
s_both = fit(make(BASE, RANK))
check(f"兩種都超 → 違規量相加，分數更低（{s_both:.4f}）", s_both < min(s_tot, s_far))
# 撞地球：t=0 在 B 的軌道上逆向燒 248 m/s，滑行半圈經過近地點（~6,160 km < 安全半徑）。
rb = make(BASE, RANK)
vb = rb.B_v0
x_crash = np.array([0.0, rb.MAX_DV_SOFT, math.acos(-vb[2] / np.linalg.norm(vb)),
                    math.atan2(-vb[1], -vb[0]), 0.0, 0.5, 0.0, 0.0, 0.0])
period = 2 * math.pi * math.sqrt(np.linalg.norm(rb.B_r0) ** 3 / rb.MU)
x_crash[4] = (period * 0.6 - rb.MIN_COAST_TIME) / (rb.T_max - 2 * rb.MIN_COAST_TIME)
check(f"排位賽模式撞地球 → {SEARCH_FAIL_SCORE_RANKED:g}（低於失格層）",
      fit(rb, x_crash, 2) == SEARCH_FAIL_SCORE_RANKED)
check("初賽模式撞地球 → 0（舊行為）", fit(pre, x_crash, 2) == 0.0)

print("\n── 6. config_validator ──")
b250 = copy.deepcopy(BASE)
b250["rules"]["MAX_DV_MPS"] = 250.0
check("MAX_DV_MPS = 250、沒填 MAX_TOTAL_DV_MPS → 擋", rejected(b250))
b250["rules"]["MAX_TOTAL_DV_MPS"] = None
check("MAX_DV_MPS = 250、MAX_TOTAL_DV_MPS = null → 擋", rejected(b250))
b250["rules"]["MAX_TOTAL_DV_MPS"] = 3000.0
check("MAX_DV_MPS = 250、MAX_TOTAL_DV_MPS = 3000 → 通過", not rejected(b250))
b100 = copy.deepcopy(BASE)
b100["rules"]["MAX_DV_MPS"] = 100.0
check("MAX_DV_MPS = 100（更嚴）沒填總上限 → 也擋", rejected(b100))
check("MAX_DV_MPS = 1500（初賽）沒填總上限 → 通過", not rejected(copy.deepcopy(BASE)))

print("\n── 7. 找不到合法路線 ──")
nl = make(BASE, RANK)               # cap 250：X 的終端 4,691 m/s、總 6,200 m/s → 失格層
fx = float(nl._fitness_wrapper(N)(X))
check(f"前提：X 在排位賽模式下的 fitness 在失格層（{-fx:.4f}）", 10.0 < fx < 20.0)
nl.burn_case_results = {N: {"fitness": fx, "best_x": X.copy(), "epochs_run": 1, "note": ""}}
check("_pick_best_case：只有失格層候選 → None", nl._pick_best_case() is None)
check("記下最接近合法的候選（棒數、x、fitness）",
      nl.no_legal_route is not None and nl.no_legal_route["burns"] == N
      and np.array_equal(nl.no_legal_route["x"], X) and nl.no_legal_route["fitness"] == fx)
pre_nl = make(BASE)
pre_nl.burn_case_results = {N: {"fitness": 0.0, "best_x": X.copy(), "epochs_run": 1, "note": ""}}
check("初賽模式 / 搜尋失敗（fitness 0）不記", pre_nl._pick_best_case() is None and pre_nl.no_legal_route is None)

with tempfile.TemporaryDirectory() as td:
    p = app.save_no_legal_route(Path(td) / "no_legal_route.json", nl)
    d = json.loads(p.read_text(encoding="utf-8"))
    v = d["violations"]
    check("no_legal_route.json：stage = no_legal_route、含 config / burns / times / mission_info",
          d["stage"] == "no_legal_route" and all(k in d for k in ("config", "burns", "times", "mission_info")))
    term = v["over_cap_burns"][-1] if v["over_cap_burns"] else {}
    check(f"違規量：終端第 {term.get('burn')} 棒 {term.get('dv_mps', 0):,.1f} m/s 超 "
          f"{term.get('over_cap_mps', 0):,.1f}、超出拆棒範圍；總 Δv 超 {v['total_dv_excess_mps']:,.1f}",
          term.get("burn") == N and term.get("over_cap_mps", 0) > 4000.0 and term.get("splittable") is False
          and v["total_dv_excess_mps"] > 3000.0 and abs(v["splitter_limit_mps"] - 3472.0) < 1e-6
          and len(v["per_burn_dv_mps"]) == N)
    check("有下一步建議（MAXITER、種子、MAX_BURNS、feasibility.py）",
          any("MAXITER" in t for t in d["next_steps"]) and any("feasibility" in t for t in d["next_steps"])
          and any("MAX_BURNS" in t for t in d["next_steps"]))
    try:
        load_mission(p)
        check("--from-mission 讀不進去（不會被拿去產繳交腳本）", False)
    except ValueError:
        check("--from-mission 讀不進去（不會被拿去產繳交腳本）", True)

    cfg_path = Path(td) / "cfg.json"
    cfg_path.write_text(json.dumps(nl.config), encoding="utf-8")
    run_dir = Path(td) / "run"
    nl2 = make(BASE, RANK)
    nl2.no_legal_route = nl.no_legal_route
    raised = None
    with patch.object(app, "run_seed_portfolio", return_value=(None, None, None, nl2)):
        try:
            app.main(["--config", str(cfg_path), "--run-dir", str(run_dir), "--quiet"])
        except app.NoLegalRouteError as exc:
            raised = exc
    check("main：找不到合法路線 → NoLegalRouteError（不是通用 RuntimeError）", raised is not None)
    run_json = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    check("run.json status = no_legal_route、指到存檔", run_json["status"] == "no_legal_route"
          and run_json.get("no_legal_route", "").endswith("no_legal_route.json"))
    produced = sorted(q.name for q in run_dir.iterdir())
    check(f"run 目錄有 no_legal_route.json、沒有 mission.json / 任何腳本（{produced}）",
          "no_legal_route.json" in produced and "mission.json" not in produced
          and not any(n.endswith(".script") for n in produced))
    check("結束碼 3（跟一般錯誤 1 分開）", app.EXIT_NO_LEGAL_ROUTE == 3)
    raised = None
    with patch.object(app, "run_seed_portfolio", return_value=(None, None, None, make(BASE, RANK))):
        try:
            app.main(["--config", str(cfg_path), "--run-dir", str(Path(td) / "run2"), "--quiet"])
        except RuntimeError as exc:
            raised = exc
    check("沒有失格候選的一般搜尋失敗 → 照舊通用 RuntimeError",
          raised is not None and not isinstance(raised, app.NoLegalRouteError))

print()
if FAILS:
    print(f"❌ {len(FAILS)} 項失敗：" + "、".join(FAILS))
    sys.exit(1)
print("✅ 全部通過")
