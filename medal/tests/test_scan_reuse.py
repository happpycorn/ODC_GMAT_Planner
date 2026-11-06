"""完全相同計算的重用：呼叫次數、逐位元輸出、狀態／參數隔離與決策生命週期。"""
from collections import Counter

import numpy as np
import pytest

import copilot
import agents.analytic as analytic
from agents.analytic import LambertPursuer
from agents.rollout import RolloutPlanner
from agents.scan_reuse import decision_scope, reuse_call, scan_reuse_enabled
from game.core import Game
from game.rules import Rules
from tools.bench_advise import exact_result


P = dict(sma=6978.0, ecc=0.0, inc=51.6, raan=10.0, aop=0.0, ta=0.0)
E = dict(sma=7010.0, ecc=0.001, inc=51.8, raan=10.3, aop=0.0, ta=4.0)
WEIGHTS = (0.0, 10.0, 60.0, 300.0)


def game(**kwargs):
    return Game.from_elements(Rules(t_max_sec=3600.0, **kwargs), P, E)


def count_physics(monkeypatch):
    counts = Counter()
    for name in ("intercept_scan", "closest_approach", "propagate"):
        original = getattr(analytic, name)

        def counted(*args, _name=name, _original=original):
            counts[_name] += 1
            return _original(*args)

        monkeypatch.setattr(analytic, name, counted)
    return counts


def test_four_weights_share_one_scan_and_coast(monkeypatch):
    monkeypatch.delenv("ODC_SCAN_REUSE", raising=False)
    assert scan_reuse_enabled()
    counts = count_physics(monkeypatch)
    g = game()
    planner = RolloutPlanner("pursuer", workers=1)
    on = planner._candidates(g)
    assert counts["intercept_scan"] == counts["closest_approach"] == 1
    # 新的一次決策即使狀態相同也不可沿用上一份。
    planner._candidates(g)
    assert counts["intercept_scan"] == counts["closest_approach"] == 2
    counts.clear()
    monkeypatch.setenv("ODC_SCAN_REUSE", "0")
    off = planner._candidates(g)
    assert counts["intercept_scan"] == counts["closest_approach"] == 4
    assert len(on) == len(off)
    assert all(np.array_equal(a, b) and a.tobytes() == b.tobytes() for a, b in zip(on, off))


@pytest.mark.parametrize("capture_mode,gravity_degree,burns", [
    ("continuous", 2, 1), ("endpoint", 2, 1), ("continuous", 0, 1), ("continuous", 2, 2)])
def test_act_on_off_bit_identical(monkeypatch, capture_mode, gravity_degree, burns):
    g = game(capture_mode=capture_mode, gravity_degree=gravity_degree, burns_per_turn=burns)
    monkeypatch.setenv("ODC_SCAN_REUSE", "0")
    off = [LambertPursuer(time_weight_mps=w).act(g, "pursuer") for w in WEIGHTS]
    monkeypatch.setenv("ODC_SCAN_REUSE", "1")
    with decision_scope(g):
        on = [LambertPursuer(time_weight_mps=w).act(g, "pursuer") for w in WEIGHTS]
    assert all(np.array_equal(a, b) and a.tobytes() == b.tobytes() for a, b in zip(on, off))


@pytest.mark.parametrize("change", ["time", "fuel", "position", "velocity", "mu", "rules", "window"])
def test_changed_state_is_never_reused(monkeypatch, change):
    monkeypatch.setenv("ODC_SCAN_REUSE", "1")
    counts = count_physics(monkeypatch)
    g = game()
    brain = LambertPursuer()
    with decision_scope(g):
        brain.act(g, "pursuer")
        brain.act(g, "pursuer")
        assert counts["intercept_scan"] == 1
        if change == "time":
            # 保持 horizon 不變，仍必須因絕對時間改變而失效。
            g.t += 1.0
            g.t_max += 1.0
        elif change == "fuel":
            g.used["evader"] = np.nextafter(0.0, 1.0)
        elif change == "position":
            g.r("evader")[0] = np.nextafter(g.r("evader")[0], np.inf)
        elif change == "velocity":
            g.v("evader")[0] = np.nextafter(g.v("evader")[0], np.inf)
        elif change == "mu":
            g.mu = np.nextafter(g.mu, np.inf)
        elif change == "rules":
            g.rules = g.rules.with_(fuel_evader_mps=g.rules.fuel_evader_mps + 1.0)
        else:
            g._win_elapsed += 1.0
        brain.act(g, "pursuer")
        assert counts["intercept_scan"] == 2


