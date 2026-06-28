import math
import torch
import numpy as np

# pymoo 核心套件
from pymoo.core.problem import Problem
from pymoo.algorithms.soo.nonconvex.de import DE
from pymoo.optimize import minimize
from pymoo.termination import get_termination

# 引入我們修好的三個模組
from batched_propagator import GPUOrbitPropagator
from batched_physics_engine import GPUPhysicsEngine
from batched_scorer import GPUCompetitionScorer

class PyMooOrbitProblem(Problem):
    """將我們的 GPU 引擎包裝成 pymoo 看得懂的格式"""
    def __init__(self, optimizer):
        # 所有的參數我們都在 decode_batch 中映射，所以這裡 bounds 一律是 [0, 1]
        super().__init__(
            n_var=optimizer.num_params, 
            n_obj=1, 
            n_ieq_constr=0, 
            xl=0.0, 
            xu=1.0
        )
        self.opt = optimizer

    def _evaluate(self, X, out, *args, **kwargs):
        # 1. X 是 NumPy 陣列 (pop_size, num_params)，將其轉為 GPU 張量
        x_tensor = torch.tensor(X, dtype=torch.float32, device=self.opt.device)
        
        # 2. 呼叫我們寫好的 GPU 批次運算 (關閉梯度計算節省記憶體)
        with torch.no_grad():
            minus_scores = self.opt.objective_batch(x_tensor)
            
        # 3. 將結果轉回 NumPy 丟給 pymoo (pymoo 是找最小值，所以我們回傳 -score)
        out["F"] = minus_scores.cpu().numpy().reshape(-1, 1)


