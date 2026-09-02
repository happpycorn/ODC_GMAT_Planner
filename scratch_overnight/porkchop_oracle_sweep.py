"""HAP-32 / CP6：把 porkchop 窮舉變成「持續對拍的 oracle」，對隨機幾何掃描。

porkchop_grid.py 已經有完備的單棒窮舉核心（`build_ephemeris` + `porkchop`）——單棒子空間
的決策只有 (出發時刻, 飛行時間) 兩維，網格一格不漏就是**全域真值**（規則只要求攔截、
到達端沒有脈衝）。這支把它包成可重用 oracle，對一批隨機 LEO 幾何做「窮舉 vs 最佳化器」對拍。

porkchop 不等式（本檢查的核心）：
    最佳化器的單棒分數  ≥  窮舉 oracle 的單棒最佳分數  −  ε
最佳化器**可以更好**（它會在命中容許球內瞄最省油的點、還做 J2 精修），但**不該明顯更差**
——明顯落後代表 L-SHADE 沒找到「窮舉都找得到」的單棒解，那就是搜尋失敗，正是要抓的。

ε 吸收兩件無害的差：oracle 用二體 Lambert、最佳化器用 J2 重播（模型差，通常 < 1 分），
加上搜尋的隨機雜訊。只有超過 ε 的落後才旗標。只在「oracle 找得到合法單棒解」的幾何上比
（那才是最佳化器該找到的）。

隨機幾何鎖在 LEO 圓軌道附近（A SMA ≤ 9000、低離心率）——對齊初賽威脅模型（A 是圓軌道），
也讓每張網格的 T_max 有界、跑得快。

跑法（一次一批，附加到 JSON）：
  uv run python scratch_overnight/porkchop_oracle_sweep.py --n 40 --seed 20260903
"""

import argparse
import json
import math
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import warnings
warnings.filterwarnings("ignore")
import numpy as np

from src.optimizer import MissionOptimizer
from porkchop_grid import build_ephemeris, porkchop

RESULTS = os.path.join(REPO, "scratch_overnight", "porkchop_oracle_results.json")
EPS = 2.0                      # 分：落後超過這個才算搜尋失敗（吸收二體/J2 模型差 + 雜訊）
GRID_H = 60.0                  # 網格步長（秒）
MAX_REVS = 4


def porkchop_oracle(opt, h=GRID_H, max_revs=MAX_REVS):
    """單棒子空間的窮舉真值：回傳全域最高分（假設精確命中 → 距離項 50）與是否存在合法單棒解。"""
    times = np.arange(0.0, opt.T_max + 1e-9, h)
    n = len(times)
    RB, VB = build_ephemeris(opt.B_r0, opt.B_v0, times, 60.0, opt.MU,
                             opt.J2_VAL, opt.J3_VAL, opt.J4_VAL, opt.RE_VAL)
    RA, VA = build_ephemeris(opt.A_r0, opt.A_v0, times, 60.0, opt.MU,
                             opt.J2_VAL, opt.J3_VAL, opt.J4_VAL, opt.RE_VAL)
    min_tof_steps = max(1, int(math.ceil(opt.MIN_COAST_TIME / h)))
    DV, MREV, NSOL, TANG = porkchop(RB, VB, RA, h, max_revs, min_tof_steps)
    valid = np.isfinite(DV)
    if not valid.any():
        return {"oracle_score": None, "has_legal_single": False, "n_nodes": n}
    ARR = times[None, :] * np.ones((n, 1))
    S = np.where(valid,
                 50.0
                 + 25.0 / (1.0 + np.exp(np.clip(opt.k_t * (ARR - opt.C_t), -700, 700)))
                 + 25.0 / (1.0 + np.exp(np.clip(opt.k_v * (DV * 1000.0 - opt.C_v), -700, 700)))
                 - 10.0 * (DV > opt.MAX_DV),
                 -np.inf)
    k = np.unravel_index(np.nanargmax(S), S.shape)
    legal = valid & (DV <= opt.MAX_DV)
    return {"oracle_score": round(float(S[k]), 3),
            "oracle_dv_mps": round(float(DV[k] * 1000.0), 1),
            "oracle_arr_s": round(float(times[k[1]]), 1),
            "has_legal_single": bool(legal.any()),
            "n_nodes": n}


