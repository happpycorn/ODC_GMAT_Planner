"""官方初始狀態匯入（game/initial_state.py）與經緯高格式轉換（tools/gmat_state_convert.py）。"""
import datetime as dt
import json
import math
import os

import numpy as np
import pytest

from game.initial_state import align_initial_states, parse_epoch
from physics import EARTH_MU, get_r0_v0, propagate
from tools.gmat_state_convert import convert_script, parse_report, run_convert, spacecraft_lines
from tools.gmat_verify import GMAT_CONSOLE

UTC = dt.timezone.utc
EL_P = {"sma": 7000.0, "ecc": 0.001, "inc": 30.0, "raan": 10.0, "aop": 0.0, "ta": 0.0}
EL_E = {"sma": 7100.0, "ecc": 0.002, "inc": 30.5, "raan": 10.0, "aop": 0.0, "ta": 20.0}
GMAT = os.path.exists(GMAT_CONSOLE)


# ------------------------------------------------------------------ parse_epoch
def test_parse_epoch_formats():
    want = dt.datetime(2026, 11, 9, 0, 0, 0, tzinfo=UTC)
    assert parse_epoch("2026-11-09T00:00:00") == want
    assert parse_epoch("2026-11-09T00:00:00Z") == want
    assert parse_epoch("2026-11-09T00:00:00.250Z") == want + dt.timedelta(milliseconds=250)
    assert parse_epoch("09 Nov 2026 00:00:00.000") == want
    assert parse_epoch("09 Nov 2026 15:30:00.500") == want + dt.timedelta(hours=15, minutes=30, milliseconds=500)
    assert parse_epoch(31353.5) == want                       # GMAT UTCModJulian（JD − 2430000.0）
    assert parse_epoch(dt.datetime(2026, 11, 9)) == want
    for bad in ("2026/11/09", "tomorrow", math.nan, None, [1]):
        with pytest.raises(ValueError):
            parse_epoch(bad)


# ------------------------------------------------------------------ align_initial_states
def test_align_propagates_earlier_ship():
    rp, vp = get_r0_v0(**EL_P)
    spec = {"pursuer": {"epoch": "2026-11-09T00:00:00Z", "r_km": list(rp), "v_kms": list(vp)},
            "evader": {"epoch": "09 Nov 2026 15:00:00.000", "elements": {k.upper(): v for k, v in EL_E.items()}}}
    out = align_initial_states(spec)
    assert out["epoch"] == dt.datetime(2026, 11, 9, 15, tzinfo=UTC)
    assert out["propagated_sec"] == {"pursuer": 54000.0, "evader": 0.0}
    r1, v1 = propagate(EARTH_MU, rp, vp, 54000.0, 0)
    assert np.linalg.norm(out["pursuer"][0] - r1) < 1e-6 and np.linalg.norm(out["pursuer"][1] - v1) < 1e-9
    re, ve = get_r0_v0(**EL_E)
    np.testing.assert_allclose(out["evader"][0], re)
    np.testing.assert_allclose(out["evader"][1], ve)


def test_align_evader_earlier_and_json_path(tmp_path):
    re, ve = get_r0_v0(**EL_E)
    spec = {"pursuer": {"epoch": 31353.5 + 0.5, "elements": EL_P},
            "evader": {"epoch": "2026-11-09T00:00:00Z", "r_km": list(re), "v_kms": list(ve)}}
    path = tmp_path / "init.json"
    path.write_text(json.dumps(spec))
    out = align_initial_states(str(path))
    assert out["propagated_sec"] == {"pursuer": 0.0, "evader": 43200.0}


def test_align_without_epochs():
    spec = {"pursuer": {"elements": EL_P}, "evader": {"elements": EL_E}}
    out = align_initial_states(spec)
    assert out["epoch"] is None and out["propagated_sec"] == {"pursuer": 0.0, "evader": 0.0}


def test_align_input_errors():
    rp, vp = get_r0_v0(**EL_P)
    good = {"epoch": "2026-11-09T00:00:00Z", "r_km": list(rp), "v_kms": list(vp)}
    with pytest.raises(ValueError, match="公尺"):
        align_initial_states({"pursuer": dict(good, r_km=list(rp * 1000)), "evader": good})
    with pytest.raises(ValueError, match="m/s"):
        align_initial_states({"pursuer": dict(good, v_kms=list(vp * 1000)), "evader": good})
    with pytest.raises(ValueError, match="epoch"):
        align_initial_states({"pursuer": good, "evader": {"r_km": list(rp), "v_kms": list(vp)}})
    with pytest.raises(ValueError):
        align_initial_states({"pursuer": good})
    with pytest.raises(ValueError, match="elements"):
        align_initial_states({"pursuer": good, "evader": {"elements": {"sma": 7000.0}}})


# ------------------------------------------------------------------ gmat_state_convert（純函式）
AZFPA = {"DateFormat": "UTCGregorian", "Epoch": "09 Nov 2026 00:00:00.000", "CoordinateSystem": "EarthFixed",
         "DisplayStateType": "SphericalAZFPA", "RMAG": 6871, "RA": 0, "DEC": 0, "VMAG": 7.2, "AZI": 90, "FPA": 90}


