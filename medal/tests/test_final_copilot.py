"""金／銅牌賽 copilot 的實際 CLI 流程與手抄提交值驗收。"""
import json
import datetime as dt
import hashlib
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from agents import make_agent
from agents.final_common import kepler
from game.core import Game
from game.initial_state import align_initial_states, parse_epoch
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
    ("late", ("T_round", "--force")),
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
    unchanged = session_path.read_bytes()
    output = _run("announce", session_path, "--opponent-dv", "0", "0", "0",
                  "--our-dv", *numbers, "--state", state_path, success=False)
    for word in expected:
        assert word in output, output
    if fault == "swapped":
        assert "對調後回推殘差合計" in output and "明顯變小" in output
    assert session_path.read_bytes() == unchanged


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


OFFICIAL_INITIAL = """name,epoch,x,y,z,vx,vy,vz
SC_Red,09 Nov 2026 05:30:00.000,6581.049518,867.099028,1748.220537,0.182551744,6.531956040,-3.913692895
SC_Blue,09 Nov 2026 07:00:00.000,6370.305748,-494.318590,2548.864197,1.860380963,6.572138471,-3.358832356
"""
OFFICIAL_DVS = {
    "pursuer": [(-63.28, 162.25, -98.34), (-110.15, 91.97, -119.23), (48.83, -165.58, 17.18),
                (-84.47, -39.62, -140.12), (136.25, 141.74, -36.71), (154.36, 90.00, 89.86)],
    "evader": [(-2.62, 178.92, -89.33), (-71.28, -4.34, -70.00), (-25.62, -103.30, -169.33),
               (2.30, 63.09, -79.55), (36.76, 64.15, 67.33), (-65.86, -51.00, 55.33)],
}


@pytest.fixture
def official_case(tmp_path):
    rules = FINAL_RULES_BASE.with_(window_sec=900.0, capture_radius_km=8.0,
                                  max_dv_pursuer_mps=200.0, max_dv_evader_mps=200.0,
                                  safe_sma_km=(7428.137, 7488.137))
    rules_path = tmp_path / "official_rules.json"
    rules_path.write_text(json.dumps(rules.to_dict()), encoding="utf-8")
    initial_path = tmp_path / "official_initial.csv"
    initial_path.write_text(OFFICIAL_INITIAL, encoding="utf-8")
    return rules, rules_path, initial_path


def _official_csv(path, game, epoch, ship_names=("SC_Red", "SC_Blue")):
    """仿主辦 CSV：位置六位、速度九位，整回合時間為 GMAT UTCGregorian 的 .000。"""
    stamp = epoch.strftime("%d %b %Y %H:%M:%S.%f")[:-3]
    rows = ["name,epoch,x,y,z,vx,vy,vz"]
    for side, name in zip(SIDES, ship_names):
        values = [*(f"{x:.6f}" for x in game.r(side)), *(f"{x:.9f}" for x in game.v(side))]
        rows.append(",".join([name, stamp, *values]))
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


