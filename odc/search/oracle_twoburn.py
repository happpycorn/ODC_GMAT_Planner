# 此模組負責雙棒網格搜尋與候選路線轉換。
# 主要入口為 run_twoburn_oracle，計算本體沿用原實作。
"""Deterministic two-burn oracle, ported from E1 (2026-10-29).

Each grid cell is independent. No parallel reductions or global RNG are used;
thread count and deadline batch boundaries do not change the floating point work.
Times are seconds, ECI impulses km/s. Deadlines use time.monotonic().
"""
import math
import time
import numpy as np
from numba import njit, prange
from poliastro._math.special import stumpff_c2 as c2, stumpff_c3 as c3
from odc.physics.core_math import (izzo_max_revs, lambert_izzo, check_constraints,
                           reaches_perigee, propagate_dop853, ephem_state)
from odc.runlog import log

BIG = 1.0e9


@njit(cache=True)
def vallado_safe(k, r0, v0, tof, numiter):
    """poliastro.core.propagation.vallado 的逐行複本，只多一個 NaN 防護（E1，2026-10-29）。

    原版的 Newton 迭代在某些雙曲線輸入會發散成 NaN，NaN 再進 stumpff_c2/c3 的級數分支
    （`while res + delta != res`，NaN 永遠不等於自己）就是無窮迴圈：hyperbolic_smoke 的兩棒網格
    h=400 s 在 (t1, t2, t3) = (4000, 5200, 10800) 卡死 2 小時（10-28 h=250 s 跑 5 小時沒結束應該也是這個）。
    psi 不是有限值就回傳 NaN，不呼叫 stumpff。正常輸入的算式與原版相同，結果逐位元一致。"""
    dot_r0v0 = r0 @ v0
    norm_r0 = np.sqrt(r0 @ r0)
    sqrt_mu = k**0.5
    alpha = -(v0 @ v0) / k + 2 / norm_r0
    if alpha > 0:
        xi_new = sqrt_mu * tof * alpha
    elif alpha < 0:
        xi_new = (np.sign(tof) * (-1 / alpha) ** 0.5
                  * np.log((-2 * k * alpha * tof)
                           / (dot_r0v0 + np.sign(tof) * np.sqrt(-k / alpha) * (1 - norm_r0 * alpha))))
    else:
        xi_new = sqrt_mu * tof / norm_r0
    count = 0
    xi = xi_new
    psi = c2_psi = c3_psi = norm_r = np.nan
    while count < numiter:
        xi = xi_new
        psi = xi * xi * alpha
        if not np.isfinite(psi):
            return np.nan, np.nan, np.nan, np.nan
        c2_psi = c2(psi)
        c3_psi = c3(psi)
        norm_r = (xi * xi * c2_psi + dot_r0v0 / sqrt_mu * xi * (1 - psi * c3_psi)
                  + norm_r0 * (1 - psi * c2_psi))
        xi_new = (xi + (sqrt_mu * tof - xi * xi * xi * c3_psi - dot_r0v0 / sqrt_mu * xi * xi * c2_psi
                        - norm_r0 * xi * (1 - psi * c3_psi)) / norm_r)
        if abs(xi_new - xi) < 1e-7:
            break
        else:
            count += 1
    else:
        return np.nan, np.nan, np.nan, np.nan
    f = 1 - xi**2 / norm_r0 * c2_psi
    g = tof - xi**3 / sqrt_mu * c3_psi
    gdot = 1 - xi**2 / norm_r * c2_psi
    fdot = sqrt_mu / (norm_r * norm_r0) * xi * (psi * c3_psi - 1)
    return f, g, fdot, gdot


@njit(cache=True)
def kepler(r0, v0, dt, mu):
    f, g, fd, gd = vallado_safe(mu, r0, v0, dt, 350)
    if not np.isfinite(f):
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
def twoburn(RB, VB, RA, t1s, t2s, t3s, mc, mu, max_revs, rmin, maxev, order):
    """三元組 (t1,t2,t3) 網格；回傳每格最小總 Δv、dv1 向量、終端圈數。

    平行化攤在 (t1,t3) 配對上、照 `order`（隨機排列）分派：t1 越早的配對工作量越大，
    直接 prange t1 會讓靜態分塊的第一個執行緒包下最重的那段，其他執行緒早早閒置
    （2026-10-28 h=250 實測 16 執行緒只有 1 個在跑、5 小時沒跑完）。"""
    n1, n2, n3 = t1s.shape[0], t2s.shape[0], t3s.shape[0]
    DV = np.full((n1, n2, n3), BIG)
    D1 = np.zeros((n1, n2, n3, 3))
    MR = np.full((n1, n2, n3), -1, dtype=np.int8)
    for q in prange(order.shape[0]):
        p = order[q]
        i = p // n3
        k = p % n3
        r1 = RB[i]; v1 = VB[i]
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


def twoburn_grid(RB, VB, RA, t1s, t2s, t3s, mc, mu, max_revs, rmin, maxev):
    order = np.random.default_rng(0).permutation(t1s.shape[0] * t3s.shape[0]).astype(np.int64)
    return twoburn(RB, VB, RA, t1s, t2s, t3s, mc, mu, max_revs, rmin, maxev, order)


