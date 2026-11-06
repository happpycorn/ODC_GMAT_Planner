"""金／銅牌賽追方的攔截、模型一致性與對打驗收測試。"""
import copy
import json
import math
import time
from pathlib import Path

import numpy as np
import pytest

from agents import make_agent
import agents.final_evader as final_evader_module
import agents.final_pursuer as final_pursuer_module
from agents.final_common import kepler, perigee_alt_km
from agents.final_evader import HeuristicEvader, heuristic_candidates
from agents.final_pursuer import CapturePursuer
from evaluation.tournament import Task, play
from game.core import Game
from game.rules import Rules
from game.scenarios import sample_final_scenario
from physics import EARTH_MU, get_r0_v0
from physics.lambert import lambert_min_dv


FINAL_RULES = Path(__file__).resolve().parents[1] / "configs" / "rulesets" / "final_official.json"


def _rules(**kw):
    """建立純二體且總推力無上限的同時出手規則。"""
    base = dict(turn_mode="simultaneous", rounds=6, window_sec=1200.0,
                max_dv_pursuer_mps=250.0, max_dv_evader_mps=250.0,
                fuel_pursuer_mps=math.inf, fuel_evader_mps=math.inf,
                capture_radius_km=5.0, gravity_degree=0, crash_altitude_km=0.0)
    base.update(kw)
    return Rules(**base)


def _zero_reachable_game(rules=None):
    """躲方零推時，追方可用一發追上法向相隔 70 km 的軌道。"""
    re, ve = get_r0_v0(sma=7100.0, ecc=0.001, inc=20.0, raan=0.0, aop=0.0, ta=0.0)
    normal = np.cross(re, ve)
    normal /= np.linalg.norm(normal)
    rp, vp = re + 70.0 * normal, ve.copy()
    return Game(_rules() if rules is None else rules, rp, vp, re, ve)


def _away_reachable_game():
    """追方初速較快，躲方背向全推後仍可在一回合內追上。"""
    re, ve = get_r0_v0(sma=7000.0, ecc=0.0, inc=0.0, raan=0.0, aop=0.0, ta=0.0)
    rp = re + np.array([0.0, -20.0, 0.0])
    vp = ve + np.array([0.0, 0.2, 0.0])
    return Game(_rules(), rp, vp, re, ve)


def _far_game(rules=None):
    """雙方相隔半圈，供決策時間與不改動賽局測試使用。"""
    op = dict(sma=7000.0, ecc=0.0, inc=20.0, raan=0.0, aop=0.0, ta=180.0)
    oe = dict(sma=7100.0, ecc=0.0, inc=20.0, raan=0.0, aop=0.0, ta=0.0)
    return Game.from_elements(_rules() if rules is None else rules, op, oe)


def _plain(value):
    """把巢狀回合紀錄轉成可直接比較的 Python 值。"""
    if isinstance(value, np.ndarray):
        return _plain(value.tolist())
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _task(pursuer, evader, rules, scenario, game_id=0):
    return Task(pursuer, evader, rules.to_dict(), scenario.orbit_pursuer,
                scenario.orbit_evader, scenario.family, game_id, 331 + game_id)


def test_zero_evader_reachable_capture():
    """零推躲方的 Lambert 可達題，選出的一發應實際捕獲。"""
    g = _zero_reachable_game()
    target = kepler(g.r("evader"), g.v("evader"), 600.0, EARTH_MU)[0]
    need, _, _ = lambert_min_dv(EARTH_MU, g.r("pursuer"), g.v("pursuer"), target, 600.0, 0)
    assert need * 1000.0 < g.burn_cap("pursuer")
    agent = CapturePursuer(w_zero=1.0, w_heuristic=0.0, w_safe=0.0, seed=7)
    dv = agent.act(g.clone(), "pursuer")
    assert np.linalg.norm(dv) <= g.burn_cap("pursuer") + 1e-8
    g.play_round(dv, np.zeros(3))
    assert g.outcome == "capture"
    assert agent.last_info["chosen_kind"] in {"lambert", "best_response", "direction", "zero"}


