"""金／銅牌賽 copilot 的實際 CLI 流程與手抄提交值驗收。"""
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from agents import make_agent
from agents.final_common import kepler
from game.core import Game
from game.scenarios import FINAL_RULES_BASE, sample_final_scenario
from physics import EARTH_MU, get_r0_v0, propagate


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "final_copilot.py"
COPILOT = ROOT / "copilot.py"
SIDES = ("pursuer", "evader")


@pytest.fixture
def final_case(tmp_path):
    """固定題目讓兩種角色都可完整打完前三回合。"""
    base = FINAL_RULES_BASE.with_(window_sec=600.0, capture_radius_km=2.0)
    rules, scenario = sample_final_scenario(np.random.default_rng(42), base)
    game = Game.from_elements(rules, scenario.orbit_pursuer, scenario.orbit_evader)
    rules_path = tmp_path / "announced.json"
    initial_path = tmp_path / "initial.json"
    rules_path.write_text(json.dumps(rules.to_dict(), ensure_ascii=False), encoding="utf-8")
    _write_state(initial_path, game, "json")
    return rules, game, rules_path, initial_path


def _run(*args, script=SCRIPT, input_text=None, success=True):
    """從工作目錄執行公開 CLI；失敗時顯示完整輸出。"""
    process = subprocess.run(
        [sys.executable, str(script), *(str(x) for x in args)],
        cwd=ROOT, input=input_text, capture_output=True, text=True, timeout=90,
    )
    if success:
        assert process.returncode == 0, process.stdout + process.stderr
    else:
        assert process.returncode != 0, process.stdout + process.stderr
        assert "Traceback" not in process.stdout + process.stderr
    return process.stdout + process.stderr


def _state_dict(game):
    return {side: {"r_km": game.r(side).tolist(), "v_kms": game.v(side).tolist()} for side in SIDES}


def _write_state(path, game, fmt):
    """同一個官方回合起點依序模擬 JSON、CSV 與空白分隔 USB 檔。"""
    state = _state_dict(game)
    if fmt == "json":
        path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    elif fmt == "csv":
        lines = ["角色;x_km;y_km;z_km;vx_kms;vy_kms;vz_kms"]
        for side, name in (("pursuer", "追方"), ("evader", "逃方")):
            values = state[side]["r_km"] + state[side]["v_kms"]
            lines.append(name + ";" + ";".join(format(x, ".17g") for x in values))
        path.write_text("\ufeff" + "\n".join(lines) + "\n", encoding="utf-8")
    elif fmt == "text":
        lines = ["# 官方本回合起點，EarthMJ2000Eq；位置 km，速度 km/s"]
        for side in SIDES:
            values = state[side]["r_km"] + state[side]["v_kms"]
            lines.append(side + " " + " ".join(format(x, ".17g") for x in values))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        raise AssertionError(fmt)
    return path


def _submission(output, expected_role, expected_round, decimals=4):
    """只從終端機最後一行讀手抄數字，不從 session 抄內部浮點值。"""
    lines = output.rstrip().splitlines()
    assert lines and lines[-1].startswith("提交："), output
    fields = [x.strip() for x in lines[-1].removeprefix("提交：").split(",")]
    assert len(fields) == 5, lines[-1]
    assert fields[:2] == [expected_role, str(expected_round)]
    assert all(re.fullmatch(rf"[+-]?\d+\.\d{{{decimals}}}", x) for x in fields[2:])
    return np.array([float(x) for x in fields[2:]], dtype=float), fields[2:]


def _scaled(raw, limit, margin=0.05):
    raw = np.asarray(raw, dtype=float)
    norm = float(np.linalg.norm(raw))
    return raw * (min(norm, limit - margin) / norm) if norm else raw


