"""決賽核心環境：回合交替的軌道追逃賽局（gym 包裝，HAP-53 → HAP-101 重寫）。

遊戲規則與物理全在 `game/`（純遊戲核心，可單獨拿去做搜尋/評測/當天 copilot），這裡只負責
把它包成 stable-baselines3 吃得下的**單 agent** 環境：

* `role`：學習中的 agent 控制哪一方（"pursuer" / "evader" / "random" 每局隨機）。
* `opponent`：另一方由 agent 物件在 env 內部推進（字串 / dict / Agent / callable，見
  agents.make_agent）。也可以給 {"pursuer": spec, "evader": spec} 依對手角色選。
  self-play 時用 `set_opponent()` 換成凍結的自己（HAP-54）。
* 一次 `step()` = 我方下一發 + 滑行一個窗口，接著對手所有回合推進到再次輪到我方。
* action ∈ [-1,1]^3 是**自己 RSW(LVLH) 座標**的 Δv 方向；大小 = 單次上限 × min(|a|,1)^p，
  所以永遠不會超過單次上限（剩餘燃料不足時 Game 會再裁）。
* 規則可固定（`rules`）或每局從 `rule_ranges` 抽；初始幾何從 `scenario` 家族抽。
* 獎勵（agent 視角，近似零和）：
    終局 ±win（勝/負） + 勢能型塑形 w·(γΦ(s')−Φ(s)) − fuel·(本步 Δv / 預算)
    Φ = ∓ψ，ψ = log((追擊所需 Δv + 1)/(追者剩餘燃料 + 1))——追者要壓低、躲者要拉高。
    勢能型塑形理論上不改變最優策略（Ng et al. 1999）。
* 比賽結束（捕獲/超時/撞地）一律 `terminated=True`：超時是賽局真正的終點（剩餘時間在
  觀測裡），標成 truncated 會讓價值函數越過終點 bootstrap。
"""
import math

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from agents import make_agent
from agents.analytic import need_horizon, pursuer_need
from game.actions import resolve_mode, to_dv
from game.core import Game
from game.obs import OBS_DIM, build_obs
from game.rules import SIDES, RuleRanges, Rules, other
from game.scenarios import sample_scenario


class GmatFinalEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, config=None):
        super().__init__()
        cfg = dict(config or {})
        self.config = cfg
        self.role_cfg = cfg.get("role", "pursuer")
        assert self.role_cfg in ("pursuer", "evader", "random")
        self.base_rules = Rules.from_dict(cfg.get("rules", {}))
        rr = cfg.get("rule_ranges")
        self.rule_ranges = None if not rr else (RuleRanges() if rr is True else RuleRanges(**rr))
        self.scenario = cfg.get("scenario", "default")
        self.set_opponent(cfg.get("opponent", "coast"))
        self.action_power = float(cfg.get("action_power", 1.0))
        # "direct" / "guided"（只對追者生效）/ {"pursuer": .., "evader": ..}，見 game/actions.py
        self.action_mode = cfg.get("action_mode", "direct")
        self.use_intercept_obs = bool(cfg.get("use_intercept_obs", True))
        rew = cfg.get("reward", {})
        self.r_win = float(rew.get("win", 10.0))
        self.r_shape = float(rew.get("shape", 1.0))
        self.r_fuel = float(rew.get("fuel", 0.0))
        self.gamma = float(rew.get("gamma", 0.99))
        self.need_windows = float(cfg.get("need_horizon_windows", 4.0))

        self.action_space = spaces.Box(low=-1.0, high=1.0, shape=(3,), dtype=np.float32)
        self.observation_space = spaces.Box(low=-np.inf, high=np.inf, shape=(OBS_DIM,), dtype=np.float32)
        self.game = None
        self.role = "pursuer" if self.role_cfg == "random" else self.role_cfg
        self._need = (math.inf, 0.0)

    # ------------------------------------------------------------------ 對手
    def set_opponent(self, spec):
        """換對手。spec 可為 agent 規格，或 {"pursuer": spec, "evader": spec}（依對手扮演的角色）。"""
        if isinstance(spec, dict) and set(spec) <= set(SIDES) and spec:
            self.opponents = {s: make_agent(spec[s]) for s in spec}
        else:
            a = make_agent(spec)
            self.opponents = {s: a for s in SIDES}

    def _opponent(self):
        return self.opponents[other(self.role)]

    # ------------------------------------------------------------------ 核心
    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        options = options or {}
        rng = self.np_random
        for _ in range(20):
            if "rules" in options:
                rules = Rules.from_dict(options["rules"])
            elif self.rule_ranges is not None:
                rules = self.rule_ranges.sample(rng, self.base_rules)
            else:
                rules = self.base_rules
            if "orbit_pursuer" in options:
                orb_p, orb_e = options["orbit_pursuer"], options["orbit_evader"]
            else:
                sc = sample_scenario(rng, options.get("scenario", self.scenario))
                orb_p, orb_e = sc.orbit_pursuer, sc.orbit_evader
            role = options.get("role", self.role_cfg)
            if role == "random":
                role = "pursuer" if rng.random() < 0.5 else "evader"
            self.role = role
            self.game = Game.from_elements(rules, orb_p, orb_e)
            opp = self._opponent()
            opp.reset(seed=int(rng.integers(2 ** 31)))
            self._advance_opponent()
            if not self.game.done:
                break
        self._refresh_need()
        self._phi = self._potential()
        return self._obs(), self._info(0.0)

    def step(self, action):
        g = self.game
        assert g is not None and not g.done, "episode 已結束，請先 reset()"
        assert g.mover == self.role
        dv = self._action_to_dv(action)
        rec = g.play_turn(dv)
        self._advance_opponent()
        self._refresh_need()

        reward = 0.0
        phi_new = self._potential()
        reward += self.gamma * phi_new - self._phi
        self._phi = phi_new
        reward -= self.r_fuel * rec["dv_mps"] / max(g.rules.fuel(self.role), 1e-9)
        if g.done:
            reward += self.r_win if g.winner == self.role else -self.r_win
        return self._obs(), float(reward), bool(g.done), False, self._info(rec["dv_mps"])

    # ------------------------------------------------------------------ 輔助
    def _advance_opponent(self):
        g = self.game
        opp = self._opponent()
        while not g.done and g.mover != self.role:
            g.play_turn(opp.act(g, g.mover))

    def _action_to_dv(self, action):
        return to_dv(self.game, self.role, action, resolve_mode(self.action_mode, self.role), self.action_power)

    def _refresh_need(self):
        g = self.game
        if g.done or not (self.use_intercept_obs or self.r_shape != 0.0):
            self._need = (math.inf, 0.0)
        else:
            self._need = pursuer_need(g, horizon=need_horizon(g, self.need_windows))

    def _potential(self):
        g = self.game
        if g.done or self.r_shape == 0.0:
            return 0.0
        need = self._need[0]
        psi = 5.0 if not math.isfinite(need) else float(
            np.clip(math.log((need + 1.0) / (g.fuel_left("pursuer") + 1.0)), -5.0, 5.0))
        sign = -1.0 if self.role == "pursuer" else 1.0
        return self.r_shape * sign * psi

    def _obs(self):
        return build_obs(self.game, self.role, use_intercept=self.use_intercept_obs, need_cache=self._need)

    def _info(self, dv_step):
        g = self.game
        info = g.summary()
        info.update({
            "role": self.role,
            "distance_km": g.distance(),
            "agent_won": None if not g.done else g.winner == self.role,
            "dv_step_mps": dv_step,
            "need_dv_mps": self._need[0],
            "rules": g.rules.to_dict(),
        })
        return info