def test_hit_probability_matches_model_replay():
    """對相同模型逐一實際重播，捕獲權重不得低於回報機率。"""
    g = _zero_reachable_game()
    kw = dict(n_dirs=24, mags=(1.0,), lambert_fracs=(0.1, 0.3, 0.6, 1.0),
              max_model=10, grid_sec=10.0, lookahead=False, seed=2718)
    model = CapturePursuer(**kw)._evader_model(g.clone())
    agent = CapturePursuer(**kw)
    dv = agent.act(g.clone(), "pursuer")
    assert model
    assert sum(float(row["weight"]) for row in model) == pytest.approx(1.0)
    actual = 0.0
    for row in model:
        sim = g.clone()
        sim.play_round(dv, row["dv_eci_mps"])
        actual += float(row["weight"]) * (sim.outcome == "capture")
    info = agent.last_info
    assert actual >= info["hit_prob"] - 0.02, (actual, info)
    assert info["n_model"] == len(model)
    assert 0.0 <= info["hit_prob_verified"] <= 1.0
    assert len(agent.history_info) == 1


def test_single_heuristic_away_candidate_capture(monkeypatch):
    """躲方確定背向全推且 Lambert 可達時，追方仍能捕獲。"""
    g = _away_reachable_game()
    original = heuristic_candidates

    def only_away(game, side="evader"):
        away = next((dv for name, dv, _ in original(game, side) if name == "away"), None)
        return [] if away is None else [("away", away.copy(), 1.0)]

    monkeypatch.setattr(final_evader_module, "heuristic_candidates", only_away)
    monkeypatch.setattr(final_pursuer_module, "heuristic_candidates", only_away)
    dv_e = HeuristicEvader(seed=9).act(g.clone(), "evader")
    target = kepler(g.r("evader"), g.v("evader") + dv_e / 1000.0, 300.0, EARTH_MU)[0]
    need, _, _ = lambert_min_dv(EARTH_MU, g.r("pursuer"), g.v("pursuer"), target, 300.0, 0)
    assert need * 1000.0 < g.burn_cap("pursuer")
    agent = CapturePursuer(w_zero=0.0, w_heuristic=1.0, w_safe=0.0, seed=9)
    model = agent._evader_model(g.clone())
    assert len(model) == 1
    np.testing.assert_allclose(model[0]["dv_eci_mps"], dv_e, atol=1e-8)
    dv_p = agent.act(g.clone(), "pursuer")
    g.play_round(dv_p, dv_e)
    assert g.outcome == "capture"


def test_selected_burn_does_not_crash_on_twenty_final_scenarios():
    """二十題 final 幾何中，所選推力保留近地點餘裕且不撞地。"""
    rng = np.random.default_rng(15121)
    agent = make_agent("capture_pursuer_fast")
    for case in range(20):
        rules, scenario = sample_final_scenario(rng, _rules())
        g = Game.from_elements(rules, scenario.orbit_pursuer, scenario.orbit_evader)
        agent.reset(seed=case)
        dv = agent.act(g.clone(), "pursuer")
        assert perigee_alt_km(g.r("pursuer"), g.v("pursuer") + dv / 1000.0) >= 30.0 - 1e-6, case
        g.play_round(dv, np.zeros(3))
        assert g.outcome != "crash_pursuer", case


def test_act_preserves_game_state_and_history():
    """決策不改動雙方狀態、時間、燃料與既有回合紀錄。"""
    g = _far_game()
    g.play_round(np.zeros(3), np.zeros(3))
    assert not g.done
    before = {side: (g.r(side).copy(), g.v(side).copy()) for side in ("pursuer", "evader")}
    t_before, turn_before = g.t, g.turn
    used_before = copy.deepcopy(g.used)
    history_before = _plain(copy.deepcopy(g.history))
    agent = CapturePursuer(n_dirs=20, mags=(1.0,), w_zero=1.0, w_heuristic=0.0,
                           w_safe=0.0, lookahead=False, seed=11)
    agent.act(g, "pursuer")
    for side in ("pursuer", "evader"):
        np.testing.assert_array_equal(g.r(side), before[side][0])
        np.testing.assert_array_equal(g.v(side), before[side][1])
    assert (g.t, g.turn, g.used) == (t_before, turn_before, used_before)
    assert _plain(g.history) == history_before
    assert len(agent.history_info) == 1
    agent.reset(seed=11)
    assert agent.last_info == {} and agent.history_info == []