def random_geometry(rng):
    """隨機 LEO 幾何（A 圓軌道附近，對齊初賽威脅模型）。"""
    def orb(sma_lo, sma_hi, ecc_hi):
        return {"SMA": round(rng.uniform(sma_lo, sma_hi), 1),
                "ECC": round(rng.uniform(0.0, ecc_hi), 4),
                "INC": round(rng.uniform(0.0, 90.0), 2),
                "RAAN": round(rng.uniform(0.0, 360.0), 2),
                "AOP": round(rng.uniform(0.0, 360.0), 2),
                "TA": round(rng.uniform(0.0, 360.0), 2)}
    return orb(7200.0, 9000.0, 0.05), orb(6600.0, 7200.0, 0.02)   # A 高一點、B 低一點


def build_config(A, B, seed):
    return {
        "orbit_A": A, "orbit_B": B,
        "rules": {"MAX_DV_MPS": 1500.0, "MIN_MANEUVER_INTERVAL_SEC": 100.0,
                  "T_MAX_PERIOD_MULTIPLE": 4.0,
                  "k_t": 0.0005, "C_t": 11000.0, "k_v": 0.002, "C_v": 1500.0},
        "strategy": {"GRAVITY_DEGREE": 2, "MISS_TOLERANCE_KM": 5.0, "LAMBERT_MAX_REVS": MAX_REVS},
        "optimization": {"MAX_BURNS": [1], "MAXITER": 120, "POPSIZE": 15,
                         "NUM_THREADS": -1, "MAX_EARLY_STOP": 120, "TOL": 0.01, "SEED": seed},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=20260903)
    ap.add_argument("--out", default=RESULTS)
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    print(f"=== HAP-32 porkchop oracle 對拍：{args.n} 組隨機 LEO 幾何（seed {args.seed}）===")
    print(f"    不等式：opt_score ≥ oracle_score − {EPS}（只在 oracle 有合法單棒解時比）\n")

    records = []
    violations = []
    t_start = time.time()
    for idx in range(args.n):
        A, B = random_geometry(rng)
        cfg = build_config(A, B, seed=args.seed + idx)
        try:
            opt = MissionOptimizer(cfg)
            orc = porkchop_oracle(opt)
            _b, _t, mi = opt.run_study()
            opt_score = None if mi is None else round(float(mi["score"]), 3)
        except Exception as exc:
            rec = {"idx": idx, "A": A, "B": B, "error": f"{type(exc).__name__}: {exc}"}
            records.append(rec)
            print(f"  [{idx:2d}] ❌ 例外 {rec['error']}")
            continue

        gap = None
        flag = False
        if orc["oracle_score"] is not None and opt_score is not None and orc["has_legal_single"]:
            gap = round(orc["oracle_score"] - opt_score, 3)
            flag = gap > EPS
        rec = {"idx": idx, "A": A, "B": B, "opt_score": opt_score,
               "oracle_score": orc["oracle_score"], "oracle_dv_mps": orc.get("oracle_dv_mps"),
               "has_legal_single": orc["has_legal_single"], "gap": gap, "violation": flag}
        records.append(rec)
        if flag:
            violations.append(rec)
        tag = "❌ 落後" if flag else ("·" if orc["has_legal_single"] else "◽無合法單棒")
        print(f"  [{idx:2d}] opt {opt_score}  oracle {orc['oracle_score']}  "
              f"gap {gap}  {tag}")

    elapsed = time.time() - t_start
    with open(args.out, "w") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    compared = [r for r in records if r.get("gap") is not None]
    gaps = [r["gap"] for r in compared]
    print(f"\n{'─'*60}")
    print(f"  比對 {len(compared)}/{args.n} 組（其餘無合法單棒解或例外）；耗時 {elapsed:.0f}s")
    if gaps:
        print(f"  gap（oracle−opt）：min {min(gaps):+.2f}  median {np.median(gaps):+.2f}  "
              f"max {max(gaps):+.2f}  （負=最佳化器更好）")
    print(f"  ❌ 違反不等式（落後 > {EPS} 分）：{len(violations)} 組")
    for v in violations:
        print(f"     idx {v['idx']}  gap {v['gap']}  opt {v['opt_score']} vs oracle {v['oracle_score']}")
    print(f"  已寫入 {os.path.basename(args.out)}")


if __name__ == "__main__":
    main()
