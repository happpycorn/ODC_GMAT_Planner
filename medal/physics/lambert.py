"""Lambert 問題求解器（Izzo 2015），純 numba、支援多圈，不需要 poliastro。

為什麼自己寫：Planner 用的是 poliastro 的 `izzo`，但 poliastro 0.17 跟本 repo 的
numpy 2.x 不相容（見 physics/PROVENANCE.md）。決賽的解析追者、攔截所需 Δv、當天
copilot 都需要 Lambert，所以在這裡重寫一份。

演算法照 D. Izzo, "Revisiting Lambert's problem", CMDA 2015 以及 pykep 的 C++ 參考
實作；介面與分支慣例（prograde / lowpath / M）跟 poliastro `izzo` 對齊，方便跟
Planner 交叉比對。與 poliastro 刻意不同的兩點：
  1. 找 T_min 的 Halley 迭代每一步都重算 T(x)（pykep 的做法；poliastro 把 T 固定在
     初值，導數會用錯的 T）。
  2. 失敗不丟例外，而是回傳 ok=False——搜尋迴圈裡大量呼叫，例外在 numba 裡很貴。

驗證：tests/test_lambert.py 用 DOP853 純二體傳播（gravity_degree=0）把解出來的 v1
實際飛 tof 秒，檢查是否抵達 r2；另有與 poliastro 的離線比對腳本
tools/compare_lambert_poliastro.py（要在 Planner 的 venv 跑）。
"""
import math

import numpy as np
from numba import njit

_PI = math.pi


@njit(cache=True)
def _norm(v):
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


@njit(cache=True)
def _cross(a, b):
    return np.array([a[1] * b[2] - a[2] * b[1],
                     a[2] * b[0] - a[0] * b[2],
                     a[0] * b[1] - a[1] * b[0]])


@njit(cache=True)
def _hyp2f1b(x):
    """超幾何函數 2F1(3, 1, 5/2, x)（Battin），x 接近 1 時發散。"""
    if x >= 1.0:
        return np.inf
    res = 1.0
    term = 1.0
    ii = 0
    while ii < 100000:
        term = term * (3.0 + ii) * (1.0 + ii) / (2.5 + ii) * x / (ii + 1.0)
        res_old = res
        res += term
        if res_old == res:
            break
        ii += 1
    return res


@njit(cache=True)
def _compute_y(x, ll):
    return math.sqrt(max(0.0, 1.0 - ll * ll * (1.0 - x * x)))


@njit(cache=True)
def _compute_psi(x, y, ll):
    if -1.0 <= x < 1.0:
        c = x * y + ll * (1.0 - x * x)
        if c > 1.0:
            c = 1.0
        elif c < -1.0:
            c = -1.0
        return math.acos(c)
    elif x > 1.0:
        return math.asinh((y - x * ll) * math.sqrt(x * x - 1.0))
    return 0.0


@njit(cache=True)
def _tof_equation_y(x, y, T0, ll, M):
    if M == 0 and math.sqrt(0.6) < x < math.sqrt(1.4):
        eta = y - ll * x
        S_1 = (1.0 - ll - x * eta) * 0.5
        Q = 4.0 / 3.0 * _hyp2f1b(S_1)
        T_ = (eta ** 3 * Q + 4.0 * ll * eta) * 0.5
    else:
        psi = _compute_psi(x, y, ll)
        T_ = ((psi + M * _PI) / math.sqrt(abs(1.0 - x * x)) - x + ll * y) / (1.0 - x * x)
    return T_ - T0


@njit(cache=True)
def _tof_equation(x, T0, ll, M):
    return _tof_equation_y(x, _compute_y(x, ll), T0, ll, M)


@njit(cache=True)
def _dT(x, y, T, ll):
    return (3.0 * T * x - 2.0 + 2.0 * ll ** 3 * x / y) / (1.0 - x * x)


