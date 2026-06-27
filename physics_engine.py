import numpy as np
from astropy import units as u
from poliastro.iod import izzo
from poliastro.bodies import Earth
from poliastro.twobody import Orbit

class PhysicsEngine:
    """模組二：負責求解蘭伯特問題與物理防呆檢查"""
    
    EARTH_RADIUS = Earth.R.to_value(u.km)
    SAFE_ALTITUDE = 100.0
    MIN_PERIAPSIS = EARTH_RADIUS + SAFE_ALTITUDE
    MAX_DV = 1.5

    @staticmethod
    def solve_lambert(r1: np.ndarray, v1: np.ndarray, r2: np.ndarray, tof_sec: float):
        r1_u = u.Quantity(r1, u.km)
        r2_u = u.Quantity(r2, u.km)
        tof_u = u.Quantity(float(tof_sec), u.s)
        
        v1_req_u, v2_req_u = izzo.lambert(Earth.k, r1_u, r2_u, tof_u)
        
        v1_req = v1_req_u.to_value(u.km / u.s)
        v2_req = v2_req_u.to_value(u.km / u.s)
        
        delta_v1 = v1_req - v1
        dv1_mag = float(np.linalg.norm(delta_v1))
        
        return v1_req, v2_req, delta_v1, dv1_mag

    @staticmethod
    def check_constraints(r1: np.ndarray, v1_req: np.ndarray, dv1_mag: float) -> tuple[bool, str]:
        if dv1_mag > PhysicsEngine.MAX_DV:
            return False, f"違規：Delta V ({dv1_mag*1000:.1f} m/s) 超出 1500 m/s 上限！"

        transfer_orbit = Orbit.from_vectors(
            Earth, 
            u.Quantity(r1, u.km),
            u.Quantity(v1_req, u.km / u.s),
        )
        rp = transfer_orbit.r_p.to_value(u.km)
        
        if rp < PhysicsEngine.MIN_PERIAPSIS:
            return False, f"危險：轉移軌道近地點 ({rp:.1f} km) 穿透地表，發生墜毀！"

        return True, "安全：這是一條完美合法的高速公路"

# ==========================================
# 測試區塊 (結合模組一的資料)
# ==========================================
if __name__ == "__main__":
    from propagator import OrbitPropagator
    
    orbit_A = OrbitPropagator.create_orbit(7000.0, 0.0, 30.0, 45.0, 0.0, 120.0)
    orbit_B = OrbitPropagator.create_orbit(6800.0, 0.0, 30.0, 45.0, 0.0, 0.0)
    
    r_B0, v_B0 = OrbitPropagator.get_future_state(orbit_B, 0)
    
    tof_test = 3600.0
    r_A_future, _ = OrbitPropagator.get_future_state(orbit_A, tof_test)
    
    print(f"=== 測試飛行時間: {tof_test} 秒 ===")

    v1_req, v2_req, dv1_vec, dv1_mag = PhysicsEngine.solve_lambert(r_B0, v_B0, r_A_future, tof_test)
    
    print(f"所需 Delta-V 向量 (km/s): {np.round(dv1_vec, 3)}")
    print(f"所需 Delta-V 大小 (m/s): {dv1_mag * 1000:.1f}")
    
    is_safe, msg = PhysicsEngine.check_constraints(r_B0, v1_req, dv1_mag)
    print(f"安檢結果: {msg}")