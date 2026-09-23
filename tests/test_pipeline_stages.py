"""Stage boundaries, snapshot integrity and isolated GMAT reports (no expensive search)."""
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main as app
from src.pipeline_artifacts import save_mission, load_mission, write_json, digest, create_run_dir
from src.runlog import setup
from src.scorer import calculate_score


class PipelineStagesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="odc-stages-")
        self.root = Path(self.tmp.name)
        self.config = copy.deepcopy(app.DEFAULT_CONFIG)
        self.config["strategy"]["GRAVITY_DEGREE"] = 0
        self.opt = app.MissionOptimizer(self.config)
        self.burns = [(0.1, 0.0, 0.0)]
        self.times = [100.0, 1000.0]
        self.mi = {
            "x": [100.0, 0.2, 0.0, 0.0, 0.0], "num_burns": 1,
            "score": float(calculate_score(0.1, 1100., 100., 0,
                                           self.opt.k_t, self.opt.C_t, self.opt.k_v, self.opt.C_v)),
            "miss_km": 0.1, "total_dv_mps": 100., "T_team": 1100.,
            "penalty_count": 0, "dc_converged": True, "earth_safe": True,
            "aim_point": [9000., 0., 0.], "final_burn_dv_mps": 100.,
            "min_arc_radius_km": 7500.,
        }
        self.snapshot = self.root / "mission.json"
        save_mission(self.snapshot, self.config, self.burns, self.times, self.mi)

    def tearDown(self):
        setup()  # close run.log handlers before removing temporary directories
        self.tmp.cleanup()

    def run_main(self, name, *args):
        folder = self.root / name
        app.main(["--run-dir", str(folder), *map(str, args)])
        return folder

    def test_snapshot_integrity_stage_and_physics_version(self):
        loaded = load_mission(self.snapshot)
        self.assertEqual(loaded["burns"], [list(b) for b in self.burns])
        self.assertEqual(loaded["times"], self.times)
        self.assertEqual(loaded["mission_info"], self.mi)
        modified = copy.deepcopy(loaded)
        modified["config"]["orbit_A"]["SMA"] += 1
        write_json(self.snapshot, modified)
        with self.assertRaisesRegex(ValueError, "雜湊"):
            load_mission(self.snapshot)
        modified = copy.deepcopy(loaded)
        modified["provenance"]["files"]["src/core_math.py"] = "old-version"
        modified["artifact_id"] = digest({k: v for k, v in modified.items() if k != "artifact_id"})
        write_json(self.snapshot, modified)
        with self.assertRaisesRegex(ValueError, "版本已變更"):
            load_mission(self.snapshot)
        write_json(self.snapshot, {"stage": "presplit", "schema_version": 1})
        with self.assertRaisesRegex(ValueError, "from-winner"):
            load_mission(self.snapshot)

    def test_from_mission_skips_all_solver_stages_and_preserves_script(self):
        cfg_path = self.root / "config.json"
        write_json(cfg_path, self.config)
        with patch.object(app, "run_seed_portfolio", return_value=(self.burns, self.times, self.mi, self.opt)):
            full = self.run_main("full", "--config", cfg_path, "--stop-after", "export")
        with patch.object(app, "run_seed_portfolio", side_effect=AssertionError("search reran")), \
             patch.object(app, "_legalize_stage", side_effect=AssertionError("split reran")), \
             patch.object(app, "primer_guided_research", side_effect=AssertionError("primer reran")), \
             patch.object(app, "load_or_create_config", side_effect=AssertionError("default config loaded")), \
             patch.object(app, "run_gmat_verification", side_effect=AssertionError("GMAT ran during export")):
            replay = self.run_main("replay", "--from-mission", full / "mission.json", "--stop-after", "export")
        self.assertEqual((full / "output.txt").read_bytes(), (replay / "output.txt").read_bytes())
        self.assertEqual(load_mission(replay / "mission.json")["mission_info"], self.mi)
        self.assertFalse((replay / "output_submit.txt").exists())
        manifest = json.loads((replay / "run.json").read_text())
        self.assertEqual(manifest["last_stage"], "export")
        self.assertEqual(manifest["source"]["artifact_id"], load_mission(full / "mission.json")["artifact_id"])

    def test_stop_after_solve_and_legacy_winner(self):
        old = self.root / "legacy.json"
        write_json(old, {"config": self.config, "burns": self.burns,
                         "times": self.times, "mission_info": self.mi})
        with patch.object(app, "run_seed_portfolio", side_effect=AssertionError("search reran")), \
             patch.object(app, "_legalize_stage", return_value=(self.burns, self.times, self.mi)) as split, \
             patch.object(app, "script_generator", side_effect=AssertionError("export ran")):
            folder = self.run_main("solve", "--from-winner", old, "--stop-after", "solve")
        split.assert_called_once()
        self.assertEqual(load_mission(folder / "mission.json")["times"], self.times)
        self.assertFalse((folder / "output.txt").exists())
        self.assertEqual(json.loads((folder / "run.json").read_text())["last_stage"], "solve")

    def test_portfolio_keeps_each_seed_snapshot(self):
        cfg = copy.deepcopy(self.config)
        cfg["strategy"]["SEED_PORTFOLIO_N"] = 2
        cfg["optimization"]["SEED"] = 10

        def search(config):
            return self.burns, self.times, self.mi, app.MissionOptimizer(config)

        with patch.object(app, "run_study_over_revs", side_effect=search), \
             patch.object(app, "primer_guided_research", return_value=None), \
             patch.object(app, "_legalize_stage", side_effect=lambda cfg, b, t, mi, opt: (b, t, mi)):
            app.run_seed_portfolio(cfg, output_dir=self.root)
        for seed in (10, 11):
            self.assertTrue((self.root / f"winner_presplit_seed{seed}.json").exists())
            self.assertEqual(load_mission(self.root / f"mission_seed{seed}.json")["config"]["optimization"]["SEED"], seed)

    def test_export_presentation_override_does_not_change_saved_solution(self):
        baseline = self.snapshot.read_bytes()
        folder = self.run_main("presentation", "--from-mission", self.snapshot,
                               "--stop-after", "export", "--model-scale", "0.8")
        self.assertIn("ModelScale = 0.8;", (folder / "output.txt").read_text())
        self.assertEqual(self.snapshot.read_bytes(), baseline)
        self.assertEqual(load_mission(folder / "mission.json")["config"], self.config)

    def test_existing_run_directory_is_not_overwritten(self):
        folder = create_run_dir(self.root / "existing")
        marker = folder / "keep.txt"
        marker.write_text("preserve me")
        with self.assertRaises(FileExistsError):
            self.run_main("existing", "--from-mission", self.snapshot)
        self.assertEqual(marker.read_text(), "preserve me")

    def fake_gmat(self, command, **kwargs):
        executed = Path(command[-1]).read_text()
        report = re.search(r"Report_Intercept.Filename = '([^']+)';", executed).group(1)
        Path(report).write_text("T miss hit dv legal v n b\n1100 0.1 1 100 1 0.09 0.01 0\n")
        return subprocess.CompletedProcess(command, 0, "The Targeter converged!", "")

    def test_verification_isolated_and_fixed_burn_uses_dc_result(self):
        with patch.object(app.subprocess, "run", side_effect=self.fake_gmat):
            folder = self.run_main("verified", "--from-mission", self.snapshot,
                                   "--gmat-console", sys.executable)
        dc = json.loads((folder / "gmat_dc" / "verification.json").read_text())
        fixed = json.loads((folder / "gmat_fixed" / "verification.json").read_text())
        self.assertNotEqual(dc["result"]["report_path"], fixed["result"]["report_path"])
        self.assertTrue(Path(dc["result"]["report_path"]).exists())
        self.assertTrue(Path(fixed["result"]["report_path"]).exists())
        fixed_text = (folder / "output_submit.txt").read_text()
        self.assertIn("BurnB0.Element1 = 0.0900000;", fixed_text)
        self.assertNotIn("Create DifferentialCorrector", fixed_text)
        original = (folder / "output_submit.txt").read_bytes()
        with patch.object(app.subprocess, "run", side_effect=self.fake_gmat), \
             patch.object(app, "run_seed_portfolio", side_effect=AssertionError("search reran")), \
             patch.object(app, "_legalize_stage", side_effect=AssertionError("split reran")), \
             patch.object(app, "script_generator", side_effect=AssertionError("script regenerated")):
            alone = self.run_main("verify-only", "--verify-script", folder / "output_submit.txt",
                                  "--gmat-console", sys.executable)
        self.assertEqual(original, (folder / "output_submit.txt").read_bytes())
        self.assertFalse((alone / "mission.json").exists())
        self.assertTrue((alone / "gmat" / "executed.script").exists())

    def test_failed_verification_keeps_failure_record_not_old_report(self):
        exported = self.run_main("exported", "--from-mission", self.snapshot, "--no-gmat")
        # Even exit=0 with no new report must fail; no shared GMAT output is consulted.
        with patch.object(app.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "no report", "")):
            with self.assertRaisesRegex(RuntimeError, "GMAT 執行失敗"):
                self.run_main("failed", "--verify-script", exported / "output.txt", "--gmat-console", sys.executable)
        record = json.loads((self.root / "failed" / "gmat" / "verification.json").read_text())
        self.assertEqual(record["status"], "failed")
        self.assertIsNone(record["result"])
        self.assertEqual(json.loads((self.root / "failed" / "run.json").read_text())["status"], "failed")

    def test_verify_only_requires_convergence_for_dc_but_not_fixed(self):
        with patch.object(app.subprocess, "run", side_effect=self.fake_gmat):
            exported = self.run_main("both-scripts", "--from-mission", self.snapshot,
                                     "--gmat-console", sys.executable)

        def without_convergence(command, **kwargs):
            result = self.fake_gmat(command, **kwargs)
            result.stdout = "No convergence message"
            return result

        for name, filename, expected in (("dc-check", "output.txt", False),
                                          ("fixed-check", "output_submit.txt", True)):
            with self.subTest(filename=filename), \
                 patch.object(app.subprocess, "run", side_effect=without_convergence):
                folder = self.run_main(name, "--verify-script", exported / filename,
                                       "--gmat-console", sys.executable)
            evidence = json.loads((folder / "gmat" / "verification.json").read_text())
            self.assertEqual(evidence["checks_passed"], expected)
            self.assertEqual(json.loads((folder / "run.json").read_text())["checks_passed"], expected)

    def test_unsafe_mission_cannot_produce_submission(self):
        self.mi["earth_safe"] = False
        save_mission(self.snapshot, self.config, self.burns, self.times, self.mi)
        with patch.object(app.subprocess, "run", side_effect=self.fake_gmat):
            folder = self.run_main("unsafe", "--from-mission", self.snapshot, "--gmat-console", sys.executable)
        self.assertTrue((folder / "output.txt").exists())
        self.assertFalse((folder / "output_submit.txt").exists())


if __name__ == "__main__":
    unittest.main()
