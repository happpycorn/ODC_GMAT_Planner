"""固定大前導棒驗證 SEARCH、重播及挑選使用相同的路線與計分政策。"""
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from odc.search.optimizer import MissionOptimizer
from odc.search.fitness import fast_fitness_evaluator
from odc.search.ranking import mission_rank_score
from odc.runlog import setup

setup(quiet=True)
FAILS = []


def check(name, ok):
    print(("  ✅ " if ok else "  ❌ ") + name)
    if not ok:
        FAILS.append(name)


def make(**strategy):
    cfg = json.loads((ROOT / "configs/shared/hyperbolic_smoke.json").read_text())
    # 無攝動時，Lambert 與 DC 重播只差積分／求解器浮點誤差；不用放寬容差來掩蓋計分差異。
    cfg["orbit_A"].update(SMA=11553.092894369236, ECC=.11007604637986733,
                          INC=0., RAAN=0., AOP=-102.62002699890604, TA=102.61491446244801)
    cfg["orbit_B"].update(SMA=12000., ECC=0., INC=0., RAAN=0., AOP=0., TA=0.)
    cfg["rules"].update(MAX_DV_MPS=250., MAX_TOTAL_DV_MPS=3000., T_MAX_SEC=6000., C_t=2500.)
    cfg["strategy"].update(GRAVITY_DEGREE=0, EPHEM_CACHE=False, LAMBERT_MAX_REVS=0,
                           SPLIT_AWARE_SEARCH=True, SPLIT_LEADING=True,
                           SPLIT_AWARE_MAX_FACTOR=5)
    cfg["strategy"].update(strategy)
    return MissionOptimizer(cfg)


# t0=500, 前導棒 600 m/s，滑行 600 s，終端滑行 1500 s，抵達 2600 s。
# A 幾乎等於這條前導棒後的軌道，終端接近零；舊搜尋的虛構加時會使終端 Δv 驟變。
X = np.array([500., .6, math.pi / 2, 0., 500. / 5300., 1400. / 4800., 0., 0., 0.])
# 刻意較晚的 1 棒候選，真實重建成績，不 mock mission_metrics。
ONE = np.array([5000., .9, 0., 0., 0.])
# 2e-6 分容差：二體 Lambert、DOP853、DC 的浮點／積分誤差；遠低於舊錯誤造成的分差。
ATOL = 2e-6


def compare(opt, x=X, n=2):
    m = opt.mission_metrics(x, n)
    f = -float(opt._fitness_wrapper(n)(x))
    target = mission_rank_score(m, split_est=opt.SPLIT_AWARE_TERMINAL)
    check(f"fast/replay 同尺 {opt.SPLIT_LEADING=}, {opt.SPLIT_AWARE_TERMINAL=}: {f:.9f}/{target:.9f}",
          abs(f - target) < ATOL)
    return m


on = make()
m = compare(on)
check("600 m/s 前導棒可拆、抵達 2600 s", m["split_leading_count"] == 1 and m["t_team"] == 2600.)
_, _, mi = on._replay_mission(X, 2)
check("mission_metrics 與 _replay_mission 的拆後估計完全相同", mi["score_split_est"] == m["score_split_est"])
check("預付 12 m/s 燃料，不加任務時間",
      abs(m["score_split_est"] - on.ranking_score(m["miss_km"], 2600., m["dv_mps"] + 12., 0)) < 1e-9)
on.burn_case_results = {n: {"best_x": x.copy(), "fitness": float(on._fitness_wrapper(n)(x))}
                        for n, x in ((1, ONE), (2, X))}
check("真實重播與分桶挑選選中 2 棒大前導棒", on._pick_best_case()[0] == 2)
# primer 重搜單開 SEARCH（SPLIT_LEADING 關）刻意保留舊算法，預設管線逐位元不變（已知不同尺，見報告）。
off = make(SPLIT_LEADING=False)
check("SPLIT_LEADING 關：維持 24 格 ABI（走舊算法）", len(off._scalar_params()) == 24)
check("SPLIT_LEADING 關：bounds 照舊放寬", off._generate_bounds(2)[1][1] == off._split_aware_dv_ub())
check("AUTO_SPLIT_LEGALIZE 關時 SPLIT_LEADING 不生效，也走舊算法",
      len(make(SPLIT_LEADING=True, AUTO_SPLIT_LEGALIZE=False)._scalar_params()) == 24)
compare(make(SPLIT_AWARE_TERMINAL=False))
compare(make(SPLIT_AWARE_DV_OVERHEAD=1.1))

edge = X.copy()
edge[1] = .249  # soft cap 248 < 249 < official cap 250：不應扣分或收取拆棒 overhead。
compare(on, edge)
big = X.copy()
big[1] = on.LEADING_SPLIT_LIMIT + .001
mbig = compare(on, big)
check("超出可拆上限進失格層", mbig["score_split_est"] < -10.)

# 改成 A/B 同軌，終端也超標，以免只驗到前導棒的特例。
both = make()
both.A_r0, both.A_v0 = both.B_r0.copy(), both.B_v0.copy()
mboth = compare(both)
check("前導與終端都超標時拆後估計仍一致",
      mboth["split_leading_count"] == 1 and mboth["split_terminal_count"] == 1)
three = np.array([500., .6, math.pi / 2, 0., 500. / 5300.,
                  .3, math.pi / 2, 0., 300. / 4700., 1400. / 4400., 0., 0., 0.])
mthree = compare(on, three, 3)
check("兩發大前導棒也不累加虛構時間", mthree["split_leading_count"] == 2 and mthree["t_team"] == 3000.)

# 預付燃料會把總量推進失格層，兩邊也必須一致。
total = make(SPLIT_AWARE_DV_OVERHEAD=1.1)
total.MAX_TOTAL_DV_MPS = 620.
mtotal = compare(total)
check("預付燃料超總量上限進失格層", mtotal["score_split_est"] < -10.)

# 24 格（舊算法）與 26 格（新算法）對同一大前導棒給不同分數：新算法跟重播同尺，舊的不是。
legacy = -float(fast_fitness_evaluator(X, 2, on._scalar_params()[:24].copy(), on._vector_params()))
check("舊算法與新算法對大前導棒分數不同（確認走到不同分支）", abs(legacy - (-float(on._fitness_wrapper(2)(X)))) > 1e-6)
legacy_off = make(SPLIT_AWARE_SEARCH=False)
check("SEARCH 關時維持 24 格 ABI 與原單棒上界",
      len(legacy_off._scalar_params()) == 24 and
      legacy_off._generate_bounds(2)[1][1] == legacy_off.MAX_DV_SOFT)
sp = legacy_off._scalar_params()
f24 = fast_fitness_evaluator(ONE, 1, sp, legacy_off._vector_params())
f26 = fast_fitness_evaluator(ONE, 1, np.append(sp, [9., 99.]), legacy_off._vector_params())
check("SEARCH 關時忽略新增欄位，結果逐位元相同", np.float64(f24).tobytes() == np.float64(f26).tobytes())

if FAILS:
    sys.exit(f"{len(FAILS)} checks failed: {FAILS}")
print("✅ 全部通過")
