"""遊戲核心（game/）與追擊所需 Δv（physics/intercept.py）的測試。"""
import math

import numpy as np
import pytest

from game.core import Game
from game.obs import OBS_DIM, build_obs
from game.rules import Rules, RuleRanges
from game.scenarios import FAMILIES, sample_scenario
from physics import EARTH_MU, get_r0_v0, orbital_period, propagate
from physics.frames import rsw_basis
from physics.intercept import intercept_solution


def _game(rules=Rules(), p=None, e=None):
    p = p or {"sma": 7000.0, "ecc": 0.0, "inc": 10.0, "raan": 0.0, "aop": 0.0, "ta": 0.0}
    e = e or {"sma": 7050.0, "ecc": 0.001, "inc": 10.2, "raan": 0.0, "aop": 0.0, "ta": 5.0}
    return Game.from_elements(rules, p, e)


# ------------------------------------------------------------------ 規則與推進
def test_dv_is_clipped_to_cap_and_fuel():
    g = _game(Rules(max_dv_pursuer_mps=100.0, fuel_pursuer_mps=150.0))
    rec = g.play_turn(np.array([1e6, 1e6, 1e6]))
    assert abs(rec["dv_mps"] - 100.0) < 1e-9
    g.play_turn(np.zeros(3))                     # evader
    rec = g.play_turn(np.array([0.0, 1e6, 0.0]))
    assert abs(rec["dv_mps"] - 50.0) < 1e-9      # 只剩 50
    assert g.fuel_left("pursuer") == 0.0
    g.play_turn(np.zeros(3))
    assert g.play_turn(np.array([1e6, 0, 0]))["dv_mps"] == 0.0


def test_alternation_and_first_mover():
    g = _game(Rules(first_mover="evader"))
    assert g.mover == "evader"
    g.play_turn(np.zeros(3))
    assert g.mover == "pursuer"
    with pytest.raises(ValueError):
        Rules(first_mover="nobody")


def test_full_coast_game_times_out_exactly():
    R = Rules(window_sec=500.0, t_max_sec=4321.0)
    g = _game(R)
    while not g.done:
        g.play_turn(np.zeros(3))
    assert g.outcome == "timeout" and g.winner == "evader"
    assert abs(g.t - 4321.0) < 1e-6
    assert g.turn == math.ceil(4321.0 / 500.0)


def test_initial_capture():
    p = {"sma": 7000.0, "ecc": 0.0, "inc": 0.0, "raan": 0.0, "aop": 0.0, "ta": 0.0}
    e = dict(p, ta=0.02)                          # ~2.4 km
    g = _game(Rules(), p, e)
    assert g.outcome == "capture" and g.winner == "pursuer"


def test_retro_burn_crashes_pursuer():
    p = {"sma": 6378.137 + 300.0, "ecc": 0.0, "inc": 0.0, "raan": 0.0, "aop": 0.0, "ta": 0.0}
    g = _game(Rules(window_sec=3000.0), p)
    dv_rsw = np.array([0.0, -1500.0, 0.0])        # 沿軌道反向全推
    g.play_turn(rsw_basis(g.r("pursuer"), g.v("pursuer")).T @ dv_rsw)
    assert g.outcome == "crash_pursuer" and g.winner == "evader"
    assert g.t < 3000.0


