"""前導棒等分、重播分類與 primer 拆後比較的回歸；直接執行，失敗 exit 1。"""
import copy
import math
import json
import os
import pickle
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import main as app
from src.optimizer import MissionOptimizer
from src.burn_splitter import presplit_leading, leading_arcs_min_radius
from src.config_validator import ConfigValidationError, validate_config

FAILS = []


def check(name, cond):
    print(("  ✅ " if cond else "  ❌ ") + name)
    if not cond:
        FAILS.append(name)


def config(**strategy):
    cfg = copy.deepcopy(app.DEFAULT_CONFIG)
    for name in ("orbit_A", "orbit_B"):
        cfg[name].update(SMA=12000., ECC=0., INC=0., RAAN=0., AOP=0., TA=0.)
    cfg["rules"].update(MAX_DV_MPS=250., MAX_TOTAL_DV_MPS=3000., T_MAX_SEC=6000.)
    cfg["strategy"].update(GRAVITY_DEGREE=0, EPHEM_CACHE=False, LAMBERT_MAX_REVS=0,
                           SPLIT_N_SPAN=0, SPLIT_NLP_MAXITER=1, SPLIT_MULTISTART=None,
                           SPLIT_PRUNE_REOPT_MPS=0, SPLIT_WORKERS=1, SPLIT_WALL_BUDGET_SEC=0)
    cfg["strategy"].update(strategy)
    cfg["optimization"]["SEED"] = 7
    return cfg


print("── 1. 前導棒等分幾何 ──")
r = presplit_leading(500., [[.6, 0., 0.]], [600.], 1500., cap=.248, min_coast=100.)
t0, dvs, coasts, terminal = r
check("600 m/s → 三段各 200 m/s", len(dvs) == 3 and np.allclose(dvs, [[.2, 0., 0.]] * 3))
check("中段在原時刻、段間 100 s、抵達仍為 2600 s",
      t0 == 400. and coasts == [100., 100., 500.] and terminal == 1500.
      and t0 + coasts[0] == 500. and t0 + sum(coasts) + terminal == 2600.)
r2 = presplit_leading(100., [[.6, 0., 0.], [0., .6, 0.]], [100., 100.], 500.,
                       cap=.248, min_coast=100.)
check("相鄰兩發各拆三段，第二組被推到 300、400、500 s",
      r2[0] == 0. and r2[2] == [100.] * 6 and r2[3] == 200.
      and np.allclose(r2[1], [[.2, 0., 0.]] * 3 + [[0., .2, 0.]] * 3))
check("終端滑行不足回 None", presplit_leading(
    0., [[.6, 0., 0.]], [100.], 200., cap=.248, min_coast=100.) is None)
empty = presplit_leading(50., [[1e-10, 0., 0.]], [200.], 300., cap=.248, min_coast=100.)
check("空燒丟掉、改從原終端時刻開始", empty == (250., [], [], 300.))
edge = presplit_leading(0., [[.496, 0., 0.]], [100.], 200., cap=.248, min_coast=100.)
check("起點不早於零、終端往後推且剛好保留最小滑行",
      edge[0] == 0. and edge[2] == [100., 100.] and edge[3] == 100.)

print("\n── 2. 真實拆棒與重播分類 ──")
on = MissionOptimizer(config(SPLIT_LEADING=True))
off_cfg = config(SPLIT_LEADING=False)
off = MissionOptimizer(off_cfg)
# t0=500 s、前導滑行=600 s、終端滑行=1500 s，第一發徑向 600 m/s。
x = np.array([500., .6, math.pi / 2, 0., 500. / 5300., 1400. / 4800., 0., 0., 0.])
burns, times, mi = on._replay_mission(x, 2)
mon, moff = on.mission_metrics(x, 2), off.mission_metrics(x, 2)
check("關閉進失格層，開啟進合法搜尋層", moff["score"] < 0. <= mon["score"])
check("重播與安靜重播都記下一發可拆前導棒",
      mon["split_leading_count"] == mi["split_leading_count"] == 1)
