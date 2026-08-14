import sys, json, math
sys.path.insert(0, "/Users/corn/Documents/Program/ODC_Program")
import numpy as np
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
    best = None
    for prograde in (True, False):
        try:
            v1, _ = izzo(mu, r0, r1, tof, M=0, prograde=prograde, lowpath=True, numiter=35, rtol=1e-8)
            return v1
        except Exception:
            continue
    return None

def test_relambert_split(opt, best, min_interval, max_dv, min_periapsis, miss_tol_km, label):
    dv, tw, ft, r_b, v_b, v1_orig, r_a_true = best
    dv_mag = dv
    N = max(1, math.ceil(dv_mag * 1000.0 / max_dv))
    print(f"\n--- {label}: 原始單棒 Dv={dv_mag*1000:.1f}m/s -> 拆成 {N} 棒，每棒重新解 Lambert ---")
    if N <= 1:
        print("  沒超標，不用拆"); return

    mu, dt = opt.MU, 60.0
    j2, j3, j4, re = opt.J2_VAL, opt.J3_VAL, opt.J4_VAL, opt.RE_VAL

    # 每棒的目標時間：最後一棒仍落在 tw+ft (A 的真實攔截時間不變)，往前推 N-1 個 min_interval
    burn_times = [tw + ft - (N - 1 - k) * min_interval for k in range(N)]

    r_cur, v_cur = r_b, v_b
    t_cur = tw
    total_dv_used = 0.0
    all_legal = True
    per_burn_dvs = []
    for k, t_burn in enumerate(burn_times):
        coast = t_burn - t_cur
        if coast > 0:
            r_cur, v_cur = propagate_dop853(r_cur, v_cur, coast, dt, mu, j2, j3, j4, re)
        remaining_time = (tw + ft) - t_burn
        if remaining_time < 1.0:
            # 最後一棒：直接瞄準 A 真實位置，flight time 趨近 0，改用「速度匹配」邏輯：
            # 剩餘時間太短 Lambert 會退化，這裡改成瞄準極短時間後的 A 位置
            r_target, v_target_A = propagate_dop853(opt.A_r0, opt.A_v0, t_burn + max(remaining_time,1.0), dt, mu, j2, j3, j4, re)
            v_req = lambert_best(mu, r_cur, r_target, max(remaining_time, 1.0))
        else:
            r_target, _ = propagate_dop853(opt.A_r0, opt.A_v0, t_burn + remaining_time, dt, mu, j2, j3, j4, re)
            v_req = lambert_best(mu, r_cur, r_target, remaining_time)
        if v_req is None:
            print(f"  第{k+1}棒 Lambert 求解失敗"); all_legal=False; break
        dv_vec = v_req - v_cur
        dv_piece_mag = fast_norm(dv_vec)
        per_burn_dvs.append(dv_piece_mag*1000)
        total_dv_used += dv_piece_mag
        if dv_piece_mag*1000 > max_dv:
            all_legal = False
        v_cur = v_cur + dv_vec
        if not check_constraints(r_cur, v_cur, mu, min_periapsis):
            print(f"  ❌ 第{k+1}棒燒完後安檢不過"); all_legal = False
        t_cur = t_burn

    final_coast = (tw + ft) - t_cur
    if final_coast > 0:
        r_cur, v_cur = propagate_dop853(r_cur, v_cur, final_coast, dt, mu, j2, j3, j4, re)

    miss_km = fast_norm(r_cur - r_a_true)
    verdict = "✅ 命中容許範圍內" if miss_km <= miss_tol_km else "❌ 脫靶"
    print(f"  每棒 Dv: {[f'{d:.1f}' for d in per_burn_dvs]} m/s  (原本上限 {max_dv:.0f}m/s)")
    print(f"  總 Dv 用量: {total_dv_used*1000:.1f}m/s  (原始單棒 {dv_mag*1000:.1f}m/s)")
    print(f"  誤差 = {miss_km:.3f} km (容許 {miss_tol_km} km)  {verdict}")
    print(f"  每棒都合法: {'✅' if all_legal else '❌'}")

for path, label in [
    ("/private/tmp/claude-501/-Users-corn-Documents-Program-ODC-Program/3ae5e3ff-4074-41e2-873d-a34bd995e9c7/scratchpad/ecc_sweep_0.5.json", "ECC=0.5 (輕度超標)"),
    ("/private/tmp/claude-501/-Users-corn-Documents-Program-ODC-Program/3ae5e3ff-4074-41e2-873d-a34bd995e9c7/scratchpad/ecc_sweep_0.7.json", "ECC=0.7 (重度超標)"),
]:
    opt, best = find_best_single_burn(path)
    if best is None:
        print(f"{label}: 沒找到候選"); continue
    test_relambert_split(opt, best, opt.MIN_COAST_TIME, opt.MAX_DV*1000.0, opt.MIN_PERIAPSIS, opt.MISS_TOLERANCE_KM, label)
