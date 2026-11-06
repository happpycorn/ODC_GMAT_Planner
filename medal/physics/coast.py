"""雙船同時滑行 + 連續事件偵測（捕獲 / 撞地）。

舊版 final_env 只在窗口結束的瞬間比距離、比半徑：兩船在窗口中間穿過捕獲球又離開、
或軌跡在窗口中間掉進大氣再爬出來，都偵測不到（2026-09-15 盤點實測：只看端點會系統性
高估最近距離）。這裡把一個窗口切成 substep 段，每段用 DOP853 傳播，再用端點的位置+速度
做三次 Hermite 內插，在段內找：
  * 相對距離第一次 <= capture_km 的時刻（捕獲）
  * 各自半徑第一次 <= min_radius_km 的時刻（撞地 / 再入）
  * 整段的最近接近距離與時刻

Hermite 內插誤差 ~ h^4 * |r''''| / 384：LEO 下 h=60s 約 0.3 m、h=120s 約 5 m，
遠小於捕獲半徑。所有函式都是 njit，可在搜尋迴圈裡大量呼叫。
"""
import math

import numpy as np
from numba import njit

from physics.propagator import propagate

N_SAMPLES = 24  # 每個 substep 內 Hermite 取樣點數（+ 二分精修）


@njit(cache=True)
def _hermite(p0, v0, p1, v1, h, s):
    """三次 Hermite：s∈[0,1]，p0/p1 位置、v0/v1 速度（對真實時間），h 段長。"""
    s2 = s * s
    s3 = s2 * s
    h00 = 2.0 * s3 - 3.0 * s2 + 1.0
    h10 = s3 - 2.0 * s2 + s
    h01 = -2.0 * s3 + 3.0 * s2
    h11 = s3 - s2
    return h00 * p0 + h10 * h * v0 + h01 * p1 + h11 * h * v1


@njit(cache=True)
def _nrm(x):
    return math.sqrt(x[0] * x[0] + x[1] * x[1] + x[2] * x[2])


@njit(cache=True)
def _first_below(p0, v0, p1, v1, h, level):
    """段內 |p(s)| 第一次 <= level 的 s（找不到回傳 -1）。並回傳段內最小值與其 s。"""
    best = _nrm(p0)
    best_s = 0.0
    prev = best
    prev_s = 0.0
    hit = -1.0
    if prev <= level:
        return 0.0, best, best_s
    for i in range(1, N_SAMPLES + 1):
        s = i / N_SAMPLES
        val = _nrm(_hermite(p0, v0, p1, v1, h, s))
        if val < best:
            best = val
            best_s = s
        if hit < 0.0 and val <= level:
            lo = prev_s
            hi = s
            for _ in range(30):
                mid = 0.5 * (lo + hi)
                if _nrm(_hermite(p0, v0, p1, v1, h, mid)) <= level:
                    hi = mid
                else:
                    lo = mid
            hit = hi
        prev = val
        prev_s = s
    # 最小值精修（黃金分割，在最佳取樣點鄰域）
    lo = max(0.0, best_s - 1.0 / N_SAMPLES)
    hi = min(1.0, best_s + 1.0 / N_SAMPLES)
    g = 0.6180339887498949
    a = hi - g * (hi - lo)
    b = lo + g * (hi - lo)
    fa = _nrm(_hermite(p0, v0, p1, v1, h, a))
    fb = _nrm(_hermite(p0, v0, p1, v1, h, b))
    for _ in range(25):
        if fa < fb:
            hi = b
            b = a
            fb = fa
            a = hi - g * (hi - lo)
            fa = _nrm(_hermite(p0, v0, p1, v1, h, a))
        else:
            lo = a
            a = b
            fa = fb
            b = lo + g * (hi - lo)
            fb = _nrm(_hermite(p0, v0, p1, v1, h, b))
    if fa < best:
        best = fa
        best_s = a
    if fb < best:
        best = fb
        best_s = b
    # 高相對速度（逆行交會 ~15 km/s）時，捕獲球可能整個落在兩個取樣點之間：取樣點都 > level，
    # 但精修後的最小值 <= level。回頭在「最小值前一個取樣點 → 最小值」之間二分找第一次穿越。
    if hit < 0.0 and level > 0.0 and best <= level:
        lo = math.floor(best_s * N_SAMPLES) / N_SAMPLES
        if lo >= best_s:
            lo = max(0.0, lo - 1.0 / N_SAMPLES)
        hi = best_s
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            if _nrm(_hermite(p0, v0, p1, v1, h, mid)) <= level:
                hi = mid
            else:
                lo = mid
        hit = hi
    return hit, best, best_s


