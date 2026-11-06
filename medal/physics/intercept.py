"""「追擊所需 Δv」：從現在起一發脈衝、在時限內追上（假設躲者之後純滑行）的最小 Δv。

這是整個決賽專案的核心局勢量（METHODOLOGY §5 的燃料消耗戰）：
  * need_dv / 追者剩餘 Δv < 1 → 若躲者不動，追者一發就能收掉比賽
  * 躲者的機動價值 = 讓這個比值變大多少
  * RL 觀測特徵與勢能型獎勵塑形都用它

做法：
  1. 沿躲者滑行軌跡取 n_tof 個時刻的星曆（J2 傳播，一路接力所以成本 ~ 一次長傳播）
  2. 每個時刻解 Lambert（M=0..max_revs、兩分支、順逆行），取最小 Δv，並排除轉移弧會
     掉到 min_radius 以下的解（弧內經過近地點才比近地點半徑，見 core_math.reaches_perigee）
  3. 在最佳的幾個局部極小值附近用黃金分割精修 tof
  4. （可選）J2 打靶：Lambert 是二體解，飛長弧時 J2 會讓落點偏幾公里～幾十公里，
     用有限差分 Newton 修正 v1 讓 J2 傳播真的命中

所有核心迴圈是 njit。
"""
import math

import numpy as np
from numba import njit

from physics.core_math import check_constraints, reaches_perigee
from physics.lambert import izzo
from physics.propagator import propagate


@njit(cache=True)
def _nrm(x):
    return math.sqrt(x[0] * x[0] + x[1] * x[1] + x[2] * x[2])


@njit(cache=True)
def _arc_safe(r1, v1, tof, mu, min_radius):
    if min_radius <= 0.0:
        return True
    if check_constraints(r1, v1, mu, min_radius):
        return True
    return not reaches_perigee(r1, v1, mu, tof)


@njit(cache=True)
def best_lambert(mu, r1, v_cur, r2, tof, max_revs, min_radius):
    """所有分支中需求 Δv 最小、且轉移弧不撞地的解。回傳 (dv_km_s, v1)。"""
    best = np.inf
    best_v = np.zeros(3)
    for M in range(max_revs + 1):
        for branch in range(2):
            lowpath = branch == 0
            if M == 0 and not lowpath:
                continue
            for direction in range(2):
                ok, v1, _ = izzo(mu, r1, r2, tof, M, direction == 0, lowpath, 35, 1e-10)
                if not ok:
                    continue
                d = _nrm(v1 - v_cur)
                if d < best and _arc_safe(r1, v1, tof, mu, min_radius):
                    best = d
                    best_v = v1
    return best, best_v


@njit(cache=True)
def intercept_scan(mu, gravity_degree, rp, vp, re, ve, tof_min, tof_max, n_tof, max_revs, min_radius):
    """沿 tof 網格掃描。回傳 (tofs[n], dvs[n] km/s, v1s[n,3], re_at[n,3], ve_at[n,3])。"""
    tofs = np.empty(n_tof)
    dvs = np.empty(n_tof)
    v1s = np.zeros((n_tof, 3))
    re_at = np.zeros((n_tof, 3))
    ve_at = np.zeros((n_tof, 3))
    if n_tof == 1:
        tofs[0] = tof_max
    else:
        for i in range(n_tof):
            tofs[i] = tof_min + (tof_max - tof_min) * i / (n_tof - 1)
    r_cur = re.copy()
    v_cur = ve.copy()
    t_cur = 0.0
    for i in range(n_tof):
        dt = tofs[i] - t_cur
        if dt > 0.0:
            r_cur, v_cur = propagate(mu, r_cur, v_cur, dt, gravity_degree)
            t_cur = tofs[i]
        re_at[i] = r_cur
        ve_at[i] = v_cur
        d, v1 = best_lambert(mu, rp, vp, r_cur, tofs[i], max_revs, min_radius)
        dvs[i] = d
        v1s[i] = v1
    return tofs, dvs, v1s, re_at, ve_at


@njit(cache=True)
def _refine_tof(mu, gravity_degree, rp, vp, re_lo, ve_lo, t_lo, t_hi, max_revs, min_radius, iters):
    """在 [t_lo, t_hi] 上黃金分割找最小 Δv；re_lo/ve_lo 是躲者在 t_lo 的狀態。"""
    g = 0.6180339887498949
    a = t_hi - g * (t_hi - t_lo)
    b = t_lo + g * (t_hi - t_lo)
    ra, _ = propagate(mu, re_lo, ve_lo, a - t_lo, gravity_degree)
    rb, _ = propagate(mu, re_lo, ve_lo, b - t_lo, gravity_degree)
    fa, va = best_lambert(mu, rp, vp, ra, a, max_revs, min_radius)
    fb, vb = best_lambert(mu, rp, vp, rb, b, max_revs, min_radius)
    for _ in range(iters):
        if fa < fb:
            t_hi = b
            b, fb, vb = a, fa, va
            a = t_hi - g * (t_hi - t_lo)
            ra, _ = propagate(mu, re_lo, ve_lo, a - t_lo, gravity_degree)
            fa, va = best_lambert(mu, rp, vp, ra, a, max_revs, min_radius)
        else:
            t_lo_new = a
            a, fa, va = b, fb, vb
            # 保持 re_lo 對應 t_lo：往前推進起點
            re_lo, ve_lo = propagate(mu, re_lo, ve_lo, t_lo_new - t_lo, gravity_degree)
            t_lo = t_lo_new
            b = t_lo + g * (t_hi - t_lo)
            rb, _ = propagate(mu, re_lo, ve_lo, b - t_lo, gravity_degree)
            fb, vb = best_lambert(mu, rp, vp, rb, b, max_revs, min_radius)
    if fa < fb:
        return fa, a, va
    return fb, b, vb


