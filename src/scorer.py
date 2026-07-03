import math
from numba import njit

@njit(fastmath=True)
def calculate_score(
    min_distance_km: float, 
    total_time_sec: float, 
    total_dv_mps: float, 
    penalty_count: int,
    k_t: float, 
    C_t: float, 
    k_v: float, 
    C_v: float
) -> float:
    """
    純數值計分函式 (JIT 加速)
    所有的環境參數 (k_t, C_t, k_v, C_v) 都必須由外部 (如 config) 傳入。
    """
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
    print("=== 模組三評分測試 (純函式 + JIT) ===")

    # 模擬從外部 config 傳入的環境參數
    k_t_val = 0.0001
    C_t_val = 11000.0
    k_v_val = 0.005
    C_v_val = 1200.0

    score_A = calculate_score(
        min_distance_km=0.0, 
        total_time_sec=0.0, 
        total_dv_mps=0.0, 
        penalty_count=0,
        k_t=k_t_val,
        C_t=C_t_val,
        k_v=k_v_val,
        C_v=C_v_val
    )
    print(f"情境 A (完美表現) 得分: {score_A:.2f}")

    score_B = calculate_score(
        min_distance_km=50.0, 
        total_time_sec=10000.0, 
        total_dv_mps=2000.0, 
        penalty_count=1,
        k_t=k_t_val,
        C_t=C_t_val,
        k_v=k_v_val,
        C_v=C_v_val
    )
    print(f"情境 B (違規且偏離) 得分: {score_B:.2f}")