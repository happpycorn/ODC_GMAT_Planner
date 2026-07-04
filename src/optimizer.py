import numpy as np
from numba import njit
from poliastro.core.iod import izzo
import concurrent.futures

from typing import Tuple
from scipy.optimize import minimize
from mealpy import FloatVar
from mealpy.evolutionary_based.SHADE import L_SHADE

from src.propagator import get_r0_v0
from src.scorer import calculate_score
from src.core_math import propagate_rk4, check_constraints, fast_norm, to_vnb_frame
import numba as nb
from tqdm import tqdm

# 這裡把所有不變的環境常數傳進來，避免 Numba 抓取外部全域變數
@njit(nb.float64(nb.float64[:], nb.int64, nb.float64[:], nb.float64[:, :]), fastmath=True, cache=True)
def fast_fitness_evaluator(
    x: np.ndarray, num_burns: int, 
    scalars: np.ndarray, vectors: np.ndarray
) -> float:
    """
    100% 純 JIT 的適應度函數。沒有任何 Python 物件，直接吃 Mealpy 的一維陣列。
    """

    min_coast_time = scalars[0]
    T_max = scalars[1]
    mu = scalars[2]
    j2_val = scalars[3]
    re_val = scalars[4]
    min_periapsis = scalars[5]
    max_dv = scalars[6]
    k_t = scalars[7]
    C_t = scalars[8]
    k_v = scalars[9]
    C_v = scalars[10]

    A_r0 = vectors[0]
    A_v0 = vectors[1]
    B_r0 = vectors[2]
    B_v0 = vectors[3]

    total_dv = 0.0
    penalty_count = 0
    dt = 60.0 # RK4 步長

    # 1. 初始等待時間 (t_wait)
    current_time = float(x[0])
    
    # 傳播太空船 B 到第一次點火點
    r_curr, v_curr = propagate_rk4(B_r0, B_v0, current_time, dt, mu, j2_val, re_val)

    idx = 1
    # 2. 執行前 N-1 次機動 (如果 num_burns > 1)
    for _ in range(1, num_burns):
        # 直接從一維陣列抓取推力向量
        dv_vec = np.array([x[idx], x[idx+1], x[idx+2]], dtype=np.float64)
        coast_frac = x[idx+3]
        idx += 4
        
        dv_mag = fast_norm(dv_vec)
        total_dv += dv_mag
        if dv_mag > max_dv: 
            penalty_count += 1

        v_curr_new = v_curr + dv_vec

        # 安檢：點火後會不會撞地球？
        if not check_constraints(r_curr, v_curr_new, mu, min_periapsis):
            return 0.0 # 直接判定 0 分 (極度差的適應度)

        # 計算這次的海岸滑行時間 (Coast Time)
        max_coast = T_max - current_time - min_coast_time
        t_coast = min_coast_time
        if max_coast > min_coast_time:
            t_coast += coast_frac * (max_coast - min_coast_time)
            
        # 傳播太空船 B 經過 Coast Time
        r_curr, v_curr = propagate_rk4(r_curr, v_curr_new, t_coast, dt, mu, j2_val, re_val)
        current_time += t_coast

    # 3. 最後一次機動 (Lambert 攔截)
    # 決定最後一段飛行時間
    final_leg_frac = x[-1]
    max_final = T_max - current_time
    t_final_leg = min_coast_time
    if max_final > min_coast_time:
        t_final_leg += final_leg_frac * (max_final - min_coast_time)
        
    intercept_time = current_time + t_final_leg

    # 傳播太空船 A (目標) 到攔截時間點
    r_A_target, _ = propagate_rk4(A_r0, A_v0, intercept_time, dt, mu, j2_val, re_val)

    # 呼叫 Poliastro 內建的純 Numba Lambert 求解器 (izzo)
    # izzo 回傳的是 (v1_req, v2_req)
    v1_req, _ = izzo(
        mu, r_curr, r_A_target, t_final_leg,
        M=0, prograde=True, lowpath=True, numiter=35, rtol=1e-8
    )
    
    # 計算需要的最後一次推力
    dv_final_vec = v1_req - v_curr
    dv_final_mag = fast_norm(dv_final_vec)
    total_dv += dv_final_mag
    
    if dv_final_mag > max_dv: 
        penalty_count += 1

    # 最終安檢
    if not check_constraints(r_curr, v1_req, mu, min_periapsis):
        return 0.0

    # 4. 結算最終分數 (利用我們剛改好的 scorer)
    score = calculate_score(
        min_distance_km=0.0, # 理論上 Lambert 算出來就是剛好撞上 (距離為 0)
        total_time_sec=intercept_time, 
        total_dv_mps=total_dv * 1000.0, 
        penalty_count=penalty_count,
        k_t=k_t, C_t=C_t, k_v=k_v, C_v=C_v
    )
    
    # Mealpy 預設是找「最小值」，所以我們把分數加負號回傳
    return -score

