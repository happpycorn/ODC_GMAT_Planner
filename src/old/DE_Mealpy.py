import numpy as np
from typing import Tuple
from scipy.optimize import minimize
from old.propagator import get_r0_v0
from old.propagator import propagate as effected_propagate

from old.JIT_Engine import (
    objective, decode_params, evaluate_mission_path, MU, MIN_PERIAPSIS
)

from mealpy import FloatVar
from mealpy.evolutionary_based.SHADE import L_SHADE

class MissionOptimizer:
    MAX_DV = 1.5
    MIN_COAST_TIME = 100.0

    def __init__(self, config, propagator = None):
        self.A_r0, self.A_v0 = get_r0_v0(
            config["orbit_A"]["SMA"], config["orbit_A"]["ECC"], config["orbit_A"]["INC"],
            config["orbit_A"]["RAAN"], config["orbit_A"]["AOP"], config["orbit_A"]["TA"],
        )
        self.B_r0, self.B_v0 = get_r0_v0(
            config["orbit_B"]["SMA"], config["orbit_B"]["ECC"], config["orbit_B"]["INC"],
            config["orbit_B"]["RAAN"], config["orbit_B"]["AOP"], config["orbit_B"]["TA"],
        )
        
        self.burns = config["optimization"]["MAX_BURNS"]
        self.maxiter = config["optimization"]["MAXITER"]
        self.popsize = config["optimization"]["POPSIZE"]
        self.num_threads = config["optimization"]["NUM_THREADS"]
        
        self.Ta_sec = 2.0 * np.pi * np.sqrt(config["orbit_A"]["SMA"]**3 / MU)
        self.T_max = 4.0 * self.Ta_sec
        self.propagator = propagator

        self.mes = config["optimization"]["MAX_EARLY_STOP"]
        self.tol = config["optimization"]["TOL"]
    
    def _generate_bounds(self, num_burns: int) -> Tuple[list, list]:
        """💡 轉為 Mealpy 需要的 lb (下界) 與 ub (上界) 陣列"""
        lb = [0.0]
        ub = [self.T_max]

        for _ in range(1, num_burns):
            lb.extend([-self.MAX_DV, -self.MAX_DV, -self.MAX_DV, 0.0])
            ub.extend([self.MAX_DV, self.MAX_DV, self.MAX_DV, 1.0])
            
        lb.append(0.0)
        ub.append(1.0)
        
        return lb, ub
    
    def run_study(self):
        print(f"🚀 啟動 Mealpy Differential Evolution (L-SHADE) 軌道最佳化...")
        print(f"測試推進項目: {self.burns} | 最大迭代次數: {self.maxiter} | 基礎族群大小: {self.popsize}")

        best_overall_score = float('inf')  
        best_overall_params = None
        best_burns_count = 1

        for current_burns in self.burns:
            print(f"\n--- 開始最佳化: 推進次數 {current_burns} ---")
            lb, ub = self._generate_bounds(current_burns)
            pop_size = (15 + 3 * current_burns) * self.popsize

            def fitness_wrapper(solution):
                res = objective(
                    solution, current_burns, 
                    self.MIN_COAST_TIME, self.T_max,
                    self.A_r0, self.A_v0, self.B_r0, self.B_v0,
                    min_periapsis=MIN_PERIAPSIS+50
                )
                return res

            problem = {
                "obj_func": fitness_wrapper,
                "bounds": [FloatVar(lb=l, ub=u) for l, u in zip(lb, ub)],
                "minmax": "min",    
                "log_to": "console"      
            }

            term_dict = {
                "max_early_stop": self.mes,  # 連續 30 代沒進步就停
                "epsilon": self.tol        # 進步門檻
            }

            model = L_SHADE(epoch=self.maxiter, pop_size=pop_size, termination=term_dict)
            g_best = model.solve(problem, n_workers=self.num_threads)
            
            current_best_x = g_best.solution
            raw_fitness = g_best.target.fitness 
            current_best_score = float(raw_fitness) if raw_fitness is not None else float('inf')

            if current_best_score < best_overall_score:
                best_overall_score = current_best_score
                best_overall_params = current_best_x
                best_burns_count = current_burns
                print(f"⭐ 發現新最佳解！推進次數: {best_burns_count}, 當前最佳目標值: {best_overall_score:.4f}")

        if best_overall_score >= 0.0 or best_overall_params is None:
            print("\n❌ 最佳化失敗：所有的嘗試都撞毀或超時了，沒有有效的軌道可以回放。")
            return None, None, (None, None)

        print(f"\n✅ 最佳化完成！採用最優推進次數: {best_burns_count}")
        
        burns, times = self.replay_mission(best_overall_params, best_burns_count)

        return burns, times, (best_overall_params, best_burns_count)

    def replay_mission(self, best_result_x, num_burns):
        best_params = decode_params(
            best_result_x, num_burns,
            self.MIN_COAST_TIME, self.T_max
        )
        print("\n📝 --- 任務執行清單 (Mission Plan) ---")

        _, _, _, _, burn_logs, times_diff = evaluate_mission_path(
            best_params, num_burns,
            self.A_r0, self.A_v0, self.B_r0, self.B_v0,
            propagator=self.propagator
        )
        
        print(f"任務開始後等待: {best_params['t_wait']:.1f} 秒")
        for current_time, dv_vec, dv_vnb, dv_mag, burn_type in burn_logs:
            print(f"  [{burn_type}] 時間: {current_time:.1f}s | 推力向量: {np.round(dv_vnb, 3)} km/s | 大小: {dv_mag*1000:.1f} m/s")

        burns = [dv_vnb for _, _, dv_vnb, _, _ in burn_logs]
        return burns, times_diff

    def refine_trajectory(self, initial_guess_x, num_burns):
        print("\n🔬 啟動高精度 NLP 微調 (含 J2 攝動)...")
        bounds = self._generate_bounds(num_burns)
        
        narrow_bounds = []
        for i, (lb, ub) in enumerate(bounds):
            x_val = initial_guess_x[i]
            span = ub - lb
            
            # 💡 動態緊箍咒：利用下界是否小於 0，來區分推力與時間參數
            # 在你的設定中，只有推力參數 (dv) 的下界是 -MAX_DV (-1.5)
            # 時間或比例參數的下界都是 0.0
            if lb < 0:
                # 這是推力向量！給予 15% 的寬容度，讓它有足夠的燃料去對抗 J2
                tolerance = span * 0.15 
            else:
                # 這是時間或比例！給予 2% 的嚴格限制，防止它亂縮短時間
                tolerance = span * 0.02 
                
            new_lb = max(lb, x_val - tolerance)
            new_ub = min(ub, x_val + tolerance)
            narrow_bounds.append((new_lb, new_ub))
        
        def fitness_wrapper(solution):
            res = objective(
                solution, num_burns, 
                self.MIN_COAST_TIME, self.T_max,
                self.A_r0, self.A_v0, self.B_r0, self.B_v0,
                propagator=effected_propagate
            )
            return res

        nlp_result = minimize(
            fun=fitness_wrapper, 
            x0=initial_guess_x,                     
            args=(num_burns,), 
            method='L-BFGS-B',                      
            bounds=narrow_bounds,                   
            options={'disp': True, 'maxiter': 50} 
        )
        
        if nlp_result.success:
            print(f"✅ NLP 微調成功！最終高精度分數: {-nlp_result.fun:.4f}")
            res = nlp_result.x
        else:
            print("⚠️ NLP 微調遇到困難，可能落入局部死胡同。")
            res = initial_guess_x
    
        return self.replay_mission(res, num_burns)