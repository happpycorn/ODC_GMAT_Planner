"""合成 GMAT 密集輸出：不呼叫 GMAT 的撞地閘門與事件順序測試。"""
from types import SimpleNamespace

import numpy as np
import pytest

from game.rules import Rules
from physics import RE_VAL
from tools import gmat_verify
from tools.gmat_verify import analyze_dense, earth_gate_lines


def _rows(times, trajectory):
    return np.array([[t, *trajectory(t)[0], *trajectory(t)[1],
                      *trajectory(t)[2], *trajectory(t)[3]] for t in times], dtype=float)


def _radial(R, gap0=20.0):
    def trajectory(t):
        return ([R+20-4*t, 0, 0], [-4, 0, 0],
                [R+20-4*t+gap0-2*t, 0, 0], [-6, 0, 0])
    return trajectory


def test_entire_trajectory_safe():
    rules = Rules(crash_altitude_km=175.0)
    rows = _rows([0, 10], lambda t: ([7000, 0, 0], [0, 0, 0], [7100, 0, 0], [0, 0, 0]))
    out = analyze_dense(rows, 5.0, rules=rules)
    assert out["earth_safe"] and out["first_event"] is None
    assert out["event_order"] == "none" and out["t_capture_sec"] is None
    assert out["crash_radius_km"] == RE_VAL + 175.0
    assert out["radii"]["pursuer"]["min_radius_km"] == 7000.0
    assert out["radii"]["evader"]["min_radius_km"] == 7100.0
    assert out["radii"]["pursuer"]["t_min_sec"] == 0.0


def test_crosses_earth_only_between_report_rows():
    rules = Rules(crash_altitude_km=200.0)
    R = RE_VAL + rules.crash_altitude_km

    def trajectory(t):
        x, vx = R+20-2*t*(10-t), -20+4*t
        return [x, 0, 0], [vx, 0, 0], [x+1000, 0, 0], [vx, 0, 0]

    rows = _rows([0, 10], trajectory)
    assert np.all(np.linalg.norm(rows[:, 1:4], axis=1) > R)
    out = analyze_dense(rows, 5.0, rules=rules)
    assert not out["earth_safe"] and out["first_event"] == "crash_pursuer"
    p = out["radii"]["pursuer"]
    assert p["min_radius_km"] == pytest.approx(R-30, abs=1e-8)
    assert p["t_min_sec"] == pytest.approx(5, abs=1e-5)
    assert p["t_crossing_sec"] == pytest.approx((20-np.sqrt(240))/4, abs=1e-7)
    assert out["event_order"] == "crash_only"


def test_crash_before_capture_invalidates_later_interception():
    rules = Rules()
    out = analyze_dense(_rows([0, 10], _radial(RE_VAL+rules.crash_altitude_km)), 5, rules=rules)
    assert out["first_event"] == "crash_pursuer" and out["crash_before_capture"]
    assert out["t_event_sec"] == pytest.approx(5, abs=1e-7)
    assert out["t_enter_capture_sec"] == pytest.approx(7.5, abs=1e-7)
    assert out["t_capture_candidate_sec"] == out["t_enter_capture_sec"]
    assert out["t_capture_sec"] is None
    assert out["event_order"] == "crash_before_capture"
    assert "【撞地閘門未通過】" in "\n".join(earth_gate_lines(out))


def test_capture_before_crash_does_not_count_as_crash():
    rules = Rules()
    out = analyze_dense(_rows([0, 10], _radial(RE_VAL+rules.crash_altitude_km, gap0=10)), 5, rules=rules)
    assert out["earth_safe"] and not out["crash_before_capture"]
    assert out["first_event"] == "capture"
    assert out["t_capture_sec"] == pytest.approx(2.5, abs=1e-7)
    assert out["event_order"] == "capture_before_crash"
    assert out["radii"]["pursuer"]["crossed_crash_radius"]
    assert "捕獲後觸及門檻不算撞地" in "\n".join(earth_gate_lines(out))


def test_simultaneous_events_prioritize_crash_like_engine():
    rules = Rules()
    out = analyze_dense(_rows([0, 10], _radial(RE_VAL+rules.crash_altitude_km, gap0=15)), 5, rules=rules)
    assert out["first_event"] == "crash_pursuer" and out["t_capture_sec"] is None


def test_endpoint_capture_does_not_count_mid_window_entry():
    rules = Rules(capture_mode="endpoint")
    out = analyze_dense(_rows([0, 10], _radial(RE_VAL+rules.crash_altitude_km, gap0=10)),
                        5, rules=rules, capture_times_sec=[10])
    assert out["t_enter_capture_sec"] == pytest.approx(2.5, abs=1e-7)
    assert out["t_capture_candidate_sec"] is None
    assert out["first_event"] == "crash_pursuer"


@pytest.mark.parametrize("rows", [np.empty((0, 13)), np.full((2, 13), np.nan), np.zeros((2, 12))])
def test_incomplete_dense_report_is_rejected(rows):
    with pytest.raises(ValueError, match="密集報表"):
        analyze_dense(rows, 5)


