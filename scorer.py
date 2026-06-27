import math

class CompetitionScorer:

    @staticmethod
    def calculate_score(
        min_distance_km: float, 
        total_time_sec: float, 
        total_dv_mps: float, 
        penalty_count: int,
        # 主辦方會公布的環境參數 (這裡先給一組合理的虛擬預設值供測試)
        k_t: float = 0.0001, 
        C_t: float = 86400.0,  # 基準時間 (例如 1 天 = 86400 秒)
        k_v: float = 0.005, 
        C_v: float = 3000.0    # 基準消耗 (例如 3000 m/s)
    ) -> float:
        dr = max(min_distance_km, 5.0)
        score_dist = 50.0 * math.exp(-(dr - 5.0) / 100.0)

        exp_time = math.exp(min(k_t * (total_time_sec - C_t), 700.0)) 
        score_time = 25.0 / (1.0 + exp_time)

        exp_dv = math.exp(min(k_v * (total_dv_mps - C_v), 700.0))
        score_dv = 25.0 / (1.0 + exp_dv)

        total_score = score_dist + score_time + score_dv - (penalty_count * 10.0)
        return max(total_score, 0.0)

# ==========================================
# 測試區塊 
# ==========================================
if __name__ == "__main__":
    print("=== 模組三評分測試 ===")

    score_A = CompetitionScorer.calculate_score(
        min_distance_km=4.0, 
        total_time_sec=43200, 
        total_dv_mps=1400, 
        penalty_count=0
    )
    print(f"情境 A (完美表現) 得分: {score_A:.2f}")

    score_B = CompetitionScorer.calculate_score(
        min_distance_km=50.0, 
        total_time_sec=10000, 
        total_dv_mps=2000, 
        penalty_count=1
    )
    print(f"情境 B (違規且偏離) 得分: {score_B:.2f}")