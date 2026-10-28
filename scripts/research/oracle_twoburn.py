"""GLOBAL_ORACLE 第 1 項：兩棒窮舉 oracle（從下面夾，2026-10-28）。

跟管線的 L-SHADE 無關的獨立搜尋：
  * 單棒子空間（第一棒時刻 t1 × 攔截時刻 t3）：網格窮舉，每格掃 Lambert 全分支
    （圈數 0..LAMBERT_MAX_REVS × 順／逆向 × 高／低路徑），取 Δv 最小。
  * 兩棒子空間（t1 × 中途棒 t2 × 攔截 t3）：時刻三維網格窮舉；每個三元組內第一棒 Δv 向量
    （3 維連續）用 Nelder–Mead 求最小總 Δv，兩個起點：dv1=0（= t2 單棒）與 dv1 = 從 t1 直接
    Lambert 打 A(t3)（= t1 單棒），所以兩棒結果不會比兩個單棒端點差。
  * **忽略 250 m/s 上限**（拆棒幾乎不加 Δv），只保留攔截前不撞地（近地點檢查）。
  * B(t1)、A(t3) 用情境的 J2–J4 星曆（跟管線同一套），兩段弧（t1→t2 滑行、t2→t3 Lambert）用二體。
  * 粗網格找區域 → 最好的幾個三元組周圍加密 → 依「拆前估分」取前 K 名（時刻相近的去重），
    交給 oracle_common.finalize_route 做 J2–J4 精修 + 拆棒，得最終合法分數。

用法：
  uv run python scripts/research/oracle_twoburn.py <情境> [--h 秒] [--K 10] [--no-finalize]
"""
import argparse
import math
import os
import sys
import time

import numpy as np
from numba import njit, prange

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oracle_common import (OUT, finalize_route, jdump, load_scenario)  # noqa: E402
from porkchop_grid import build_ephemeris                                # noqa: E402
from src.core_math import izzo_max_revs, lambert_izzo, check_constraints, reaches_perigee  # noqa: E402
from poliastro.core.propagation import vallado                          # noqa: E402

BIG = 1.0e9


@njit(cache=True)
def kepler(r0, v0, dt, mu):
    try:
        f, g, fd, gd = vallado(mu, r0, v0, dt, 350)
    except Exception:
        return r0 * np.nan, v0 * np.nan
    return f * r0 + g * v0, fd * r0 + gd * v0


@njit(cache=True)
def lam_best(r1, v1, r2, tof, mu, max_revs, rmin):
    """所有 Lambert 分支裡 Δv 最小的那個；轉移弧會撞地的分支跳過。回傳 (dv, M, v_req)。"""
    best = BIG
    bm = -1
    bv = np.zeros(3)
    mpro = izzo_max_revs(mu, r1, r2, tof, True, 35, 1e-8)
    mret = izzo_max_revs(mu, r1, r2, tof, False, 35, 1e-8)
    for m in range(0, max_revs + 1):
        for lp in range(2):
            if m == 0 and lp == 1:
                continue
            for pg in range(2):
                if m > (mpro if pg == 0 else mret):
                    continue
                try:
                    vr, _ = lambert_izzo(mu, r1, r2, tof, m, pg == 0, lp == 0)
                except Exception:
                    continue
                d = math.sqrt((vr[0] - v1[0])**2 + (vr[1] - v1[1])**2 + (vr[2] - v1[2])**2)
                if d < best:
                    if reaches_perigee(r1, vr, mu, tof) and not check_constraints(r1, vr, mu, rmin):
                        continue
                    best = d
                    bm = m
                    bv = vr
    return best, bm, bv


@njit(cache=True)
def two_cost(dv1, r1, v1, tc, r3, tf, mu, max_revs, rmin):
    """第一棒 dv1 → 滑行 tc → 終端 Lambert 打 r3（飛行 tf）的總 Δv。撞地回 BIG。"""
    v1n = v1 + dv1
    if reaches_perigee(r1, v1n, mu, tc) and not check_constraints(r1, v1n, mu, rmin):
        return BIG, -1
    r2, v2 = kepler(r1, v1n, tc, mu)
    if not (math.isfinite(r2[0]) and math.isfinite(v2[0])):
        return BIG, -1
    d2, m, _ = lam_best(r2, v2, r3, tf, mu, max_revs, rmin)
    return math.sqrt(dv1[0]**2 + dv1[1]**2 + dv1[2]**2) + d2, m


