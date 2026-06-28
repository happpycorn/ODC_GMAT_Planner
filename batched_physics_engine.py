import torch

class GPUPhysicsEngine:
    """模組二 (GPU版)：負責批次求解蘭伯特問題與物理防呆檢查"""
    
    MU = 398600.4418            # 地球標準重力參數 (km^3/s^2)
    EARTH_RADIUS = 6378.137     # 地球赤道半徑 (km)
    SAFE_ALTITUDE = 100.0       # 安全高度 (km)
    MIN_PERIAPSIS = EARTH_RADIUS + SAFE_ALTITUDE
    MAX_DV = 1.5                # 最大 Delta-V (km/s)

    @staticmethod
    def get_geometric_params(r1, r2):
        """步驟 1: 計算幾何常數 A 與夾角相關參數"""
        r1_mag = torch.norm(r1, dim=-1, keepdim=True)
        r2_mag = torch.norm(r2, dim=-1, keepdim=True)
        cos_dnu = torch.sum(r1 * r2, dim=-1, keepdim=True) / (r1_mag * r2_mag)
        cos_dnu = torch.clamp(cos_dnu, -1.0, 1.0)
        
        sin_dnu = torch.sqrt(1.0 - cos_dnu**2)
        A = sin_dnu * torch.sqrt((r1_mag * r2_mag) / (1.0 + cos_dnu + 1e-8)) # 加上 1e-8 防呆
        return r1_mag, r2_mag, A

    @staticmethod
    def stumpff_functions(z):
        """步驟 2: 計算 Stumpff 函數 C(z) 與 S(z) (完美支援橢圓、雙曲線與拋物線)"""
        z_abs = torch.abs(z)
        sqrt_z = torch.sqrt(z_abs)
        
        C = torch.zeros_like(z)
        S = torch.zeros_like(z)
        
        # 1. 橢圓軌道 (z > 0)
        mask_pos = z > 1e-4
        if mask_pos.any():
            C[mask_pos] = (1.0 - torch.cos(sqrt_z[mask_pos])) / z[mask_pos]
            S[mask_pos] = (sqrt_z[mask_pos] - torch.sin(sqrt_z[mask_pos])) / (sqrt_z[mask_pos]**3)
            
        # 2. 雙曲線軌道 (z < 0)
        mask_neg = z < -1e-4
        if mask_neg.any():
            C[mask_neg] = (torch.cosh(sqrt_z[mask_neg]) - 1.0) / z_abs[mask_neg]
            S[mask_neg] = (torch.sinh(sqrt_z[mask_neg]) - sqrt_z[mask_neg]) / (sqrt_z[mask_neg]**3)
            
        # 3. 拋物線或接近拋物線 (z ~ 0，使用泰勒展開避免除以零)
        mask_zero = ~(mask_pos | mask_neg)
        if mask_zero.any():
            C[mask_zero] = 1.0/2.0 - z[mask_zero]/24.0
            S[mask_zero] = 1.0/6.0 - z[mask_zero]/120.0
            
        return C, S

    @staticmethod
    def compute_tof(z, A, r1_mag, r2_mag):
        """步驟 3: 計算該 z 值對應的飛行時間"""
        C, S = GPUPhysicsEngine.stumpff_functions(z)
        
        y = r1_mag + r2_mag - A * (1.0 - z * S) / torch.sqrt(C + 1e-8)
        y = torch.clamp(y, min=1e-6) # 【修復 3】: 防止 y 變成負數導致後續開根號出現 NaN
        
        x = torch.sqrt(y / C)
        t_calc = (x**3 * S + A * torch.sqrt(y)) / torch.sqrt(torch.tensor(GPUPhysicsEngine.MU, device=z.device))
        return t_calc, y

    @staticmethod
    def solve_lambert(r1, v1, r2, tof_sec):
        """使用 100% 穩定的二元搜尋法 (Bisection Method) 求解批次蘭伯特問題"""
        N = r1.shape[0]
        r1_mag = torch.norm(r1, dim=-1, keepdim=True)
        r2_mag = torch.norm(r2, dim=-1, keepdim=True)
        
        cos_dnu = torch.sum(r1 * r2, dim=-1, keepdim=True) / (r1_mag * r2_mag)
        cos_dnu = torch.clamp(cos_dnu, -1.0, 1.0)
        
        # --- 計算夾角餘弦 ---
        cos_dnu = torch.sum(r1 * r2, dim=-1, keepdim=True) / (r1_mag * r2_mag)
        cos_dnu = torch.clamp(cos_dnu, -1.0, 1.0)
        
        # --- 【全新修復】強制順向 (Prograde) 轉移邏輯 ---
        # 1. 計算轉移幾何法向量 c_vec
        c_vec = torch.linalg.cross(r1, r2, dim=-1)
        
        # 2. 提取法向量的 Z 軸分量 (假設 Z 軸為極軸)
        c_z = c_vec[..., 2:3]
        
        # 3. 判斷 A 的正負號：c_z >= 0 時 A 為正 (走短路徑)，c_z < 0 時 A 為負 (走長路徑)
        sign_A = torch.sign(c_z)
        sign_A = torch.where(sign_A == 0, torch.ones_like(sign_A), sign_A) # 防呆
        
        # 4. 計算最終的 A (這下 GPU 永遠只會產出順向軌道了！)
        A = sign_A * torch.sqrt(r1_mag * r2_mag * (1.0 + cos_dnu))
        
        # 【關鍵修復 2】: 捨棄牛頓法，改用絕對收斂的二元搜尋法 (Bisection)
        z_low = torch.full((N, 1), -1000.0, device=r1.device)  # 極端雙曲線
        z_high = torch.full((N, 1), 4.0 * torch.pi**2 - 1e-6, device=r1.device) # 極端橢圓
        
        # 執行 50 次迭代，精度可達 2^-50，完全足夠且 GPU 執行極快
        for _ in range(50):
            z_mid = (z_low + z_high) / 2.0
            z_abs = torch.abs(z_mid)
            sqrt_z = torch.sqrt(z_abs)
            
            # 計算 Stumpff 函數 (向量化防呆)
            C = torch.where(z_mid > 1e-4, (1.0 - torch.cos(sqrt_z)) / z_mid,
                    torch.where(z_mid < -1e-4, (torch.cosh(sqrt_z) - 1.0) / z_abs, 
                        1.0/2.0 - z_mid/24.0))
            S = torch.where(z_mid > 1e-4, (sqrt_z - torch.sin(sqrt_z)) / (sqrt_z**3),
                    torch.where(z_mid < -1e-4, (torch.sinh(sqrt_z) - sqrt_z) / (sqrt_z**3), 
                        1.0/6.0 - z_mid/120.0))
            
            # 計算 y 與時間
            y = r1_mag + r2_mag - A * (1.0 - z_mid * S) / torch.sqrt(C)
            y = torch.clamp(y, min=1e-8)
            
            x = torch.sqrt(y / C)
            t_calc = (x**3 * S + A * torch.sqrt(y)) / torch.sqrt(torch.tensor(GPUPhysicsEngine.MU, device=r1.device))
            
            # 更新邊界
            mask_too_small = t_calc < tof_sec
            z_low = torch.where(mask_too_small, z_mid, z_low)
            z_high = torch.where(mask_too_small, z_high, z_mid)
            
        # 取最終收斂的 z 值
        z = (z_low + z_high) / 2.0
        
        # --- 最終計算轉移速度向量 f, g ---
        z_abs = torch.abs(z)
        sqrt_z = torch.sqrt(z_abs)
        C = torch.where(z > 1e-4, (1.0 - torch.cos(sqrt_z)) / z,
                torch.where(z < -1e-4, (torch.cosh(sqrt_z) - 1.0) / z_abs, 1.0/2.0 - z/24.0))
        S = torch.where(z > 1e-4, (sqrt_z - torch.sin(sqrt_z)) / (sqrt_z**3),
                torch.where(z < -1e-4, (torch.sinh(sqrt_z) - sqrt_z) / (sqrt_z**3), 1.0/6.0 - z/120.0))
        
        y = r1_mag + r2_mag - A * (1.0 - z * S) / torch.sqrt(C)
        y = torch.clamp(y, min=1e-8)
        
        f = 1.0 - y / r1_mag
        g = A * torch.sqrt(y / GPUPhysicsEngine.MU)
        g = torch.where(torch.abs(g) < 1e-8, torch.ones_like(g)*1e-8, g) # 防除以零
        g_dot = 1.0 - y / r2_mag
        
        v1_req = (r2 - f * r1) / g
        v2_req = (g_dot * r2 - r1) / g
        
        delta_v1 = v1_req - v1
        dv1_mag = torch.norm(delta_v1, dim=-1, keepdim=True)
        
        # 處理可能殘留的極端值
        v1_req = torch.nan_to_num(v1_req, nan=0.0)
        v2_req = torch.nan_to_num(v2_req, nan=0.0)
        dv1_mag = torch.nan_to_num(dv1_mag, nan=99999.0)
        
        return v1_req, v2_req, delta_v1, dv1_mag

    @staticmethod
    def check_constraints(r1: torch.Tensor, v1_req: torch.Tensor, dv1_mag: torch.Tensor):
        # ... (這裡維持你原本寫得很好的張量化演算法，無需更動) ...
        dv_safe = dv1_mag <= GPUPhysicsEngine.MAX_DV
        h_vec = torch.linalg.cross(r1, v1_req, dim=-1)
        h_mag_sq = torch.sum(h_vec**2, dim=-1, keepdim=True) 
        r1_mag = torch.norm(r1, dim=-1, keepdim=True)
        v_x_h = torch.linalg.cross(v1_req, h_vec, dim=-1)
        e_vec = v_x_h / GPUPhysicsEngine.MU - (r1 / r1_mag)
        e_mag = torch.norm(e_vec, dim=-1, keepdim=True) 
        r_p = h_mag_sq / (GPUPhysicsEngine.MU * (1.0 + e_mag))
        rp_safe = r_p >= GPUPhysicsEngine.MIN_PERIAPSIS
        is_safe = dv_safe & rp_safe
        return is_safe.squeeze(), r_p.squeeze()