def test_convert_script_text():
    lines = spacecraft_lines("ShipP", {"RMAG": 6871.5, **AZFPA})
    assert lines[0] == "Create Spacecraft ShipP;"
    assert lines[1:5] == ["ShipP.DateFormat = UTCGregorian;", "ShipP.Epoch = '09 Nov 2026 00:00:00.000';",
                          "ShipP.CoordinateSystem = EarthFixed;", "ShipP.DisplayStateType = SphericalAZFPA;"]
    assert "ShipP.RMAG = 6871;" in lines and "ShipP.VMAG = 7.2;" in lines
    script = convert_script({"pursuer": AZFPA, "evader": dict(AZFPA, Epoch=31353.5)}, "/tmp/r.txt")
    script.encode("ascii")
    assert "ShipE.Epoch = '31353.5';" in script
    assert script.count("Report Rep ") == 2
    assert "Report Rep ShipE.UTCModJulian ShipE.EarthMJ2000Eq.X" in script and script.rstrip().endswith(
        "ShipE.UTCGregorian;")
    for bad in ({"RMAG; Create": 1}, {"1RMAG": 1}, {"RA.x": 1}, {"Epoch": "x'; y"}, {"Epoch": "a;b"},
                {"CoordinateSystem": "Earth\nFixed"}, {"RMAG": math.inf}, {"RMAG": True}, {"RMAG": [1]}):
        with pytest.raises(ValueError):
            spacecraft_lines("ShipP", bad)
    with pytest.raises(ValueError):
        convert_script({"pursuer": AZFPA}, "/tmp/r.txt")


def test_parse_report_text():
    text = ("31353.5                   4611.898762095566         5093.219111753266         -12.24286946159785        "
            "-5.708478848075311        5.169050740133242         0.01482384356928228       09 Nov 2026 00:00:00.000\n"
            "31354.125                 415.8712145871688         -6887.956924485437        -0.888431715850764        "
            "5.530319591268994         0.2711848409733537        5.005752195310467         09 Nov 2026 15:00:00.000\n")
    out = parse_report(text)
    assert out["pursuer"]["epoch"] == "2026-11-09T00:00:00Z"
    assert out["evader"]["epoch"] == "2026-11-09T15:00:00Z"
    assert out["evader"]["epoch_utc_gregorian"] == "09 Nov 2026 15:00:00.000"
    assert out["pursuer"]["r_km"][2] == pytest.approx(-12.24286946159785)
    assert out["evader"]["v_kms"] == pytest.approx([5.530319591268994, 0.2711848409733537, 5.005752195310467])
    assert align_initial_states(out)["propagated_sec"]["pursuer"] == pytest.approx(54000.0, abs=1e-3)
    with pytest.raises(ValueError):
        parse_report(text.splitlines()[0])                      # 少一列
    with pytest.raises(ValueError):
        parse_report(text.replace("31354.125", "31354.5"))      # MJD 跟 Gregorian 對不起來


# ------------------------------------------------------------------ gmat_state_convert（實跑 GMAT）
@pytest.mark.skipif(not GMAT, reason="GmatConsole 不在這台機器上")
def test_gmat_convert_spherical_azfpa():
    """赤道上 RA=0、DEC=0、FPA=90（水平）、AZI=90（往東）。

    EarthFixed 赤道跟 EarthMJ2000Eq 赤道差了 J2000 以來的歲差章動（2026 年約 0.15°），所以 MJ2000 的 z
    不會剛好是 0（00:00 時約 −12 km）；這裡檢查跟座標系無關的量：|r| = RMAG、r ⟂ v（FPA = 90 時慣性系
    速度 = 相對速度 + ω×r，兩項都垂直 r）、扣除地球自轉後 |v| = VMAG。DEC=30 時 z ≈ RMAG·sin 30°。"""
    omega = 7.2921158553e-5
    spec = {"pursuer": AZFPA, "evader": dict(AZFPA, Epoch="09 Nov 2026 15:00:00.000", DEC=30, RMAG=6900.5)}
    out = run_convert(spec)
    for side, st, rmag, dec in (("pursuer", out["pursuer"], 6871.0, 0.0), ("evader", out["evader"], 6900.5, 30.0)):
        r, v = np.array(st["r_km"]), np.array(st["v_kms"])
        assert abs(np.linalg.norm(r) - rmag) < 1e-3, side                 # < 1 m
        assert abs(r @ v) / (np.linalg.norm(r) * np.linalg.norm(v)) < 1e-9, side
        v_rel = v - np.cross([0.0, 0.0, omega], r)
        assert abs(np.linalg.norm(v_rel) - 7.2) < 5e-3, side              # 自轉軸跟 MJ2000 z 差 ~0.15°
        assert abs(r[2] - rmag * math.sin(math.radians(dec))) < 25.0, side
    assert out["pursuer"]["epoch"] == "2026-11-09T00:00:00Z"
    assert out["evader"]["epoch"] == "2026-11-09T15:00:00Z"
    aligned = align_initial_states(out)
    assert aligned["propagated_sec"]["pursuer"] == pytest.approx(54000.0, abs=1e-3)


@pytest.mark.skipif(not GMAT, reason="GmatConsole 不在這台機器上")
def test_gmat_convert_cartesian_identity():
    """EarthMJ2000Eq 笛卡兒原樣進出（確認報表欄位與解析沒有錯位）。"""
    rp, vp = get_r0_v0(**EL_P)
    sc = {"DateFormat": "UTCGregorian", "Epoch": "09 Nov 2026 00:00:00.000", "CoordinateSystem": "EarthMJ2000Eq",
          "DisplayStateType": "Cartesian", **{k: float(x) for k, x in zip(("X", "Y", "Z", "VX", "VY", "VZ"),
                                                                            list(rp) + list(vp))}}
    out = run_convert({"pursuer": sc, "evader": sc})
    np.testing.assert_allclose(out["pursuer"]["r_km"], rp, atol=1e-9)
    np.testing.assert_allclose(out["evader"]["v_kms"], vp, atol=1e-12)
