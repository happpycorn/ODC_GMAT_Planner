"""公告題目的角色選擇器 CLI。"""
import json
import os
import subprocess
import sys
import time

import numpy as np
import pytest

from agents.final_common import kepler
from game.initial_state import align_initial_states
from game.scenarios import FINAL_RULES_BASE, sample_final_scenario
from physics import EARTH_MU, get_r0_v0


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "tools", "role_select.py")


@pytest.fixture(scope="module")
def announced_task(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("role_select")
    rules, scenario = sample_final_scenario(np.random.default_rng(19), FINAL_RULES_BASE)
    rp, vp = get_r0_v0(**scenario.orbit_pursuer)
    re, ve = get_r0_v0(**scenario.orbit_evader)
    rp_early, vp_early = kepler(rp, vp, -3600.0, EARTH_MU)
    initial = {
        "pursuer": {"epoch": "2026-11-09T00:00:00Z", "r_km": rp_early.tolist(), "v_kms": vp_early.tolist()},
        "evader": {"epoch": "2026-11-09T01:00:00Z", "r_km": re.tolist(), "v_kms": ve.tolist(),
                   "epoch_utc_gregorian": "09 Nov 2026 01:00:00.000"},
    }
    aligned = align_initial_states(initial)
    assert aligned["propagated_sec"] == {"pursuer": 3600.0, "evader": 0.0}
    assert np.linalg.norm(aligned["pursuer"][0] - rp) < 1e-3
    initial_path = tmp_path / "initial.json"
    rules_path = tmp_path / "announced.json"
    initial_path.write_text(json.dumps(initial), encoding="utf-8")
    rules_path.write_text(json.dumps(rules.to_dict()), encoding="utf-8")
    return initial_path, rules_path


def _run(initial, rules, *extra, timeout=60):
    return subprocess.run([sys.executable, SCRIPT, str(initial), "--rules", str(rules), *extra],
                          cwd=ROOT, capture_output=True, text=True, timeout=timeout)


def test_role_select_fast_budget_and_json(announced_task, tmp_path):
    initial, rules = announced_task
    output = tmp_path / "role.json"
    start = time.monotonic()
    process = _run(initial, rules, "--fast", "--budget-sec", "40", "--workers", "2", "--max-games", "3",
                   "--seed", "0", "--json", str(output))
    wall_sec = time.monotonic() - start
    assert process.returncode == 0, process.stdout + process.stderr
    assert wall_sec < 60.0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert len(data["pairings"]) == 5
    assert data["total_games"] == sum(row["n_games"] for row in data["pairings"])
    assert data["elapsed_sec"] <= wall_sec
    expected = {
        ("pursuer", "safe_evader_fast"),
        ("pursuer", "heuristic_evader"),
        ("pursuer", "dv_evader"),
        ("evader", "capture_pursuer_fast"),
        ("evader", "lambert_pursuer"),
    }
    assert {(row["our_role"], row["opponent"]) for row in data["pairings"]} == expected
    for row in data["pairings"]:
        assert 1 <= row["n_games"] <= 3
        assert 0.0 <= row["win_rate"] <= 1.0
        lo, hi = row["ci95"]
        assert -1e-12 <= lo <= row["win_rate"] + 1e-12
        assert row["win_rate"] - 1e-12 <= hi <= 1.0 + 1e-12
        assert sum(row["outcomes"].values()) == row["n_games"]
        assert row["avg_decision_ms"] >= 0.0
    assert data["recommendation"]["text"]
    assert "建議選" in process.stdout or "差不多" in process.stdout


def test_role_select_rejects_alternating(announced_task, tmp_path):
    initial, rules_path = announced_task
    rules = json.loads(rules_path.read_text(encoding="utf-8"))
    rules["turn_mode"] = "alternating"
    alternating = tmp_path / "alternating.json"
    alternating.write_text(json.dumps(rules), encoding="utf-8")
    process = _run(initial, alternating)
    output = process.stdout + process.stderr
    assert process.returncode != 0
    assert "simultaneous" in output
    assert "Traceback" not in output


@pytest.mark.parametrize("change, keyword", [
    ("position_in_meters", "km"),
    ("invalid_epoch", "epoch"),
])
def test_role_select_reports_initial_errors(announced_task, tmp_path, change, keyword):
    initial_path, rules_path = announced_task
    initial = json.loads(initial_path.read_text(encoding="utf-8"))
    if change == "position_in_meters":
        initial["pursuer"]["r_km"] = [x * 1000.0 for x in initial["pursuer"]["r_km"]]
    else:
        initial["pursuer"]["epoch"] = "明天早上"
    bad = tmp_path / f"{change}.json"
    bad.write_text(json.dumps(initial, ensure_ascii=False), encoding="utf-8")
    process = _run(bad, rules_path)
    output = process.stdout + process.stderr
    assert process.returncode != 0
    assert keyword in output
    assert "Traceback" not in output


def test_role_select_reports_missing_file(announced_task, tmp_path):
    _, rules = announced_task
    process = _run(tmp_path / "missing.json", rules)
    output = process.stdout + process.stderr
    assert process.returncode != 0
    assert "missing.json" in output and "找不到" in output
    assert "Traceback" not in output


def test_zone_features_unreachable_overrides_recommendation():
    """E29：6 發全推也到不了安全空域時，不看勝率表直接建議追方。"""
    from game.scenarios import sample_adversarial_scenario, sample_final_rules
    from physics import get_r0_v0
    from tools.role_select import _recommend, _zone_features
    rng = np.random.default_rng([3, 1])
    R, sc = sample_adversarial_scenario(rng, sample_final_rules(rng), "narrow")
    rp, vp = get_r0_v0(**sc.orbit_pursuer)
    re, ve = get_r0_v0(**sc.orbit_evader)
    feats = _zone_features(rp, vp, re, ve, R)
    assert feats["reachable"] and any("很窄" in f for f in feats["flags"])
    far = R.with_(safe_sma_km=(sc.meta["a_e"] + 30 * sc.meta["da"], sc.meta["a_e"] + 31 * sc.meta["da"]))
    feats = _zone_features(rp, vp, re, ve, far)
    assert not feats["reachable"] and any("到不了" in f for f in feats["flags"])
    rows = [{"win_rate": 0.0}] * 3 + [{"win_rate": 1.0}] * 2
    rec = _recommend(rows, {"zone_features": feats})
    assert rec["role"] == "pursuer" and "追方" in rec["text"]
    assert _recommend(rows, {"zone_features": {"reachable": True}})["role"] == "evader"
