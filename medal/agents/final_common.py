"""金／銅牌賽共用的二體幾何與安全距離工具。

本模組固定使用點質量二體模型。規則的 ``gravity_degree`` 非零時，結果仍是二體近似；
正式二體賽制可直接使用。位置、速度與距離分別以 km、km/s 與 km 表示，單發上限以 m/s 表示。
"""
import math

import numpy as np
from numba import njit

from physics import EARTH_MU, RE_VAL
from physics.frames import rsw_basis


@njit(cache=True)
def _norm3(x):
    return math.sqrt(x[0] * x[0] + x[1] * x[1] + x[2] * x[2])


@njit(cache=True)
def _stumpff(z):
    """回傳通用變數的 Stumpff C(z)、S(z)。"""
    if z > 1e-6:
        q = math.sqrt(z)
        return (1.0 - math.cos(q)) / z, (q - math.sin(q)) / (q * q * q)
    if z < -1e-6:
        q = math.sqrt(-z)
        return (math.cosh(q) - 1.0) / (-z), (math.sinh(q) - q) / (q * q * q)
    # 近拋物線時避開兩個相近數相減。
    c = 0.5 - z / 24.0 + z * z / 720.0 - z * z * z / 40320.0
    s = 1.0 / 6.0 - z / 120.0 + z * z / 5040.0 - z * z * z / 362880.0
    return c, s


@njit(cache=True)
def _universal_value(chi, r0n, rv0, alpha, sqrt_mu):
    z = alpha * chi * chi
    c, s = _stumpff(z)
    q = rv0 / sqrt_mu
    f = q * chi * chi * c + (1.0 - alpha * r0n) * chi * chi * chi * s + r0n * chi
    fp = q * chi * (1.0 - z * s) + (1.0 - alpha * r0n) * chi * chi * c + r0n
    return f, fp, c, s


@njit(cache=True)
def kepler(r0, v0, dt, mu=EARTH_MU):
    """通用變數法傳播二體軌道；橢圓、雙曲線與正負時間皆可。"""
    if dt == 0.0:
        return r0.copy(), v0.copy()
    r0n = _norm3(r0)
    rv0 = r0[0] * v0[0] + r0[1] * v0[1] + r0[2] * v0[2]
    v2 = v0[0] * v0[0] + v0[1] * v0[1] + v0[2] * v0[2]
    alpha = 2.0 / r0n - v2 / mu
    sqrt_mu = math.sqrt(mu)
    sign = 1.0 if dt > 0.0 else -1.0
    target = sqrt_mu * abs(dt)
    if alpha > 1e-12:
        guess = sqrt_mu * abs(dt) * alpha
    elif alpha < -1e-12:
        a_abs = -1.0 / alpha
        guess = math.sqrt(a_abs) * math.asinh(abs(dt) * math.sqrt(mu / (a_abs * a_abs * a_abs)))
    else:
        guess = target / r0n
    # 時間對通用變數嚴格遞增；括住根後用 Newton，越界時二分。
    lo = 0.0
    hi = max(1.0, guess * 1.5)
    for _ in range(80):
        fhi, _, _, _ = _universal_value(sign * hi, r0n, rv0, alpha, sqrt_mu)
        if sign * fhi >= target:
            break
        hi *= 2.0
    u = min(max(guess, lo), hi)
    for _ in range(50):
        f, fp, _, _ = _universal_value(sign * u, r0n, rv0, alpha, sqrt_mu)
        err = sign * f - target
        if abs(err) <= 1e-12 * max(target, r0n):
            break
        if err > 0.0:
            hi = u
        else:
            lo = u
        nxt = u - err / fp
        if not (lo < nxt < hi) or not math.isfinite(nxt):
            nxt = 0.5 * (lo + hi)
        u = nxt
    chi = sign * u
    z = alpha * chi * chi
    c, s = _stumpff(z)
    f = 1.0 - chi * chi * c / r0n
    g = dt - chi * chi * chi * s / sqrt_mu
    r = f * r0 + g * v0
    rn = _norm3(r)
    fdot = sqrt_mu * chi * (z * s - 1.0) / (rn * r0n)
    gdot = 1.0 - chi * chi * c / rn
    v = fdot * r0 + gdot * v0
    return r, v


