"""Agent 註冊表：用字串 / dict / 物件 / callable 指定 agent。

    make_agent("coast")
    make_agent({"name": "lambert_pursuer", "time_weight_mps": 30})
    make_agent("sb3:runs/xxx/pursuer_final.zip")      # 訓練好的 RL 策略（見 agents/rl.py）
    make_agent("py:agents.foo:BarEvader")             # 任意模組裡的類別/工廠，免改 REGISTRY
    make_agent({"name": "py:agents.foo:BarEvader", "k": 1})
"""
import importlib

from runtime_threads import limit_blas_threads

limit_blas_threads()  # 直接使用 agents.rollout 時，base 匯入 numpy 前也要固定。

from agents.base import Agent, CallableAgent, CoastAgent, PoolAgent, RandomAgent
from agents.analytic import DvEvader, EscapeEvader, LambertPursuer
from agents.search import MinimaxEvader, MinimaxPursuer

REGISTRY = {
    "coast": CoastAgent,
    "random": RandomAgent,
    "pool": PoolAgent,
    "lambert_pursuer": LambertPursuer,
    # 訓練對手用的快速版（決策 ~1.4 ms vs 完整版 ~4–20 ms）：少一圈、網格稀、不做 J2 打靶
    "lambert_pursuer_fast": lambda **kw: LambertPursuer(**{"max_revs": 1, "pts_per_period": 12,
                                                          "j2_shoot": False, **kw}),
    "dv_evader": DvEvader,
    "escape_evader": EscapeEvader,
    "dv_evader_fast": lambda **kw: DvEvader(directions="axes", mags=(1.0,), **kw),
    "minimax_pursuer": MinimaxPursuer,
    "minimax_evader": MinimaxEvader,
    "minimax_evader_fast": lambda **kw: MinimaxEvader(directions="axes", mags=(1.0,), reply_weights=(0.0,), **kw),
    "rollout_pursuer": lambda **kw: _rollout("pursuer", **kw),
    "rollout_evader": lambda **kw: _rollout("evader", **kw),
    "adaptive_evader": lambda **kw: _adaptive(**kw),
    # 受威脅才閃（E22）：平常不推，追者下一回合窗口內攔得到才用 DvEvader 的閃法；排位版規則下對我們所有追者都存活
    "lazy_evader": lambda **kw: _lazy(**kw),
    "safe_evader": lambda **kw: _safe_evader(**kw),
    "safe_evader_fast": lambda **kw: _safe_evader(**{"n_dirs": 60, "mags": (1.0,),
                                                  "grid_sec": 10.0, "lookahead": False,
                                                  "zone_dirs": 30, **kw}),
    "heuristic_evader": lambda **kw: _heuristic_evader(**kw),
    "capture_pursuer": lambda **kw: _capture_pursuer(**kw),
    "capture_pursuer_fast": lambda **kw: _capture_pursuer(**{"n_dirs": 40,
                                                                "lambert_fracs": (0.1, 0.3, 0.6, 1.0),
                                                                "max_model": 15, "grid_sec": 10.0,
                                                                "lookahead": False, **kw}),
}


def _safe_evader(**kw):
    from agents.final_evader import SafeEvader
    return SafeEvader(**kw)


def _heuristic_evader(**kw):
    from agents.final_evader import HeuristicEvader
    return HeuristicEvader(**kw)


def _capture_pursuer(**kw):
    from agents.final_pursuer import CapturePursuer
    return CapturePursuer(**kw)


def _lazy(**kw):
    from agents.evader_lab import LazyEvader3
    return LazyEvader3(**kw)


def _adaptive(**kw):
    from agents.adaptive import AdaptiveEvader
    return AdaptiveEvader(**kw)


def _rollout(side, **kw):
    from agents.rollout import RolloutPlanner
    return RolloutPlanner(side, **kw)


def _py_agent(path, **kw):
    """'模組:類別或工廠'（例 agents.foo:BarEvader）→ agent。新 agent 先用這個規格，穩定後再進 REGISTRY。"""
    mod, _, attr = path.partition(":")
    if not attr:
        raise KeyError(f"py: 規格要寫成 'py:模組:類別'，收到 {path!r}")
    return getattr(importlib.import_module(mod), attr)(**kw)


def make_agent(spec) -> Agent:
    if isinstance(spec, Agent):
        return spec
    if isinstance(spec, str):
        if spec.startswith("sb3:"):
            from agents.rl import SB3Agent
            return SB3Agent.load(spec[4:])
        if spec.startswith("py:"):
            return _py_agent(spec[3:])
        if spec not in REGISTRY:
            raise KeyError(f"未知 agent {spec!r}，可用：{sorted(REGISTRY)} 或 'sb3:<path>'")
        a = REGISTRY[spec]()
        a.name = spec
        return a
    if isinstance(spec, dict):
        kw = dict(spec)
        name = kw.pop("name")
        if name == "sb3":
            from agents.rl import SB3Agent
            return SB3Agent.load(**kw)
        if name.startswith("py:"):
            return _py_agent(name[3:], **kw)
        return REGISTRY[name](**kw)
    if callable(spec):
        return CallableAgent(spec)
    raise TypeError(f"無法把 {spec!r} 變成 agent")


__all__ = ["Agent", "CoastAgent", "RandomAgent", "CallableAgent", "LambertPursuer", "DvEvader",
           "make_agent", "REGISTRY"]