@pytest.mark.parametrize("role", SIDES)
def test_whole_match_recovers_csv_and_remembers_names(official_case, tmp_path, role):
    """僅在 new 指定船名，每回合只在 announce 提供一次 USB 檔，打到終局。"""
    rules, rules_path, initial_path = official_case
    session_path = tmp_path / f"whole_{role}.json"
    _run("new", "--rules", rules_path, "--initial", initial_path, "--role", role,
         "--names", "pursuer=SC_Red,evader=SC_Blue", "--out", session_path)
    session = json.loads(session_path.read_text(encoding="utf-8"))
    assert session["names"] == {"pursuer": ["SC_Red"], "evader": ["SC_Blue"]}
    assert session["order"] is None
    assert session["used_states"] == [{"sha256": hashlib.sha256(initial_path.read_bytes()).hexdigest(),
                                       "epoch": session["initial"]["epoch"], "round": 0,
                                       "path": str(initial_path)}]
    start = session["initial"]
    assert start["epoch"] == "2026-11-09T07:00:00+00:00"
    rp, vp = propagate(EARTH_MU, [6581.049518, 867.099028, 1748.220537],
                       [0.182551744, 6.531956040, -3.913692895], 5400.0, 0)
    np.testing.assert_allclose(start["pursuer"]["r_km"], rp, atol=1e-6, rtol=0)
    np.testing.assert_allclose(start["pursuer"]["v_kms"], vp, atol=1e-9, rtol=0)
    game = Game(rules, start["pursuer"]["r_km"], start["pursuer"]["v_kms"],
                start["evader"]["r_km"], start["evader"]["v_kms"])
    epoch0 = parse_epoch(start["epoch"])
    opponent = "evader" if role == "pursuer" else "pursuer"
    for number in range(1, rules.rounds + 1):
        advice = _run("advise", session_path, "--fast")
        submitted, _ = _submission(advice, "追方" if role == "pursuer" else "逃方", number)
        typed = np.asarray(OFFICIAL_DVS[opponent][number - 1], dtype=float)
        simulated = game.play_round(submitted, typed) if role == "pursuer" else game.play_round(typed, submitted)
        actual = {burn["side"]: burn["dv_eci_mps"] for burn in simulated["burns"]}
        state_path = _official_csv(tmp_path / f"usb_{number}.csv", game,
                                   epoch0 + dt.timedelta(seconds=game.t))
        output = _run("announce", session_path, "--state", state_path)
        assert output.splitlines()[0] in ("反推：通過", "反推：警告")
        assert output.rstrip().splitlines()[-1] == f"下一回合：{number + 1}"
        assert "UTC 時刻" in output and "是否攔截" in output and "安全空域" in output
        session = json.loads(session_path.read_text(encoding="utf-8"))
        record = session["rounds"][-1]
        announced = record["announcement"]
        assert announced["source"] == "state"
        assert announced["dt_source"] == "epoch"
        assert announced["typed_opponent_dv_mps"] is None and announced["typed_our_dv_mps"] is None
        assert np.linalg.norm(np.asarray(announced["opponent_dv_mps"]) - actual[opponent]) < 1e-3
        assert np.linalg.norm(np.asarray(announced["our_dv_mps"]) - submitted) < 1e-3
        assert session["current_state"] == session["predicted_state"]
        for side in SIDES:
            np.testing.assert_allclose(session["current_state"][side]["r_km"], game.r(side), atol=1e-6, rtol=0)
        assert record["round_result"]["outcome"] == game.outcome
        assert record["round_result"]["min_dist_km"] == pytest.approx(simulated["window_min_dist_km"], abs=1e-3)
        if any(abs(np.linalg.norm(actual[side]) - rules.max_dv(side)) <= 0.01 for side in SIDES):
            assert "已推滿上限（可能被縮放）" in output
        assert len(session["used_states"]) == number + 1
        assert session["used_states"][-1]["round"] == number
        if game.done:
            assert session["finished"] == {"outcome": game.outcome, "winner": game.winner, "round": number}
            unchanged = session_path.read_bytes()
            error = _run("advise", session_path, "--fast", success=False)
            assert f"比賽已在第 {number} 回合結束" in error and "不用再交" in error
            assert session_path.read_bytes() == unchanged
            break
    assert game.done and session.get("finished")
    assert sum(session["opponent_preferences"].values()) == session["round"] - 1
    summary = _run("show", session_path)
    assert "反推來源" in summary and "回合結果" in summary and "獲勝" in summary


@pytest.fixture
def ready_round(final_case, tmp_path):
    """建立已提交、已有回合末檔而尚未 announce 的 session。"""
    rules, game, rules_path, initial_path = final_case
    session_path = tmp_path / "ready.json"
    _run("new", "--rules", rules_path, "--initial", initial_path, "--role", "evader", "--out", session_path)
    output = _run("advise", session_path, "--fast")
    submitted, _ = _submission(output, "逃方", 1)
    game.play_round(np.zeros(3), submitted)
    assert not game.done
    state_path = _write_state(tmp_path / "ready_end.json", game, "json")
    return rules, game, session_path, state_path, submitted


def test_rejects_reused_state_by_content_and_keeps_session(ready_round, tmp_path):
    _, _, session_path, state_path, _ = ready_round
    _run("announce", session_path, "--state", state_path)
    unchanged = session_path.read_bytes()
    copied_path = tmp_path / "renamed.json"
    copied_path.write_bytes(state_path.read_bytes())
    output = _run("announce", session_path, "--state", copied_path, "--force", success=False)
    assert "第 1 回合已經用過了" in output and str(state_path) in output
    assert session_path.read_bytes() == unchanged


@pytest.mark.parametrize("source", ["epoch", "t_sec", "T_round"])
def test_rejects_round_start_with_different_file_content(ready_round, tmp_path, source):
    _, _, session_path, _, _ = ready_round
    session = json.loads(session_path.read_text(encoding="utf-8"))
    start = session["rounds"][0]["start_state"]
    if source == "epoch":
        start["epoch"] = "2026-11-09T07:00:00Z"
    elif source == "t_sec":
        start["t_sec"] = 0.0
    session_path.write_text(json.dumps(session), encoding="utf-8")
    state_path = tmp_path / "start_again.json"
    state_path.write_text(json.dumps(start, indent=4), encoding="utf-8")
    unchanged = session_path.read_bytes()
    output = _run("announce", session_path, "--state", state_path, "--force", success=False)
    assert "這是本回合起點的狀態，不是回合末" in output
    assert session_path.read_bytes() == unchanged