@njit(cache=True)
def kepler_grid(r0, v0, taus, mu=EARTH_MU):
    """一次傳播時間網格；各時刻都從同一初態起算。"""
    n = len(taus)
    rs = np.empty((n, 3), dtype=np.float64)
    vs = np.empty((n, 3), dtype=np.float64)
    for i in range(n):
        rs[i], vs[i] = kepler(r0, v0, taus[i], mu)
    return rs, vs


@njit(cache=True)
def stm_rv(r0, v0, tau, mu=EARTH_MU):
    """中央差分的速度到位置狀態轉移矩陣，單位 km/(km/s)。"""
    phi = np.empty((3, 3), dtype=np.float64)
    if tau == 0.0:
        phi[:] = 0.0
        return phi
    h = 1e-5
    for j in range(3):
        vp = v0.copy()
        vm = v0.copy()
        vp[j] += h
        vm[j] -= h
        rp, _ = kepler(r0, vp, tau, mu)
        rm, _ = kepler(r0, vm, tau, mu)
        for k in range(3):
            phi[k, j] = (rp[k] - rm[k]) / (2.0 * h)
    return phi


@njit(cache=True)
def stm_rv_grid(r0, v0, taus, mu=EARTH_MU):
    """一次求整個時間網格的速度到位置狀態轉移矩陣。"""
    out = np.empty((len(taus), 3, 3), dtype=np.float64)
    for i in range(len(taus)):
        out[i] = stm_rv(r0, v0, taus[i], mu)
    return out


@njit(cache=True)
def ball_ls(Phi, d, D):
    """解球內最小平方 ``min |Phi y-d|``，回傳距離與球內解。"""
    if D <= 0.0:
        return _norm3(d), np.zeros(3, dtype=np.float64)
    U, s, Vt = np.linalg.svd(Phi)
    c = U.T @ d
    z = np.zeros(3, dtype=np.float64)
    tol = max(1e-14 * s[0], 1e-15)
    for i in range(3):
        if s[i] > tol:
            z[i] = c[i] / s[i]
    if _norm3(z) <= D:
        y = Vt.T @ z
        return _norm3(Phi @ y - d), y
    # 球面最優解滿足 secular equation；Newton 步留在二分括號內。
    lo = 0.0
    hi = max(s[0] * s[0], 1e-20)
    D2 = D * D
    for _ in range(80):
        q = 0.0
        for i in range(3):
            zi = s[i] * c[i] / (s[i] * s[i] + hi)
            q += zi * zi
        if q <= D2:
            break
        hi *= 2.0
    lam = 0.5 * hi
    for _ in range(60):
        q = 0.0
        dq = 0.0
        for i in range(3):
            den = s[i] * s[i] + lam
            zi = s[i] * c[i] / den
            q += zi * zi
            dq -= 2.0 * zi * zi / den
        err = q - D2
        if abs(err) <= 1e-13 * D2:
            break
        if err > 0.0:
            lo = lam
        else:
            hi = lam
        nxt = lam - err / dq if dq != 0.0 else math.nan
        if not (lo < nxt < hi) or not math.isfinite(nxt):
            nxt = 0.5 * (lo + hi)
        lam = nxt
    for i in range(3):
        z[i] = s[i] * c[i] / (s[i] * s[i] + lam)
    y = Vt.T @ z
    return _norm3(Phi @ y - d), y


def time_grid(T, grid_sec=5.0):
    """建立含窗口終點的正時間網格。"""
    T = float(T)
    if T <= 0.0:
        return np.empty(0, dtype=np.float64)
    n = max(1, int(math.ceil(T / float(grid_sec))))
    return np.linspace(T / n, T, n, dtype=np.float64)


class ReachSet:
    """單發球形速度上限的線性化可達位置；非二體規則時仍是二體近似。"""

    def __init__(self, r0, v0, D_mps, taus, mu=EARTH_MU):
        self.r0 = np.asarray(r0, dtype=np.float64).reshape(3).copy()
        self.v0 = np.asarray(v0, dtype=np.float64).reshape(3).copy()
        self.D_mps = float(D_mps)
        self.D_kms = self.D_mps / 1000.0
        self.taus = np.asarray(taus, dtype=np.float64).reshape(-1).copy()
        self.mu = float(mu)
        self.r_nom, self.v_nom = kepler_grid(self.r0, self.v0, self.taus, self.mu)
        self.Phi = stm_rv_grid(self.r0, self.v0, self.taus, self.mu)


