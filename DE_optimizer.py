import os
import json
import numpy as np
from tqdm import tqdm
import multiprocessing
from astropy import units as u
from poliastro.twobody import Orbit
from poliastro.bodies import Earth
from scipy.optimize import minimize
from scipy.optimize import differential_evolution

from propagator import OrbitPropagator
from physics_engine import PhysicsEngine
from scorer import CompetitionScorer
from script_generator import script_generator

DEFAULT_CONFIG = {
    "orbit_A": {
        "SMA": 9000.0, "ECC": 0.0, "INC": 0.0, 
        "RAAN": 0.0, "AOP": 0.0, "TA": 0.0
    },
    "orbit_B": {
        "SMA": 7500.0, "ECC": 0.0, "INC": 0.0, 
        "RAAN": 0.0, "AOP": 0.0, "TA": 0.0
    },
    "optimization": {
        "MAX_BURNS": 8,
        "MAXITER": 200,
        "POPSIZE": 10,
        "NUM_THREADS": -1,
        "TOL":10e-4,
    }
}

def load_or_create_config(filename="config.json"):
    """讀取設定檔；如果不存在，則建立一個預設的設定檔"""
    if not os.path.exists(filename):
        print(f"⚠️ 找不到 {filename}，正在自動生成預設設定檔...")
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        return DEFAULT_CONFIG
    
    # print(f"📂 成功讀取 {filename} 設定檔！")
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)