def test_rejects_initial_file_and_missing_announcement(ready_round, final_case):
    _, _, session_path, _, _ = ready_round
    initial_path = final_case[3]
    unchanged = session_path.read_bytes()
    reused = _run("announce", session_path, "--state", initial_path, success=False)
    assert "第 0 回合已經用過了" in reused
    missing = _run("announce", session_path, success=False)
    assert "請給主辦的回合末狀態檔 --state（建議）" in missing
    assert "--opponent-dv X Y Z" in missing
    assert session_path.read_bytes() == unchanged


def test_typed_burns_only_warn_and_state_wins(ready_round):
    _, _, session_path, state_path, submitted = ready_round
    output = _run("announce", session_path, "--state", state_path, "--opponent-dv", 5, 0, 0,
                  "--our-dv", *(submitted + [0, 5, 0]))
    assert output.splitlines()[0] == "反推：警告"
    assert "你打的對手 Δv 跟檔案反推差 5.00 m/s；以檔案反推值為準" in output
    assert "你打的我方 Δv 跟檔案反推差 5.00 m/s" in output
    session = json.loads(session_path.read_text(encoding="utf-8"))
    announced = session["rounds"][0]["announcement"]
    assert np.linalg.norm(announced["opponent_dv_mps"]) < 1e-5
    assert np.linalg.norm(np.asarray(announced["our_dv_mps"]) - submitted) < 1e-5
    assert announced["typed_opponent_dv_mps"] == [5.0, 0.0, 0.0]
    assert len(announced["warnings"]) == 2


def _coasted_state(start, dv_p, dv_e, seconds):
    state = {}
    for side, dv in zip(SIDES, (dv_p, dv_e)):
        ship = start[side]
        r, v = kepler(np.asarray(ship["r_km"]), np.asarray(ship["v_kms"]) + np.asarray(dv) / 1000.0, seconds)
        state[side] = {"r_km": r.tolist(), "v_kms": v.tolist()}
    return state


@pytest.mark.parametrize("source", ["epoch", "t_sec"])
def test_uses_actual_elapsed_time_and_warns(ready_round, source):
    rules, _, session_path, state_path, submitted = ready_round
    session = json.loads(session_path.read_text(encoding="utf-8"))
    start = session["rounds"][0]["start_state"]
    seconds = rules.window_sec - 60.0
    state = _coasted_state(start, np.zeros(3), submitted, seconds)
    if source == "epoch":
        start["epoch"] = "2026-11-09T07:00:00Z"
        state["epoch"] = (parse_epoch(start["epoch"]) + dt.timedelta(seconds=seconds)).isoformat()
    else:
        start["t_sec"] = 0.0
        state["t_sec"] = seconds
    session_path.write_text(json.dumps(session), encoding="utf-8")
    state_path.write_text(json.dumps(state), encoding="utf-8")
    output = _run("announce", session_path, "--state", state_path)
    assert f"已用 {seconds:.1f} s 反推" in output and "T_round 抄錯" in output
    announced = json.loads(session_path.read_text(encoding="utf-8"))["rounds"][0]["announcement"]
    assert announced["dt_sec"] == seconds and announced["dt_source"] == source
    assert np.linalg.norm(np.asarray(announced["our_dv_mps"]) - submitted) < 1e-5


@pytest.mark.parametrize("fault", ["residual", "cap"])
def test_invalid_recovery_requires_force(ready_round, fault):
    rules, _, session_path, state_path, submitted = ready_round
    session = json.loads(session_path.read_text(encoding="utf-8"))
    start = session["rounds"][0]["start_state"]
    if fault == "residual":
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["pursuer"]["r_km"][0] += 20.0
    else:
        state = _coasted_state(start, [rules.max_dv("pursuer") + 20, 0, 0], submitted, rules.window_sec)
    state_path.write_text(json.dumps(state), encoding="utf-8")
    unchanged = session_path.read_bytes()
    output = _run("announce", session_path, "--state", state_path, success=False)
    assert "--force" in output and "核對後再放一次" in output
    assert ("回不到本回合起點" if fault == "residual" else "超過上限") in output
    assert session_path.read_bytes() == unchanged
    forced = _run("announce", session_path, "--state", state_path, "--force")
    assert forced.splitlines()[0] == "反推：警告" and "已用 --force 強制寫入" in forced
    assert json.loads(session_path.read_text(encoding="utf-8"))["round"] == 2