def test_all_scan_parameters_and_returned_arrays_are_isolated(monkeypatch):
    monkeypatch.setenv("ODC_SCAN_REUSE", "1")
    g = game()
    args = [g.mu, 2, g.r("pursuer"), g.v("pursuer"), g.r("evader"), g.v("evader"),
            60.0, 3600.0, 16, 2, g.crash_radius + 50.0]
    calls = 0
    source = np.arange(3.0)

    def scan(*params):
        nonlocal calls
        calls += 1
        return (source, source + 1.0)

    with decision_scope(g) as memo:
        result = reuse_call(scan, *args)
        result[0][:] = -100.0
        again = reuse_call(scan, *args)
        assert calls == 1
        assert np.array_equal(again[0], np.arange(3.0))
        again[1][:] = -200.0
        assert np.array_equal(reuse_call(scan, *args)[1], np.arange(3.0) + 1.0)
        for i, arg in enumerate(args):
            changed = list(args)
            if isinstance(arg, np.ndarray):
                changed[i] = arg.copy()
                changed[i][0] = np.nextafter(arg[0], np.inf)
            else:
                changed[i] = arg + 1
            reuse_call(scan, *changed)
        assert calls == 1 + len(args)
    assert not memo.values
    reuse_call(scan, *args)
    assert calls == 2 + len(args)


def test_advise_weights_share_root_scan_and_drop_it_afterwards(monkeypatch):
    monkeypatch.setenv("ODC_SCAN_REUSE", "1")
    counts = count_physics(monkeypatch)
    st = copilot.state_from_game(game(), "pursuer")
    brains = [{"name": "lambert_pursuer", "time_weight_mps": w} for w in WEIGHTS]
    copilot.advise(st, brains, ["coast"], rollouts=False, with_situation=False)
    assert counts["intercept_scan"] == counts["closest_approach"] == 1
    copilot.advise(st, brains, ["coast"], rollouts=False, with_situation=False)
    assert counts["intercept_scan"] == counts["closest_approach"] == 2


def test_identical_target_propagation_once_inside_act(monkeypatch):
    g = Game.from_elements(Rules(t_max_sec=3600.0, capture_mode="endpoint"), P,
                           {**E, "sma": 6990.0, "inc": 51.7, "raan": 10.1, "ta": 1.0})
    original = analytic.propagate
    calls = []

    def counted(mu, r, v, dt, gd):
        if np.array_equal(r, g.r("evader")) and np.array_equal(v, g.v("evader")) and dt == g.next_window():
            calls.append(float(dt))
        return original(mu, r, v, dt, gd)

    monkeypatch.setattr(analytic, "propagate", counted)
    monkeypatch.setenv("ODC_SCAN_REUSE", "0")
    off = LambertPursuer(time_weight_mps=3000.0).act(g, "pursuer")
    # 窗口末滑行檢查、J2 目標、最後的命中驗證，都是同一個 300 秒目標。
    assert len(calls) == 3
    calls.clear()
    monkeypatch.setenv("ODC_SCAN_REUSE", "1")
    on = LambertPursuer(time_weight_mps=3000.0).act(g, "pursuer")
    assert len(calls) == 1
    assert np.array_equal(on, off) and on.tobytes() == off.tobytes()


@pytest.mark.parametrize("role,burns", [("pursuer", 1), ("evader", 1), ("pursuer", 2)])
def test_pruned_star_scores_and_terminal_summaries_exact(monkeypatch, role, burns):
    g = game(first_mover=role, burns_per_turn=burns)
    st = copilot.state_from_game(g, role)
    brains = ["rollout_pursuer", {"name": "lambert_pursuer", "time_weight_mps": 60.0}] if role == "pursuer" else ["lazy_evader", "rollout_evader"]
    opponents = ["coast", "dv_evader_fast"] if role == "pursuer" else ["coast", "lambert_pursuer_fast"]
    monkeypatch.setenv("ODC_SCAN_REUSE", "0")
    off = copilot.advise(st, brains, opponents, prune=True, workers=1)
    monkeypatch.setenv("ODC_SCAN_REUSE", "1")
    on = copilot.advise(st, brains, opponents, prune=True, workers=1)
    assert exact_result(on) == exact_result(off)
