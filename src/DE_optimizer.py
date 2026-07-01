import numpy as np

from astropy import units as u
from poliastro.bodies import Earth
from scipy.optimize import differential_evolution

from src.propagator import OrbitPropagator
from src.physics_engine import PhysicsEngine as PE
from src.scorer import CompetitionScorer
from poliastro.core.propagation import farnocchia
from typing import Callable, Tuple

PropagatorFunc = Callable[[float, np.ndarray, np.ndarray, float], Tuple[np.ndarray, np.ndarray]]

def default_propagator(k: float, r0: np.ndarray, v0: np.ndarray, tof: float) -> Tuple[np.ndarray, np.ndarray]:
    r, v = farnocchia(k, r0, v0, tof)
    return r, v

class MissionOptimizer:
    MU = Earth.k.to_value((u.km ** 3) / (u.s ** 2)) # type: ignore
    MIN_PERIAPSIS = Earth.R.to_value(u.km) + 100.0
    MAX_DV = 1.5
    MIN_COAST_TIME = 100.0

    def __init__(self, config, propagator: PropagatorFunc = default_propagator):
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

        self.propagator = propagator

    def objective(self, x, num_burns) -> float:
        params = self.decode_params(x, num_burns)
        
        # 呼叫核心物理引擎
        sim_result = self.evaluate_mission_path(params, num_burns)
        
        if not sim_result["is_valid"]:
            return 0.0 # 或者回傳一個極小的負數來保留梯度

        # 這裡單純負責計分
        score = CompetitionScorer.calculate_score(
            min_distance_km=0.0, 
            total_time_sec=sim_result["intercept_time"], 
            total_dv_mps=float(sim_result["total_dv"] * 1000.0), 
            penalty_count=sim_result["penalty_count"]
        )
        return -score
    
    def _generate_bounds(self, num_burns: int) -> list:
        """根據固定的推進次數，動態產生 DE 需要的搜尋空間邊界"""
        bounds = [(0.0, self.Ta_sec * 0.5)]

        for _ in range(1, num_burns):
            bounds.extend([
                (-self.MAX_DV, self.MAX_DV), 
                (-self.MAX_DV, self.MAX_DV), 
                (-self.MAX_DV, self.MAX_DV),
                (0.0, 1.0)  # t_coast 的比例
            ])
            
        bounds.append((0.0, 1.0))
        
        return bounds
    
    def run_study(self):
        print(f"🚀 啟動 Differential Evolution 軌道最佳化...")
        print(f"最大推進次數: {self.max_burns} | 最大迭代次數: {self.maxiter} | 族群大小: {self.popsize}")

        best_overall_score = float('inf')  # 記錄全局最低分 (最優解)
        best_overall_params = None
        best_burns_count = 1

        # 迴圈測試不同的推進次數
        for current_burns in range(1, self.max_burns + 1):
            print(f"\n--- 開始最佳化: 推進次數 {current_burns} ---")

            bounds = self._generate_bounds(current_burns)

            result = differential_evolution(
                self.objective, 
                bounds, 
                args=(current_burns,),  # 重要：這裡的 tuple 會傳入 objective(x, current_burns)
                maxiter=self.maxiter, 
                popsize=self.popsize, 
                workers=self.num_threads, 
                disp=True, 
                updating='deferred',
                polish=True,
                tol=self.tol,
            )

            if result.fun < best_overall_score:
                best_overall_score = result.fun
                best_overall_params = result.x
                best_burns_count = current_burns
                print(f"⭐ 發現新最佳解！推進次數: {best_burns_count}, 當前最佳目標值: {best_overall_score:.4f}")

        if best_overall_score >= 0.0 or best_overall_params is None:
            print("\n❌ 最佳化失敗：所有的嘗試都撞毀或超時了，沒有有效的軌道可以回放。")
            return None, None

        print(f"\n✅ 最佳化完成！採用最優推進次數: {best_burns_count}")
        
        best_params_dict = self.decode_params(best_overall_params, best_burns_count)
        burns, times = self.replay_mission(best_params_dict, best_burns_count)

        return burns, times

    def replay_mission(self, best_params, num_burns):
        print("\n📝 --- 任務執行清單 (Mission Plan) ---")
        
        sim_result = self.evaluate_mission_path(best_params, num_burns)
        
        print(f"任務開始後等待: {best_params['t_wait']:.1f} 秒")
        for log in sim_result["burn_logs"]:
            print(f"  [{log['type']}] 時間: {log['time']:.1f}s | 推力向量: {np.round(log['dv_vnb'], 3)} km/s | 大小: {log['dv_mag']*1000:.1f} m/s")

        burns = [log["dv_vnb"] for log in sim_result["burn_logs"]]
        return burns, sim_result["times_diff"]
    
    def decode_params(self, x: list, num_burns: int) -> dict:
        """把 DE 給出的純數字陣列，轉換成具名參數字典"""
        params = {}
        params["num_burns"] = num_burns
        params["t_wait"] = x[0]  # 原本是 x[1]，現在變成 x[0]
        
        current_time = params["t_wait"]
        idx = 1  # 索引從 1 開始抓推進參數
        
        for i in range(1, num_burns):
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
    
    def evaluate_mission_path(self, params: dict, num_burns: int) -> dict:
        result = {
            "is_valid": True,
            "total_dv": 0.0,
            "penalty_count": 0,
            "intercept_time": 0.0,
            "burn_logs": [],
            "times_diff": []
        }

        times = [0.0]
        current_time = params["t_wait"]
        r_current, v_current = self.propagator(self.MU, self.B_r0, self.B_v0, current_time)

        for i in range(1, num_burns):
            dv_vec = np.array([params[f"b{i}_dv_x"], params[f"b{i}_dv_y"], params[f"b{i}_dv_z"]])
            dv_mag = np.linalg.norm(dv_vec)
            
            result["total_dv"] += dv_mag
            if dv_mag > self.MAX_DV: 
                result["penalty_count"] += 1

            dv_vnb = PE.to_vnb_frame(r_current, v_current, dv_vec)
            result["burn_logs"].append({
                "time": current_time, "dv_vec": dv_vec, 
                "dv_vnb": dv_vnb, "dv_mag": dv_mag, "type": f"Burn {i}"
            })
            times.append(current_time)

            v_current_new = v_current + dv_vec

            if not PE.check_constraints(r_current, v_current_new, self.MU, self.MIN_PERIAPSIS):
                result["is_valid"] = False
                return result

            t_coast = params[f"b{i}_t_coast"]
            current_time += t_coast
            r_current, v_current = self.propagator(self.MU, r_current, v_current_new, t_coast)

        t_final_leg = params["t_final_leg"]
        intercept_time = current_time + t_final_leg
        result["intercept_time"] = intercept_time

        r_a_target, _ = self.propagator(self.MU, self.A_r0, self.A_v0, intercept_time)

        v_req, _, dv_final_vec, dv_final_mag = PE.solve_lambert(
            self.MU, r_current, v_current, r_a_target, t_final_leg
        )
        
        result["total_dv"] += dv_final_mag
        if dv_final_mag > self.MAX_DV: 
            result["penalty_count"] += 1

        dv_final_vnb = PE.to_vnb_frame(r_current, v_current, dv_final_vec)
        result["burn_logs"].append({
            "time": current_time, "dv_vec": dv_final_vec, 
            "dv_vnb": dv_final_vnb, "dv_mag": dv_final_mag, "type": "Final Burn"
        })
        times.extend([current_time, intercept_time])

        if not PE.check_constraints(r_current, v_req, self.MU, self.MIN_PERIAPSIS):
            result["is_valid"] = False
            return result

        result["times_diff"] = np.diff(times).tolist()
        return result