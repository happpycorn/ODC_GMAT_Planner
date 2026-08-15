"""
設計一個「傾角差 90 度 + 兩邊軌道都有明顯遠地點」的極限測資。

動機 (STATUS.md「還沒做」清單第 15 項)：夜間種子機制的多棒 A/B 測試贏了，但
2026-08-15 正式預算驗證拆開來看，多棒解全部是 Δv=0 的退化單棒 —— 從來沒有展示
教科書等級的「在慢速點 (遠地點) 做平面轉向」策略。那組測資 (weird_test.json) 的
幾何本來就不適合示範這件事：A 的遠地點在 289,500km，B 在 LEO，兩者尺度差太多，
真正的瓶頸是窄窗時機而不是平面轉向。

這支腳本先把候選情境的物理算清楚 (週期、T_max、遠地點速度、平面轉向理論成本)，
確認「遠地點轉向」這個策略在 1500 m/s 單棒上限內真的做得到、而近地點轉向做不到，
再據此挑 C_t / C_v (計分 sigmoid 的半分中點，要落在好解的實際數值附近才有鑑別力)。
"""
import sys, os, math
import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

MU = 398600.4418  # km^3/s^2
RE = 6378.137


def orbit_facts(name, sma, ecc, inc_deg):
    rp = sma * (1 - ecc)
    ra = sma * (1 + ecc)
    period = 2 * math.pi * math.sqrt(sma**3 / MU)
    v_p = math.sqrt(MU * (2 / rp - 1 / sma))
    v_a = math.sqrt(MU * (2 / ra - 1 / sma))
    print(f"{name}: SMA={sma:,.0f} ECC={ecc} INC={inc_deg}deg")
    print(f"   近地點 rp={rp:,.1f} km (地表高度 {rp-RE:,.1f} km)"
          f"{'  <-- 穿地球!' if rp < RE + 200 else ''}")
    print(f"   遠地點 ra={ra:,.1f} km")
    print(f"   週期   T ={period:,.1f} s ({period/86400:.3f} 天)")
    print(f"   速度   近地點 {v_p:.4f} km/s   遠地點 {v_a:.4f} km/s")
    return {"rp": rp, "ra": ra, "period": period, "v_p": v_p, "v_a": v_a}


def plane_change_cost(v, angle_deg):
    """純平面轉向 (不改變速率大小) 的 Δv = 2 v sin(theta/2)。"""
    return 2 * v * math.sin(math.radians(angle_deg) / 2) * 1000.0  # m/s


if __name__ == "__main__":
    print("=" * 70)
    print("候選情境：兩邊都是大橢圓，只差在傾角 90 度")
    print("=" * 70)
    A = orbit_facts("A (目標)", 50000.0, 0.85, 90.0)
    print()
    B = orbit_facts("B (我方)", 48000.0, 0.84, 0.0)

    T_max = 4 * A["period"]
    print(f"\nT_max = 4 x A週期 = {T_max:,.1f} s ({T_max/86400:.3f} 天)")
    print(f"B 在 T_max 內可以繞 {T_max/B['period']:.2f} 圈")

    print("\n" + "=" * 70)
    print("關鍵：90 度平面轉向，在不同位置做的理論成本")
    print("=" * 70)
    for label, v in (("B 近地點 (最快)", B["v_p"]), ("B 遠地點 (最慢)", B["v_a"])):
        cost = plane_change_cost(v, 90.0)
        verdict = "✅ 合法 (<=1500)" if cost <= 1500 else "❌ 超標"
        print(f"  {label:<16} v={v:.4f} km/s  ->  Δv = {cost:8.1f} m/s   {verdict}")

    ratio = plane_change_cost(B["v_p"], 90.0) / plane_change_cost(B["v_a"], 90.0)
    print(f"\n  近地點/遠地點 成本比 = {ratio:.1f} 倍")
    print("  => 這個情境有明確的教科書答案：滑到遠地點再轉平面。")
    print("     如果搜尋出來的多棒解真的把大棒放在遠地點附近，就是多棒機制")
    print("     發揮預期效果的乾淨證據；如果又退化成單棒，就是反證。")

    print("\n" + "=" * 70)
    print("挑 C_t / C_v：計分是 25/(1+exp(k*(x-C)))，C 是半分中點")
    print("=" * 70)
    # 好解的 Δv 量級 = 遠地點轉向成本 + 一些形狀微調
    dv_good = plane_change_cost(B["v_a"], 90.0)
    print(f"  預期好解 Δv 量級 ≈ {dv_good:.0f} m/s (遠地點轉向) + 形狀微調")

    C_v, k_v = 1300.0, 0.01
    print(f"\n  選 C_v={C_v:.0f}, k_v={k_v}：")
    for dv in (900, 1100, 1202, 1300, 1500, 2000, 3000):
        s = 25.0 / (1.0 + math.exp(min(k_v * (dv - C_v), 700.0)))
        print(f"     Δv={dv:5d} m/s -> score_dv = {s:5.2f} / 25")

    C_t, k_t = 200000.0, 1e-5
    print(f"\n  選 C_t={C_t:,.0f}s ({C_t/86400:.2f}天), k_t={k_t}：")
    for t in (0, 50000, 104660, 200000, 300000, int(T_max)):
        s = 25.0 / (1.0 + math.exp(min(k_t * (t - C_t), 700.0)))
        print(f"     T={t:7d}s ({t/86400:5.2f}天) -> score_time = {s:5.2f} / 25")
    print("\n  (兩條都刻意不要在 [0, T_max] 內提早飽和 —— 第四階段的教訓："
          "\n   飽和會讓計分變成一片沒有梯度的平原，搜尋在上面亂漂。)")
