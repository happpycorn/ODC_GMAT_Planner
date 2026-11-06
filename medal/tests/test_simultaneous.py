"""金／銅牌賽正式賽制（同時出手回合、安全空域終局）：game.rules / game.core / 題目產生器 / GMAT 二體重播。"""
import json
import math
import os

import numpy as np
import pytest

from game.core import Game, round_view, sma_official, take_round, take_turn
from game.rules import Rules
from game.scenarios import (FINAL_DIST_KM, FINAL_MIN_PERIGEE_ALT_KM, FINAL_ZONE_ROUNDS, FINAL_ZONE_WIDTH_ROUNDS,
                            full_burn_dsma_km, sample_final_scenario)
from physics import EARTH_MU, RE_VAL, get_r0_v0, propagate

FINAL_RULES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "configs", "rulesets", "final_official.json")
ORB_P = {"sma": 7000.0, "ecc": 0.001, "inc": 30.0, "raan": 0.0, "aop": 0.0, "ta": 0.0}
ORB_E = {"sma": 7050.0, "ecc": 0.002, "inc": 30.0, "raan": 0.0, "aop": 0.0, "ta": 5.0}


def _rules(**kw):
    base = dict(turn_mode="simultaneous", rounds=6, window_sec=600.0, max_dv_pursuer_mps=250.0,
                max_dv_evader_mps=250.0, fuel_pursuer_mps=math.inf, fuel_evader_mps=math.inf,
                capture_radius_km=5.0, gravity_degree=0, crash_altitude_km=0.0)
    base.update(kw)
    return Rules(**base)


def _final_rules():
    with open(FINAL_RULES) as f:
        return Rules.from_dict(json.load(f))


# ------------------------------------------------------------------ 1. Rules
def test_rules_validation():
    with pytest.raises(ValueError):
        _rules(burns_per_turn=2)
    with pytest.raises(ValueError):
        _rules(safe_sma_km=(7100.0, 7000.0))
    with pytest.raises(ValueError):
        _rules(safe_sma_km=(7000.0, 7000.0))
    with pytest.raises(ValueError):
        _rules(turn_mode="random")
    with pytest.raises(ValueError):
        _rules(rounds=0)
    R = Rules.from_dict({"turn_mode": "simultaneous", "fuel_pursuer_mps": None, "fuel_evader_mps": None,
                         "safe_sma_km": [7000, 7100]})
    assert R.fuel_pursuer_mps == math.inf and R.fuel_evader_mps == math.inf
    assert R.safe_sma_km == (7000.0, 7100.0) and isinstance(R.safe_sma_km, tuple)
    assert R.simultaneous and not Rules().simultaneous
    assert Rules.from_dict(R.to_dict()) == R


def test_final_official_ruleset():
    R = _final_rules()
    assert R.simultaneous and R.rounds == 6 and R.burns_per_turn == 1
    assert R.gravity_degree == 0 and R.crash_altitude_km == 0.0
    assert R.fuel_pursuer_mps == math.inf and R.fuel_evader_mps == math.inf
    assert R.safe_sma_km is None


# ------------------------------------------------------------------ 2. play_round 施加與縮放
def test_play_round_applies_both_burns_at_round_start():
    g = Game.from_elements(_rules(), ORB_P, ORB_E)
    assert g.t_max == 6 * 600.0 and g.t_max_basis == "rounds"
    rp0, vp0, re0, ve0 = g.r("pursuer").copy(), g.v("pursuer").copy(), g.r("evader").copy(), g.v("evader").copy()
    dv_p, dv_e = np.array([30.0, -20.0, 10.0]), np.array([-5.0, 40.0, 0.0])
    rec = g.play_round(dv_p, dv_e)
    rp1, _ = propagate(EARTH_MU, rp0, vp0 + dv_p / 1000.0, 600.0, 0)
    re1, _ = propagate(EARTH_MU, re0, ve0 + dv_e / 1000.0, 600.0, 0)
    assert np.linalg.norm(g.r("pursuer") - rp1) < 1e-3
    assert np.linalg.norm(g.r("evader") - re1) < 1e-3
    assert rec["round"] == 1 and rec["turn"] == 0 and rec["side"] == "both" and rec["t"] == 0.0
    assert [b["side"] for b in rec["burns"]] == ["pursuer", "evader"]
    assert all(b["t"] == 0.0 and not b["scaled"] for b in rec["burns"])
    np.testing.assert_allclose(rec["burns"][0]["r_before"], rp0)
    np.testing.assert_allclose(rec["burns"][1]["v_before"], ve0)
    assert rec["coast_sec"] == 600.0 and g.t == 600.0 and g.turn == 1
    assert rec["sma_evader_km"] == pytest.approx(sma_official(g.r("evader"), g.v("evader")))
    for k in ("window_min_dist_km", "t_window_min", "distance_after_km", "rp_after", "vp_after", "re_after",
              "ve_after", "outcome"):
        assert k in rec
    assert g.used["pursuer"] == pytest.approx(np.linalg.norm(dv_p))


