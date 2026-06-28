import math
import torch
from poliastro.twobody import Orbit
from poliastro.bodies import Earth
from astropy import units as u

# 引入我們修好的三個模組
from batched_propagator import GPUOrbitPropagator
from batched_physics_engine import GPUPhysicsEngine
from batched_scorer import GPUCompetitionScorer

class MissionOptimizer:
    def __init__(self, orbit_a_params, orbit_b_params, max_burns, popsize, num_params):
        if torch.backends.mps.is_available():
            self.device = torch.device("mps")
            print("✅ 核心引擎: 使用 Apple Silicon GPU (MPS) 加速")
        elif torch.cuda.is_available():
            self.device = torch.device("cuda")
            print("✅ 核心引擎: 使用 CUDA GPU 加速")
        else:
            self.device = torch.device("cpu")
            print("✅ 核心引擎: 使用 CPU 運行")

        # 準備起點與目標的批次張量
        r_A0, v_A0 = GPUOrbitPropagator.elements_to_vectors(
            sma=orbit_a_params["SMA"], ecc=orbit_a_params["ECC"],
            inc=orbit_a_params["INC"], raan=orbit_a_params["RAAN"],
            aop=orbit_a_params["AOP"], ta=orbit_a_params["TA"], 
            device=self.device
        )
        self.r_A0_batch = r_A0.repeat(popsize, 1)
        self.v_A0_batch = v_A0.repeat(popsize, 1)

        r_B0, v_B0 = GPUOrbitPropagator.elements_to_vectors(
            sma=orbit_b_params["SMA"], ecc=orbit_b_params["ECC"],
            inc=orbit_b_params["INC"], raan=orbit_b_params["RAAN"],
            aop=orbit_b_params["AOP"], ta=orbit_b_params["TA"], 
            device=self.device
        )
        self.r_B0_batch = r_B0.repeat(popsize, 1)
        self.v_B0_batch = v_B0.repeat(popsize, 1)

        # 【修復 3】修正字典大小寫錯誤
        sma = orbit_a_params["SMA"]
        self.Ta_sec = 2.0 * math.pi * math.sqrt(math.pow(sma, 3) / GPUPhysicsEngine.MU)
        self.T_max = self.Ta_sec * 4.0
        self.max_burns = max_burns

        # 【修復 4】防呆：只使用真正需要的參數維度，避免 PSO 在無效維度上迷路
        self.actual_params_needed = 2 + (max_burns - 1) * 4 + 1
        if num_params < self.actual_params_needed:
            print(f"⚠️ 警告: 設定檔的 NUM_PARAMS ({num_params}) 太小，已自動擴展為 {self.actual_params_needed}")
            num_params = self.actual_params_needed
        self.num_params = num_params

        # 初始化粒子群 (限制在 [0, 1] 之間，之後靠 decode_batch 放大到物理尺度)
        self.pos = torch.rand(popsize, self.num_params, device=self.device)
        self.vel = torch.zeros(popsize, self.num_params, device=self.device)

        self.pbest_pos = self.pos.clone()
        self.pbest_score = torch.full((popsize,), float('inf'), device=self.device)
        self.gbest_pos = torch.zeros(self.num_params, device=self.device)
        self.gbest_score = float('inf')

    def decode_batch(self, x_batch, max_burns, T_max):
        """
        將 PSO 的 [0, 1] 虛擬參數，還原映射回真實的物理範圍
        """
        pop_size = x_batch.shape[0]
        device = x_batch.device
        
        # 【修復 1】正確映射點火次數：將 [0, 1) 映射到 1 ~ max_burns 的整數
        num_burns = torch.floor(x_batch[:, 0] * max_burns).long() + 1
        num_burns = torch.clamp(num_burns, 1, max_burns)
        
        # 映射等待時間 (最多等半個最大週期)
        t_wait = x_batch[:, 1] * (0.5 * T_max)
        
        dv_vecs = torch.zeros((pop_size, max_burns, 3), device=device)
        t_coasts = torch.zeros((pop_size, max_burns), device=device)
        
        idx = 2
        current_times = t_wait.clone()
        
        for i in range(max_burns - 1):
            mask = num_burns > (i + 1)
            
            # 【修復 1】將 [0, 1] 映射到 [-MAX_DV, MAX_DV]，允許各方向加減速
            dv_raw = x_batch[:, idx:idx+3]
            dv = (dv_raw * 2.0 - 1.0) * GPUPhysicsEngine.MAX_DV
            
            coast_frac = x_batch[:, idx+3]
            idx += 4
            
            max_coast = (T_max - current_times - 100.0).clamp(min=100.0)
            t_coast = 100.0 + coast_frac * (max_coast - 100.0)
            
            dv_vecs[mask, i, :] = dv[mask]
            t_coasts[mask, i] = t_coast[mask]
            current_times += t_coast * mask.float()
            
        final_leg_frac = x_batch[:, -1]
        max_final = (T_max - current_times - 100.0).clamp(min=100.0)
        t_final_leg = 100.0 + final_leg_frac * max_final
        
        return num_burns, t_wait, dv_vecs, t_coasts, t_final_leg

    def objective_batch(self, x_batch, r_B0, v_B0, r_A0, v_A0):
        # 1. 解碼參數
        num_burns, t_wait, dv_vecs, t_coasts, t_final_leg = self.decode_batch(x_batch, self.max_burns, self.T_max)
        
        # 【修復 2】補上 .unsqueeze(1) 讓時間從 (N,) 變成 (N, 1)
        r_curr, v_curr = GPUOrbitPropagator.propagate_batch(r_B0, v_B0, t_wait.unsqueeze(1))
        
        total_dv = torch.zeros(x_batch.size(0), device=self.device)
        penalty_count = torch.zeros(x_batch.size(0), device=self.device)
        
        for i in range(self.max_burns - 1):
            dv_mag = torch.norm(dv_vecs[:, i, :], dim=-1)
            total_dv += dv_mag
            penalty_count += (dv_mag > GPUPhysicsEngine.MAX_DV).float()
            
            v_curr += dv_vecs[:, i, :]
            
            # 【修復 2】補上 .unsqueeze(1)
            r_curr, v_curr = GPUOrbitPropagator.propagate_batch(r_curr, v_curr, t_coasts[:, i].unsqueeze(1))
            
            # 碰撞檢查 (低於地表高度視為碰撞)
            penalty_count += (torch.norm(r_curr, dim=-1) < GPUPhysicsEngine.EARTH_RADIUS).float() * 10.0
        
        intercept_time = t_wait + t_coasts.sum(dim=1) + t_final_leg
        
        # 【修復 2】補上 .unsqueeze(1)
        r_target, _ = GPUOrbitPropagator.propagate_batch(r_A0, v_A0, intercept_time.unsqueeze(1))
        
        # 5. Lambert 求解器 
        v1_req, _, _, dv_final_mag_2d = GPUPhysicsEngine.solve_lambert(r_curr, v_curr, r_target, t_final_leg.unsqueeze(1))
        dv_final_mag = dv_final_mag_2d.squeeze()
        
        total_dv += dv_final_mag
        
        # 【連續梯度修復】將二元懲罰轉換為連續斜率
        is_safe, _ = GPUPhysicsEngine.check_constraints(r_curr, v1_req, dv_final_mag_2d)
        
        # 計算具體超出的 Delta-V 數值 (低於 MAX_DV 則為 0)
        dv_excess = torch.relu(dv_final_mag - GPUPhysicsEngine.MAX_DV)
        
        # 疊加嚴重程度：違規基本扣分 + 超出量的比例懲罰
        penalty_count += (~is_safe).float() + dv_excess * 2.0
        
        dist = torch.zeros_like(dv_final_mag)
        failed_lambert = dv_final_mag > 90000.0
        dist[failed_lambert] = torch.norm(r_curr - r_target, dim=-1)[failed_lambert]
        
        scores = GPUCompetitionScorer.calculate_score(dist, intercept_time, total_dv, penalty_count)
        
        return -scores
    
    def optimize_step(self, w=0.5, c1=1.5, c2=1.5):
        scores = self.objective_batch(self.pos, self.r_B0_batch, self.v_B0_batch, self.r_A0_batch, self.v_A0_batch)
        
        improved = scores < self.pbest_score
        self.pbest_pos[improved] = self.pos[improved].clone()
        self.pbest_score[improved] = scores[improved]
        
        min_score, min_idx = torch.min(self.pbest_score, dim=0)
        if min_score < self.gbest_score:
            self.gbest_score = min_score.item()
            self.gbest_pos = self.pbest_pos[min_idx].clone()
        
        r1 = torch.rand_like(self.pos)
        r2 = torch.rand_like(self.pos)
        
        self.vel = (w * self.vel) + \
                   (c1 * r1 * (self.pbest_pos - self.pos)) + \
                   (c2 * r2 * (self.gbest_pos - self.pos))
        
        self.pos = torch.clamp(self.pos + self.vel, 0.0, 1.0)
        
        return self.gbest_score, self.gbest_pos

