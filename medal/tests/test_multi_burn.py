"""一回合多發（HAP-107）：燃料帳、間隔與發數檢查、窗口中途捕獲、與單發的相容性、GMAT 重播。"""
import os

import numpy as np
import pytest

from agents import make_agent
from game.core import Game, plan_turn, take_turn
from game.rules import Rules
from tools.gmat_verify import GMAT_CONSOLE, game_to_script, verify_game

P0 = {"sma": 7000.0, "ecc": 0.0, "inc": 10.0, "raan": 0.0, "aop": 0.0, "ta": 0.0}
E0 = {"sma": 7050.0, "ecc": 0.001, "inc": 10.2, "raan": 0.0, "aop": 0.0, "ta": 5.0}


def _game(**kw):
    return Game.from_elements(Rules(**kw), P0, E0)


def _burn_offsets(rec):
    return [round(b["t"] - rec["t"], 6) for b in rec["burns"] if b["dv_mps"] > 0.0]


def test_default_rules_are_single_burn():
    assert Rules().burns_per_turn == 1
    with pytest.raises(ValueError):
        Rules(burns_per_turn=0)


def test_plan_fuel_accounting_and_cap():
    g = _game(burns_per_turn=3, max_dv_pursuer_mps=250.0, fuel_pursuer_mps=600.0)
    big = np.array([1e6, 0.0, 0.0])
    rec = g.play_plan([(0.0, big), (100.0, big), (200.0, big)])
    assert [round(b["dv_mps"], 9) for b in rec["burns"] if b["dv_mps"] > 0] == [250.0, 250.0, 100.0]
    assert abs(g.used["pursuer"] - 600.0) < 1e-9
    assert abs(rec["dv_mps"] - 600.0) < 1e-9
    assert rec["coast_sec"] == pytest.approx(300.0)
    assert g.mover == "evader" and g.turn == 1


def test_plan_drops_burns_too_close_or_over_count():
    dv = np.array([0.0, 10.0, 0.0])
    g = _game(burns_per_turn=3, min_burn_gap_sec=100.0)
    rec = g.play_plan([(0.0, dv), (50.0, dv), (150.0, dv), (299.0, dv)])
    assert _burn_offsets(rec) == [0.0, 150.0, 299.0]    # 50 離 0 太近被丟
    g2 = _game(burns_per_turn=2, min_burn_gap_sec=100.0)
    rec2 = g2.play_plan([(0.0, dv), (100.0, dv), (200.0, dv)])
    assert _burn_offsets(rec2) == [0.0, 100.0]          # 超過 2 發的丟掉


def test_plan_can_start_mid_window_and_skips_out_of_window():
    dv = np.array([0.0, 10.0, 0.0])
    g = _game(burns_per_turn=2)
    rec = g.play_plan([(120.0, dv), (400.0, dv)])       # 400 超出 300 s 窗口
    assert _burn_offsets(rec) == [120.0]
    assert rec["coast_sec"] == pytest.approx(300.0)


def test_single_burn_plan_matches_play_turn_exactly():
    dv = np.array([3.0, 40.0, -2.0])
    a = _game(burns_per_turn=3)
    b = _game(burns_per_turn=1)
    ra = a.play_plan([(0.0, dv)])
    rb = b.play_turn(dv)
    for s in ("pursuer", "evader"):
        assert np.array_equal(a.r(s), b.r(s)) and np.array_equal(a.v(s), b.v(s))
    assert ra["coast_sec"] == rb["coast_sec"] and ra["window_min_dist_km"] == rb["window_min_dist_km"]


def test_capture_mid_window_stops_plan():
    """追者以 ~20 m/s 接近 3 km 外的躲者，約 75 s 進 1.5 km 捕獲球：150 s 那發不該執行。"""
    rp, vp = np.array([7000.0, 0.0, 0.0]), np.array([0.0, 7.546, 0.0])
    re, ve = rp + np.array([0.0, 3.0, 0.0]), vp - np.array([0.0, 0.02, 0.0])
    g = Game(Rules(burns_per_turn=2, capture_radius_km=1.5, t_max_sec=3000.0), rp, vp, re, ve)
    first = np.array([0.0, 1.0, 0.0])
    rec = g.play_plan([(0.0, first), (150.0, np.array([0.0, 50.0, 0.0]))])
    assert g.outcome == "capture"
    assert _burn_offsets(rec) == [0.0]
    assert rec["coast_sec"] < 150.0
    assert abs(g.used["pursuer"] - 1.0) < 1e-12
    assert g.history[-1] is rec


