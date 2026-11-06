"""金／銅牌賽安全空域對抗題（game.scenarios.sample_adversarial_scenario）、台灣入軌題庫、評測接線。"""
import json

import numpy as np
import pytest

from game.core import Game, sma_official
from game.rules import Rules
from game.scenarios import (ADVERSARIAL_KINDS, FINAL_MIN_PERIGEE_ALT_KM, TAIWAN_BANK_PATH, full_burn_dsma_km,
                            sample_adversarial_scenario, sample_final_rules, sample_final_scenario)
from physics import RE_VAL, get_r0_v0
from physics.frames import rv2coe

N = 30


def _draw(kind, i):
    rng = np.random.default_rng([31, i])
    return sample_adversarial_scenario(rng, sample_final_rules(rng), kind)


@pytest.mark.parametrize("kind", ADVERSARIAL_KINDS)
def test_adversarial_conditions(kind):
    for i in range(N):
        R, sc = _draw(kind, i)
        m = sc.meta
        assert sc.family == f"final_adv_{kind}" and m["kind"] == kind
        rp, vp = get_r0_v0(**sc.orbit_pursuer)
        re, ve = get_r0_v0(**sc.orbit_evader)
        a_p, a_e = sma_official(rp, vp), sma_official(re, ve)
        da = full_burn_dsma_km(a_e, R.max_dv_evader_mps)
        lo, hi = R.safe_sma_km
        center, width = (lo + hi) / 2, hi - lo
        dist = float(np.linalg.norm(rp - re))
        assert lo >= RE_VAL + 300.0 - 1e-9
        for o in (sc.orbit_pursuer, sc.orbit_evader):
            assert o["sma"] * (1 - o["ecc"]) - RE_VAL >= FINAL_MIN_PERIGEE_ALT_KM - 1e-9
        assert m["a_p"] == pytest.approx(a_p) and m["a_e"] == pytest.approx(a_e) and m["da"] == pytest.approx(da)
        assert m["dist0_km"] == pytest.approx(dist)
        zone_mode = m["sub"] if kind == "taiwan" else kind
        if kind == "cover":
            assert lo <= a_p <= hi and not lo <= a_e <= hi
            assert 0.3 - 1e-9 <= width / da <= 1.0 + 1e-9
        elif kind == "narrow" or zone_mode == "narrow":
            assert width / da <= 0.1 + 1e-9
            if m["sub"] == "w002":
                assert width / da == pytest.approx(0.02)
            if kind == "narrow":
                assert 1.0 - 1e-9 <= abs(center - a_e) / da <= 4.0 + 1e-9 and not lo <= a_e <= hi
        if kind == "cross":
            assert (a_e - a_p) * (center - a_p) < 0.0 and m["cross"]
        if kind == "far":
            assert 4.5 - 1e-9 <= abs(center - a_e) / da <= 5.5 + 1e-9
            assert np.sign(center - a_e) == np.sign(a_p - a_e)
        if kind == "close":
            assert lo <= a_p <= hi
            if m["sub"] == "close_km":
                assert 20.0 <= dist <= 100.0
            else:
                assert 2 * R.capture_radius_km <= dist < 0.2 * R.max_dv_evader_mps / 1000.0 * R.window_sec
        if kind == "taiwan":
            assert 0.0 <= m["epoch_gap_h"] <= 24.0
        else:
            assert 20.0 <= dist <= 1500.0
        g = Game.from_elements(R, sc.orbit_pursuer, sc.orbit_evader)
        assert not g.done and g.t_max == R.rounds * R.window_sec


def test_unknown_kind():
    with pytest.raises(ValueError):
        sample_adversarial_scenario(np.random.default_rng(0), sample_final_rules(np.random.default_rng(0)), "nope")


def test_final_scenario_unchanged():
    """既有 final 題目不受影響（數字取自加對抗題之前的 commit 45599ab）。"""
    base = Rules.from_dict(json.load(open("configs/rulesets/final_official.json")))
    R, sc = sample_final_scenario(np.random.default_rng([0, 0]), base)
    assert sc.meta is None and sc.family == "final"
    assert R.safe_sma_km == pytest.approx((7522.526175205364, 7664.814507885795), abs=1e-9)


def test_taiwan_bank_roundtrip():
    bank = json.load(open(TAIWAN_BANK_PATH))
    assert len(bank["pairs"]) >= 100
    for pair in bank["pairs"][:40]:
        assert 0.0 <= pair["epoch_gap_h"] <= 24.0
        prop = pair["propagated"]
        assert max(prop.values()) == pytest.approx(pair["epoch_gap_h"] * 3600.0, abs=1e-3)
        assert min(prop.values()) == 0.0
        for side in ("pursuer", "evader"):
            r, v = np.array(pair[side]["r_km"]), np.array(pair[side]["v_kms"])
            r2, v2 = get_r0_v0(**rv2coe(r, v))
            assert np.linalg.norm(r2 - r) < 1e-6 and np.linalg.norm(v2 - v) < 1e-9
            assert pair["gmat_input"][side]["CoordinateSystem"] == "EarthFixed"
            assert pair["gmat_input"][side]["DisplayStateType"] == "SphericalAZFPA"


def test_make_games_and_play_meta(tmp_path):
    from evaluation.tournament import make_games, play, run_tournament, Task
    games = make_games(2, "final_ranges", "final_adv_cross", seed=0)
    assert all(len(g) == 5 and g[4]["kind"] == "cross" for g in games)
    assert all(len(g) == 4 for g in make_games(2, "final_ranges", "final", seed=0))
    R, op, oe, fam, meta = games[0]
    out = play(Task("lambert_pursuer", "heuristic_evader", R, op, oe, fam, 0, 0, meta))
    assert out["scenario_meta"]["kind"] == "cross"
    json.dumps(out, default=float)

    from tools.final_breakdown import main as breakdown_main
    res = run_tournament(["lambert_pursuer"], ["safe_evader_fast", "heuristic_evader"],
                         make_games(2, "final_ranges", "final_adv_narrow", seed=1), workers=1, progress=False)
    path = tmp_path / "adv.jsonl"
    path.write_text("".join(json.dumps(r, default=float) + "\n" for r in res))
    md_path = tmp_path / "adv.md"
    breakdown_main([str(path), "--out", str(md_path)])
    md = md_path.read_text()
    assert "zone_width_da" in md or "區間寬度" in md
    assert "輸" in md