@njit(cache=True)
def nelder_mead(x0, step, r1, v1, tc, r3, tf, mu, max_revs, rmin, maxev):
    n = 3
    S = np.zeros((n + 1, n))
    F = np.zeros(n + 1)
    for i in range(n + 1):
        S[i] = x0
        if i > 0:
            S[i, i - 1] += step
        F[i] = two_cost(S[i], r1, v1, tc, r3, tf, mu, max_revs, rmin)[0]
    ev = n + 1
    while ev < maxev:
        o = np.argsort(F)
        S = S[o]
        F = F[o]
        if F[n] - F[0] < 1e-7 and ev > 40:
            break
        c = (S[0] + S[1] + S[2]) / 3.0
        xr = c + (c - S[n]); fr = two_cost(xr, r1, v1, tc, r3, tf, mu, max_revs, rmin)[0]; ev += 1
        if fr < F[0]:
            xe = c + 2.0 * (c - S[n]); fe = two_cost(xe, r1, v1, tc, r3, tf, mu, max_revs, rmin)[0]; ev += 1
            if fe < fr:
                S[n] = xe; F[n] = fe
            else:
                S[n] = xr; F[n] = fr
        elif fr < F[n - 1]:
            S[n] = xr; F[n] = fr
        else:
            xc = c + 0.5 * (S[n] - c); fc = two_cost(xc, r1, v1, tc, r3, tf, mu, max_revs, rmin)[0]; ev += 1
            if fc < F[n]:
                S[n] = xc; F[n] = fc
            else:
                for i in range(1, n + 1):
                    S[i] = S[0] + 0.5 * (S[i] - S[0])
                    F[i] = two_cost(S[i], r1, v1, tc, r3, tf, mu, max_revs, rmin)[0]; ev += 1
    o = np.argmin(F)
    return S[o], F[o]


@njit(cache=True, parallel=True)
def porkchop1(RB, VB, RA, times, mc, mu, max_revs, rmin):
    n = times.shape[0]
    DV = np.full((n, n), BIG)
    MR = np.full((n, n), -1, dtype=np.int8)
    for i in prange(n):
        for j in range(i + 1, n):
            tof = times[j] - times[i]
            if tof < mc:
                continue
            d, m, _ = lam_best(RB[i], VB[i], RA[j], tof, mu, max_revs, rmin)
            DV[i, j] = d
            MR[i, j] = m
    return DV, MR


@njit(cache=True, parallel=True)
def twoburn(RB, VB, RA, t1s, t2s, t3s, mc, mu, max_revs, rmin, maxev):
    """三元組 (t1,t2,t3) 網格；回傳每格最小總 Δv、dv1 向量、終端圈數。"""
    n1, n2, n3 = t1s.shape[0], t2s.shape[0], t3s.shape[0]
    DV = np.full((n1, n2, n3), BIG)
    D1 = np.zeros((n1, n2, n3, 3))
    MR = np.full((n1, n2, n3), -1, dtype=np.int8)
    for i in prange(n1):
        r1 = RB[i]; v1 = VB[i]
        for k in range(n3):
            tf_all = t3s[k] - t1s[i]
            if tf_all < 2 * mc:
                continue
            # 起點 B：t1 直接 Lambert 打 A(t3) 的那一發
            dA, _, vA = lam_best(r1, v1, RA[k], tf_all, mu, max_revs, rmin)
            for j in range(n2):
                tc = t2s[j] - t1s[i]
                tf = t3s[k] - t2s[j]
                if tc < mc or tf < mc:
                    continue
                bestf = BIG; bestx = np.zeros(3)
                x0 = np.zeros(3)
                xs, fs = nelder_mead(x0, 0.05, r1, v1, tc, RA[k], tf, mu, max_revs, rmin, maxev)
                if fs < bestf:
                    bestf = fs; bestx = xs
                if dA < BIG:
                    x0 = vA - v1
                    xs, fs = nelder_mead(x0, 0.05, r1, v1, tc, RA[k], tf, mu, max_revs, rmin, maxev)
                    if fs < bestf:
                        bestf = fs; bestx = xs
                DV[i, j, k] = bestf
                D1[i, j, k] = bestx
                MR[i, j, k] = two_cost(bestx, r1, v1, tc, RA[k], tf, mu, max_revs, rmin)[1]
    return DV, D1, MR


def est_score(opt, T, dv_kms):
    from src.scorer import calculate_score
    return calculate_score(min_distance_km=0.0, total_time_sec=float(T), total_dv_mps=float(dv_kms) * 1000.0,
                           penalty_count=0, k_t=opt.k_t, C_t=opt.C_t, k_v=opt.k_v, C_v=opt.C_v)


