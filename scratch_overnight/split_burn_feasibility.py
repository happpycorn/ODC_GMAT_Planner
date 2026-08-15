"""
「把一棒太大的燒拆成多棒」到底行不行？——用 hyper_fast (ECC=5) 當測試對象。

背景：ECC=5 那組情境，搜尋交出的最佳解是「花 611,787 m/s 買一次違規」(Score 62.76)。
`feasibility.py` 說單棒 0/14,400、切向階梯三棒也沒找到，但它自己標註了「這不等於無解，
只試了一個家族」。今天已經學到那個標註要當真 —— 所以自己再試一個**不同的**家族。

構造：貪婪式的「連續 Lambert 重新瞄準」。
  1. 在 t0 用 Lambert 算「要多少 Δv 才能在 t_arrive 抵達瞄準點」，得到需求 D。
  2. D 超過每棒上限就只燒上限那麼多 (沿 Lambert 方向)，滑行 MIN_INTERVAL，
     再從新狀態重算一次 —— 因為位置變了，需求也會變。
  3. 直到某一次的需求 <= 上限，整個燒完收尾。
這跟階梯種子不同：階梯是「在近地點沿速度方向爬升 + 整數週期滑行」，這裡是
「沿 Lambert 方向連續修正」，兩者涵蓋的區域不一樣。

如果這樣能找到合法解，那 611,787 m/s 那個結果就是**搜尋能力問題**（合法解存在但沒找到），
不是「這組情境本來就無解」。兩者的處理方式完全不同，所以要先分清楚。
"""

import sys, os, math, json, itertools
import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import warnings
warnings.filterwarnings("ignore")
from src.core_math import propagate_dop853, fast_norm, check_constraints
from poliastro.core.iod import izzo
from poliastro.bodies import Earth
from poliastro.twobody import Orbit
from astropy import units as u

MU = 398600.4418
RE = 6378.137
MIN_PERI = RE + 100.0

CFG = json.load(open(os.path.join(REPO_ROOT, "configs", "hyper_fast.json")))
CAP = CFG["rules"]["MAX_DV_MPS"]                    # m/s
MIN_INT = CFG["rules"]["MIN_MANEUVER_INTERVAL_SEC"]  # s
T_MAX = CFG["rules"]["T_MAX_SEC"]
k_t, C_t = CFG["rules"]["k_t"], CFG["rules"]["C_t"]
k_v, C_v = CFG["rules"]["k_v"], CFG["rules"]["C_v"]
MISS_TOL = CFG["strategy"]["MISS_TOLERANCE_KM"]


def build(o):
    orb = Orbit.from_classical(Earth, o["SMA"]*u.km, o["ECC"]*u.one, o["INC"]*u.deg,
                                o["RAAN"]*u.deg, o["AOP"]*u.deg, o["TA"]*u.deg)
    return (orb.r.to(u.km).value.astype(np.float64),
            orb.v.to(u.km/u.s).value.astype(np.float64))


A_r0, A_v0 = build(CFG["orbit_A"])
B_r0, B_v0 = build(CFG["orbit_B"])


def score(dr_km, t_sec, dv_mps, viol):
    s = 50.0*math.exp(-(dr_km - 5.0)/100.0)
    s += 25.0/(1.0 + math.exp(k_t*(t_sec - C_t)))
    s += 25.0/(1.0 + math.exp(k_v*(dv_mps - C_v)))
    return s - 10.0*viol


def lambert_dv(r0, v0, r_t, tof):
    """回傳 (需求 Δv 向量 km/s, 大小 m/s)，取順逆行較省的那個。"""
    best_vec, best = None, float("inf")
    for pro in (True, False):
        try:
            v1, _ = izzo(MU, r0, r_t, float(tof), M=0, prograde=pro,
                          lowpath=True, numiter=35, rtol=1e-8)
        except Exception:
            continue
        d = fast_norm(v1 - v0)
        if d < best:
            best, best_vec = d, (v1 - v0)
    return best_vec, best*1000.0


