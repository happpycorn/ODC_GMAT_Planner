"""座標系轉換：RSW(LVLH/Hill)、VNB(GMAT)、以及 r,v -> 古典六根數。

* RSW（= RIC = LVLH 的一種慣例）：R 徑向朝外、S 沿軌道前進方向（在軌道面內、垂直 R）、
  W 軌道角動量方向。追逃觀測與 RL action 都用這個座標，讓策略對軌道姿態旋轉不變。
* VNB（GMAT ImpulsiveBurn 的 Axes=VNB）：V 沿速度、N 沿角動量、B = V x N。
  與 physics.core_math.to_vnb_frame 的定義一致，當天輸入 GMAT 指令用。
"""
import math

import numpy as np
from numba import njit

from physics.propagator import EARTH_MU


@njit(cache=True)
def rsw_basis(r, v):
    """回傳 3x3 矩陣，列為 R、S、W 單位向量（ECI 表示）。eci->rsw: B @ x；rsw->eci: B.T @ x。"""
    rn = math.sqrt(r[0] * r[0] + r[1] * r[1] + r[2] * r[2])
    R = r / rn
    h = np.array([r[1] * v[2] - r[2] * v[1], r[2] * v[0] - r[0] * v[2], r[0] * v[1] - r[1] * v[0]])
    hn = math.sqrt(h[0] * h[0] + h[1] * h[1] + h[2] * h[2])
    W = h / hn
    S = np.array([W[1] * R[2] - W[2] * R[1], W[2] * R[0] - W[0] * R[2], W[0] * R[1] - W[1] * R[0]])
    B = np.empty((3, 3))
    B[0] = R
    B[1] = S
    B[2] = W
    return B


@njit(cache=True)
def vnb_basis(r, v):
    """回傳 3x3 矩陣，列為 V、N、B 單位向量（ECI 表示）。"""
    vn = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    V = v / vn
    h = np.array([r[1] * v[2] - r[2] * v[1], r[2] * v[0] - r[0] * v[2], r[0] * v[1] - r[1] * v[0]])
    hn = math.sqrt(h[0] * h[0] + h[1] * h[1] + h[2] * h[2])
    N = h / hn
    Bv = np.array([V[1] * N[2] - V[2] * N[1], V[2] * N[0] - V[0] * N[2], V[0] * N[1] - V[1] * N[0]])
    M = np.empty((3, 3))
    M[0] = V
    M[1] = N
    M[2] = Bv
    return M


def eci_to_rsw(vec, r, v):
    return rsw_basis(r, v) @ np.asarray(vec, dtype=np.float64)


def rsw_to_eci(vec, r, v):
    return rsw_basis(r, v).T @ np.asarray(vec, dtype=np.float64)


def eci_to_vnb(vec, r, v):
    return vnb_basis(r, v) @ np.asarray(vec, dtype=np.float64)


def vnb_to_eci(vec, r, v):
    return vnb_basis(r, v).T @ np.asarray(vec, dtype=np.float64)


def relative_rsw(r_ref, v_ref, r_other, v_other):
    """other 相對 ref 的位置/速度，表示在 ref 的 RSW 座標（旋轉座標系的科氏項不扣，
    是「慣性相對速度投影到 RSW」；觀測特徵用，不做 CW 動力學）。"""
    B = rsw_basis(r_ref, v_ref)
    return B @ (r_other - r_ref), B @ (v_other - v_ref)


def rv2coe(r, v, mu=EARTH_MU):
    """ECI r,v -> 古典六根數 dict（sma km, ecc, inc/raan/aop/ta 度），與 get_r0_v0 互逆。

    圓軌道（ecc≈0）時 aop 定為 0、ta 從升交點量起；赤道軌道（inc≈0）時 raan 定為 0、
    aop 從 x 軸量起——與 GMAT 的退化處理一致到「位置/速度重建後相同」的程度。
    """
    r = np.asarray(r, dtype=np.float64)
    v = np.asarray(v, dtype=np.float64)
    rn = np.linalg.norm(r)
    vn2 = float(v @ v)
    h = np.cross(r, v)
    hn = np.linalg.norm(h)
    n = np.cross([0.0, 0.0, 1.0], h)
    nn = np.linalg.norm(n)
    e_vec = ((vn2 - mu / rn) * r - (r @ v) * v) / mu
    ecc = float(np.linalg.norm(e_vec))
    energy = vn2 / 2.0 - mu / rn
    sma = -mu / (2.0 * energy) if abs(energy) > 1e-12 else np.inf
    inc = math.degrees(math.acos(np.clip(h[2] / hn, -1.0, 1.0)))

    eps = 1e-10
    if nn > eps:
        raan = math.degrees(math.atan2(n[1], n[0])) % 360.0
    else:
        raan = 0.0
        n = np.array([1.0, 0.0, 0.0])
        nn = 1.0
    if ecc > eps:
        aop = math.degrees(math.acos(np.clip((n @ e_vec) / (nn * ecc), -1.0, 1.0)))
        if (e_vec[2] < 0.0 and inc > 1e-8) or (inc <= 1e-8 and np.cross(n, e_vec)[2] * np.sign(h[2]) < 0.0):
            aop = 360.0 - aop
        ta = math.degrees(math.acos(np.clip((e_vec @ r) / (ecc * rn), -1.0, 1.0)))
        if r @ v < 0.0:
            ta = 360.0 - ta
    else:
        aop = 0.0
        ta = math.degrees(math.acos(np.clip((n @ r) / (nn * rn), -1.0, 1.0)))
        # 以角動量方向判斷在升交點之後還是之前
        if np.cross(n, r) @ h < 0.0:
            ta = 360.0 - ta
    return {"sma": float(sma), "ecc": ecc, "inc": inc, "raan": raan, "aop": aop % 360.0, "ta": ta % 360.0}
