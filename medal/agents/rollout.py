"""Rollout 規劃器：候選脈衝 × 對手模型集合，逐一推演到比賽結束，挑「最壞情況最好」的一發。

跟 2-ply 極小極大（agents/search.py）的差別：葉節點不用啟發式值（短 horizon 追擊所需 Δv
會飽和/太悲觀，實測比單層 LambertPursuer 還弱），而是**真的下完整場**——對手用多個模型
（解析/RL），我方後續交給 continuation 策略。成本 = 候選數 × 對手模型數 × 一場推演，
適合 copilot 與小規模評測（每步數百 ms ~ 數秒），不適合當訓練對手。

`workers > 1` 時各（候選, 對手模型）推演丟進常駐行程池平行跑（copilot 用；結果與序列版相同）。

分數（我方視角，越大越好）：
  贏：1000 + 追者早抓到/剩油多、躲者剩油多且距離大 的小獎勵
  輸：追者看最近距離（越近越好）、躲者看撐多久（越久越好）
"""
import json
import math
from concurrent.futures import ProcessPoolExecutor

from runtime_threads import limit_blas_threads

import numpy as np

from agents.base import Agent, rsw_to_eci_dv
from agents.scan_reuse import reset_scan_reuse, scoped_decision
from game.core import take_turn

DEFAULTS = {
    "pursuer": dict(
        candidates=[{"name": "lambert_pursuer", "time_weight_mps": w} for w in (0.0, 10.0, 60.0, 300.0)],
        opponents=["coast", "dv_evader_fast"], continuation="lambert_pursuer_fast"),
    "evader": dict(
        candidates=["dv_evader", "dv_evader_fast"],
        opponents=["lambert_pursuer_fast", {"name": "lambert_pursuer_fast", "time_weight_mps": 60.0}],
        continuation="dv_evader_fast"),
}


def outcome_score(h, side):
    s = h.summary()
    R = h.rules
    if h.winner == side:
        if side == "pursuer":
            return 1000.0 + 100.0 * (1.0 - s["t_end"] / h.t_max) + 50.0 * h.fuel_left("pursuer") / max(R.fuel_pursuer_mps, 1)
        return 1000.0 + 50.0 * h.fuel_left("evader") / max(R.fuel_evader_mps, 1) + min(s["final_dist_km"], 1e4) / 100.0
    if side == "pursuer":
        return -min(s["min_dist_km"], 1e5) / 10.0
    return 500.0 * s["t_end"] / h.t_max


def play_out(game, dv, side, cont, opp):
    """從 game 開始：我方推 dv，之後我方交給 cont、對手交給 opp，下到結束，回傳分數。"""
    opp.reset(seed=0)
    h = game.clone()
    h.history = []
    take_turn(h, cont, first_dv=dv)          # 多發規則下，這個窗口剩下的發交給 cont
    while not h.done:
        take_turn(h, cont if h.mover == side else opp)
    return outcome_score(h, side)


# ------------------------------------------------------------------ 平行化
_WORKER_AGENTS = {}
_POOL = {"pool": None, "n": 0}


def _worker_agent(spec):
    from agents import make_agent
    key = json.dumps(spec, sort_keys=True, default=str)
    if key not in _WORKER_AGENTS:
        _WORKER_AGENTS[key] = make_agent(spec)
    return _WORKER_AGENTS[key]


def _rollout_task(args):
    game, dv, side, cont_spec, opp_spec = args
    return play_out(game, dv, side, _worker_agent(cont_spec), _worker_agent(opp_spec))


def _initialize_worker():
    limit_blas_threads()
    reset_scan_reuse()


def _pool(n):
    if _POOL["pool"] is None or _POOL["n"] != n:
        if _POOL["pool"] is not None:
            _POOL["pool"].shutdown(cancel_futures=True)
        _POOL["pool"] = ProcessPoolExecutor(max_workers=n, initializer=_initialize_worker)
        _POOL["n"] = n
    return _POOL["pool"]


class RolloutPlanner(Agent):
    def __init__(self, side, candidates=None, opponents=None, continuation=None, aggregate="min",
                 extra_rsw_fracs=(), workers=0, name=None):
        from agents import make_agent
        self.side = side
        d = DEFAULTS[side]
        self.cand_specs = list(candidates or d["candidates"])
        self.opp_specs = list(opponents or d["opponents"])
        self.cont_spec = continuation or d["continuation"]
        self.cand_agents = [make_agent(c) for c in self.cand_specs]
        self.opp_agents = [make_agent(o) for o in self.opp_specs]
        self.cont = make_agent(self.cont_spec)
        self.aggregate = aggregate
        self.extra_rsw_fracs = tuple(extra_rsw_fracs)   # 額外候選：沿 ±S、+R 推這些比例的上限
        self.workers = int(workers)
        self.name = name or f"rollout_{side}"

    @scoped_decision
    def _candidates(self, game):
        cands = [np.zeros(3)]
        for a in self.cand_agents:
            cands.append(game.clip_dv(self.side, a.act(game, self.side)))
        cap = game.burn_cap(self.side)
        for frac in self.extra_rsw_fracs:
            for d in ((0, 1, 0), (0, -1, 0), (1, 0, 0)):
                cands.append(rsw_to_eci_dv(game, self.side, np.array(d, dtype=float) * frac * cap))
        out = []
        for c in cands:
            if all(np.linalg.norm(c - o) > 0.5 for o in out):
                out.append(c)
        return out

    def evaluate(self, game, side):
        """回傳 [(dv, 各對手模型分數 list)]，供 copilot 顯示。"""
        cands = self._candidates(game)
        if self.workers > 1:
            g = game.clone()
            g.history = []
            tasks = [(g, dv, side, self.cont_spec, o) for dv in cands for o in self.opp_specs]
            flat = list(_pool(self.workers).map(_rollout_task, tasks))
            k = len(self.opp_specs)
            return [(dv, flat[i * k:(i + 1) * k]) for i, dv in enumerate(cands)]
        return [(dv, [play_out(game, dv, side, self.cont, o) for o in self.opp_agents]) for dv in cands]

    def act(self, game, side):
        assert side == self.side
        best_s, best_dv = -math.inf, np.zeros(3)
        for dv, scores in self.evaluate(game, side):
            s = min(scores) if self.aggregate == "min" else float(np.mean(scores))
            if s > best_s:
                best_s, best_dv = s, dv
        return best_dv
