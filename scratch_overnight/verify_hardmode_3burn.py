"""
驗證「超難模式」測資存不存在合法的 3 棒解。

為什麼一定要先確認：verify_hardmode_2burn.py 已經證實 2 棒在 118,800 組取樣裡
0 命中 (最好的一組第二棒要 2,142 m/s，超標 43%)。如果 3 棒也無解，那這組測資
就是「無論如何都拿不到合法解」——等一下跑 main.py 找不到合法解時，會分不清是
工具不夠力還是題目本身無解，測試就白做了。

做法不是再開一維暴力掃 (太貴)，而是照 perigee_kick_test 實際跑出來的那個策略去
構造：把 2 棒方案裡那把超標的最後一棒，拆成兩把間隔 MIN_COAST (100s) 的燃燒，
第二把用 Lambert 重新解 (不是把向量對半砍——那樣會破壞 Lambert 的前提，見
STATUS.md 第二階段)。perigee_kick 的搜尋自己找到的就是這個結構，而且拆分損失
趨近於零 (100 秒內飛船幾乎沒移動)，所以這是最有機會成立的構造。
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
MIN_COAST = 100.0
MAX_DV = 1500.0

A = dict(SMA=100000.0, ECC=0.5,   INC=63.4, RAAN=40.0, AOP=270.0, TA=0.0)
B = dict(SMA=6800.0,   ECC=0.001, INC=0.0,  RAAN=0.0,  AOP=0.0,   TA=0.0)


def build(o):
    orb = Orbit.from_classical(Earth, o["SMA"]*u.km, o["ECC"]*u.one, o["INC"]*u.deg,
                                o["RAAN"]*u.deg, o["AOP"]*u.deg, o["TA"]*u.deg)
    return (orb.r.to(u.km).value.astype(np.float64),
            orb.v.to(u.km/u.s).value.astype(np.float64))


def lambert_dv(r0, v0, r_target, tof):
    """回傳 (最小 Δv, 所需初速向量)。"""
    best, bv = np.inf, None
    for pro in (True, False):
        try:
            v1, _ = izzo(MU, r0, r_target, float(tof), M=0, prograde=pro,
                          lowpath=True, numiter=35, rtol=1e-8)
        except Exception:
            continue
        d = fast_norm(v1 - v0)
        if d < best:
            best, bv = d, v1
    return best * 1000.0, bv


def main():
    A_r0, A_v0 = build(A)
    B_r0, B_v0 = build(B)
    dt = 60.0
    j2 = j3 = j4 = 0.0
    b_per = 2*math.pi*math.sqrt(B["SMA"]**3/MU)
    T_max = 4 * 2*math.pi*math.sqrt(A["SMA"]**3/MU)

    print(f"T_max = {T_max:,.0f}s ({T_max/86400:.2f} 天)")
    print("構造 3 棒方案：近地點推進 x1 -> 滑行 -> 拆成兩把間隔 100s 的燃燒\n")

    best = None
    n_legal = 0
    n_tested = 0

    for t_wait in np.arange(0.0, b_per*4, b_per/8):
        r1, v1 = propagate_dop853(B_r0, B_v0, float(t_wait), dt, MU, j2, j3, j4, RE)
        v1_hat = v1 / fast_norm(v1)
        for dv1 in np.arange(1100.0, 1501.0, 50.0):
            v_after1 = v1 + v1_hat * (dv1/1000.0)
            a1 = 1.0/(2.0/fast_norm(r1) - fast_norm(v_after1)**2/MU)
            if a1 <= 0:
                continue
            per1 = 2*math.pi*math.sqrt(a1**3/MU)
            for frac in (0.5, 1.0, 1.5, 2.0):
                coast = per1*frac
                t2 = t_wait + coast
                if t2 + MIN_COAST >= T_max - 600:
                    continue
                r2, v2 = propagate_dop853(r1, v_after1, coast, dt, MU, j2, j3, j4, RE)
                # 第二棒：沿速度方向再推一把 (繼續抬能量)，大小也掃
                v2_hat = v2 / fast_norm(v2)
                for dv2 in np.arange(600.0, 1501.0, 100.0):
                    v_after2 = v2 + v2_hat * (dv2/1000.0)
                    a2 = 1.0/(2.0/fast_norm(r2) - fast_norm(v_after2)**2/MU)
                    if a2 <= 0:
                        continue
                    # 滑行最短間隔後，第三棒用 Lambert 收尾
                    r3, v3 = propagate_dop853(r2, v_after2, MIN_COAST, dt, MU, j2, j3, j4, RE)
                    t3 = t2 + MIN_COAST
                    max_ft = T_max - t3
                    if max_ft < 600:
                        continue
                    for ft in np.linspace(600.0, min(max_ft, 800000.0), 30):
                        r_a, _ = propagate_dop853(A_r0, A_v0, t3+ft, dt, MU, j2, j3, j4, RE)
                        dv3, _ = lambert_dv(r3, v3, r_a, ft)
                        if not np.isfinite(dv3):
                            continue
                        n_tested += 1
                        if dv3 <= MAX_DV:
                            n_legal += 1
                            total = dv1 + dv2 + dv3
                            cand = (total, dv1, dv2, dv3, t_wait, coast, ft, t3+ft)
                            if best is None or total < best[0]:
                                best = cand

    print("=" * 72)
    print(f"測試了 {n_tested:,} 組 (前兩棒已限定 <=1500)")
    print(f"三棒都合法的組合 = {n_legal:,}"
          f"  ({100.0*n_legal/max(n_tested,1):.4f}%)")
    if best:
        total, d1, d2, d3, tw, co, ft, ti = best
        print(f"\n✅ 存在合法 3 棒解！最省的一組：總 Δv = {total:,.1f} m/s")
        print(f"   第一棒 {d1:,.1f} m/s @ t={tw:,.0f}s (近地點推進)")
        print(f"   第二棒 {d2:,.1f} m/s @ t={tw+co:,.0f}s (滑行 {co/3600:.1f} 小時後)")
        print(f"   第三棒 {d3:,.1f} m/s @ t={tw+co+MIN_COAST:,.0f}s (Lambert 收尾)")
        print(f"   攔截於 t={ti:,.0f}s ({ti/86400:.2f} 天)")
        print(f"\n   -> 測資有解，可以拿來測工具。建議 C_v ≈ {total*1.1:,.0f}")
        print(f"      建議 C_t ≈ {ti*1.3:,.0f}s ({ti*1.3/86400:.2f}天)")
    else:
        print(f"\n🔴 這個構造下找不到合法 3 棒解")
        print("   -> 要嘛這組測資太難 (連 3 棒都不夠，那 LEO 出發根本無解，該調鬆)，")
        print("      要嘛是我這個構造太侷限 (只試了「兩次切向推進 + Lambert」)。")
        print("   建議：把 A 的近地點拉近一點再測一次，讓能量門檻降到 3 棒搆得到。")


if __name__ == "__main__":
    main()
