import math
import numpy as np

from numba import njit
from numba import types
from numba.typed import Dict
from astropy import units as u
from poliastro.bodies import Earth
from typing import Callable, Tuple
from poliastro.core.propagation import farnocchia

from old.physics_engine import to_vnb_frame, check_constraints, solve_lambert

MU = Earth.k.to_value((u.km ** 3) / (u.s ** 2)) # type: ignore
MIN_PERIAPSIS = Earth.R.to_value(u.km) + 100.0

PropagatorFunc = Callable[[float, np.ndarray, np.ndarray, float], Tuple[np.ndarray, np.ndarray]]

@njit(fastmath=True)
def calculate_score(
    min_distance_km: float, 
    total_time_sec: float, 
    total_dv_mps: float, 
    penalty_count: int,
    # 主辦方會公布的環境參數 (這裡先給一組合理的虛擬預設值供測試)
    k_t: float = 0.0001, 
    C_t: float = 11000.0,  # 基準時間 (例如 1 天 = 86400 秒)
    k_v: float = 0.005, 
    C_v: float = 1200.0    # 基準消耗 (例如 3000 m/s)
) -> float:
    dr = max(min_distance_km, 5.0)
    score_dist = 50.0 * math.exp(-(dr - 5.0) / 100.0)

    exp_time = math.exp(min(k_t * (total_time_sec - C_t), 700.0)) 
    score_time = 25.0 / (1.0 + exp_time)

    exp_dv = math.exp(min(k_v * (total_dv_mps - C_v), 700.0))
    score_dv = 25.0 / (1.0 + exp_dv)

    total_score = score_dist + score_time + score_dv - (penalty_count * 10.0)
    return max(total_score, 0.0)

@njit(fastmath=True)
def default_propagator(k: float, r0: np.ndarray, v0: np.ndarray, tof: float) -> Tuple[np.ndarray, np.ndarray]:
    r, v = farnocchia(k, r0, v0, tof)
    return r, v

import numpy as np
from numba import njit

@njit(fastmath=True)
def evaluate_mission_path_obj(
    x: np.ndarray, num_burns: int, 
    A_r0, A_v0, B_r0, B_v0,
    max_dv: float = 1.5,
    propagator=default_propagator,
    min_periapsis: float = MIN_PERIAPSIS
):
    total_dv = 0.0
    penalty_count = 0

    current_time = x[0] 

    times = np.zeros(num_burns + 2, dtype=np.float64)
    times[0] = 0.0
    times[1] = current_time

    r_current, v_current = propagator(MU, B_r0, B_v0, current_time)

    for i in range(1, num_burns):
        idx = 1 + (i - 1) * 4
        dv_vec = np.array([x[idx], x[idx+1], x[idx+2]])
        t_coast = x[idx+3]
        
        dv_mag = np.linalg.norm(dv_vec)
        total_dv += dv_mag
        
        if dv_mag > max_dv: 
            penalty_count += 1

        v_current_new = v_current + dv_vec

        if not check_constraints(r_current, v_current_new, MU, min_periapsis):
            return False, total_dv, penalty_count, 0.0, np.zeros(0) # 提早中斷

        current_time += t_coast
        times[i+1] = current_time
        r_current, v_current = default_propagator(MU, r_current, v_current_new, t_coast)

    t_final_leg = x[-1] # 陣列最後一個元素一定是 t_final_leg
    intercept_time = current_time + t_final_leg
    times[-1] = intercept_time

    r_a_target, _ = default_propagator(MU, A_r0, A_v0, intercept_time)

    v_req, _, dv_final_vec, dv_final_mag = solve_lambert(
        MU, r_current, v_current, r_a_target, t_final_leg
    )
    
    total_dv += dv_final_mag
    if dv_final_mag > max_dv: 
        penalty_count += 1

    if not check_constraints(r_current, v_req, MU, min_periapsis):
        return False, total_dv, penalty_count, intercept_time, np.zeros(0)

    times_diff = np.diff(times)

    return True, total_dv, penalty_count, intercept_time, times_diff

