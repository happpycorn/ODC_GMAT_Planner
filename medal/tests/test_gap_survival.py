"""多發規則的「間隔存活」放寬（agents/analytic.py：next_burn_gap、gap_burn_survives、LambertPursuer.gap_survival）。"""
import numpy as np
import pytest

import agents.analytic as A
from agents import make_agent
from agents.analytic import LambertPursuer, gap_burn_survives, next_burn_gap, orbit_survives
from game.core import Game, take_turn
from game.rules import Rules
from physics.propagator import propagate

P0 = {"sma": 7000.0, "ecc": 0.0, "inc": 10.0, "raan": 0.0, "aop": 0.0, "ta": 0.0}
E0 = {"sma": 7050.0, "ecc": 0.001, "inc": 10.2, "raan": 0.0, "aop": 0.0, "ta": 5.0}


def _game(orbit_p=P0, **kw):
    return Game.from_elements(Rules(**kw), orbit_p, E0)


def _retro(g, mag):
    v = g.v("pursuer")
    return -v / np.linalg.norm(v) * mag


def test_next_burn_gap_follows_plan_turn_schedule():
    assert next_burn_gap(_game(), "pursuer") is None                         # 單發規則
    g = _game(burns_per_turn=2)
    assert next_burn_gap(g, "pursuer") == 100.0
    assert next_burn_gap(g, "evader") is None                                # 不是輪到的一方
    g.sub_burn(np.array([0.0, 5.0, 0.0]), 100.0)
    assert next_burn_gap(g, "pursuer") is None                               # 兩發用完
    g = _game(burns_per_turn=2)
    g.sub_burn(np.zeros(3), 100.0)                                           # 第一問推零也用掉一問
    assert next_burn_gap(g, "pursuer") is None
    g = _game(burns_per_turn=3)
    g.sub_burn(np.zeros(3), 100.0)
    assert next_burn_gap(g, "pursuer") == 100.0                              # 3 發：200 s 還有一問
    g.sub_burn(np.zeros(3), 100.0)
    assert next_burn_gap(g, "pursuer") is None                               # 200 s 是最後一問
    assert next_burn_gap(_game(burns_per_turn=2, window_sec=100.0), "pursuer") is None   # 下一問在窗口外


def test_gap_burn_survives_allows_rescuable_intermediate_orbit():
    """逆推 1500 m/s：中間軌道近地點在地表下（嚴格檢查不過），但 100 s 內還很高、之後順推救得回來。"""
    g = _game(burns_per_turn=2)
    dv = _retro(g, 1500.0)
    assert not orbit_survives(g, "pursuer", dv)
    assert gap_burn_survives(g, "pursuer", dv, 100.0)
    # 燃料只夠這一發 → 救不回來
    g2 = _game(burns_per_turn=2, fuel_pursuer_mps=1500.0)
    assert not gap_burn_survives(g2, "pursuer", dv, 100.0)


def test_gap_burn_survives_rejects_crash_inside_gap():
    """低軌道朝地心推 1500 m/s：100 s 內就掉到撞地高度以下 → 不放寬。"""
    low = {**P0, "sma": 6578.0}
    g = _game(orbit_p=low, burns_per_turn=2)
    r = g.r("pursuer")
    dv = -r / np.linalg.norm(r) * 1500.0
    assert not gap_burn_survives(g, "pursuer", dv, 100.0)


def test_level2_requires_completing_the_same_intercept():
    """逆推 600 m/s（中間軌道近地點在地表下）：100 s 後一發就能回到原軌道 1500 s 後的位置 → 補得完；
    目標時刻在第二發之前 → 補不完。"""
    g = _game(burns_per_turn=2)
    dv = _retro(g, 600.0)
    assert not orbit_survives(g, "pursuer", dv)
    r_far, _ = propagate(g.mu, g.r("pursuer"), g.v("pursuer"), 1500.0, 2)
    assert gap_burn_survives(g, "pursuer", dv, 100.0, target=(r_far, 1500.0))
    assert not gap_burn_survives(g, "pursuer", dv, 100.0, target=(r_far, 150.0))


def test_switch_env_and_default(monkeypatch):
    monkeypatch.setenv(A.GAP_SURVIVAL_ENV, "1")
    assert LambertPursuer().gap_survival == 1
    assert make_agent("lambert_pursuer_fast").gap_survival == 1
    monkeypatch.setenv(A.GAP_SURVIVAL_ENV, "2")
    assert LambertPursuer().gap_survival == 2
    monkeypatch.setenv(A.GAP_SURVIVAL_ENV, "0")
    assert LambertPursuer().gap_survival == 0
    monkeypatch.delenv(A.GAP_SURVIVAL_ENV)
    assert LambertPursuer().gap_survival == A.GAP_SURVIVAL_DEFAULT
    assert LambertPursuer(gap_survival=True).gap_survival == 1 and LambertPursuer(gap_survival=False).gap_survival == 0


@pytest.mark.parametrize("level", [1, 2])
def test_relaxed_pursuer_ends_every_window_on_a_safe_orbit(level):
    """大推力兩發（1500/3000）：放寬後窗口中途可以在不安全的中間軌道上，但每個窗口結束時追者軌道都要過嚴格檢查、不撞地。"""
    R = Rules(burns_per_turn=2, t_max_sec=6000.0)
    far = {**E0, "sma": 7400.0, "ta": 40.0}
    g = Game.from_elements(R, P0, far)
    P, E = LambertPursuer(gap_survival=level), make_agent("dv_evader_fast")
    while not g.done:
        side = g.mover
        take_turn(g, P if side == "pursuer" else E)
        if side == "pursuer" and not g.done:
            assert orbit_survives(g, "pursuer", np.zeros(3))
    assert g.outcome != "crash_pursuer"


@pytest.mark.parametrize("rules", [Rules(), Rules(max_dv_pursuer_mps=250.0, max_dv_evader_mps=250.0)])
def test_single_burn_rules_identical_regardless_of_switch(rules):
    g = Game.from_elements(rules, P0, E0)
    on, off = LambertPursuer(gap_survival=True), LambertPursuer(gap_survival=False)
    E = make_agent("dv_evader_fast")
    for _ in range(6):
        if g.done:
            break
        if g.mover == "pursuer":
            a, b = on.act(g, "pursuer"), off.act(g, "pursuer")
            assert np.array_equal(a, b)
            g.play_turn(a)
        else:
            take_turn(g, E)