def make_reach(r0, v0, D_mps, taus, mu=EARTH_MU):
    """建立可達集合；單發上限 D 使用 m/s。"""
    return ReachSet(r0, v0, D_mps, taus, mu)


@njit(cache=True)
def _reach_distance_core(r_nom, phi, D_kms, x_grid):
    out = np.empty(len(r_nom), dtype=np.float64)
    for i in range(len(r_nom)):
        out[i] = ball_ls(phi[i], x_grid[i] - r_nom[i], D_kms)[0]
    return out


def reach_distance(reach, x_grid):
    """各網格時刻的點到追方線性化可達集合距離，單位 km。"""
    x = np.asarray(x_grid, dtype=np.float64)
    if x.shape != reach.r_nom.shape:
        raise ValueError("x_grid 形狀須與 ReachSet.r_nom 相同")
    return _reach_distance_core(reach.r_nom, reach.Phi, reach.D_kms, x)


@njit(cache=True)
def _linear_distance_at(rp0, vp0, re0, ve0, D_kms, tau, mu):
    rp, _ = kepler(rp0, vp0, tau, mu)
    re, _ = kepler(re0, ve0, tau, mu)
    phi = stm_rv(rp0, vp0, tau, mu)
    return ball_ls(phi, re - rp, D_kms)[0]


@njit(cache=True)
def _golden_linear(rp0, vp0, re0, ve0, D_kms, lo, hi, mu):
    q = 0.6180339887498949
    x1 = hi - q * (hi - lo)
    x2 = lo + q * (hi - lo)
    f1 = _linear_distance_at(rp0, vp0, re0, ve0, D_kms, x1, mu)
    f2 = _linear_distance_at(rp0, vp0, re0, ve0, D_kms, x2, mu)
    for _ in range(15):
        if f1 <= f2:
            hi, x2, f2 = x2, x1, f1
            x1 = hi - q * (hi - lo)
            f1 = _linear_distance_at(rp0, vp0, re0, ve0, D_kms, x1, mu)
        else:
            lo, x1, f1 = x1, x2, f2
            x2 = lo + q * (hi - lo)
            f2 = _linear_distance_at(rp0, vp0, re0, ve0, D_kms, x2, mu)
    if f1 <= f2:
        return f1, x1
    return f2, x2


@njit(cache=True)
def _linear_scan_batch(rp0, vp0, r_nom, phi, taus, D_kms, re0, ve0, dvs_mps, R_cap, mu, refine):
    n = len(dvs_mps)
    margins = np.empty(n, dtype=np.float64)
    times = np.empty(n, dtype=np.float64)
    d0 = _norm3(re0 - rp0)
    for j in range(n):
        ve = ve0 + dvs_mps[j] / 1000.0
        best = d0
        best_tau = 0.0
        best_idx = -1
        for i in range(len(taus)):
            re, _ = kepler(re0, ve, taus[i], mu)
            dist = ball_ls(phi[i], re - r_nom[i], D_kms)[0]
            if dist < best:
                best = dist
                best_tau = taus[i]
                best_idx = i
        if refine and len(taus) > 0:
            if best_idx < 0:
                lo, hi = 0.0, taus[0]
            else:
                lo = 0.0 if best_idx == 0 else taus[best_idx - 1]
                hi = taus[best_idx] if best_idx == len(taus) - 1 else taus[best_idx + 1]
            refined, tau = _golden_linear(rp0, vp0, re0, ve, D_kms, lo, hi, mu)
            if refined < best:
                best = refined
                best_tau = tau
        margins[j] = best - R_cap
        times[j] = best_tau
    return margins, times


def linear_margins_batch(reach_p, r_e0, v_e0, dv_e_mps, R_cap, refine=False):
    """批次求候選躲方推力的最小線性距離餘裕；推力單位 m/s。"""
    dvs = np.asarray(dv_e_mps, dtype=np.float64).reshape(-1, 3)
    return _linear_scan_batch(reach_p.r0, reach_p.v0, reach_p.r_nom, reach_p.Phi,
                              reach_p.taus, reach_p.D_kms,
                              np.asarray(r_e0, dtype=np.float64), np.asarray(v_e0, dtype=np.float64),
                              dvs, float(R_cap), reach_p.mu, bool(refine))


