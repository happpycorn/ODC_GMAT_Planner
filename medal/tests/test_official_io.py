"""官方狀態檔解析（game/official_io.py）：各種格式結果一致、錯誤訊息可行動、手動輸入。"""
import json

import numpy as np
import pytest

from game.official_io import manual_entry, read_official_state
from game.state_io import StateImportError
from physics import get_r0_v0

RP, VP = get_r0_v0(sma=7000.0, ecc=0.001, inc=30.0, raan=10.0, aop=0.0, ta=0.0)
RE, VE = get_r0_v0(sma=7100.0, ecc=0.002, inc=30.5, raan=10.0, aop=0.0, ta=3.0)


def _f(x):
    return format(float(x), ".17g")


def _check(out):
    for side, (r, v) in (("pursuer", (RP, VP)), ("evader", (RE, VE))):
        np.testing.assert_allclose(out[side][0], r, atol=1e-12, rtol=0)
        np.testing.assert_allclose(out[side][1], v, atol=1e-12, rtol=0)


def _gmat(tmp_path, with_epoch=True):
    cols = ["ShipP.UTCGregorian"] if with_epoch else []
    cols += [f"ShipP.EarthMJ2000Eq.{k}" for k in ("X", "Y", "Z", "VX", "VY", "VZ")]
    cols += [f"ShipE.EarthMJ2000Eq.{k}" for k in ("X", "Y", "Z", "VX", "VY", "VZ")]
    vals = (["09 Nov 2026 00:20:00.000"] if with_epoch else []) + [_f(x) for x in [*RP, *VP, *RE, *VE]]
    p = tmp_path / "gmat.txt"
    p.write_text("  ".join(cols) + "\n" + "  ".join(vals) + "\n")
    return p


def test_formats_agree(tmp_path):
    _check(read_official_state(_gmat(tmp_path)))
    out = read_official_state(_gmat(tmp_path))
    assert out["epoch"] is not None and out["epoch"].hour == 0 and out["epoch"].minute == 20

    csv = tmp_path / "s.csv"
    csv.write_text("﻿角色;x_km;y_km;z_km;vx_kms;vy_kms;vz_kms\n"
                   f"追方;{';'.join(_f(x) for x in [*RP, *VP])}\n逃方;{';'.join(_f(x) for x in [*RE, *VE])}\n",
                   encoding="utf-8")
    _check(read_official_state(csv))

    csv2 = tmp_path / "s2.csv"
    csv2.write_text("name,x,y,z,vx,vy,vz\n"
                    f"Evader,{','.join(_f(x) for x in [*RE, *VE])}\nPursuer,{','.join(_f(x) for x in [*RP, *VP])}\n")
    _check(read_official_state(csv2))                       # 順序對調也靠名稱認

    js = tmp_path / "s.json"
    js.write_text(json.dumps({"pursuer": {"r_km": list(RP), "v_kms": list(VP)},
                              "evader": {"r_km": list(RE), "v_kms": list(VE)}}))
    _check(read_official_state(js))
    js2 = tmp_path / "s2.json"
    js2.write_text(json.dumps({"pursuer": [*RP, *VP], "evader": [*RE, *VE]}))
    _check(read_official_state(js2))

    txt = tmp_path / "s.txt"
    txt.write_text("# 官方狀態\n" + "pursuer " + " ".join(_f(x) for x in [*RP, *VP]) + "\n"
                   + "evader " + " ".join(_f(x) for x in [*RE, *VE]) + "\n")
    _check(read_official_state(txt))
    txt12 = tmp_path / "s12.txt"
    txt12.write_text(" ".join(_f(x) for x in [*RP, *VP, *RE, *VE]) + "\n")
    _check(read_official_state(txt12, order="pursuer,evader"))


def test_names_and_order(tmp_path):
    p = tmp_path / "anon.csv"
    p.write_text("name,x,y,z,vx,vy,vz\n"
                 f"SatA,{','.join(_f(x) for x in [*RP, *VP])}\nSatB,{','.join(_f(x) for x in [*RE, *VE])}\n")
    with pytest.raises(StateImportError) as e:
        read_official_state(p)
    assert "SatA" in str(e.value) and "SatB" in str(e.value)
    _check(read_official_state(p, order="pursuer,evader"))
    _check(read_official_state(p, names={"pursuer": ["sata"], "evader": ["satb"]}))


def test_unit_and_field_errors(tmp_path):
    p = tmp_path / "m.txt"
    p.write_text("pursuer " + " ".join(_f(x) for x in [*(RP * 1000), *VP]) + "\n"
                 + "evader " + " ".join(_f(x) for x in [*RE, *VE]) + "\n")
    with pytest.raises(StateImportError, match="公尺"):
        read_official_state(p)
    p.write_text("pursuer " + " ".join(_f(x) for x in [*RP, *(VP * 1000)]) + "\n"
                 + "evader " + " ".join(_f(x) for x in [*RE, *VE]) + "\n")
    with pytest.raises(StateImportError, match="m/s"):
        read_official_state(p)
    p.write_text("pursuer " + " ".join(_f(x) for x in [*RP, *VP][:5]) + "\n"
                 + "evader " + " ".join(_f(x) for x in [*RE, *VE]) + "\n")
    with pytest.raises(StateImportError):
        read_official_state(p)
    p.write_text("pursuer " + " ".join(_f(x) for x in [*RP, *VP]) + " abc\n"
                 + "evader " + " ".join(_f(x) for x in [*RE, *VE]) + "\n")
    with pytest.raises(StateImportError):
        read_official_state(p)


def test_manual_entry_retries_bad_input():
    answers = iter(["abc", *(_f(x) for x in [*RP, *VP]), "7000000", *(_f(x) for x in [*RE, *VE]), "y"])
    printed = []
    out = manual_entry(input_fn=lambda prompt="": next(answers), print_fn=lambda *a, **k: printed.append(a))
    _check(out)
    assert len(printed) > 2
