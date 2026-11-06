"""agents/evader_lab.py 的測試（小規模、決定性）。"""
import math

import numpy as np

from agents import make_agent
from agents.evader_lab import LazyEvader, ReserveRolloutEvader, fuelwar_score, inwindow_need
from game.core import Game
from game.rules import Rules

RANKING = Rules(max_dv_pursuer_mps=250.0, max_dv_evader_mps=250.0, fuel_pursuer_mps=3000.0,
                fuel_evader_mps=3000.0, t_max_sec=3600.0)
NEAR_P = {"sma": 6978.0, "ecc": 0.0, "inc": 51.6, "raan": 10.0, "aop": 0.0, "ta": 0.0}
FAR_E = {"sma": 7010.0, "ecc": 0.001, "inc": 51.8, "raan": 10.3, "aop": 0.0, "ta": 4.0}      # ~500 km
CLOSE_E = {"sma": 6980.0, "ecc": 0.0, "inc": 51.6, "raan": 10.0, "aop": 0.0, "ta": 0.25}     # ~30 km


def _evader_turn(rules, p, e):
    g = Game.from_elements(rules, p, e)
    g.play_turn(np.zeros(3))              # 追者先手：不推，輪到躲者
    return g


def test_inwindow_need_close_vs_far():
    assert inwindow_need(_evader_turn(RANKING, NEAR_P, CLOSE_E)) < 250.0
    assert inwindow_need(_evader_turn(RANKING, NEAR_P, FAR_E)) > 1000.0


def test_lazy_evader_coasts_when_safe_and_dodges_when_threatened():
    lazy = LazyEvader()
    g_far = _evader_turn(RANKING, NEAR_P, FAR_E)
    assert not lazy.threatened(g_far)
    assert np.allclose(lazy.act(g_far, "evader"), 0.0)
    g_close = _evader_turn(RANKING, NEAR_P, CLOSE_E)
    assert lazy.threatened(g_close)
    dv = lazy.act(g_close, "evader")
    assert 0.0 < np.linalg.norm(dv) <= 250.0 + 1e-6


def _boundary_collision_game(t_hit=306.0):
    """躲者回合開始；雙方都滑行的話，在 t_hit 秒（追者窗口開始後幾秒）以 ~7 km/s 相撞（交叉軌道）。"""
    from physics.propagator import propagate
    g0 = Game.from_elements(RANKING, NEAR_P, FAR_E)
    re, ve = g0.r("evader"), g0.v("evader")
    r_hit, v_hit = propagate(g0.mu, re, ve, t_hit, 2)
    # 速度繞徑向轉 60°（Rodrigues）：同速率、不同軌道面 → 交叉軌道
    u = r_hit / np.linalg.norm(r_hit)
    th = np.radians(60.0)
    vp_hit = v_hit * np.cos(th) + np.cross(u, v_hit) * np.sin(th) + u * (u @ v_hit) * (1 - np.cos(th))
    rb, vb = propagate(g0.mu, r_hit, -vp_hit, t_hit, 2)        # 保守力場可逆：反向速度往前推 = 往回推
    return Game.from_snapshot(RANKING, rb, -vb, re, ve, t=0.0, t_max=3600.0, mover="evader")


def test_lazy_evader2_sees_boundary_collision():
    from agents.evader_lab import LazyEvader2
    g = _boundary_collision_game()
    assert g.distance() > 1000.0
    h = g.clone()
    h.play_turn(np.zeros(3))
    h.play_turn(np.zeros(3))
    assert h.outcome == "capture"                  # 都不推 → 追者窗口一開始就相撞
    assert not LazyEvader().threatened(g)          # 舊版的盲點
    lazy2 = LazyEvader2()
    assert lazy2.threatened(g)
    dv = lazy2.act(g, "evader")
    assert np.linalg.norm(dv) > 0.0
    h = g.clone()
    h.play_turn(dv)
    h.play_turn(np.zeros(3))
    assert h.outcome != "capture"


def test_strict_survives_catches_crash_before_perigee():
    """近地點在地底下、二體近地點時刻在比賽結束後 → orbit_survives 說安全，但還沒到近地點就撞地。"""
    from agents.analytic import orbit_survives
    from agents.base import rsw_to_eci_dv
    from agents.evader_lab import strict_survives
    sym = Rules(t_max_sec=1650.0)                      # 1500/3000
    e600 = {"sma": 6978.0, "ecc": 0.0, "inc": 51.6, "raan": 10.0, "aop": 0.0, "ta": 20.0}
    g = Game.from_elements(sym, NEAR_P, e600)
    g.play_turn(np.zeros(3))                           # 追者回合；輪到躲者，剩 1350 s
    dv = rsw_to_eci_dv(g, "evader", np.array([-1061.0, -1061.0, 0.0]))
    assert orbit_survives(g, "evader", dv, strict=False)   # 舊檢查（ODC_STRICT_SURVIVAL=0）的漏判
    assert not orbit_survives(g, "evader", dv)         # 預設開（E25）已修正
    assert not strict_survives(g, "evader", dv)
    assert strict_survives(g, "evader", np.zeros(3))
    h = g.clone()
    h.play_turn(dv)
    while not h.done:
        h.play_turn(np.zeros(3))
    assert h.outcome == "crash_evader"


def test_fuelwar_score_prefers_win_fuel_and_margin():
    g = Game.from_elements(RANKING, NEAR_P, FAR_E)
    win = g.clone()
    win.outcome = "timeout"
    win.min_dist = 50.0
    rich = win.clone()
    rich.used = {"pursuer": 2000.0, "evader": 0.0}
    poor = win.clone()
    poor.used = {"pursuer": 2000.0, "evader": 2000.0}
    lose = g.clone()
    lose.outcome = "capture"
    assert fuelwar_score(rich, "evader") > fuelwar_score(poor, "evader") > fuelwar_score(lose, "evader")
    near = rich.clone()
    near.min_dist = 6.0
    assert fuelwar_score(rich, "evader") > fuelwar_score(near, "evader")


def test_reserve_rollout_evader_legal_and_registered():
    a = make_agent("py:agents.evader_lab:ReserveRolloutEvader")
    assert isinstance(a, ReserveRolloutEvader)
    g = _evader_turn(RANKING.with_(t_max_sec=1800.0), NEAR_P, CLOSE_E)
    cands = a._candidates(g)
    assert np.allclose(cands[0], 0.0) and len(cands) >= 3
    dv = a.act(g, "evader")
    assert np.all(np.isfinite(dv)) and np.linalg.norm(dv) <= 250.0 + 1e-6
    # 整局推演到結束（短 T_max），燃料帳合法
    P = make_agent("lambert_pursuer_fast")
    while not g.done:
        g.play_turn((P if g.mover == "pursuer" else a).act(g, g.mover))
    assert g.used["evader"] <= 3000.0 + 1e-6 and math.isfinite(g.min_dist)
