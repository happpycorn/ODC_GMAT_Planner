"""
驗證「兩次近地點推進」在含傾角差的真實 3D 幾何下，兩棒是不是都真的 <= 1500 m/s。

design_perigee_kick_case.py 的步驟 4 是共平面的解析算法 (純 Hohmann)，沒有把
A_INC 的平面差算進去。第二棒是 Lambert 解，如果它得在近地點 (速度快) 順便扛
平面轉向，很可能被推爆 1500——那這組測資就沒有合法的 2 棒解，設計目的達不到。

這支腳本直接掃 (第一棒大小, 滑行時間, 最後一段飛行時間)，用真的 propagate +
izzo 算出兩棒各自的 Δv，回報有沒有「兩棒都合法」的組合。
"""
import sys, os, math
import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from src.core_math import propagate_dop853, fast_norm
from poliastro.core.iod import izzo
from poliastro.bodies import Earth
from poliastro.twobody import Orbit
from astropy import units as u

MU = 398600.4418
RE = 6378.137


def build(a_inc_deg):
    orb_a = Orbit.from_classical(Earth, 42164.0*u.km, 0.0*u.one, a_inc_deg*u.deg,
                                  0*u.deg, 0*u.deg, 0.0*u.deg)
    orb_b = Orbit.from_classical(Earth, 6800.0*u.km, 0.001*u.one, 0.0*u.deg,
                                  0*u.deg, 0*u.deg, 0.0*u.deg)
    return (orb_a.r.to(u.km).value.astype(np.float64),
            orb_a.v.to(u.km/u.s).value.astype(np.float64),
            orb_b.r.to(u.km).value.astype(np.float64),
            orb_b.v.to(u.km/u.s).value.astype(np.float64))


def sweep(a_inc_deg, verbose=True):
    A_r0, A_v0, B_r0, B_v0 = build(a_inc_deg)
    dt = 60.0
    j2 = j3 = j4 = 0.0
    T_max = 4 * 2*math.pi*math.sqrt(42164.0**3/MU)

    best = None            # 兩棒都合法之中，總 Δv 最小的
    best_any = None        # 不管合不合法，總 Δv 最小的
    n_legal = 0

    # 第一棒：在 B 的近地點附近沿速度方向燒，大小掃 900~1500
    # t_wait 掃 B 的前幾圈近地點 (B 週期 5581s)
    for t_wait in np.arange(0.0, 5581.0*8, 5581.0/4):
        r1, v1 = propagate_dop853(B_r0, B_v0, t_wait, dt, MU, j2, j3, j4, RE)
        v1_hat = v1 / fast_norm(v1)
        for dv1_mps in np.arange(900.0, 1501.0, 50.0):
            v_after1 = v1 + v1_hat * (dv1_mps / 1000.0)
            # 滑行：掃「回到近地點附近」的幾個週期，也允許其他滑行長度
            a1 = 1.0/(2.0/fast_norm(r1) - fast_norm(v_after1)**2/MU)
            if a1 <= 0:
                continue
            per1 = 2*math.pi*math.sqrt(a1**3/MU)
            for coast in [per1*f for f in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0)]:
                t2 = t_wait + coast
                if t2 >= T_max - 600:
                    continue
                r2, v2 = propagate_dop853(r1, v_after1, coast, dt, MU, j2, j3, j4, RE)
                max_ft = T_max - t2
                for ft in np.linspace(600.0, min(max_ft, 120000.0), 40):
                    r_a, _ = propagate_dop853(A_r0, A_v0, t2+ft, dt, MU, j2, j3, j4, RE)
                    for prograde in (True, False):
                        try:
                            vreq, _ = izzo(MU, r2, r_a, ft, M=0, prograde=prograde,
                                            lowpath=True, numiter=35, rtol=1e-8)
                        except Exception:
                            continue
                        dv2 = fast_norm(vreq - v2) * 1000.0
                        total = dv1_mps + dv2
                        cand = (total, dv1_mps, dv2, t_wait, coast, ft, t2+ft)
                        if best_any is None or total < best_any[0]:
                            best_any = cand
                        if dv1_mps <= 1500.0 and dv2 <= 1500.0:
                            n_legal += 1
                            if best is None or total < best[0]:
                                best = cand
    if verbose:
        print(f"\n--- A_INC = {a_inc_deg} 度 ---")
        print(f"  兩棒都合法的組合數 = {n_legal}")
        if best:
            total, d1, d2, tw, co, ft, ti = best
            print(f"  ✅ 最省的合法 2 棒解：總 Δv = {total:,.1f} m/s")
            print(f"     第一棒 {d1:,.1f} m/s @ t={tw:,.0f}s")
            print(f"     第二棒 {d2:,.1f} m/s @ t={tw+co:,.0f}s (滑行 {co:,.0f}s)")
            print(f"     攔截於 t={ti:,.0f}s ({ti/3600:.2f} 小時)")
        else:
            t = best_any
            print(f"  ❌ 沒有兩棒都合法的組合")
            print(f"     最好的 (違規) 是總 {t[0]:,.1f} m/s"
                  f" (第一棒 {t[1]:,.1f}, 第二棒 {t[2]:,.1f})")
    return best


if __name__ == "__main__":
    print("=" * 72)
    print("驗證含傾角差時，2 棒近地點推進是否還有合法解")
    print("=" * 72)
    for inc in (0.0, 5.0, 10.0):
        sweep(inc)
