import numpy as np
from astropy import units as u
from poliastro.bodies import Earth
from poliastro.twobody import Orbit
from poliastro.core.propagation import farnocchia

from scipy.integrate import solve_ivp

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
    
    @staticmethod
    def compute_gravity(r_vec, mu):
        r_norm = np.linalg.norm(r_vec)
        a_2body = -mu / (r_norm**3) * r_vec
        return a_2body

    @staticmethod
    def compute_j2(r_vec, j2, mu, re):
        x, y, z = r_vec
        r_norm = np.linalg.norm(r_vec)

        factor = - (3/2) * j2 * (mu / r_norm**2) * (re / r_norm)**2
        
        ax = factor * (1 - 5 * (z / r_norm)**2) * (x / r_norm)
        ay = factor * (1 - 5 * (z / r_norm)**2) * (y / r_norm)
        az = factor * (3 - 5 * (z / r_norm)**2) * (z / r_norm)
        
        return np.array([ax, ay, az])

    @staticmethod
    def dynamics(t, state, j2=1.08262668e-3, mu=3.986004418e14, re=6378137.0):
        """ODE 的導數函數: 接收狀態 [r, v]，回傳變化率 [v, a]"""
        r_vec = state[0:3]
        v_vec = state[3:6]

        a_total = OrbitPropagator.compute_gravity(r_vec, mu) + OrbitPropagator.compute_j2(r_vec, j2, mu, re)
        
        return np.concatenate((v_vec, a_total))

    @staticmethod
    def propagate(state0, t_span, dt_eval):
        """
        執行軌道傳播
        :param state0: 初始狀態陣列 [x, y, z, vx, vy, vz]
        :param t_span: 積分時間區間 (t_start, t_end)
        :param dt_eval: 星曆表輸出的時間間隔 (秒)
        """
        t_eval = np.arange(t_span[0], t_span[1] + dt_eval, dt_eval)
        
        # 呼叫強大的 RK45 求解器
        sol = solve_ivp(
            fun=OrbitPropagator.dynamics,
            t_span=t_span,
            y0=state0,
            t_eval=t_eval,
            method='RK45',
            rtol=1e-9,  # 相對誤差容忍度 (軌道計算建議設 1e-9 或更小)
            atol=1e-9   # 絕對誤差容忍度
        )
        
        # sol.t 是時間陣列，sol.y.T 是形狀為 (資料筆數, 6) 的狀態矩陣
        return sol.t, sol.y.T

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