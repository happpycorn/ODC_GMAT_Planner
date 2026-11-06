"""2-ply 極小極大搜尋（回合交替 → 賽局樹天然是輪流的，見 METHODOLOGY §4）。

每個候選脈衝：模擬自己的窗口 → 對手所有候選回應 → 以「追擊所需 Δv − 追者剩餘燃料」
（短 horizon）當葉節點值，取最壞情況下最好的那一發。對手回應集用解析 agent 的提案
（LambertPursuer 多種時間偏好）或 RSW 方向集，所以這是「對解析對手群的最佳回應」，
不是完整賽局解——但比單層啟發式穩，且當天 copilot 可以直接拿來用（決策 < 數秒）。

葉節點值一律以**躲者視角**表示：value_E = need − fuel_left_P（越大躲者越好），
追者取負號。終局：追者勝 → value_E = −1e9；躲者勝 → +1e9。
"""
import math

import numpy as np

from agents.analytic import (LambertPursuer, _direction_set, need_horizon, orbit_survives, pursuer_need)
from agents.base import Agent, rsw_to_eci_dv

WIN = 1e9


def _value_e(g, horizon_windows):
    if g.done:
        return WIN if g.winner == "evader" else -WIN
    need, _ = pursuer_need(g, horizon=need_horizon(g, horizon_windows), max_revs=1, pts_per_period=16,
                           n_refine=1)
    if not math.isfinite(need):
        return 1e8
    return need - g.fuel_left("pursuer")


def _dedupe(cands, tol=1.0):
    out = []
    for c in cands:
        if all(np.linalg.norm(c - o) > tol for o in out):
            out.append(c)
    return out


def _pursuer_proposals(game, weights, axes_frac):
    cands = [np.zeros(3)]
    for w in weights:
        cands.append(LambertPursuer(time_weight_mps=w, coast_if_captures=False, pts_per_period=16).act(game, "pursuer"))
    cap = game.burn_cap("pursuer")
    if cap > 0 and axes_frac > 0:
        for d in _direction_set("axes"):
            dv = rsw_to_eci_dv(game, "pursuer", d * cap * axes_frac)
            if orbit_survives(game, "pursuer", dv):
                cands.append(dv)
    return _dedupe(cands)


def _evader_proposals(game, directions, mags):
    cands = [np.zeros(3)]
    cap = game.burn_cap("evader")
    if cap > 0:
        for d in _direction_set(directions):
            for m in mags:
                dv = rsw_to_eci_dv(game, "evader", d * cap * m)
                if orbit_survives(game, "evader", dv):
                    cands.append(dv)
    return cands


class MinimaxPursuer(Agent):
    name = "minimax_pursuer"

    def __init__(self, time_weights=(0.0, 10.0, 60.0, 300.0), axes_frac=0.5, reply_directions="axes",
                 reply_mags=(1.0,), horizon_windows=4.0, fuel_weight=0.1):
        self.time_weights = tuple(time_weights)
        self.axes_frac = axes_frac
        self.reply_directions = reply_directions
        self.reply_mags = tuple(reply_mags)
        self.horizon_windows = horizon_windows
        self.fuel_weight = fuel_weight

    def act(self, game, side):
        assert side == "pursuer"
        if game.burn_cap(side) <= 0:
            return np.zeros(3)
        best_v, best_dv = -math.inf, np.zeros(3)
        for dv in _pursuer_proposals(game, self.time_weights, self.axes_frac):
            g1 = game.clone()
            g1.play_turn(dv)
            spent = float(np.linalg.norm(dv))
            if g1.done:
                v = -_value_e(g1, self.horizon_windows)
            else:
                worst = math.inf
                for e_dv in _evader_proposals(g1, self.reply_directions, self.reply_mags):
                    g2 = g1.clone()
                    g2.play_turn(e_dv)
                    worst = min(worst, -_value_e(g2, self.horizon_windows))
                    if worst - self.fuel_weight * spent <= best_v:
                        break                          # alpha 剪枝：已不可能比目前最好的好
                v = worst
            v -= self.fuel_weight * spent
            if v > best_v:
                best_v, best_dv = v, dv
            if best_v >= WIN / 2:
                break                                  # 保證捕獲，不必再看
        return best_dv


class MinimaxEvader(Agent):
    name = "minimax_evader"

    def __init__(self, directions="full", mags=(1.0, 0.4), reply_weights=(0.0, 60.0), horizon_windows=4.0,
                 fuel_weight=0.3):
        self.directions = directions
        self.mags = tuple(mags)
        self.reply_weights = tuple(reply_weights)
        self.horizon_windows = horizon_windows
        self.fuel_weight = fuel_weight

    def act(self, game, side):
        assert side == "evader"
        best_v, best_dv = -math.inf, np.zeros(3)
        for dv in _evader_proposals(game, self.directions, self.mags):
            g1 = game.clone()
            g1.play_turn(dv)
            spent = float(np.linalg.norm(dv))
            if g1.done:
                v = _value_e(g1, self.horizon_windows)
            else:
                worst = math.inf
                for p_dv in _pursuer_proposals(g1, self.reply_weights, 0.0):
                    g2 = g1.clone()
                    g2.play_turn(p_dv)
                    worst = min(worst, _value_e(g2, self.horizon_windows))
                    if worst - self.fuel_weight * spent <= best_v:
                        break
                v = worst
            v -= self.fuel_weight * spent
            if v > best_v:
                best_v, best_dv = v, dv
        return best_dv
