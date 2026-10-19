import math
from numba import njit

@njit(fastmath=True, inline='always')
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

    penalty_count = 扣分次數 (每次 −10，扣到 0 為止)。排位賽規則裡官方只剩「機動間隔
    < MIN_MANEUVER_INTERVAL_SEC」一種扣分；單棒超過 MAX_DV_MPS、總 Δv 超過
    MAX_TOTAL_DV_MPS 都是**失格**，不是扣分——那由 assess_legality 判定，失格解沒有
    官方分數。搜尋/挑候選時呼叫端可以把單棒超標次數一起塞進來當「軟懲罰」(讓 DE 還能
    探索超標、之後交給拆棒器的路線)，但那個數字不是交件分數。
    """
    dr = max(min_distance_km, 5.0)
    score_dist = 50.0 * math.exp(-(dr - 5.0) / 100.0)

    exp_time = math.exp(min(k_t * (total_time_sec - C_t), 700.0)) 
    score_time = 25.0 / (1.0 + exp_time)

    exp_dv = math.exp(min(k_v * (total_dv_mps - C_v), 700.0))
    score_dv = 25.0 / (1.0 + exp_dv)

    total_score = score_dist + score_time + score_dv - (penalty_count * 10.0)
    return max(total_score, 0.0)


# 排位賽規則：單棒超過 上限 + 1e-5 m/s 才算超標 (直接失格)。總 Δv 規則只寫「≤ 3 km/s」，
# 沒給容許量，這裡同樣只吸收浮點雜訊等級的 1e-5 m/s。
DV_LIMIT_TOL_MPS = 1e-5
# 機動間隔判定吸收浮點雜訊用 (時刻是 t0 + 各段滑行累加出來的，等於下限時可能差幾個 ulp)。
INTERVAL_TOL_SEC = 1e-6
# 總 Δv 超標的搜尋軟懲罰：固定 10 分 (跟單棒超標的軟懲罰同一個量級) + 每超 1 m/s 再扣
# 0.01 分。斜率讓整群候選都超標時 DE 仍有往上限內推的梯度，不會卡在 0 分平台。
TOTAL_DV_SOFT_PENALTY_POINTS = 10.0
TOTAL_DV_SOFT_PENALTY_PER_MPS = 0.01


@njit(fastmath=True, inline='always')
def total_dv_soft_penalty(total_dv_mps: float, max_total_dv_mps: float) -> float:
    """搜尋用的總 Δv 軟懲罰 (分)。max_total_dv_mps <= 0 代表沒有上限 (初賽)，回 0。
    只給搜尋/挑候選用；最終交件判定看 assess_legality (超標就是失格)。"""
    if max_total_dv_mps <= 0.0:
        return 0.0
    excess = total_dv_mps - max_total_dv_mps
    if excess <= DV_LIMIT_TOL_MPS:
        return 0.0
    return TOTAL_DV_SOFT_PENALTY_POINTS + TOTAL_DV_SOFT_PENALTY_PER_MPS * excess


def assess_legality(burn_dvs_mps, burn_times_sec, max_dv_mps, min_interval_sec,
                    max_total_dv_mps=None) -> dict:
    """最終交件判定 (純 Python，不給搜尋迴圈用)。

    burn_dvs_mps：每棒 Δv 大小 (m/s)；burn_times_sec：每棒點火時刻 (s，遞增)。
    max_total_dv_mps 為 None 或 <=0 代表沒有總 Δv 上限 (初賽行為)。

    回傳：
      penalty_count  機動間隔 < min_interval_sec 的次數 (官方每次 −10 分)
      over_dv_legs   超過單棒上限的棒索引 (失格)
      over_dv_count  len(over_dv_legs)
      total_dv_mps   總 Δv
      total_dv_over  總 Δv 是否超過上限 (失格)
      disqualified   上面任一失格條件成立
      dq_reasons     失格原因 (給報表印)
    """
    dvs = [float(d) for d in burn_dvs_mps]
    ts = [float(t) for t in burn_times_sec]
    cap = float(max_dv_mps)
    over = [i for i, d in enumerate(dvs) if d > cap + DV_LIMIT_TOL_MPS]
    gaps = [b - a for a, b in zip(ts, ts[1:])]
    penalty_count = sum(1 for g in gaps if g < float(min_interval_sec) - INTERVAL_TOL_SEC)
    total = sum(dvs)
    total_cap = None if max_total_dv_mps is None or max_total_dv_mps <= 0 else float(max_total_dv_mps)
    total_over = total_cap is not None and total > total_cap + DV_LIMIT_TOL_MPS
    reasons = []
    if over:
        worst = max(dvs[i] for i in over)
        reasons.append(f"{len(over)} 棒超過單棒上限 {cap:,.0f} m/s（最大 {worst:,.3f} m/s）")
    if total_over:
        reasons.append(f"總 Δv {total:,.3f} m/s 超過上限 {total_cap:,.0f} m/s")
    return {
        "penalty_count": int(penalty_count),
        "over_dv_legs": over,
        "over_dv_count": len(over),
        "total_dv_mps": total,
        "total_dv_over": bool(total_over),
        "disqualified": bool(over or total_over),
        "dq_reasons": reasons,
    }

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