@njit(cache=True)
def _ddT(x, y, T, dT, ll):
    return (3.0 * T + 5.0 * x * dT + 2.0 * (1.0 - ll * ll) * ll ** 3 / y ** 3) / (1.0 - x * x)


@njit(cache=True)
def _dddT(x, y, dT, ddT, ll):
    return (7.0 * x * ddT + 8.0 * dT - 6.0 * (1.0 - ll * ll) * ll ** 5 * x / y ** 5) / (1.0 - x * x)


@njit(cache=True)
def _compute_T_min(ll, M, numiter, rtol):
    """M 圈解存在所需的最小無因次飛行時間（Halley 迭代找 dT/dx=0）。回傳 (ok, x, T_min)。"""
    if ll == 1.0:
        return True, 0.0, _tof_equation(0.0, 0.0, ll, M)
    if M == 0:
        return True, np.inf, 0.0
    x = 0.1
    for _ in range(numiter):
        y = _compute_y(x, ll)
        T = _tof_equation_y(x, y, 0.0, ll, M)
        d1 = _dT(x, y, T, ll)
        d2 = _ddT(x, y, T, d1, ll)
        if d2 == 0.0:
            return False, x, 0.0
        d3 = _dddT(x, y, d1, d2, ll)
        x_new = x - 2.0 * d1 * d2 / (2.0 * d2 * d2 - d1 * d3)
        if not math.isfinite(x_new):
            return False, x, 0.0
        if abs(x_new - x) < rtol:
            x = x_new
            return True, x, _tof_equation(x, 0.0, ll, M)
        x = x_new
    return False, x, 0.0


@njit(cache=True)
def _initial_guess(T, ll, M, lowpath):
    if M == 0:
        T_0 = math.acos(ll) + ll * math.sqrt(1.0 - ll * ll)
        T_1 = 2.0 * (1.0 - ll ** 3) / 3.0
        if T >= T_0:
            return (T_0 / T) ** (2.0 / 3.0) - 1.0
        elif T < T_1:
            return 2.5 * T_1 / T * (T_1 - T) / (1.0 - ll ** 5) + 1.0
        # pykep 的版本：指數 = ln2 / ln(T_0/T_1)
        return (T_0 / T) ** (math.log(2.0) / math.log(T_0 / T_1)) - 1.0
    tmp = ((M * _PI + _PI) / (8.0 * T)) ** (2.0 / 3.0)
    x_0l = (tmp - 1.0) / (tmp + 1.0)
    tmp = ((8.0 * T) / (M * _PI)) ** (2.0 / 3.0)
    x_0r = (tmp - 1.0) / (tmp + 1.0)
    if lowpath:
        return max(x_0l, x_0r)
    return min(x_0l, x_0r)


@njit(cache=True)
def _householder(x0, T0, ll, M, tol, maxiter):
    x = x0
    for _ in range(maxiter):
        if not (x > -1.0):
            return False, x
        y = _compute_y(x, ll)
        fval = _tof_equation_y(x, y, T0, ll, M)
        T = fval + T0
        d1 = _dT(x, y, T, ll)
        d2 = _ddT(x, y, T, d1, ll)
        d3 = _dddT(x, y, d1, d2, ll)
        denom = d1 * (d1 * d1 - fval * d2) + d3 * fval * fval / 6.0
        if denom == 0.0:
            return False, x
        x_new = x - fval * ((d1 * d1 - fval * d2 / 2.0) / denom)
        if not math.isfinite(x_new):
            return False, x
        if abs(x_new - x) < tol:
            return True, x_new
        x = x_new
    return False, x


