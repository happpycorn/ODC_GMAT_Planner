"""
量「超難模式」測資裡，合法的 2 棒解到底有多稀有。

design_hard_mode_case.py 已經確認單棒無解 (能量下限證明 + 網格 0 命中)。但那只說明
「必須多棒」，沒說明「多棒有多難找」——這兩件事差很多：
  - perigee_kick_test：單棒無解，但合法 2 棒解粗網格就有 174 組，L-SHADE 輕鬆找到。
  - weird_test：合法解存在但只佔 0.0086%，跑 2000 代都撞不到。
如果不先量這個數字，等一下跑 main.py 找不到解時，會分不清是「工具不夠力」還是
「這組根本沒有合法解」——那樣的測試沒有解讀價值。

做法：第一棒在 B 的近地點附近沿速度方向燒 (近地點推進，Oberth 最有效率)，掃大小
跟滑行時間；第二棒用 Lambert 解，看有沒有兩棒都 <=1500 m/s 的組合。
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

A = dict(SMA=100000.0, ECC=0.5,   INC=63.4, RAAN=40.0, AOP=270.0, TA=0.0)
B = dict(SMA=6800.0,   ECC=0.001, INC=0.0,  RAAN=0.0,  AOP=0.0,   TA=0.0)


def build(o):
    orb = Orbit.from_classical(Earth, o["SMA"]*u.km, o["ECC"]*u.one, o["INC"]*u.deg,
                                o["RAAN"]*u.deg, o["AOP"]*u.deg, o["TA"]*u.deg)
    return (orb.r.to(u.km).value.astype(np.float64),
            orb.v.to(u.km/u.s).value.astype(np.float64))


def main():
    A_r0, A_v0 = build(A)
    B_r0, B_v0 = build(B)
    dt = 60.0
    j2 = j3 = j4 = 0.0
    b_per = 2*math.pi*math.sqrt(B["SMA"]**3/MU)
    T_max = 4 * 2*math.pi*math.sqrt(A["SMA"]**3/MU)

    print(f"B 週期 {b_per:,.0f}s, T_max {T_max:,.0f}s ({T_max/86400:.2f}天)")
    print("掃描中 (第一棒大小 x 起燒時機 x 滑行圈數 x 最後一段飛行時間)...\n")

    best_legal = None
    best_any = None
    n_legal = 0
    n_tested = 0

    # 第一棒：B 前幾圈的近地點附近，沿速度方向
    for t_wait in np.arange(0.0, b_per*4, b_per/6):
        r1, v1 = propagate_dop853(B_r0, B_v0, float(t_wait), dt, MU, j2, j3, j4, RE)
        v1_hat = v1 / fast_norm(v1)
        for dv1 in np.arange(1000.0, 1501.0, 50.0):
            v_after = v1 + v1_hat * (dv1/1000.0)
            a1 = 1.0/(2.0/fast_norm(r1) - fast_norm(v_after)**2/MU)
            if a1 <= 0:
                continue
            per1 = 2*math.pi*math.sqrt(a1**3/MU)
            # 滑行：繞完整圈回到近地點 (1,2,3 圈)，也試半圈 (到遠地點)
            for frac in (0.5, 1.0, 1.5, 2.0, 3.0):
                coast = per1*frac
                t2 = t_wait + coast
                if t2 >= T_max - 600:
                    continue
                r2, v2 = propagate_dop853(r1, v_after, coast, dt, MU, j2, j3, j4, RE)
                max_ft = T_max - t2
                for ft in np.linspace(600.0, min(max_ft, 700000.0), 45):
                    r_a, _ = propagate_dop853(A_r0, A_v0, t2+ft, dt, MU, j2, j3, j4, RE)
                    for pro in (True, False):
                        try:
                            vreq, _ = izzo(MU, r2, r_a, float(ft), M=0, prograde=pro,
                                            lowpath=True, numiter=35, rtol=1e-8)
                        except Exception:
                            continue
                        n_tested += 1
                        dv2 = fast_norm(vreq - v2) * 1000.0
                        total = dv1 + dv2
                        cand = (total, dv1, dv2, t_wait, coast, ft, t2+ft)
                        if best_any is None or total < best_any[0]:
                            best_any = cand
                        if dv2 <= 1500.0:
                            n_legal += 1
                            if best_legal is None or total < best_legal[0]:
                                best_legal = cand

    print("=" * 72)
    print(f"測試了 {n_tested:,} 組 (第一棒已限定 <=1500)")
    print(f"兩棒都合法的組合 = {n_legal:,}"
          f"  ({100.0*n_legal/max(n_tested,1):.4f}% 的取樣空間)")
    if best_legal:
        total, d1, d2, tw, co, ft, ti = best_legal
        print(f"\n✅ 存在合法 2 棒解，最省的一組：總 Δv = {total:,.1f} m/s")
        print(f"   第一棒 {d1:,.1f} m/s @ t={tw:,.0f}s")
        print(f"   第二棒 {d2:,.1f} m/s @ t={tw+co:,.0f}s (滑行 {co:,.0f}s = {co/3600:.1f} 小時)")
        print(f"   攔截於 t={ti:,.0f}s ({ti/86400:.2f} 天)")
        rarity = 100.0*n_legal/max(n_tested,1)
        print(f"\n難度評估：合法解佔 {rarity:.4f}%")
        if rarity < 0.05:
            print("  🔴 極稀有，跟 weird_test 的窄窗同一等級——這組是真的超難")
        elif rarity < 1.0:
            print("  🟠 稀有，比 perigee_kick 難不少，搜尋需要種子機制幫忙")
        else:
            print("  🟡 不算罕見，難度主要來自能量門檻而不是窄窗")
    else:
        t = best_any
        print(f"\n🔴 取樣範圍內找不到兩棒都合法的組合")
        print(f"   最好的是總 {t[0]:,.1f} m/s (第一棒 {t[1]:,.1f}, 第二棒 {t[2]:,.1f} 超標)")
        print("   -> 可能要 3 棒才行，或是這組取樣網格太粗漏掉了窄窗")


if __name__ == "__main__":
    main()
