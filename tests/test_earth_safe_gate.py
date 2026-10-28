"""Submission radius gate, nonbound perigees, and the initial waiting arc."""
import copy
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import main as app
from src.burn_splitter import _osc_perigee, _arc_min_radius, _simulate_free, _simulate_free_reuse
from src.core_math import (fast_norm, reaches_perigee, propagate_dop853,
                           initial_wait_min_radius, arc_radius_from_end)
from src.earth_gate import analyze_radius_report, MIN_PERIAPSIS
from src.optimizer import MissionOptimizer, fast_fitness_evaluator
from src.script_generator import script_generator
from src.scorer import calculate_score

MU, RE = 398600.4418, 6378.137


def conic(rp, e, nu):
    p = rp*(1+e)
    c, s = math.cos(nu), math.sin(nu)
    rr = p/(1+e*c)
    return np.array([rr*c, rr*s, 0.]), math.sqrt(MU/p)*np.array([-s, e+c, 0.])


class EarthGateTests(unittest.TestCase):
    def test_fixed_submission_uses_gmat_radius_after_dc_correction(self):
        cfg = copy.deepcopy(app.DEFAULT_CONFIG)
        cfg["strategy"]["GRAVITY_DEGREE"] = 0
        opt = MissionOptimizer(cfg)
        mi = {"x": [100., .2, 0., 0., 0.], "num_burns": 1,
              "score": float(calculate_score(.1, 1100., 100., 0, opt.k_t, opt.C_t, opt.k_v, opt.C_v)),
              "miss_km": .1, "total_dv_mps": 100., "T_team": 1100., "penalty_count": 0,
              "dc_converged": True, "earth_safe": True, "aim_point": [9000., 0., 0.],
              "final_burn_dv_mps": 100., "min_arc_radius_km": 7500.}
        with tempfile.TemporaryDirectory(prefix="odc-earth-output-") as tmp:
            folder = Path(tmp)

            def fake(command, **kwargs):
                txt = Path(command[-1]).read_text()
                report = re.search(r"Report_Intercept.Filename = '([^']+)';", txt)[1]
                radius = re.search(r"EarthGate.Filename = '([^']+)';", txt)[1]
                Path(report).write_text("t miss hit dv legal v n b\n1100 .1 1 100 1 .09 .01 0\n")
                r = 7500. if "Target DC_Targeter" in txt else 6400.
                Path(radius).write_text(f"0 {r} 0 0 0 0 0\n1100 {r} 0 0 0 0 0\n")
                return subprocess.CompletedProcess(command, 0, "The Targeter converged!", "")

            manifest = {"timings_sec": {}}
            with patch.object(app.subprocess, "run", side_effect=fake), self.assertLogs("odc", level="INFO") as logs:
                app.run_output_stage(cfg, [(0.1, 0., 0.)], [100., 1000.], mi, opt,
                    args=app.parse_args([]), run_dir=folder, gmat_console_path=sys.executable, manifest=manifest)
            self.assertTrue(manifest["verification"]["dc"]["earth_safe"])
            self.assertFalse(manifest["verification"]["fixed"]["checks_passed"])
            self.assertIn("BurnB0.Element1 = 0.0900000;", (folder/"output_submit.txt").read_text())
            self.assertTrue(any("不可繳交" in message for message in logs.output))
            self.assertFalse(any("可以直接繳交" in message for message in logs.output))

    @unittest.skipUnless(Path(app.GMAT_CONSOLE_DEFAULT).is_file() and
                         (ROOT/"outputs/runs/macbench-rt/output_submit.txt").is_file(),
                         "需要本機 GMAT 與 macbench-rt 提交腳本")
    def test_real_gmat_verify_script(self):
        source = ROOT/"outputs/runs/macbench-rt/output_submit.txt"
        before = source.read_bytes()
        with tempfile.TemporaryDirectory(prefix="odc-earth-gmat-") as tmp:
            folder = Path(tmp)/"run"
            proc = subprocess.run([sys.executable, str(ROOT/"main.py"), "--verify-script", str(source),
                "--gmat-console", app.GMAT_CONSOLE_DEFAULT, "--run-dir", str(folder)],
                cwd=ROOT, capture_output=True, text=True, timeout=150.)
            self.assertEqual(proc.returncode, 0, proc.stdout+proc.stderr)
            evidence = json.loads((folder/"gmat/verification.json").read_text())
            self.assertTrue(evidence["checks_passed"], proc.stdout+proc.stderr)
            self.assertIn("最低半徑", proc.stdout)
            self.assertGreater(evidence["result"]["min_radius_before_intercept_km"], MIN_PERIAPSIS)
        self.assertEqual(before, source.read_bytes())

    def test_nonbound_inward_outward_and_short_arcs(self):
        for e in (1., 1.000000001, 1.5, 3.):
            r, v = conic(6000., e, -0.9)
            self.assertAlmostEqual(_osc_perigee(r, v, MU), 6000., places=8)
            self.assertTrue(reaches_perigee(r, v, MU, 5000.))
            self.assertAlmostEqual(_arc_min_radius(r, v, 5000., MU, 0., 0., 0., RE), 6000., places=8)
            self.assertFalse(reaches_perigee(r, v, MU, 1.))
            rend, _ = propagate_dop853(r, v, 1., 60., MU, 0., 0., 0., RE)
            self.assertEqual(_arc_min_radius(r, v, 1., MU, 0., 0., 0., RE), fast_norm(rend))
            r, v = conic(6000., e, 0.9)
            self.assertEqual(_osc_perigee(r, v, MU), fast_norm(r))
            self.assertEqual(_arc_min_radius(r, v, 5000., MU, 0., 0., 0., RE), fast_norm(r))
        r, v = conic(6000., 1.5, -0.9)
        xf = np.array([0., 5000., 0., 0., 0.])
        args = (MU, 0., 0., 0., RE, r, v, r, v)
        a, b = _simulate_free(xf, 1, *args), _simulate_free_reuse(xf, 1, *args)
        self.assertAlmostEqual(a["arc_minr"][0], 6000., places=8)
        self.assertTrue(all(np.array_equal(a[k], b[k]) for k in a))
        # Around escape energy and radial states, SLSQP must see finite values.
        for vr in (-1., 0., 1.):
            r = np.array([9000., 0., 0.])
            for delta in (-1e-10, 0., 1e-10):
                v = np.array([vr, math.sqrt(2*MU/9000.-vr*vr)*(1+delta), 0.])
                self.assertTrue(math.isfinite(_osc_perigee(r, v, MU)))

    def test_bound_results_bitwise_unchanged(self):
        # Exact former implementation, including its operation order.
        def old(r, v):
            rr = fast_norm(r)
            energy = fast_norm(v)**2 / 2. - MU/rr
            a = -MU/(2.*energy)
            ev = ((fast_norm(v)**2 - MU/rr)*r - np.dot(r, v)*v)/MU
            return a*(1.-fast_norm(ev))
        for e in (0., .1, .5, .9):
            for nu in np.linspace(-math.pi, math.pi, 25):
                r, v = conic(6800., e, nu)
                want = old(r, v)
                self.assertEqual(np.float64(_osc_perigee(r, v, MU)).tobytes(), np.float64(want).tobytes())
                for dt in (1., 100., 10000.):
                    if reaches_perigee(r, v, MU, dt):
                        expected = want
                    else:
                        rend, _ = propagate_dop853(r, v, dt, 60., MU, 0., 0., 0., RE)
                        expected = min(fast_norm(r), fast_norm(rend))
                    self.assertEqual(np.float64(_arc_min_radius(r, v, dt, MU, 0., 0., 0., RE)).tobytes(),
                                     np.float64(expected).tobytes())

    def test_wait_arc_search_replay_and_splitter(self):
        cfg = copy.deepcopy(app.DEFAULT_CONFIG)
        cfg["strategy"].update(GRAVITY_DEGREE=0, LAMBERT_MAX_REVS=0)
        cfg["orbit_B"].update(SMA=7400., ECC=1000./7400., TA=180.)  # rp=6400, ra=8400
        cfg["rules"]["MAX_TOTAL_DV_MPS"] = 3000.
        wait = 2*math.pi*math.sqrt(7400.**3/MU)
        x = np.array([wait, .2, 0., 0., 0.])
        for enabled in (True, False):
            cfg["strategy"]["EPHEM_CACHE"] = enabled
            opt = MissionOptimizer(cfg)
            rend, _ = opt.state_B(wait)
            radius = initial_wait_min_radius(opt.B_r0, opt.B_v0, wait, rend, MU, opt.ephem)
            self.assertAlmostEqual(radius, 6400., places=5)
            # Partial last interval cannot consume a future interval's minimum.
            for t in (0., 1., 59.9, 60., 60.1, wait):
                r_end, _ = opt.state_B(t)
                got = initial_wait_min_radius(opt.B_r0, opt.B_v0, t, r_end, MU, opt.ephem)
                want = arc_radius_from_end(opt.B_r0, opt.B_v0, t, r_end, MU)
                self.assertAlmostEqual(got, want, places=5)
            fit = fast_fitness_evaluator(x, 1, opt._scalar_params(), opt._vector_params())
            self.assertGreater(fit, 0.)  # ranked failure, before attempting Lambert
            metrics = opt.mission_metrics(x, 1)
            self.assertFalse(metrics["earth_safe"])
            self.assertLess(metrics["min_arc_radius_km"], MIN_PERIAPSIS)
            _, _, replay = opt._replay_mission(x, 1)
            self.assertFalse(replay["earth_safe"])
            xf = np.array([wait, 100., 0., 0., 0.])
            args = (MU, 0., 0., 0., RE, opt.A_r0, opt.A_v0, opt.B_r0, opt.B_v0)
            a, b = (_simulate_free(xf, 1, *args, ephem=opt.ephem),
                    _simulate_free_reuse(xf, 1, *args, ephem=opt.ephem))
            self.assertTrue(all(np.array_equal(a[k], b[k]) for k in a))
            self.assertLess(a["arc_minr"].min(), MIN_PERIAPSIS-1e-3)
            self.assertGreater(a["arc_minr"][0], MIN_PERIAPSIS)  # only waiting arc unsafe

    def test_verification_gate_preserves_source_and_checks_exact_cutoff(self):
        with tempfile.TemporaryDirectory(prefix="odc-earth-") as tmp:
            root = Path(tmp)
            cfg = app.DEFAULT_CONFIG
            a, b = cfg["orbit_A"], cfg["orbit_B"]
            script = Path(script_generator(*a.values(), *b.values(), [(0., 0., 0.)], [0., 60.],
                [9000., 0., 0.], final_burn_fixed_vnb=(0., 0., 0.), output_dir=root))
            original = script.read_bytes()

            def fake(command, **kwargs):
                txt = Path(command[-1]).read_text()
                intercept = re.search(r"Report_Intercept.Filename = '([^']+)';", txt)[1]
                radius = re.search(r"EarthGate.Filename = '([^']+)';", txt)[1]
                Path(intercept).write_text("t miss hit dv legal v n b\n60 .1 1 0 1 0 0 0\n")
                # Endpoints safe, trajectory dips to 6000 km at t=30 s.
                Path(radius).write_text("0 7000 0 0 -66.66666666666667 0 0\n"
                                        "60 7000 0 0 66.66666666666667 0 0\n")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch.object(app.subprocess, "run", side_effect=fake):
                result = app.run_gmat_verification(sys.executable, script, artifacts_dir=root/"verify")
            self.assertTrue(result["intercept_success"])
            self.assertFalse(result["checks_passed"])
            self.assertAlmostEqual(result["min_radius_before_intercept_km"], 6000.)
            self.assertAlmostEqual(result["min_radius_time_sec"], 30.)
            self.assertEqual(script.read_bytes(), original)
            evidence = json.loads((root/"verify/verification.json").read_text())
            self.assertFalse(evidence["checks_passed"])
            self.assertEqual(evidence["result"]["min_periapsis_km"], MIN_PERIAPSIS)
            radius = root/"verify/GMAT_RadiusReport.txt"
            # A descending segment whose minimum is precisely the fractional cutoff.
            radius.write_text("0 7000 0 0 -1 0 0\n60 6940 0 0 -1 0 0\n")
            got = analyze_radius_report(radius, 30.12345)
            self.assertAlmostEqual(got["min_radius_time_sec"], 30.12345)
            self.assertAlmostEqual(got["min_radius_before_intercept_km"], 6969.87655)
            for r, safe in ((MIN_PERIAPSIS-.0009, True), (MIN_PERIAPSIS-.0011, False)):
                radius.write_text(f"0 {r} 0 0 0 0 0\n60 {r} 0 0 0 0 0\n")
                self.assertEqual(analyze_radius_report(radius, 60.)["earth_safe"], safe)
            radius.unlink()
            with patch.object(app, "_run_gmat_verification", return_value={
                "t_team_sec":60., "intercept_success":True, "final_burn_legal":True,
                "targeter_converged":True}):
                missing = app.run_gmat_verification(sys.executable, script, artifacts_dir=root/"missing")
            self.assertFalse(missing["checks_passed"])


if __name__ == "__main__":
    unittest.main()