def test_small_recovery_residual_warns_without_force(ready_round):
    _, _, session_path, state_path, _ = ready_round
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["pursuer"]["r_km"][0] += 0.05
    state_path.write_text(json.dumps(state), encoding="utf-8")
    output = _run("announce", session_path, "--state", state_path)
    assert output.splitlines()[0] == "反推：警告" and "回推位置殘差" in output
    announced = json.loads(session_path.read_text(encoding="utf-8"))["rounds"][0]["announcement"]
    assert 0.01 < announced["recovery"]["pursuer"]["position_residual_km"] < 5.0
    assert announced["recovery"]["pursuer"]["lambert_diff_mps"] > 0.01


def test_warns_if_our_submission_was_not_executed(ready_round):
    rules, _, session_path, state_path, _ = ready_round
    session = json.loads(session_path.read_text(encoding="utf-8"))
    state = _coasted_state(session["rounds"][0]["start_state"], np.zeros(3), np.zeros(3), rules.window_sec)
    state_path.write_text(json.dumps(state), encoding="utf-8")
    output = _run("announce", session_path, "--state", state_path)
    assert "主辦執行的我方 Δv 跟提交行差" in output and "軸" in output
    assert "主辦當我們沒交（逾時）？馬上找工作人員" in output


def test_old_session_and_typed_only_announcement(ready_round):
    _, _, session_path, _, submitted = ready_round
    session = json.loads(session_path.read_text(encoding="utf-8"))
    for key in ("names", "order", "used_states"):
        session.pop(key)
    session_path.write_text(json.dumps(session), encoding="utf-8")
    _run("announce", session_path, "--opponent-dv", 0, 0, 0, "--our-dv", *submitted)
    session = json.loads(session_path.read_text(encoding="utf-8"))
    assert session["round"] == 2
    assert session["rounds"][0]["announcement"]["our_dv_mps"] == submitted.tolist()
    output = _run("advise", session_path, "--fast")
    _submission(output, "逃方", 2)


def test_old_session_state_announcement(ready_round):
    _, _, session_path, state_path, _ = ready_round
    session = json.loads(session_path.read_text(encoding="utf-8"))
    for key in ("names", "order", "used_states"):
        session.pop(key)
    session_path.write_text(json.dumps(session), encoding="utf-8")
    _run("announce", session_path, "--state", state_path)
    session = json.loads(session_path.read_text(encoding="utf-8"))
    assert session["round"] == 2 and len(session["used_states"]) == 1


def test_names_and_order_overrides_persist(official_case, tmp_path):
    rules, rules_path, initial_path = official_case
    session_path = tmp_path / "options.json"
    _run("new", "--rules", rules_path, "--initial", initial_path, "--role", "evader",
         "--order", "pursuer,evader", "--out", session_path)
    session = json.loads(session_path.read_text(encoding="utf-8"))
    assert session["order"] == "pursuer,evader" and session["names"] is None
    state = session["initial"]
    game = Game(rules, state["pursuer"]["r_km"], state["pursuer"]["v_kms"],
                state["evader"]["r_km"], state["evader"]["v_kms"])
    epoch = parse_epoch(state["epoch"])
    path = _official_csv(tmp_path / "renamed_start.csv", game, epoch, ("船甲", "船乙"))
    advice = _run("advise", session_path, "--state", path, "--fast",
                  "--names", "pursuer=船甲,evader=船乙", "--order", "pursuer,evader")
    submitted, _ = _submission(advice, "逃方", 1)
    session = json.loads(session_path.read_text(encoding="utf-8"))
    assert session["names"] == {"pursuer": ["船甲"], "evader": ["船乙"]}
    game.play_round(np.zeros(3), submitted)
    path = _official_csv(tmp_path / "renamed_end.csv", game, epoch + dt.timedelta(seconds=game.t), ("船丙", "船丁"))
    _run("announce", session_path, "--state", path, "--names", "pursuer=船丙,evader=船丁",
         "--order", "pursuer,evader")
    session = json.loads(session_path.read_text(encoding="utf-8"))
    assert session["names"] == {"pursuer": ["船丙"], "evader": ["船丁"]}
    assert session["order"] == "pursuer,evader"


