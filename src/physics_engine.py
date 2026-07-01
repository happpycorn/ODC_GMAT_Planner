import numpy as np
from poliastro.core.iod import izzo

class PhysicsEngine:    
    @staticmethod
    def solve_lambert(mu, r1, v1, r2, tof):
        v1_req, v2_req = izzo(
            mu, r1, r2, tof,
            M=0, prograde=True, lowpath=True, numiter=35, rtol=1e-8
        )
        
        dv1 = v1_req - v1
        dv1_mag = np.linalg.norm(dv1)
        
        return v1_req, v2_req, dv1, dv1_mag

    @staticmethod
    def check_constraints(r: np.ndarray, v: np.ndarray, mu: float, min_rp: float) -> bool:
        h_vec = np.cross(r, v)
        h2 = np.sum(h_vec**2)
        
        r_mag = np.linalg.norm(r)
        v2 = np.sum(v**2)
        epsilon = (v2 / 2.0) - (mu / r_mag)
        
        e = np.sqrt(1.0 + (2.0 * epsilon * h2) / (mu**2))

        rp = h2 / (mu * (1.0 + e))

        return rp >= min_rp
    
    @staticmethod
    def to_vnb_frame(r_vec, v_vec, dv_inertial):
        v_hat = v_vec / np.linalg.norm(v_vec)
        h_vec = np.cross(r_vec, v_vec)
        n_hat = h_vec / np.linalg.norm(h_vec)
        b_hat = np.cross(v_hat, n_hat)
        
        T_mat = np.array([v_hat, n_hat, b_hat])
        
        dv_vnb = T_mat @ dv_inertial
        return dv_vnb

# ==========================================
# 測試區塊 (結合模組一的資料)
# ==========================================
if __name__ == "__main__":
    from astropy import units as u
    from poliastro.bodies import Earth
    from src.propagator import OrbitPropagator
    from poliastro.core.propagation import farnocchia
    from poliastro.twobody import Orbit
    
    mu = Earth.k.to_value((u.km ** 3) / (u.s ** 2)) # type: ignore
    A_r0, A_v0 = OrbitPropagator.get_r0_v0(9000.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    B_r0, B_v0 = OrbitPropagator.get_r0_v0(7500.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    
    tof_test = 3600.0
    r_A_future, _ = farnocchia(mu, A_r0, A_v0, tof_test)
    
    print(f"=== 測試飛行時間: {tof_test} 秒 ===")

    v1_req, v2_req, dv1_vec, dv1_mag = PhysicsEngine.solve_lambert(mu, B_r0, B_v0, r_A_future, tof_test)
    
    print(f"所需 Delta-V 向量 (km/s): {np.round(dv1_vec, 3)}")
    print(f"所需 Delta-V 大小 (m/s): {dv1_mag * 1000:.1f}")

    EARTH_RADIUS = Earth.R.to_value(u.km)
    SAFE_ALTITUDE = 100.0
    MIN_PERIAPSIS = EARTH_RADIUS + SAFE_ALTITUDE
    
    is_safe = PhysicsEngine.check_constraints(B_r0, B_v0+dv1_vec, mu, MIN_PERIAPSIS)
    print(f"安檢結果: {is_safe}")

    v1_req, v2_req, _, _ = PhysicsEngine.solve_lambert(mu, B_r0, B_v0, r_A_future, tof_test)
    
    # 2. 計算 Lambert 軌道的比能 (Specific Orbital Energy)
    # 能量公式: epsilon = v^2 / 2 - mu / r
    r_mag = np.linalg.norm(B_r0)
    v1_req_mag = np.linalg.norm(v1_req)
    eps_lambert = (v1_req_mag**2 / 2.0) - (mu / r_mag)
    
    # 3. 使用 poliastro 建立同一個軌道進行比對
    # 這樣可以直接利用 poliastro 內建的方法算能量
    orbit_lambert = Orbit.from_vectors(Earth, B_r0 * u.km, v1_req * u.km / u.s)
    
    print(f"\n--- 能量一致性檢查 ---")
    print(f"Lambert 算出的比能: {eps_lambert:.4f} km^2/s^2")
    print(f"Poliastro 軌道比能: {orbit_lambert.energy.to_value(u.km**2 / u.s**2):.4f} km^2/s^2") # type: ignore
    
    # 4. 關鍵驗證：檢查軌道是否在 tof 後確實抵達 r2 (r_A_future)
    # 傳播 Lambert 軌道到 tof 時間點
    orbit_after_tof = orbit_lambert.propagate(tof_test * u.s)
    r_final = orbit_after_tof.r.to_value(u.km)
    
    error = np.linalg.norm(r_final - r_A_future)
    print(f"攔截位置誤差 (km): {error:.6f}")
    
    if error < 1e-3:
        print("✅ 驗證成功：Lambert 求解器產出的軌道符合物理定律且精確抵達目標。")
    else:
        print("❌ 驗證失敗：軌道傳播誤差過大，請檢查 mu 值或單位。")