def ephem(opt, times, which):
    r0, v0 = (opt.B_r0, opt.B_v0) if which == "B" else (opt.A_r0, opt.A_v0)
    eph = None if opt.ephem is None else (opt.ephem[0], opt.ephem[2] if which == "B" else opt.ephem[1])
    return build_ephemeris(r0, v0, times, 60.0, opt.MU, opt.J2_VAL, opt.J3_VAL, opt.J4_VAL,
                           opt.RE_VAL, ephem=eph)


def run(name, h=None, K=10, finalize=True, maxev=160, refine_top=6, fine_div=5):
    cfg, opt = load_scenario(name)
    T, mc, mu, R = opt.T_max, opt.MIN_COAST_TIME, opt.MU, opt.LAMBERT_MAX_REVS
    rmin = opt.MIN_PERIAPSIS
    if h is None:
        h = max(mc, T / 80.0)
    out = {"scenario": name, "T_max": T, "max_revs": R, "energy_floor_mps": opt.energy_floor_dv() * 1000.0,
           "h_coarse": h, "maxev": maxev}
    t_all = time.time()

    # --- 單棒：細網格窮舉（h1 = h/4）
    h1 = max(mc / 2, h / 4.0)
    tt = np.arange(0.0, T + 1e-9, h1)
    RB, VB = ephem(opt, tt, "B"); RA, _ = ephem(opt, tt, "A")
    t0 = time.time()
    DV1, MR1 = porkchop1(RB, VB, RA, tt, mc, mu, R, rmin)
    S1 = np.full(DV1.shape, -np.inf)
    ok = DV1 < BIG
    ii, jj = np.nonzero(ok)
    for a, b in zip(ii, jj):
        S1[a, b] = est_score(opt, tt[b], DV1[a, b])
    a, b = np.unravel_index(np.argmax(S1), S1.shape)
    c, d = np.unravel_index(np.argmin(np.where(ok, DV1, BIG)), DV1.shape)
    out["single"] = {"h": h1, "cells": int(ok.sum()), "sec": round(time.time() - t0, 1),
                     "best_score": {"t1": tt[a], "t3": tt[b], "dv_mps": DV1[a, b] * 1000, "M": int(MR1[a, b]),
                                    "est_score": S1[a, b]},
                     "min_dv": {"t1": tt[c], "t3": tt[d], "dv_mps": DV1[c, d] * 1000, "M": int(MR1[c, d]),
                                "est_score": S1[c, d]}}
    # 單棒 Pareto（每個攔截時刻的最小 Δv）供天花板估計
    out["single_pareto"] = [[float(tt[j]), float(np.min(DV1[:, j]) * 1000)] for j in range(len(tt))
                            if np.min(DV1[:, j]) < BIG]
    print(f"[{name}] 單棒 h={h1:.0f}s：最佳估分 {S1[a, b]:.4f}（{DV1[a, b]*1000:.1f} m/s, T={tt[b]:.0f}）"
          f"；最省 {DV1[c, d]*1000:.1f} m/s（{time.time()-t0:.1f}s）", flush=True)

    # --- 兩棒：粗網格
    tg = np.arange(0.0, T + 1e-9, h)
    RBg, VBg = ephem(opt, tg, "B"); RAg, _ = ephem(opt, tg, "A")
    t0 = time.time()
    DV2, D12, MR2 = twoburn(RBg, VBg, RAg, tg, tg, tg, mc, mu, R, rmin, maxev)
    print(f"[{name}] 兩棒粗網格 h={h:.0f}s（{len(tg)}³）：{time.time()-t0:.1f}s", flush=True)
    cands = []

    def collect(t1s, t2s, t3s, DV, D1, MR):
        idx = np.argwhere(DV < BIG)
        for (i, j, k) in idx:
            cands.append((est_score(opt, t3s[k], DV[i, j, k]), float(t1s[i]), float(t2s[j]), float(t3s[k]),
                          float(DV[i, j, k]), D1[i, j, k].copy(), int(MR[i, j, k])))
    collect(tg, tg, tg, DV2, D12, MR2)
    out["coarse_sec"] = round(time.time() - t0, 1)

    # --- 加密：粗網格前 refine_top 名（去重）周圍 ±h、步長 h/fine_div
    cands.sort(key=lambda c: -c[0])
    seeds = []
    for c in cands:
        if all(abs(c[1] - s[1]) > 1.5 * h or abs(c[3] - s[3]) > 1.5 * h for s in seeds):
            seeds.append(c)
        if len(seeds) >= refine_top:
            break
    t0 = time.time()
    hf = h / fine_div
    for s in seeds:
        axes = []
        for tc_ in (s[1], s[2], s[3]):
            axes.append(np.clip(np.arange(tc_ - h, tc_ + h + 1e-9, hf), 0.0, T))
        t1s, t2s, t3s = (np.unique(a) for a in axes)
        R1, V1 = ephem(opt, t1s, "B"); R3, _ = ephem(opt, t3s, "A")
        DVf, D1f, MRf = twoburn(R1, V1, R3, t1s, t2s, t3s, mc, mu, R, rmin, maxev)
        collect(t1s, t2s, t3s, DVf, D1f, MRf)
    out["fine_sec"] = round(time.time() - t0, 1)
    # 單棒網格最好的幾格也當候選（兩棒的特例，t2 = t1）
    for (sc, t1, t3, dv, m) in sorted(((S1[i, j], tt[i], tt[j], DV1[i, j], MR1[i, j]) for i, j in zip(ii, jj)),
                                      key=lambda z: -z[0])[:K]:
        cands.append((float(sc), float(t1), float(t1), float(t3), float(dv), None, int(m)))
    cands.sort(key=lambda c: -c[0])
    mins = min(cands, key=lambda c: c[4])
    out["two_best_est"] = {"est_score": cands[0][0], "t1": cands[0][1], "t2": cands[0][2], "t3": cands[0][3],
                           "dv_mps": cands[0][4] * 1000, "dv1_mps": None if cands[0][5] is None else
                           float(np.linalg.norm(cands[0][5]) * 1000), "M": cands[0][6]}
    out["two_min_dv"] = {"est_score": mins[0], "t1": mins[1], "t2": mins[2], "t3": mins[3],
                         "dv_mps": mins[4] * 1000, "M": mins[6]}
    # 兩棒 Pareto（攔截時刻分箱的最小 Δv）供天花板估計
    par = {}
    for c in cands:
        kbin = round(c[3] / h1)
        if kbin not in par or c[4] < par[kbin][1]:
            par[kbin] = (c[3], c[4])
    out["two_pareto"] = sorted([[float(v[0]), float(v[1] * 1000)] for v in par.values()])
    print(f"[{name}] 兩棒最佳估分 {cands[0][0]:.4f}（{cands[0][4]*1000:.1f} m/s, T={cands[0][3]:.0f}）"
          f"；最省 {mins[4]*1000:.1f} m/s；加密 {out['fine_sec']}s", flush=True)

    # --- 前 K 名（去重）→ J2–J4 精修 + 拆棒
    top = []
    for c in cands:
        if all(abs(c[1] - s[1]) > h or abs(c[3] - s[3]) > h or (c[5] is None) != (s[5] is None) for s in top):
            top.append(c)
        if len(top) >= K:
            break
    out["top"] = [{"est_score": c[0], "t1": c[1], "t2": c[2], "t3": c[3], "dv_mps": c[4] * 1000,
                   "dv1_mps": None if c[5] is None else float(np.linalg.norm(c[5]) * 1000), "M": c[6]}
                  for c in top]
    if finalize:
        fin = []
        for rank, c in enumerate(top):
            if c[5] is None:
                dvs, coasts, t0r = [np.zeros(3)], [c[3] - c[1]], c[1]
            else:
                dvs, coasts, t0r = [c[5], np.zeros(3)], [c[2] - c[1], c[3] - c[2]], c[1]
            r = finalize_route(opt, cfg, t0r, dvs, coasts, tag=f"oracle#{rank}")
            r.update({"est_score": c[0], "M": c[6], "pre_dv_mps": c[4] * 1000, "structure":
                      "1-burn" if c[5] is None else "2-burn"})
            fin.append(r)
            print(f"[{name}] oracle#{rank} 估 {c[0]:.4f} → "
                  + (f"合法 {r['score']:.4f}（{r['num_burns']} 棒, {r['total_dv_mps']:.1f} m/s, "
                     f"T={r['T_team']:.0f}）" if r.get("ok") and r.get("legal") else f"失敗：{r.get('reason')}")
                  + f" {r.get('sec')}s", flush=True)
        out["finalized"] = fin
    out["total_sec"] = round(time.time() - t_all, 1)
    jdump(os.path.join(OUT, f"oracle_twoburn_{name}.json"), out)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario")
    ap.add_argument("--h", type=float, default=None, help="兩棒粗網格步長（秒，預設 T_max/80）")
    ap.add_argument("--K", type=int, default=10)
    ap.add_argument("--maxev", type=int, default=160)
    ap.add_argument("--refine-top", type=int, default=6)
    ap.add_argument("--no-finalize", action="store_true")
    a = ap.parse_args()
    run(a.scenario, h=a.h, K=a.K, finalize=not a.no_finalize, maxev=a.maxev, refine_top=a.refine_top)