def test_duplicate_burn_rows_are_not_interpolated_across_velocity_jump():
    rows = _rows([0, 5, 5, 10], lambda t: ([7000, 0, 0], [0, 0, 0], [7100, 0, 0], [0, 0, 0]))
    # 第一段的末速仍為零，第二段的初速也是零；只有同時刻的速度會跳變。
    rows[1, 4] = 0.1
    rows[2, 4] = -0.1
    out = analyze_dense(rows, 5)
    assert out["earth_safe"] and out["radii"]["pursuer"]["min_radius_km"] > 6999


def test_verification_and_truth_use_actual_rules_and_dense_gate(monkeypatch):
    rules = Rules(crash_altitude_km=250, t_max_sec=10, window_sec=10)
    dense = _rows([0, 10], _radial(RE_VAL+rules.crash_altitude_km))
    rec = {"t": 0, "side": "pursuer", "coast_sec": 10, "dv_mps": 0,
           "dv_eci_mps": np.zeros(3), "rp_after": dense[-1, 1:4], "re_after": dense[-1, 7:10],
           "distance_after_km": float(np.linalg.norm(dense[-1, 1:4]-dense[-1, 7:10]))}
    game = SimpleNamespace(rules=rules, initial={"pursuer": (dense[0, 1:4], dense[0, 4:7]),
                                                "evader": (dense[0, 7:10], dense[0, 10:13])},
                           history=[rec], outcome="timeout", t_max=10, distance=lambda: rec["distance_after_km"])

    def fake_run(script, console, *, dense=False):
        assert dense and "Create ReportFile RF" in script
        return globals_dense.copy(), globals_dense.copy()

    globals_dense = dense
    monkeypatch.setattr(gmat_verify, "run_gmat", fake_run)
    for result in [gmat_verify.verify_game(game), gmat_verify.gmat_truth(game),
                   gmat_verify.gmat_step(rules, game.initial, rec, with_analysis=True)[1]]:
        assert result["first_event"] == "crash_pursuer" and result["t_capture_sec"] is None
        assert result["crash_radius_km"] == RE_VAL + 250


def test_copilot_verify_prints_crash_gate(tmp_path, monkeypatch, capsys):
    import copilot

    path = tmp_path / "state.json"
    copilot.main(["init", str(path)])
    gate = analyze_dense(_rows([0, 10], _radial(RE_VAL+Rules().crash_altitude_km)), 5)
    monkeypatch.setattr(gmat_verify, "verify_game", lambda game: {
        **gate, "max_dpos_km": .001, "final_dist_ours_km": 1., "final_dist_gmat_km": 1.})
    assert copilot.main(["advise", str(path), "--brains", "lambert_pursuer", "--no-rollout",
                         "--gmat", str(tmp_path / "advice.script"), "--verify"]) == 0
    printed = capsys.readouterr().out
    assert "【撞地閘門未通過】" in printed and "捕獲不成立" in printed
    assert "追者最低地心半徑" in printed and "躲者最低地心半徑" in printed


def test_rehearsal_stops_at_gmat_crash_and_saves_resynced_start_states(tmp_path, monkeypatch, capsys):
    import json
    import sys

    import copilot
    from tools import dress_rehearsal
    from tools.gmat_sensitivity import load_record

    monkeypatch.chdir(tmp_path)
    rules_path = tmp_path / "rules.json"
    rules_path.write_text(json.dumps(Rules(t_max_sec=900).to_dict()))
    crash = analyze_dense(_rows([0, 10], _radial(RE_VAL+Rules().crash_altitude_km)), 5)
    safe = analyze_dense(_rows([0, 300], lambda t: ([7000, 0, 0], [0, 0, 0], [7100, 0, 0], [0, 0, 0])), 5)
    calls = []

    def fake_step(rules, state, rec, *args, **kwargs):
        assert kwargs["with_analysis"]
        calls.append(rec["turn"])
        return state, safe if len(calls) == 1 else crash

    monkeypatch.setattr(gmat_verify, "gmat_step", fake_step)
    monkeypatch.setattr(gmat_verify, "gmat_truth", lambda *args, **kwargs: crash)
    monkeypatch.setattr(copilot, "advise", lambda *args, **kwargs: {
        "advice": [{"brain": "coast", "plan": [{"offset_sec": 0, "eci_mps": [0, 0, 0]}]}]})
    record_path = tmp_path / "replay.json"
    monkeypatch.setattr(sys, "argv", ["dress_rehearsal.py", "--rules", str(rules_path), "--role", "evader",
                                      "--opponent", "coast", "--no-rollout", "--force-model", "ranking_full",
                                      "--record-out", str(record_path), "--name", "gate_test"])
    dress_rehearsal.main()
    assert calls == [0, 1]  # 撞地後不再決策，也不重複推進最後一回合
    record = load_record(record_path)
    assert len(record["history"]) == 2 and record["source"]["resync"]
    for side in ("pursuer", "evader"):
        np.testing.assert_allclose(record["history"][1]["state_before"][side], record["initial"][side],
                                   rtol=0, atol=1e-10)  # 彩排報表以 12 位小數模擬官方輸入
    assert record["history"][1]["state_before"]["pursuer"][0] != record["history"][0]["rp_after"]
    assert "【撞地閘門未通過】" in capsys.readouterr().out
    report = (tmp_path / "reports/gate_test.md").read_text()
    assert "**【撞地閘門未通過】" in report and "捕獲不成立" in report
