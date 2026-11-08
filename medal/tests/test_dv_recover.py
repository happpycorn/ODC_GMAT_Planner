"""用實際回合傳播驗證 Δv 反推、負時間 Kepler 與 Lambert 交叉核對。"""
import math

import numpy as np
import pytest

import game.dv_recover as recovery
from agents.final_common import kepler
from game.core import Game
from game.dv_recover import elapsed_sec, recover_dv
from game.scenarios import FINAL_RULES_BASE
from physics import EARTH_MU, get_r0_v0


@pytest.mark.parametrize("magnitude", [0.0, 75.0, 200.0, 350.0])
def test_random_leo_rounds_recover_executed_burn(magnitude):
    """隨機順、逆行 LEO；超過 200 m/s 的提交由 Game 真正等比例縮放。"""
    rng = np.random.default_rng(810)
    rules = FINAL_RULES_BASE.with_(window_sec=900.0, max_dv_pursuer_mps=200.0,
                                  max_dv_evader_mps=200.0)
    re, ve = get_r0_v0(sma=14000.0, ecc=0.0, inc=20.0, raan=0.0, aop=0.0, ta=180.0)
    for _ in range(24):
        r0, v0 = get_r0_v0(sma=rng.uniform(7000.0, 8200.0), ecc=rng.uniform(0.0, 0.02),
                           inc=rng.uniform(1.0, 179.0), raan=rng.uniform(0.0, 360.0),
                           aop=rng.uniform(0.0, 360.0), ta=rng.uniform(0.0, 360.0))
        direction = rng.normal(size=3)
        submitted = direction * (magnitude / np.linalg.norm(direction))
        game = Game(rules, r0, v0, re, ve)
        record = game.play_round(submitted, np.zeros(3))
        assert record["coast_sec"] == pytest.approx(900.0)
        executed = record["burns"][0]["dv_eci_mps"]
        assert np.linalg.norm(executed) == pytest.approx(min(magnitude, 200.0), abs=1e-10)
        if magnitude > 200.0:
            assert record["burns"][0]["scaled"]
        result = recover_dv(r0, v0, game.r("pursuer"), game.v("pursuer"), 900.0)
        assert np.linalg.norm(np.asarray(result["dv_mps"]) - executed) < 1e-6
        assert result["position_residual_km"] < 1e-6
        assert result["lambert_dv_mps"] is not None
        assert result["lambert_diff_mps"] < 1e-3


@pytest.mark.parametrize("inc", [25.0, 155.0])
def test_negative_time_and_lambert_both_directions(inc):
    """負時間直接回到原狀態，Lambert 依回推後速度選中正確轉移方向。"""
    r0, v0 = get_r0_v0(sma=7400.0, ecc=0.015, inc=inc, raan=30.0, aop=20.0, ta=100.0)
    dv = np.array([51.0, -72.0, 80.0])
    r1, v1 = kepler(r0, v0 + dv / 1000.0, 900.0)
    rb, vb = kepler(r1, v1, -900.0)
    assert np.linalg.norm(rb - r0) < 1e-6
    assert np.linalg.norm((vb - v0) * 1000.0 - dv) < 1e-6
    result = recover_dv(r0, v0, r1, v1, 900.0)
    assert result["lambert_diff_mps"] < 1e-3


def test_lambert_skips_past_half_period(monkeypatch):
    r0, v0 = get_r0_v0(sma=7200.0, ecc=0.01, inc=30.0, raan=0.0, aop=0.0, ta=30.0)
    dt = math.pi * math.sqrt(7200.0 ** 3 / EARTH_MU) + 10.0
    r1, v1 = kepler(r0, v0, dt)

    def forbidden(*args):
        pytest.fail("超過半週期時不該呼叫零圈 Lambert")

    monkeypatch.setattr(recovery, "izzo", forbidden)
    result = recover_dv(r0, v0, r1, v1, dt)
    assert np.linalg.norm(result["dv_mps"]) < 1e-6
    assert result["lambert_dv_mps"] is None
    assert result["lambert_diff_mps"] is None


@pytest.mark.parametrize("error", [None, ValueError, RuntimeError, Exception])
def test_lambert_failure_preserves_primary_recovery(monkeypatch, error):
    r0, v0 = get_r0_v0(sma=7200.0, ecc=0.01, inc=30.0, raan=0.0, aop=0.0, ta=30.0)
    r1, v1 = kepler(r0, v0, 900.0)
    tried = []

    def failed(mu, r0, r1, dt, revolutions, prograde, *args):
        tried.append((revolutions, prograde))
        if error is not None:
            raise error("刻意模擬 Lambert 無解")
        return False, np.zeros(3), np.zeros(3)

    monkeypatch.setattr(recovery, "izzo", failed)
    result = recover_dv(r0, v0, r1, v1, 900.0)
    assert tried == [(0, True), (0, False)]
    assert np.linalg.norm(result["dv_mps"]) < 1e-6
    assert result["lambert_dv_mps"] is None
    assert result["lambert_diff_mps"] is None


@pytest.mark.parametrize("dt", [0.0, -1.0, float("nan"), float("inf")])
def test_recovery_rejects_invalid_elapsed_time(dt):
    with pytest.raises(ValueError, match="時間 dt 必須是大於 0"):
        recover_dv([7000, 0, 0], [0, 7.5, 0], [7000, 0, 0], [0, 7.5, 0], dt)


@pytest.mark.parametrize("start,end,expected", [
    ({"epoch": "2026-11-09T07:00:00Z", "t_sec": 0},
     {"epoch": "2026-11-09T15:15:00+08:00", "t_sec": 120}, (900.0, "epoch")),
    ({"epoch": None, "t_sec": 0}, {"epoch": "2026-11-09T07:15:00Z", "t_sec": 120},
     (120.0, "t_sec")),
    ({"t_sec": 12}, {"t_sec": 912}, (900.0, "t_sec")),
    ({"epoch": "2026-11-09T07:00:00Z"}, {"epoch": None}, (900.0, "T_round")),
    ({}, {}, (900.0, "T_round")),
])
def test_elapsed_time_priority(start, end, expected):
    assert elapsed_sec(start, end, 900.0) == expected