class MissionOptimizer:
    def __init__(self, orbit_a_params, orbit_b_params, max_burns):
        if torch.backends.mps.is_available():
            self.device = torch.device("mps")
            print("✅ 核心引擎: 使用 Apple Silicon GPU (MPS) 加速")
        elif torch.cuda.is_available():
            self.device = torch.device("cuda")
            print("✅ 核心引擎: 使用 CUDA GPU 加速")
        else:
            self.device = torch.device("cpu")
            print("✅ 核心引擎: 使用 CPU 運行")

        # 取得單一初始狀態 (1, 3)
        self.r_A0, self.v_A0 = GPUOrbitPropagator.elements_to_vectors(
            sma=orbit_a_params["SMA"], ecc=orbit_a_params["ECC"],
            inc=orbit_a_params["INC"], raan=orbit_a_params["RAAN"],
            aop=orbit_a_params["AOP"], ta=orbit_a_params["TA"], device=self.device
        )
        self.r_B0, self.v_B0 = GPUOrbitPropagator.elements_to_vectors(
            sma=orbit_b_params["SMA"], ecc=orbit_b_params["ECC"],
            inc=orbit_b_params["INC"], raan=orbit_b_params["RAAN"],
            aop=orbit_b_params["AOP"], ta=orbit_b_params["TA"], device=self.device
        )

        sma = orbit_a_params["SMA"]
        self.Ta_sec = 2.0 * math.pi * math.sqrt(math.pow(sma, 3) / GPUPhysicsEngine.MU)
        self.T_max = self.Ta_sec * 4.0
        self.max_burns = max_burns

        # 動態計算所需參數維度
        self.num_params = 2 + (max_burns - 1) * 4 + 1

    def decode_batch(self, x_batch):
        """將 [0, 1] 虛擬參數，還原映射回真實的物理範圍"""
        pop_size = x_batch.shape[0]
        
        num_burns = torch.floor(x_batch[:, 0] * self.max_burns).long() + 1
        num_burns = torch.clamp(num_burns, 1, self.max_burns)
        
        t_wait = x_batch[:, 1] * (0.5 * self.T_max)
        
        dv_vecs = torch.zeros((pop_size, self.max_burns, 3), device=self.device)
        t_coasts = torch.zeros((pop_size, self.max_burns), device=self.device)
        
        idx = 2
        current_times = t_wait.clone()
        
        for i in range(self.max_burns - 1):
            mask = num_burns > (i + 1)
            dv_raw = x_batch[:, idx:idx+3]
            dv = (dv_raw * 2.0 - 1.0) * GPUPhysicsEngine.MAX_DV
            coast_frac = x_batch[:, idx+3]
            idx += 4
            
            max_coast = (self.T_max - current_times - 100.0).clamp(min=100.0)
            t_coast = 100.0 + coast_frac * (max_coast - 100.0)
            
            dv_vecs[mask, i, :] = dv[mask]
            t_coasts[mask, i] = t_coast[mask]
            current_times += t_coast * mask.float()
            
        final_leg_frac = x_batch[:, -1]
        max_final = (self.T_max - current_times - 100.0).clamp(min=100.0)
        t_final_leg = 100.0 + final_leg_frac * max_final
        
        return num_burns, t_wait, dv_vecs, t_coasts, t_final_leg

    def objective_batch(self, x_batch):
        pop_size = x_batch.shape[0]
        
        r_B0_batch = self.r_B0.repeat(pop_size, 1)
        v_B0_batch = self.v_B0.repeat(pop_size, 1)
        r_A0_batch = self.r_A0.repeat(pop_size, 1)
        v_A0_batch = self.v_A0.repeat(pop_size, 1)

        num_burns, t_wait, dv_vecs, t_coasts, t_final_leg = self.decode_batch(x_batch)
        
        r_curr, v_curr = GPUOrbitPropagator.propagate_batch(r_B0_batch, v_B0_batch, t_wait.unsqueeze(1))
        
        total_dv = torch.zeros(pop_size, device=self.device)
        penalty_count = torch.zeros(pop_size, device=self.device)
        
        # 【新增】：追蹤是否撞毀的布林遮罩
        crashed = torch.zeros(pop_size, dtype=torch.bool, device=self.device)
        
        for i in range(self.max_burns - 1):
            dv_mag = torch.norm(dv_vecs[:, i, :], dim=-1)
            total_dv += dv_mag
            penalty_count += (dv_mag > GPUPhysicsEngine.MAX_DV).float()
            v_curr += dv_vecs[:, i, :]
            
            r_curr, v_curr = GPUOrbitPropagator.propagate_batch(r_curr, v_curr, t_coasts[:, i].unsqueeze(1))
            # 檢查中間過程是否撞毀
            crashed |= (torch.norm(r_curr, dim=-1) < GPUPhysicsEngine.MIN_PERIAPSIS)
        
        intercept_time = t_wait + t_coasts.sum(dim=1) + t_final_leg
        r_target, _ = GPUOrbitPropagator.propagate_batch(r_A0_batch, v_A0_batch, intercept_time.unsqueeze(1))
        
        v1_req, _, _, dv_final_mag_2d = GPUPhysicsEngine.solve_lambert(r_curr, v_curr, r_target, t_final_leg.unsqueeze(1))
        dv_final_mag = dv_final_mag_2d.squeeze()
        total_dv += dv_final_mag
        
        # 安全檢查
        is_safe, _ = GPUPhysicsEngine.check_constraints(r_curr, v1_req, dv_final_mag_2d)
        penalty_count += (~is_safe).float()
        
        dist = torch.zeros_like(dv_final_mag)
        failed_lambert = dv_final_mag > 90000.0
        dist[failed_lambert] = torch.norm(r_curr - r_target, dim=-1)[failed_lambert]
        
        # ... (前面的 Lambert 求解與 dist 計算保持不變) ...
        
        # 1. 取得原本的 0~100 基礎分數 (包含 -10 的基礎違規扣分)
        scores = GPUCompetitionScorer.calculate_score(dist, intercept_time, total_dv, penalty_count)
        
        # 2. 【魔法梯度】：計算到底超出了多少燃料限制？
        dv_excess = torch.relu(total_dv - GPUPhysicsEngine.MAX_DV)
        
        # 3. 連續重罰：每超出 1 km/s，就額外扣 50 分！
        # 這會把那些光速太空船的分數打到負幾萬分，產生極其明確的下坡梯度
        # scores = scores - (dv_excess * 5)
        
        # 4. 如果真的撞毀地球或 Lambert 算不出來，再給予致命的底線懲罰
        crashed = failed_lambert | (torch.norm(r_curr, dim=-1) < GPUPhysicsEngine.MIN_PERIAPSIS)
        scores = torch.where(crashed, scores - 1000.0, scores) 
        
        # 回傳負分供 pymoo 尋找最小值
        return -scores

    def run_pymoo_optimization(self, pop_size=1000, max_gen=100):
        print(f"\n🚀 啟動 pymoo DE 軌道最佳化 (GPU 批次加速版)")
        print(f"族群大小: {pop_size} | 最大迭代: {max_gen}")

        problem = PyMooOrbitProblem(self)
        
        # 使用你原本 CPU 版用得最順手的 DE (差分進化) 演算法
        algorithm = DE(
            pop_size=pop_size,
            variant="DE/rand/1/bin", 
            CR=0.7,  # 交配機率
            F=0.8,   # 突變權重
        )

        termination = get_termination("n_gen", max_gen)

        res = minimize(
            problem,
            algorithm,
            termination,
            seed=42,
            save_history=False,
            verbose=True  # 開啟 pymoo 的預設進度條，超好看！
        )

        best_score = -res.F[0]
        print("\n✨ 最佳化完成！")
        print(f"🏆 最高得分: {best_score:.4f}")
        
        return res.X, best_score

# =========================================
# 快速沙盒測試區 
# =========================================
if __name__ == "__main__":
    test_config = {
        "orbit_A": {"SMA": 9000.0, "ECC": 0.0, "INC": 0.0, "RAAN": 0.0, "AOP": 0.0, "TA": 120.0},
        "orbit_B": {"SMA": 7500.0, "ECC": 0.0, "INC": 0.0, "RAAN": 0.0, "AOP": 0.0, "TA": 0.0},
        "optimization": {"MAX_BURNS":1, "POPSIZE": 10000} 
    }
    
    optimizer = MissionOptimizer(
        orbit_a_params=test_config["orbit_A"],
        orbit_b_params=test_config["orbit_B"],
        max_burns=test_config["optimization"]["MAX_BURNS"],
    )
    
    import time
    start = time.time()
    
    # 執行 pymoo 最佳化！我們把 Pop size 開到 2000，榨乾 GPU 的效能
    best_x, best_score = optimizer.run_pymoo_optimization(
        pop_size=test_config["optimization"]["POPSIZE"], 
        max_gen=20
    )
    
    print(f"總耗時: {time.time() - start:.2f} 秒")