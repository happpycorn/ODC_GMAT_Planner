"""GMAT 報表匯入（game/state_io.py）與 copilot import 子命令。"""
import json

import numpy as np
import pytest

import copilot
from game.state_io import StateImportError, apply_report_to_state, read_gmat_report
from physics import get_r0_v0

CART_HDR = ("ShipP.ElapsedSecs ShipP.EarthMJ2000Eq.X ShipP.EarthMJ2000Eq.Y ShipP.EarthMJ2000Eq.Z "
            "ShipP.EarthMJ2000Eq.VX ShipP.EarthMJ2000Eq.VY ShipP.EarthMJ2000Eq.VZ "
            "ShipE.EarthMJ2000Eq.X ShipE.EarthMJ2000Eq.Y ShipE.EarthMJ2000Eq.Z "
            "ShipE.EarthMJ2000Eq.VX ShipE.EarthMJ2000Eq.VY ShipE.EarthMJ2000Eq.VZ")


def _row(t, rp, vp, re, ve):
    return " ".join(f"{x:.10f}" for x in [t, *rp, *vp, *re, *ve])


def test_cartesian_report_roundtrip(tmp_path):
    rp, vp = get_r0_v0(7000.0, 0.001, 30.0, 10.0, 0.0, 5.0)
    re, ve = get_r0_v0(7050.0, 0.002, 30.5, 10.2, 0.0, 9.0)
    path = tmp_path / "rep.txt"
    path.write_text(CART_HDR + "\n" + _row(0.0, rp * 0.9, vp, re, ve) + "\n" + _row(1200.0, rp, vp, re, ve) + "\n")
    rec = read_gmat_report(path)
    st = apply_report_to_state(copilot.template_state(), rec, "ShipP", "ShipE")
    assert st["t_elapsed_sec"] == 1200.0
    g = copilot.game_from_state(st)
    assert np.allclose(g.r("pursuer"), rp, atol=1e-6) and np.allclose(g.v("evader"), ve, atol=1e-9)


def test_keplerian_report(tmp_path):
    hdr = ("ShipP.ElapsedSecs ShipP.Earth.SMA ShipP.Earth.ECC ShipP.EarthMJ2000Eq.INC ShipP.EarthMJ2000Eq.RAAN "
           "ShipP.EarthMJ2000Eq.AOP ShipP.Earth.TA ShipE.Earth.SMA ShipE.Earth.ECC ShipE.EarthMJ2000Eq.INC "
           "ShipE.EarthMJ2000Eq.RAAN ShipE.EarthMJ2000Eq.AOP ShipE.Earth.TA")
    path = tmp_path / "kep.txt"
    path.write_text(hdr + "\n300 6878 0 135 30 0 60 6978 0 45 0 0 0\n")
    st = apply_report_to_state(copilot.template_state(), read_gmat_report(path), "ShipP", "ShipE")
    assert st["pursuer"]["elements"]["inc"] == 135.0 and st["t_elapsed_sec"] == 300.0


def test_unit_traps_are_rejected(tmp_path):
    rp, vp = get_r0_v0(7000.0, 0.0, 30.0, 0.0, 0.0, 0.0)
    re, ve = get_r0_v0(7050.0, 0.0, 30.0, 0.0, 0.0, 5.0)
    path = tmp_path / "m.txt"
    path.write_text(CART_HDR + "\n" + _row(0.0, rp * 1000, vp, re, ve) + "\n")       # 位置寫成公尺
    with pytest.raises(StateImportError, match="公尺"):
        apply_report_to_state({}, read_gmat_report(path), "ShipP", "ShipE")
    path.write_text(CART_HDR + "\n" + _row(0.0, rp, vp * 1000, re, ve) + "\n")       # 速度寫成 m/s
    with pytest.raises(StateImportError, match="m/s"):
        apply_report_to_state({}, read_gmat_report(path), "ShipP", "ShipE")
    with pytest.raises(StateImportError, match="找不到"):
        apply_report_to_state({}, read_gmat_report(path), "Alien", "ShipE")


def test_copilot_import_command(tmp_path):
    rp, vp = get_r0_v0(7000.0, 0.001, 30.0, 10.0, 0.0, 5.0)
    re, ve = get_r0_v0(7050.0, 0.002, 30.5, 10.2, 0.0, 9.0)
    rep = tmp_path / "rep.txt"
    rep.write_text(CART_HDR + "\n" + _row(600.0, rp, vp, re, ve) + "\n")
    state = tmp_path / "state.json"
    copilot.main(["init", str(state)])
    assert copilot.main(["import", str(state), str(rep), "--pursuer-ship", "ShipP", "--evader-ship", "ShipE",
                         "--mover", "evader"]) == 0
    st = json.loads(state.read_text())
    assert st["t_elapsed_sec"] == 600.0 and st["mover"] == "evader"
    assert np.allclose(st["pursuer"]["r_km"], rp)
