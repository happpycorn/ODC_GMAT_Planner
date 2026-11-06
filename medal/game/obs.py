"""從 Game 組 RL 觀測（任一方視角），env 與「把訓練好的模型當 agent」共用同一份。

設計原則（HAP-101）：
  * 相對態用**自己的 RSW(LVLH) 座標** → 對軌道姿態旋轉不變，網路不必重學每種軌道面
  * 所有量都壓到 O(1)：距離/速度用 signed-log，高度/燃料/時間用比例
  * 放進**規則參數**（單次上限、燃料、捕獲半徑、窗口）→ rule-conditioned policy
  * 放進物理上最優策略真正依賴的量：純滑行最近接近（距離/時刻/方向）、追擊所需 Δv 比
"""
import math

import numpy as np

from game.rules import other
from physics import RE_VAL
from physics.coast import closest_approach
from physics.frames import rsw_basis

OBS_DIM = 30

FEATURE_NAMES = (
    ["rel_pos_R", "rel_pos_S", "rel_pos_W", "rel_vel_R", "rel_vel_S", "rel_vel_W", "dist",
     "alt_own", "alt_opp", "perigee_alt_own", "perigee_alt_opp",
     "fuel_frac_own", "fuel_frac_opp", "burn_cap_own", "burn_cap_opp", "fuel_left_own", "fuel_left_opp",
     "time_frac_left", "turns_left", "capture_radius", "window", "role",
     "ca_dist", "ca_time_frac", "ca_rel_R", "ca_rel_S", "ca_rel_W", "ca_over_capture",
     "need_ratio", "need_tof_frac"]
)
assert len(FEATURE_NAMES) == OBS_DIM


def slog(x, scale=1.0):
    x = np.asarray(x, dtype=np.float64)
    return np.sign(x) * np.log1p(np.abs(x) / scale)


def _perigee_alt(r, v, mu):
    rn = float(np.linalg.norm(r))
    v2 = float(v @ v)
    h = np.cross(r, v)
    energy = v2 / 2.0 - mu / rn
    e = math.sqrt(max(0.0, 1.0 + 2.0 * energy * float(h @ h) / mu ** 2))
    rp = float(h @ h) / (mu * (1.0 + e))
    return rp - RE_VAL


def build_obs(game, side, *, use_intercept=True, ca_substep=120.0, need_cache=None):
    o = other(side)
    R = game.rules
    mu = game.mu
    r_s, v_s, r_o, v_o = game.r(side), game.v(side), game.r(o), game.v(o)
    B = rsw_basis(r_s, v_s)
    d_vec = r_o - r_s
    drel = B @ d_vec
    vrel = (B @ (v_o - v_s)) * 1000.0
    dist = float(np.linalg.norm(d_vec))

    f = np.zeros(OBS_DIM, dtype=np.float64)
    f[0:3] = slog(drel) / 5.0
    f[3:6] = slog(vrel) / 5.0
    f[6] = slog(dist) / 5.0
    f[7] = (np.linalg.norm(r_s) - RE_VAL) / 1000.0
    f[8] = (np.linalg.norm(r_o) - RE_VAL) / 1000.0
    f[9] = np.clip(_perigee_alt(r_s, v_s, mu) / 1000.0, -3.0, 5.0)
    f[10] = np.clip(_perigee_alt(r_o, v_o, mu) / 1000.0, -3.0, 5.0)
    f[11] = game.fuel_left(side) / max(R.fuel(side), 1e-9)
    f[12] = game.fuel_left(o) / max(R.fuel(o), 1e-9)
    f[13] = game.burn_cap(side) / 1000.0
    f[14] = game.burn_cap(o) / 1000.0
    f[15] = game.fuel_left(side) / 3000.0
    f[16] = game.fuel_left(o) / 3000.0
    tl = game.time_left
    f[17] = tl / game.t_max
    f[18] = min(tl / (2.0 * R.window_sec) / 20.0, 5.0)
    f[19] = slog(R.capture_radius_km) / 3.0
    f[20] = R.window_sec / 1000.0
    f[21] = 1.0 if side == "pursuer" else -1.0

    period = 2.0 * math.pi * math.sqrt(max(float(np.linalg.norm(r_s)), RE_VAL) ** 3 / mu)
    horizon = min(tl, period)
    if horizon > 0.0:
        ca_d, ca_t, ca_rel = closest_approach(game.r("pursuer"), game.v("pursuer"), game.r("evader"),
                                              game.v("evader"), horizon, ca_substep, mu, R.gravity_degree)
        if side == "evader":
            ca_rel = -ca_rel
        f[22] = slog(ca_d) / 5.0
        f[23] = ca_t / horizon
        f[24:27] = slog(B @ ca_rel) / 5.0
        f[27] = slog(ca_d / R.capture_radius_km) / 3.0
    else:
        f[22] = f[6]
        f[27] = slog(dist / R.capture_radius_km) / 3.0

    if use_intercept:
        if need_cache is not None:
            need, tof = need_cache
        else:
            from agents.analytic import need_horizon, pursuer_need
            need, tof = pursuer_need(game, horizon=need_horizon(game))
        if math.isfinite(need):
            f[28] = np.clip(math.log((need + 1.0) / (game.fuel_left("pursuer") + 1.0)), -5.0, 5.0) / 5.0
            f[29] = tof / max(tl, 1.0)
        else:
            f[28] = 1.0
            f[29] = 1.0
    return np.nan_to_num(f, nan=0.0, posinf=10.0, neginf=-10.0).astype(np.float32)
