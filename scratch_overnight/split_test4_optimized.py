import sys, json, math
sys.path.insert(0, "/Users/corn/Documents/Program/ODC_Program")
import numpy as np
from scipy.optimize import minimize
from src.optimizer import MissionOptimizer
from src.core_math import propagate_dop853, fast_norm, check_constraints
from poliastro.core.iod import izzo

def find_best_single_burn(config_path):
    config = json.load(open(config_path))
    opt = MissionOptimizer(config)
    mu, dt = opt.MU, 60.0
    j2, j3, j4, re = opt.J2_VAL, opt.J3_VAL, opt.J4_VAL, opt.RE_VAL
    seeds = opt._generate_seed_candidates(1, 5)
    best = None
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
                if best is None or d < best[0]:
                    best = (d, tw, ft, r_b, v_b, v1, r_a)
            except Exception:
                pass
    return opt, best

def lambert_best(mu, r0, r1, tof):
    for prograde in (True, False):
        try:
            v1, _ = izzo(mu, r0, r1, tof, M=0, prograde=prograde, lowpath=True, numiter=35, rtol=1e-8)
            return v1
        except Exception:
            continue
    return None

def total_cost(v_after_burn1, mu, dt, j2,j3,j4,re, r_b, v_b, r_a_true, coast1, remaining_time):
    dv1 = fast_norm(v_after_burn1 - v_b)
    r_mid, _ = propagate_dop853(r_b, v_after_burn1, coast1, dt, mu, j2, j3, j4, re)
    v2_req = lambert_best(mu, r_mid, r_a_true, remaining_time)
    if v2_req is None:
        return 1e6
    v_mid_before_burn2 = propagate_dop853(r_b, v_after_burn1, coast1, dt, mu, j2, j3, j4, re)[1]
    dv2 = fast_norm(v2_req - v_mid_before_burn2)
    return dv1 + dv2

for path, label in [
    ("/private/tmp/claude-501/-Users-corn-Documents-Program-ODC-Program/3ae5e3ff-4074-41e2-873d-a34bd995e9c7/scratchpad/ecc_sweep_0.5.json", "ECC=0.5 (輕度超標,原1540m/s)"),
]:
    opt, best = find_best_single_burn(path)
    dv_orig, tw, ft, r_b, v_b, v1_orig, r_a_true = best
    mu, dt = opt.MU, 60.0
    j2, j3, j4, re = opt.J2_VAL, opt.J3_VAL, opt.J4_VAL, opt.RE_VAL
    min_interval = opt.MIN_COAST_TIME
    max_dv = opt.MAX_DV * 1000.0
    coast1 = min_interval
    remaining_time = ft - min_interval

    print(f"\n--- {label}：用局部最佳化找『真正最好的』兩棒分割 (不是硬解析拆) ---")
    # 初始猜測：延續原本方向，但只給 30% 的量 (刻意跟"對半"不同，避免陷入同一個爛局部解)
    x0 = v_b + 0.3 * (v1_orig - v_b)
    res = minimize(
        total_cost, x0, args=(mu, dt, j2, j3, j4, re, r_b, v_b, r_a_true, coast1, remaining_time),
        method='Nelder-Mead', options={'maxiter': 3000, 'xatol': 1e-6, 'fatol': 1e-9}
    )
    v_after_burn1 = res.x
    dv1 = fast_norm(v_after_burn1 - v_b) * 1000
    r_mid, v_mid = propagate_dop853(r_b, v_after_burn1, coast1, dt, mu, j2, j3, j4, re)
    v2_req = lambert_best(mu, r_mid, r_a_true, remaining_time)
    dv2 = fast_norm(v2_req - v_mid) * 1000
    print(f"  最佳化後: 第1棒Dv={dv1:.1f}m/s, 第2棒Dv={dv2:.1f}m/s, 總計={dv1+dv2:.1f}m/s (原單棒 {dv_orig*1000:.1f}m/s)")
    print(f"  最佳化收斂: {res.success}, 迭代={res.nit}")
    print(f"  兩棒都合法(<={max_dv:.0f}m/s): {'✅' if dv1<=max_dv and dv2<=max_dv else '❌'}")

    v_final_after_burn2 = v_mid + (v2_req - v_mid)
    r_final, _ = propagate_dop853(r_mid, v_final_after_burn2, remaining_time, dt, mu, j2, j3, j4, re)
    miss_km = fast_norm(r_final - r_a_true)
    print(f"  命中誤差: {miss_km:.3f}km (容許 {opt.MISS_TOLERANCE_KM}km)")
