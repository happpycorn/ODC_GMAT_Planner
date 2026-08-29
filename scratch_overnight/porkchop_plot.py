"""把 porkchop 網格畫出來。兩張圖：ΔV 等高線 + 勝出的圈數。"""
import json, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import warnings; warnings.filterwarnings("ignore")
from src.optimizer import MissionOptimizer

H = int(sys.argv[1]) if len(sys.argv) > 1 else 20
d = np.load(os.path.join(REPO, "scratch_overnight", "porkchop_h%d.npz" % H))
DV, MREV, times = d["DV"], d["MREV"], d["times"]
n = len(times)
m = MissionOptimizer(json.load(open(os.path.join(REPO, "configs/official_sample.json"))))

# 轉成 (出發時刻, 飛行時間) 座標
# TOF 網格必須全是有限值（pcolormesh 不吃 NaN 座標），無效的格子改成遮罩資料本身
TOF = (np.arange(n)[None, :] - np.arange(n)[:, None]).astype(float) * H
dv_mps = np.where(np.isfinite(DV), DV * 1000.0, np.nan)

fig, axes = plt.subplots(1, 2, figsize=(15, 6))

ax = axes[0]
X, Y = np.meshgrid(times, times, indexing="ij")
lev = [200, 400, 800, 1500, 2500, 4000, 6000, 9000, 14000]
cf = ax.contourf(X / 1000.0, TOF / 1000.0, np.clip(dv_mps, 0, 14000),
                 levels=lev, cmap="viridis_r", extend="max")
ax.contour(X / 1000.0, TOF / 1000.0, dv_mps, levels=[1500.0],
           colors="red", linewidths=1.6)
plt.colorbar(cf, ax=ax, label="single-burn dV (m/s)")
ax.plot(0.0, 3.1583, "*", color="white", ms=22, mec="red", mew=2.0, zorder=5,
        label="our answer: 2 burns, 2242 m/s, dr 2.36 km, 90.43")
ax.annotate("ours", xy=(0.0, 3.1583), xytext=(3.0, 1.2), color="red", fontsize=9,
            arrowprops=dict(arrowstyle="->", color="red", lw=1.4), zorder=6)
ax.set_xlabel("departure time (ks)"); ax.set_ylabel("time of flight (ks)")
ax.set_title("Porkchop: single-burn intercept dV\nred contour = 1500 m/s per-burn rule limit")
ax.set_ylim(0, times[-1] / 1000.0); ax.set_xlim(0, times[-1] / 1000.0)
ax.legend(loc="upper right", fontsize=7.5)

ax = axes[1]
Mm = np.where(np.isfinite(DV) & (DV <= m.MAX_DV), MREV, np.nan)
im = ax.pcolormesh(X / 1000.0, TOF / 1000.0, Mm, cmap="tab10", vmin=-0.5, vmax=4.5,
                   shading="nearest")
plt.colorbar(im, ax=ax, label="winning revolution count M", ticks=[0, 1, 2, 3, 4])
ax.set_xlabel("departure time (ks)"); ax.set_ylabel("time of flight (ks)")
ax.set_title("Which Lambert branch wins (legal cells only)\n72% of them need M>=1 - the old M=0 default could not see those")
ax.set_ylim(0, times[-1] / 1000.0); ax.set_xlim(0, times[-1] / 1000.0)

plt.tight_layout()
out = os.path.join(REPO, "scratch_overnight", "porkchop.png")
plt.savefig(out, dpi=130)
print("saved", out)
