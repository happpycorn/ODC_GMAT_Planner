"""決賽規則參數與規則分布。

⚠️ 官方決賽規則（HAP-50）尚未公告。這裡的預設值是**佔位**：沿用初賽的量級（單次
Δv 上限 1500 m/s、T_max = 4 × 追者週期、5 km 捕獲半徑）。因為數字未知，訓練時
用 `RuleRanges` 隨機抽規則並把規則參數放進觀測（rule-conditioned policy），公告一到
只要填 `Rules(...)` 就能直接評估 / 微調。
"""
from dataclasses import asdict, dataclass, fields, replace
import math

import numpy as np

SIDES = ("pursuer", "evader")
TURN_MODES = ("alternating", "simultaneous")


def other(side: str) -> str:
    return "evader" if side == "pursuer" else "pursuer"


@dataclass(frozen=True)
class Rules:
    window_sec: float = 300.0            # 一方下完脈衝後雙方滑行的時間（回合交替的一半）
    max_dv_pursuer_mps: float = 1500.0   # 追者單次脈衝上限
    max_dv_evader_mps: float = 1500.0    # 躲者單次脈衝上限
    fuel_pursuer_mps: float = 3000.0     # 追者總 Δv 預算
    fuel_evader_mps: float = 3000.0      # 躲者總 Δv 預算
    capture_radius_km: float = 5.0       # 相對距離 <= 此值即捕獲（追者勝）
    t_max_sec: float = 0.0               # > 0 直接指定；<= 0 用 t_max_boundary_km 或 t_max_periods × 追者初始週期
    t_max_periods: float = 4.0           # 追者初始軌道是雙曲線（沒有週期）時改用躲者的週期
    # > 0（且 t_max_sec <= 0）：排位賽定義——飛掠方（初始比能量較高的一方，排位賽的外星船 A）純滑行、
    # 過近地點後地心距離第一次增加到這個值（km，地心距離）的時刻。見 game.core.boundary_exit_time
    t_max_boundary_km: float = 0.0
    gravity_degree: int = 2              # 0=點質量, 2=J2, 3=J3, 4=J4（同 physics.propagate）
    first_mover: str = "pursuer"         # 誰先下第一發
    crash_altitude_km: float = 100.0     # 軌跡低於此高度 = 撞地/再入（佔位，同 Planner MIN_PERIAPSIS）
    substep_sec: float = 60.0            # 窗口內事件偵測的分段長度（數值參數，不是規則）
    capture_mode: str = "continuous"     # "continuous"：任何時刻進捕獲球就算；"endpoint"：只看每回合結束瞬間
    burns_per_turn: int = 1              # 一個回合（窗口）內輪到的一方最多下幾發（HAP-107）
    min_burn_gap_sec: float = 100.0      # 同一窗口內兩發的最小間隔（照排位賽規則；只在 burns_per_turn > 1 時有作用）
    # 金／銅牌賽正式賽制（2026/10/29 規則）："simultaneous" = 雙方在回合起點同時各推一發、互相看不到，
    # 每回合滑行 window_sec（= T_round），共 rounds 回合。"alternating" = 舊的回合交替。
    turn_mode: str = "alternating"
    rounds: int = 6                      # simultaneous 的回合數；T_max = rounds × window_sec（t_max_sec 沒給時）
    # simultaneous 終局：最後一回合結束時逃方半長軸（km，雙曲線為負）落在 [lo, hi] 才算逃方贏；None = 撐完就贏
    safe_sma_km: tuple = None

    def __post_init__(self):
        if self.first_mover not in SIDES:
            raise ValueError(f"first_mover 必須是 {SIDES}，收到 {self.first_mover!r}")
        if self.capture_mode not in ("continuous", "endpoint"):
            raise ValueError(f"capture_mode 必須是 continuous / endpoint，收到 {self.capture_mode!r}")
        if self.burns_per_turn < 1:
            raise ValueError("burns_per_turn 至少 1")
        if self.window_sec <= 0:
            raise ValueError("window_sec 必須 > 0")
        if not self.t_max_boundary_km >= 0:
            raise ValueError(f"t_max_boundary_km 必須 >= 0（0 = 不用邊界定義），收到 {self.t_max_boundary_km!r}")
        if self.turn_mode not in TURN_MODES:
            raise ValueError(f"turn_mode 必須是 {TURN_MODES}，收到 {self.turn_mode!r}")
        if self.rounds < 1:
            raise ValueError("rounds 至少 1")
        if self.turn_mode == "simultaneous" and self.burns_per_turn != 1:
            raise ValueError("simultaneous 賽制每回合只能一發（burns_per_turn 必須是 1）")
        if self.safe_sma_km is not None:
            lo, hi = self.safe_sma_km
            if not (math.isfinite(lo) and math.isfinite(hi) and lo < hi):
                raise ValueError(f"safe_sma_km 必須是 (lo, hi) 且 lo < hi，收到 {self.safe_sma_km!r}")

    def max_dv(self, side: str) -> float:
        return self.max_dv_pursuer_mps if side == "pursuer" else self.max_dv_evader_mps

    def fuel(self, side: str) -> float:
        return self.fuel_pursuer_mps if side == "pursuer" else self.fuel_evader_mps

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Rules":
        if isinstance(d, Rules):
            return d
        names = {f.name for f in fields(cls)}
        d = {k: v for k, v in d.items() if not k.startswith("_")}   # "_comment" 之類的註解欄位
        unknown = set(d) - names
        if unknown:
            raise KeyError(f"未知的規則欄位：{sorted(unknown)}（可用：{sorted(names)}）")
        for k in ("fuel_pursuer_mps", "fuel_evader_mps"):
            if k in d and d[k] is None:
                d[k] = math.inf                          # JSON 的 null = 總 Δv 不設上限
        if d.get("safe_sma_km") is not None:
            d["safe_sma_km"] = tuple(float(x) for x in d["safe_sma_km"])
        return cls(**d)

    def with_(self, **kw) -> "Rules":
        if kw.get("safe_sma_km") is not None:
            kw["safe_sma_km"] = tuple(float(x) for x in kw["safe_sma_km"])
        return replace(self, **kw)

    @property
    def simultaneous(self) -> bool:
        return self.turn_mode == "simultaneous"


