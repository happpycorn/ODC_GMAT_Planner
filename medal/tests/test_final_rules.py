"""金／銅牌賽規則分布、逐局軌道紀錄與分桶報表。"""
import json
import math
import os
import subprocess
import sys

import numpy as np
import pytest

from evaluation.tournament import make_games, run_tournament
from game.rules import Rules
from game.scenarios import FINAL_RULE_RANGES, FINAL_RULES_BASE, full_burn_dsma_km, sample_final_rules
from tools.final_breakdown import breakdown_report, game_buckets


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FINAL_RULES = os.path.join(ROOT, "configs", "rulesets", "final_official.json")


def test_final_rules_base_matches_official_json():
    with open(FINAL_RULES, encoding="utf-8") as f:
        official = Rules.from_dict(json.load(f))
    assert FINAL_RULES_BASE == official


def test_sample_final_rules_ranges_are_log_uniform():
    rng = np.random.default_rng(20261101)
    samples = [sample_final_rules(rng) for _ in range(1000)]
    fields = {
        "dv_lim_mps": lambda r: r.max_dv_pursuer_mps,
        "capture_radius_km": lambda r: r.capture_radius_km,
        "window_sec": lambda r: r.window_sec,
    }
    for name, value in fields.items():
        lo, hi = FINAL_RULE_RANGES[name]
        values = np.array([value(r) for r in samples])
        assert np.all((lo <= values) & (values <= hi))
        positions = np.log(values / lo) / math.log(hi / lo)
        assert 0.45 < float(np.mean(positions)) < 0.55
        assert 0.43 < float(np.mean(positions < 0.5)) < 0.57
    for r in samples:
        assert r.max_dv_pursuer_mps == r.max_dv_evader_mps
        assert r.with_(window_sec=FINAL_RULES_BASE.window_sec,
                       max_dv_pursuer_mps=FINAL_RULES_BASE.max_dv_pursuer_mps,
                       max_dv_evader_mps=FINAL_RULES_BASE.max_dv_evader_mps,
                       capture_radius_km=FINAL_RULES_BASE.capture_radius_km) == FINAL_RULES_BASE


def test_make_games_final_ranges():
    games = make_games(4, "final_ranges", "final", seed=7)
    assert len(games) == 4
    rule_tuples = set()
    for rules, _, _, family in games:
        assert family == "final"
        assert rules["safe_sma_km"] is not None
        assert rules["max_dv_pursuer_mps"] == rules["max_dv_evader_mps"]
        rule_tuples.add((rules["max_dv_pursuer_mps"], rules["capture_radius_km"], rules["window_sec"]))
    assert len(rule_tuples) == 4
    with pytest.raises(ValueError, match="final"):
        make_games(1, "final_ranges", "near_coplanar")


def test_evaluate_help_mentions_final_ranges():
    process = subprocess.run([sys.executable, os.path.join(ROOT, "evaluate.py"), "--help"],
                             cwd=ROOT, capture_output=True, text=True, timeout=10)
    assert process.returncode == 0
    assert "final_ranges" in process.stdout and "--scenario" in process.stdout


def test_breakdown_buckets_and_certificate_violation():
    orbit_p = {"sma": 7000.0, "ecc": 0.0, "inc": 0.0, "raan": 0.0, "aop": 0.0, "ta": 1.0}
    orbit_e = dict(orbit_p, ta=0.0)
    capacity = full_burn_dsma_km(7000.0, 250.0)
    result = {
        "pursuer": "capture_pursuer", "evader": "safe_evader", "winner": "pursuer",
        "outcome": "capture", "rounds_played": 2, "game_id": 42,
        "rules": {"max_dv_pursuer_mps": 250.0, "max_dv_evader_mps": 250.0,
                  "capture_radius_km": 5.0, "window_sec": 1200.0,
                  "safe_sma_km": [7000.0 + 2.5 * capacity, 7000.0 + 3.5 * capacity]},
        "orbit_pursuer": orbit_p, "orbit_evader": orbit_e,
        "info_evader": [{"round": 1, "certificate": False}, {"round": 2, "certificate": True}],
        "info_pursuer": [{"round": 1, "hit_prob": 0.2}, {"round": 2, "hit_prob": 0.8}],
    }
    assert game_buckets(result) == {
        "dv": "200–350", "radius": "3–8", "window": "1200–2400",
        "tau": "10–30", "distance": "0–0.5", "zone": "2–4",
    }
    body = breakdown_report([result])
    assert "證書成立的回合被捕獲：1 次" in body
    assert "game_id=42" in body
    assert "平均 hit_prob" in body and "50.0%" in body


@pytest.fixture(scope="module")
def final_results():
    games = make_games(4, "final_ranges", "final", seed=13)
    return run_tournament(["lambert_pursuer"], ["safe_evader_fast"],
                          games, workers=1, progress=False)


def test_play_records_orbits_as_json(final_results):
    assert len(final_results) == 4
    for result in final_results:
        for side in ("pursuer", "evader"):
            orbit = result[f"orbit_{side}"]
            assert set(orbit) == {"sma", "ecc", "inc", "raan", "aop", "ta"}
            assert all(math.isfinite(float(v)) for v in orbit.values())
        json.dumps(result, default=float)


def test_final_breakdown_cli(final_results, tmp_path):
    source = tmp_path / "games.jsonl"
    source.write_text("".join(json.dumps(r, default=float) + "\n" for r in final_results), encoding="utf-8")
    report = tmp_path / "breakdown.md"
    command = [sys.executable, os.path.join(ROOT, "tools", "final_breakdown.py"),
               str(source), "--out", str(report)]
    process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert process.returncode == 0, process.stdout + process.stderr
    body = report.read_text(encoding="utf-8")
    for heading in ("躲方勝率", "結局", "ΔV_lim", "R_cap", "T_round", "τ*",
                    "初始距離", "安全空域偏移", "證書成立比例", "依回合", "依規則與題目分桶"):
        assert heading in body
    assert "lambert_pursuer" in body and "safe_evader_fast" in body
