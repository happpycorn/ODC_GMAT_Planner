import numpy as np

from astropy import units as u
from poliastro.bodies import Earth
from scipy.optimize import minimize
from scipy.optimize import differential_evolution

from propagator import OrbitPropagator
from physics_engine import PhysicsEngine as PE
from scorer import CompetitionScorer
from poliastro.core.propagation import farnocchia

class MissionOptimizer:
    MU = Earth.k.to_value((u.km ** 3) / (u.s ** 2)) # type: ignore
    MIN_PERIAPSIS = Earth.R.to_value(u.km) + 100.0
    MAX_DV = 1.5
    MIN_COAST_TIME = 100.0

    def __init__(self, config):
        self.A_r0, self.A_v0 = OrbitPropagator.get_r0_v0(
            config["orbit_A"]["SMA"], config["orbit_A"]["ECC"], config["orbit_A"]["INC"],
            config["orbit_A"]["RAAN"], config["orbit_A"]["AOP"], config["orbit_A"]["TA"],
        )
        self.B_r0, self.B_v0 = OrbitPropagator.get_r0_v0(
            config["orbit_B"]["SMA"], config["orbit_B"]["ECC"], config["orbit_B"]["INC"],
            config["orbit_B"]["RAAN"], config["orbit_B"]["AOP"], config["orbit_B"]["TA"],
        )
        
        self.max_burns = config["optimization"]["MAX_BURNS"]
        self.maxiter = config["optimization"]["MAXITER"]
        self.popsize = config["optimization"]["POPSIZE"]
        self.num_threads = config["optimization"]["NUM_THREADS"]
        self.tol = config["optimization"]["TOL"]

        self.Ta_sec = 2.0 * np.pi * np.sqrt(config["orbit_A"]["SMA"]**3 / self.MU)
        self.T_max = 4.0 * self.Ta_sec

    def decode_params(self, x):
        params = {}
        params["num_burns"] = int(np.clip(round(x[0]), 1, self.max_burns))
        params["t_wait"] = x[1]
        
        current_time = params["t_wait"]
        idx = 2
        
        for i in range(1, params["num_burns"]):
            params[f"b{i}_dv_x"] = x[idx]
            params[f"b{i}_dv_y"] = x[idx+1]
            params[f"b{i}_dv_z"] = x[idx+2]
            coast_frac = x[idx+3]
            idx += 4

            max_coast = self.T_max - current_time - self.MIN_COAST_TIME
            t_coast = self.MIN_COAST_TIME + coast_frac * (max_coast - self.MIN_COAST_TIME) if max_coast > self.MIN_COAST_TIME else self.MIN_COAST_TIME
            params[f"b{i}_t_coast"] = t_coast
            current_time += t_coast
            
        max_final = self.T_max - current_time
        final_leg_frac = x[-1]
        t_final_leg = self.MIN_COAST_TIME + final_leg_frac * (max_final - self.MIN_COAST_TIME) if max_final > self.MIN_COAST_TIME else self.MIN_COAST_TIME
        params["t_final_leg"] = t_final_leg
        
        return params
    
    def objective(self, x) -> float:
        num_burns = int(np.clip(round(x[0]), 1, self.max_burns))
        current_time = x[1]
        
        penalty_count = 0
        total_dv = 0.0
        r_current, v_current = farnocchia(self.MU, self.B_r0, self.B_v0, current_time)

        idx = 2
        for i in range(1, num_burns):
            dv_vec = x[idx:idx+3]
            coast_frac = x[idx+3]
            idx += 4

            dv_mag = np.linalg.norm(dv_vec)
            total_dv += dv_mag
            if dv_mag > self.MAX_DV: penalty_count += 1

            v_current_new = v_current + dv_vec

            if not PE.check_constraints(r_current, v_current_new, self.MU, self.MIN_PERIAPSIS):
                return 0.0

            max_coast = self.T_max - current_time - self.MIN_COAST_TIME
            if max_coast <= self.MIN_COAST_TIME: return 0.0 

            t_coast = self.MIN_COAST_TIME + coast_frac * (max_coast - self.MIN_COAST_TIME)
            current_time += t_coast
            
            r_current, v_current = farnocchia(self.MU, r_current, v_current_new, t_coast)

        max_final = self.T_max - current_time
        if max_final <= self.MIN_COAST_TIME: return 0.0
        
        final_leg_frac = x[-1]
        t_final_leg = self.MIN_COAST_TIME + final_leg_frac * (max_final - self.MIN_COAST_TIME)
        
        intercept_time = current_time + t_final_leg
        
        r_a_target, _ = farnocchia(self.MU, self.A_r0, self.A_v0, intercept_time)

        v_req, _, _, dv_final_mag = PE.solve_lambert(self.MU, r_current, v_current, r_a_target, t_final_leg)
        
        total_dv += dv_final_mag
        if dv_final_mag > self.MAX_DV: penalty_count += 1

        if not PE.check_constraints(r_current, v_req, self.MU, self.MIN_PERIAPSIS):
            return 0.0

        score = CompetitionScorer.calculate_score(
            min_distance_km=0.0, 
            total_time_sec=intercept_time, 
            total_dv_mps=float(total_dv * 1000.0), 
            penalty_count=penalty_count
        )

        return -score
    
    def run_study(self):
        print(f"🚀 啟動 Differential Evolution 軌道最佳化...")
        print(f"最大推進次數: {self.max_burns} | 最大迭代次數: {self.maxiter} | 族群大小: {self.popsize}")

        bounds = [
            (1.0, self.max_burns + 0.49),
            (0.0, self.Ta_sec * 0.5)
        ]
        
        for _ in range(self.max_burns - 1):
            bounds.extend([
                (-1.5, 1.5), (-1.5, 1.5), (-1.5, 1.5),
                (0.0, 1.0)
            ])
            
        bounds.append((0.0, 1.0))

        result = differential_evolution(
            self.objective, bounds, maxiter=self.maxiter, popsize=self.popsize, 
            workers=self.num_threads, disp=True, updating='deferred',
            polish=True,
            tol=self.tol,
        )

        if result.fun > 0.0:
            print("❌ 最佳化失敗：所有的嘗試都撞毀或超時了，沒有有效的軌道可以回放。")
            return

        best_params = self.decode_params(result.x)

        burns, times = self.replay_mission(best_params)

        return burns, times

    def replay_mission(self, best_params):
        print("\n📝 --- 任務執行清單 (Mission Plan) ---")
        penalty_count = 0
        total_dv = 0.0

        burns = []
        times = [0]
        
        num_burns = int(best_params["num_burns"])
        current_time = best_params["t_wait"]
        r_current, v_current = farnocchia(self.MU, self.B_r0, self.B_v0, current_time)
        
        print(f"任務開始後等待: {current_time:.1f} 秒")

        for i in range(1, num_burns):
            dv_vec = np.array([best_params[f"b{i}_dv_x"], best_params[f"b{i}_dv_y"], best_params[f"b{i}_dv_z"]])
            dv_mag = np.linalg.norm(dv_vec)
            dv_vnb = PE.to_vnb_frame(r_current, v_current, dv_vec)
            
            print(f"  [點火 {i}] 時間: {current_time:.1f}s | 推力向量: {np.round(dv_vnb, 3)} km/s | 大小: {dv_mag*1000:.1f} m/s")

            burns.append(dv_vnb)
            times.append(current_time)
            
            total_dv += dv_mag
            if dv_mag > self.MAX_DV: penalty_count += 1
            
            t_coast = best_params[f"b{i}_t_coast"]
            current_time += t_coast
            v_current = v_current + dv_vec
            r_current, v_current = farnocchia(self.MU, r_current, v_current, t_coast)

        t_final_leg = best_params["t_final_leg"]
        intercept_time = current_time + t_final_leg
        r_a_target, _ = farnocchia(self.MU, self.A_r0, self.A_v0, intercept_time)
        
        _, _, dv_final_vec, dv_final_mag = PE.solve_lambert(self.MU, r_current, v_current, r_a_target, t_final_leg)
        dv_final_vnb = PE.to_vnb_frame(r_current, v_current, dv_final_vec)

        print(f"  [最後點火] 時間: {current_time:.1f}s | 鎖定推力向量: {np.round(dv_final_vnb, 3)} km/s | 大小: {dv_final_mag*1000:.1f} m/s")

        burns.append(dv_final_vnb)
        times.append(current_time)
        times.append(intercept_time)
        
        r_final, _ = farnocchia(self.MU, r_current, v_current + dv_final_vec, t_final_leg)
        print(f"最終攔截誤差 (km): {np.linalg.norm(r_final - r_a_target)}")

        times = np.diff(times).tolist()

        return burns, times