def test_initial_template_parse_new_and_role_select(official_case, tmp_path):
    """範本只需填真實的十四格，三個讀檔入口皆能保留註解並對齊時間。"""
    from tools.role_select import _load_inputs

    _, rules_path, _ = official_case
    template = json.loads((ROOT / "configs" / "initial_template.json").read_text(encoding="utf-8"))
    for side, row in zip(SIDES, OFFICIAL_INITIAL.splitlines()[1:]):
        _, epoch, *values = row.split(",")
        template[side].update(epoch=epoch, r_km=[float(x) for x in values[:3]],
                              v_kms=[float(x) for x in values[3:]])
    initial_path = tmp_path / "filled_template.json"
    initial_path.write_text(json.dumps(template, ensure_ascii=False), encoding="utf-8")
    parsed = _run("final", "parse", initial_path, "--names", "pursuer=SC_Red,evader=SC_Blue", script=COPILOT)
    assert "共同 epoch" in parsed and "5400" in parsed
    session_path = tmp_path / "template_session.json"
    _run("new", "--rules", rules_path, "--initial", initial_path, "--role", "pursuer", "--out", session_path,
         "--names", "pursuer=SC_Red,evader=SC_Blue")
    game, aligned = _load_inputs(initial_path, rules_path)
    expected = align_initial_states(template)
    state = json.loads(session_path.read_text(encoding="utf-8"))["initial"]
    assert aligned["epoch"] == expected["epoch"]
    for side in SIDES:
        np.testing.assert_allclose(game.r(side), state[side]["r_km"], atol=1e-9, rtol=0)
        np.testing.assert_allclose(game.v(side), state[side]["v_kms"], atol=1e-12, rtol=0)


def test_advise_manual_and_parse_manual_output(final_case, tmp_path):
    _, game, rules_path, initial_path = final_case
    session_path = tmp_path / "manual_session.json"
    _run("new", "--rules", rules_path, "--initial", initial_path, "--role", "evader", "--out", session_path)
    values = [x for side in SIDES for x in [*game.r(side), *game.v(side)]]
    answers = "\n".join([*(format(x, ".17g") for x in values), "y", ""])
    output = _run("advise", session_path, "--manual", "--fast", input_text=answers)
    _submission(output, "逃方", 1)
    manual_path = tmp_path / "manual_state.json"
    _run("manual", "--out", manual_path, input_text=answers)
    assert "偵測格式" in _run("parse", manual_path)


def test_midround_capture_finishes_session(tmp_path):
    """同一條圓軌道上從 20 km 外相向接近，回合中進入攔截球即終局。"""
    rules = FINAL_RULES_BASE.with_(window_sec=900.0, capture_radius_km=8.0,
                                  max_dv_pursuer_mps=200.0, max_dv_evader_mps=200.0)
    rp, vp = get_r0_v0(sma=7400.0, ecc=0.0, inc=30.0, raan=10.0, aop=0.0, ta=0.0)
    re, ve = get_r0_v0(sma=7400.0, ecc=0.0, inc=30.0, raan=10.0, aop=0.0, ta=0.2)
    game = Game(rules, rp, vp, re, ve)
    initial_path = _write_state(tmp_path / "capture_initial.json", game, "json")
    initial = json.loads(initial_path.read_text(encoding="utf-8"))
    initial["epoch"] = "2026-11-09T07:00:00Z"
    initial_path.write_text(json.dumps(initial), encoding="utf-8")
    rules_path = tmp_path / "capture_rules.json"
    rules_path.write_text(json.dumps(rules.to_dict()), encoding="utf-8")
    session_path = tmp_path / "capture_session.json"
    _run("new", "--rules", rules_path, "--initial", initial_path, "--role", "pursuer", "--out", session_path)
    advice = _run("advise", session_path, "--fast")
    submitted, _ = _submission(advice, "追方", 1)
    toward = (rp - re) / np.linalg.norm(rp - re) * 150.0
    simulated = game.play_round(submitted, toward)
    assert game.outcome == "capture" and 1.0 < simulated["coast_sec"] < rules.window_sec
    state = _state_dict(game)
    state["epoch"] = (parse_epoch(initial["epoch"]) + dt.timedelta(seconds=game.t)).isoformat()
    state_path = tmp_path / "capture_end.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    output = _run("announce", session_path, "--state", state_path)
    assert "是否攔截：是" in output and "比賽應已結束：攔截，追方獲勝" in output
    session = json.loads(session_path.read_text(encoding="utf-8"))
    assert session["finished"] == {"outcome": "capture", "winner": "pursuer", "round": 1}
    assert session["rounds"][0]["round_result"]["outcome"] == "capture"
    assert "不用再交" in _run("advise", session_path, success=False)
