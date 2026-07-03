import numpy as np
from typing import Tuple
from astropy import units as u
from poliastro.bodies import Earth
from poliastro.twobody import Orbit
from src.core_math import propagate_rk4

J2_VAL = 1.08262668e-3
RE_VAL = 6378.137

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

def propagate(
    k: float, r0: np.ndarray, v0: np.ndarray, tof: float, use_j2: bool = True
) -> Tuple[np.ndarray, np.ndarray]:
    """
    改用純 Numba RK4 引擎的軌道傳播器。
    """
    active_j2 = J2_VAL if use_j2 else 0.0
    
    # 設定時間步長。60秒(1分鐘)是低軌道(LEO)非常經典且足夠精準的步長。
    dt = 60.0 
    
    # 直接呼叫 core_math 裡面的純數學迴圈
    r_final, v_final = propagate_rk4(r0, v0, tof, dt, k, active_j2, RE_VAL)
    
    return r_final, v_final

# ==========================================
# 測試區塊 
# ==========================================
if __name__ == "__main__":
    import time

    mu = Earth.k.to_value((u.km ** 3) / (u.s ** 2)) # type: ignore
    
    params = {
        "sma": 7000.0, "ecc": 0.0, "inc": 30.0, 
        "raan": 45.0, "aop": 0.0, "ta": 120.0
    }
    
    print("=== 初始化高階軌道模型 ===")
    r0, v0 = get_r0_v0(**params)
    tof = 3600.0
    
    print("\n=== 啟動傳播器測試 (JIT + SciPy DOP853) ===")
    
    # 暖機 (讓 Numba 先編譯一次)
    propagate(mu, r0, v0, tof, use_j2=True)
    
    start_time = time.perf_counter()
    for _ in range(100):
        r_new, v_new = propagate(mu, r0, v0, tof, use_j2=True)
    end_time = time.perf_counter()
    
    print(f"[t={tof}s] 未來位置 (km): {np.round(r_new, 2)}")
    print(f"[t={tof}s] 未來速度 (km/s): {np.round(v_new, 2)}")
    print(f"✅ 100 次含 J2 運算耗時: {(end_time - start_time) * 1000:.2f} 毫秒")