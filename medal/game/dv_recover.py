"""由回合起點與官方回合末狀態反推瞬時推力；位置 km、速度 km/s、推力 m/s。"""
import math

import numpy as np

from agents.final_common import kepler
from game.initial_state import parse_epoch
from physics import EARTH_MU
from physics.lambert import izzo


def recover_dv(r0, v0, r1, v1, dt, mu=EARTH_MU) -> dict:
    """回推二體軌道取得實際 Δv，並用零圈 Lambert 的順、逆行分支交叉核對。"""
    dt, mu = float(dt), float(mu)
    if not math.isfinite(dt) or dt <= 0.0:
        raise ValueError("反推 Δv 的時間 dt 必須是大於 0 的有限秒數；請核對回合起點與回合末時間")
    if not math.isfinite(mu) or mu <= 0.0:
        raise ValueError("反推 Δv 的重力參數必須是大於 0 的有限數字")
    r0, v0, r1, v1 = (np.asarray(x, dtype=np.float64).reshape(3) for x in (r0, v0, r1, v1))
    if not all(np.isfinite(x).all() for x in (r0, v0, r1, v1)):
        raise ValueError("反推 Δv 的位置與速度必須都是有限數字，單位為 km、km/s")
    if min(np.linalg.norm(r0), np.linalg.norm(r1)) <= 0.0:
        raise ValueError("反推 Δv 的起點與終點位置不能在地心；請核對 km 單位與位置欄位")

    r0_back, v0_post = kepler(r1, v1, -dt, mu)
    if not (np.isfinite(r0_back).all() and np.isfinite(v0_post).all()):
        raise ValueError("二體回推未得到有限狀態；請核對單位、時間與官方狀態檔")
    dv = (v0_post - v0) * 1000.0
    result = {"dv_mps": dv.tolist(),
              "position_residual_km": float(np.linalg.norm(r0_back - r0)),
              "lambert_dv_mps": None, "lambert_diff_mps": None}

    # 超過實際滑行軌道的半週期時，零圈解不再適合作為本回合的交叉核對。
    alpha = 2.0 / float(np.linalg.norm(r1)) - float(v1 @ v1) / mu
    if alpha > 0.0 and dt > math.pi / (math.sqrt(mu) * alpha ** 1.5):
        return result
    candidates = []
    for prograde in (True, False):
        try:
            ok, initial_v, _ = izzo(mu, r0, r1, dt, 0, prograde, True, 50, 1e-12)
        except Exception:
            # Lambert 僅供交叉核對；求解失敗時保留已完成的二體回推結果。
            continue
        if ok and np.isfinite(initial_v).all():
            candidates.append(initial_v)
    if candidates:
        closest = min(candidates, key=lambda v: float(np.linalg.norm(v - v0_post)))
        lambert_dv = (closest - v0) * 1000.0
        result["lambert_dv_mps"] = lambert_dv.tolist()
        result["lambert_diff_mps"] = float(np.linalg.norm(lambert_dv - dv))
    return result


def elapsed_sec(start_state, end_state, window_sec):
    """優先用共同 epoch，其次用經過秒數，皆不足時採公告的 T_round。"""
    if start_state.get("epoch") is not None and end_state.get("epoch") is not None:
        dt = (parse_epoch(end_state["epoch"]) - parse_epoch(start_state["epoch"])).total_seconds()
        return float(dt), "epoch"
    if start_state.get("t_sec") is not None and end_state.get("t_sec") is not None:
        return float(end_state["t_sec"]) - float(start_state["t_sec"]), "t_sec"
    return float(window_sec), "T_round"