class MissionOptimizer:
    def __init__(self, max_burns=8):
        self.orbit_A = OrbitPropagator.create_orbit(ORBIT_A_SMA, ORBIT_A_ECC, ORBIT_A_INC, ORBIT_A_RAAN, ORBIT_A_AOP, ORBIT_A_TA)
        self.orbit_B = OrbitPropagator.create_orbit(ORBIT_B_SMA, ORBIT_B_ECC, ORBIT_B_INC, ORBIT_B_RAAN, ORBIT_B_AOP, ORBIT_B_TA)
        
        self.Ta_sec = self.orbit_A.period.to_value(u.s)
        self.T_max = 4.0 * self.Ta_sec
        self.max_burns = max_burns

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

            max_coast = self.T_max - current_time - 100.0
            t_coast = 100.0 + coast_frac * (max_coast - 100.0) if max_coast > 100.0 else 100.0
            params[f"b{i}_t_coast"] = t_coast
            current_time += t_coast
            
        max_final = self.T_max - current_time
        final_leg_frac = x[-1]
        t_final_leg = 100.0 + final_leg_frac * (max_final - 100.0) if max_final > 100.0 else 100.0
        params["t_final_leg"] = t_final_leg
        
        return params

    def objective(self, x) -> float:
        params = self.decode_params(x)
        
        penalty_count = 0
        total_dv = 0.0
        
        num_burns = params["num_burns"]
        current_time = params["t_wait"]
        
        r_current, v_current = OrbitPropagator.get_future_state(self.orbit_B, current_time)

        for i in range(1, num_burns):
            dv_vec = np.array([params[f"b{i}_dv_x"], params[f"b{i}_dv_y"], params[f"b{i}_dv_z"]])
            dv_mag = np.linalg.norm(dv_vec)

            total_dv += dv_mag
            if dv_mag > PhysicsEngine.MAX_DV: penalty_count += 1

            v_current_new = v_current + dv_vec
            intermediate_orbit = Orbit.from_vectors(
                Earth, 
                u.Quantity(r_current, u.km),
                u.Quantity(v_current_new, u.km / u.s)
            )

            if intermediate_orbit.r_p.to_value(u.km) < PhysicsEngine.MIN_PERIAPSIS:
                return 0.0

            max_coast = self.T_max - current_time - 100.0
            if max_coast <= 100.0: return 0.0 

            t_coast = params[f"b{i}_t_coast"]
            current_time += t_coast
            
            r_current, v_current = OrbitPropagator.get_future_state(intermediate_orbit, t_coast)

        max_final = self.T_max - current_time
        if max_final <= 100.0: return 0.0
        
        t_final_leg = params["t_final_leg"]
        intercept_time = current_time + t_final_leg
        
        r_a_target, _ = OrbitPropagator.get_future_state(self.orbit_A, intercept_time)

        v_req, _, _, dv_final_mag = PhysicsEngine.solve_lambert(r_current, v_current, r_a_target, t_final_leg)
        
        total_dv += dv_final_mag
        if dv_final_mag > PhysicsEngine.MAX_DV: penalty_count += 1

        final_orbit = Orbit.from_vectors(Earth, u.Quantity(r_current, u.km), u.Quantity(v_req, u.km/u.s))
        if final_orbit.r_p.to_value(u.km) < PhysicsEngine.MIN_PERIAPSIS:
            return 0.0

        score = CompetitionScorer.calculate_score(
            min_distance_km=0.0, 
            total_time_sec=intercept_time, 
            total_dv_mps=float(total_dv * 1000.0), 
            penalty_count=penalty_count
        )

        return -score
    
    def run_study(self, maxiter=200, popsize=15):
        print(f"🚀 啟動 Differential Evolution 軌道最佳化...")
        print(f"最大推進次數: {self.max_burns} | 最大迭代次數: {maxiter} | 族群大小: {popsize}")

        bounds = [
            (1, self.max_burns + 0.49),
            (0, self.Ta_sec * 0.5)
        ]
        
        for _ in range(self.max_burns - 1):
            bounds.extend([
                (-1.5, 1.5), (-1.5, 1.5), (-1.5, 1.5),
                (0.0, 1.0)
            ])
            
        bounds.append((0.0, 1.0))

        result = differential_evolution(
            self.objective, bounds, maxiter=maxiter, popsize=popsize, 
            workers=NUM_THREADS, disp=False, updating='deferred',
            polish=False, # 關閉預設的 L-BFGS-B
            tol=TOL,
        )

        print("\n✨ 啟動 Nelder-Mead 幾何拋光微調...")
        polished_result = minimize(
            self.objective, 
            result.x,               # 把 DE 找到的最佳解當作起點
            method='Nelder-Mead',   # 使用無梯度的單形法
            options={'xatol': 1e-5, 'fatol': 1e-5, 'maxiter': 1000}
        )

        best_score_de = -result.fun
        best_score_polished = -polished_result.fun

        print(f"DE 原始得分: {best_score_de:.4f}")
        print(f"拋光後得分: {best_score_polished:.4f}")

        if best_score_polished <= 0.0:
            print("❌ 最佳化失敗：所有的嘗試都撞毀或超時了，沒有有效的軌道可以回放。")
            return

        best_params = self.decode_params(polished_result.x)

        burns, times = self.replay_mission(best_params)
        script_generator(
            ORBIT_A_SMA, ORBIT_A_ECC, ORBIT_A_INC, ORBIT_A_RAAN, ORBIT_A_AOP, ORBIT_A_TA,
            ORBIT_B_SMA, ORBIT_B_ECC, ORBIT_B_INC, ORBIT_B_RAAN, ORBIT_B_AOP, ORBIT_B_TA,
            burns, times
        )

    def replay_mission(self, best_params):
        print("\n📝 --- 任務執行清單 (Mission Plan) ---")
        penalty_count = 0
        total_dv = 0.0

        burns = []
        times = [0]
        
        num_burns = int(best_params["num_burns"])
        current_time = best_params["t_wait"]
        r_current, v_current = OrbitPropagator.get_future_state(self.orbit_B, current_time)
        
        print(f"任務開始後等待: {current_time:.1f} 秒")

        for i in range(1, num_burns):
            dv_vec = np.array([best_params[f"b{i}_dv_x"], best_params[f"b{i}_dv_y"], best_params[f"b{i}_dv_z"]])
            dv_mag = np.linalg.norm(dv_vec)
            dv_vnb = self.to_vnb_frame(r_current, v_current, dv_vec)
            
            print(f"  [點火 {i}] 時間: {current_time:.1f}s | 推力向量: {np.round(dv_vnb, 3)} km/s | 大小: {dv_mag*1000:.1f} m/s")

            burns.append(dv_vnb)
            times.append(current_time)
            
            total_dv += dv_mag
            if dv_mag > PhysicsEngine.MAX_DV: penalty_count += 1
            
            t_coast = best_params[f"b{i}_t_coast"]
            current_time += t_coast
            v_current = v_current + dv_vec
            intermediate_orbit = Orbit.from_vectors(Earth, u.Quantity(r_current, u.km), u.Quantity(v_current, u.km/u.s))
            r_current, v_current = OrbitPropagator.get_future_state(intermediate_orbit, t_coast)

        t_final_leg = best_params["t_final_leg"]
        intercept_time = current_time + t_final_leg
        r_a_target, _ = OrbitPropagator.get_future_state(self.orbit_A, intercept_time)
        
        v_req, _, dv_final_vec, dv_final_mag = PhysicsEngine.solve_lambert(r_current, v_current, r_a_target, t_final_leg)

        dv_final_vnb = self.to_vnb_frame(r_current, v_current, dv_final_vec,)
        
        print(f"  [最後點火] 時間: {current_time:.1f}s | 鎖定推力向量: {np.round(dv_final_vnb, 3)} km/s | 大小: {dv_final_mag*1000:.1f} m/s")
        print(f"  預計攔截時間: {intercept_time:.1f}s")

        burns.append(dv_final_vnb)
        times.append(current_time)
        times.append(intercept_time)
        
        total_dv += dv_final_mag
        print(f"--- 總消耗 Delta-V: {total_dv*1000:.1f} m/s | 違規次數: {penalty_count} ---")
        
        final_orbit = Orbit.from_vectors(Earth, u.Quantity(r_current, u.km), u.Quantity(v_current + dv_final_vec, u.km/u.s))
        r_final, _ = OrbitPropagator.get_future_state(final_orbit, t_final_leg)
        
        print(f"最終攔截誤差 (km): {np.linalg.norm(r_final - r_a_target)}")

        times = [times[i+1]-times[i] for i in range(len(times)-1)]

        return burns, times
    
    def to_vnb_frame(self, r_vec, v_vec, dv_inertial):
        v_hat = v_vec / np.linalg.norm(v_vec)
        h_vec = np.cross(r_vec, v_vec)
        n_hat = h_vec / np.linalg.norm(h_vec)
        b_hat = np.cross(v_hat, n_hat)
        
        T_mat = np.array([v_hat, n_hat, b_hat])
        
        dv_vnb = T_mat @ dv_inertial
        return dv_vnb

