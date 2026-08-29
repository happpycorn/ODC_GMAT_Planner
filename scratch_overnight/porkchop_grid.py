"""單棒攔截的 Porkchop 全域網格：窮舉真值，不是「我們的最佳化器找到什麼」。

為什麼 (2026-08-29)：`sample_pareto_frontier.py` 畫的是**跑我們的最佳化器**在不同
時間上限下的輸出——那是「我們找到什麼」，不是「存在什麼」。要驗「有沒有找到全域
最佳」，唯一乾淨的方法是把子空間窮舉一遍。

單棒的情況剛好可以窮舉完備：決策就是 (出發時刻 t_dep, 飛行時間 TOF) 兩個變數，
ΔV = |v_Lambert(t_dep, TOF) - v_B(t_dep)|，因為規則只要求攔截、不要求共軌，
**到達端沒有脈衝**。所以這張網格就是單棒子空間的全域真值，一格不漏。

一次回答三件事：
  1. 我們的單棒解在不在全域谷底
  2. izzo 在轉移角接近 180 度時會丟 RuntimeError（我們接住當爛解），那些洞在哪、
     洞裡有沒有藏著更好的解
  3. 相位共振造成的多個局部最佳「島」長什麼樣，L-SHADE 有沒有訪問到
"""
import json, math, os, sys, time
import numpy as np
from numba import njit, prange
from poliastro.core.iod import izzo

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import warnings
warnings.filterwarnings("ignore")
from src.optimizer import MissionOptimizer          # noqa: E402
from src.core_math import propagate_dop853, fast_norm   # noqa: E402
from src.scorer import calculate_score              # noqa: E402


@njit(cache=True, parallel=True)
def build_ephemeris(r0, v0, times, dt, mu, j2, j3, j4, re):
    n = times.shape[0]
    R = np.zeros((n, 3)); V = np.zeros((n, 3))
    for i in prange(n):
        # 每一格都從 t=0 重新積分，不要累積遞推誤差
        r, v = propagate_dop853(r0, v0, times[i], dt, mu, j2, j3, j4, re)
        R[i, 0] = r[0]; R[i, 1] = r[1]; R[i, 2] = r[2]
        V[i, 0] = v[0]; V[i, 1] = v[1]; V[i, 2] = v[2]
    return R, V


@njit(cache=True, parallel=True)
def porkchop(RB, VB, RA, h, max_revs, min_tof_steps):
    """回傳 (最小 ΔV, 勝出的圈數, 勝出的分支數, 轉移角)。ΔV 單位 km/s。"""
    n = RB.shape[0]
    DV = np.full((n, n), np.nan)
    MREV = np.full((n, n), -1, dtype=np.int8)
    NSOL = np.zeros((n, n), dtype=np.int8)
    TANG = np.full((n, n), np.nan)
    for i in prange(n):
        r1 = RB[i]; v1 = VB[i]
        for j in range(i + min_tof_steps, n):
            tof = (j - i) * h
            r2 = RA[j]
            best = 1.0e18; best_m = -1; cnt = 0
            for m_rev in range(0, max_revs + 1):
                for lp in range(0, 2):
                    if m_rev == 0 and lp == 1:
                        continue
                    for pg in range(0, 2):
                        try:
                            vt, _ = izzo(398600.4418, r1, r2, tof, M=m_rev,
                                         prograde=(pg == 0), lowpath=(lp == 0),
                                         numiter=35, rtol=1e-8)
                        except Exception:
                            continue
                        cnt += 1
                        d = fast_norm(vt - v1)
                        if d < best:
                            best = d; best_m = m_rev
            if cnt > 0:
                DV[i, j] = best; MREV[i, j] = best_m; NSOL[i, j] = cnt
            # 轉移角（用來標出 180 度那條脊）
            n1 = fast_norm(r1); n2 = fast_norm(r2)
            c = (r1[0]*r2[0] + r1[1]*r2[1] + r1[2]*r2[2]) / (n1 * n2)
            if c > 1.0: c = 1.0
            elif c < -1.0: c = -1.0
            TANG[i, j] = math.acos(c) * 180.0 / math.pi
    return DV, MREV, NSOL, TANG