def est_score(opt, T, dv_kms):
    from odc.scoring.scorer import calculate_score
    return calculate_score(min_distance_km=0.0, total_time_sec=float(T), total_dv_mps=float(dv_kms) * 1000.0,
                           penalty_count=0, k_t=opt.k_t, C_t=opt.C_t, k_v=opt.k_v, C_v=opt.C_v)


def ephem(opt, times, which):
    r0, v0 = (opt.B_r0, opt.B_v0) if which == "B" else (opt.A_r0, opt.A_v0)
    eph = None if opt.ephem is None else (opt.ephem[0], opt.ephem[2] if which == "B" else opt.ephem[1])
    return build_ephemeris(r0, v0, times, 60.0, opt.MU, opt.J2_VAL, opt.J3_VAL, opt.J4_VAL,
                           opt.RE_VAL, ephem=eph)



@njit(cache=True, parallel=True)
def build_ephemeris(r0, v0, times, dt, mu, j2, j3, j4, re, ephem=None):
    n = times.shape[0]
    R = np.zeros((n, 3)); V = np.zeros((n, 3))
    for i in prange(n):
        # 固定軌道檢查點 + 原 DOP853 補積分，無插值。
        if ephem is None:
            r, v = propagate_dop853(r0, v0, times[i], dt, mu, j2, j3, j4, re)
        else:
            r, v = ephem_state(0.0, ephem[0], ephem[1], times[i], mu, j2, j3, j4, re)
        R[i, 0] = r[0]; R[i, 1] = r[1]; R[i, 2] = r[2]
        V[i, 0] = v[0]; V[i, 1] = v[1]; V[i, 2] = v[2]
    return R, V


def route_from_standard_x(opt, x, N):
    """main.py 標準決策向量（球座標、coast_frac、final_leg_frac、瞄準偏移）→ (t0, dvs, coasts)。
    解碼慣例跟 main.legalize_violating_winner 逐字一致；終端棒 Δv 用 None（拆棒器重算）。"""
    mc, T_max = opt.MIN_COAST_TIME, opt.T_max
    x = np.asarray(x, dtype=np.float64)

    def sph(rr, th, ph):
        st = math.sin(th)
        return np.array([rr * st * math.cos(ph), rr * st * math.sin(ph), rr * math.cos(th)])
    t0 = float(x[0]); cur = t0; dvs, coasts, idx = [], [], 1
    for _ in range(1, N):
        dvv = sph(x[idx], x[idx + 1], x[idx + 2]); cf = x[idx + 3]; idx += 4
        mx = T_max - cur - mc
        tco = mc + cf * (mx - mc) if mx > mc else mc
        dvs.append(dvv); coasts.append(tco); cur += tco
    flf = x[-4]; mxf = T_max - cur
    tfin = mc + flf * (mxf - mc) if mxf > mc else mc
    dvs.append(np.zeros(3)); coasts.append(tfin)
    return t0, dvs, coasts


def standard_x_from_route(opt, t1, dv1, t2, t3):
    """兩棒路線（t1 燒 dv1、t2 終端 Lambert、t3 攔截）→ 標準決策向量（N=2）；dv1=None → N=1。"""
    mc, T_max = opt.MIN_COAST_TIME, opt.T_max
    if dv1 is None:
        mxf = T_max - t1
        flf = 0.0 if mxf <= mc else (t3 - t1 - mc) / (mxf - mc)
        return np.array([t1, min(max(flf, 0.0), 1.0), 0.0, 0.0, 0.0]), 1
    r = float(np.linalg.norm(dv1))
    th = math.acos(max(-1.0, min(1.0, dv1[2] / r))) if r > 0 else 0.0
    ph = math.atan2(dv1[1], dv1[0]) % (2 * math.pi)
    mx = T_max - t1 - mc
    cf = 0.0 if mx <= mc else (t2 - t1 - mc) / (mx - mc)
    mxf = T_max - t2
    flf = 0.0 if mxf <= mc else (t3 - t2 - mc) / (mxf - mc)
    return np.array([t1, r, th, ph, min(max(cf, 0.0), 1.0), min(max(flf, 0.0), 1.0),
                     0.0, 0.0, 0.0]), 2



class _DeadlineExpired(Exception):
    pass


def _check_deadline(deadline):
    if deadline is not None and time.monotonic() >= deadline:
        raise _DeadlineExpired


def _deadline_grid(deadline, RB, VB, RA, t1s, t2s, t3s, *args):
    if deadline is None:
        return twoburn_grid(RB, VB, RA, t1s, t2s, t3s, *args)
    # A few departure rows per batch bounds cooperative cancellation latency.
    pieces = []
    for i in range(0, len(t1s), 2):
        _check_deadline(deadline)
        pieces.append(twoburn_grid(RB[i:i+2], VB[i:i+2], RA,
                                  t1s[i:i+2], t2s, t3s, *args))
    _check_deadline(deadline)
    return tuple(np.concatenate([p[j] for p in pieces]) for j in range(3))


