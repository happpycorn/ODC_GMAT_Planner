"""Agent 介面：`act(game, side) -> Δv (ECI, m/s)`。

Agent 拿到的是完整遊戲狀態（game.core.Game），可以自己決定要看什麼；Game 會把回傳的
Δv 裁到合法（單次上限、剩餘燃料），所以 agent 不必自己保證合法。
"""
import numpy as np

from physics.frames import rsw_basis


class Agent:
    name = "agent"

    def reset(self, seed=None):
        """每局開始前呼叫。"""

    def act(self, game, side) -> np.ndarray:
        raise NotImplementedError

    def __repr__(self):
        return f"<{type(self).__name__} {self.name}>"


def rsw_to_eci_dv(game, side, dv_rsw_mps):
    return rsw_basis(game.r(side), game.v(side)).T @ np.asarray(dv_rsw_mps, dtype=np.float64)


class CoastAgent(Agent):
    """完全不推（純漂移）。追者對它 = 初賽問題。"""
    name = "coast"

    def act(self, game, side):
        return np.zeros(3)


class RandomAgent(Agent):
    """每回合以機率 p_burn 朝 RSW 隨機方向推 [0, frac_max] × burn_cap。"""
    name = "random"

    def __init__(self, p_burn=0.5, frac_max=1.0, seed=None):
        self.p_burn = p_burn
        self.frac_max = frac_max
        self.rng = np.random.default_rng(seed)

    def reset(self, seed=None):
        if seed is not None:
            self.rng = np.random.default_rng(seed)

    def act(self, game, side):
        if self.rng.random() > self.p_burn:
            return np.zeros(3)
        d = self.rng.normal(size=3)
        d /= np.linalg.norm(d)
        mag = self.rng.uniform(0.0, self.frac_max) * game.burn_cap(side)
        return rsw_to_eci_dv(game, side, d * mag)


class PoolAgent(Agent):
    """對手池：每局開始依機率抽一個成員（self-play league / curriculum 混合對手）。

    成員用規格描述（字串 / dict / "sb3:path"），第一次抽到才建構，同一行程內重複使用。
    """
    name = "pool"

    def __init__(self, specs, probs=None, seed=None):
        self.specs = list(specs)
        p = np.ones(len(self.specs)) if probs is None else np.asarray(probs, dtype=float)
        self.probs = p / p.sum()
        self.rng = np.random.default_rng(seed)
        self._agents = {}
        self.current = None

    def _get(self, i):
        if i not in self._agents:
            from agents import make_agent
            self._agents[i] = make_agent(self.specs[i])
        return self._agents[i]

    def reset(self, seed=None):
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        i = int(self.rng.choice(len(self.specs), p=self.probs))
        self.current = self._get(i)
        self.current.reset(seed=None if seed is None else seed + 7)

    def act(self, game, side):
        if self.current is None:
            self.reset()
        return self.current.act(game, side)


class CallableAgent(Agent):
    """把 `fn(game, side) -> dv` 包成 Agent。"""

    def __init__(self, fn, name="callable"):
        self.fn = fn
        self.name = name

    def act(self, game, side):
        return np.asarray(self.fn(game, side), dtype=np.float64)