def test_play_round_scales_oversized_burn():
    g = Game.from_elements(_rules(), ORB_P, ORB_E)
    dv_p = np.array([300.0, 400.0, 0.0])                     # 500 m/s > 250
    rec = g.play_round(dv_p, np.zeros(3))
    bp, be = rec["burns"]
    assert bp["scaled"] and bp["dv_mps"] == pytest.approx(250.0)
    np.testing.assert_allclose(bp["dv_eci_mps"], dv_p * 0.5)
    np.testing.assert_array_equal(bp["dv_submitted_mps"], dv_p)
    assert not be["scaled"] and be["dv_mps"] == 0.0
    assert g.used["pursuer"] == pytest.approx(250.0)


# ------------------------------------------------------------------ 3. 回合中途捕獲
def test_capture_mid_round_stops_at_event():
    re, ve = get_r0_v0(**ORB_E)
    w = np.cross(re, ve)
    w /= np.linalg.norm(w)
    rp, vp = re + 15.0 * w, ve - 0.05 * w                    # 法向 15 km、以 50 m/s 靠近
    g = Game(_rules(window_sec=1200.0), rp, vp, re, ve)
    rec = g.play_round(np.zeros(3), np.zeros(3))
    assert g.done and g.outcome == "capture" and g.winner == "pursuer"
    assert 100.0 < g.t < 300.0 and rec["coast_sec"] == pytest.approx(g.t)
    assert g.distance() <= g.rules.capture_radius_km + 1e-3
    with pytest.raises(RuntimeError):
        g.play_round(np.zeros(3), np.zeros(3))


# ------------------------------------------------------------------ 4. 終局判定
def _coast_out(R, orb_e=ORB_E):
    g = Game.from_elements(R, ORB_P, orb_e)
    while not g.done:
        g.play_round(np.zeros(3), np.zeros(3))
    return g


def test_terminal_outcomes():
    a0 = sma_official(*get_r0_v0(**ORB_E))
    g = _coast_out(_rules(safe_sma_km=(a0 - 10.0, a0 + 10.0)))
    assert g.outcome == "escape" and g.winner == "evader"
    assert g.turn == 6 and g.t == pytest.approx(6 * 600.0) and len(g.history) == 6
    s = g.summary()
    assert s["rounds_played"] == 6 and s["final_sma_evader_km"] == pytest.approx(a0, abs=1e-6)
    assert [h["round"] for h in g.history] == [1, 2, 3, 4, 5, 6]
    assert g.history[-1]["outcome"] == "escape" and all(h["outcome"] is None for h in g.history[:-1])

    g = _coast_out(_rules(safe_sma_km=(a0 + 10.0, a0 + 100.0)))
    assert g.outcome == "sma_out" and g.winner == "pursuer"

    g = _coast_out(_rules(safe_sma_km=None))
    assert g.outcome == "timeout" and g.winner == "evader"


def test_hyperbolic_evader_is_sma_out():
    re, ve = get_r0_v0(**ORB_E)
    ve = ve * 1.5                                             # 超過脫離速度
    assert sma_official(re, ve) < 0
    g = Game(_rules(safe_sma_km=(6900.0, 7200.0)), *get_r0_v0(**ORB_P), re, ve)
    while not g.done:
        g.play_round(np.zeros(3), np.zeros(3))
    assert g.outcome == "sma_out" and g.summary()["final_sma_evader_km"] < 0


def test_sma_official():
    r, v = get_r0_v0(sma=7000.0, ecc=0.1, inc=10.0, raan=0.0, aop=0.0, ta=40.0)
    assert sma_official(r, v) == pytest.approx(7000.0)
    assert sma_official(r, v * 1.5) < 0                       # 雙曲線為負
    assert sma_official(np.array([2.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0]), mu=1.0) == math.inf   # 拋物線


# ------------------------------------------------------------------ 5. 撞地（地表）
def test_crash_through_surface():
    low = {"sma": 6700.0, "ecc": 0.05, "inc": 30.0, "raan": 0.0, "aop": 0.0, "ta": 180.0}   # 近地點在地表下
    assert low["sma"] * (1 - low["ecc"]) < RE_VAL
    g = _coast_out(_rules(window_sec=1200.0), low)
    assert g.outcome == "crash_evader" and g.winner == "pursuer"
    assert np.linalg.norm(g.r("evader")) == pytest.approx(RE_VAL, abs=1e-3)

    graze = dict(low, sma=(RE_VAL + 10.0) / 0.95)                 # 近地點高度 10 km：掠過不算撞
    g = _coast_out(_rules(window_sec=1200.0), graze)
    assert g.outcome == "timeout"
    assert g.t == pytest.approx(6 * 1200.0)


