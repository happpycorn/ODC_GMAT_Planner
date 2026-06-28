import torch

class GPUCompetitionScorer:
    @staticmethod
    def calculate_score(
        min_distance_km: torch.Tensor, 
        total_time_sec: torch.Tensor, 
        total_dv_kms: torch.Tensor, 
        penalty_count: torch.Tensor,
        k_t: float = 0.0001, 
        C_t: float = 86400.0, 
        k_v: float = 5.0, 
        C_v: float = 3.0
    ) -> torch.Tensor:
        
        dr = torch.clamp(min_distance_km, min=5.0)
        score_dist = 50.0 * torch.exp(-(dr - 5.0) / 100.0)

        exp_time = torch.exp(torch.clamp(k_t * (total_time_sec - C_t), max=80.0))
        score_time = 25.0 / (1.0 + exp_time)

        exp_dv = torch.exp(torch.clamp(k_v * (total_dv_kms - C_v), max=80.0))
        score_dv = 25.0 / (1.0 + exp_dv)

        # 【完美還原】：只扣 10 分，不加碼毀滅性懲罰
        total_score = score_dist + score_time + score_dv - (penalty_count.float() * 10.0)
        
        # 【完美還原】：最低就是 0 分，創造平坦的探索荒原
        return torch.clamp(total_score, min=0.0)
    
if __name__ == "__main__":
    print("\n" + "="*50)
    print("🎯 測試 1: 競賽計分器 (Scorer) 情境與懲罰測試")
    print("="*50)

    # 1. 裝置自動選擇
    if torch.backends.mps.is_available():
        device = torch.device("mps")
    elif torch.cuda.is_available():
        device = torch.device("cuda")
    else:
        device = torch.device("cpu")

    # 建立 6 種極端情境來驗證計分邏輯
    # 情境: [完美解, 稍慢解, 耗燃料解, 稍微錯過, 完全飛走, 撞地球/超推力]
    N_tests = 6
    
    # 距離 (km)
    min_distance_km = torch.tensor([5.0, 5.0, 5.0, 100.0, 50000.0, 5.0], device=device)
    # 時間 (sec)
    total_time_sec = torch.tensor([86400.0, 150000.0, 86400.0, 86400.0, 86400.0, 86400.0], device=device)
    # 燃料 (km/s) - 注意這裡現在是 km/s
    total_dv_kms = torch.tensor([3.0, 3.0, 15.0, 3.0, 3.0, 3.0], device=device)
    # 違規次數
    penalty_count = torch.tensor([0, 0, 0, 0, 0, 1], device=device)

    labels = [
        "🏆 完美神級解 (距離5km, 1天, 3km/s)",
        "🐢 龜速到達解 (距離5km, 快2天, 3km/s)",
        "🔥 狂噴燃料解 (距離5km, 1天, 15km/s)",
        "🤏 稍微擦邊解 (距離100km, 1天, 3km/s)",
        "🌌 飛去外太空 (距離5萬km, 1天, 3km/s)",
        "💥 撞毀或違規 (完美到達但撞地球/超推力了)"
    ]

    scores = GPUCompetitionScorer.calculate_score(
        min_distance_km, total_time_sec, total_dv_kms, penalty_count
    )

    for i in range(N_tests):
        print(f"{labels[i]}")
        # 使用 :>10.2f 讓分數對齊，方便觀察
        print(f"   => 總分: {scores[i].item():>10.2f}\n")


    print("="*50)
    print("📉 測試 2: 梯度消失防護 (Gradient Survival Test)")
    print("="*50)
    # 驗證梯度：錯過 5 萬公里和錯過 10 萬公里的分數是否有差異 (確保沒有被 clamp 抹平)
    
    dr_bad = torch.tensor([50000.0, 100000.0], device=device)
    t_bad = torch.tensor([86400.0, 86400.0], device=device)
    dv_bad = torch.tensor([3.0, 3.0], device=device)
    pen_bad = torch.tensor([0, 0], device=device)
    
    bad_scores = GPUCompetitionScorer.calculate_score(dr_bad, t_bad, dv_bad, pen_bad)
    
    print(f"距離  5 萬公里得分: {bad_scores[0].item():>10.2f}")
    print(f"距離 10 萬公里得分: {bad_scores[1].item():>10.2f}")
    print("-" * 50)
    
    if bad_scores[0] > bad_scores[1]:
        print("✔️ 梯度正常！較近的瞎猜解分數，依然比更遠的瞎猜解高。")
        print("   PSO 雖然都在看負分，但它知道往分數「沒那麼負」的方向爬了！")
    else:
        print("❌ 警告：分數被抹平了，PSO 會變成瞎子！")