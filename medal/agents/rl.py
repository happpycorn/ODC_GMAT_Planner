"""把訓練好的 stable-baselines3 策略包成 Agent（評測 / self-play 對手 / copilot 共用）。

模型存成 `xxx.zip`，旁邊放 `xxx.json` 描述觀測與 action 設定：
    {"algo": "PPO", "role": "pursuer", "action_power": 1.0, "use_intercept_obs": true}
"""
import json
import os

import numpy as np

from agents.base import Agent
from game.actions import resolve_mode, to_dv
from game.obs import build_obs

_MODEL_CACHE = {}


def _load_model(path, algo, device):
    key = (os.path.abspath(path), algo, device)
    if key not in _MODEL_CACHE:
        import torch
        torch.set_num_threads(1)
        from stable_baselines3 import PPO, SAC
        cls = {"PPO": PPO, "SAC": SAC}[algo]
        _MODEL_CACHE[key] = cls.load(path, device=device)
    return _MODEL_CACHE[key]


def read_meta(path):
    meta_path = os.path.splitext(path)[0] + ".json"
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            return json.load(f)
    return {}


def write_meta(path, meta):
    with open(os.path.splitext(path)[0] + ".json", "w") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)


class SB3Agent(Agent):
    def __init__(self, model, action_power=1.0, use_intercept_obs=True, deterministic=True, name="sb3",
                 action_mode="direct"):
        self.model = model
        self.action_power = action_power
        self.use_intercept_obs = use_intercept_obs
        self.deterministic = deterministic
        self.name = name
        self.action_mode = action_mode

    @classmethod
    def load(cls, path, device="cpu", deterministic=True):
        meta = read_meta(path)
        model = _load_model(path, meta.get("algo", "PPO"), device)
        name = "sb3:" + os.path.relpath(path)
        return cls(model, meta.get("action_power", 1.0), meta.get("use_intercept_obs", True),
                   deterministic, name, meta.get("action_mode", "direct"))

    safety = True   # 推完軌道撐不到比賽結束 → 減半重試 / 救命推力（與解析 agent 相同的防呆）

    def act(self, game, side):
        obs = build_obs(game, side, use_intercept=self.use_intercept_obs)
        a, _ = self.model.predict(obs, deterministic=self.deterministic)
        dv = to_dv(game, side, np.asarray(a).reshape(3), resolve_mode(self.action_mode, side), self.action_power)
        if not self.safety:
            return dv
        # sp3 部署評測：RL 躲者 40 局裡自己撞地 5–7 局（策略沒學會顧近地點）
        from agents.analytic import orbit_survives, rescue_burn
        dv = game.clip_dv(side, dv)
        if orbit_survives(game, side, dv):
            return dv
        for _ in range(6):
            dv = dv * 0.5
            if orbit_survives(game, side, dv):
                return dv
        rb = rescue_burn(game, side)
        return rb if rb is not None else np.zeros(3)
