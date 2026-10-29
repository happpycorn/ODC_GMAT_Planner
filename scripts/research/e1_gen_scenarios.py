"""E1（2026-10-29）：隨機產生排位賽型題目（B = LEO、A = 雙曲線飛越），量「中段大燒前導棒」家族多常出現。

範圍貼近排位賽題庫（hyper_far、hyperbolic_smoke、ranking_round）：
  B：SMA U(6700, 7400) km、ECC U(0, 0.01)、INC U(0, 60)°、RAAN/AOP/TA U(0, 360)°
  A：近地點 rp U(8000, 30000) km、ECC U(1.1, 1.6)、INC U(0, 60)°、RAAN/AOP U(0, 360)°；
     起點 TA = −f·ν∞（ν∞ = acos(−1/e) 漸近線角），f U(0.82, 0.92)（兩個錨點 f ≈ 0.89）
  T_max = 2 × 到近地點的時間（題庫同一個規則）；只收 20,000 ≤ T_max ≤ 200,000 s
  計分：C_t = U(0.55, 0.70)·T_max、k_t = U(3, 4)/T_max（錨點 C_t/T_max ≈ 0.62、k_t·T_max 3.25–4）；
        C_v U(1500, 2500) m/s、k_v U(0.0015, 0.0025)
  能量下限（點質量 Hohmann）> 2,500 m/s 的丟掉重抽。其他欄位（拆棒設定、MAX_BURNS [1,2] 等）照抄
  configs/shared/ranking_round.json，也就是比賽當天設定。

用法：python scripts/research/e1_gen_scenarios.py [--seed 20261029] [--n 8]
輸出：configs/research/e1/e1_r<k>.json（每題一檔）與 sweeps/e1_random.json（管線 sweep 規格）。
"""
import argparse
import copy
import json
import math
import os

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MU, RE = 398600.4418, 6378.137


def t_to_periapsis(sma, ecc, ta_deg):
    nu = math.radians(ta_deg)
    F = 2.0 * math.atanh(math.sqrt((ecc - 1) / (ecc + 1)) * math.tan(nu / 2))
    M = ecc * math.sinh(F) - F
    return -M / math.sqrt(MU / (-sma) ** 3)


def energy_floor_mps(sma_b, ecc_b, rp_a):
    rp_b, ra_b = sma_b * (1 - ecc_b), sma_b * (1 + ecc_b)
    if ra_b >= rp_a:
        return 0.0
    v_now = math.sqrt(MU * (2 / rp_b - 1 / sma_b))
    v_need = math.sqrt(MU * (2 / rp_b - 2 / (rp_b + rp_a)))
    return (v_need - v_now) * 1000.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20261029)
    ap.add_argument("--n", type=int, default=8)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    with open(os.path.join(REPO, "configs/shared/ranking_round.json"), encoding="utf-8") as f:
        tmpl = json.load(f)
    for k in [k for k in tmpl if k.startswith("_comment")]:
        del tmpl[k]
    os.makedirs(os.path.join(REPO, "configs/research/e1"), exist_ok=True)
    names, tries = [], 0
    while len(names) < a.n:
        tries += 1
        u = rng.uniform
        B = {"SMA": round(u(6700, 7400), 1), "ECC": round(u(0, 0.01), 5), "INC": round(u(0, 60), 2),
             "RAAN": round(u(0, 360), 2), "AOP": round(u(0, 360), 2), "TA": round(u(0, 360), 2)}
        rp, e = u(8000, 30000), u(1.1, 1.6)
        nu_inf = math.degrees(math.acos(-1 / e))
        ta = -u(0.82, 0.92) * nu_inf
        A = {"SMA": round(rp / (1 - e), 1), "ECC": round(e, 4), "INC": round(u(0, 60), 2),
             "RAAN": round(u(0, 360), 2), "AOP": round(u(0, 360), 2), "TA": round(ta % 360, 3)}
        T = 2 * t_to_periapsis(A["SMA"], A["ECC"], A["TA"] - 360)
        ct, kt, cv, kv = u(0.55, 0.70), u(3, 4), u(1500, 2500), u(0.0015, 0.0025)
        floor = energy_floor_mps(B["SMA"], B["ECC"], A["SMA"] * (1 - A["ECC"]))
        if not (20000 <= T <= 200000) or floor > 2500:
            continue
        name = f"e1_r{len(names) + 1}"
        cfg = copy.deepcopy(tmpl)
        cfg["_comment_e1"] = (f"E1 隨機題（e1_gen_scenarios.py --seed {a.seed}，第 {tries} 抽）。"
                              f"rp_A={rp:.0f} km、能量下限 {floor:.0f} m/s、T_max = 2×到近地點時間。佔位題，不是官方題目。")
        cfg["orbit_A"], cfg["orbit_B"] = A, B
        cfg["rules"].update({"T_MAX_SEC": round(T, 0), "k_t": float(f"{kt / T:.3g}"), "C_t": round(ct * T, -2),
                             "k_v": round(kv, 5), "C_v": round(cv, -1)})
        with open(os.path.join(REPO, f"configs/research/e1/{name}.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        names.append(name)
        print(f"{name}: rp_A={rp:.0f} e={e:.3f} inc_A={A['INC']} inc_B={B['INC']} T_max={T:.0f} floor={floor:.0f}")
    with open(os.path.join(REPO, "sweeps/global_oracle_contest.json"), encoding="utf-8") as f:
        base = json.load(f)["base"]
    spec = {"name": "e1_random",
            "_說明": f"E1 隨機題（e1_gen_scenarios.py --seed {a.seed} --n {a.n}）× 比賽當天設定（同 global_oracle_contest 的 base）、種子 0–2、--slots 3。",
            "scenarios": [{"name": n, "config": f"configs/research/e1/{n}.json"} for n in names],
            "seeds": [0, 1, 2], "base": base}
    with open(os.path.join(REPO, "sweeps/e1_random.json"), "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)
    print(f"{tries} 抽收 {len(names)} 題")


if __name__ == "__main__":
    main()