# ------------------------------------------------------------------ 6. take_round：副本、互相看不到
class _Spy:
    simultaneous_aware = True

    def __init__(self, dv):
        self.dv = np.asarray(dv, dtype=float)
        self.seen = []

    def act(self, game, side):
        self.seen.append({"t": game.t, "n_hist": len(game.history),
                          "v_other": game.v("pursuer" if side == "evader" else "evader").copy(),
                          "turn_mode": game.rules.turn_mode})
        game.play_round(np.array([200.0, 0.0, 0.0]), np.array([0.0, 200.0, 0.0]))   # 亂動副本
        game.used[side] = 1e9
        return self.dv


class _Legacy:
    def act(self, game, side):
        self.view = game
        game.play_turn(np.array([0.0, 0.0, 100.0]))          # 舊 agent 在副本上用 play_turn 模擬
        return np.zeros(3)


def test_take_round_gives_isolated_copies():
    g = Game.from_elements(_rules(), ORB_P, ORB_E)
    v_p0 = g.v("pursuer").copy()
    P, E = _Spy([10.0, 0.0, 0.0]), _Spy([0.0, 0.0, -10.0])
    rec = take_round(g, P, E)
    assert E.seen[0]["n_hist"] == 0 and E.seen[0]["t"] == 0.0
    np.testing.assert_array_equal(E.seen[0]["v_other"], v_p0)  # 看不到追方這回合的 Δv
    assert E.seen[0]["turn_mode"] == "simultaneous"
    assert len(g.history) == 1 and g.turn == 1 and g.t == 600.0
    np.testing.assert_allclose(rec["burns"][0]["dv_eci_mps"], [10.0, 0.0, 0.0])
    np.testing.assert_allclose(rec["burns"][1]["dv_eci_mps"], [0.0, 0.0, -10.0])
    assert g.used["pursuer"] == pytest.approx(10.0) and g.used["evader"] == pytest.approx(10.0)


def test_legacy_agent_gets_alternating_view():
    g = Game.from_elements(_rules(), ORB_P, ORB_E)
    take_round(g, _Spy(np.zeros(3)), _Spy(np.zeros(3)))
    L = _Legacy()
    view = round_view(g, L, "evader")
    assert view.rules.turn_mode == "alternating" and view.mover == "evader"
    assert view.t_max == g.t_max and view.t == g.t
    take_round(g, _Spy(np.zeros(3)), L)
    assert len(g.history) == 2 and g.history[-1]["side"] == "both"
    assert L.view.history[-1]["side"] == "evader"            # 只動到副本


# ------------------------------------------------------------------ 7. 模式互斥
def test_mode_guards():
    g = Game.from_elements(Rules(), ORB_P, ORB_E)
    with pytest.raises(RuntimeError):
        g.play_round(np.zeros(3), np.zeros(3))
    g = Game.from_elements(_rules(), ORB_P, ORB_E)
    with pytest.raises(RuntimeError):
        g.play_turn(np.zeros(3))
    with pytest.raises(RuntimeError):
        g.sub_burn(np.zeros(3), 100.0)
    with pytest.raises(RuntimeError):
        g.play_plan([(0.0, np.zeros(3))])


def test_from_snapshot_round_index():
    R = _rules(safe_sma_km=(7000.0, 7100.0))
    rp, vp = get_r0_v0(**ORB_P)
    re, ve = get_r0_v0(**ORB_E)
    g = Game.from_snapshot(R, rp, vp, re, ve, t=1800.0)
    assert g.turn == 3 and g.t_max == 3600.0 and not g.done
    assert Game.from_snapshot(R, rp, vp, re, ve, t=1800.0, round_index=2).turn == 2
    g = Game.from_snapshot(R, rp, vp, re, ve, t=1800.0, round_index=3)
    while not g.done:
        g.play_round(np.zeros(3), np.zeros(3))
    assert g.turn == 6 and g.history[0]["round"] == 4 and g.t == pytest.approx(3600.0)
    g = Game.from_snapshot(R, rp, vp, re, ve, t=3600.0)
    assert g.done and g.outcome in ("escape", "sma_out")


