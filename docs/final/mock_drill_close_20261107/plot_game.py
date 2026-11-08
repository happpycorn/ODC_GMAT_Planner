"""把一場 organizer 對局匯出成路徑 CSV 並畫圖。在 medal/ 下跑：
    .venv/bin/python ../docs/final/mock_drill_close_20261107/plot_game.py <organizer_log.json> <輸出資料夾>
起點讀本資料夾的 usb/initial_state.csv，推力讀 organizer_log.json（雙方每回合的 Δv），用金牌賽引擎的二體傳播取樣。
"""
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.getcwd())

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from final_copilot import _parse_state, _rv  # noqa: E402
from game.core import sma_official  # noqa: E402
from physics import EARTH_MU, RE_VAL  # noqa: E402
from physics.propagator import propagate  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
spec = __import__("importlib.util").util.spec_from_file_location("org", os.path.join(HERE, "organizer.py"))
org = __import__("importlib.util").util.module_from_spec(spec)
spec.loader.exec_module(org)

W = org.RULES["window_sec"]
RCAP = org.RULES["capture_radius_km"]
ZONE = org.RULES["safe_sma_km"]
STEP = 2.0
C_P, C_E = "#eb6834", "#2a78d6"   # 追方 orange、躲方 blue（分類色 2、1）
INK, MUTED, GRID, SURF = "#1f1f1e", "#6b6a64", "#e4e3de", "#fcfcfb"

