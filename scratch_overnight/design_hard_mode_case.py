"""
設計一組「盡可能難」的測資：把 2026-08-15 這一整天量出來的三個難度來源疊在一起。

今天學到的難度軸（每一條都有實測支撐，不是猜的）：
  1. 能量門檻 (perigee_kick_test)：B 卡在低軌道，要爬到 A 那裡的能量差就超過單棒
     1500 m/s 上限——這是**可以證明**的下限，不受網格解析度影響。
  2. 窄窗 (weird_test)：合法解存在但只佔搜尋空間極小一部分 (0.0086%)，隨機搜尋
     幾乎撞不到，要靠種子機制的網格粗掃。
  3. 近地點通過次數 (今天推論出來、還沒實測)：高離心率軌道的積分誤差幾乎都產生在
     近地點通過的瞬間。逼搜尋熬過好幾次近地點通過，才會讓 Python 跟 GMAT 真正分岔。

以及今天學到「什麼會讓問題變簡單」，要刻意避開：
  - 遠地點慢速區既便宜又好算 (antialigned_highecc_test：0.38 km/s 的遠地點，
    35 度平面轉向只要 240 m/s，GMAT 只差 0.53 公尺)。所以 **B 要鎖在低軌道**，
    不讓它一開始就待在慢速區佔便宜。
  - 純位置攔截比軌道匹配便宜得多 (apoapsis_planechange_test 的教訓)，所以難度
    不能只靠「傾角差很大」堆出來，一定要有能量門檻墊底。

設計：B 在 LEO 圓軌道 (快、能量低)，A 是一條近地點就在 5 萬公里外的大橢圓
(B 想碰到 A 就必須先爬上去)，再加高傾角。B 每次近地點推進上限 1500 m/s，要爬到
A 的高度得燒好幾次，每次之間要繞完一整圈——強迫多次近地點通過。

這支腳本只做設計期偵察，不跑 L-SHADE。難度用實測衡量，不用形容詞。
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


def dv_to_reach(r_from, r_to):
    """從 r_from 圓軌道，把遠地點抬到 r_to 的最小 Δv (近地點切向燒最省)。"""
    v_circ = math.sqrt(MU / r_from)
    a_t = (r_from + r_to) / 2.0
    return (math.sqrt(MU * (2.0/r_from - 1.0/a_t)) - v_circ) * 1000.0, v_circ


def main():
    a_rp = A["SMA"] * (1 - A["ECC"])
    a_ra = A["SMA"] * (1 + A["ECC"])
    a_per = 2*math.pi*math.sqrt(A["SMA"]**3/MU)
    b_per = 2*math.pi*math.sqrt(B["SMA"]**3/MU)
    T_max = 4 * a_per

    print("=" * 72)
    print("幾何")
    print("=" * 72)
    print(f"A: SMA={A['SMA']:,.0f} ECC={A['ECC']} INC={A['INC']}deg")
    print(f"   近地點 {a_rp:,.0f} km  遠地點 {a_ra:,.0f} km  週期 {a_per:,.0f}s ({a_per/86400:.2f}天)")
    print(f"   -> A 的近地點就在 {a_rp:,.0f} km，B 想碰到它至少要爬到這個高度")
    print(f"B: SMA={B['SMA']:,.0f} 圓軌道 INC={B['INC']}deg  週期 {b_per:,.0f}s ({b_per/3600:.2f}小時)")
    print(f"   -> 鎖在低軌道，速度 {math.sqrt(MU/B['SMA']):.4f} km/s，享受不到遠地點慢速區的便宜")
    print(f"\nT_max = {T_max:,.0f}s ({T_max/86400:.2f} 天)，B 起始軌道可繞 {T_max/b_per:.0f} 圈")

    print("\n" + "=" * 72)
    print("難度軸 1：能量門檻（這是證明，不是網格統計）")
    print("=" * 72)
    dv_min, v_circ = dv_to_reach(B["SMA"], a_rp)
    v_esc = math.sqrt(2*MU/B["SMA"])
    print(f"  B 圓軌道速度 {v_circ:.4f} km/s，逃逸速度 {v_esc:.4f} km/s")
    print(f"  要把遠地點抬到 A 的近地點 ({a_rp:,.0f} km)：最小 Δv = {dv_min:,.1f} m/s")
    print(f"  每棒上限 1500 m/s -> 至少需要 {math.ceil(dv_min/1500)} 棒才可能合法")
    print(f"  ⚠️ 注意上限：從這個高度完全逃逸也只要 {(v_esc-v_circ)*1000:,.0f} m/s"
          f" = {math.ceil((v_esc-v_circ)*1000/1500)} 棒，")
    print(f"     所以「從 LEO 出發」這個設定本質上最多只能逼出 3 棒左右，逼不出更多。")

    print("\n" + "=" * 72)
    print("難度軸 3：要熬過幾次近地點通過")
    print("=" * 72)
    # 模擬連續近地點推進：每次燒 1500，算新週期
    v = v_circ
    total_time = 0.0
    for kick in range(1, 5):
        v_new = min(v + 1.5, math.sqrt(MU*(2/B["SMA"] - 1/(1e9))))  # 不要超過逃逸
        a_new = 1.0/(2.0/B["SMA"] - v_new**2/MU)
        if a_new <= 0:
            print(f"  第 {kick} 次推進後已經逃逸，停。")
            break
        ra_new = 2*a_new - B["SMA"]
        per_new = 2*math.pi*math.sqrt(a_new**3/MU)
        total_time += per_new
        print(f"  第 {kick} 次近地點推進 (+1500 m/s)：遠地點 -> {ra_new:,.0f} km，"
              f"新週期 {per_new:,.0f}s ({per_new/86400:.2f}天)")
        v = v_new
        if ra_new >= a_rp:
            print(f"     ✅ 已經搆到 A 的近地點高度 ({a_rp:,.0f} km)")
            print(f"     -> 累計要繞 {kick} 圈才爬得上來，也就是 {kick} 次近地點通過")
            break

    print("\n" + "=" * 72)
    print("難度軸 2：合法解有多稀有（Lambert 網格實掃，單棒）")
    print("=" * 72)
    A_r0, A_v0 = build(A)
    B_r0, B_v0 = build(B)
    dt = 60.0
    j2 = j3 = j4 = 0.0
    n_b, n_f = 110, 110
    best, legal, n_ok = np.inf, 0, 0
    for tb in np.linspace(0.0, T_max*0.8, n_b):
        r_b, v_b = propagate_dop853(B_r0, B_v0, tb, dt, MU, j2, j3, j4, RE)
        max_ft = T_max - tb
        if max_ft < 600:
            continue
        for ft in np.linspace(600.0, max_ft, n_f):
            r_a, _ = propagate_dop853(A_r0, A_v0, tb+ft, dt, MU, j2, j3, j4, RE)
            for pro in (True, False):
                try:
                    v1, _ = izzo(MU, r_b, r_a, ft, M=0, prograde=pro,
                                  lowpath=True, numiter=35, rtol=1e-8)
                except Exception:
                    continue
                n_ok += 1
                dv = fast_norm(v1 - v_b) * 1000.0
                if dv <= 1500.0:
                    legal += 1
                best = min(best, dv)
    print(f"  掃了 {n_b}x{n_f}x2 組，解出 {n_ok:,} 組")
    print(f"  最小單棒 Δv = {best:,.1f} m/s，合法組合 = {legal}")
    if legal == 0:
        print(f"  ✅ 單棒無解（跟能量門檻的證明一致，互相印證）")
    else:
        print(f"  ⚠️ 網格找到合法單棒解，跟能量下限矛盾——檢查設計是不是哪裡算錯")

    print("\n" + "=" * 72)
    print("建議的計分參數")
    print("=" * 72)
    print(f"  好解的總 Δv 量級 ≈ {dv_min:,.0f} m/s (爬升) + 平面/相位調整")
    print(f"  建議 C_v ≈ {dv_min*1.25:,.0f}")
    print(f"  建議 C_t ≈ {T_max*0.35:,.0f}s ({T_max*0.35/86400:.2f}天)")


if __name__ == "__main__":
    main()
