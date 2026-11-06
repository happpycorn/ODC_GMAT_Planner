"""GMAT 重播一致性（HAP-56）。沒裝 GmatConsole 的機器自動略過。"""
import os

import numpy as np
import pytest

from tools.gmat_verify import GMAT_CONSOLE, game_to_script, verify_game

pytestmark = pytest.mark.skipif(not os.path.exists(GMAT_CONSOLE), reason="GmatConsole 不在這台機器上")


def _short_game(gravity_degree):
    from agents import make_agent
    from game.core import Game
    from game.rules import Rules
    R = Rules(window_sec=400.0, t_max_sec=4000.0, max_dv_pursuer_mps=300.0, max_dv_evader_mps=150.0,
              fuel_pursuer_mps=1200.0, fuel_evader_mps=600.0, gravity_degree=gravity_degree)
    p = {"sma": 6978.0, "ecc": 0.001, "inc": 51.6, "raan": 10.0, "aop": 30.0, "ta": 0.0}
    e = {"sma": 7030.0, "ecc": 0.002, "inc": 52.0, "raan": 10.5, "aop": 40.0, "ta": 350.0}
    g = Game.from_elements(R, p, e)
    P, E = make_agent("lambert_pursuer"), make_agent({"name": "random", "seed": 3, "p_burn": 1.0})
    while not g.done:
        g.play_turn((P if g.mover == "pursuer" else E).act(g, g.mover))
    return g


def test_script_is_ascii():
    g = _short_game(2)
    game_to_script(g, "/tmp/x.txt").encode("ascii")


@pytest.mark.parametrize("deg", [0, 2, 4])
def test_gmat_replay_matches_physics(deg):
    g = _short_game(deg)
    out = verify_game(g)
    assert out["max_dt_sec"] < 1e-3
    # 4000 s 內多次脈衝：兩邊位置差應在 10 m 以內（捕獲半徑的 1/500）
    assert out["max_dpos_km"] < 0.01, out["per_turn"]


# ------------------------------------------------------------------ 全攝動（排位賽官方模型）彩排用
def test_ranking_full_script_ascii_and_model():
    g = _short_game(2)
    s = game_to_script(g, "/tmp/x.txt", "ranking_full", dense_path="/tmp/d.txt")
    s.encode("ascii")
    assert "EGM96.cof" in s and "NRLMSISE00" in s and "PointMasses = {Sun, Luna}" in s
    assert "ShipP.Cd = 2.2;" in s and "RF.Add = {ShipP.ElapsedSecs, " in s
    z = game_to_script(g, "/tmp/x.txt")
    assert "JGM2.cof" in z and "EGM96" not in z and "RF.Add" not in z and "Epoch = '21545';" in z


def test_gmat_step_matches_full_replay_under_full_perturbation():
    """逐回合推進（每回合從上回合的 GMAT 狀態重起、曆元跟著走）要跟整局重播一致。"""
    from tools.gmat_verify import gmat_step, gmat_truth, run_gmat
    g = _short_game(2)
    rows = run_gmat(game_to_script(g, "__REPORT__", "ranking_full"))
    state = {s: (g.initial[s][0].copy(), g.initial[s][1].copy()) for s in ("pursuer", "evader")}
    for rec in g.history:
        state = gmat_step(g.rules, state, rec, "ranking_full")
    last = rows[-1]
    assert np.linalg.norm(state["pursuer"][0] - last[1:4]) < 1e-3       # < 1 m
    assert np.linalg.norm(state["evader"][0] - last[7:10]) < 1e-3
    truth = gmat_truth(g, "ranking_full")
    assert truth["d_min_km"] <= min(r["window_min_dist_km"] for r in g.history) + 1.0


def test_gmat_truth_sees_past_engine_capture_instant():
    """引擎在進捕獲球的瞬間結束比賽；GMAT 判定要把窗口滑完，不能只看到剛好 5 km。"""
    from game.core import Game
    from game.rules import Rules
    from tools.gmat_verify import gmat_truth
    rp, vp = np.array([7000.0, 0.0, 0.0]), np.array([0.0, 7.546, 0.0])
    re, ve = rp + np.array([0.0, 8.0, 0.0]), vp - np.array([0.0, 0.03, 0.0])
    g = Game(Rules(capture_radius_km=5.0, t_max_sec=3000.0), rp, vp, re, ve)
    g.play_turn(np.zeros(3))
    assert g.outcome == "capture" and g.history[-1]["coast_sec"] < 300.0
    truth = gmat_truth(g, "ranking_full")
    assert truth["t_capture_sec"] is not None and truth["d_min_km"] < 4.0