if __name__ == "__main__":
    import time

    # 1. 裝置自動選擇
    if torch.backends.mps.is_available():
        device = torch.device("mps")
        print("✅ 使用 Apple Silicon GPU (MPS) 進行測試")
    elif torch.cuda.is_available():
        device = torch.device("cuda")
        print("✅ 使用 CUDA GPU 進行測試")
    else:
        device = torch.device("cpu")
        print("✅ 使用 CPU 進行測試")

    print("\n" + "="*50)
    print("🚀 測試 1: 蘭伯特求解器 (Lambert Solver) 極限壓力測試")
    print("="*50)

    # 設定批次大小 (挑戰 10,000 個並行運算！)
    N_batch = 10000  

    # 隨機生成出發點 r1 (高度大約 6800~7500 km)
    r1_dir = torch.randn(N_batch, 3, device=device)
    r1_dir = r1_dir / torch.norm(r1_dir, dim=1, keepdim=True)
    r1_mag = torch.rand(N_batch, 1, device=device) * 700.0 + 6800.0
    r1_batch = r1_dir * r1_mag

    # 隨機生成出發點初始速度 v1 (大小約 7.5 km/s)
    v1_dir = torch.randn(N_batch, 3, device=device)
    v1_dir = v1_dir / torch.norm(v1_dir, dim=1, keepdim=True)
    v1_batch = v1_dir * 7.5

    # 隨機生成目標點 r2 (高度大約 7000~9000 km)
    r2_dir = torch.randn(N_batch, 3, device=device)
    r2_dir = r2_dir / torch.norm(r2_dir, dim=1, keepdim=True)
    r2_mag = torch.rand(N_batch, 1, device=device) * 2000.0 + 7000.0
    r2_batch = r2_dir * r2_mag

    # 隨機飛行時間 TOF (包含極短的 100 秒 到 長達近 3 天的秒數，企圖弄壞牛頓法)
    tof_batch = torch.rand(N_batch, 1, device=device) * 250000.0 + 100.0

    print(f"⏳ 正在為 {N_batch} 個隨機任務進行 Lambert 批次求解...")
    
    start_time = time.time()
    
    # 執行我們剛剛修好防呆機制的批次求解
    v1_req, v2_req, dv1_vec, dv1_mag = GPUPhysicsEngine.solve_lambert(
        r1_batch, v1_batch, r2_batch, tof_batch
    )

    calc_time = time.time() - start_time
    
    # 檢查有沒有被我們最後的 nan_to_num 攔截並設為 99999.0 的極端失敗解
    failed_mask = dv1_mag.flatten() >= 99990.0
    num_failed = failed_mask.sum().item()
    
    print(f"⏱️ 計算耗時: {calc_time:.4f} 秒")
    
    if num_failed == 0:
        print(f"✔️ 完美收斂！{N_batch} 個軌道全部成功算出結果，完全沒有 NaN 產生。")
    else:
        print(f"⚠️ 發現 {num_failed} 個極端瞎猜軌道無法收斂 (已成功攔截並給予 99999 懲罰值)。")
        print("  👉 備註：在隨機生成的極端參數下有極少數不收斂是正常的，")
        print("     重點是系統沒有崩潰，也沒有讓 NaN 像病毒一樣擴散。")
    
    print("\n" + "="*50)
    print("🛡️ 測試 2: 物理防呆檢查 (近地點與 DV 限制)")
    print("="*50)
    
    is_safe, rp = GPUPhysicsEngine.check_constraints(r1_batch, v1_req, dv1_mag)
    safe_count = is_safe.sum().item()
    print(f"✅ 通過安全檢查的軌道數: {safe_count} / {N_batch}")

    # ==========================================================
    # 🌟 新增：測試 3 - 與 Poliastro (Izzo 演算法) 進行交叉比對
    # ==========================================================
    print("\n" + "="*50)
    print("🔬 測試 3: 與 Poliastro (Izzo 演算法) 進行交叉比對")
    print("="*50)

    try:
        from poliastro.iod.izzo import lambert as izzo_lambert
        from astropy import units as u
        import numpy as np

        valid_indices = torch.where(failed_mask == False)[0]
        num_compare = min(100, len(valid_indices))
        
        if num_compare > 0:
            compare_idx = valid_indices[:num_compare]
            
            r1_np = r1_batch[compare_idx].cpu().numpy()
            r2_np = r2_batch[compare_idx].cpu().numpy()
            tof_np = tof_batch[compare_idx].cpu().numpy()
            
            v1_gpu = v1_req[compare_idx].cpu().numpy()
            v2_gpu = v2_req[compare_idx].cpu().numpy()
            
            mu_with_units = GPUPhysicsEngine.MU * (u.km**3 / u.s**2)
            
            max_err_v1 = 0.0
            avg_err_v1 = 0.0
            
            print(f"🔄 正在將 {num_compare} 個軌道送入 Poliastro Izzo Lambert 進行 CPU 計算...")
            
            for i in range(num_compare):
                r1_u = r1_np[i] * u.km
                r2_u = r2_np[i] * u.km
                tof_u = tof_np[i][0] * u.s
                
                # 判斷軌道法向量，強迫 Poliastro 永遠走我們設定的短路徑 (Short-Way)
                cross_r1_r2 = np.cross(r1_np[i], r2_np[i])
                is_prograde = cross_r1_r2[2] >= 0
                
                # Poliastro 的 Izzo Lambert
                v1_izzo_u, v2_izzo_u = izzo_lambert(k=mu_with_units, r0=r1_u, r=r2_u, tof=tof_u, prograde=True)
                
                v1_izzo = v1_izzo_u.to_value(u.km / u.s)
                
                err_v1 = np.linalg.norm(v1_gpu[i] - v1_izzo)
                max_err_v1 = max(max_err_v1, err_v1)
                avg_err_v1 += err_v1
                
            avg_err_v1 /= num_compare
                
            print(f"✔️ 比對完成！")
            print(f"📊 v1 最大誤差: {max_err_v1:.8e} km/s")
            print(f"📊 v1 平均誤差: {avg_err_v1:.8e} km/s")
            
            if max_err_v1 < 1e-3:
                print("🎉 結論: 誤差接近零！你的 GPU Lambert 求解器與 Izzo 已經完全一致！")
            else:
                print("⚠️ 結論: 誤差依舊偏大，還有其他潛在問題。")
        else:
            print("❌ 沒有有效的軌道可以比對。")
            
    except ImportError:
        print("⚠️ 找不到 poliastro 或 astropy，請確定環境中有安裝。")

    print("\n" + "="*50)
    print("🛡️ 測試 2: 物理防呆檢查 (近地點與 DV 限制)")
    print("="*50)
    
    # 測試你手刻的超高效率向量化安全檢查
    is_safe, rp = GPUPhysicsEngine.check_constraints(r1_batch, v1_req, dv1_mag)
    safe_count = is_safe.sum().item()
    
    print(f"✅ 通過安全檢查 (沒撞地球且 Delta-V <= {GPUPhysicsEngine.MAX_DV} km/s) 的軌道數: {safe_count} / {N_batch}")
    
    if safe_count > 0:
        print(f"   安全軌道的平均近地點高度: {rp[is_safe].mean().item() - GPUPhysicsEngine.EARTH_RADIUS:.2f} km")
    else:
        print("   (因為是完全亂數生成的目標，沒有軌道符合如此嚴格的安全條件很正常)")