plt.rcParams.update({"font.family": ["Heiti TC", "PingFang TC", "Arial Unicode MS", "sans-serif"],
                     "axes.unicode_minus": False, "axes.edgecolor": GRID, "axes.labelcolor": MUTED,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.facecolor": SURF, "figure.facecolor": SURF,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "font.size": 10})


def rsw(r, v):
    rh = r / np.linalg.norm(r)
    wh = np.cross(r, v)
    wh /= np.linalg.norm(wh)
    return np.vstack([rh, np.cross(wh, rh), wh])


def main():
    log = json.load(open(sys.argv[1], encoding="utf-8"))
    out = sys.argv[2]
    os.makedirs(out, exist_ok=True)
    st, _ = _parse_state(os.path.join(HERE, "usb/initial_state.csv"),
                         names={"pursuer": [org.NAMES["pursuer"]], "evader": [org.NAMES["evader"]]})
    rp, vp = _rv(st, "pursuer")
    re, ve = _rv(st, "evader")
    role = log["role"]
    rows, burns = [(0.0, rp.copy(), vp.copy(), re.copy(), ve.copy())], []
    h0 = np.cross(re, ve)
    h0 /= np.linalg.norm(h0)
    for k, rd in enumerate(log["rounds"]):
        dv = {role: np.array(rd["our_dv"]), ("pursuer" if role == "evader" else "evader"): np.array(rd["opp_dv"])}
        for side in ("pursuer", "evader"):
            d = dv[side]
            n = np.linalg.norm(d)
            if n > 200.0:
                d = d * 200.0 / n
            dv[side] = d / 1000.0
        burns.append((k * W, rp.copy(), re.copy(), np.linalg.norm(dv["pursuer"]) * 1e3, np.linalg.norm(dv["evader"]) * 1e3))
        vp, ve = vp + dv["pursuer"], ve + dv["evader"]
        t = 0.0
        while True:
            rows.append((k * W + t, rp.copy(), vp.copy(), re.copy(), ve.copy()))
            if t >= W - 1e-9:
                break
            h = min(STEP, W - t)
            rp, vp = propagate(EARTH_MU, rp, vp, h, 0)
            re, ve = propagate(EARTH_MU, re, ve, h, 0)
            t += h
            # 捕獲就停
            if np.linalg.norm(rp - re) <= RCAP:
                rows.append((k * W + t, rp.copy(), vp.copy(), re.copy(), ve.copy()))
                break
        if np.linalg.norm(rp - re) <= RCAP:
            break

    T = np.array([r[0] for r in rows])
    P = np.array([r[1] for r in rows])
    E = np.array([r[3] for r in rows])
    D = np.linalg.norm(P - E, axis=1)
    AP = np.array([sma_official(r[1], r[2]) for r in rows])
    AE = np.array([sma_official(r[3], r[4]) for r in rows])
    start = org.START

    with open(os.path.join(out, "trajectory.csv"), "w", encoding="utf-8") as f:
        f.write("t_sec,utc,round,p_x,p_y,p_z,p_vx,p_vy,p_vz,e_x,e_y,e_z,e_vx,e_vy,e_vz,dist_km,a_p_km,a_e_km\n")
        for (t, rp_, vp_, re_, ve_), d, ap, ae in zip(rows, D, AP, AE):
            utc = (start + dt.timedelta(seconds=float(t))).strftime("%Y-%m-%dT%H:%M:%S")
            rnd = min(int(t // W) + 1, len(log["rounds"]))
            f.write(f"{t:.1f},{utc},{rnd}," + ",".join(f"{x:.6f}" for x in (*rp_, *vp_, *re_, *ve_))
                    + f",{d:.6f},{ap:.6f},{ae:.6f}\n")

    fig = plt.figure(figsize=(14, 10.5))
    gs = fig.add_gridspec(2, 2, hspace=0.32, wspace=0.22)

    # (1) 3D
    ax = fig.add_subplot(gs[0, 0], projection="3d")
    ax.set_facecolor(SURF)
    u, v = np.mgrid[0:2 * np.pi:40j, 0:np.pi:20j]
    ax.plot_wireframe(RE_VAL * np.cos(u) * np.sin(v), RE_VAL * np.sin(u) * np.sin(v), RE_VAL * np.cos(v),
                      color=GRID, linewidth=0.5)
    ax.plot(*P.T, color=C_P, lw=2, label=f"追方 {org.NAMES['pursuer']}")
    ax.plot(*E.T, color=C_E, lw=2, label=f"躲方 {org.NAMES['evader']}")
    for t0, bp, be, _, _ in burns:
        ax.scatter(*bp, color=C_P, s=36, edgecolor=SURF, linewidth=1.5, depthshade=False)
        ax.scatter(*be, color=C_E, s=36, edgecolor=SURF, linewidth=1.5, depthshade=False)
    i = int(np.argmin(D))
    ax.scatter(*E[i], marker="x", color=INK, s=60, depthshade=False)
    ax.text(*E[i], f"  最近 {D[i]:.2f} km", color=INK, fontsize=9)
    lim = np.abs(np.vstack([P, E])).max()
    ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim); ax.set_zlim(-lim, lim)
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev=float(np.degrees(np.arcsin(h0[2]))) - 25.0, azim=float(np.degrees(np.arctan2(h0[1], h0[0]))))
    ax.set_xlabel("X km"); ax.set_ylabel("Y km"); ax.set_zlabel("Z km")
    ax.set_title("ECI 路徑（從軌道面法向斜看；點＝每回合起點推力）", color=INK, loc="left")
    ax.legend(loc="upper left", frameon=False)

    # (2) 距離
    ax = fig.add_subplot(gs[0, 1])
    ax.semilogy(T / 60, D, color=INK, lw=2)
    ax.axhline(RCAP, color="#d03b3b", lw=1.2, ls="--")
    ax.text(0.5, RCAP * 0.82, f"R_cap {RCAP:.0f} km", color="#d03b3b", fontsize=9, va="top")
    for k in range(len(log["rounds"]) + 1):
        ax.axvline(k * W / 60, color=GRID, lw=1)
    for k in range(len(log["rounds"])):
        m = (T >= k * W) & (T <= (k + 1) * W)
        if m.any():
            j = np.argmin(np.where(m, D, np.inf))
            ax.scatter(T[j] / 60, D[j], s=40, color=INK, zorder=3, edgecolor=SURF, linewidth=1.5)
            ax.annotate(f"R{k + 1} {D[j]:.1f}", (T[j] / 60, D[j]), xytext=(7, -4), textcoords="offset points",
                        fontsize=9, color=INK, va="top")
    ax.set_xlabel("比賽時間（分）"); ax.set_ylabel("雙方距離 km（對數）")
    ax.set_title("距離與每回合最近點", color=INK, loc="left")

    # (3) 半長軸
    ax = fig.add_subplot(gs[1, 0])
    ax.axhspan(*ZONE, color="#1baf7a", alpha=0.18, lw=0)
    ax.text(1, ZONE[0] - 30, f"安全空域 {ZONE[0]:.0f}–{ZONE[1]:.0f} km", color="#147a55", fontsize=9,
            ha="left", va="top")
    ax.plot(T / 60, AP, color=C_P, lw=2, label="追方 a")
    ax.plot(T / 60, AE, color=C_E, lw=2, label="躲方 a")
    ax.annotate(f"結束 a = {AE[-1]:.1f} km（下界 +{AE[-1] - ZONE[0]:.1f}）", (T[-1] / 60, AE[-1]), xytext=(-60, -55),
                textcoords="offset points", fontsize=9, color=INK, ha="right",
                arrowprops={"arrowstyle": "-", "color": MUTED, "lw": 0.8})
    ax.annotate(f"開局 {AE[0]:.0f}", (0, AE[0]), xytext=(4, 6), textcoords="offset points", fontsize=9, color=INK)
    ax.set_xlabel("比賽時間（分）"); ax.set_ylabel("半長軸 a（km）")
    ax.set_title("躲方得一路爬升、中途穿過追方的 a", color=INK, loc="left")
    ax.legend(loc="lower right", frameon=False)

    # (4) 相對運動（躲方 RSW）
    ax = fig.add_subplot(gs[1, 1])
    rel = np.array([rsw(r[3], r[4]) @ (r[1] - r[3]) for r in rows])
    near = D < 150
    ax.plot(rel[:, 1], rel[:, 0], color=GRID, lw=1)
    sc = ax.scatter(rel[near, 1], rel[near, 0], c=T[near] / 60, cmap="Oranges", s=6, vmin=0, vmax=T[-1] / 60)
    ax.add_patch(plt.Circle((0, 0), RCAP, color="#d03b3b", fill=False, ls="--", lw=1.2))
    ax.scatter([0], [0], color=C_E, s=50, zorder=3, edgecolor=SURF, linewidth=1.5)
    ax.annotate("躲方", (0, 0), xytext=(6, 6), textcoords="offset points", fontsize=9, color=INK)
    offs = [(14, -22), (-150, 26), (14, 20)]
    shown = 0
    for k in range(len(log["rounds"])):
        m = (T > k * W) & (T <= (k + 1) * W)
        if not m.any():
            continue
        j = int(np.argmin(np.where(m, D, np.inf)))
        if D[j] > 30:
            continue
        ax.scatter([rel[j, 1]], [rel[j, 0]], s=40, color=INK, zorder=4, edgecolor=SURF, linewidth=1.5)
        ax.annotate(f"R{k + 1} 最近 {D[j]:.2f} km（+{T[j] - k * W:.0f} s）", (rel[j, 1], rel[j, 0]),
                    xytext=offs[shown % 3], textcoords="offset points", fontsize=9, color=INK,
                    arrowprops={"arrowstyle": "-", "color": MUTED, "lw": 0.8})
        shown += 1
    ax.set_xlim(-80, 80); ax.set_ylim(-60, 60); ax.set_aspect("equal")
    ax.set_xlabel("沿軌 S km（躲方前方 +）"); ax.set_ylabel("徑向 R km（躲方上方 +）")
    ax.set_title("追方相對躲方（RSW 的 R–S 投影，W 出平面沒畫；只畫 150 km 內）", color=INK, loc="left")
    cb = fig.colorbar(sc, ax=ax, shrink=0.8, pad=0.02)
    cb.set_label("比賽時間（分）", color=MUTED); cb.outline.set_visible(False)

    res = "escape" if D.min() > RCAP else "capture"
    fig.suptitle(f"勢均力敵版彩排：我方{'躲方' if role == 'evader' else '追方'}、對手種子 {log['opp_seed']}  →  {res}，"
                 f"全場最近 {D.min():.3f} km", x=0.06, ha="left", fontsize=13, color=INK)
    fig.savefig(os.path.join(out, "trajectory.png"), dpi=130, bbox_inches="tight")
    print(f"取樣 {len(rows)} 點（{STEP:.0f} s）；全場最近 {D.min():.3f} km @ {T[np.argmin(D)]:.0f} s；結束 a_e = {AE[-1]:.3f} km")
    print(f"→ {out}/trajectory.csv、trajectory.png")


if __name__ == "__main__":
    main()