# 終端棒的估計貢獻另扣除，前導棒應正好加回 10 分並預付 12 m/s。
prepaid = .6 * (on.SPLIT_AWARE_DV_OVERHEAD - 1.) * 1000.
expected = on.ranking_score(mon["miss_km"], mon["t_team"], mon["dv_mps"] + prepaid, 0)
check("拆後估計加回軟懲罰並預付燃料", abs(mon["score_split_est"] - expected) < 1e-9)
check("分數差 = 加回每發 10 分 − 燃料扣分",
      abs(mon["score_split_est"] - mon["score"]
          - (10. * (1 + mon["split_terminal_count"]) + expected
             - on.ranking_score(mon["miss_km"], mon["t_team"], mon["dv_mps"], 0))) < 1e-9)
# A 選成第一發後的同一條二體軌道：由 r=12000 km、圓軌道速度加 ECI [0.6,0,0]
# 在 t=500 s 的狀態換算回 epoch 根數，讓終端棒近乎零，單獨驗證一次 −10 的貢獻。
matched_cfg = config(SPLIT_LEADING=True)
matched_cfg["orbit_A"].update(SMA=11553.092894369236, ECC=.11007604637986733,
                              AOP=-102.62002699890604, TA=102.61491446244801)
matched = MissionOptimizer(matched_cfg)
matched_off = copy.copy(matched); matched_off.SPLIT_LEADING = False
mm = matched.mission_metrics(x, 2)
mm_off = matched_off.mission_metrics(x, 2)
base_score = matched.ranking_score(mm["miss_km"], mm["t_team"], mm["dv_mps"], 0)
paid_score = matched.ranking_score(mm["miss_km"], mm["t_team"], mm["dv_mps"] + prepaid, 0)
check("只有前導棒超標：關閉失格、開啟僅一次 −10",
      mm_off["score"] < 0. <= mm["score"] and mm["split_terminal_count"] == 0
      and mm["split_leading_count"] == 1 and abs(mm["score"] - (base_score - 10.)) < 1e-9)
check("只有前導棒超標：估計差 = 10 − 預付燃料扣分",
      abs(mm["score_split_est"] - mm["score"] - (10. + paid_score - base_score)) < 1e-9)
with patch.object(app, "legalize_route", wraps=app.legalize_route) as splitter:
    post = app.legalize_violating_winner(on.config, burns, times, mi, on)
    route_kw = splitter.call_args.kwargs
    check("送進拆棒器的抵達時刻與瞄準點不變",
          route_kw["t0"] + sum(route_kw["leading_coasts"]) + route_kw["terminal_coast"] == 2600.
          and np.array_equal(route_kw["target"], on.state_A(2600.)[0]))
check("開啟後能拆成合法解", post is not None)
if post is not None:
    pb, pt, pm = post
    check("拆後不失格、每棒 ≤ MAX_DV", not pm["disqualified"]
          and max(np.linalg.norm(b) for b in pb) <= on.MAX_DV + 1e-9)
    check("拆後間隔合法、Earth-safe、總燃料合法", pm["penalty_count"] == 0
          and min(pt[1:-1]) >= on.MIN_COAST_TIME - 1e-6 and pm["earth_safe"]
          and pm["total_dv_mps"] <= on.MAX_TOTAL_DV_MPS)
with patch.object(app, "presplit_leading", wraps=presplit_leading) as pre:
    off_result = app.legalize_violating_winner(off_cfg, burns, times, mi, off)
    check("關閉不呼叫等分、同一路線仍不合法",
          pre.call_count == 0 and (off_result is None or off_result[2]["disqualified"]))
xbig = x.copy(); xbig[1] = on.LEADING_SPLIT_LIMIT + .001
check("超出前導可拆上限仍在失格層", on.mission_metrics(xbig, 2)["score"] < 0.)
# hard cap 使用真實上限，涵蓋 .748~.750 km/s 的搜尋邊緣。
leg = {"penalty_count": 0, "over_dv_legs": [0]}
check("搜尋上界邊緣仍可拆", on._search_score_terms(leg, [.75, .1]) == (1, 0.))
check("超出前導上限只累加超出量", np.allclose(on._search_score_terms(leg, [.8, .1]), (0, 50.)))
prelim = copy.copy(on); prelim.RANKING_RULES = False
check("初賽分類維持每發 −10", prelim._search_score_terms(
    dict(leg, over_dv_count=1), [.6, .1]) == (1, 0.))
