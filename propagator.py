import numpy as np
from astropy import units as u
from poliastro.bodies import Earth
from poliastro.twobody import Orbit
from poliastro.core.propagation import farnocchia

class OrbitPropagator:
    @staticmethod
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

if __name__ == "__main__":
    import time

    mu = Earth.k.to_value((u.km ** 3) / (u.s ** 2)) # type: ignore
    
    params = {
        "sma": 7000.0, "ecc": 0.0, "inc": 30.0, 
        "raan": 45.0, "aop": 0.0, "ta": 120.0
    }
    
    print("=== 初始化高階軌道模型 (只做一次) ===")
    r0, v0 = OrbitPropagator.get_r0_v0(**params)
    
    print("\n=== 開始極速推進測試 ===")
    tof = 3600.0
    
    start_time = time.perf_counter()
    
    for _ in range(10000):r_new, v_new = farnocchia(mu, r0, v0, tof)
        
    end_time = time.perf_counter()
    
    print(f"[t={tof}s] 未來位置 (km): {np.round(r_new, 2)}")
    print(f"[t={tof}s] 未來速度 (km/s): {np.round(v_new, 2)}")
    print(f"✅ 10,000 次運算耗時: {(end_time - start_time) * 1000:.2f} 毫秒")