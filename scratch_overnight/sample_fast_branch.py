"""官方範例題目的「快速攔截」分支：連續 Lambert 重新瞄準能不能追平官方參考解？

背景：官方參考解是 2 棒、總 2,241.4 m/s、抵達 3,211.7s，第一棒剛好頂到 1,500 m/s
上限。我們的工具在完整 T_max 下找到 1 棒 412 m/s 但要 6,121s——省 5.4 倍油卻慢 1.9 倍。
哪邊分數高取決於當天才公告的 k_t/C_t，所以**兩條分支都要能打**。

疑慮：這題兩軌道面夾角 93.84 度，快速攔截需要一發很大、而且方向很特殊（大量離面分量）
的第一棒。我們的種子家族是「窗口種子 + 近地點踢階梯」，階梯是沿**速度方向**爬升的，
結構上就不會產生大離面分量的種子。如果搜尋只靠 L-SHADE 亂找找不到，那是能力缺口。

這支腳本用一個**不同的**家族當獨立對照：貪婪式連續 Lambert 重新瞄準——沿 Lambert
需求方向燒滿上限，滑行 MIN_INTERVAL，位置變了再重算一次需求，直到需求 <= 上限收尾。
這跟階梯種子涵蓋的區域不一樣，而且天生會產生大離面分量。

跟 split_burn_feasibility.py 是同一套方法，那次用在 hyper_fast 上得到負面結果
（證明無解）；這次用在一個**已知有解**的題目上，所以能拿來檢驗方法本身。
"""

import json
import math
import os
import sys

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

CFG = json.load(open(os.path.join(REPO_ROOT, "configs", "official_sample.json")))
CAP = CFG["rules"]["MAX_DV_MPS"]
MIN_INT = CFG["rules"]["MIN_MANEUVER_INTERVAL_SEC"]
REF_DV, REF_T = 2241.427, 3211.737


def build(o):
    x = Orbit.from_classical(Earth, o["SMA"]*u.km, o["ECC"]*u.one, o["INC"]*u.deg,
                              o["RAAN"]*u.deg, o["AOP"]*u.deg, o["TA"]*u.deg)
    return (x.r.to(u.km).value.astype(np.float64),
            x.v.to(u.km/u.s).value.astype(np.float64))


A_r0, A_v0 = build(CFG["orbit_A"])
B_r0, B_v0 = build(CFG["orbit_B"])


def lambert_dv(r0, v0, r_t, tof):
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
    return best_vec, best * 1000.0


def try_split(t_start, t_arrive, max_burns=5):
    """從 t_start 開始貪婪拆棒，目標在 t_arrive 抵達 A 的位置。回傳合法方案或 None。"""
    r_c, v_c = propagate_dop853(B_r0, B_v0, float(t_start), 60.0, MU, 0, 0, 0, RE)
    r_a, _ = propagate_dop853(A_r0, A_v0, float(t_arrive), 60.0, MU, 0, 0, 0, RE)
    t_now = float(t_start)
    burns, total = [], 0.0
    for _ in range(max_burns):
        tof = t_arrive - t_now
        if tof < 60.0:
            return None
        vec, mag = lambert_dv(r_c, v_c, r_a, tof)
        if vec is None:
            return None
        if mag <= CAP:
            v_new = v_c + vec
            if not check_constraints(r_c, v_new, MU, MIN_PERI):
                return None
            burns.append((t_now, mag))
            return {"burns": burns + [], "total": total + mag,
                    "t_arrive": t_arrive, "n": len(burns)}
        u_hat = vec / fast_norm(vec)
        v_new = v_c + u_hat * (CAP / 1000.0)
        if not check_constraints(r_c, v_new, MU, MIN_PERI):
            return None
        burns.append((t_now, CAP))
        total += CAP
        r_c, v_c = propagate_dop853(r_c, v_new, MIN_INT, 60.0, MU, 0, 0, 0, RE)
        t_now += MIN_INT
    return None


if __name__ == "__main__":
    print("=" * 92)
    print("官方範例題目：快速攔截分支（連續 Lambert 重新瞄準）")
    print("=" * 92)
    print(f"對照 — 官方參考解：2 棒、{REF_DV:,.1f} m/s、抵達 {REF_T:,.1f}s")
    print(f"每棒上限 {CAP:,.0f} m/s、機動間隔下限 {MIN_INT:.0f}s\n")
    print(f"{'抵達時間上限(s)':>16}{'最省總 ΔV':>14}{'棒數':>7}{'起燒(s)':>10}"
          f"{'抵達(s)':>10}{'vs 參考解':>12}")
    print("-" * 92)

    for cap_t in (2000.0, 2500.0, 3000.0, REF_T, 3600.0, 4200.0, 5000.0, 6200.0):
        best = None
        for t_start in np.linspace(0.0, max(0.0, cap_t - 300.0), 120):
            for t_arrive in np.linspace(float(t_start) + 200.0, cap_t, 120):
                out = try_split(float(t_start), float(t_arrive))
                if out is None:
                    continue
                if best is None or out["total"] < best["total"]:
                    best = out
        if best is None:
            print(f"{cap_t:>16,.0f}{'找不到':>14}")
            continue
        ratio = REF_DV / best["total"]
        print(f"{cap_t:>16,.0f}{best['total']:>14,.1f}{best['n']:>7d}"
              f"{best['burns'][0][0]:>10,.0f}{best['t_arrive']:>10,.0f}{ratio:>11.2f}x",
              flush=True)

    print("-" * 92)
    print("解讀：這個家族找得到、而主線搜尋找不到 => 是種子涵蓋的缺口（可修）。")
    print("      兩邊都找不到 => 這個時間尺度本來就沒有便宜的解（不是 bug）。")