# =========================================
# 快速沙盒測試區 (直接測試整個 PSO 系統)
# =========================================
if __name__ == "__main__":
    print("\n" + "="*50)
    print("🚀 核心整合測試: GPU 軌道攔截最佳化引擎")
    print("="*50)
    
    # 模擬主程式的 config
    test_config = {
        "orbit_A": {"SMA": 9000.0, "ECC": 0.0, "INC": 0.0, "RAAN": 0.0, "AOP": 0.0, "TA": 120.0},
        "orbit_B": {"SMA": 7500.0, "ECC": 0.0, "INC": 0.0, "RAAN": 0.0, "AOP": 0.0, "TA": 0.0},
        "optimization": {"MAX_BURNS": 4, "POPSIZE": 1000, "NUM_PARAMS": 30} # 適當的參數數量
    }
    
    # 初始化引擎 (1000 個粒子)
    optimizer = MissionOptimizer(
        orbit_a_params=test_config["orbit_A"],
        orbit_b_params=test_config["orbit_B"],
        max_burns=test_config["optimization"]["MAX_BURNS"],
        popsize=test_config["optimization"]["POPSIZE"],
        num_params=test_config["optimization"]["NUM_PARAMS"],
    )
    
    print("\n⏳ 開始執行 PSO 演化測試 (100 代)...")
    import time
    start = time.time()
    
    for i in range(100):
        # 隨著迭代降低慣性，幫助收斂
        w = 0.9 - (0.5 * (i / 100.0))
        best_score, best_pos = optimizer.optimize_step(w=w)
        
        if (i+1) % 20 == 0:
            # 將負分轉正印出
            print(f"迭代 {i+1:03d} | 目前全域最高分: {-best_score:>8.2f} 分")
            
    print(f"\n⏱️ 測試完成！總耗時: {time.time() - start:.2f} 秒")
    print(f"🏁 最佳策略參數已找到 (維度: {best_pos.shape[0]})")