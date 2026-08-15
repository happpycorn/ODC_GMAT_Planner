"""
設計一組「單棒在數學上不可能合法」的測資：LEO -> GEO 高度，近地點連續推進。

為什麼相信單棒不可能：B 在 6800km 圓軌道，要讓遠地點搆到 A 所在的半徑，軌道
能量必須提高到對應的轉移橢圓，這個能量差有硬下限 (在近地點沿速度方向燒最省，
任何其他位置/方向都更貴)。如果這個下限就已經超過每棒 1500 m/s 的規則上限，
單棒就不可能合法——只能撞到但違規 (工具刻意不對最後一棒設硬上限，見 STATUS.md
「設計筆記」那節)。

拆成兩次近地點推進則沒有拆分損失：兩棒都在同一半徑、同方向，速度變化線性相加，
跟 STATUS.md 第二階段那種「間隔 100 秒在轉移弧線中間硬拆」完全不同。

⚠️ 這支腳本刻意「不只做解析推理」：2026-08-15 設計 apoapsis_planechange_test 時，
我用「90 度平面轉向」的解析成本 (1202 m/s) 當教科書答案，結果搜尋找到 721 m/s
——因為任務只要求位置攔截、不要求共軌，解析的軌道匹配成本一定高估。教訓是
凡是「這個情境有多難」的宣稱，都要用實際的 Lambert 網格掃過才算數。
所以下面第 3 步是真的掃網格，不是算公式。
"""
import sys, os, math
import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from src.core_math import propagate_dop853, fast_norm
from poliastro.core.iod import izzo

MU = 398600.4418
RE = 6378.137

# --- 候選情境 ---
B_SMA, B_ECC, B_INC = 6800.0, 0.001, 0.0
A_SMA, A_ECC, A_INC = 42164.0, 0.0, 5.0
A_TA0 = 0.0
B_TA0 = 0.0


def hohmann_first_burn(r_from, r_to):
    """從 r_from 圓軌道，把遠地點抬到 r_to 所需的最小 Δv (近地點切向燒)。"""
    v_circ = math.sqrt(MU / r_from)
    a_t = (r_from + r_to) / 2.0
    v_peri = math.sqrt(MU * (2.0 / r_from - 1.0 / a_t))
    return (v_peri - v_circ) * 1000.0, v_circ, v_peri