if __name__ == "__main__":
    import time
    import warnings
    multiprocessing.freeze_support()
    warnings.filterwarnings("ignore")

    config = load_or_create_config()

    ORBIT_A_SMA = config["orbit_A"]["SMA"]
    ORBIT_A_ECC = config["orbit_A"]["ECC"]
    ORBIT_A_INC = config["orbit_A"]["INC"]
    ORBIT_A_RAAN = config["orbit_A"]["RAAN"]
    ORBIT_A_AOP = config["orbit_A"]["AOP"]
    ORBIT_A_TA = config["orbit_A"]["TA"]

    ORBIT_B_SMA = config["orbit_B"]["SMA"]
    ORBIT_B_ECC = config["orbit_B"]["ECC"]
    ORBIT_B_INC = config["orbit_B"]["INC"]
    ORBIT_B_RAAN = config["orbit_B"]["RAAN"]
    ORBIT_B_AOP = config["orbit_B"]["AOP"]
    ORBIT_B_TA = config["orbit_B"]["TA"]

    MAX_BURNS = config["optimization"]["MAX_BURNS"]
    MAXITER = config["optimization"]["MAXITER"]
    POPSIZE = config["optimization"]["POPSIZE"]
    NUM_THREADS = config["optimization"]["NUM_THREADS"]

    TOL = config["optimization"]["TOL"]
    
    start_time = time.perf_counter() 
    
    optimizer = MissionOptimizer(max_burns=MAX_BURNS)
    optimizer.run_study(maxiter=MAXITER, popsize=POPSIZE)
    
    end_time = time.perf_counter() 
    execution_time = end_time - start_time
    
    print("\n" + "="*40)
    print(f"⏳ 總計算時間: {execution_time:.2f} 秒")
    if execution_time > 60:
        print(f"   (大約 {execution_time / 60:.2f} 分鐘)")
    print("="*40)