class MissionOptimizer:
    def __init__(self, config):
        self.config = config
        # 從 config 提取環境常數 (避免每次呼叫都查字典)
        self.k_t = config.get("k_t", 0.0001)
        self.C_t = config.get("C_t", 11000.0)
        self.k_v = config.get("k_v", 0.005)
        self.C_v = config.get("C_v", 1200.0)
        
        # 物理常數與限制
        self.MU = 398600.4418          # 地球標準重力參數
        self.J2_VAL = 1.08262668e-3
        self.RE_VAL = 6378.137
        self.MIN_PERIAPSIS = self.RE_VAL + 100.0
        self.MAX_DV = 1.5
        self.MIN_COAST_TIME = 100.0

        # 初始化軌道
        self.A_r0, self.A_v0 = get_r0_v0(
            config["orbit_A"]["SMA"], config["orbit_A"]["ECC"], config["orbit_A"]["INC"],
            config["orbit_A"]["RAAN"], config["orbit_A"]["AOP"], config["orbit_A"]["TA"]
        )
        self.B_r0, self.B_v0 = get_r0_v0(
            config["orbit_B"]["SMA"], config["orbit_B"]["ECC"], config["orbit_B"]["INC"],
            config["orbit_B"]["RAAN"], config["orbit_B"]["AOP"], config["orbit_B"]["TA"]
        )
        
        # 演算法設定
        self.burns = config["optimization"]["MAX_BURNS"]
        self.maxiter = config["optimization"]["MAXITER"]
        self.popsize = config["optimization"]["POPSIZE"]
        self.num_threads = config["optimization"]["NUM_THREADS"]
        self.mes = config["optimization"]["MAX_EARLY_STOP"]
        self.tol = config["optimization"]["TOL"]
        
        # 計算時間上限
        self.Ta_sec = 2.0 * np.pi * np.sqrt(config["orbit_A"]["SMA"]**3 / self.MU)
        self.T_max = 4.0 * self.Ta_sec
    
    def _generate_bounds(self, num_burns: int) -> Tuple[list, list]:
        """產生純陣列的上下界"""
        lb = [0.0]
        ub = [self.T_max]
        for _ in range(1, num_burns):
            lb.extend([-self.MAX_DV, -self.MAX_DV, -self.MAX_DV, 0.0])
            ub.extend([self.MAX_DV, self.MAX_DV, self.MAX_DV, 1.0])
        lb.append(0.0)
        ub.append(1.0)
        return lb, ub
    
    def _optimize_burn_case(self, current_burns, scalar_params, vector_params):
        """
        獨立的工作包：負責在單一核心上，執行特定推進次數的 4000 代最佳化。
        """
        print(f"⏳ [核心啟動] 開始計算推進次數: {current_burns} ...")
        lb, ub = self._generate_bounds(current_burns)
        pop_size = (15 + 3 * current_burns) * self.popsize

        def fitness_wrapper(solution):
            return fast_fitness_evaluator(
                np.asarray(solution, dtype=np.float64), 
                current_burns, 
                scalar_params, 
                vector_params
            )

        problem = {
            "obj_func": fitness_wrapper,
            "bounds": [FloatVar(lb=l, ub=u) for l, u in zip(lb, ub)],
            "minmax": "min",    
            "log_to": None
        }

        term_dict = {"max_early_stop": self.mes, "epsilon": self.tol}
        model = L_SHADE(epoch=self.maxiter, pop_size=pop_size, termination=term_dict)
        
        # ⚠️ 效能關鍵：因為外層已經分配核心了，這裡的 Mealpy 必須強制設定為單核 (n_workers=1)！
        g_best = model.solve(problem, n_workers=1)
        
        current_best_x = g_best.solution
        raw_fitness = g_best.target.fitness 
        current_best_score = float(raw_fitness) if raw_fitness is not None else float('inf')

        return current_burns, current_best_x, current_best_score
    
    def run_study(self):
        print(f"🚀 啟動 JIT 極速版 L-SHADE 軌道最佳化 (多核心巨觀平行化)...")

        scalar_params = np.array([
            self.MIN_COAST_TIME, self.T_max, self.MU, self.J2_VAL, self.RE_VAL,
            self.MIN_PERIAPSIS, self.MAX_DV, self.k_t, self.C_t, self.k_v, self.C_v
        ], dtype=np.float64)
        
        vector_params = np.vstack([
            self.A_r0, self.A_v0, self.B_r0, self.B_v0
        ])  
        
        best_overall_score = float('inf')  
        best_overall_params = None
        best_burns_count = 1

        # 開啟多行程池，最大核心數設定為你要測試的推進情境總數 (例如 burns = [1, 2, 3] 就是開 3 個)
        num_cases = len(self.burns)
        
        with concurrent.futures.ProcessPoolExecutor(max_workers=num_cases) as executor:
            # 1. 提交所有任務：把不同的 current_burns 丟給不同的核心
            futures = [
                executor.submit(self._optimize_burn_case, b, scalar_params, vector_params)
                for b in self.burns
            ]

            # 2. 監聽完成狀態：哪個核心先算完 4000 代，就先驗收誰的結果
            for future in tqdm(concurrent.futures.as_completed(futures), total=num_cases):
                try:
                    # 接收 _optimize_burn_case 回傳的三個變數
                    b_count, best_x, best_score = future.result()
                    tqdm.write(f"✅ [核心回傳] 推進 {b_count} 次完成！最佳目標值: {best_score:.4f}")

                    # 更新全局最佳解
                    if best_score < best_overall_score:
                        best_overall_score = best_score
                        best_overall_params = best_x
                        best_burns_count = b_count
                        tqdm.write(f"⭐ 發現目前全局新最佳解！推進次數: {best_burns_count}")

                except Exception as exc:
                    tqdm.write(f"❌ [核心錯誤] 崩潰: {exc}")

        if best_overall_score >= 0.0 or best_overall_params is None:
            print("\n❌ 最佳化失敗：所有的嘗試都撞毀或違規了。")
            return None, None, (None, None)

        print(f"\n✅ 最佳化完成！")
        return self.refine_trajectory(best_overall_params, best_burns_count)

    def refine_trajectory(self, initial_guess_x, num_burns):
        print("\n🔬 啟動高精度 NLP 微調...")
        bounds = self._generate_bounds(num_burns)
        
        narrow_bounds = []
        for i, (lb, ub) in enumerate(zip(*bounds)):
            x_val = initial_guess_x[i]
            span = ub - lb
            # 推力給 15% 寬容度，時間給 2% 嚴格限制
            tolerance = span * 0.15 if lb < 0 else span * 0.02 
            narrow_bounds.append((max(lb, x_val - tolerance), min(ub, x_val + tolerance)))
        
        scalar_params = np.array([
            self.MIN_COAST_TIME, self.T_max, self.MU, self.J2_VAL, self.RE_VAL,
            self.MIN_PERIAPSIS, self.MAX_DV, self.k_t, self.C_t, self.k_v, self.C_v
        ], dtype=np.float64)
        
        vector_params = np.vstack([
            self.A_r0, self.A_v0, self.B_r0, self.B_v0
        ]) 

        def fitness_wrapper(solution):
            return fast_fitness_evaluator(
                np.asarray(solution, dtype=np.float64), 
                num_burns, 
                scalar_params, 
                vector_params
            )

        nlp_result = minimize(
            fun=fitness_wrapper, x0=initial_guess_x,                     
            method='L-BFGS-B', bounds=narrow_bounds,                   
            options={'disp': True, 'maxiter': 50} 
        )
        
        res = nlp_result.x if nlp_result.success else initial_guess_x
        return self._replay_mission(res, num_burns)

    def _replay_mission(self, x, num_burns):
        """純 Python 的日誌重建器，只在最後跑一次以輸出人類可讀的報表"""
        print("\n📝 --- 任務執行清單 (Mission Plan) ---")
        burn_logs, times = reconstruct_mission_logs(
            x, num_burns, self.MIN_COAST_TIME, self.T_max,
            self.A_r0, self.A_v0, self.B_r0, self.B_v0,
            self.MU, self.J2_VAL, self.RE_VAL
        )
        
        print(f"任務開始後等待: {x[0]:.1f} 秒")
        for log in burn_logs:
            print(f"  [{log['type']}] 時間: {log['time']:.1f}s | 推力: {np.round(log['dv_vnb'], 3)} km/s | 大小: {log['dv_mag']*1000:.1f} m/s")

        burns = [log['dv_vnb'] for log in burn_logs]
        times_diff = np.diff(times).tolist()
        # 回傳給最外層的 script_generator 使用
        return burns, times_diff, (x, num_burns)