def test_take_turn_single_burn_identical_to_act_and_play_turn():
    a, b = _game(), _game()
    P = make_agent("lambert_pursuer")
    take_turn(a, P)
    b.play_turn(P.act(b, "pursuer"))
    assert np.array_equal(a.v("pursuer"), b.v("pursuer"))


def test_take_turn_multi_burn_respects_gap_and_count():
    g = _game(burns_per_turn=3, min_burn_gap_sec=100.0, max_dv_evader_mps=50.0, first_mover="evader")
    rec = take_turn(g, make_agent("escape_evader"))
    offs = _burn_offsets(rec)
    assert 1 <= len(offs) <= 3
    assert all(b - a >= 100.0 - 1e-6 for a, b in zip(offs, offs[1:]))
    assert g.used["evader"] <= 150.0 + 1e-9


def test_plan_turn_mid_window_continues_window():
    """rollout 推演從窗口中途接手時，發數與間隔要算上這個窗口已經下的。"""
    g = _game(burns_per_turn=2, min_burn_gap_sec=100.0)
    assert g.sub_burn(np.array([0.0, 5.0, 0.0]), 100.0) is None and g.mid_window
    plan = plan_turn(g, make_agent({"name": "random", "seed": 1, "p_burn": 1.0}))
    assert len(plan) <= 1 and all(o >= 100.0 - 1e-6 for o, _ in plan)
    rec = g.play_plan(plan)
    assert rec is not None and not g.mid_window
    assert len(_burn_offsets(rec)) <= 2


def test_rollout_planner_runs_with_multi_burn():
    g = _game(burns_per_turn=2, max_dv_pursuer_mps=250.0, max_dv_evader_mps=250.0, t_max_sec=3000.0)
    P = make_agent({"name": "rollout_pursuer"})
    E = make_agent("dv_evader_fast")
    while not g.done:
        take_turn(g, P if g.mover == "pursuer" else E)
    assert g.done


def test_gmat_script_has_every_burn_and_segments_sum_to_window():
    g = _game(burns_per_turn=3, t_max_sec=900.0)
    dv = np.array([0.0, 10.0, 0.0])
    g.play_plan([(0.0, dv), (100.0, dv), (250.0, dv)])
    s = game_to_script(g, "/tmp/x.txt")
    assert "Maneuver B0(ShipP);" in s and "Maneuver B0_1(ShipP);" in s and "Maneuver B0_2(ShipP);" in s
    segs = [float(line.split("= ")[1].rstrip("}; ")) for line in s.splitlines()
            if line.startswith("Propagate") and "ElapsedSecs" in line][:3]
    assert sum(segs) == pytest.approx(300.0)


@pytest.mark.skipif(not os.path.exists(GMAT_CONSOLE), reason="GmatConsole 不在這台機器上")
def test_gmat_replay_multi_burn_matches_physics():
    R = Rules(window_sec=400.0, t_max_sec=4000.0, max_dv_pursuer_mps=150.0, max_dv_evader_mps=100.0,
              fuel_pursuer_mps=1200.0, fuel_evader_mps=600.0, gravity_degree=2, burns_per_turn=3)
    p = {"sma": 6978.0, "ecc": 0.001, "inc": 51.6, "raan": 10.0, "aop": 30.0, "ta": 0.0}
    e = {"sma": 7030.0, "ecc": 0.002, "inc": 52.0, "raan": 10.5, "aop": 40.0, "ta": 350.0}
    g = Game.from_elements(R, p, e)
    P, E = make_agent("lambert_pursuer"), make_agent({"name": "random", "seed": 3, "p_burn": 1.0})
    while not g.done:
        take_turn(g, P if g.mover == "pursuer" else E)
    assert any(len(_burn_offsets(r)) > 1 for r in g.history)
    out = verify_game(g)
    assert out["max_dt_sec"] < 1e-3
    assert out["max_dpos_km"] < 0.01, out["per_turn"]