def try_split(t_start, t_arrive, max_burns=6):
    """從 t_start 開始，貪婪拆棒，目標是在 t_arrive 抵達 A 的位置。"""
    r_c, v_c = propagate_dop853(B_r0, B_v0, float(t_start), 60.0, MU, 0, 0, 0, RE)
    r_a, _ = propagate_dop853(A_r0, A_v0, float(t_arrive), 60.0, MU, 0, 0, 0, RE)
    t_now = float(t_start)
    burns, total = [], 0.0

    for i in range(max_burns):
        tof = t_arrive - t_now
        if tof < 60.0:
            return None
        vec, mag = lambert_dv(r_c, v_c, r_a, tof)
        if vec is None:
            return None
        if mag <= CAP:
            # 最後一棒，整個燒完
            v_new = v_c + vec
            if not check_constraints(r_c, v_new, MU, MIN_PERI):
                return None
            burns.append((t_now, mag))
            total += mag
            return {"burns": burns, "total": total, "t_arrive": t_arrive,
                    "n": len(burns)}
        # 只燒上限，沿 Lambert 需求的方向
        u_hat = vec / fast_norm(vec)
        v_new = v_c + u_hat*(CAP/1000.0)
        if not check_constraints(r_c, v_new, MU, MIN_PERI):
            return None
        burns.append((t_now, CAP))
        total += CAP
        r_c, v_c = propagate_dop853(r_c, v_new, MIN_INT, 60.0, MU, 0, 0, 0, RE)
        t_now += MIN_INT
    return None


if __name__ == "__main__":
    print("=" * 82)
    print("拆棒可行性：hyper_fast (ECC=5.0，T_max=9,101s)")
    print("=" * 82)
    print(f"每棒上限 {CAP:,.0f} m/s，機動間隔下限 {MIN_INT:.0f}s\n")

    best = None
    tried = 0
    for t_start in np.linspace(0.0, T_MAX*0.55, 90):
        for t_arrive in np.linspace(float(t_start)+300.0, T_MAX, 90):
            tried += 1
            out = try_split(float(t_start), float(t_arrive))
            if out is None:
                continue
            s = score(MISS_TOL, out["t_arrive"], out["total"], 0)
            if best is None or s > best[0]:
                best = (s, out)

    print(f"掃了 {tried:,} 組 (起燒時刻 x 抵達時刻)")
    if best is None:
        print("\n找不到任何合法拆棒解。")
        print("這**仍然不等於無解**——這裡只試了「連續 Lambert 重新瞄準」這一個家族。")
        sys.exit(0)

    s, out = best
    print(f"\n找到合法解！{out['n']} 棒，總 Δv = {out['total']:,.1f} m/s，"
          f"抵達時刻 {out['t_arrive']:,.0f}s")
    for i, (t, m) in enumerate(out["burns"], 1):
        tag = "最後一棒" if i == out["n"] else f"Burn {i}"
        print(f"    [{tag:<9}] t={t:>9,.1f}s   Δv={m:>9,.1f} m/s"
              + ("  <= 貼上限" if m >= CAP-0.5 else ""))
    print(f"\n  估計 Score = {s:.2f}（0 違規）")
    print(f"  搜尋交出的違規解 Score = 62.76（611,787 m/s，1 次違規）")
    if s > 62.76:
        print(f"\n  >>> 合法解分數高出 {s-62.76:.2f} 分。")
        print("      所以搜尋買違規**不是**因為無解，也不是因為誘因不足——")
        print("      是**沒找到**。這跟 hard_mode 當初的診斷是同一類問題（能力，不是誘因）。")
    else:
        print(f"\n  >>> 合法解分數反而較低（差 {62.76-s:.2f} 分）。")
        print("      那搜尋買違規是**理性的**，問題出在規則的懲罰設計，不是搜尋。")