def run_twoburn_oracle(opt, *, K, grid_div, maxev=160, refine_top=6,
                       fine_div=5, deadline=None):
    """Return the E1 top K, or [] on timeout (including partial grids).

    The pipeline also supervises this work in a disposable spawn process so cold
    compilation and ephemeris/single-burn kernels have a hard wall-clock bound.
    """
    try:
        return _run(opt, K=K, grid_div=grid_div, maxev=maxev,
                    refine_top=refine_top, fine_div=fine_div, deadline=deadline)
    except _DeadlineExpired:
        log.warning("Oracle grid deadline exceeded; discarding incomplete grid")
        return []


def _run(opt, *, K, grid_div, maxev, refine_top, fine_div, deadline):
    h = opt.T_max / grid_div
    _check_deadline(deadline)
    T, mc, mu, R = opt.T_max, opt.MIN_COAST_TIME, opt.MU, opt.LAMBERT_MAX_REVS
    rmin = opt.MIN_PERIAPSIS
    _check_deadline(deadline)
    # --- 單棒：細網格窮舉（h1 = h/4）
    h1 = max(mc / 2, h / 4.0)
    tt = np.arange(0.0, T + 1e-9, h1)
    RB, VB = ephem(opt, tt, "B"); RA, _ = ephem(opt, tt, "A")
    DV1, MR1 = porkchop1(RB, VB, RA, tt, mc, mu, R, rmin)
    S1 = np.full(DV1.shape, -np.inf)
    ok = DV1 < BIG
    ii, jj = np.nonzero(ok)
    for a, b in zip(ii, jj):
        S1[a, b] = est_score(opt, tt[b], DV1[a, b])
    _check_deadline(deadline)
    # --- 兩棒：粗網格
    tg = np.arange(0.0, T + 1e-9, h)
    RBg, VBg = ephem(opt, tg, "B"); RAg, _ = ephem(opt, tg, "A")
    DV2, D12, MR2 = _deadline_grid(deadline, RBg, VBg, RAg, tg, tg, tg, mc, mu, R, rmin, maxev)
    cands = []

    def collect(t1s, t2s, t3s, DV, D1, MR):
        idx = np.argwhere(DV < BIG)
        for (i, j, k) in idx:
            cands.append((est_score(opt, t3s[k], DV[i, j, k]), float(t1s[i]), float(t2s[j]), float(t3s[k]),
                          float(DV[i, j, k]), D1[i, j, k].copy(), int(MR[i, j, k])))
    collect(tg, tg, tg, DV2, D12, MR2)

    _check_deadline(deadline)
    # --- 加密：粗網格前 refine_top 名（去重）周圍 ±h、步長 h/fine_div
    cap_tot0 = (opt.MAX_TOTAL_DV_MPS or 1e9) / 1000.0
    cands.sort(key=lambda c: (c[4] > cap_tot0, -c[0]))
    seeds = []
    for c in cands:
        if all(abs(c[1] - s[1]) > 1.5 * h or abs(c[3] - s[3]) > 1.5 * h for s in seeds):
            seeds.append(c)
        if len(seeds) >= refine_top:
            break
    hf = h / fine_div
    for s in seeds:
        _check_deadline(deadline)
        axes = []
        for tc_ in (s[1], s[2], s[3]):
            axes.append(np.clip(np.arange(tc_ - h, tc_ + h + 1e-9, hf), 0.0, T))
        t1s, t2s, t3s = (np.unique(a) for a in axes)
        R1, V1 = ephem(opt, t1s, "B"); R3, _ = ephem(opt, t3s, "A")
        DVf, D1f, MRf = _deadline_grid(deadline, R1, V1, R3, t1s, t2s, t3s, mc, mu, R, rmin, maxev)
        collect(t1s, t2s, t3s, DVf, D1f, MRf)
    # 單棒網格最好的幾格也當候選（兩棒的特例，t2 = t1）
    for (sc, t1, t3, dv, m) in sorted(((S1[i, j], tt[i], tt[j], DV1[i, j], MR1[i, j]) for i, j in zip(ii, jj)),
                                      key=lambda z: -z[0])[:K]:
        cands.append((float(sc), float(t1), float(t1), float(t3), float(dv), None, int(m)))
    cap_tot = (opt.MAX_TOTAL_DV_MPS or 1e9) / 1000.0
    cands.sort(key=lambda c: (c[4] > cap_tot, -c[0]))      # 總 Δv ≤ 3 km/s 的排前面
    _check_deadline(deadline)
    # --- 前 K 名（去重）→ J2–J4 精修 + 拆棒
    top = []
    for c in cands:
        if all(abs(c[1] - s[1]) > h or abs(c[3] - s[3]) > h or (c[5] is None) != (s[5] is None) for s in top):
            top.append(c)
        if len(top) >= K:
            break
    _check_deadline(deadline)
    return [dict(rank=rank, t1=c[1], t2=c[2], t3=c[3],
                 dv1=None if c[5] is None else c[5].tolist(),
                 dv_mps=c[4] * 1000, est_score=c[0], M=c[6],
                 structure="1-burn" if c[5] is None else "2-burn")
            for rank, c in enumerate(top)]