def _flyby_game(mode):
    """兩船在窗口中間（~150 s）以 1 km/s 穿過彼此，窗口末已分開很遠。"""
    rp, vp = get_r0_v0(7000.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    re, ve = rp + np.array([0.0, 0.0, 150.0]), vp + np.array([0.0, 0.0, -1.0])
    return Game(Rules(window_sec=300.0, capture_mode=mode), rp, vp, re, ve)


def test_capture_mode_continuous_vs_endpoint():
    g = _flyby_game("continuous")
    g.play_turn(np.zeros(3))
    assert g.outcome == "capture"
    g = _flyby_game("endpoint")
    g.play_turn(np.zeros(3))
    assert g.outcome is None and g.min_dist < 5.0      # 中途有進球，但 endpoint 規則不算
    with pytest.raises(ValueError):
        Rules(capture_mode="sometimes")


def test_lambert_pursuer_endpoint_mode_captures_passive_target():
    from agents import make_agent
    R = Rules(capture_mode="endpoint")
    p = {"sma": 6978.0, "ecc": 0.0, "inc": 51.6, "raan": 10.0, "aop": 0.0, "ta": 0.0}
    e = {"sma": 7010.0, "ecc": 0.001, "inc": 51.8, "raan": 10.3, "aop": 0.0, "ta": 4.0}
    g = Game.from_elements(R, p, e)
    P, E = make_agent("lambert_pursuer"), make_agent("coast")
    while not g.done:
        g.play_turn((P if g.mover == "pursuer" else E).act(g, g.mover))
    assert g.outcome == "capture", g.summary()


def test_clone_is_independent():
    g = _game()
    h = g.clone()
    h.play_turn(np.array([0.0, 50.0, 0.0]))
    assert g.turn == 0 and g.used["pursuer"] == 0.0 and g.t == 0.0
    assert not np.allclose(g.v("pursuer"), h.v("pursuer"))


def test_rule_sampling_and_scenarios_valid():
    rng = np.random.default_rng(0)
    for _ in range(50):
        R = RuleRanges().sample(rng)
        assert R.max_dv_evader_mps <= R.max_dv_pursuer_mps + 1e-9
        assert R.fuel_pursuer_mps >= 2.0 * R.max_dv_pursuer_mps - 1e-9
    for fam in FAMILIES:
        for _ in range(5):
            sc = sample_scenario(rng, fam)
            Game.from_elements(Rules(), sc.orbit_pursuer, sc.orbit_evader)
    with pytest.raises(KeyError):
        Rules.from_dict({"window": 3})
    assert Rules.from_dict({"_comment": "註解欄位忽略", "window_sec": 200.0}).window_sec == 200.0


# ------------------------------------------------------------------ 觀測
def test_obs_shape_finite_and_rotation_invariant():
    g = _game()
    o1 = build_obs(g, "pursuer")
    assert o1.shape == (OBS_DIM,) and np.all(np.isfinite(o1))
    # 把整個問題繞地球 z 軸（J2 對稱軸）轉 40°：觀測應不變
    th = math.radians(40.0)
    Rz = np.array([[math.cos(th), -math.sin(th), 0], [math.sin(th), math.cos(th), 0], [0, 0, 1]])
    g2 = Game(Rules(), Rz @ g.r("pursuer"), Rz @ g.v("pursuer"), Rz @ g.r("evader"), Rz @ g.v("evader"))
    o2 = build_obs(g2, "pursuer")
    assert np.allclose(o1, o2, atol=2e-4), np.abs(o1 - o2).max()
    oe = build_obs(g, "evader")
    assert oe[21] == -1.0 and o1[21] == 1.0


# ------------------------------------------------------------------ 追擊所需 Δv
def test_intercept_solution_hits_target_point_mass():
    rp, vp = get_r0_v0(7000.0, 0.0, 20.0, 0.0, 0.0, 0.0)
    re, ve = get_r0_v0(7100.0, 0.002, 21.0, 1.0, 0.0, 10.0)
    T = orbital_period(7000.0)
    sol = intercept_solution(EARTH_MU, 0, rp, vp, re, ve, 2 * T)
    assert math.isfinite(sol["dv_mps"]) and sol["dv_mps"] < 1500.0
    rf, _ = propagate(EARTH_MU, rp, vp + sol["dv_vec_mps"] / 1000.0, sol["tof"], 0)
    ref, _ = propagate(EARTH_MU, re, ve, sol["tof"], 0)
    assert np.linalg.norm(rf - ref) < 0.01


def test_intercept_solution_j2_shooting():
    rp, vp = get_r0_v0(7000.0, 0.0, 50.0, 0.0, 0.0, 0.0)
    re, ve = get_r0_v0(7080.0, 0.001, 50.5, 0.5, 0.0, 20.0)
    T = orbital_period(7000.0)
    sol = intercept_solution(EARTH_MU, 2, rp, vp, re, ve, 3 * T)
    assert sol["miss_km"] < 0.01
    rf, _ = propagate(EARTH_MU, rp, vp + sol["dv_vec_mps"] / 1000.0, sol["tof"], 2)
    ref, _ = propagate(EARTH_MU, re, ve, sol["tof"], 2)
    assert np.linalg.norm(rf - ref) < 0.01


def test_intercept_no_horizon():
    rp, vp = get_r0_v0(7000.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    re, ve = get_r0_v0(7000.0, 0.0, 0.0, 0.0, 0.0, 30.0)
    sol = intercept_solution(EARTH_MU, 2, rp, vp, re, ve, 30.0)
    assert sol["dv_mps"] == math.inf
