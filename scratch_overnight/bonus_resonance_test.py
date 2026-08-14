import sys, time
sys.path.insert(0, "/Users/corn/Documents/Program/ODC_Program")
import copy
import numpy as np
from src.optimizer import MissionOptimizer
from src.core_math import propagate_dop853, fast_norm
from poliastro.core.iod import izzo

# 第三種可能的窄窗來源：A、B 週期接近整數比 (軌道共振)。跟離心率/傾角都無關，
# 兩軌道都用低離心率、低傾角差 (排除前兩種效應)，只讓 A 的 SMA 掃過會跟 B
# 產生簡單整數比週期的區域，看共振點附近會不會也出現類似的窄窗放大。
BASE = {
    "orbit_A": {"SMA": None, "ECC": 0.1, "INC": 10.0, "RAAN": 0.0, "AOP": 0.0, "TA": 0.0},
    "orbit_B": {"SMA": 6800.0, "ECC": 0.05, "INC": 0.0, "RAAN": 0.0, "AOP": 0.0, "TA": 200.0},
    "rules": {"MAX_DV_MPS": 1500.0, "MIN_MANEUVER_INTERVAL_SEC": 100.0, "T_MAX_PERIOD_MULTIPLE": 4.0,
              "k_t": 0.000002, "C_t": 1800000.0, "k_v": 0.05, "C_v": 1200.0},
    "strategy": {"GRAVITY_DEGREE": 4, "MISS_TOLERANCE_KM": 5.0},
    "optimization": {"MAX_BURNS": [1], "MAXITER": 1000, "POPSIZE": 20, "NUM_THREADS": -1,
                      "MAX_EARLY_STOP": 40, "TOL": 0.02, "SEED": None}
}
# B 週期 (SMA=6800): 用克卜勒算，A 的 SMA 掃過讓 T_A/T_B 分別接近 1:1, 3:2, 2:1, 3:1 的區域
import math
mu = 398600.4418
T_B = 2*math.pi*math.sqrt(6800.0**3/mu)
ratios = {"1:1": 1.0, "5:4": 1.25, "3:2": 1.5, "2:1": 2.0, "e:2 (非共振對照)": math.e/2}
print(f"B 週期 = {T_B:.1f}s\n")

for label, ratio in ratios.items():
    T_A_target = T_B * ratio
    sma = (mu * (T_A_target/(2*math.pi))**2) ** (1/3)
    cfg = copy.deepcopy(BASE)
    cfg["orbit_A"]["SMA"] = sma
    opt = MissionOptimizer(cfg)
    mu2, dt = opt.MU, 60.0
    j2, j3, j4, re = opt.J2_VAL, opt.J3_VAL, opt.J4_VAL, opt.RE_VAL

    n_coarse_tw = 200
    flight_times_probe = np.array([600.0, 1800.0, 3600.0, 7200.0, 14400.0])
    tws_probe = np.linspace(0, opt.T_max, n_coarse_tw)
    brute_best_dv, brute_tw, brute_ft = np.inf, None, None
    for ft in flight_times_probe:
        for tw in tws_probe:
            if tw + ft > opt.T_max: continue
            r_b, v_b = propagate_dop853(opt.B_r0, opt.B_v0, tw, dt, mu2, j2, j3, j4, re)
            r_a, _ = propagate_dop853(opt.A_r0, opt.A_v0, tw + ft, dt, mu2, j2, j3, j4, re)
            for prograde in (True, False):
                try:
                    v1, _ = izzo(mu2, r_b, r_a, ft, M=0, prograde=prograde, lowpath=True, numiter=35, rtol=1e-8)
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
            r_b, v_b = propagate_dop853(opt.B_r0, opt.B_v0, tw, dt, mu2, j2, j3, j4, re)
            r_a, _ = propagate_dop853(opt.A_r0, opt.A_v0, tw + brute_ft, dt, mu2, j2, j3, j4, re)
            best = np.inf
            for prograde in (True, False):
                try:
                    v1, _ = izzo(mu2, r_b, r_a, brute_ft, M=0, prograde=prograde, lowpath=True, numiter=35, rtol=1e-8)
                    d = fast_norm(v1 - v_b)
                    if d < best: best = d
                except Exception: pass
            dvs.append(best)
        dvs = np.array(dvs)
        legal = dvs <= 1.5
        if legal.any():
            idx = np.where(legal)[0]
            width_s = (idx[-1]-idx[0]+1)*step
    w_str = f"{width_s:.0f}s" if width_s is not None else "無合法解"
    print(f"週期比 T_A:T_B={label:>18} (SMA={sma:>8.0f}km)  最佳Dv={brute_best_dv*1000:>8.1f}m/s  窗寬={w_str:>10}")