check("AUTO_SPLIT_LEGALIZE 關時不生效", not MissionOptimizer(config(
    SPLIT_LEADING=True, AUTO_SPLIT_LEGALIZE=False)).SPLIT_LEADING)

print("\n── 3. 等分後的前導弧安全閘門 ──")
kw = dict(mu=on.MU, j2=0., j3=0., j4=0., re=on.RE_VAL, B_r0=on.B_r0, B_v0=on.B_v0)
check("安全路線不誤判", min(leading_arcs_min_radius(t0, dvs, coasts, **kw)) >= on.MIN_PERIAPSIS)
unsafe_cfg = config(SPLIT_LEADING=True)
unsafe_cfg["orbit_B"]["SMA"] = 7000.
unsafe = MissionOptimizer(unsafe_cfg)
u = presplit_leading(0., [[0., -.6, 0.]], [3000.], 500., cap=.248, min_coast=100.)
ur = leading_arcs_min_radius(u[0], u[1], u[2], mu=unsafe.MU, j2=0., j3=0., j4=0.,
                             re=unsafe.RE_VAL, B_r0=unsafe.B_r0, B_v0=unsafe.B_v0)
check("反向燒後實際經過低近地點會被抓到", min(ur) < unsafe.MIN_PERIAPSIS - 1e-3)
ux = np.array([0., .6, math.pi / 2, -math.pi / 2, 2900. / 5800., 400. / 2900., 0., 0., 0.])
umi = dict(mi, x=ux, num_burns=2)
with patch.object(app, "legalize_route", side_effect=AssertionError("不安全路線不應送進拆棒器")):
    check("不安全前導弧在拆棒前退回 None", app.legalize_violating_winner(
        unsafe_cfg, burns, times, umi, unsafe) is None)
# 等分後終端時刻被往後推到抵達點，時間閘門應先擋。
short_x = np.array([0., .6, math.pi / 2, 0., 0., 100. / 5800., 0., 0., 0.])
with patch.object(app, "legalize_route", side_effect=AssertionError("時間不足不應送進拆棒器")):
    check("接線也拒絕時間不足", app.legalize_violating_winner(
        on.config, burns, times, dict(mi, x=short_x), on) is None)

print("\n── 4. 關閉逐位元相容與設定檢查 ──")
missing_cfg = config(); missing_cfg["strategy"].pop("SPLIT_LEADING", None)
missing = MissionOptimizer(missing_cfg).mission_metrics(x, 2)
check("沒寫與 false：除新欄位外每欄逐位元相同", all(
    pickle.dumps(v) == pickle.dumps(moff[k]) for k, v in missing.items() if k != "split_leading_count"))
check("關閉新增計數為零", missing["split_leading_count"] == moff["split_leading_count"] == 0)
with tempfile.TemporaryDirectory() as folder:
    for opt in (on, off):
        opt.no_legal_route = {"x": x, "burns": 2, "fitness": 1.}
        path = os.path.join(folder, "no_legal_route.json")
        with patch.object(opt, "_replay_mission", return_value=(burns, times, mi)), \
             patch.object(app.log, "error"):
            app.save_no_legal_route(path, opt)
        with open(path, encoding="utf-8") as source:
            saved = json.load(source)
        check(f"失格存檔的前導可拆標記跟旋鈕一致（{opt.SPLIT_LEADING}）",
              saved["violations"]["over_cap_burns"][0]["splittable"] is opt.SPLIT_LEADING)
for key, values in (("SPLIT_LEADING", [0, 1, "true", None]),
                    ("SPLIT_AWARE_MAX_FACTOR", [0, 15, "3", True, 3.5])):
    for value in values:
        try:
            validate_config(config(**{key: value}))
            check(f"{key} 拒絕 {value!r}", False)
        except ConfigValidationError as exc:
            check(f"{key} 拒絕 {value!r}", key in str(exc))