def linear_margin(reach_p, r_e0, v_e0, R_cap):
    """躲方滑行軌跡對追方可達集合的全窗口最小餘裕及時刻。"""
    margins, times = linear_margins_batch(reach_p, r_e0, v_e0, np.zeros((1, 3)), R_cap, refine=True)
    return float(margins[0]), float(times[0])


@njit(cache=True)
def _exact_distance_at(rp0, vp0, re0, ve0, dv, tau, mu):
    rp, vp = kepler(rp0, vp0 + dv, tau, mu)
    re, ve = kepler(re0, ve0, tau, mu)
    return _norm3(rp - re), rp, vp, re, ve


@njit(cache=True)
def _golden_exact_time(rp0, vp0, re0, ve0, dv, lo, hi, mu):
    q = 0.6180339887498949
    x1 = hi - q * (hi - lo)
    x2 = lo + q * (hi - lo)
    f1 = _exact_distance_at(rp0, vp0, re0, ve0, dv, x1, mu)[0]
    f2 = _exact_distance_at(rp0, vp0, re0, ve0, dv, x2, mu)[0]
    for _ in range(20):
        if f1 <= f2:
            hi, x2, f2 = x2, x1, f1
            x1 = hi - q * (hi - lo)
            f1 = _exact_distance_at(rp0, vp0, re0, ve0, dv, x1, mu)[0]
        else:
            lo, x1, f1 = x1, x2, f2
            x2 = lo + q * (hi - lo)
            f2 = _exact_distance_at(rp0, vp0, re0, ve0, dv, x2, mu)[0]
    if f1 <= f2:
        return f1, x1
    return f2, x2


@njit(cache=True)
def _exact_refine(rp0, vp0, re0, ve0, D_kms, dv0, tau0, T, grid_sec, mu):
    dv = dv0.copy()
    tau = tau0
    dist = _exact_distance_at(rp0, vp0, re0, ve0, dv, tau, mu)[0]
    for _ in range(20):
        old_dv = dv.copy()
        old_tau = tau
        rp, _ = kepler(rp0, vp0 + dv, tau, mu)
        re, _ = kepler(re0, ve0, tau, mu)
        phi = stm_rv(rp0, vp0 + dv, tau, mu)
        d = re - rp + phi @ dv
        _, new_dv = ball_ls(phi, d, D_kms)
        # 非線性模型若失準，沿步長回退到實際距離確實縮小。
        trial = new_dv
        trial_dist = _exact_distance_at(rp0, vp0, re0, ve0, trial, tau, mu)[0]
        for _ in range(8):
            if trial_dist <= dist + 1e-10:
                break
            trial = 0.5 * (trial + dv)
            trial_dist = _exact_distance_at(rp0, vp0, re0, ve0, trial, tau, mu)[0]
        if trial_dist <= dist + 1e-10:
            dv = trial
            dist = trial_dist
        width = max(2.0 * grid_sec, min(60.0, 0.1 * T))
        lo = max(0.0, tau - width)
        hi = min(T, tau + width)
        if hi > lo:
            ftime, ttime = _golden_exact_time(rp0, vp0, re0, ve0, dv, lo, hi, mu)
            if ftime < dist:
                tau = ttime
                dist = ftime
        # 以實際位置改變量判斷一公尺收斂，推力本身是 km/s，不能直接比較。
        if _norm3(phi @ (dv - old_dv)) < 0.001 and abs(tau - old_tau) < 1e-4:
            break
    return dist, dv, tau