@njit(cache=True)
def min_intercept(mu, gravity_degree, rp, vp, re, ve, tof_min, tof_max, n_tof, max_revs, min_radius,
                  n_refine, refine_iters):
    """掃描 + 精修，回傳全域最小 (dv_km_s, tof, v1)。找不到可行解時 dv=inf。"""
    tofs, dvs, v1s, re_at, ve_at = intercept_scan(mu, gravity_degree, rp, vp, re, ve,
                                                  tof_min, tof_max, n_tof, max_revs, min_radius)
    best_i = 0
    for i in range(n_tof):
        if dvs[i] < dvs[best_i]:
            best_i = i
    best_dv = dvs[best_i]
    best_t = tofs[best_i]
    best_v = v1s[best_i].copy()
    if n_refine <= 0 or n_tof < 3 or not math.isfinite(best_dv):
        return best_dv, best_t, best_v

    # 找局部極小值，依 Δv 由小到大精修前 n_refine 個
    cand = np.full(n_tof, np.inf)
    for i in range(n_tof):
        left = dvs[i - 1] if i > 0 else np.inf
        right = dvs[i + 1] if i < n_tof - 1 else np.inf
        if dvs[i] <= left and dvs[i] <= right and math.isfinite(dvs[i]):
            cand[i] = dvs[i]
    order = np.argsort(cand)
    for k in range(min(n_refine, n_tof)):
        i = order[k]
        if not math.isfinite(cand[i]):
            break
        lo = max(i - 1, 0)
        hi = min(i + 1, n_tof - 1)
        d, t, v = _refine_tof(mu, gravity_degree, rp, vp, re_at[lo], ve_at[lo], tofs[lo], tofs[hi],
                              max_revs, min_radius, refine_iters)
        if d < best_dv:
            best_dv, best_t, best_v = d, t, v
    return best_dv, best_t, best_v


@njit(cache=True)
def shoot_j2(mu, gravity_degree, rp, v_guess, r_target, tof, iters, tol_km):
    """J2 打靶：修正 v1 讓 J2 傳播 tof 秒後命中 r_target。回傳 (v1, miss_km)。

    有限差分 3x3 Jacobian + Newton；每次迭代 4 次傳播。Lambert 解通常 2~3 次收斂到公尺級。
    """
    v = v_guess.copy()
    eps = 1e-6  # km/s
    miss = np.inf
    for _ in range(iters):
        rf, _ = propagate(mu, rp, v, tof, gravity_degree)
        err = rf - r_target
        miss = _nrm(err)
        if miss < tol_km:
            return v, miss
        J = np.empty((3, 3))
        for j in range(3):
            vp_ = v.copy()
            vp_[j] += eps
            rj, _ = propagate(mu, rp, vp_, tof, gravity_degree)
            J[:, j] = (rj - rf) / eps
        dv = np.linalg.solve(J, err)
        if not (math.isfinite(dv[0]) and math.isfinite(dv[1]) and math.isfinite(dv[2])):
            return v, miss
        v = v - dv
    rf, _ = propagate(mu, rp, v, tof, gravity_degree)
    return v, _nrm(rf - r_target)


def intercept_solution(mu, gravity_degree, rp, vp, re, ve, t_horizon, *, tof_min=60.0, n_tof=48,
                       max_revs=2, min_radius=0.0, n_refine=3, refine_iters=14, j2_shoot=True):
    """Python 包裝：回傳 dict(dv_mps, tof, dv_vec_mps(ECI), miss_km)。

    t_horizon <= tof_min 或完全無解時 dv_mps=inf、dv_vec_mps=0。
    """
    rp = np.asarray(rp, dtype=np.float64)
    vp = np.asarray(vp, dtype=np.float64)
    re = np.asarray(re, dtype=np.float64)
    ve = np.asarray(ve, dtype=np.float64)
    if t_horizon <= tof_min:
        return {"dv_mps": math.inf, "tof": 0.0, "dv_vec_mps": np.zeros(3), "miss_km": math.inf}
    dv, tof, v1 = min_intercept(mu, gravity_degree, rp, vp, re, ve, tof_min, t_horizon, n_tof, max_revs,
                                min_radius, n_refine, refine_iters)
    if not math.isfinite(dv):
        return {"dv_mps": math.inf, "tof": 0.0, "dv_vec_mps": np.zeros(3), "miss_km": math.inf}
    miss = math.nan
    if j2_shoot and gravity_degree > 0:
        r_t, _ = propagate(mu, re, ve, tof, gravity_degree)
        v1, miss = shoot_j2(mu, gravity_degree, rp, v1, r_t, tof, 6, 1e-3)
        dv = float(np.linalg.norm(v1 - vp))
    return {"dv_mps": float(dv) * 1000.0, "tof": float(tof), "dv_vec_mps": (v1 - vp) * 1000.0,
            "miss_km": float(miss)}
