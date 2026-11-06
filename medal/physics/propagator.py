"""高精度軌道傳播器（DRL env 用的物理引擎）。

本檔是 `ODC_GMAT_Planner/src/propagator.py` 的 **poliastro-free 改寫版**——`propagate()`
的包裝與相依常數跟 Planner 逐字對齊，唯一差別是把 `get_r0_v0()`（六根數→Cartesian）
從 poliastro/astropy 換成自帶的純 numpy 實作，理由見 physics/PROVENANCE.md。

`propagate()` 走的引擎是 `core_math.propagate_dop853`（8 階 Dormand-Prince，與 GMAT
交叉驗證到公尺級），完全不需要 poliastro。
"""
import math
import numpy as np
from typing import Tuple
from numba import njit

from physics.core_math import propagate_dop853

# --- 與 ODC_GMAT_Planner/src/propagator.py 對齊的常數（JGM2.cof 反算）---
J2_VAL = 1.08262668e-3
J3_VAL = -2.5323078e-6
J4_VAL = -1.62042999e-6
RE_VAL = 6378.137  # 地球赤道半徑 (km)

# 地球重力參數 mu (km^3/s^2)。Planner 的 get_r0_v0 用 poliastro 的 Earth.k =
# 398600.4418；這裡沿用同一個數字，好讓本 env 的傳播結果與 Planner 的 GMAT 驗證
# 結果對得起來（GMAT JGM2 內部值 398600.4415，差在公尺以下）。
EARTH_MU = 398600.4418


def get_r0_v0(sma: float, ecc: float, inc: float, raan: float, aop: float, ta: float,
              mu: float = EARTH_MU) -> Tuple[np.ndarray, np.ndarray]:
    """古典軌道六根數 → ECI 慣性系的位置/速度 (km, km/s)。

    標準 perifocal(PQW)→ECI 的 3-1-3 (Rz(raan)·Rx(inc)·Rz(aop)) 轉換，與 poliastro
    `Orbit.from_classical` 的慣例一致。角度單位：度。橢圓/圓 (0<=ecc<1, sma>0) 與
    雙曲線 (ecc>1, sma<0) 都成立，因為 p=a(1-e^2) 對兩者都是正值。
    """
    inc_r = math.radians(inc)
    raan_r = math.radians(raan)
    aop_r = math.radians(aop)
    ta_r = math.radians(ta)

    p = sma * (1.0 - ecc * ecc)          # semi-latus rectum
    if p <= 0.0:
        raise ValueError(f"非法軌道：semi-latus rectum p={p} <= 0 (sma={sma}, ecc={ecc})")

    cos_ta = math.cos(ta_r)
    sin_ta = math.sin(ta_r)
    r_mag = p / (1.0 + ecc * cos_ta)

    # perifocal (PQW) 座標
    r_pqw = np.array([r_mag * cos_ta, r_mag * sin_ta, 0.0], dtype=np.float64)
    sqrt_mu_p = math.sqrt(mu / p)
    v_pqw = np.array([-sqrt_mu_p * sin_ta, sqrt_mu_p * (ecc + cos_ta), 0.0], dtype=np.float64)

    # PQW → ECI 旋轉矩陣 R = Rz(raan) Rx(inc) Rz(aop)
    cO, sO = math.cos(raan_r), math.sin(raan_r)
    ci, si = math.cos(inc_r), math.sin(inc_r)
    cw, sw = math.cos(aop_r), math.sin(aop_r)

    R = np.array([
        [cO * cw - sO * sw * ci, -cO * sw - sO * cw * ci,  sO * si],
        [sO * cw + cO * sw * ci, -sO * sw + cO * cw * ci, -cO * si],
        [sw * si,                 cw * si,                  ci],
    ], dtype=np.float64)

    r0 = R @ r_pqw
    v0 = R @ v_pqw
    return r0, v0


@njit(fastmath=True)
def propagate(
    k: float, r0: np.ndarray, v0: np.ndarray, tof: float, gravity_degree: int = 2
) -> Tuple[np.ndarray, np.ndarray]:
    """DOP853 自適應步長軌道傳播器（與 Planner 的 propagate() 同一份包裝）。

    gravity_degree: 0=純點質量, 2=J2, 3=J2+J3, 4=J2+J3+J4。
    """
    active_j2 = J2_VAL if gravity_degree >= 2 else 0.0
    active_j3 = J3_VAL if gravity_degree >= 3 else 0.0
    active_j4 = J4_VAL if gravity_degree >= 4 else 0.0

    dt0 = 60.0  # 初始步長猜測；自適應積分器會自己調整
    r_final, v_final = propagate_dop853(r0, v0, tof, dt0, k, active_j2, active_j3, active_j4, RE_VAL)
    return r_final, v_final


def orbital_period(sma: float, mu: float = EARTH_MU) -> float:
    """封閉軌道週期 (秒)。sma<=0（雙曲線/拋物線）沒有週期，回傳 inf。"""
    if sma <= 0.0:
        return float("inf")
    return 2.0 * math.pi * math.sqrt(sma ** 3 / mu)
