"""
重驗 weird_test.json 的結論 —— 2026-08-15 傍晚發現傳播器容忍度太鬆之後。

背景：舊預設 (rtol=1e-9, atol=1e-6) 在高離心率軌道上，誤差會隨「近地點通過次數」
累積。weird_test 的 A 是 SMA=150,000 / ECC=0.93，實測跨越 T_max 誤差達 223 km。
先前那套「藏在 0.0086% 窄窗裡的 1,189.73 m/s 合法單棒解」的分析全部是在舊容忍度
下做的，**A 的位置可能一直是錯的**。

這支腳本回答四件事：
  1. 舊容忍度下 A/B 的位置到底錯多少 (用 rtol=1e-14 當基準)
  2. 那個 1,189.73 m/s 的解，用正確的傳播重算還是多少
  3. 窄窗還在不在、位置有沒有移動、寬度有沒有變
  4. 「第三層模型分岔」到底是容忍度還是缺 J3/J4 造成的

GRAVITY_DEGREE=4 所以沒有解析解可用，改用 rtol=1e-14/atol=1e-11 當「真值」——
比新預設再緊 100 倍，兩者若一致就代表新預設已經收斂。
"""
import sys, os, math, json
import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

import warnings
warnings.filterwarnings("ignore")
from src.optimizer import MissionOptimizer
from src.core_math import propagate_dop853, fast_norm
from poliastro.core.iod import izzo

OLD = dict(rtol=1e-9, atol=1e-6)      # 修正前的預設
NEW = dict(rtol=1e-12, atol=1e-9)     # 修正後的預設
REF = dict(rtol=1e-14, atol=1e-11)    # 當真值用

# 先前記錄的窄窗解 (STATUS.md「第五階段」)
CLAIM_TW = 1_714_683.0
CLAIM_FT = 6_800.0
CLAIM_DV = 1_189.73


def load():
    cfg = json.load(open("configs/weird_test.json"))
    c = dict(cfg); c["optimization"] = dict(cfg["optimization"])
    c["optimization"]["MAX_BURNS"] = [1]
    return MissionOptimizer(c)


def prop(opt, r0, v0, t, tol):
    return propagate_dop853(r0, v0, float(t), 60.0, opt.MU,
                             opt.J2_VAL, opt.J3_VAL, opt.J4_VAL, opt.RE_VAL, **tol)


def lam_dv(mu, r0, v0, r_t, tof):
    best = float("inf")
    for pro in (True, False):
        try:
            v1, _ = izzo(mu, r0, r_t, float(tof), M=0, prograde=pro,
                          lowpath=True, numiter=35, rtol=1e-8)
        except Exception:
            continue
        best = min(best, fast_norm(v1 - v0))
    return best * 1000.0


