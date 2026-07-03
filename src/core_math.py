# src/core_math.py
import math
import numpy as np
from numba import njit

@njit(fastmath=True)
def fast_cross(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.array([
        a[1]*b[2] - a[2]*b[1],
        a[2]*b[0] - a[0]*b[2],
        a[0]*b[1] - a[1]*b[0]
    ], dtype=np.float64)

@njit(fastmath=True)
def fast_norm(v: np.ndarray) -> float:
    return math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)

@njit(fastmath=True)
def to_vnb_frame(r_vec: np.ndarray, v_vec: np.ndarray, dv_inertial: np.ndarray) -> np.ndarray:
    v_norm = fast_norm(v_vec)
    v_hat = v_vec / v_norm

    h = fast_cross(r_vec, v_vec)
    h_norm = fast_norm(h)
    n_hat = h / h_norm

    b_hat = fast_cross(v_hat, n_hat)

    dv_v = dv_inertial[0]*v_hat[0] + dv_inertial[1]*v_hat[1] + dv_inertial[2]*v_hat[2]
    dv_n = dv_inertial[0]*n_hat[0] + dv_inertial[1]*n_hat[1] + dv_inertial[2]*n_hat[2]
    dv_b = dv_inertial[0]*b_hat[0] + dv_inertial[1]*b_hat[1] + dv_inertial[2]*b_hat[2]
    
    return np.array([dv_v, dv_n, dv_b], dtype=np.float64)

@njit(fastmath=True)
def check_constraints(r: np.ndarray, v: np.ndarray, mu: float, min_rp: float) -> bool:
    r2 = r[0]**2 + r[1]**2 + r[2]**2
    v2 = v[0]**2 + v[1]**2 + v[2]**2
    r_mag = math.sqrt(r2)
    
    h = fast_cross(r, v)
    h2 = h[0]**2 + h[1]**2 + h[2]**2
    
    epsilon = (v2 / 2.0) - (mu / r_mag)
    e = math.sqrt(max(0.0, 1.0 + (2.0 * epsilon * h2) / (mu**2)))
    rp = h2 / (mu * (1.0 + e))
    
    return rp >= min_rp  

@njit(fastmath=True)
def compute_dv_mag(v1_req: np.ndarray, v1: np.ndarray):
    dv = v1_req - v1
    return dv, fast_norm(dv)

@njit(fastmath=True)
def fast_dynamics(t: float, state: np.ndarray, mu: float, j2: float, re: float) -> np.ndarray:
    """從原本 propagator.py 搬過來的底層動力學計算"""
    x, y, z = state[0], state[1], state[2]
    vx, vy, vz = state[3], state[4], state[5]

    r2 = x**2 + y**2 + z**2
    r_norm = r2**0.5

    mu_r3 = mu / (r_norm * r2)
    ax = -mu_r3 * x
    ay = -mu_r3 * y
    az = -mu_r3 * z

    factor = -1.5 * j2 * (mu / r2) * (re / r_norm)**2
    z2_r2_5 = 5.0 * (z / r_norm)**2
    
    ax += factor * (1.0 - z2_r2_5) * (x / r_norm)
    ay += factor * (1.0 - z2_r2_5) * (y / r_norm)
    az += factor * (3.0 - z2_r2_5) * (z / r_norm)

    out = np.empty(6, dtype=np.float64)
    out[0], out[1], out[2] = vx, vy, vz
    out[3], out[4], out[5] = ax, ay, az
    
    return out

@njit(fastmath=True)
def rk4_step(t: float, state: np.ndarray, dt: float, mu: float, j2: float, re: float) -> np.ndarray:
    """
    執行單步的 RK4 積分。
    收集 4 個測試點的斜率 (k1, k2, k3, k4)，然後做加權平均。
    """
    # 1. 取得起點斜率
    k1 = fast_dynamics(t, state, mu, j2, re)
    
    # 2. 取得中點斜率 A (用 k1 往前推半步)
    state_k2 = state + 0.5 * dt * k1
    k2 = fast_dynamics(t + 0.5 * dt, state_k2, mu, j2, re)
    
    # 3. 取得中點斜率 B (改用 k2 往前推半步)
    state_k3 = state + 0.5 * dt * k2
    k3 = fast_dynamics(t + 0.5 * dt, state_k3, mu, j2, re)
    
    # 4. 取得終點斜率 (用 k3 往前推整步)
    state_k4 = state + dt * k3
    k4 = fast_dynamics(t + dt, state_k4, mu, j2, re)
    
    # 計算加權平均並更新狀態 (中點權重較高)
    next_state = state + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)
    return next_state

@njit(fastmath=True)
def propagate_rk4(
    r0: np.ndarray, v0: np.ndarray, tof: float, dt: float, 
    mu: float, j2: float, re: float
):
    """
    純 Numba 的軌道傳播主迴圈。
    取代原本的 scipy.integrate.solve_ivp。
    """
    state = np.empty(6, dtype=np.float64)
    state[0], state[1], state[2] = r0[0], r0[1], r0[2]
    state[3], state[4], state[5] = v0[0], v0[1], v0[2]
    
    t = 0.0
    # 只要還沒抵達目標時間，就繼續往前跨步
    while t < tof:
        # 關鍵防護：確保最後一步剛好精準踩在 tof 上，不會超時
        step_size = min(dt, tof - t)
        
        state = rk4_step(t, state, step_size, mu, j2, re)
        t += step_size
        
    # 分離出位置與速度並回傳
    r_final = np.array([state[0], state[1], state[2]], dtype=np.float64)
    v_final = np.array([state[3], state[4], state[5]], dtype=np.float64)
    
    return r_final, v_final