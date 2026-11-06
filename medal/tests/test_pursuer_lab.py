"""agents/pursuer_lab.py 的測試（小規模、決定性）。"""
import numpy as np

from agents import make_agent
from agents.base import CallableAgent, CoastAgent, rsw_to_eci_dv
from agents.pursuer_lab import (HarassPursuer, LazyHunter, cornered, evader_decisions, first_threat,
                                window_capture)
from game.core import Game, take_turn
from game.rules import Rules

RANKING = Rules(max_dv_pursuer_mps=250.0, max_dv_evader_mps=250.0, fuel_pursuer_mps=3000.0,
                fuel_evader_mps=3000.0, t_max_sec=3600.0)
NEAR_P = {"sma": 6978.0, "ecc": 0.0, "inc": 51.6, "raan": 10.0, "aop": 0.0, "ta": 0.0}
FAR_E = {"sma": 7010.0, "ecc": 0.001, "inc": 51.8, "raan": 10.3, "aop": 0.0, "ta": 4.0}      # ~500 km
CLOSE_E = {"sma": 6980.0, "ecc": 0.0, "inc": 51.6, "raan": 10.0, "aop": 0.0, "ta": 0.25}     # ~30 km
LAZY = "py:agents.evader_lab:LazyEvader3"


def _evader_turn(p, e, used_evader=0.0):
    g = Game.from_elements(RANKING, p, e)
    g.play_turn(np.zeros(3))                       # 追者先手：不推，輪到躲者
    g.used["evader"] = used_evader
    return g


def test_window_capture_close_vs_far():
    g = Game.from_elements(RANKING, NEAR_P, CLOSE_E)
    dv = window_capture(g)
    assert dv is not None and np.linalg.norm(dv) <= 250.0 + 1e-6
    h = g.clone()
    h.play_turn(dv)
    assert h.outcome == "capture"
    assert window_capture(Game.from_elements(RANKING, NEAR_P, FAR_E)) is None


def test_first_threat_and_cornered():
    lazy = make_agent(LAZY)
    assert first_threat(_evader_turn(NEAR_P, CLOSE_E), lazy, 3) == 0
    assert first_threat(_evader_turn(NEAR_P, FAR_E), lazy, 2) is None
    # 油滿：LazyEvader3 閃一發 250 m/s，追者下一個窗口抓不到；油剩 10 m/s：閃不掉
    assert not cornered(_evader_turn(NEAR_P, CLOSE_E), lazy)
    assert cornered(_evader_turn(NEAR_P, CLOSE_E, used_evader=2990.0), lazy)


def test_harass_takes_window_capture_and_respects_reserve():
    hp = HarassPursuer()
    g = Game.from_elements(RANKING, NEAR_P, CLOSE_E)
    dv = hp.act(g, "pursuer")
    assert hp.log[-1][0] == "capture"
    h = g.clone()
    h.play_turn(dv)
    assert h.outcome == "capture"
    # 非捕獲用途的推力不會吃掉保留的油
    g2 = Game.from_elements(RANKING, NEAR_P, FAR_E)
    g2.used["pursuer"] = 3000.0 - hp.reserve(g2) - 20.0
    assert hp.spend_cap(g2) == 20.0
    dv2 = hp.act(g2, "pursuer")
    assert hp.log[-1][0] != "capture" and np.linalg.norm(dv2) <= 20.0 + 1e-6


def test_harass_finisher_when_evader_empty():
    hp = HarassPursuer()
    g = Game.from_elements(RANKING, NEAR_P, FAR_E)
    g.used["evader"] = 3000.0
    hp.act(g, "pursuer")
    assert hp.log[-1][0] == "finish"


def _play(hunter, evader, n_turns):
    g = Game.from_elements(RANKING, NEAR_P, FAR_E)
    hunter.reset(seed=0)
    for _ in range(n_turns):
        if g.done:
            break
        take_turn(g, hunter if g.mover == "pursuer" else evader)
    return g


def test_evader_decisions_reconstruct_states():
    g = _play(CoastAgent(), CoastAgent(), 4)
    decs = evader_decisions(g)
    assert len(decs) == 2
    snap, dv = decs[1]
    rec = g.history[3]
    assert np.allclose(snap.r("evader"), rec["r_before"]) and np.allclose(snap.r("pursuer"), g.history[2]["rp_after"])
    assert snap.mover == "evader" and dv == 0.0


def test_lazy_hunter_switches_on_lazy_evader_only():
    fast = {"active": "lambert_pursuer_fast", "harass": {"k_max": 2, "fracs": (1.0,), "lam_scales": (1.0,)}}
    hunter = LazyHunter(**fast)
    _play(hunter, CoastAgent(), 5)                 # 躲者兩次決策都沒推 → 換燃料消耗戰
    assert hunter.mode == "harass" and hunter.switches[0][1] == "harass"

    def prograde(game, side):
        return rsw_to_eci_dv(game, side, np.array([0.0, 50.0, 0.0]))

    hunter2 = LazyHunter(**fast)
    _play(hunter2, CallableAgent(prograde), 5)     # 沒受威脅也一直推 → 維持 active
    assert hunter2.mode == "active" and hunter2.switches == []
