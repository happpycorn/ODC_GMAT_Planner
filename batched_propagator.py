import torch
from batched_physics_engine import GPUPhysicsEngine

class GPUOrbitPropagator:
    MU = torch.tensor(398600.4418, dtype=torch.float32)

    @staticmethod
    def propagate_batch(r0, v0, dt, max_iters = 50, tol = 1e-6):
        """
        r0: (N, 3), v0: (N, 3), dt: (N, 1)
        """
        r0_mag = torch.norm(r0, dim=-1, keepdim=True)
        v0_mag = torch.norm(v0, dim=-1, keepdim=True)
        vr0 = torch.sum(r0 * v0, dim=-1, keepdim=True) / r0_mag
        
        alpha = 2.0 / r0_mag - v0_mag**2 / GPUOrbitPropagator.MU
        
        chi = torch.zeros_like(r0_mag)
        
        for _ in range(max_iters):
            z = (chi**2) * alpha
            C, S = GPUPhysicsEngine.stumpff_functions(z)

            dt_calc = (r0_mag * vr0 / torch.sqrt(GPUOrbitPropagator.MU) * chi**2 * C + 
                       (1 - alpha * r0_mag) * chi**3 * S + r0_mag * chi) / torch.sqrt(GPUOrbitPropagator.MU)

            # 2. 安全除法：加上一個極小值 1e-8 防止分母為零導致 NaN
            denominator = (r0_mag * chi**2 * S + (1 - alpha * r0_mag) * chi**2 * C + r0_mag) + 1e-8
            dchi = (dt - dt_calc) / denominator 
            
            # 3. 避免一次步進太大導致發散 (可以限制單次更新的最大值)
            dchi = torch.clamp(dchi, -100.0, 100.0)
            
            chi = chi + dchi

            if torch.max(torch.abs(dchi)) < tol: break

        z = (chi**2) * alpha
        C, S = GPUPhysicsEngine.stumpff_functions(z)
        
        f = 1 - (chi**2 / r0_mag) * C
        g = dt - (1 / torch.sqrt(GPUOrbitPropagator.MU)) * (chi**3 * S)

        r = f * r0 + g * v0
        r_mag = torch.norm(r, dim=-1, keepdim=True)
        
        f_dot = (torch.sqrt(GPUOrbitPropagator.MU) / (r0_mag * r_mag)) * (z * S - 1) * chi
        g_dot = 1 - (chi**2 / r_mag) * C

        r = f * r0 + g * v0
        v = f_dot * r0 + g_dot * v0
        
        return r, v
    
    @staticmethod
    def elements_to_vectors(sma, ecc, inc, raan, aop, ta, device=None):
        """
        將軌道根數 (Classical Orbital Elements) 轉換為 ECI 狀態向量 (r, v)
        """
        if device is None:
            device = torch.device("cpu")

        # 【關鍵修復 1】: 強制把所有輸入都轉成 1D 張量 (N,)
        def to_tensor(val):
            if not isinstance(val, torch.Tensor):
                val = torch.tensor(val, dtype=torch.float32, device=device)
            return val.view(-1).to(device) 

        sma = to_tensor(sma)
        ecc = to_tensor(ecc)
        inc = to_tensor(inc)
        raan = to_tensor(raan)
        aop = to_tensor(aop)
        ta = to_tensor(ta)

        # 轉為弧度
        inc, raan, aop, ta = map(torch.deg2rad, [inc, raan, aop, ta])
        
        # 1. 軌道平面內座標 (r_pqw, v_pqw)
        p = sma * (1.0 - ecc**2)
        r_mag = p / (1.0 + ecc * torch.cos(ta))
        
        # 【關鍵修復 2】: 加上 .unsqueeze(1)，讓 (N,) 變成 (N, 1)，完美對齊 (N, 3)！
        r_pqw = r_mag.unsqueeze(1) * torch.stack([torch.cos(ta), torch.sin(ta), torch.zeros_like(ta)], dim=1)
        
        mu_dev = torch.tensor(398600.4418, dtype=torch.float32, device=device)
        v_pqw = torch.sqrt(mu_dev / p).unsqueeze(1) * torch.stack([-torch.sin(ta), ecc + torch.cos(ta), torch.zeros_like(ta)], dim=1)
        
        # 2. 展開後的旋轉矩陣係數 (R = Rz(raan) * Rx(inc) * Rz(aop))
        cO, sO = torch.cos(raan), torch.sin(raan)
        ci, si = torch.cos(inc), torch.sin(inc)
        cw, sw = torch.cos(aop), torch.sin(aop)
        
        r11 = cO * cw - sO * sw * ci
        r12 = -cO * sw - sO * cw * ci
        
        r21 = sO * cw + cO * sw * ci
        r22 = -sO * sw + cO * cw * ci
        
        r31 = sw * si
        r32 = cw * si
        
        # 3. 直接進行向量化旋轉 (ECI = R * PQW)
        r_eci = torch.stack([
            r11 * r_pqw[:, 0] + r12 * r_pqw[:, 1],
            r21 * r_pqw[:, 0] + r22 * r_pqw[:, 1],
            r31 * r_pqw[:, 0] + r32 * r_pqw[:, 1]
        ], dim=1)
        
        v_eci = torch.stack([
            r11 * v_pqw[:, 0] + r12 * v_pqw[:, 1],
            r21 * v_pqw[:, 0] + r22 * v_pqw[:, 1],
            r31 * v_pqw[:, 0] + r32 * v_pqw[:, 1]
        ], dim=1)
        
        return r_eci, v_eci

