"""
設計「兩條超高離心率 (>0.9) 橢圓、不共面、而且遠地點指向相反 (在地球兩側)」的測資。

使用者想知道：這種幾何下工具找不找得到解。

為什麼這個幾何刁鑽：
  - 高離心率代表兩艘船絕大部分時間都待在遠地點附近 (慢、遠)，只有很短時間掃過
    近地點 (快、近)。
  - 遠地點指向相反 (AOP 差 180 度) 代表「兩邊都在遠地點」時，它們分別在地球的
    兩側，距離最遠——最舒服的慢速區完全錯開。
  - 不共面再加一層：連交會的位置都被限制在兩個軌道平面的交線 (節線) 附近。
  三個條件疊起來，可攔截的時機/位置都被壓得很窄。

⚠️ 重要前提：ECC>0.9 落在 STATUS.md「系統性測試軌道參數極限」那節標為不可信的
   區間 (0.9~0.95 誤差 2~9km 已逼近 5km 門檻，>0.95 可到 10~120km)。所以這組測資
   要回答的是**兩個獨立的問題**：
     (1) 搜尋找不找得到解？
     (2) 找到的解在真實 GMAT 裡站不站得住？
   刻意選 0.92/0.93 (警戒帶但還沒崩)，並且一定要跑 GMAT 對照把真實誤差量出來。

這支腳本只做設計期的可行性偵察 (不跑 L-SHADE)：把幾何算清楚，再用 Lambert 網格
實掃看看到底存不存在合法解——延續 perigee_kick 那次的紀律，不用解析公式下結論。
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

# A: 遠地點朝 +X 方向 (AOP=0)；B: 遠地點朝 -X (AOP=180)，兩邊背對背
#
# SMA 為什麼被迫這麼大：rp = SMA*(1-ECC)，ECC 越接近 1，要讓近地點浮出地表所需的
# SMA 就越大。ECC=0.92 要 rp>6600km 就得 SMA>82,500；ECC=0.93 要 SMA>94,286。
# 第一版用了 SMA 45,000/40,000，近地點直接掉到地球內部 (-2,778km / -3,578km)，
# config_validator 會擋下來——「高離心率」跟「小軌道」在物理上不能兼得。
A = dict(SMA=90000.0,  ECC=0.92, INC=0.0,  RAAN=0.0, AOP=0.0,   TA=180.0)
B = dict(SMA=100000.0, ECC=0.93, INC=35.0, RAAN=0.0, AOP=180.0, TA=180.0)


def facts(name, o):
    rp = o["SMA"] * (1 - o["ECC"])
    ra = o["SMA"] * (1 + o["ECC"])
    per = 2 * math.pi * math.sqrt(o["SMA"]**3 / MU)
    vp = math.sqrt(MU * (2/rp - 1/o["SMA"]))
    va = math.sqrt(MU * (2/ra - 1/o["SMA"]))
    flag = "  ⚠️ 近地點穿地球!" if rp < RE + 150 else ""
    print(f"{name}: SMA={o['SMA']:,.0f} ECC={o['ECC']} INC={o['INC']}deg AOP={o['AOP']}deg")
    print(f"   近地點 {rp:,.1f} km (高度 {rp-RE:,.1f} km){flag}")
    print(f"   遠地點 {ra:,.1f} km")
    print(f"   週期   {per:,.0f}s ({per/86400:.3f} 天)")
    print(f"   速度   近地點 {vp:.4f} km/s，遠地點 {va:.4f} km/s (相差 {vp/va:.1f} 倍)")
    return dict(rp=rp, ra=ra, per=per, vp=vp, va=va)


def build(o):
    orb = Orbit.from_classical(Earth, o["SMA"]*u.km, o["ECC"]*u.one, o["INC"]*u.deg,
                                o["RAAN"]*u.deg, o["AOP"]*u.deg, o["TA"]*u.deg)
    return (orb.r.to(u.km).value.astype(np.float64),
            orb.v.to(u.km/u.s).value.astype(np.float64))


def main():
    print("=" * 72)
    print("幾何")
    print("=" * 72)
    fa = facts("A (目標)", A)
    print()
    fb = facts("B (我方)", B)

    A_r0, A_v0 = build(A)
    B_r0, B_v0 = build(B)
    print(f"\n初始位置：A |r|={fast_norm(A_r0):,.1f} km  B |r|={fast_norm(B_r0):,.1f} km")
    cos_sep = np.dot(A_r0, B_r0) / (fast_norm(A_r0) * fast_norm(B_r0))
    print(f"初始張角 (地心夾角)：{math.degrees(math.acos(np.clip(cos_sep,-1,1))):.1f} 度"
          f"  <- 接近 180 度就是「在地球對面」")

    T_max = 4 * fa["per"]
    print(f"\nT_max = 4 x A週期 = {T_max:,.0f}s ({T_max/86400:.2f} 天)")
    print(f"B 在 T_max 內可繞 {T_max/fb['per']:.2f} 圈")

    print("\n" + "=" * 72)
    print("Lambert 網格實掃：到底存不存在合法解 (<=1500 m/s 單棒)")
    print("=" * 72)
    dt = 60.0
    j2 = j3 = j4 = 0.0
    n_b, n_f = 160, 160
    best = np.inf
    best_at = None
    legal = 0
    hist = []
    for tb in np.linspace(0.0, T_max*0.85, n_b):
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
                dv = fast_norm(v1 - v_b) * 1000.0
                hist.append(dv)
                if dv <= 1500.0:
                    legal += 1
                if dv < best:
                    best, best_at = dv, (tb, ft)

    hist = np.array(hist)
    print(f"  掃了 {n_b}x{n_f}x2 = {n_b*n_f*2:,} 組，成功解出 {len(hist):,} 組")
    print(f"  最小單棒 Δv = {best:,.1f} m/s  (t_burn={best_at[0]:,.0f}s, flight={best_at[1]:,.0f}s)")
    print(f"  合法 (<=1500) 組合數 = {legal:,}  ({100.0*legal/max(len(hist),1):.4f}% 的搜尋空間)")
    for q in (1, 5, 25, 50):
        print(f"    第 {q:2d} 百分位 Δv = {np.percentile(hist, q):,.1f} m/s")

    print("\n" + "=" * 72)
    print("評估")
    print("=" * 72)
    if legal == 0:
        print("  🔴 單棒完全沒有合法解——跟 perigee_kick 一樣是「只能靠多棒」的情境，")
        print("     但成因不同 (那組是能量不夠，這組是幾何/時機被壓死)。")
    elif 100.0*legal/len(hist) < 0.5:
        print(f"  ⚠️ 合法解存在但極稀有 ({legal:,} 組，佔 {100.0*legal/len(hist):.4f}%)——")
        print("     這正是 weird_test 那種「窄窗」地形，考驗種子機制找不找得到。")
    else:
        print("  ✅ 合法解不算罕見，這個幾何沒有想像中刁鑽，可能要再調參數加難度。")
    print(f"\n  建議 C_v ≈ {max(best*1.1, 1200):,.0f} (貼著實際最小值，才有鑑別力)")
    print(f"  建議 C_t ≈ {T_max*0.4:,.0f}s ({T_max*0.4/86400:.2f}天，T_max 的 40%)")


if __name__ == "__main__":
    main()