def _loguniform(rng, lo, hi):
    return float(math.exp(rng.uniform(math.log(lo), math.log(hi))))


@dataclass(frozen=True)
class RuleRanges:
    """規則分布（官方公告前的訓練/評估用）。每個欄位是 (lo, hi)。"""
    window_sec: tuple = (120.0, 900.0)          # log-uniform
    max_dv_pursuer_mps: tuple = (50.0, 1500.0)  # log-uniform
    evader_dv_ratio: tuple = (0.3, 1.0)         # 躲者單次上限 = 追者 × ratio
    fuel_turns_pursuer: tuple = (2.0, 8.0)      # 追者總預算 = 單次上限 × turns
    fuel_turns_evader: tuple = (2.0, 8.0)
    capture_radius_km: tuple = (1.0, 20.0)      # log-uniform
    t_max_periods: tuple = (1.5, 5.0)
    p_pursuer_first: float = 0.5
    gravity_degree: int = 2

    def sample(self, rng: np.random.Generator, base: Rules = Rules()) -> Rules:
        max_dv_p = _loguniform(rng, *self.max_dv_pursuer_mps)
        max_dv_e = max_dv_p * rng.uniform(*self.evader_dv_ratio)
        return base.with_(
            window_sec=_loguniform(rng, *self.window_sec),
            max_dv_pursuer_mps=max_dv_p,
            max_dv_evader_mps=max_dv_e,
            fuel_pursuer_mps=max_dv_p * rng.uniform(*self.fuel_turns_pursuer),
            fuel_evader_mps=max_dv_e * rng.uniform(*self.fuel_turns_evader),
            capture_radius_km=_loguniform(rng, *self.capture_radius_km),
            t_max_sec=0.0,
            t_max_periods=float(rng.uniform(*self.t_max_periods)),
            gravity_degree=self.gravity_degree,
            first_mover="pursuer" if rng.random() < self.p_pursuer_first else "evader",
        )
