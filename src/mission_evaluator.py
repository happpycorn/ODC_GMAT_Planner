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