def main(h=30.0, max_revs=4):
    cfg = json.load(open(os.path.join(REPO, "configs", "official_sample.json")))
    m = MissionOptimizer(cfg)
    T_max = m.T_max
    times = np.arange(0.0, T_max + 1e-9, h)
    n = len(times)
    print("grid step %.0f s   nodes %d   T_max %.1f s   cells ~%.2f M"
          % (h, n, T_max, n * n / 2 / 1e6))

    t0 = time.time()
    RB, VB = build_ephemeris(m.B_r0, m.B_v0, times, 60.0, m.MU,
                            m.J2_VAL, m.J3_VAL, m.J4_VAL, m.RE_VAL)
    RA, VA = build_ephemeris(m.A_r0, m.A_v0, times, 60.0, m.MU,
                            m.J2_VAL, m.J3_VAL, m.J4_VAL, m.RE_VAL)
    print("ephemeris: %.1f s" % (time.time() - t0))

    min_tof_steps = max(1, int(math.ceil(m.MIN_COAST_TIME / h)))
    t0 = time.time()
    DV, MREV, NSOL, TANG = porkchop(RB, VB, RA, h, max_revs, min_tof_steps)
    print("porkchop : %.1f s" % (time.time() - t0))

    np.savez_compressed(os.path.join(REPO, "scratch_overnight",
                                     "porkchop_h%d.npz" % int(h)),
                        DV=DV, MREV=MREV, NSOL=NSOL, TANG=TANG, times=times)

    valid = np.isfinite(DV)
    upper = np.triu(np.ones_like(DV, dtype=bool), k=min_tof_steps)
    total = int(upper.sum())
    print("\ncells in range      : %d" % total)
    print("Lambert found a soln: %d  (%.3f%%)" % (valid.sum(), 100.0 * valid.sum() / total))
    holes = upper & ~valid
    print("all branches failed : %d  (%.4f%%)" % (holes.sum(), 100.0 * holes.sum() / total))
    if holes.sum():
        print("   those cells' transfer angle: min %.2f  median %.2f  max %.2f deg"
              % (np.nanmin(TANG[holes]), np.nanmedian(TANG[holes]), np.nanmax(TANG[holes])))

    # --- 全域最省 ΔV ---
    idx = np.unravel_index(np.nanargmin(np.where(valid, DV, np.inf)), DV.shape)
    i, j = idx
    print("\n=== global minimum dV (single burn, any legality) ===")
    print("   t_dep %.1f s   TOF %.1f s   arrival %.1f s   dV %.3f m/s   M=%d  angle %.2f deg"
          % (times[i], (j - i) * h, times[j], DV[i, j] * 1000.0, MREV[i, j], TANG[i, j]))

    # --- 全域最高分（Lambert 精確命中 -> Δr=0，所以距離項固定 50 分）---
    ARR = times[None, :] * np.ones((n, 1))
    S = np.where(valid, 50.0
                 + 25.0 / (1.0 + np.exp(np.clip(m.k_t * (ARR - m.C_t), -700, 700)))
                 + 25.0 / (1.0 + np.exp(np.clip(m.k_v * (DV * 1000.0 - m.C_v), -700, 700)))
                 - 10.0 * (DV > m.MAX_DV), -np.inf)
    k = np.unravel_index(np.nanargmax(S), S.shape)
    print("\n=== global maximum score (assumes dr=0; legality penalty included) ===")
    print("   t_dep %.1f s   TOF %.1f s   arrival %.1f s   dV %.3f m/s   M=%d  score %.4f"
          % (times[k[0]], (k[1] - k[0]) * h, times[k[1]], DV[k] * 1000.0, MREV[k], S[k]))

    # --- 只看合法的（單棒 <= MAX_DV）---
    legal = valid & (DV <= m.MAX_DV)
    print("\nlegal cells (dV <= %.0f m/s): %d (%.2f%%)"
          % (m.MAX_DV * 1000.0, legal.sum(), 100.0 * legal.sum() / total))
    if legal.sum():
        Sl = np.where(legal, S, -np.inf)
        kl = np.unravel_index(np.nanargmax(Sl), Sl.shape)
        print("   best legal: t_dep %.1f  TOF %.1f  arrival %.1f  dV %.3f m/s  M=%d  score %.4f"
              % (times[kl[0]], (kl[1] - kl[0]) * h, times[kl[1]],
                 DV[kl] * 1000.0, MREV[kl], S[kl]))
        dmin = np.unravel_index(np.nanargmin(np.where(legal, DV, np.inf)), DV.shape)
        print("   cheapest legal: t_dep %.1f  TOF %.1f  arrival %.1f  dV %.3f m/s  M=%d"
              % (times[dmin[0]], (dmin[1] - dmin[0]) * h, times[dmin[1]],
                 DV[dmin] * 1000.0, MREV[dmin]))

    # --- 多圈到底貢獻了多少 ---
    print("\nwinning revolution count among legal cells:")
    for mv in range(0, max_revs + 1):
        c = int((legal & (MREV == mv)).sum())
        print("   M=%d : %7d cells (%5.2f%%)" % (mv, c, 100.0 * c / max(1, legal.sum())))
    return times, DV, MREV, NSOL, TANG, S, m


if __name__ == "__main__":
    h = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
    main(h)