@pytest.mark.parametrize("role, opposite", [
    ("evader", "capture_pursuer"),
    ("pursuer", "heuristic_evader"),
])
def test_three_rounds_use_printed_submission_and_official_state(final_case, tmp_path, role, opposite):
    """三回合用印出的數字交手；每回合公告後用官方狀態核對二體預測。"""
    rules, initial_game, rules_path, initial_path = final_case
    session_path = tmp_path / f"{role}_session.json"
    _run("new", "--rules", rules_path, "--initial", initial_path,
         "--role", role, "--out", session_path)
    game = initial_game.clone()
    for round_number, fmt in enumerate(("json", "csv", "text"), 1):
        state_path = _write_state(tmp_path / f"round_{round_number}.{fmt}", game, fmt)
        before = game.clone()
        output = _run("advise", session_path, "--state", state_path, "--seed", round_number)
        submitted, numbers = _submission(output, "追方" if role == "pursuer" else "逃方", round_number)
        assert "重驗" in output and "通過" in output, output
        assert np.linalg.norm(submitted) <= rules.max_dv(role) - 0.05 + 1e-9

        session = json.loads(session_path.read_text(encoding="utf-8"))
        assert session["role"] == role and session["round"] == round_number
        record = session["rounds"][round_number - 1]
        raw = np.asarray(record["advice"]["raw_dv_mps"], dtype=float)
        np.testing.assert_allclose(submitted, _scaled(raw, rules.max_dv(role)), atol=1.01e-4, rtol=0)   # 四捨五入超過上限時改取捨去／進位，差一個步長內
        np.testing.assert_allclose(record["submission"]["dv_mps"], submitted, atol=1e-12, rtol=0)
        if role == "evader":
            own = make_agent({"name": "safe_evader", "seed": round_number})
            original = own.act(before.clone(), "evader")
            assert np.linalg.norm(submitted - _scaled(original, rules.max_dv(role))) < 1e-4
            assert record["advice"]["agent_info"]["certificate"] == own.last_info["certificate"]

        opponent = make_agent({"name": opposite, "seed": 100 + round_number})
        opponent_dv = np.asarray(opponent.act(before.clone(),
                                               "pursuer" if role == "evader" else "evader"), dtype=float)
        if role == "evader":
            game.play_round(opponent_dv, submitted)
        else:
            game.play_round(submitted, opponent_dv)
        assert not game.done, f"固定題目在第 {round_number} 回合提前結束"

        end_path = _write_state(tmp_path / f"end_{round_number}.json", game, "json")
        announcement = _run("announce", session_path, "--opponent-dv",
                            *(format(x, ".17g") for x in opponent_dv),
                            "--our-dv", *numbers, "--state", end_path)
        assert "一致性" in announcement and "通過" in announcement, announcement
        record = json.loads(session_path.read_text(encoding="utf-8"))["rounds"][round_number - 1]
        assert record["announcement"]["opponent_class"] in {
            "zero", "away", "normal+", "normal-", "radial+", "radial-", "zone", "other",
        }

    session = json.loads(session_path.read_text(encoding="utf-8"))
    assert session["round"] == 4 and len(session["rounds"]) == 3
    if role == "pursuer":
        assert sum(session["opponent_preferences"].values()) == 3
    summary = _run("show", session_path)
    for round_number in (1, 2, 3):
        assert re.search(rf"(?:第\s*{round_number}\s*回合|回合\s*{round_number})", summary), summary
    assert "一致性" in summary


def test_new_aligns_epochs_and_rejects_old_turn_mode(final_case, tmp_path):
    """兩艘起始 epoch 不同要對齊；舊的交替賽制不得誤建新 session。"""
    rules, game, rules_path, _ = final_case
    rp, vp = kepler(game.r("pursuer"), game.v("pursuer"), -60.0, EARTH_MU)   # physics.propagate 不支援負時間
    initial = _state_dict(game)
    initial["pursuer"].update(r_km=rp.tolist(), v_kms=vp.tolist(), epoch="2026-11-09T00:00:00Z")
    initial["evader"]["epoch"] = "2026-11-09T00:01:00Z"
    initial_path = tmp_path / "epochs.json"
    initial_path.write_text(json.dumps(initial), encoding="utf-8")
    session_path = tmp_path / "aligned.json"
    output = _run("new", "--rules", rules_path, "--initial", initial_path,
                  "--role", "evader", "--out", session_path)
    assert "60" in output and "秒" in output
    state = json.loads(session_path.read_text(encoding="utf-8"))["current_state"]
    np.testing.assert_allclose(state["pursuer"]["r_km"], game.r("pursuer"), atol=1e-5, rtol=0)
    np.testing.assert_allclose(state["pursuer"]["v_kms"], game.v("pursuer"), atol=1e-8, rtol=0)

    old_rules = rules.to_dict()
    old_rules["turn_mode"] = "alternating"
    old_path = tmp_path / "old_rules.json"
    old_path.write_text(json.dumps(old_rules), encoding="utf-8")
    failure = _run("new", "--rules", old_path, "--initial", initial_path,
                   "--role", "evader", "--out", tmp_path / "must_not_exist.json", success=False)
    assert "simultaneous" in failure


