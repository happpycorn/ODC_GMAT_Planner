"""GLOBAL_ORACLE 第 3 項：換求解器、換參數化（2026-10-28）。

(a) 同一個適應度 `fast_fitness_evaluator`、同一組決策變數與邊界（`_generate_bounds`），
    換掉 L-SHADE：scipy `differential_evolution`（rand1bin、隨機初始族群）與 CMA-ES（`cma`，
    [0,1] 正規化、IPOP 重啟）。**不用管線的任何種子產生器**。每個 MAX_BURNS 案例都跑，
    預算「相當」= MAXITER×POPSIZE×2（REVS 集成跑兩趟）次評估，「大」= 10 倍。
(b) 獨立參數化：free-ECI（每棒 ECI Δv 向量 + 滑行秒數）多起點 SLSQP。起點是隨機挑的單棒
    Lambert 攔截（單棒網格裡 Δv ≤ 3 km/s 的格子均勻抽），前導棒等分、交給 joint NLP 在
    J2–J4 下用真實計分最佳化（`oracle_common.finalize_route`；NLP 引擎與拆棒器同一個
    `joint_nlp_split`，但起點跟 DE 無關、決策變數不經過球座標/coast_frac/Lambert 終端）。
所有結果都走 `finalize_route`（J2–J4 精修 + 拆棒），得最終合法分數。

用法：uv run --with cma python scripts/research/oracle_solvers.py <情境> [--seeds 3] [--random-starts 8]
"""
import argparse
import os
import sys
import time

import numpy as np
from scipy.optimize import differential_evolution

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oracle_common import (OUT, finalize_route, jdump, load_scenario, route_from_standard_x)  # noqa: E402