for factor in (1, 4, 14):
    validate_config(config(SPLIT_AWARE_MAX_FACTOR=factor))
check("前導可拆倍數 1、4、14 通過", True)

print("\n── 5. primer 拆後比較與快取 ──")
PROFILE = {"verdict": "add-node", "max_peak": 1.5, "worst_arc": 0,
           "arcs": [{"kind": "inter-impulse", "p_peak_frac": .5}]}


def candidate(label, score, post_score, n=2, **post_fields):
    cfg = config(SPLIT_LEADING=True)
    opt = SimpleNamespace(config=cfg, SPLIT_LEADING=True, SPLIT_AWARE_TERMINAL=True,
                          TIEBREAK_SCORE_EPS=1e-9, T_max=6000., MIN_COAST_TIME=100., LAMBERT_MAX_REVS=0)
    info = dict(score=score, score_split_est=score, miss_km=.001, total_dv_mps=1000., T_team=2000.,
                x=np.full(4 * n + 1, float(label)), num_burns=n, earth_safe=True, disqualified=False)
    opt.post = dict(info, score=post_score, score_split_est=post_score, **post_fields)
    return [label], [100.], info, opt


def fake_legal(cfg, b, t, info, opt):
    return b, t, opt.post


for mode in ("full", "fast"):
    old = candidate(1, 95., 60.)
    new = candidate(2, 80., 85., n=3)
    glob = candidate(3, 99., 99., n=3, earth_safe=False)
    cfg = copy.deepcopy(old[3].config); cfg["strategy"]["PRIMER_RESEARCH_MODE"] = mode
    new[3]._generate_nlp_refined_seed_candidates = Mock(return_value=[])
    new[3].refine_trajectory = Mock(return_value=new[:3])
    with patch.object(app, "_primer_diagnose_winner", return_value=PROFILE), \
         patch.object(app, "insert_node_seed", return_value=np.ones(13)), \
         patch.object(app, "MissionOptimizer", return_value=new[3]), \
         patch.object(app, "run_study_over_revs", return_value=new if mode == "full" else glob), \
         patch.object(app, "legalize_violating_winner", side_effect=fake_legal) as legal:
        result = app.primer_guided_research(cfg, *old)
        check(f"{mode} 比拆後結果、回傳拆前 tuple", result is not None
              and result[2] is new[2] and result[3] is new[3])
        calls = legal.call_count
        again = app._legalize_stage(new[3].config, *new)
        check(f"{mode} 贏家二次合法化命中快取", legal.call_count == calls and again[2] is new[3].post)
        check(f"{mode} 原候選也有快取", len(old[3]._legalize_cache) == 1)
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "winner.json")
            app.save_winner_checkpoint(path, new[3], *new[:3])
            with open(path, encoding="utf-8") as source:
                saved = json.load(source)
            check(f"{mode} checkpoint 保留拆前資料且不含快取",
                  saved["mission_info"]["score"] == new[2]["score"]
                  and "_legalize_cache" not in json.dumps(saved))
        changed = dict(new[2], x=new[2]["x"].copy()); changed["x"][0] += .01
        app._legalize_stage(new[3].config, new[0], new[1], changed, new[3])
        check(f"{mode} 不同向量不誤用快取", legal.call_count == calls + 1)
        old[3]._legalize_cache.clear(); new[3]._legalize_cache.clear()
        old[3].post = dict(old[3].post, score=90., score_split_est=90.)
        result = app.primer_guided_research(cfg, *old)
        check(f"{mode} 原解拆後較好時沿用原解", result is None)

old = candidate(4, 90., 80.)
old[3].SPLIT_LEADING = False
with patch.object(app, "legalize_violating_winner", return_value=None) as legal:
    app._legalize_stage(old[3].config, *old)
    app._legalize_stage(old[3].config, *old)
    check("關閉不寫快取、每次照舊執行", legal.call_count == 2 and not hasattr(old[3], "_legalize_cache"))

if FAILS:
    print(f"\n❌ {len(FAILS)} 項失敗：" + "、".join(FAILS))
    sys.exit(1)
print("\n✅ 前導棒拆分全部通過")
