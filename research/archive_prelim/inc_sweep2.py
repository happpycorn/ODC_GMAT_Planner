import sys, time
sys.path.insert(0, "/Users/corn/Documents/Program/ODC_Program")
import copy
import numpy as np
from src.optimizer import MissionOptimizer
from src.core_math import propagate_dop853, fast_norm
from poliastro.core.iod import izzo

# 近地點 7500km (跟 B 的 6800km 接近，之前驗證過這個量級容易找到便宜解)，
# 離心率壓到 0.2 排除窄窗效應，RAAN 對齊讓傾角差 = INC_A 本身。
BASE = {
    "orbit_A": {"SMA": 9375.0, "ECC": 0.2, "INC": None, "RAAN": 0.0, "AOP": 0.0, "TA": 0.0},
    "orbit_B": {"SMA": 6800.0, "ECC": 0.001, "INC": 0.0, "RAAN": 0.0, "AOP": 0.0, "TA": 200.0},
    "rules": {"MAX_DV_MPS": 1500.0, "MIN_MANEUVER_INTERVAL_SEC": 100.0, "T_MAX_PERIOD_MULTIPLE": 4.0,
              "k_t": 0.000002, "C_t": 1800000.0, "k_v": 0.05, "C_v": 1200.0},
    "strategy": {"GRAVITY_DEGREE": 4, "MISS_TOLERANCE_KM": 5.0},
    "optimization": {"MAX_BURNS": [1], "MAXITER": 1000, "POPSIZE": 20, "NUM_THREADS": -1,
                      "MAX_EARLY_STOP": 40, "TOL": 0.02, "SEED": None}
}
print(f"A: r_p={9375*0.8:.0f}km r_a={9375*1.2:.0f}km  B: ~6800km 正圓\n")

INC_LIST = [5.0, 15.0, 30.0, 45.0, 60.0, 75.0, 90.0, 110.0, 130.0, 150.0, 170.0]
results = []

for inc in INC_LIST:
    cfg = copy.deepcopy(BASE)
    cfg["orbit_A"]["INC"] = inc
    opt = MissionOptimizer(cfg)
    mu, dt = opt.MU, 60.0
    j2, j3, j4, re = opt.J2_VAL, opt.J3_VAL, opt.J4_VAL, opt.RE_VAL

    t0 = time.time()
    n_coarse_tw = 250
    flight_times_probe = np.array([600.0, 1800.0, 3600.0, 7200.0, 14400.0, 43200.0])
    tws_probe = np.linspace(0, opt.T_max, n_coarse_tw)
    brute_best_dv, brute_tw, brute_ft = np.inf, None, None
    for ft in flight_times_probe:
        for tw in tws_probe:
            if tw + ft > opt.T_max: continue
            r_b, v_b = propagate_dop853(opt.B_r0, opt.B_v0, tw, dt, mu, j2, j3, j4, re)
            r_a, _ = propagate_dop853(opt.A_r0, opt.A_v0, tw + ft, dt, mu, j2, j3, j4, re)
            for prograde in (True, False):
                try:
                    v1, _ = izzo(mu, r_b, r_a, ft, M=0, prograde=prograde, lowpath=True, numiter=35, rtol=1e-8)
                    d = fast_norm(v1 - v_b)
                    if d < brute_best_dv: brute_best_dv, brute_tw, brute_ft = d, tw, ft
                except Exception: pass

    width_s = None
    if brute_tw is not None:
        span = max(2000.0, brute_ft * 0.5)
        fine_tws = np.linspace(max(0, brute_tw - span), min(opt.T_max, brute_tw + span), 201)
        step = fine_tws[1] - fine_tws[0]
        dvs = []
        for tw in fine_tws:
            r_b, v_b = propagate_dop853(opt.B_r0, opt.B_v0, tw, dt, mu, j2, j3, j4, re)
            r_a, _ = propagate_dop853(opt.A_r0, opt.A_v0, tw + brute_ft, dt, mu, j2, j3, j4, re)
            best = np.inf
            for prograde in (True, False):
                try:
                    v1, _ = izzo(mu, r_b, r_a, brute_ft, M=0, prograde=prograde, lowpath=True, numiter=35, rtol=1e-8)
                    d = fast_norm(v1 - v_b)
                    if d < best: best = d
                except Exception: pass
            dvs.append(best)
        dvs = np.array(dvs)
        legal = dvs <= 1.5
        if legal.any():
            idx = np.where(legal)[0]
            width_s = (idx[-1]-idx[0]+1)*step
    gen_time = time.time() - t0
    results.append((inc, brute_best_dv, width_s, gen_time))
    w_str = f"{width_s:.0f}s" if width_s is not None else "無合法解"
    print(f"傾角差={inc:>6.1f}°  最佳Dv={brute_best_dv*1000:>8.1f}m/s  窗寬={w_str:>10}  (耗時{gen_time:.1f}s)")

print("\n=== 總結 ===")
for inc, bdv, w, gt in results:
    w_str = f"{w:.0f}s" if w is not None else "無合法解"
    print(f"傾角差={inc:>6.1f}°  最佳Dv={bdv*1000:>8.1f}m/s  窗寬={w_str:>10}")
