"""攔截版二體 primer vector 診斷的回歸（C1，2026-09-22）。

斷言**性質**（邊界條件對、最優解 |p|≤1、次優解被抓到 |p|>1），不賭確切數字——STM 積分
換 scipy 版本尾數會飄，但性質必須守住。確定性（純幾何 + Lambert，不涉 DE/亂數）。

被 run_regression.py 自動發現。全過 exit 0，任一不過 exit 1。
"""
import os
import sys
import json
import math

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.optimizer import MissionOptimizer
from src.core_math import propagate_dop853, fast_norm
from poliastro.core.iod import izzo
from src.primer import intercept_primer_profile

_FAILED = []


def check(desc, ok):
    print(f"  {'✅' if ok else '❌'} {desc}")
    if not ok:
        _FAILED.append(desc)


def main():
    cfg = json.load(open(os.path.join("configs", "contest.json")))
    o = MissionOptimizer(cfg)
    mu, j2, j3, j4, re = o.MU, o.J2_VAL, o.J3_VAL, o.J4_VAL, o.RE_VAL

    def prop(r, v, t):
        return propagate_dop853(r, v, float(t), 60.0, mu, j2, j3, j4, re)

    print("\n── primer 診斷回歸 ──")

    # Case 1：單棒 Lambert 攔截——單發弧結構上無「該加中途棒」的餘地 → optimal-ish
    t_dep, tof = 300.0, 2500.0
    rB, vB = prop(o.B_r0, o.B_v0, t_dep)
    rA, _ = prop(o.A_r0, o.A_v0, t_dep + tof)
    v1, _ = izzo(mu, rB, rA, tof, M=0, prograde=True, lowpath=True, numiter=35, rtol=1e-8)
    r1 = intercept_primer_profile(rB, vB, [(t_dep, v1 - vB)], t_dep + tof, mu)
    check(f"單棒攔截 verdict=optimal-ish（max|p|={r1['max_peak']:.3f}≤1）",
          r1["verdict"] == "optimal-ish" and r1["max_peak"] <= 1.0 + 1e-2)
    check("單棒攔截 末端 primer≈0（攔截橫截條件：速度自由）",
          r1["arcs"][-1]["p_end_norm"] <= 1e-2)
    # 脈衝處 |p|=1（邊界建構）：第一段起點就是脈衝，取樣首點應 =1
    ts, pm = r1["arcs"][0]["samples"]
    check(f"單棒攔截 脈衝處 |p|≈1（={pm[0]:.3f}）", abs(pm[0] - 1.0) <= 1e-2)

    # Case 2：抬高+換面 → 一發大棒攔截。大棒前的弧應 |p|>1（該處插中途棒能省）→ add-node
    rb, vb = prop(o.B_r0, o.B_v0, 0.0)
    Vh = vb / fast_norm(vb)
    Nh = np.cross(rb, vb); Nh = Nh / fast_norm(Nh)
    k = (Vh - Nh); k = k / fast_norm(k) * o.MAX_DV_SOFT
    vb1 = vb + k
    sp = fast_norm(vb1) ** 2 / 2.0 - mu / fast_norm(rb)
    a_new = -mu / (2.0 * sp)
    tc = 0.75 * 2.0 * math.pi * math.sqrt(a_new ** 3 / mu)
    rm, vm = prop(rb, vb1, tc)
    Tarr = tc + o.Ta_sec * 0.5
    r_a, _ = prop(o.A_r0, o.A_v0, float(Tarr))
    v1b, _ = izzo(mu, rm, r_a, Tarr - tc, M=0, prograde=True, lowpath=True, numiter=35, rtol=1e-8)
    r2 = intercept_primer_profile(rb, vb, [(0.0, k), (tc, v1b - vm)], Tarr, mu)
    check(f"次優(大棒)解 verdict=add-node（max|p|={r2['max_peak']:.3f}>1）",
          r2["verdict"] == "add-node" and r2["max_peak"] > 1.0 + 1e-2)
    check("次優(大棒)解 峰值落在大棒前的 inter-impulse 弧",
          r2["arcs"][r2["worst_arc"]]["kind"] == "inter-impulse")
    check("次優(大棒)解 末端 primer≈0（攔截橫截條件）",
          r2["arcs"][-1]["p_end_norm"] <= 1e-2)

    print("\n── 收工 ──")
    if _FAILED:
        print(f"❌ {len(_FAILED)} 項未通過：{_FAILED}")
        sys.exit(1)
    print("✅ primer 診斷回歸全過")


if __name__ == "__main__":
    main()