def main():
    opt = load()
    print("=" * 74)
    print(f"weird_test 重驗 (GRAVITY_DEGREE={opt.GRAVITY_DEGREE}, "
          f"T_max={opt.T_max:,.0f}s = {opt.T_max/86400:.2f} 天)")
    print("=" * 74)

    # --- 1. 位置誤差 ---
    print("\n[1] 舊容忍度的位置誤差 (以 rtol=1e-14 為真值)")
    print(f"{'目標':<6}{'時刻':>14}{'舊預設誤差':>15}{'新預設誤差':>15}")
    print("-" * 52)
    t_hit = CLAIM_TW + CLAIM_FT
    for label, r0, v0, t in (("A", opt.A_r0, opt.A_v0, t_hit),
                              ("B", opt.B_r0, opt.B_v0, CLAIM_TW)):
        ref, _ = prop(opt, r0, v0, t, REF)
        old, _ = prop(opt, r0, v0, t, OLD)
        new, _ = prop(opt, r0, v0, t, NEW)
        print(f"{label:<6}{t:>13,.0f}s{fast_norm(old-ref):>13,.3f}km{fast_norm(new-ref):>13,.3f}km")

    # --- 2. 重算宣稱的解 ---
    print(f"\n[2] 先前宣稱的窄窗解 (t_wait={CLAIM_TW:,.0f}s, flight={CLAIM_FT:,.0f}s, "
          f"Δv={CLAIM_DV:,.2f} m/s) 重算")
    for name, tol in (("舊預設", OLD), ("新預設", NEW), ("參考值", REF)):
        r_b, v_b = prop(opt, opt.B_r0, opt.B_v0, CLAIM_TW, tol)
        r_a, _ = prop(opt, opt.A_r0, opt.A_v0, t_hit, tol)
        dv = lam_dv(opt.MU, r_b, v_b, r_a, CLAIM_FT)
        verdict = "✅ 合法" if dv <= opt.MAX_DV * 1000 else "❌ 超標"
        print(f"   {name:<8} Δv = {dv:>10,.2f} m/s   {verdict}")

    # --- 3. 窄窗還在不在 ---
    print(f"\n[3] 用新容忍度重掃窄窗 (t_wait ± 3000s，flight 固定 {CLAIM_FT:,.0f}s)")
    cap = opt.MAX_DV * 1000
    for name, tol in (("舊預設", OLD), ("新預設", NEW)):
        legal_tw = []
        best = (float("inf"), None)
        for tw in np.arange(CLAIM_TW - 3000, CLAIM_TW + 3000, 25.0):
            r_b, v_b = prop(opt, opt.B_r0, opt.B_v0, tw, tol)
            r_a, _ = prop(opt, opt.A_r0, opt.A_v0, tw + CLAIM_FT, tol)
            dv = lam_dv(opt.MU, r_b, v_b, r_a, CLAIM_FT)
            if dv < best[0]:
                best = (dv, tw)
            if dv <= cap:
                legal_tw.append(tw)
        if legal_tw:
            width = max(legal_tw) - min(legal_tw) + 25.0
            print(f"   {name}: 最小 Δv={best[0]:,.1f} m/s @ t_wait={best[1]:,.0f}s，"
                  f"合法窗寬 ≈ {width:,.0f}s ({100*width/opt.T_max:.4f}% of T_max)")
        else:
            print(f"   {name}: 這個範圍內**沒有**合法解，最小 Δv={best[0]:,.1f} m/s "
                  f"@ t_wait={best[1]:,.0f}s")

    # --- 4. 容忍度 vs 重力階數，誰才是模型分岔的主因 ---
    print("\n[4] 「第三層模型分岔」的歸因：容忍度 vs 重力階數")
    print("    (同一條 A 軌道傳播到攔截時刻，比較各種組合跟「J4+極緊容忍度」的差距)")
    ref4, _ = propagate_dop853(opt.A_r0, opt.A_v0, t_hit, 60.0, opt.MU,
                                opt.J2_VAL, opt.J3_VAL, opt.J4_VAL, opt.RE_VAL, **REF)
    combos = [
        ("J2+J3+J4, 舊容忍度", opt.J2_VAL, opt.J3_VAL, opt.J4_VAL, OLD),
        ("J2+J3+J4, 新容忍度", opt.J2_VAL, opt.J3_VAL, opt.J4_VAL, NEW),
        ("只有 J2,  舊容忍度", opt.J2_VAL, 0.0, 0.0, OLD),
        ("只有 J2,  新容忍度", opt.J2_VAL, 0.0, 0.0, NEW),
        ("純點質量, 新容忍度", 0.0, 0.0, 0.0, NEW),
    ]
    for label, j2, j3, j4, tol in combos:
        r, _ = propagate_dop853(opt.A_r0, opt.A_v0, t_hit, 60.0, opt.MU,
                                 j2, j3, j4, opt.RE_VAL, **tol)
        print(f"    {label:<22} 差 {fast_norm(r - ref4):>10,.3f} km")
    print("\n    -> 如果「舊容忍度」那幾行的差距遠大於「只有 J2 vs J4」的差距，")
    print("       就代表當初把分岔歸因給缺 J3/J4 是歸錯了，主因是容忍度。")


if __name__ == "__main__":
    main()