# 事件代碼
EV_NONE = 0
EV_CAPTURE = 1
EV_CRASH_P = 2
EV_CRASH_E = 3


@njit(cache=True)
def coast_pair(rp, vp, re, ve, dt, substep, mu, gravity_degree, capture_km, min_radius_km):
    """兩船一起滑行 dt 秒，途中偵測事件；有事件就停在事件發生時刻。

    回傳 (rp, vp, re, ve, t_elapsed, event, min_dist_km, t_min_dist)
      event: EV_NONE / EV_CAPTURE / EV_CRASH_P / EV_CRASH_E（同段多個事件取最早；
             同時發生時優先序 撞地 > 捕獲，與舊 env 一致）
      capture_km <= 0 或 min_radius_km <= 0 表示不偵測該類事件。
    """
    d0 = _nrm(rp - re)
    min_d = d0
    t_min = 0.0
    if capture_km > 0.0 and d0 <= capture_km:
        return rp, vp, re, ve, 0.0, EV_CAPTURE, d0, 0.0
    if dt <= 0.0:
        return rp, vp, re, ve, 0.0, EV_NONE, d0, 0.0

    n = max(1, int(math.ceil(dt / substep - 1e-9)))
    h = dt / n
    t = 0.0
    for _ in range(n):
        rp1, vp1 = propagate(mu, rp, vp, h, gravity_degree)
        re1, ve1 = propagate(mu, re, ve, h, gravity_degree)

        s_cap, dmin, s_dmin = _first_below(rp - re, vp - ve, rp1 - re1, vp1 - ve1, h,
                                           capture_km if capture_km > 0.0 else -1.0)
        if dmin < min_d:
            min_d = dmin
            t_min = t + s_dmin * h

        s_cp = -1.0
        s_ce = -1.0
        if min_radius_km > 0.0:
            s_cp, _, _ = _first_below(rp, vp, rp1, vp1, h, min_radius_km)
            s_ce, _, _ = _first_below(re, ve, re1, ve1, h, min_radius_km)
        if not (math.isfinite(rp1[0]) and math.isfinite(rp1[1]) and math.isfinite(rp1[2])):
            s_cp = 1.0
        if not (math.isfinite(re1[0]) and math.isfinite(re1[1]) and math.isfinite(re1[2])):
            s_ce = 1.0

        # 取最早事件；同時刻撞地優先
        ev = EV_NONE
        s_ev = 2.0
        if s_cp >= 0.0 and s_cp < s_ev:
            ev = EV_CRASH_P
            s_ev = s_cp
        if s_ce >= 0.0 and s_ce < s_ev:
            ev = EV_CRASH_E
            s_ev = s_ce
        if s_cap >= 0.0 and s_cap < s_ev:
            ev = EV_CAPTURE
            s_ev = s_cap

        if ev != EV_NONE:
            te = s_ev * h
            if te > 0.0:
                rpe, vpe = propagate(mu, rp, vp, te, gravity_degree)
                ree, vee = propagate(mu, re, ve, te, gravity_degree)
            else:
                rpe, vpe, ree, vee = rp, vp, re, ve
            if ev == EV_CAPTURE:
                dcap = _nrm(rpe - ree)
                if dcap < min_d:
                    min_d = dcap
                    t_min = t + te
            return rpe, vpe, ree, vee, t + te, ev, min_d, t_min

        rp, vp, re, ve = rp1, vp1, re1, ve1
        t += h
    return rp, vp, re, ve, t, EV_NONE, min_d, t_min


@njit(cache=True)
def closest_approach(rp, vp, re, ve, horizon, substep, mu, gravity_degree):
    """純滑行下（雙方都不再推）接下來 horizon 秒內的最近距離、發生時刻、當下相對位置(re-rp)。"""
    d0 = _nrm(rp - re)
    best = d0
    best_t = 0.0
    best_rel = re - rp
    if horizon <= 0.0:
        return best, best_t, best_rel
    n = max(1, int(math.ceil(horizon / substep - 1e-9)))
    h = horizon / n
    t = 0.0
    for _ in range(n):
        rp1, vp1 = propagate(mu, rp, vp, h, gravity_degree)
        re1, ve1 = propagate(mu, re, ve, h, gravity_degree)
        _, dmin, s = _first_below(rp - re, vp - ve, rp1 - re1, vp1 - ve1, h, -1.0)
        if dmin < best:
            best = dmin
            best_t = t + s * h
            best_rel = -_hermite(rp - re, vp - ve, rp1 - re1, vp1 - ve1, h, s)
        rp, vp, re, ve = rp1, vp1, re1, ve1
        t += h
    return best, best_t, best_rel