def test_final_round_has_no_next_margin():
    """最後一回合由 snapshot 進入時不計下一回合可達餘量。"""
    g0 = _zero_reachable_game()
    T = g0.rules.window_sec
    g = Game.from_snapshot(g0.rules, g0.r("pursuer"), g0.v("pursuer"),
                           g0.r("evader"), g0.v("evader"), t=5 * T, round_index=5)
    agent = CapturePursuer(n_dirs=20, mags=(1.0,), w_zero=1.0, w_heuristic=0.0,
                           w_safe=0.0, seed=4)
    dv = agent.act(g.clone(), "pursuer")
    assert np.linalg.norm(dv) <= g.burn_cap("pursuer") + 1e-8
    assert agent.last_info["round"] == 6
    assert agent.last_info["next_margin_km"] is None


def test_capture_pursuer_decision_time():
    """暖機後 T=3600 秒的完整版與快速版達到單次決策限制。"""
    g = _far_game(_rules(window_sec=3600.0, safe_sma_km=None))
    full = CapturePursuer(seed=43)
    fast = make_agent({"name": "capture_pursuer_fast", "seed": 43})
    full.act(g.clone(), "pursuer")
    fast.act(g.clone(), "pursuer")
    start = time.perf_counter()
    full.act(g.clone(), "pursuer")
    full_s = time.perf_counter() - start
    start = time.perf_counter()
    fast.act(g.clone(), "pursuer")
    fast_s = time.perf_counter() - start
    print(f"CapturePursuer 決策時間：完整版 {full_s:.3f} s；快速版 {fast_s:.3f} s")
    assert full_s < 5.0
    assert fast_s < 1.0


def test_tournament_records_info_against_three_evaders():
    """三種躲方各打一局 final 題，結果合法且追方紀錄可序列化。"""
    with FINAL_RULES.open() as f:
        base_rules = Rules.from_dict(json.load(f))
    rules, scenario = sample_final_scenario(np.random.default_rng(331), base_rules)
    outcomes = {"capture", "crash_pursuer", "crash_evader", "escape", "sma_out"}
    for evader in ("safe_evader", "heuristic_evader", "dv_evader"):
        out = play(_task("capture_pursuer", evader, rules, scenario))
        assert out["outcome"] in outcomes, evader
        assert 1 <= out["rounds_played"] <= 6
        assert isinstance(out["info_pursuer"], list) and out["info_pursuer"]
        assert len(out["info_pursuer"]) == out["rounds_played"]
        if evader == "safe_evader":
            assert isinstance(out["info_evader"], list)
        else:
            assert out["info_evader"] is None
        json.dumps(out)


def test_capture_rate_at_least_lambert_against_coast():
    """同十題 final 幾何比較對 coast 的實際捕獲率。"""
    rng = np.random.default_rng(20261101)
    base_rules = _rules()
    scenarios = [sample_final_scenario(rng, base_rules) for _ in range(10)]
    counts = {}
    for pursuer in ("capture_pursuer", "lambert_pursuer"):
        counts[pursuer] = sum(
            play(_task(pursuer, "coast", rules, scenario, game_id=i))["outcome"] == "capture"
            for i, (rules, scenario) in enumerate(scenarios))
    print(f"對 coast 的十題捕獲：CapturePursuer {counts['capture_pursuer']}/10；"
          f"LambertPursuer {counts['lambert_pursuer']}/10")
    assert counts["capture_pursuer"] >= counts["lambert_pursuer"]
