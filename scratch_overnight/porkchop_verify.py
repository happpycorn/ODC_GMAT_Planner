"""把 porkchop 網格的頂端格子用真傳播器重播，量「網格分數」跟「真分數」的落差。

網格算 ΔV 用的是二體 Lambert，但星曆是 J2/J3/J4 積出來的——所以網格說的
「Δr = 0（精確命中）」在實際飛的時候不成立。網格分數是**上界**，真分數要重播才知道。

同時輸出單棒的窮舉下界曲線 ΔV_min(抵達時間)，那是這個子空間的 Pareto 前緣真值，
可以直接跟最佳化器找到的點對照。
"""
import json, math, os, sys
import numpy as np
from poliastro.core.iod import izzo

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import warnings
warnings.filterwarnings("ignore")
from src.optimizer import MissionOptimizer
from src.core_math import propagate_dop853, fast_norm
from src.scorer import calculate_score

H = int(sys.argv[1]) if len(sys.argv) > 1 else 20
d = np.load(os.path.join(REPO, "scratch_overnight", "porkchop_h%d.npz" % H))
DV, MREV, TANG, times = d["DV"], d["MREV"], d["TANG"], d["times"]
n = len(times)

cfg = json.load(open(os.path.join(REPO, "configs", "official_sample.json")))
m = MissionOptimizer(cfg)
MU, DT = m.MU, 60.0
GRAV = (m.J2_VAL, m.J3_VAL, m.J4_VAL, m.RE_VAL)


def state(r0, v0, t):
    return propagate_dop853(r0, v0, float(t), DT, MU, *GRAV)


def replay(i, j):
    """單棒方案的忠實重播：真傳播器 + 真計分。"""
    t_dep, t_arr = times[i], times[j]
    tof = t_arr - t_dep
    r1, v1 = state(m.B_r0, m.B_v0, t_dep)
    r2, _ = state(m.A_r0, m.A_v0, t_arr)
    best = None
    for mv in range(0, 5):
        for lp in (0, 1):
            if mv == 0 and lp == 1:
                continue
            for pg in (0, 1):
                try:
                    vt, _ = izzo(MU, r1, r2, tof, M=mv, prograde=(pg == 0),
                                 lowpath=(lp == 0), numiter=35, rtol=1e-8)
                except Exception:
                    continue
                dv = fast_norm(vt - v1)
                if best is None or dv < best[0]:
                    best = (dv, vt)
    if best is None:
        return None
    dv, vt = best
    rf, _ = state(r1, vt, tof)              # 燒完之後真的飛一遍
    miss = float(np.linalg.norm(rf - r2))
    pen = 1 if dv > m.MAX_DV else 0
    sc = calculate_score(miss, t_arr, dv * 1000.0, pen, m.k_t, m.C_t, m.k_v, m.C_v)
    return dict(t_dep=t_dep, t_arr=t_arr, tof=tof, dv_mps=dv * 1000.0,
                miss_km=miss, pen=pen, score=sc)


# ---- 網格分數（Δr=0 的上界）----
valid = np.isfinite(DV)
ARR = times[None, :] * np.ones((n, 1))
S = np.where(valid, 50.0
             + 25.0 / (1.0 + np.exp(np.clip(m.k_t * (ARR - m.C_t), -700, 700)))
             + 25.0 / (1.0 + np.exp(np.clip(m.k_v * (DV * 1000.0 - m.C_v), -700, 700)))
             - 10.0 * (DV > m.MAX_DV), -np.inf)

flat = np.argsort(S, axis=None)[::-1][:12]
print("=== 網格前 12 名，用真傳播器重播 ===")
print("%8s %8s %10s %9s %9s %8s %8s %7s" %
      ("t_dep", "TOF", "arrive", "dV_mps", "miss_km", "grid_S", "real_S", "gap"))
for f in flat:
    i, j = np.unravel_index(f, S.shape)
    r = replay(i, j)
    if r is None:
        continue
    print("%8.0f %8.0f %10.0f %9.2f %9.4f %8.3f %8.3f %+7.3f"
          % (r["t_dep"], r["tof"], r["t_arr"], r["dv_mps"], r["miss_km"],
             S[i, j], r["score"], r["score"] - S[i, j]))

# ---- 只看合法（單棒 <= 1500 m/s）的前 8 名 ----
Sl = np.where(valid & (DV <= m.MAX_DV), S, -np.inf)
print("\n=== 合法單棒前 8 名（每棒 <= %.0f m/s）===" % (m.MAX_DV * 1000))
for f in np.argsort(Sl, axis=None)[::-1][:8]:
    i, j = np.unravel_index(f, S.shape)
    r = replay(i, j)
    if r is None:
        continue
    print("%8.0f %8.0f %10.0f %9.2f %9.4f %8.3f %8.3f %+7.3f"
          % (r["t_dep"], r["tof"], r["t_arr"], r["dv_mps"], r["miss_km"],
             Sl[i, j], r["score"], r["score"] - Sl[i, j]))

# ---- 窮舉下界：ΔV_min(抵達時間) ----
env = np.where(valid, DV, np.inf).min(axis=0) * 1000.0
print("\n=== 單棒窮舉下界 ΔV_min(抵達時間) ===")
print("%10s %12s   %s" % ("arrive_s", "dV_min_mps", "M"))
for t_target in (3000, 3158, 3500, 4000, 5000, 6121, 8000, 11928, 16000, 20600):
    j = int(np.argmin(np.abs(times - t_target)))
    if not np.isfinite(env[j]):
        continue
    i = int(np.nanargmin(np.where(valid[:, j], DV[:, j], np.inf)))
    print("%10.0f %12.2f   M=%d   (t_dep %.0f)" % (times[j], env[j], MREV[i, j], times[i]))

print("\n我們實際交出去的答案：2 棒 2242.0 m/s、抵達 3158.3 s、Δr 2.36 km、90.43 分")
j = int(np.argmin(np.abs(times - 3158.3)))
i = int(np.nanargmin(np.where(valid[:, j], DV[:, j], np.inf)))
print("同一個抵達時間的單棒理論下界：%.2f m/s（t_dep %.0f, M=%d）— 我們多付 %.2f%%"
      % (env[j], times[i], MREV[i, j], 100.0 * (2242.0 - env[j]) / env[j]))