# ------------------------------------------------------------------ 11. 題目產生器
def test_sample_final_scenario():
    R0 = _final_rules()
    n_in = 0
    for i in range(50):
        R, sc = sample_final_scenario(np.random.default_rng([7, i]), R0)
        assert sc.family == "final" and R.simultaneous and R.safe_sma_km is not None
        assert R.with_(safe_sma_km=None) == R0
        rp, vp = get_r0_v0(**sc.orbit_pursuer)
        re, ve = get_r0_v0(**sc.orbit_evader)
        assert FINAL_DIST_KM[0] <= np.linalg.norm(rp - re) <= FINAL_DIST_KM[1]
        for o in (sc.orbit_pursuer, sc.orbit_evader):
            assert 400.0 <= o["sma"] - RE_VAL <= 1500.0
            assert o["sma"] * (1 - o["ecc"]) - RE_VAL >= FINAL_MIN_PERIGEE_ALT_KM
        a0 = sma_official(re, ve)
        da = full_burn_dsma_km(a0, R.max_dv_evader_mps)
        lo, hi = R.safe_sma_km
        width, center = hi - lo, (lo + hi) / 2
        assert FINAL_ZONE_WIDTH_ROUNDS[0] - 1e-9 <= width / da <= FINAL_ZONE_WIDTH_ROUNDS[1] + 1e-9
        assert lo > RE_VAL
        if lo <= a0 <= hi:
            n_in += 1
        else:
            assert FINAL_ZONE_ROUNDS[0] - 1e-9 <= abs(center - a0) / da <= FINAL_ZONE_ROUNDS[1] + 1e-9
        g = Game.from_elements(R, sc.orbit_pursuer, sc.orbit_evader)
        assert not g.done and g.t_max == R.rounds * R.window_sec
    assert 4 <= n_in <= 18                                    # 約 20%


def test_tournament_final_scenario():
    from evaluation.tournament import Task, make_games, play
    with open(FINAL_RULES) as f:
        games = make_games(2, json.load(f), "final", seed=0)
    for R, op, oe, fam in games:
        assert fam == "final" and R["safe_sma_km"] is not None
        out = play(Task("coast", {"name": "random", "seed": 1, "p_burn": 1.0}, R, op, oe, fam, 0, 0))
        assert out["outcome"] in ("capture", "crash_pursuer", "crash_evader", "escape", "sma_out")
        assert 1 <= out["rounds_played"] <= 6


# ------------------------------------------------------------------ 10. GMAT 二體重播
def _gmat():
    from tools.gmat_verify import GMAT_CONSOLE
    return GMAT_CONSOLE if os.path.exists(GMAT_CONSOLE) else None


def _final_game(min_rounds=3):
    from agents import make_agent
    R0 = _final_rules()
    for seed in range(20):
        R, sc = sample_final_scenario(np.random.default_rng([11, seed]), R0)
        g = Game.from_elements(R, sc.orbit_pursuer, sc.orbit_evader)
        P = make_agent({"name": "random", "seed": seed, "p_burn": 1.0})
        E = make_agent({"name": "random", "seed": seed + 100, "p_burn": 1.0})
        while not g.done:
            take_round(g, P, E)
        if g.turn >= min_rounds:
            return g
    raise RuntimeError("找不到撐過 3 回合的局")


def test_gmat_script_simultaneous():
    from tools.gmat_verify import game_to_script
    g = _final_game()
    script = game_to_script(g, "/tmp/x.txt")
    script.encode("ascii")
    names = [ln.split()[2].rstrip(";") for ln in script.splitlines() if ln.startswith("Create ImpulsiveBurn")]
    assert len(names) == len(set(names)) == 2 * len(g.history)
    assert "Maneuver B0(ShipP);" in script and "Maneuver B0_1(ShipE);" in script
    assert script.count("Propagate Synchronized") == len(g.history)
    assert script.count("Report Rep") == len(g.history) + 1
    assert "FM.GravityField.Earth.Degree = 0;" in script


@pytest.mark.skipif(_gmat() is None, reason="GmatConsole 不在這台機器上")
def test_gmat_replay_simultaneous_two_body():
    from tools.gmat_verify import verify_game
    g = _final_game()
    out = verify_game(g, force_model="zonal")
    assert out["turns"] == g.turn >= 3
    for p in out["per_turn"]:
        assert p["dpos_pursuer_km"] < 0.010 and p["dpos_evader_km"] < 0.010, p
        assert abs(p["dt_sec"]) < 1e-3


@pytest.mark.skipif(_gmat() is None, reason="GmatConsole 不在這台機器上")
def test_gmat_step_simultaneous_round():
    from tools.gmat_verify import gmat_step
    g = _final_game()
    rec = g.history[1]
    state = {"pursuer": (rec["burns"][0]["r_before"], rec["burns"][0]["v_before"]),
             "evader": (rec["burns"][1]["r_before"], rec["burns"][1]["v_before"])}
    new = gmat_step(g.rules, state, rec, force_model="zonal")
    assert np.linalg.norm(new["pursuer"][0] - rec["rp_after"]) < 0.010
    assert np.linalg.norm(new["evader"][0] - rec["re_after"]) < 0.010