def exact_miss(r_p0, v_p0, D, r_e0, v_e0, T, mu=EARTH_MU, grid_sec=5.0, n_starts=4,
               reach_p=None):
    """求追方單發最佳回應的非線性最近距離，回傳 km、推力 km/s、時刻 s。

    初值取線性可達集合的局部極小；各初值交替求球內 Gauss–Newton 步與連續時間極小，
    每個答案均以重新傳播的實際距離驗證。規則有高階重力時仍採二體近似。
    """
    rp0 = np.asarray(r_p0, dtype=np.float64).reshape(3)
    vp0 = np.asarray(v_p0, dtype=np.float64).reshape(3)
    re0 = np.asarray(r_e0, dtype=np.float64).reshape(3)
    ve0 = np.asarray(v_e0, dtype=np.float64).reshape(3)
    T = float(T)
    D_kms = max(0.0, float(D)) / 1000.0
    if T <= 0.0:
        return float(np.linalg.norm(rp0 - re0)), np.zeros(3), 0.0
    if reach_p is None or reach_p.taus[-1] < T - 1e-8:
        reach_p = ReachSet(rp0, vp0, D, time_grid(T, grid_sec), mu)
    taus = reach_p.taus
    r_e, _ = kepler_grid(re0, ve0, taus, mu)
    dist = reach_distance(reach_p, r_e)
    # 局部極小以線性預估排序；保留窗口兩端，避免端點解漏掉。
    local = [i for i in range(len(taus)) if (i == 0 or dist[i] <= dist[i - 1])
             and (i == len(taus) - 1 or dist[i] <= dist[i + 1])]
    local.sort(key=lambda i: dist[i])
    picks = local[:max(1, int(n_starts))]
    if len(taus) - 1 not in picks:
        picks.append(len(taus) - 1)
    best = float(np.linalg.norm(rp0 - re0))
    best_dv = np.zeros(3, dtype=np.float64)
    best_tau = 0.0
    for i in picks:
        _, dv0 = ball_ls(reach_p.Phi[i], r_e[i] - reach_p.r_nom[i], D_kms)
        got, dv, tau = _exact_refine(rp0, vp0, re0, ve0, D_kms, dv0, float(taus[i]), T,
                                     float(grid_sec), float(mu))
        if got < best:
            best, best_dv, best_tau = got, dv, tau
    # 固定最終推力再掃描全窗口，確認回報的是該軌跡的最近距離。
    rs_p, _ = kepler_grid(rp0, vp0 + best_dv, taus, mu)
    d_actual = np.linalg.norm(rs_p - r_e, axis=1)
    i = int(np.argmin(d_actual))
    lo = 0.0 if i == 0 else float(taus[i - 1])
    hi = float(taus[i]) if i == len(taus) - 1 else float(taus[i + 1])
    got, tau = _golden_exact_time(rp0, vp0, re0, ve0, best_dv, lo, hi, mu)
    if got < best:
        best, best_tau = got, tau
    return float(best), best_dv, float(best_tau)


@njit(cache=True)
def sma_after(r, v, dv_kms):
    """一發推完的官方半長軸；雙曲線為負、拋物線為正無窮。"""
    w = v + dv_kms
    x = 2.0 / _norm3(r) - (w[0] * w[0] + w[1] * w[1] + w[2] * w[2]) / EARTH_MU
    return 1.0 / x if x != 0.0 else math.inf


def dsma_capacity(r, v, D):
    """沿速度正反方向推至 D m/s 時，半長軸增加與減少的容量。

    順向的增加量與逆向的減少量分開計算；該方向跨過拋物線時容量發散。
    """
    r = np.asarray(r, dtype=np.float64)
    v = np.asarray(v, dtype=np.float64)
    vn = float(np.linalg.norm(v))
    if vn == 0.0 or D <= 0.0:
        return 0.0, 0.0
    delta = v * (float(D) / (1000.0 * vn))
    rn = float(np.linalg.norm(r))
    x0 = 2.0 / rn - vn * vn / EARTH_MU
    xp = 2.0 / rn - float(np.dot(v + delta, v + delta)) / EARTH_MU
    xm = 2.0 / rn - float(np.dot(v - delta, v - delta)) / EARTH_MU
    if x0 == 0.0:
        return 0.0, math.inf
    a = 1.0 / x0
    ap = float(sma_after(r, v, delta))
    am = float(sma_after(r, v, -delta))
    up = math.inf if x0 > 0.0 and xp <= 0.0 else max(0.0, ap - a)
    # 逆向推可越過零速；雙曲線的端點即使仍是雙曲線，也可能途中跨界兩次。
    retro_t = min(float(D) / 1000.0, vn)
    x_retro_max = 2.0 / rn - (vn - retro_t) ** 2 / EARTH_MU
    if x0 < 0.0 and x_retro_max >= 0.0:
        down = math.inf
    elif x0 > 0.0 and xm <= 0.0:
        # 橢圓逆向推過零速後才跨界時，最小 a 出現在零速處。
        down = max(0.0, a - rn / 2.0)
    else:
        down = max(0.0, a - am)
    return up, down