if __name__ == "__main__":
    import time

    # 1. 裝置設定
    if torch.backends.mps.is_available():
        device = torch.device("mps")
        print("✅ 使用 Apple Silicon GPU (MPS) 進行測試")
    elif torch.cuda.is_available():
        device = torch.device("cuda")
        print("✅ 使用 CUDA GPU 進行測試")
    else:
        device = torch.device("cpu")
        print("✅ 使用 CPU 進行測試")

    print("\n=== 測試 1: 軌道根數轉換 (支援標量與批次) ===")
    try:
        # 模擬主程式傳進來的單一字典數值
        r_single, v_single = GPUOrbitPropagator.elements_to_vectors(
            sma=9000.0, ecc=0.0, inc=30.0, raan=45.0, aop=0.0, ta=120.0, device=device
        )
        print("✔️ 單一軌道轉換成功！ Shape:", r_single.shape)

        # 批次壓力測試 (1000 個隨機軌道)
        N_batch = 1000
        r_batch, v_batch = GPUOrbitPropagator.elements_to_vectors(
            sma=torch.full((N_batch,), 9000.0),
            ecc=torch.rand(N_batch) * 0.5, 
            inc=torch.rand(N_batch) * 90.0,
            raan=torch.rand(N_batch) * 360.0,
            aop=torch.rand(N_batch) * 360.0,
            ta=torch.rand(N_batch) * 360.0,
            device=device
        )
        print(f"✔️ 批次軌道轉換成功！ r_batch Shape: {r_batch.shape}")
    except Exception as e:
        print(f"❌ 轉換失敗: {e}")

    print("\n=== 測試 2: Propagator 穩定度與 NaN 防護 ===")
    if 'r_batch' in locals():
        # 刻意給出包含極短與極長飛行時間的陣列來刁難牛頓法
        dt_batch = torch.empty((N_batch, 1), device=device)
        dt_batch[:N_batch//2] = torch.rand(N_batch//2, 1, device=device) * 10.0      # 0~10 秒
        dt_batch[N_batch//2:] = torch.rand(N_batch//2, 1, device=device) * 86400.0   # 長達一天的秒數

        start_time = time.time()
        r_future, v_future = GPUOrbitPropagator.propagate_batch(r_batch, v_batch, dt_batch)
        calc_time = time.time() - start_time
        
        nan_count = torch.isnan(r_future).sum().item()
        if nan_count == 0:
            print(f"✔️ 物理傳遞完成！完全沒有產生 NaN。耗時: {calc_time:.4f} 秒")
        else:
            print(f"❌ 警告：發現了 {nan_count} 個 NaN！")