# --- 放在同一個檔案或 mission_evaluator.py 中的輔助函式 ---
def reconstruct_mission_logs(x, num_burns, min_coast_time, T_max, A_r0, A_v0, B_r0, B_v0, mu, j2_val, re_val):
    """
    一步一步重播最佳解，並把 VNB 轉換和時間記錄下來。
    因為不用 JIT，可以盡情使用 list 和 dict。
    """
    burn_logs = []
    times = [0.0]
    dt = 60.0
    
    current_time = float(x[0])
    times.append(current_time)
    r_curr, v_curr = propagate_rk4(B_r0, B_v0, current_time, dt, mu, j2_val, re_val)
    
    idx = 1
    for i in range(1, num_burns):
        dv_vec = np.array([x[idx], x[idx+1], x[idx+2]])
        coast_frac = x[idx+3]
        idx += 4
        
        dv_mag = fast_norm(dv_vec)
        dv_vnb = to_vnb_frame(r_curr, v_curr, dv_vec)
        
        burn_logs.append({"time": current_time, "dv_vec": dv_vec, "dv_vnb": dv_vnb, "dv_mag": dv_mag, "type": f"Burn {i}"})
        v_curr_new = v_curr + dv_vec
        
        max_coast = T_max - current_time - min_coast_time
        t_coast = min_coast_time + coast_frac * (max_coast - min_coast_time) if max_coast > min_coast_time else min_coast_time
        
        r_curr, v_curr = propagate_rk4(r_curr, v_curr_new, t_coast, dt, mu, j2_val, re_val)
        current_time += t_coast
        times.append(current_time)
        
    final_leg_frac = x[-1]
    max_final = T_max - current_time
    t_final_leg = min_coast_time + final_leg_frac * (max_final - min_coast_time) if max_final > min_coast_time else min_coast_time
    intercept_time = current_time + t_final_leg
    
    r_A_target, _ = propagate_rk4(A_r0, A_v0, intercept_time, dt, mu, j2_val, re_val)
    v1_req, _ = izzo(mu, r_curr, r_A_target, t_final_leg, M=0, prograde=True, lowpath=True, numiter=35, rtol=1e-8)
    
    dv_final_vec = v1_req - v_curr
    dv_final_mag = fast_norm(dv_final_vec)
    dv_final_vnb = to_vnb_frame(r_curr, v_curr, dv_final_vec)
    
    burn_logs.append({"time": current_time, "dv_vec": dv_final_vec, "dv_vnb": dv_final_vnb, "dv_mag": dv_final_mag, "type": "Final Burn"})
    times.append(intercept_time)
    
    return burn_logs, times