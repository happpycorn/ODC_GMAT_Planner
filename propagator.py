import numpy as np
from astropy import units as u
from poliastro.twobody import Orbit
from poliastro.bodies import Earth

class OrbitPropagator:    
    @staticmethod
    def create_orbit(sma: float, ecc: float, inc: float, raan: float, aop: float, ta: float) -> Orbit:
        return Orbit.from_classical(
            attractor=Earth,
            a=u.Quantity(float(sma), u.km),
            ecc=u.Quantity(float(ecc), u.one),
            inc=u.Quantity(float(inc), u.deg),
            raan=u.Quantity(float(raan), u.deg),
            argp=u.Quantity(float(aop), u.deg),
            nu=u.Quantity(float(ta), u.deg)  # True Anomaly
        )

    @staticmethod
    def get_future_state(orbit: Orbit, delta_t_sec: float):
        future_orbit = orbit.propagate(float(delta_t_sec) * u.s)
        
        r_vector = future_orbit.r.to_value(u.km)
        v_vector = future_orbit.v.to_value(u.km / u.s)
        
        return r_vector, v_vector

# ==========================================
# 測試區塊 (SITL 軟體迴圈測試)
# ==========================================
if __name__ == "__main__":
    orbit_A = OrbitPropagator.create_orbit(
        sma=7000.0, 
        ecc=0.0, 
        inc=30.0, 
        raan=45.0, 
        aop=0.0, 
        ta=120.0
    )
    
    orbit_B = OrbitPropagator.create_orbit(
        sma=6800.0, 
        ecc=0.0, 
        inc=30.0, 
        raan=45.0, 
        aop=0.0, 
        ta=0.0
    )
    
    print("=== 模組一測試開始 ===")

    r_B0, v_B0 = OrbitPropagator.get_future_state(orbit_B, 0)
    print(f"[t=0] 飛船 B 起始位置 (km): {np.round(r_B0, 2)}")
    print(f"[t=0] 飛船 B 起始速度 (km/s): {np.round(v_B0, 2)}\n")
    
    tof_seconds = 3600.0
    r_A_future, v_A_future = OrbitPropagator.get_future_state(orbit_A, tof_seconds)
    print(f"[t={tof_seconds}s] 飛船 A 未來位置 (km): {np.round(r_A_future, 2)}")