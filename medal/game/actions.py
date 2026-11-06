"""RL action ↔ 物理 Δv 的對應（env 與 SB3Agent 共用，避免兩邊各寫一份）。

兩種模式：
* **direct**：action ∈ [-1,1]^3 是自己 RSW(LVLH) 座標的 Δv 方向；大小 = 單次上限 × min(|a|,1)^power。
  躲者用這個——閃避不需要 m/s 級精度。
* **guided**（追者）：action 是「策略參數」，精度交給 Lambert：
    a0 → 時間偏好 w = 10^(1.5·a0 + 1) m/s/窗口 ∈ [0.3, 316]（a0=0 → 10，LambertPursuer 預設）
    a1 → 這一發推多少比例 f = clip(0.625·(a1+1), 0, 1)（a1 >= 0.6 → 推滿）
    a2 → 攔截 horizon 比例 h = clip(0.625·(a2+1), 0.05, 1)（只考慮 TOF <= 剩餘時間 × h）
  為什麼（2026-09-15 實測）：直接輸出 Δv 的追者 BC 後 action 誤差 RMS ~0.16×上限（≈240 m/s），
  對被動目標捕獲率只剩 4%（專家 92%）——攔截需要 m/s 級精度，MLP 學不到 Lambert 幾何。
"""
import numpy as np

from physics.frames import rsw_basis

GUIDED_DEFAULT_ACTION = np.array([0.0, 0.8, 0.8], dtype=np.float32)


def action_to_dv(game, side, action, power=1.0):
    a = np.nan_to_num(np.asarray(action, dtype=np.float64).reshape(3), nan=0.0)
    n = float(np.linalg.norm(a))
    if n < 1e-6:
        return np.zeros(3)
    mag = game.rules.max_dv(side) * min(n, 1.0) ** power
    return rsw_basis(game.r(side), game.v(side)).T @ (a / n * mag)


def dv_to_action(game, side, dv_eci_mps, power=1.0):
    """action_to_dv 的反函數（行為複製用）。超過單次上限的部分會被夾掉。"""
    dv_rsw = rsw_basis(game.r(side), game.v(side)) @ np.asarray(dv_eci_mps, dtype=np.float64)
    mag = float(np.linalg.norm(dv_rsw))
    if mag < 1e-9:
        return np.zeros(3, dtype=np.float32)
    frac = min(mag / game.rules.max_dv(side), 1.0) ** (1.0 / power)
    return (dv_rsw / mag * frac).astype(np.float32)


def guided_params(action):
    a = np.clip(np.nan_to_num(np.asarray(action, dtype=np.float64).reshape(3)), -1.0, 1.0)
    w = 10.0 ** (1.5 * a[0] + 1.0)
    f = float(np.clip(0.625 * (a[1] + 1.0), 0.0, 1.0))
    h = float(np.clip(0.625 * (a[2] + 1.0), 0.05, 1.0))
    return w, f, h


def guided_pursuer_dv(game, side, action):
    from agents.analytic import LambertPursuer, orbit_survives
    w, f, h = guided_params(action)
    lam = LambertPursuer(time_weight_mps=w, pts_per_period=16, horizon_frac=h)
    dv = lam.act(game, side)
    if f >= 1.0:
        return dv
    dv_f = dv * f
    return dv_f if orbit_survives(game, side, dv_f) else dv


def to_dv(game, side, action, mode="direct", power=1.0):
    if mode == "guided":
        assert side == "pursuer", "guided 模式只給追者用"
        return guided_pursuer_dv(game, side, action)
    return action_to_dv(game, side, action, power)


def resolve_mode(action_mode, side):
    if isinstance(action_mode, dict):
        return action_mode.get(side, "direct")
    return action_mode if (action_mode != "guided" or side == "pursuer") else "direct"
