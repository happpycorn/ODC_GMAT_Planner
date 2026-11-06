"""依規則選打法的躲者（HAP-108 收穫）。

實測：
  * 燃料與單發上限都對稱：純 EscapeEvader 存活 88%，rollout 躲者 72%
    （reports/hap108_escape_evader_symmetric.md）
  * 追者燃料 2×：EscapeEvader 只剩 12%，rollout 躲者 31%（…_pursuer_fuel_2x.md）
  * 隨機規則分布（躲者單發上限只有追者的 0.3–1.0 倍）：只看燃料比的版本全部輸給 rollout 躲者
    （存活 44–49% vs 60%，reports/hap108_adaptive_ranges.md）——逃逸需要大推力，躲者單發小時無效
  * 把 escape 塞進 rollout 躲者的候選集沒用（對手模型太弱 → 推演過度樂觀、永遠省油）

所以只在**已驗證的近對稱區域**切逃逸：
    躲者燃料/追者燃料 >= fuel_ratio 且 躲者單發/追者單發 >= dv_ratio → 整場逃逸；否則 rollout 躲者。
"""
from agents.base import Agent


class AdaptiveEvader(Agent):
    name = "adaptive_evader"

    def __init__(self, fuel_ratio=0.75, dv_ratio=0.9, escape="escape_evader", default="rollout_evader",
                 threshold=None):
        from agents import make_agent
        if threshold is not None:            # 舊參數名（只看燃料比）
            fuel_ratio, dv_ratio = float(threshold), 0.0
        self.fuel_ratio = float(fuel_ratio)
        self.dv_ratio = float(dv_ratio)
        self.escape = make_agent(escape)
        self.default = make_agent(default)
        self._pick = None
        self._pick_key = None

    def reset(self, seed=None):
        self._pick = None
        self._pick_key = None
        self.escape.reset(seed)
        self.default.reset(seed)

    def choose(self, rules):
        fr = rules.fuel_evader_mps / max(rules.fuel_pursuer_mps, 1e-9)
        dr = rules.max_dv_evader_mps / max(rules.max_dv_pursuer_mps, 1e-9)
        return self.escape if (fr >= self.fuel_ratio and dr >= self.dv_ratio) else self.default

    def act(self, game, side):
        assert side == "evader"
        key = id(game.rules)
        if self._pick is None or self._pick_key != key:     # 每局（每組規則）決定一次
            self._pick = self.choose(game.rules)
            self._pick_key = key
        return self._pick.act(game, side)
