import numpy as np
from astropy import units as u
from poliastro.bodies import Earth
from numba import njit
from typing import Tuple
from poliastro.twobody import Orbit
from poliastro.core.propagation import farnocchia

from scipy.integrate import solve_ivp

@njit(fastmath=True)
def _fast_dynamics(t: float, state: np.ndarray, mu: float, j2: float, re: float) -> np.ndarray:
    """
    Numba JIT 加速的軌道動力學方程。
    將引力與 J2 計算合併，並避免建立多餘的暫存陣列。
    """
    # 解包狀態 (x, y, z, vx, vy, vz)
    x, y, z = state[0], state[1], state[2]
    vx, vy, vz = state[3], state[4], state[5]

    # 計算距離的平方與絕對值 (展開計算比 np.linalg.norm 更快)
    r2 = x**2 + y**2 + z**2
    r_norm = r2**0.5

    # --- 1. 兩體引力加速度 ---
    mu_r3 = mu / (r_norm * r2)
    ax = -mu_r3 * x
    ay = -mu_r3 * y
    az = -mu_r3 * z

    # --- 2. J2 攝動加速度 ---
    factor = -1.5 * j2 * (mu / r2) * (re / r_norm)**2
    z2_r2_5 = 5.0 * (z / r_norm)**2
    
    ax += factor * (1.0 - z2_r2_5) * (x / r_norm)
    ay += factor * (1.0 - z2_r2_5) * (y / r_norm)
    az += factor * (3.0 - z2_r2_5) * (z / r_norm)

    # --- 3. 組合回傳結果 ---
    # Numba 中預先配置 empty 陣列比 np.concatenate 快非常多
    out = np.empty(6, dtype=np.float64)
    out[0], out[1], out[2] = vx, vy, vz
    out[3], out[4], out[5] = ax, ay, az
    
    return out

def get_r0_v0(sma: float, ecc: float, inc: float, raan: float, aop: float, ta: float):
    initial_orbit = Orbit.from_classical(
        attractor=Earth,
        a=u.Quantity(float(sma), u.km),
        ecc=u.Quantity(float(ecc), u.one),
        inc=u.Quantity(float(inc), u.deg),
        raan=u.Quantity(float(raan), u.deg),
        argp=u.Quantity(float(aop), u.deg),
        nu=u.Quantity(float(ta), u.deg)
    )
    
    r0 = initial_orbit.r.to_value(u.km).astype(np.float64)
    v0 = initial_orbit.v.to_value(u.km / u.s).astype(np.float64)

    return r0, v0   

@njit(fastmath=True)
def propagate(
    k: float, r0: np.ndarray, v0: np.ndarray, tof: float
) -> Tuple[np.ndarray, np.ndarray]:
    """
    執行軌道傳播 (Numba 加速版)
    """
    state0 = np.empty(6, dtype=np.float64)
    state0[:3] = r0
    state0[3:] = v0
    t_span = (0.0, tof)
    
    # 預設的地球常數 (單位：公里)
    j2_val = 1.08262668e-3
    re_val = 6378.137
    
    sol = solve_ivp(
        fun=_fast_dynamics,             # 直接傳入 JIT 函數
        t_span=t_span,
        y0=state0,
        args=(k, j2_val, re_val),       # 用 args 傳參數，避免使用 lambda
        method='DOP853',                # 強烈建議：高精度軌道換成 DOP853 會比 RK45 快好幾倍
        rtol=1e-9, 
        atol=1e-9
    )
    
    final_state = sol.y[:, -1]
    r_final = final_state[:3]
    v_final = final_state[3:]
    
    return r_final, v_final

if __name__ == "__main__":
    import time

    mu = Earth.k.to_value((u.km ** 3) / (u.s ** 2)) # type: ignore
    
    params = {
        "sma": 7000.0, "ecc": 0.0, "inc": 30.0, 
        "raan": 45.0, "aop": 0.0, "ta": 120.0
    }
    
    print("=== 初始化高階軌道模型 (只做一次) ===")
    r0, v0 = get_r0_v0(**params)
    
    print("\n=== 開始極速推進測試 ===")
    tof = 3600.0
    
    start_time = time.perf_counter()
    
    for _ in range(10000):r_new, v_new = farnocchia(mu, r0, v0, tof)
        
    end_time = time.perf_counter()
    
    print(f"[t={tof}s] 未來位置 (km): {np.round(r_new, 2)}")
    print(f"[t={tof}s] 未來速度 (km/s): {np.round(v_new, 2)}")
    print(f"✅ 10,000 次運算耗時: {(end_time - start_time) * 1000:.2f} 毫秒")