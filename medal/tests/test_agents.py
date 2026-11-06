"""解析 / 搜尋 agent 與對打評測系統的測試（小規模、決定性）。"""
import math

import numpy as np

from agents import make_agent
from agents.analytic import orbit_survives, pursuer_need
from evaluation.tournament import make_games, markdown_report, run_tournament
from game.core import Game
from game.rules import Rules
from physics.frames import rsw_basis

NEAR_P = {"sma": 6978.0, "ecc": 0.0, "inc": 51.6, "raan": 10.0, "aop": 0.0, "ta": 0.0}
NEAR_E = {"sma": 7010.0, "ecc": 0.001, "inc": 51.8, "raan": 10.3, "aop": 0.0, "ta": 4.0}


def _play(P, E, rules, p=NEAR_P, e=NEAR_E):
    g = Game.from_elements(rules, p, e)
    while not g.done:
        a = P if g.mover == "pursuer" else E
        g.play_turn(a.act(g, g.mover))
    return g


def test_lambert_pursuer_captures_passive_target():
    g = _play(make_agent("lambert_pursuer"), make_agent("coast"), Rules())
    assert g.outcome == "capture", g.summary()
    assert g.used["pursuer"] <= Rules().fuel_pursuer_mps


def test_orbit_survives_detects_deorbit_burn():
    g = Game.from_elements(Rules(), NEAR_P, NEAR_E)
    retro = rsw_basis(g.r("pursuer"), g.v("pursuer")).T @ np.array([0.0, -1500.0, 0.0])
    assert not orbit_survives(g, "pursuer", retro)
    assert orbit_survives(g, "pursuer", np.zeros(3))


def test_pursuer_need_drops_after_following_solution():
    g = Game.from_elements(Rules(t_max_sec=12000.0), NEAR_P, NEAR_E)
    need0, _ = pursuer_need(g)
    assert math.isfinite(need0)
    dv = make_agent("lambert_pursuer").act(g, "pursuer")
    g.play_turn(dv)
    g.play_turn(np.zeros(3))
    need1, _ = pursuer_need(g)
    assert need1 < need0


def test_search_agents_return_legal_moves():
    rules = Rules(max_dv_pursuer_mps=200.0, max_dv_evader_mps=100.0, fuel_pursuer_mps=800.0,
                  fuel_evader_mps=400.0, window_sec=600.0, t_max_sec=3000.0)
    g = Game.from_elements(rules, NEAR_P, NEAR_E)
    dv = make_agent("minimax_pursuer").act(g, "pursuer")
    assert np.linalg.norm(dv) <= 200.0 + 1e-6
    g.play_turn(dv)
    dv = make_agent("minimax_evader_fast").act(g, "evader")
    assert np.linalg.norm(dv) <= 100.0 + 1e-6


def test_rollout_planner_picks_legal_move_and_captures_passive_target():
    rules = Rules(t_max_sec=6000.0)
    P = make_agent({"name": "rollout_pursuer", "opponents": ["coast"],
                    "candidates": ["lambert_pursuer", {"name": "lambert_pursuer", "time_weight_mps": 300.0}]})
    g = _play(P, make_agent("coast"), rules)
    assert g.outcome == "capture", g.summary()


def test_rollout_parallel_matches_serial():
    from agents.rollout import RolloutPlanner
    rules = Rules(t_max_sec=5000.0, max_dv_evader_mps=300.0, fuel_evader_mps=600.0)
    g = Game.from_elements(rules, NEAR_P, NEAR_E)
    kw = dict(candidates=["lambert_pursuer", {"name": "lambert_pursuer", "time_weight_mps": 300.0}],
              opponents=["coast", "dv_evader_fast"])
    serial = RolloutPlanner("pursuer", **kw).evaluate(g, "pursuer")
    parallel = RolloutPlanner("pursuer", workers=2, **kw).evaluate(g, "pursuer")
    assert len(serial) == len(parallel)
    for (dv_s, sc_s), (dv_p, sc_p) in zip(serial, parallel):
        assert np.allclose(dv_s, dv_p) and np.allclose(sc_s, sc_p)


def test_escape_evader_burns_twice_then_hands_over():
    rules = Rules(first_mover="evader", t_max_sec=4000.0)
    g = Game.from_elements(rules, NEAR_P, NEAR_E)
    E = make_agent("escape_evader")
    E.reset()
    mags = []
    while not g.done:
        if g.mover == "evader":
            rec = g.play_turn(E.act(g, "evader"))
            mags.append(rec["dv_mps"])
        else:
            g.play_turn(np.zeros(3))
    assert mags[0] > 1000.0 and mags[1] > 1000.0          # 開局兩發推滿（或為了存活減半）
    assert g.outcome != "crash_evader"


def test_adaptive_evader_picks_by_fuel_ratio():
    from agents.adaptive import AdaptiveEvader
    from agents.analytic import EscapeEvader
    from agents.rollout import RolloutPlanner
    a = AdaptiveEvader()
    assert isinstance(a.choose(Rules()), EscapeEvader)                                  # 對稱 → 逃逸
    assert isinstance(a.choose(Rules(fuel_pursuer_mps=6000.0)), RolloutPlanner)         # 追者 2× → rollout
    assert isinstance(a.choose(Rules(max_dv_evader_mps=500.0)), RolloutPlanner)         # 躲者單發小 → rollout
    g = Game.from_elements(Rules(first_mover="evader", t_max_sec=3000.0), NEAR_P, NEAR_E)
    a.reset()
    dv = a.act(g, "evader")
    assert np.linalg.norm(dv) > 1000.0                                                   # 對稱規則開局推滿


def test_tournament_runs_and_reports():
    games = make_games(2, "default", "near_coplanar", seed=1)
    res = run_tournament(["lambert_pursuer"], ["coast", "random"], games, workers=1, progress=False)
    assert len(res) == 4
    md = markdown_report(res)
    assert "lambert_pursuer" in md and "coast" in md