def run_de(f, lb, ub, budget, seed):
    dim = len(lb)
    pop = max(5, int(round(15 / max(1, dim / 5))))        # 族群 = pop×dim
    maxiter = max(10, budget // (pop * dim) - 1)
    t = time.time()
    r = differential_evolution(f, list(zip(lb, ub)), strategy="rand1bin", popsize=pop, maxiter=maxiter,
                               tol=0, atol=0, mutation=(0.5, 1.0), recombination=0.9, seed=seed,
                               polish=False, init="latinhypercube", updating="deferred", workers=1)
    return r.x, float(r.fun), int(r.nfev), time.time() - t


def run_cma(f, lb, ub, budget, seed):
    import cma
    lb = np.asarray(lb); ub = np.asarray(ub); span = ub - lb
    g = lambda z: f(lb + np.clip(z, 0, 1) * span)          # noqa: E731
    rng = np.random.default_rng(seed)
    best_x, best_f, nfev, t = None, np.inf, 0, time.time()
    popsize = None; restarts = 0
    while nfev < budget:
        opts = {"bounds": [0, 1], "seed": int(rng.integers(1, 2**31 - 1)), "verbose": -9,
                "maxfevals": budget - nfev, "tolfun": 1e-11, "tolx": 1e-12}
        if popsize:
            opts["popsize"] = popsize
        es = cma.CMAEvolutionStrategy(rng.random(len(lb)), 0.3, opts)
        while not es.stop():
            Z = es.ask(); F = [g(z) for z in Z]; es.tell(Z, F); nfev += len(Z)
            if nfev >= budget:
                break
        xb, fb = es.result.xbest, es.result.fbest
        if xb is not None and fb < best_f:
            best_f, best_x = float(fb), lb + np.clip(xb, 0, 1) * span
        popsize = 2 * (es.popsize if popsize is None else popsize)   # IPOP
        restarts += 1
    return best_x, best_f, nfev, time.time() - t


def main(name, seeds=3, random_starts=8, big_factor=10, finalize=True):
    cfg, opt = load_scenario(name)
    out = {"scenario": name, "burn_cases": list(opt.burns), "seeds": seeds}
    base_budget = int(cfg["optimization"]["MAXITER"]) * int(cfg["optimization"]["POPSIZE"]) * 2
    res = []
    for N in opt.burns:
        lb, ub = opt._generate_bounds(N)
        f = opt._fitness_wrapper(N)
        f(np.asarray(lb))                                   # 編譯
        for solver, fn in (("scipy_de", run_de), ("cma_es", run_cma)):
            for tag, budget in (("match", base_budget), ("big", base_budget * big_factor)):
                for s in range(seeds):
                    x, fv, nfev, sec = fn(f, lb, ub, budget, s)
                    res.append({"solver": solver, "budget": tag, "N": int(N), "seed": s, "score_presplit": -fv,
                                "nfev": nfev, "sec": round(sec, 1), "x": [float(v) for v in x]})
                    print(f"[{name}] {solver} {tag} N={N} s{s}: 拆前 {-fv:.4f}（{nfev} 次, {sec:.0f}s）", flush=True)
    out["search"] = res
    jdump(os.path.join(OUT, f"oracle_solvers_{name}.json"), out)

    fin = []
    if finalize:
        # 每個 solver×預算 取拆前分數最高的那顆種子（跨 N）做 J2–J4 精修 + 拆棒
        groups = {}
        for r in res:
            k = (r["solver"], r["budget"])
            if k not in groups or r["score_presplit"] > groups[k]["score_presplit"]:
                groups[k] = r
        for (solver, tag), r in sorted(groups.items()):
            t0, dvs, coasts = route_from_standard_x(opt, r["x"], r["N"])
            fr = finalize_route(opt, cfg, t0, dvs, coasts, tag=f"{solver}/{tag}")
            fr.update({"solver": solver, "budget": tag, "N_presplit": r["N"], "seed": r["seed"],
                       "score_presplit": r["score_presplit"]})
            fin.append(fr)
            print(f"[{name}] {solver}/{tag} → " + (f"合法 {fr['score']:.4f}（{fr['num_burns']} 棒, "
                  f"{fr['total_dv_mps']:.1f} m/s, T={fr['T_team']:.0f}）" if fr.get("legal") else
                  f"失敗：{fr.get('reason')}"), flush=True)
        out["finalized"] = fin
        jdump(os.path.join(OUT, f"oracle_solvers_{name}.json"), out)

    # (b) free-ECI 多起點：隨機單棒攔截起點
    from oracle_twoburn import ephem, porkchop1, BIG
    T, mc = opt.T_max, opt.MIN_COAST_TIME
    tt = np.arange(0.0, T + 1e-9, max(mc, T / 200.0))
    RB, VB = ephem(opt, tt, "B"); RA, _ = ephem(opt, tt, "A")
    DV1, MR1 = porkchop1(RB, VB, RA, tt, mc, opt.MU, opt.LAMBERT_MAX_REVS, opt.MIN_PERIAPSIS)
    cells = np.argwhere(DV1 <= 3.0)
    rng = np.random.default_rng(12345)
    free = []
    if len(cells):
        pick = cells[rng.choice(len(cells), size=min(random_starts, len(cells)), replace=False)]
        from oracle_twoburn import lam_best
        for q, (i, j) in enumerate(pick):
            d, m, vreq = lam_best(RB[i], VB[i], RA[j], tt[j] - tt[i], opt.MU, opt.LAMBERT_MAX_REVS,
                                  opt.MIN_PERIAPSIS)
            dv = vreq - VB[i]
            # 這發當「前導棒」等分（presplit_leading），終端只留一點滑行讓拆棒器重新瞄準
            tf = max(mc, min(0.25 * (tt[j] - tt[i]), 2 * mc))
            fr = finalize_route(opt, cfg, tt[i], [dv, np.zeros(3)], [tt[j] - tt[i] - tf, tf], tag=f"freeECI#{q}")
            fr.update({"start_t1": float(tt[i]), "start_t3": float(tt[j]), "start_dv_mps": float(d * 1000),
                       "start_M": int(m)})
            free.append(fr)
            print(f"[{name}] freeECI#{q} 起點 t1={tt[i]:.0f} t3={tt[j]:.0f} {d*1000:.0f} m/s → "
                  + (f"合法 {fr['score']:.4f}（{fr['num_burns']} 棒, {fr['total_dv_mps']:.1f} m/s, "
                     f"T={fr['T_team']:.0f}）" if fr.get("legal") else f"失敗：{fr.get('reason')}"), flush=True)
    else:
        print(f"[{name}] 單棒網格沒有 Δv ≤ 3 km/s 的格子，free-ECI 隨機起點跳過", flush=True)
    out["free_eci"] = free
    out["free_eci_cells_le3kms"] = int(len(cells))
    jdump(os.path.join(OUT, f"oracle_solvers_{name}.json"), out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--random-starts", type=int, default=8)
    ap.add_argument("--big-factor", type=int, default=10)
    ap.add_argument("--no-finalize", action="store_true")
    a = ap.parse_args()
    main(a.scenario, seeds=a.seeds, random_starts=a.random_starts, big_factor=a.big_factor,
         finalize=not a.no_finalize)
