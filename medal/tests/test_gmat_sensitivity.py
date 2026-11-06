"""敏感度計畫、參數注入及預設腳本文字相容性；全部不需要 GMAT。"""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from game.core import Game
from game.rules import Rules
from tools import gmat_sensitivity as sensitivity
from tools.gmat_verify import (FULL_SPACECRAFT, game_to_script, instrument_dense_script,
                               spacecraft_parameters)


def _script_game():
    """此輸入在修改前的 gmat_verify.py 上算出下方 SHA-256，包含多發與零脈衝。"""
    return SimpleNamespace(
        rules=Rules(gravity_degree=4),
        initial={"pursuer": (np.array([7000., 1., 2.]), np.array([0., 7.5, .01])),
                 "evader": (np.array([7100., 20., 3.]), np.array([-.1, 7.4, .02]))},
        history=[{"side": "pursuer", "t": 0., "coast_sec": 300., "burns": [
            {"t": 0., "dv_eci_mps": [1., 2., 3.], "dv_mps": float(np.sqrt(14))},
            {"t": 100., "dv_eci_mps": [0., 0., 0.], "dv_mps": 0.}]},
                 {"side": "evader", "t": 300., "coast_sec": 150., "burns": [
                     {"t": 300., "dv_eci_mps": [0., 0., 0.], "dv_mps": 0.},
                     {"t": 400., "dv_eci_mps": [-2., 0., 0.], "dv_mps": 2.}]}])


# 修改前程式直接產生的雜湊；防止測試僅比較新實作的兩條路徑而漏掉文字變動。
BEFORE_SHA256 = {
    ('zonal', False, 0.0): 'e7ae243582b8011574f50bccdfa0f4cd312dd46e832c64322de8f7712e316c61',
    ('zonal', False, 123.0): '6ae79959cf3a3d255579ff840864b90dab74732eb2dd6a20432e7e5a98be1824',
    ('zonal', True, 0.0): '3938373567c32a3a13af75a3979ac5c01bb8ecefb271529618091893d781b4b4',
    ('zonal', True, 123.0): 'e77b01015819745578a9661d7a3575e4f9dafd1ca407caf0858890cc65b7c16b',
    ('ranking_full', False, 0.0): 'c2f5d087cf6f87c206d5ba402a55f5f303767fe2f4f0481ff62ffe9870bd4602',
    ('ranking_full', False, 123.0): '5c312ce4611aafc9adf75ce8d146df9de9123750ec13addb68ea5609dc53fd89',
    ('ranking_full', True, 0.0): 'cd7a228436893fed163270dce57bdca079afff4c812525904ff2380435fdcb74',
    ('ranking_full', True, 123.0): '0bbb1e8d59dd72f86af6b4a0e6d27ddbff9dc2b4464343e9069255cb5ae8d9f9',
}


@pytest.mark.parametrize("model,dense,offset", list(BEFORE_SHA256))
def test_default_script_is_byte_identical_to_before(model, dense, offset):
    script = game_to_script(_script_game(), "/tmp/report.txt", model,
                            dense_path="/tmp/dense.txt" if dense else None, epoch_offset_sec=offset)
    assert hashlib.sha256(script.encode("ascii")).hexdigest() == BEFORE_SHA256[model, dense, offset]
    explicit = game_to_script(_script_game(), "/tmp/report.txt", model,
                              dense_path="/tmp/dense.txt" if dense else None, epoch_offset_sec=offset,
                              spacecraft=FULL_SPACECRAFT, epoch_tai_mjd=21545.0)
    assert explicit == script


@pytest.fixture
def replay(tmp_path):
    game = Game(Rules(t_max_sec=600, burns_per_turn=2, gravity_degree=4),
                [7000, 0, 0], [0, 7.5, 0], [7100, 0, 0], [0, 7.45, 0])
    before = []
    for plan in ([(0, [1, 2, 3]), (100, [.5, 0, 0])], [(100, [-2, 0, 0])]):
        before.append({s: (game.r(s).copy(), game.v(s).copy()) for s in ("pursuer", "evader")})
        game.play_plan(plan)
    path = tmp_path / "replay.json"
    record = sensitivity.save_record(game, path, states_before=before, source={"kind": "test"})
    return path, record, game


def test_default_variants_are_single_factor_plus_combination():
    variants = sensitivity.resolve_variants()
    assert len(variants) == 15
    assert variants[0]["name"] == "baseline" and variants[-1]["name"] == "combined_worst"
    base = spacecraft_parameters()
    for v in variants[1:-1]:
        changed = [k for k in base if v["spacecraft"][k] != base[k]]
        assert len(changed) + int(v["epoch_offset_days"] != 0) == 1
    assert {v["epoch_offset_days"] for v in variants if v.get("group") == "epoch"} == {.5, 30., 180.}
    assert variants[-1]["provisional"]