@njit(cache=True)
def izzo(k, r1, r2, tof, M, prograde, lowpath, numiter, rtol):
    """解 Lambert 問題。回傳 (ok, v1, v2)。

    k: 重力參數 (km^3/s^2)；r1, r2: 位置 (km)；tof: 飛行時間 (s)；M: 完整圈數；
    prograde: 轉移方向（以 +z 為正的順行）；lowpath: 多圈時選哪一支（同 poliastro）。
    """
    v1 = np.zeros(3)
    v2 = np.zeros(3)
    if tof <= 0.0 or k <= 0.0:
        return False, v1, v2

    c = r2 - r1
    c_norm = _norm(c)
    r1_norm = _norm(r1)
    r2_norm = _norm(r2)
    if c_norm == 0.0 or r1_norm == 0.0 or r2_norm == 0.0:
        return False, v1, v2

    s = (r1_norm + r2_norm + c_norm) * 0.5
    i_r1 = r1 / r1_norm
    i_r2 = r2 / r2_norm
    i_h = _cross(i_r1, i_r2)
    h_norm = _norm(i_h)
    if h_norm < 1e-12:                       # 共線：轉移平面不確定
        return False, v1, v2
    i_h = i_h / h_norm

    ll = math.sqrt(max(0.0, 1.0 - min(1.0, c_norm / s)))
    if i_h[2] < 0.0:
        ll = -ll
        i_t1 = _cross(i_r1, i_h)
        i_t2 = _cross(i_r2, i_h)
    else:
        i_t1 = _cross(i_h, i_r1)
        i_t2 = _cross(i_h, i_r2)
    if not prograde:
        ll = -ll
        i_t1 = -i_t1
        i_t2 = -i_t2
    if abs(ll) >= 1.0:
        return False, v1, v2

    T = math.sqrt(2.0 * k / s ** 3) * tof

    # 這個 T 最多容得下幾圈
    M_max = math.floor(T / _PI)
    T_00 = math.acos(ll) + ll * math.sqrt(1.0 - ll * ll)
    if T < T_00 + M_max * _PI and M_max > 0:
        okm, _, T_min = _compute_T_min(ll, int(M_max), numiter, rtol)
        if okm and T < T_min:
            M_max -= 1
    if M > M_max:
        return False, v1, v2

    x0 = _initial_guess(T, ll, M, lowpath)
    ok, x = _householder(x0, T, ll, M, rtol, numiter)
    if not ok:
        return False, v1, v2
    y = _compute_y(x, ll)

    gamma = math.sqrt(k * s / 2.0)
    rho = (r1_norm - r2_norm) / c_norm
    sigma = math.sqrt(max(0.0, 1.0 - rho * rho))

    V_r1 = gamma * ((ll * y - x) - rho * (ll * y + x)) / r1_norm
    V_r2 = -gamma * ((ll * y - x) + rho * (ll * y + x)) / r2_norm
    V_t1 = gamma * sigma * (y + ll * x) / r1_norm
    V_t2 = gamma * sigma * (y + ll * x) / r2_norm

    v1 = V_r1 * i_r1 + V_t1 * i_t1
    v2 = V_r2 * i_r2 + V_t2 * i_t2
    if not (math.isfinite(v1[0]) and math.isfinite(v1[1]) and math.isfinite(v1[2])):
        return False, np.zeros(3), np.zeros(3)
    return True, v1, v2


@njit(cache=True)
def lambert_min_dv(k, r1, v_current, r2, tof, max_revs):
    """掃過 M=0..max_revs、兩個路徑分支、順/逆行，回傳需求 Δv 最小的解。

    回傳 (dv_km_s, v1, v2)；全部分支失敗時 dv=inf。分支政策與 Planner 的
    `MissionOptimizer._best_lambert` 相同。
    """
    best = np.inf
    best_v1 = np.zeros(3)
    best_v2 = np.zeros(3)
    for M in range(max_revs + 1):
        for branch in range(2):
            lowpath = branch == 0
            if M == 0 and not lowpath:
                continue
            for direction in range(2):
                prograde = direction == 0
                ok, v1, v2 = izzo(k, r1, r2, tof, M, prograde, lowpath, 35, 1e-10)
                if not ok:
                    continue
                d = _norm(v1 - v_current)
                if d < best:
                    best = d
                    best_v1 = v1
                    best_v2 = v2
    return best, best_v1, best_v2
