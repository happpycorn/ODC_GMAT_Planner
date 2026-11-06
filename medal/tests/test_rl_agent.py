"""已部署 RL 模型（models/）當 agent：載入、合法 Δv、撞地防呆。沒有模型檔時略過。"""
import os

import numpy as np
import pytest

from agents import make_agent
from agents.analytic import orbit_survives
from game.core import Game
from game.rules import Rules

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = {s: os.path.join(ROOT, "models", f"{s}.zip") for s in ("pursuer", "evader")}

P = {"sma": 6778.0, "ecc": 0.0, "inc": 51.6, "raan": 10.0, "aop": 0.0, "ta": 0.0}
E = {"sma": 6800.0, "ecc": 0.001, "inc": 51.8, "raan": 10.3, "aop": 0.0, "ta": 4.0}


@pytest.mark.parametrize("side", ["pursuer", "evader"])
def test_deployed_model_acts_legally_and_safely(side):
    if not os.path.exists(MODELS[side]):
        pytest.skip("models/ 沒有部署模型")
    agent = make_agent("sb3:" + MODELS[side])
    rules = Rules(first_mover=side)
    g = Game.from_elements(rules, P, E)
    for _ in range(6):
        if g.done:
            break
        if g.mover == side:
            dv = agent.act(g, side)
            assert np.linalg.norm(dv) <= rules.max_dv(side) + 1e-6
            assert orbit_survives(g, side, dv) or not orbit_survives(g, side, np.zeros(3))
            g.play_turn(dv)
        else:
            g.play_turn(np.zeros(3))