def test_custom_submission_format_and_margin(final_case, tmp_path):
    """自訂英文角色、兩位小數與回合基數；滿推建議須保留 0.05 m/s。"""
    rules, _, rules_path, initial_path = final_case
    session_path = tmp_path / "custom.json"
    fmt_path = tmp_path / "format.json"
    fmt = {"role_names": {"pursuer": "Chaser", "evader": "Target"},
           "round_base": 0, "decimals": 2, "dv_margin_mps": 0.05,
           "template": "{role}, {round}, {dvx}, {dvy}, {dvz}"}
    fmt_path.write_text(json.dumps(fmt), encoding="utf-8")
    _run("new", "--rules", rules_path, "--initial", initial_path, "--role", "evader",
         "--format", fmt_path, "--out", session_path)
    output = _run("advise", session_path, "--seed", 1)
    submitted, _ = _submission(output, "Target", 0, decimals=2)
    record = json.loads(session_path.read_text(encoding="utf-8"))["rounds"][0]
    raw = np.asarray(record["advice"]["raw_dv_mps"])
    assert np.linalg.norm(raw) == pytest.approx(rules.max_dv("evader"), abs=1e-6)
    assert np.linalg.norm(submitted) <= rules.max_dv("evader") - 0.05 + 1e-9
    assert np.linalg.norm(submitted - _scaled(raw, rules.max_dv("evader"))) < 0.009

    fmt["template"] = "{role}, {round}, {dvx}, {dvy}, {dvz}, {unknown}"
    fmt_path.write_text(json.dumps(fmt), encoding="utf-8")
    error = _run("new", "--rules", rules_path, "--initial", initial_path, "--role", "evader",
                 "--format", fmt_path, "--out", tmp_path / "invalid.json", success=False)
    assert "unknown" in error and "template" in error


@pytest.mark.parametrize("fault, expected", [
    ("meters", ("公尺", "km")),
    ("swapped", ("對調",)),
    ("late", ("時間", "60")),
])
def test_official_state_diagnostics(final_case, tmp_path, fault, expected):
    """發現單位、角色或時間不一致時給可行動的原因提示。"""
    _, game, rules_path, initial_path = final_case
    session_path = tmp_path / "session.json"
    _run("new", "--rules", rules_path, "--initial", initial_path,
         "--role", "evader", "--out", session_path)
    advice = _run("advise", session_path, "--seed", 1)
    submitted, numbers = _submission(advice, "逃方", 1)
    game.play_round(np.zeros(3), submitted)
    state = _state_dict(game)
    if fault == "meters":
        for side in SIDES:
            state[side]["r_km"] = (1000.0 * np.asarray(state[side]["r_km"])).tolist()
            state[side]["v_kms"] = (1000.0 * np.asarray(state[side]["v_kms"])).tolist()
    elif fault == "swapped":
        state = {"pursuer": state["evader"], "evader": state["pursuer"]}
    else:
        for side in SIDES:
            r, v = propagate(EARTH_MU, state[side]["r_km"], state[side]["v_kms"], 60.0, 0)
            state[side] = {"r_km": r.tolist(), "v_kms": v.tolist()}
    state_path = tmp_path / f"{fault}.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    output = _run("announce", session_path, "--opponent-dv", "0", "0", "0",
                  "--our-dv", *numbers, "--state", state_path, success=fault != "meters")
    for word in expected:
        assert word in output, output
    if fault != "meters":
        assert json.loads(session_path.read_text(encoding="utf-8"))["round"] == 2


def test_manual_state_file_and_copilot_router(final_case, tmp_path):
    """互動建檔可直接解析；舊 copilot 的 final 轉接可到 parse。"""
    _, game, _, initial_path = final_case
    values = []
    for side in SIDES:
        values.extend(game.r(side).tolist())
        values.extend(game.v(side).tolist())
    answers = "\n".join([*(format(x, ".17g") for x in values), "y", ""])
    state_path = tmp_path / "manual.json"
    _run("manual", "--out", state_path, input_text=answers)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    for side in SIDES:
        np.testing.assert_allclose(state[side]["r_km"], game.r(side), atol=1e-12, rtol=0)
        np.testing.assert_allclose(state[side]["v_kms"], game.v(side), atol=1e-12, rtol=0)
    output = _run("final", "parse", initial_path, script=COPILOT)
    assert "pursuer" in output or "追方" in output
    assert "evader" in output or "逃方" in output
