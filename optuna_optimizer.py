import os
import optuna
import numpy as np
from tqdm import tqdm
from astropy import units as u
from poliastro.twobody import Orbit
from poliastro.bodies import Earth
import concurrent.futures

from propagator import OrbitPropagator
from physics_engine import PhysicsEngine
from scorer import CompetitionScorer
from script_generator import script_generator

ORBIT_A_SMA = 9000.0
ORBIT_A_ECC = 0.0
ORBIT_A_INC = 30.0
ORBIT_A_RAAN = 60.0
ORBIT_A_AOP = 0.0
ORBIT_A_TA = 0.0

ORBIT_B_SMA = 7500.0
ORBIT_B_ECC = 0.0
ORBIT_B_INC = 0.0
ORBIT_B_RAAN = 0.0
ORBIT_B_AOP = 0.0
ORBIT_B_TA = 180.0

N_TRIALS = 2000
NUM_THREADS = 8

class MissionOptimizer:
    """模組四：使用 Optuna 動態尋找最佳多脈衝機動策略"""

    def __init__(self):
        self.orbit_A = OrbitPropagator.create_orbit(ORBIT_A_SMA, ORBIT_A_ECC, ORBIT_A_INC, ORBIT_A_RAAN, ORBIT_A_AOP, ORBIT_A_TA)
        self.orbit_B = OrbitPropagator.create_orbit(ORBIT_B_SMA, ORBIT_B_ECC, ORBIT_B_INC, ORBIT_B_RAAN, ORBIT_B_AOP, ORBIT_B_TA)
        
        self.Ta_sec = self.orbit_A.period.to_value(u.s)
        self.T_max = 4.0 * self.Ta_sec

    def objective(self, trial: optuna.Trial) -> float:
        penalty_count = 0
        total_dv = 0.0
        
        num_burns = trial.suggest_int(
            "num_burns", 
            1, 
            self.T_max/100
        )

        # ==========================================
        # 1. 任務起點設定
        # ==========================================
        # 猜測出發前要先等多久 (0 到 半個週期)
        current_time = trial.suggest_float("t_wait", 0, self.Ta_sec * 0.5)
        r_current, v_current = OrbitPropagator.get_future_state(self.orbit_B, current_time)

        # ==========================================
        # 2. 動態生成前 N-1 次的盲猜推進
        # ==========================================
        for i in range(1, num_burns):
            # 猜測推力 (動態命名參數)
            dv_x = trial.suggest_float(f"b{i}_dv_x", -1.5, 1.5)
            dv_y = trial.suggest_float(f"b{i}_dv_y", -1.5, 1.5)
            dv_z = trial.suggest_float(f"b{i}_dv_z", -1.5, 1.5)
            dv_vec = np.array([dv_x, dv_y, dv_z])
            dv_mag = np.linalg.norm(dv_vec)

            total_dv += dv_mag
            if dv_mag > PhysicsEngine.MAX_DV: penalty_count += 1

            # 建立中繼軌道
            v_current_new = v_current + dv_vec
            intermediate_orbit = Orbit.from_vectors(
                Earth, 
                u.Quantity(r_current, u.km),
                u.Quantity(v_current_new, u.km / u.s)
            )

            # 安檢：撞地球直接提早結束 (給 0 分)
            if intermediate_orbit.r_p.to_value(u.km) < PhysicsEngine.MIN_PERIAPSIS:
                return 0.0 

            # 計算剩餘可用時間，保留至少 100 秒給最後的 Lambert
            max_coast = self.T_max - current_time - 100.0
            if max_coast <= 100.0: return 0.0 # 時間用盡，這條路不通

            # 猜測滑行時間
            t_coast = trial.suggest_float(f"b{i}_t_coast", 100.0, max_coast)
            current_time += t_coast
            
            # 更新狀態到下一個節點
            r_current, v_current = OrbitPropagator.get_future_state(intermediate_orbit, t_coast)

        # ==========================================
        # 3. 執行最後一次推進 (Burn N: Lambert 精準打擊)
        # ==========================================
        max_final = self.T_max - current_time
        if max_final <= 100.0: return 0.0
        
        # 猜測最後這段 Lambert 轉移要飛多久
        t_final_leg = trial.suggest_float("t_final_leg", 100.0, max_final)
        intercept_time = current_time + t_final_leg
        
        r_a_target, _ = OrbitPropagator.get_future_state(self.orbit_A, intercept_time)

        # 呼叫 Lambert 求解器
        v_req, _, _, dv_final_mag = PhysicsEngine.solve_lambert(r_current, v_current, r_a_target, t_final_leg)
        
        total_dv += dv_final_mag
        if dv_final_mag > PhysicsEngine.MAX_DV: penalty_count += 1

        # 安檢：最後這條 Lambert 軌道會不會撞地球
        final_orbit = Orbit.from_vectors(Earth, u.Quantity(r_current, u.km), u.Quantity(v_req, u.km/u.s))
        if final_orbit.r_p.to_value(u.km) < PhysicsEngine.MIN_PERIAPSIS:
            return 0.0

        # ==========================================
        # 4. 結算總分
        # ==========================================
        score = CompetitionScorer.calculate_score(
            min_distance_km=0.0, 
            total_time_sec=intercept_time, 
            total_dv_mps=float(total_dv * 1000.0), 
            penalty_count=penalty_count
        )

        return score
    
    def _single_study_task(self, task_id, n_trials):
        optuna.logging.set_verbosity(optuna.logging.WARNING)
        study = optuna.create_study(direction="maximize")
        study.optimize(self.objective, n_trials=n_trials, show_progress_bar=False)

        return {
            "task_id": task_id,
            "best_value": study.best_value,
            "best_params": study.best_params
        }
    
    def run_multiple_studies(self, total_runs=100, n_trials=500):
        safe_workers = 8
        
        print(f"⚡ 準備啟動 {total_runs} 個獨立的最佳化計算...")
        print(f"🖥️ 偵測到系統核心，將使用 {safe_workers} 個核心進行自動排程。")
        
        all_results = []

        with concurrent.futures.ProcessPoolExecutor(max_workers=safe_workers) as executor:
            futures = [
                executor.submit(self._single_study_task, i+1, n_trials) 
                for i in range(total_runs)
            ]
            
            for future in tqdm(concurrent.futures.as_completed(futures), total=total_runs):
                try:
                    result = future.result()
                    all_results.append(result)
                    # print(f"🏆 [任務 {result['task_id']}/{total_runs}] 完成！得分: {result['best_value']:.2f}")
                except Exception as e:
                    print(f"❌ 計算發生錯誤: {e}")

        best_overall = max(all_results, key=lambda x: x['best_value'])
        print(f"全域最高得分: {best_overall['best_value']:.2f} (來自任務 {best_overall['task_id']})")

        if best_overall['best_value'] <= 0.0:
            print("❌ 最佳化失敗：所有的嘗試都撞毀或超時了，沒有有效的軌道可以回放。")
            return

        burns, times = self.replay_mission(best_overall['best_params'])
        script_generator(
            ORBIT_A_SMA, ORBIT_A_ECC, ORBIT_A_INC, ORBIT_A_RAAN, ORBIT_A_AOP, ORBIT_A_TA,
            ORBIT_B_SMA, ORBIT_B_ECC, ORBIT_B_INC, ORBIT_B_RAAN, ORBIT_B_AOP, ORBIT_B_TA,
            burns, times
        )        

    def run_study(self, n_trials=500):
        print(f"🚀 啟動 Optuna 軌道最佳化，預計執行 {n_trials} 次嘗試...")
        
        study = optuna.create_study(direction="maximize")
        study.optimize(self.objective, n_trials=n_trials, show_progress_bar=True)

        print("\n🏆 最佳化完成！")
        print(f"最高得分: {study.best_value:.2f}")
        print("最佳策略參數:")

        burns, times = self.replay_mission(study.best_params)
        script_generator(
            ORBIT_A_SMA, ORBIT_A_ECC, ORBIT_A_INC, ORBIT_A_RAAN, ORBIT_A_AOP, ORBIT_A_TA,
            ORBIT_B_SMA, ORBIT_B_ECC, ORBIT_B_INC, ORBIT_B_RAAN, ORBIT_B_AOP, ORBIT_B_TA,
            burns, times
        )
    
    def replay_mission(self, best_params):
        """
        傳入 best_params，重新執行一次軌道運算並印出所有點火指令
        """
        print("\n📝 --- 任務執行清單 (Mission Plan) ---")
        penalty_count = 0
        total_dv = 0.0

        burns = []
        times = [best_params["t_wait"]]
        
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
        times.append(intercept_time)
        
        total_dv += dv_final_mag
        print(f"--- 總消耗 Delta-V: {total_dv*1000:.1f} m/s | 違規次數: {penalty_count} ---")
        
        final_orbit = Orbit.from_vectors(Earth, u.Quantity(r_current, u.km), u.Quantity(v_current + dv_final_vec, u.km/u.s))
        r_final, _ = OrbitPropagator.get_future_state(final_orbit, t_final_leg)
        
        print(f"最終攔截誤差 (km): {np.linalg.norm(r_final - r_a_target)}")

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
    import warnings
    warnings.filterwarnings("ignore")
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    
    optimizer = MissionOptimizer()
    optimizer.run_multiple_studies(total_runs=NUM_THREADS ,n_trials=N_TRIALS)