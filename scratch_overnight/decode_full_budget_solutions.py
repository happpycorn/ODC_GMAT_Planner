"""
把 full_budget_ab_validation.py 跑出來的解拆開，看每一棒實際燒了多少、
在什麼時間點燒——用來確認「多棒優勢」到底是不是真的用到了多棒。

決策向量結構 (見 _generate_bounds)：
  [t_wait, (r,theta,phi,coast_frac)*(num_burns-1), final_leg_frac,
   offset_r, offset_theta, offset_phi]
"""
import sys, os, json, math
import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from src.optimizer import MissionOptimizer
from src.core_math import propagate_dop853, fast_norm
from poliastro.core.iod import izzo

config = json.load(open(os.path.join(REPO_ROOT, "configs", "weird_test.json")))
results = json.load(open(os.path.join(REPO_ROOT, "scratch_overnight",
                                      "full_budget_ab_results.json")))


def decode(num_burns, x, label):
    cfg = dict(config)
    cfg["optimization"] = dict(config["optimization"])
    cfg["optimization"]["MAX_BURNS"] = [num_burns]
    opt = MissionOptimizer(cfg)
    mu, dt = opt.MU, 60.0
    j2, j3, j4, re = opt.J2_VAL, opt.J3_VAL, opt.J4_VAL, opt.RE_VAL

    x = np.asarray(x, dtype=np.float64)
    print(f"\n{'='*66}")
    print(f"{label}  (score={results[f'{num_burns}_seed']['score']:.4f})")
    print(f"{'='*66}")

    t_wait = x[0]
    r_cur, v_cur = propagate_dop853(opt.B_r0, opt.B_v0, t_wait, dt, mu, j2, j3, j4, re)
    current_time = t_wait
    print(f"t_wait = {t_wait:,.1f}s ({t_wait/86400:.4f} 天)")

    total_dv = 0.0
    # 中間棒 (num_burns-1 個)
    for i in range(num_burns - 1):
        base = 1 + i * 4
        dv_r, dv_theta, dv_phi, coast_frac = x[base], x[base+1], x[base+2], x[base+3]
        sin_t = math.sin(dv_theta)
        dv_vec = np.array([dv_r*sin_t*math.cos(dv_phi),
                            dv_r*sin_t*math.sin(dv_phi),
                            dv_r*math.cos(dv_theta)])
        dv_mag = fast_norm(dv_vec) * 1000.0
        total_dv += dv_mag
        v_cur = v_cur + dv_vec
        max_coast = opt.T_max - current_time - opt.MIN_COAST_TIME
        t_coast = opt.MIN_COAST_TIME + coast_frac * (max_coast - opt.MIN_COAST_TIME)
        print(f"  中間棒 {i+1}: Δv = {dv_mag:9.3f} m/s   於 t={current_time:,.1f}s"
              f"   之後滑行 {t_coast:,.1f}s")
        r_cur, v_cur = propagate_dop853(r_cur, v_cur, t_coast, dt, mu, j2, j3, j4, re)
        current_time += t_coast

    # 最後一棒 (Lambert 攔截)
    final_leg_frac = x[1 + (num_burns-1)*4]
    max_final = opt.T_max - current_time
    t_final_leg = opt.MIN_COAST_TIME + final_leg_frac * (max_final - opt.MIN_COAST_TIME)
    intercept_time = current_time + t_final_leg
    r_a, _ = propagate_dop853(opt.A_r0, opt.A_v0, intercept_time, dt, mu, j2, j3, j4, re)
    off_r, off_th, off_ph = x[-3], x[-2], x[-1]
    sin_o = math.sin(off_th)
    offset = np.array([off_r*sin_o*math.cos(off_ph),
                        off_r*sin_o*math.sin(off_ph),
                        off_r*math.cos(off_th)])
    r_aim = r_a + offset

    best = np.inf
    for prograde in (True, False):
        try:
            v1, _ = izzo(mu, r_cur, r_aim, t_final_leg, M=0, prograde=prograde,
                          lowpath=True, numiter=35, rtol=1e-8)
            d = fast_norm(v1 - v_cur)
            if d < best:
                best = d
        except Exception:
            pass
    final_dv = best * 1000.0
    total_dv += final_dv
    print(f"  最後棒  : Δv = {final_dv:9.3f} m/s   於 t={current_time:,.1f}s"
          f"   飛行 {t_final_leg:,.1f}s")
    print(f"  攔截時刻: t = {intercept_time:,.1f}s ({intercept_time/86400:.4f} 天)")
    print(f"  瞄準偏移: r={off_r:.3f} km (軟上限 {opt.MISS_TOLERANCE_SOFT:.3f})")
    print(f"  ── 總 ΔV_team = {total_dv:.3f} m/s")
    return {"total_dv": total_dv, "intercept_time": intercept_time,
            "effective_start": t_wait}


if __name__ == "__main__":
    out = {}
    out[1] = decode(1, results["1_seed"]["x"], "1 棒 (有種子，正式預算)")
    out[2] = decode(2, results["2_seed"]["x"], "2 棒 (有種子，正式預算)")
    out[3] = decode(3, results["3_seed"]["x"], "3 棒 (有種子，正式預算)")

    print(f"\n{'='*66}")
    print("對照總表")
    print(f"{'='*66}")
    print(f"{'案例':<8}{'分數':>11}{'總Δv(m/s)':>13}{'攔截時刻(天)':>15}")
    for n in (1, 2, 3):
        print(f"{n}棒{'':<5}{results[f'{n}_seed']['score']:>11.4f}"
              f"{out[n]['total_dv']:>13.3f}{out[n]['intercept_time']/86400:>15.4f}")
    print("\n已知的窄窗最佳解 (第五階段網格搜尋)： t_wait=1,714,683s, Δv=1189.73 m/s")