def test_cli_dry_run_writes_every_script_and_never_calls_gmat(replay, tmp_path, monkeypatch, capsys):
    path, record, _ = replay
    output = tmp_path / "scan"

    def forbidden(*args, **kwargs):
        pytest.fail("dry-run 不得啟動任何 subprocess")

    monkeypatch.setattr(sensitivity.subprocess, "run", forbidden)
    assert sensitivity.main(["--record", str(path), "--output-dir", str(output), "--dry-run",
                             "--gmat-console", "/missing/GMAT Console"]) == 0
    plan = json.loads((output / "plan.json").read_text())
    assert plan["gmat_calls"] == 45 and len(plan["jobs"]) == 45
    assert len(list(output.rglob("*.script"))) == 45
    assert json.loads((output / "results.json").read_text())["gmat_executed"] == 0
    assert "未執行 GMAT" in (output / "results.md").read_text()
    assert "45 次" in capsys.readouterr().out
    for job in plan["jobs"]:
        text = Path(job["script"]).read_text()
        variant = next(v for v in plan["variants"] if v["name"] == job["variant"])
        for ship in ("ShipP", "ShipE"):
            for key, value in variant["spacecraft"].items():
                assert f"{ship}.{key} = {value};" in text
            epoch = variant["epoch_tai_mjd"] + job["t_offset_sec"]/86400
            literal = "21545" if epoch == 21545.0 else f"{epoch:.12f}"
            assert f"{ship}.Epoch = '{literal}';" in text
        assert job["command"][0] == "/missing/GMAT Console"
        assert "Report RF ShipP.ElapsedSecs" in text
        if job["kind"] == "window":
            before = np.array(record["history"][job["turn"]]["state_before"]["pursuer"][0])
            assert f"ShipP.X = {before[0]:.15f};" in text
            assert job["capture_times_sec"] == [sum([record["history"][job["turn"]]["t"],
                                                     record["history"][job["turn"]]["coast_sec"]])]


def test_engine_window_replays_same_multiburn_state_and_minimum(replay):
    _, record, game = replay
    for rec in record["history"]:
        prediction = sensitivity.engine_window(game.rules, rec["state_before"], rec)
        assert np.allclose(prediction["state_after"]["pursuer"][0], rec["rp_after"], atol=1e-9, rtol=0)
        assert np.allclose(prediction["state_after"]["evader"][0], rec["re_after"], atol=1e-9, rtol=0)
        assert prediction["d_min_km"] == pytest.approx(rec["window_min_dist_km"], abs=1e-9)


def test_parameter_overrides_and_epoch_compose_with_turn_time(replay, tmp_path):
    _, record, _ = replay
    variants = sensitivity.resolve_variants([
        {"name": "custom", "spacecraft": {"DryMass": 1234, "Cd": 1.7}, "epoch_offset_days": .5},
        {"name": "combined_worst", "spacecraft": {"Cr": 1.1}}],
        base_spacecraft={"SRPArea": 9}, epoch_tai_mjd=22000)
    plan = sensitivity.build_plan(record, variants, tmp_path / "custom", "/does/not/exist")
    job = next(j for j in plan["jobs"] if j["variant"] == "custom" and j["turn"] == 1)
    text = Path(job["script"]).read_text()
    assert "ShipE.DryMass = 1234;" in text and "ShipP.Cd = 1.7;" in text
    assert "ShipP.SRPArea = 9;" in text
    assert f"ShipP.Epoch = '{22000.5+300/86400:.12f}';" in text
    assert FULL_SPACECRAFT == {"DryMass": "850", "Cd": "2.2", "Cr": "1.8", "DragArea": "6", "SRPArea": "8"}


def test_combination_uses_measured_worst_direction():
    variants = sensitivity.resolve_variants()
    summaries = {}
    for i, v in enumerate(variants[:-1]):
        summaries[v["name"]] = {"max_endpoint_error_km": float(i), "max_abs_d_min_error_km": .1,
                                 "windows_completed": 2, "windows_expected": 2}
    combined = sensitivity.measured_combination(variants, summaries, 21545.0)
    assert not combined["provisional"]
    assert combined["selected"]["DryMass"] == "drymass_high"  # 不是先假定低質量一定最壞
    assert combined["spacecraft"]["DryMass"] == "1700"
    assert combined["spacecraft"]["Cd"] == "3"
    assert combined["epoch_tai_mjd"] == 21545+180


@pytest.mark.parametrize("kwargs", [{"spacecraft": {"DryMass": 0}}, {"spacecraft": {"Cd": float("nan")}},
                                    {"spacecraft": {"typo": 2}}, {"epoch_tai_mjd": float("inf")}])
def test_bad_parameters_are_rejected(kwargs):
    with pytest.raises(ValueError):
        game_to_script(_script_game(), "/tmp/x", "ranking_full", **kwargs)