def reconstruct_mission_logs(
    x, num_burns, A_r0, A_v0, B_r0, B_v0,
    propagator=default_propagator
):
    """
    純 Python 函式，只在取得最佳解後執行「一次」，用來產生人類可讀的詳細日誌。
    這裡可以盡情使用 list, dict, f-string 等純 Python 功能。
    """
    burn_logs = []
    times = []
    
    current_time = x[0] 
    r_current, v_current = propagator(MU, B_r0, B_v0, current_time)

    for i in range(1, num_burns):
        idx = 1 + (i - 1) * 4
        dv_vec = np.array([x[idx], x[idx+1], x[idx+2]])
        t_coast = x[idx+3]
        dv_mag = np.linalg.norm(dv_vec)
        
        dv_vnb = to_vnb_frame(r_current, v_current, dv_vec)
        
        # 這裡可以放心使用字典和動態字串了！
        burn_logs.append({
            "time": current_time,
            "dv_vec": dv_vec.tolist(),
            "dv_vnb": dv_vnb.tolist(),
            "dv_mag": dv_mag,
            "type": f"Burn {i}"
        })
        times.append(current_time)

        v_current_new = v_current + dv_vec
        current_time += t_coast
        r_current, v_current = propagator(MU, r_current, v_current_new, t_coast)

    # 處理最後的 Lambert 攔截
    t_final_leg = x[-1]
    intercept_time = current_time + t_final_leg
    r_a_target, _ = propagator(MU, A_r0, A_v0, intercept_time)

    v_req, _, dv_final_vec, dv_final_mag = solve_lambert(
        MU, r_current, v_current, r_a_target, t_final_leg
    )
    times.extend([current_time, intercept_time])
    
    dv_final_vnb = to_vnb_frame(r_current, v_current, dv_final_vec)
    
    burn_logs.append({
        "time": current_time,
        "dv_vec": dv_final_vec.tolist(),
        "dv_vnb": dv_final_vnb.tolist(),
        "dv_mag": dv_final_mag,
        "type": "Final Burn"
    })

    times_diff = np.diff(times).tolist()

    return burn_logs, intercept_time, times_diff

@njit(fastmath=True)
def decode_params(
    x: list | np.ndarray, num_burns: int,
    min_coast_time: float, T_max: float
) -> dict:
    """把 DE 給出的純數字陣列，轉換成具名參數字典"""
    params = Dict.empty(
        key_type=types.unicode_type,
        value_type=types.float64,
    )
    params["num_burns"] = float(num_burns)
    params["t_wait"] = float(x[0])  # 原本是 x[1]，現在變成 x[0]
    
    current_time = params["t_wait"]
    idx = 1  # 索引從 1 開始抓推進參數
    
    for i in range(1, num_burns):
        params[f"b{i}_dv_x"] = float(x[idx])
        params[f"b{i}_dv_y"] = float(x[idx+1])
        params[f"b{i}_dv_z"] = float(x[idx+2])
        coast_frac = x[idx+3]
        idx += 4

        max_coast = T_max - current_time - min_coast_time
        t_coast = min_coast_time + coast_frac * (max_coast - min_coast_time) if max_coast > min_coast_time else min_coast_time
        params[f"b{i}_t_coast"] = float(t_coast)
        current_time += t_coast
        
    max_final = T_max - current_time
    final_leg_frac = x[-1]
    t_final_leg = min_coast_time + final_leg_frac * (max_final - min_coast_time) if max_final > min_coast_time else min_coast_time
    params["t_final_leg"] = float(t_final_leg)
    
    return params

@njit(fastmath=True)
def objective(
    x: list | np.ndarray, num_burns: int,
    min_coast_time: float, T_max: float,
    A_r0, A_v0, B_r0, B_v0,
    propagator: PropagatorFunc | None = None,
    min_periapsis: float = MIN_PERIAPSIS
) -> float:
    params = decode_params(x, num_burns, min_coast_time, T_max)
    is_valid, total_dv, penalty_count, intercept_time, _ = evaluate_mission_path_obj(
        params, num_burns, 
        A_r0, A_v0, B_r0, B_v0,
        propagator=propagator,
        min_periapsis=min_periapsis
    )
    
    if not is_valid: return 0.0 

    score = calculate_score(
        min_distance_km=0.0, 
        total_time_sec=intercept_time, 
        total_dv_mps=float(total_dv * 1000.0), 
        penalty_count=penalty_count
    )
    return -score