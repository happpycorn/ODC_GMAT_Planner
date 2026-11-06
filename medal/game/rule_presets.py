"""規則分布的預設（不改 game/rules.py）：排位版（250 m/s 級）規則不確定時的平均。

`RuleRanges`（game/rules.py）是 2026-09 的佔位分布：單發 50–1500 m/s、燃料 2–8 發、一回合一發。
排位賽規則（單發 250 m/s、總 Δv 3 km/s、機動間隔 100 s）公布後，四強賽最可能落在它附近，
所以這裡另外給一個「排位版」分布，用來回答「官方規則還沒定時，平均起來誰有利」：

* 單發上限 150–400 m/s（log-uniform）；躲者 = 追者 × 0.8–1.25（近對稱，角色是抽籤決定的）
* 總燃料 8–16 發（每方獨立）
* 窗口 120–900 s（log-uniform）、捕獲半徑 1–20 km（log-uniform）、T_max 2–6 個追者週期
* 一回合 1–3 發（間隔 100 s；窗口放不下的發數照實截掉，例如 120 s 窗口最多 2 發）

`RankingRuleRanges` 是 `RuleRanges` 的子類別：先照父類別的順序抽完所有欄位，再多抽一個
`burns_per_turn`。父類別 `RuleRanges().sample()` 的結果與亂數消耗完全不受影響（tests/test_rule_map.py）。
"""
from dataclasses import dataclass

import numpy as np

from game.rules import RuleRanges, Rules


def burns_that_fit(window_sec: float, burns_per_turn: int, min_burn_gap_sec: float) -> int:
    """窗口裡實際下得了幾發：第 k 發在偏移 k × 間隔，必須 < 窗口長度（同 game.core.plan_turn）。"""
    if burns_per_turn <= 1:
        return 1
    fit = 1 + int((float(window_sec) - 1e-6) // float(min_burn_gap_sec))
    return max(1, min(int(burns_per_turn), fit))


@dataclass(frozen=True)
class RankingRuleRanges(RuleRanges):
    """排位版規則分布（見模組說明）。欄位意義同 RuleRanges，多兩個：

    burns_per_turn：(lo, hi) 整數均勻；min_burn_gap_sec：同窗口兩發的最小間隔（固定值）。"""
    window_sec: tuple = (120.0, 900.0)
    max_dv_pursuer_mps: tuple = (150.0, 400.0)
    evader_dv_ratio: tuple = (0.8, 1.25)
    fuel_turns_pursuer: tuple = (8.0, 16.0)
    fuel_turns_evader: tuple = (8.0, 16.0)
    capture_radius_km: tuple = (1.0, 20.0)
    t_max_periods: tuple = (2.0, 6.0)
    p_pursuer_first: float = 0.5
    gravity_degree: int = 2
    burns_per_turn: tuple = (1, 3)
    min_burn_gap_sec: float = 100.0

    def sample(self, rng: np.random.Generator, base: Rules = Rules()) -> Rules:
        R = super().sample(rng, base)
        lo, hi = self.burns_per_turn
        n = int(rng.integers(int(lo), int(hi) + 1))
        n = burns_that_fit(R.window_sec, n, self.min_burn_gap_sec)
        return R.with_(burns_per_turn=n, min_burn_gap_sec=float(self.min_burn_gap_sec))


PRESETS = {
    "ranking": RankingRuleRanges,
}


def make_ranges(name: str) -> RuleRanges:
    """'default'（= RuleRanges()）或 PRESETS 裡的名字 → 規則分布物件。"""
    if name in ("default", "ranges"):
        return RuleRanges()
    if name not in PRESETS:
        raise KeyError(f"未知的規則分布 {name!r}；可用：default、{', '.join(sorted(PRESETS))}")
    return PRESETS[name]()