def main():
    print("=" * 72)
    print("步驟 1：能量下限——單棒最少要花多少才搆得到 A 的半徑")
    print("=" * 72)
    dv_min, v_circ, v_peri = hohmann_first_burn(B_SMA, A_SMA)
    print(f"  B 圓軌道 r={B_SMA:,.0f} km, v={v_circ:.4f} km/s")
    print(f"  要把遠地點抬到 r={A_SMA:,.0f} km 需要近地點速度 {v_peri:.4f} km/s")
    print(f"  => 理論最小 Δv = {dv_min:,.1f} m/s")
    print(f"     每棒上限 1500 m/s  ->  {'❌ 單棒不可能合法' if dv_min > 1500 else '⚠️ 單棒還做得到'}")
    print(f"     拆成 2 棒近地點推進：每棒 {dv_min/2:,.1f} m/s"
          f"  {'✅ 合法' if dv_min/2 <= 1500 else '❌ 還是超標'}")

    # A 的週期 / T_max
    a_period = 2 * math.pi * math.sqrt(A_SMA**3 / MU)
    b_period = 2 * math.pi * math.sqrt(B_SMA**3 / MU)
    T_max = 4 * a_period
    print(f"\n  A 週期 = {a_period:,.0f}s ({a_period/3600:.2f} 小時)")
    print(f"  B 週期 = {b_period:,.0f}s ({b_period/3600:.2f} 小時)")
    print(f"  T_max  = {T_max:,.0f}s ({T_max/86400:.2f} 天)"
          f"  -> B 起始軌道可繞 {T_max/b_period:.0f} 圈，近地點通過機會很多")

    # --- 用真的軌道狀態做 Lambert 網格 ---
    print("\n" + "=" * 72)
    print("步驟 2：建立真實初始狀態 (poliastro)")
    print("=" * 72)
    from poliastro.bodies import Earth
    from poliastro.twobody import Orbit
    from astropy import units as u

    orb_a = Orbit.from_classical(Earth, A_SMA*u.km, A_ECC*u.one, A_INC*u.deg,
                                  0*u.deg, 0*u.deg, A_TA0*u.deg)
    orb_b = Orbit.from_classical(Earth, B_SMA*u.km, B_ECC*u.one, B_INC*u.deg,
                                  0*u.deg, 0*u.deg, B_TA0*u.deg)
    A_r0 = orb_a.r.to(u.km).value.astype(np.float64)
    A_v0 = orb_a.v.to(u.km/u.s).value.astype(np.float64)
    B_r0 = orb_b.r.to(u.km).value.astype(np.float64)
    B_v0 = orb_b.v.to(u.km/u.s).value.astype(np.float64)
    print(f"  A r0={A_r0.round(1)}  |r0|={fast_norm(A_r0):,.1f} km")
    print(f"  B r0={B_r0.round(1)}  |r0|={fast_norm(B_r0):,.1f} km")

    # --- 步驟 3：實際掃 Lambert 網格 (不是算公式) ---
    print("\n" + "=" * 72)
    print("步驟 3：單棒 Lambert 網格實掃 —— 驗證「處處超標」")
    print("=" * 72)
    dt = 60.0
    j2 = j3 = j4 = 0.0   # 純二體即可，這一步只要成本量級
    re = RE

    n_burn, n_flight = 140, 140
    burn_times = np.linspace(0.0, T_max * 0.75, n_burn)
    best_overall = np.inf
    best_at = None
    legal_hits = 0

    for tb in burn_times:
        r_b, v_b = propagate_dop853(B_r0, B_v0, tb, dt, MU, j2, j3, j4, re)
        max_ft = T_max - tb
        if max_ft < 600:
            continue
        for ft in np.linspace(600.0, max_ft, n_flight):
            r_a, _ = propagate_dop853(A_r0, A_v0, tb + ft, dt, MU, j2, j3, j4, re)
            for prograde in (True, False):
                try:
                    v1, _ = izzo(MU, r_b, r_a, ft, M=0, prograde=prograde,
                                  lowpath=True, numiter=35, rtol=1e-8)
                except Exception:
                    continue
                dv = fast_norm(v1 - v_b) * 1000.0
                if dv <= 1500.0:
                    legal_hits += 1
                if dv < best_overall:
                    best_overall = dv
                    best_at = (tb, ft)

    print(f"  掃了 {n_burn}x{n_flight}x2 = {n_burn*n_flight*2:,} 組 (t_burn, flight_time, 方向)")
    print(f"  找到的最小單棒 Δv = {best_overall:,.1f} m/s"
          f"  (t_burn={best_at[0]:,.0f}s, flight={best_at[1]:,.0f}s)")
    print(f"  合法 (<=1500 m/s) 的組合數 = {legal_hits}")
    if legal_hits == 0 and best_overall > 1500:
        print(f"  ✅ 網格實掃證實：單棒在整個搜尋空間裡都超標"
              f" (最好的也要 {best_overall:,.0f} m/s，超出 {best_overall-1500:,.0f} m/s)")
    else:
        print(f"  ⚠️ 找到合法單棒解，這組情境沒有達到設計目的，要再調整")

    # --- 步驟 4：驗證 2 棒近地點推進真的可行 ---
    print("\n" + "=" * 72)
    print("步驟 4：兩次近地點推進 —— 驗證真的做得到且合法")
    print("=" * 72)
    dv1 = dv_min / 2.0 / 1000.0          # km/s，第一棒
    v_after1 = v_circ + dv1
    a1 = 1.0 / (2.0 / B_SMA - v_after1**2 / MU)
    period1 = 2 * math.pi * math.sqrt(a1**3 / MU)
    print(f"  第一棒 (近地點切向) Δv = {dv1*1000:,.1f} m/s")
    print(f"    -> 新軌道 a={a1:,.1f} km, 遠地點={2*a1-B_SMA:,.1f} km, 週期={period1:,.0f}s")
    print(f"    -> 滑行一圈 {period1:,.0f}s 回到同一個近地點再燒第二棒")
    dv2_needed = (v_peri - v_after1) * 1000.0
    print(f"  第二棒 Δv = {dv2_needed:,.1f} m/s"
          f"  {'✅ 合法' if dv2_needed <= 1500 else '❌ 超標'}")
    print(f"  兩棒總計 = {dv1*1000 + dv2_needed:,.1f} m/s"
          f"  (跟單棒理論下限 {dv_min:,.1f} m/s 一樣——同半徑同方向，沒有拆分損失)")

    print("\n" + "=" * 72)
    print("結論")
    print("=" * 72)
    print(f"  score_dv 吃的是「總 Δv」，兩種做法總量一樣 ({dv_min:,.0f} m/s)，")
    print(f"  所以 1 棒 vs 2 棒的分數差距 = 違規懲罰 10 分，訊號乾淨無歧義。")
    print(f"  建議 C_v ≈ {dv_min*1.1:,.0f} (讓合法解落在 sigmoid 中段偏高，還有鑑別力)")


if __name__ == "__main__":
    main()