def dsma_capacity_worst(r, v, D):
    """之後各回合起點可能在軌道上任何位置：取遠地點（速度最小、沿速度推改 a 最少）的容量，跟此刻的取小。

    E29 教訓：推出偏心軌道後，下一回合剛好在遠地點附近，逆向推滿拉不回安全空域。雙曲線沒有遠地點，退回此刻的容量。"""
    up, down = dsma_capacity(r, v, D)
    r = np.asarray(r, dtype=np.float64)
    v = np.asarray(v, dtype=np.float64)
    rn = float(np.linalg.norm(r))
    a = float(sma_after(r, v, np.zeros(3)))
    if not (math.isfinite(a) and a > 0.0):
        return up, down
    h = np.cross(r, v)
    ecc = math.sqrt(max(0.0, 1.0 - float(h @ h) / (EARTH_MU * a)))
    ra = a * (1.0 + ecc)
    va = math.sqrt(max(0.0, EARTH_MU * (2.0 / ra - 1.0 / a)))
    if va <= 0.0 or ra <= rn * 0.999999 and ecc < 1e-12:
        return up, down
    r_apo = np.array([ra, 0.0, 0.0])
    v_apo = np.array([0.0, va, 0.0])
    up_a, down_a = dsma_capacity(r_apo, v_apo, D)
    return min(up, up_a), min(down, down_a)


def zone_slack(a, zone, n_burns, up, down):
    """剩餘發數的保守半長軸可達餘裕，負值表示到不了安全區間。"""
    if zone is None:
        return math.inf
    lo, hi = zone
    a = float(a)
    if not math.isfinite(a):
        return -math.inf
    n = max(0, int(n_burns))
    if lo <= a <= hi:
        return 0.0 if n == 0 else n * 0.9 * min(max(0.0, up), max(0.0, down))
    if a < lo:
        need = lo - a
        return -need if n == 0 else 0.9 * n * max(0.0, up) - need
    need = a - hi
    return -need if n == 0 else 0.9 * n * max(0.0, down) - need


@njit(cache=True)
def perigee_alt_km(r, v):
    """二體近地點相對赤道半徑的高度；向外雙曲線回傳無窮大。"""
    rn = _norm3(r)
    rv = r[0] * v[0] + r[1] * v[1] + r[2] * v[2]
    v2 = v[0] * v[0] + v[1] * v[1] + v[2] * v[2]
    energy = 0.5 * v2 - EARTH_MU / rn
    if energy > 0.0 and rv > 0.0:
        return math.inf
    h = np.array((r[1] * v[2] - r[2] * v[1],
                  r[2] * v[0] - r[0] * v[2],
                  r[0] * v[1] - r[1] * v[0]))
    h2 = h[0] * h[0] + h[1] * h[1] + h[2] * h[2]
    ecc = math.sqrt(max(0.0, 1.0 + 2.0 * energy * h2 / (EARTH_MU * EARTH_MU)))
    rp = h2 / (EARTH_MU * (1.0 + ecc))
    return rp - RE_VAL


def direction_set(n, r, v):
    """Fibonacci 球面方向與 RSW 六軸的 ECI 單位向量。"""
    n = max(0, int(n))
    out = np.empty((n + 6, 3), dtype=np.float64)
    golden = math.pi * (3.0 - math.sqrt(5.0))
    for i in range(n):
        z = 1.0 - 2.0 * (i + 0.5) / n
        radius = math.sqrt(max(0.0, 1.0 - z * z))
        angle = golden * i
        out[i] = (radius * math.cos(angle), radius * math.sin(angle), z)
    basis = rsw_basis(np.asarray(r, dtype=np.float64), np.asarray(v, dtype=np.float64))
    for j in range(3):
        out[n + 2 * j] = basis[j]
        out[n + 2 * j + 1] = -basis[j]
    return out


def round_context(game):
    """擷取同時回合決策所需的規則、發數與窗口長度。"""
    window = float(game.rules.window_sec)
    return {"T": min(window, float(game.time_left)),
            "round": int(game.turn) + 1,
            "burns_left_after": max(0, int(round(float(game.time_left) / window)) - 1),
            "D_p": float(game.burn_cap("pursuer")),
            "D_e": float(game.burn_cap("evader")),
            "R_cap": float(game.rules.capture_radius_km),
            "zone": game.rules.safe_sma_km}
