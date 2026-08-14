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

def test_split(opt, best, min_interval, max_dv, min_periapsis, miss_tol_km, label):
    dv, tw, ft, r_b, v_b, v1, r_a_true = best
    dv_vec = v1 - v_b
    dv_mag = fast_norm(dv_vec)
    N = max(1, math.ceil(dv_mag * 1000.0 / max_dv))  # dv_mag單位km/s, max_dv單位m/s
    print(f"\n--- {label}: 原始單棒 Dv={dv_mag*1000:.1f}m/s (超標 {dv_mag*1000/max_dv:.2f}x) -> 需要拆成 {N} 棒 ---")
    if N <= 1:
        print("  沒超標，不用拆")
        return

    mu, dt = opt.MU, 60.0
    j2, j3, j4, re = opt.J2_VAL, opt.J3_VAL, opt.J4_VAL, opt.RE_VAL
    dv_piece = dv_vec / N

    # N 棒平均間隔 min_interval，最後一棒剛好落在原本的攔截時刻 tw+ft
    burn_times = [tw + ft - (N - 1 - k) * min_interval for k in range(N)]
    print(f"  每棒 Dv={fast_norm(dv_piece)*1000:.1f}m/s ({'合法' if fast_norm(dv_piece)*1000<=max_dv else '還是超標！'})")
    print(f"  燃燒時間點: {[f'{t:.1f}s' for t in burn_times]}")

    # 實際傳播：從 tw 開始滑行到第一棒時間，依序燒 N 棒，中間都用真實傳播模型
    r_cur, v_cur = r_b, v_b
    t_cur = tw
    all_legal = True
    for k, t_burn in enumerate(burn_times):
        coast = t_burn - t_cur
        if coast > 0:
            r_cur, v_cur = propagate_dop853(r_cur, v_cur, coast, dt, mu, j2, j3, j4, re)
        v_cur = v_cur + dv_piece
        if not check_constraints(r_cur, v_cur, mu, min_periapsis):
            print(f"  ❌ 第{k+1}棒燒完後安檢不過 (轉移軌道擦地)")
            all_legal = False
        t_cur = t_burn

    # 燒完最後一棒後，滑行到原本的抵達時間 (應該已經到了，因為最後一棒時間=tw+ft)
    final_coast = (tw + ft) - t_cur
    if final_coast > 0:
        r_cur, v_cur = propagate_dop853(r_cur, v_cur, final_coast, dt, mu, j2, j3, j4, re)

    miss_km = fast_norm(r_cur - r_a_true)
    verdict = "✅ 命中容許範圍內" if miss_km <= miss_tol_km else "❌ 脫靶"
    print(f"  拆分後實際位置 vs A 真實位置: 誤差 = {miss_km:.3f} km (容許 {miss_tol_km} km)  {verdict}")
    print(f"  每棒都合法: {'✅' if all_legal else '❌'}")
    return miss_km, all_legal

for path, label in [
    ("/private/tmp/claude-501/-Users-corn-Documents-Program-ODC-Program/3ae5e3ff-4074-41e2-873d-a34bd995e9c7/scratchpad/ecc_sweep_0.5.json", "ECC=0.5 (輕度超標)"),
    ("/private/tmp/claude-501/-Users-corn-Documents-Program-ODC-Program/3ae5e3ff-4074-41e2-873d-a34bd995e9c7/scratchpad/ecc_sweep_0.7.json", "ECC=0.7 (重度超標)"),
]:
    opt, best = find_best_single_burn(path)
    if best is None:
        print(f"{label}: 沒找到候選")
        continue
    test_split(opt, best, opt.MIN_COAST_TIME, opt.MAX_DV*1000.0, opt.MIN_PERIAPSIS, opt.MISS_TOLERANCE_KM, label)
