"""GLOBAL_ORACLE 第 2 項：理論分數天花板（從上面壓，2026-10-28）。

**證明**（點質量重力；J2–J4 位能修正在這些軌道 <0.1%，速度界另乘 1.01 保守）：
  * Δv 下界 = `MissionOptimizer.energy_floor_dv()`：B 的半徑範圍要碰到 A 的半徑範圍的最少衝量
    （封閉解）。任何攔截都要 B 到達 A 的地心距離，所以 ΔV_team ≥ 這個值。
  * T 下界（速度界）：令 u = sqrt(2(ε_B + μ/r_min))，ε_B 是 B 的初始比能量、r_min = MIN_PERIAPSIS
    （攔截前弧段不得低於它）。一發 Δv 讓速度最多增加 Δv，能量增加 ≤ u·Δv + Δv²/2，所以
    「r ≥ r_min 處可能的最大速率」u 每發最多加 Δv：任何時刻 |v_B| ≤ U = u + ΔV_max（ΔV_max = 3 km/s 總上限）。
    因此 |r_B(t) − r_B(0)| ≤ U·t，攔截（Δr ≤ 5 km）需要 |r_A(T) − r_B(0)| − 5 ≤ U·T。
    T_lb = 滿足這式的最早 T（用 A 的 J2–J4 星曆以 1 s 解析度掃）。
  * 天花板（證明）= calculate_score(Δr=5, T_lb, ΔV_lb)。兩個下界各自成立、但不一定能同時達到，所以很寬。
**估計**（不是證明）：兩棒 oracle 的 Δv–T Pareto 前緣（二體弧、忽略單棒上限與拆棒代價、Δr 取 5 km 內）
  代入計分取最大。拆棒幾乎不加 Δv，但兩棒以上的結構、J2–J4 差異與網格解析度都沒涵蓋。

用法：uv run python scripts/research/oracle_ceiling.py <情境>（估計部分要先跑 oracle_twoburn.py）
"""
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oracle_common import OUT, jdump, load_scenario   # noqa: E402
from src.scorer import calculate_score                # noqa: E402


def main(name):
    cfg, opt = load_scenario(name)
    mu = opt.MU
    dv_lb = opt.energy_floor_dv()                      # km/s
    r0 = np.asarray(opt.B_r0); v0 = np.asarray(opt.B_v0)
    eps = 0.5 * float(v0 @ v0) - mu / float(np.linalg.norm(r0))
    u = math.sqrt(2.0 * (eps + mu / opt.MIN_PERIAPSIS))
    dvmax = (opt.MAX_TOTAL_DV_MPS or 3000.0) / 1000.0
    U = 1.01 * (u + dvmax)
    T_lb = None
    tgrid = np.arange(0.0, opt.T_max + 1.0, 1.0)
    for t in tgrid:
        rA, _ = opt.state_A(float(t))
        if float(np.linalg.norm(np.asarray(rA) - r0)) - 5.0 <= U * t:
            T_lb = float(t)
            break
    sc = lambda T, dv: calculate_score(5.0, T, dv * 1000.0, 0, opt.k_t, opt.C_t, opt.k_v, opt.C_v)  # noqa: E731
    out = {"scenario": name,
           "proof": {"dv_lb_mps": dv_lb * 1000.0, "T_lb_sec": T_lb, "speed_bound_kms": U,
                     "ceiling": None if T_lb is None else sc(T_lb, dv_lb),
                     "time_term_at_T_lb": None if T_lb is None else 25.0 / (1 + math.exp(min(opt.k_t * (T_lb - opt.C_t), 700))),
                     "fuel_term_at_dv_lb": 25.0 / (1 + math.exp(min(opt.k_v * (dv_lb * 1000 - opt.C_v), 700)))}}
    p = os.path.join(OUT, f"oracle_twoburn_{name}.json")
    if os.path.exists(p):
        o = json.load(open(p))
        front = [(T, dv / 1000.0) for T, dv in o.get("two_pareto", []) + o.get("single_pareto", [])
                 if dv <= dvmax * 1000.0]
        if front:
            best = max(front, key=lambda z: sc(z[0], z[1]))
            out["estimate"] = {"ceiling": sc(best[0], best[1]), "T": best[0], "dv_mps": best[1] * 1000.0,
                               "source": "兩棒 oracle Pareto 前緣（二體、忽略單棒上限與拆棒、Δr≤5 km）"}
    jdump(os.path.join(OUT, f"oracle_ceiling_{name}.json"), out)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