def test_dense_instrumentation_has_initial_final_and_both_sides_of_burns():
    script = instrument_dense_script(game_to_script(_script_game(), "/tmp/x", dense_path="/tmp/d"))
    report = next(line for line in script.splitlines() if line.startswith("Report RF "))
    lines = script.splitlines()
    assert lines[lines.index("BeginMissionSequence;")+1] == report
    assert lines[-1] == report
    for i, line in enumerate(lines):
        if line.startswith("Maneuver "):
            assert lines[i-1] == report and lines[i+1] == report


def test_result_measurement_rejects_truncated_reports(replay, tmp_path):
    _, record, _ = replay
    plan = sensitivity.build_plan(record, sensitivity.resolve_variants([]), tmp_path / "broken", "/missing")
    job = plan["jobs"][0]
    row = np.concatenate([[0], *record["initial"]["pursuer"], *record["initial"]["evader"]])
    np.savetxt(job["report"], row[None, :])
    np.savetxt(job["dense"], row[None, :])
    with pytest.raises(ValueError, match="完整涵蓋"):
        sensitivity._measure_job(job, plan)


def test_full_scan_analysis_measured_combination_and_resume_without_gmat(replay, tmp_path, monkeypatch):
    """用合成 GMAT 報表走實跑流程，驗證兩種量測及續跑；沒有啟動外部程式。"""
    path, record, _ = replay
    output = tmp_path / "fake_scan"
    specs_path = tmp_path / "variants.json"
    specs_path.write_text(json.dumps([
        {"name": "light", "spacecraft": {"DryMass": 425}},
        {"name": "heavy", "spacecraft": {"DryMass": 1700}},
        {"name": "later", "epoch_offset_days": .5}]))
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        plan = json.loads((output / "plan.json").read_text())
        job = next(j for j in plan["jobs"] if j["script"] == command[-1])
        variant = next(v for v in plan["variants"] if v["name"] == job["variant"])
        error = float(variant["spacecraft"]["DryMass"])/850 + variant["epoch_offset_days"]
        if job["kind"] == "window":
            before = record["history"][job["turn"]]["state_before"]
            after = plan["engine_windows"][job["turn"]]["state_after"]
        else:
            before, after = record["initial"], plan["engine_windows"][-1]["state_after"]
        starts = np.array([before[s][0] for s in ("pursuer", "evader")])
        ends = np.array([after[s][0] for s in ("pursuer", "evader")])
        ends[0, 0] += error
        duration = job["duration_sec"]
        velocities = (ends-starts)/duration

        def row(t):
            positions = starts+(ends-starts)*(t/duration)
            return [t, *positions[0], *velocities[0], *positions[1], *velocities[1]]

        times = [0., *[t-job["t_offset_sec"] for t in job["capture_times_sec"]]]
        np.savetxt(job["report"], np.array([row(t) for t in times]))
        np.savetxt(job["dense"], np.array([row(t) for t in np.linspace(0, duration, int(np.ceil(duration/60))+1)]))
        return SimpleNamespace(returncode=0, stdout="合成輸出", stderr="")

    monkeypatch.setattr(sensitivity.subprocess, "run", fake_run)
    args = ["--record", str(path), "--output-dir", str(output), "--variants", str(specs_path),
            "--gmat-console", "/fake/GmatConsole"]
    assert sensitivity.main(args) == 0
    assert len(calls) == 15  # 5 變體 ×（2 窗口 + 1 整場）
    results = json.loads((output / "results.json").read_text())
    combined = next(v for v in results["variants"] if v["name"] == "combined_worst")
    assert combined["selected"] == {"DryMass": "heavy", "epoch": "later"}
    summary = next(s for s in results["summaries"] if s["variant"] == "combined_worst")
    assert summary["max_endpoint_error_km"] == pytest.approx(2.5)
    assert summary["open_loop"]["status"] == "completed"
    assert isinstance(summary["open_loop"]["captured"], bool)
    assert "radii" in summary["open_loop"]["gate"]
    assert "t_crossing_sec" in summary["open_loop"]["gate"]["radii"]["pursuer"]
    assert "失敗" not in (output / "results.md").read_text()
    assert sensitivity.main([*args, "--resume"]) == 0
    assert len(calls) == 15
    resumed = json.loads((output / "results.json").read_text())
    assert resumed["gmat_executed"] == 0 and resumed["gmat_resumed"] == 15


def test_gmat_console_symlink_keeps_original_bin_working_directory(replay, tmp_path):
    _, record, _ = replay
    app = tmp_path / "Fake.app/Contents/MacOS/GmatConsole"
    app.parent.mkdir(parents=True)
    app.write_text("不執行")
    console = tmp_path / "bin/GmatConsole"
    console.parent.mkdir()
    console.symlink_to(app)
    plan = sensitivity.build_plan(record, sensitivity.resolve_variants([]), tmp_path / "links", str(console))
    assert plan["jobs"][0]["command"][0] == str(console)
    assert plan["jobs"][0]["cwd"] == str(console.parent)
