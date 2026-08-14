import sys, time
sys.path.insert(0, "/Users/corn/Documents/Program/ODC_Program")
import copy
import numpy as np
from src.optimizer import MissionOptimizer
from src.core_math import propagate_dop853, fast_norm
from poliastro.core.iod import izzo

# 固定在窗寬最窄的傾角差 (90°)，掃 AOP (近地點在軌道平面上的位置)，
# 測試現有種子機制 (以「A離地球最近」= 近地點時間 為候選來源) 在近地點
# 離節線很遠時，還找不找得到真正的窄窗。
BASE = {
    "orbit_A": {"SMA": 9375.0, "ECC": 0.2, "INC": 90.0, "RAAN": 0.0, "AOP": None, "TA": 0.0},
    "orbit_B": {"SMA": 6800.0, "ECC": 0.001, "INC": 0.0, "RAAN": 0.0, "AOP": 0.0, "TA": 200.0},
    "rules": {"MAX_DV_MPS": 1500.0, "MIN_MANEUVER_INTERVAL_SEC": 100.0, "T_MAX_PERIOD_MULTIPLE": 4.0,
              "k_t": 0.000002, "C_t": 1800000.0, "k_v": 0.05, "C_v": 1200.0},
    "strategy": {"GRAVITY_DEGREE": 4, "MISS_TOLERANCE_KM": 5.0},
    "optimization": {"MAX_BURNS": [1], "MAXITER": 1000, "POPSIZE": 20, "NUM_THREADS": -1,
                      "MAX_EARLY_STOP": 40, "TOL": 0.02, "SEED": None}
}

AOP_LIST = [0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0]

for aop in AOP_LIST:
    cfg = copy.deepcopy(BASE)
    cfg["orbit_A"]["AOP"] = aop
    opt = MissionOptimizer(cfg)
    mu, dt = opt.MU, 60.0
    j2, j3, j4, re = opt.J2_VAL, opt.J3_VAL, opt.J4_VAL, opt.RE_VAL

    # 現有種子機制
    seeds = opt._generate_seed_candidates(1, 5)
    seed_best_dv = np.inf
    for x in seeds:
        tw, flf = x[0], x[1]
        max_final = opt.T_max - tw
        ft = opt.MIN_COAST_TIME + flf * (max_final - opt.MIN_COAST_TIME)
        r_b, v_b = propagate_dop853(opt.B_r0, opt.B_v0, tw, dt, mu, j2, j3, j4, re)
        r_a, _ = propagate_dop853(opt.A_r0, opt.A_v0, tw + ft, dt, mu, j2, j3, j4, re)
        for prograde in (True, False):
            try:
                v1, _ = izzo(mu, r_b, r_a, ft, M=0, prograde=prograde, lowpath=True, numiter=35, rtol=1e-8)
                d = fast_norm(v1 - v_b)
                if d < seed_best_dv: seed_best_dv = d
            except Exception: pass

    # 暴力全域掃描當 ground truth
    n_coarse_tw = 250
    flight_times_probe = np.array([600.0, 1800.0, 3600.0, 7200.0, 14400.0, 43200.0])
    tws_probe = np.linspace(0, opt.T_max, n_coarse_tw)
    brute_best_dv = np.inf
    for ft in flight_times_probe:
        for tw in tws_probe:
            if tw + ft > opt.T_max: continue
            r_b, v_b = propagate_dop853(opt.B_r0, opt.B_v0, tw, dt, mu, j2, j3, j4, re)
            r_a, _ = propagate_dop853(opt.A_r0, opt.A_v0, tw + ft, dt, mu, j2, j3, j4, re)
            for prograde in (True, False):
                try:
                    v1, _ = izzo(mu, r_b, r_a, ft, M=0, prograde=prograde, lowpath=True, numiter=35, rtol=1e-8)
                    d = fast_norm(v1 - v_b)
                    if d < brute_best_dv: brute_best_dv = d
                except Exception: pass

    gap = (seed_best_dv - brute_best_dv) * 1000
    flag = "✓" if gap < 50 else ("△" if gap < 300 else "✗ 種子機制找偏了")
    print(f"AOP={aop:>6.1f}°  種子找到Dv={seed_best_dv*1000:>8.1f}m/s  暴力全域Dv={brute_best_dv*1000:>8.1f}m/s  差距={gap:>+8.1f}m/s  {flag}")
