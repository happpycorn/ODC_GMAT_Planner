"""排位賽全攝動力學模型與 B 平面重瞄準（2026-10-19）的單元測試，不跑 GMAT。

- 預設（contest_prelim）產出的腳本跟 Master 6d2f134 逐位元相同（golden 檔由當時的
  script_generator 產生，見 tests/fixtures/golden_prelim_*.script）。
- ranking_full 腳本內容、GMAT 環境設定驗證、B 平面 DC 腳本結構。
- 密集報表後處理（Hermite 最近點）、B 平面基底。
- 重瞄準判定（用替身取代 GMAT）：通過、單棒/總 Δv 失格、DC 不收斂、Earth-safe、T_max。
- main.py 階段：失敗保留原方案不產繳交腳本、通過時產全攝動繳交腳本、--config 覆寫太空船參數、CLI 組合檢查。
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import odc.config.defaults as ref_defaults
import odc.pipeline.stages as ref_stages
import odc.search.optimizer as ref_optimizer
import odc.gmat.retarget as rt
from odc.config.gmat_env import DEFAULT_SPACECRAFT, resolve_gmat_env, validate_gmat_env
from odc.pipeline.artifacts import save_mission
from odc.runlog import setup
from odc.scoring.scorer import calculate_score
from odc.gmat.script_generator import full_perturbation_script, script_generator

FIX = ROOT / "tests" / "fixtures"
BURNS = [(0.1234567891, -0.02, 0.003), (0.2499999, 0.0, 0.0), (0.05, 0.01, -0.2)]
TIMES = [100.0, 500.123456, 300.0, 1234.5]
ORBIT_A = {"SMA": 7100.0, "ECC": 0.0, "INC": 28.6, "RAAN": 0.0, "AOP": 0.0, "TA": 358.0}
ORBIT_B = {"SMA": 7000.0, "ECC": 0.0005, "INC": 28.5, "RAAN": 0.0, "AOP": 0.0, "TA": 0.0}


def ranking_config(**strategy):
    cfg = copy.deepcopy(ref_defaults.DEFAULT_CONFIG)
    cfg["orbit_A"], cfg["orbit_B"] = dict(ORBIT_A), dict(ORBIT_B)
    cfg["rules"].update(MAX_DV_MPS=250.0, MAX_TOTAL_DV_MPS=3000.0)
    cfg["strategy"]["GRAVITY_DEGREE"] = 4
    cfg["strategy"].update(strategy)
    return cfg


class GeneratorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="odc-fm-")
        self.d = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def gen(self, *orbit, name, **kw):
        return Path(script_generator(*orbit, BURNS, TIMES, aim_point=(1.5, -2.25, 3.125),
                                     output_filename=name, output_dir=self.d, **kw)).read_bytes()

    def test_default_output_is_byte_identical_to_master(self):
        dc_orbit = (-50000.0, 1.2, 30.0, 0.0, 0.0, 230.0, 7000.0, 0.001, 0.0, 0.0, 0.0, 0.0)
        fx_orbit = (7100.0, 0.0, 120.0, 10.0, 0.0, 45.0, 6800.0, 0.0, 97.5, 0.0, 0.0, 0.0)
        dc = dict(max_dv=0.25, gravity_degree=4, model_scale=0.5)
        fx = dict(max_dv=1.5, gravity_degree=2, final_burn_fixed_vnb=(0.05, 0.01, -0.2), model_scale=2)
        golden_dc = (FIX / "golden_prelim_dc.script").read_bytes()
        golden_fx = (FIX / "golden_prelim_fixed.script").read_bytes()
        self.assertEqual(self.gen(*dc_orbit, name="a.txt", **dc), golden_dc)
        self.assertEqual(self.gen(*fx_orbit, name="b.txt", **fx), golden_fx)
        # main.py 一律傳 resolve_gmat_env(config)：設定沒寫 GMAT 欄位時也必須逐位元相同
        env = resolve_gmat_env(ref_defaults.DEFAULT_CONFIG)
        self.assertEqual(env["force_model"], "contest_prelim")
        self.assertEqual(self.gen(*dc_orbit, name="c.txt", **dc, **env), golden_dc)
        self.assertEqual(self.gen(*fx_orbit, name="d.txt", **fx, **env), golden_fx)
        # 明寫 contest_prelim + 等於預設值的太空船參數也一樣
        cfg = ranking_config(FORCE_MODEL="contest_prelim",
                             GMAT_SPACECRAFT={"DRY_MASS_KG": 850, "CD": 2.2, "CR": 1.8,
                                              "DRAG_AREA_M2": 6, "SRP_AREA_M2": 8},
                             GMAT_EPOCH="21545", GMAT_EPOCH_FORMAT="TAIModJulian")
        self.assertEqual(self.gen(*dc_orbit, name="e.txt", **dc, **resolve_gmat_env(cfg)), golden_dc)

    def test_ranking_full_script(self):
        cfg = ranking_config(FORCE_MODEL="ranking_full",
                             GMAT_SPACECRAFT={"DRY_MASS_KG": 123.5, "CD": 2.1, "CR": 1.3,
                                              "DRAG_AREA_M2": 2.25, "SRP_AREA_M2": 3.5},
                             GMAT_SPACECRAFT_A={"DRY_MASS_KG": 4000},
                             GMAT_EPOCH="09 Nov 2026 01:00:00.000", GMAT_EPOCH_FORMAT="UTCGregorian")
        txt = self.gen(*ORBIT_A.values(), *ORBIT_B.values(), name="r.txt", max_dv=0.25,
                       gravity_degree=4, final_burn_fixed_vnb=BURNS[-1], **resolve_gmat_env(cfg)).decode("ascii")
        for line in ("DefaultProp_ForceModel.GravityField.Earth.PotentialFile = 'EGM96.cof';",
                     "DefaultProp_ForceModel.GravityField.Earth.Degree = 20;",
                     "DefaultProp_ForceModel.GravityField.Earth.Order = 20;",
                     "DefaultProp_ForceModel.GravityField.Earth.TideModel = 'SolidAndPole';",
                     "DefaultProp_ForceModel.Drag.AtmosphereModel = NRLMSISE00;",
                     "DefaultProp_ForceModel.Drag.DragModel = 'Spherical';",
                     "DefaultProp_ForceModel.PointMasses = {Sun, Luna};",
                     "DefaultProp_ForceModel.SRP = On;",
                     "DefaultProp_ForceModel.RelativisticCorrection = On;",
                     "SC_Human.DryMass = 123.5;", "SC_Human.Cd = 2.1;", "SC_Human.Cr = 1.3;",
                     "SC_Human.DragArea = 2.25;", "SC_Human.SRPArea = 3.5;",
                     "SC_Alien.DryMass = 4000;", "SC_Alien.Cd = 2.1;",
                     "SC_Alien.DateFormat = UTCGregorian;", "SC_Human.Epoch = '09 Nov 2026 01:00:00.000';"):
            self.assertIn(line, txt)
        for gone in ("Drag = None;", "SRP = Off;", "JGM2.cof", "TideModel = 'None'"):
            self.assertNotIn(gone, txt)
        # 一般版（DC）也能產生；只是 main.py 會警告，不建議這樣用
        dc = self.gen(*ORBIT_A.values(), *ORBIT_B.values(), name="r2.txt", max_dv=0.25,
                      **resolve_gmat_env(cfg)).decode("ascii")
        self.assertIn("Target DC_Targeter;", dc)
        self.assertIn("EGM96.cof", dc)

    def test_spad_files(self):
        cfg = ranking_config(FORCE_MODEL="ranking_full",
                             GMAT_SPACECRAFT={"SPAD_DRAG_FILE": "/abs/sat.spo", "SPAD_SRP_FILE": "/abs/sat.spo"})
        txt = self.gen(*ORBIT_A.values(), *ORBIT_B.values(), name="s.txt", max_dv=0.25,
                       **resolve_gmat_env(cfg)).decode("ascii")
        self.assertIn("DefaultProp_ForceModel.Drag.DragModel = 'SPADFile';", txt)
        self.assertIn("DefaultProp_ForceModel.SRP.SRPModel = SPADFile;", txt)
        self.assertIn("SC_Alien.SPADDragFile = '/abs/sat.spo';", txt)
        self.assertIn("SC_Human.SPADSRPFile = '/abs/sat.spo';", txt)

    def test_env_validation(self):
        self.assertEqual(validate_gmat_env(ref_defaults.DEFAULT_CONFIG, []), [])
        bad = [
            dict(FORCE_MODEL="full"),
            dict(GMAT_SPACECRAFT={"DRY_MASS_KG": -1}),
            dict(GMAT_SPACECRAFT={"CD": "2.2"}),
            dict(GMAT_SPACECRAFT={"MASS": 100}),
            dict(GMAT_SPACECRAFT={"SPAD_DRAG_FILE": "rel/path.spo"}),
            dict(GMAT_SPACECRAFT={"SPAD_DRAG_FILE": "/a'b.spo"}),
            dict(GMAT_SPACECRAFT_A={"SPAD_SRP_FILE": "/only/A.spo"}),  # 兩艘共用 ForceModel
            dict(GMAT_SPACECRAFT=[1, 2]),
            dict(GMAT_EPOCH="21545';"),
            dict(GMAT_EPOCH=21545),
            dict(GMAT_EPOCH_FORMAT="JulianDate"),
        ]
        for strat in bad:
            with self.subTest(strat=strat), self.assertRaises(ValueError):
                resolve_gmat_env(ranking_config(**strat))
        env = resolve_gmat_env(ranking_config(GMAT_SPACECRAFT={"CD": 2.0}, GMAT_SPACECRAFT_A={"CD": 2.4}),
                               force_model="ranking_full")
        self.assertEqual((env["sc_B"]["CD"], env["sc_A"]["CD"], env["force_model"]), (2.0, 2.4, "ranking_full"))
        self.assertEqual(env["sc_B"]["DRY_MASS_KG"], DEFAULT_SPACECRAFT["DRY_MASS_KG"])
        # load_or_create_config 也會擋（不要等到產腳本才炸）
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.json"
            p.write_text(json.dumps(ranking_config(FORCE_MODEL="nope")))
            with self.assertRaises(SystemExit):
                ref_defaults.load_or_create_config(str(p))

    def test_bplane_dc_script(self):
        env = resolve_gmat_env(ranking_config(), force_model="ranking_full")
        basis = rt.bplane_basis([0.3, -1.2, 0.4])
        txt = full_perturbation_script(ORBIT_A, ORBIT_B, [list(b) for b in BURNS], TIMES, env,
                                       retarget_idx=1, bplane=basis, summary_path="/tmp/x.summary")
        lines = txt.splitlines()
        i_target = lines.index("Target DC {SolveMode = Solve, ExitMode = SaveAndContinue};")
        # Target 在第 1 棒之前的滑行之後、第 1 棒之前；只 Vary 第 1 棒
        self.assertTrue(lines[i_target - 1].startswith("Propagate Prop(SC_Alien, SC_Human) {SC_Alien.ElapsedSecs = 500.12346"))
        self.assertEqual(lines[i_target - 2], "Maneuver BurnB0(SC_Human);")
        varies = [ln for ln in lines if "Vary DC(" in ln]
        self.assertEqual(len(varies), 3)
        self.assertTrue(all("BurnB1.Element" in ln for ln in varies))
        self.assertIn("Lower = -2.0, Upper = 2.0", varies[0])
        achieves = [ln for ln in lines if "Achieve DC(" in ln]
        self.assertEqual([a.split("(")[1].split(" ")[0] for a in achieves], ["p1", "p2"])
        self.assertNotIn("Achieve DC(dX", txt)
        self.assertTrue(all("SC_Human.Earth.Altitude = 50" in ln for ln in lines if ln.startswith("Propagate")))
        self.assertIn("EGM96.cof", txt)
        self.assertIn("Report RS BurnB1.Element1 BurnB1.Element2 BurnB1.Element3 dX dY dZ;", txt)
        # 上下限要比原本分量大（1.5 km/s 的初賽棒）
        big = full_perturbation_script(ORBIT_A, ORBIT_B, [[1.8, 0, 0]], [10.0, 100.0], env,
                                       retarget_idx=0, bplane=basis, summary_path="/tmp/x.summary")
        self.assertIn("Lower = -2.3, Upper = 2.3", big)
        with self.assertRaises(ValueError):
            full_perturbation_script(ORBIT_A, ORBIT_B, BURNS, TIMES, env, report_path="relative.report")
        rep = full_perturbation_script(ORBIT_A, ORBIT_B, BURNS, TIMES, env, report_path="/tmp/a.report")
        self.assertNotIn("Target", rep)
        self.assertTrue(rep.rstrip().endswith("{SC_Alien.ElapsedSecs = 600.00000, SC_Human.Earth.Altitude = 50};"))


class AnalysisTest(unittest.TestCase):
    def test_bplane_basis(self):
        for v in ([0.3, -1.2, 0.4], [0.0, 0.0, 2.0], [1e-3, 0, 0]):
            e1, e2 = map(np.array, rt.bplane_basis(v))
            u = np.array(v) / np.linalg.norm(v)
            for a, b in ((e1, u), (e2, u), (e1, e2)):
                self.assertAlmostEqual(float(a @ b), 0.0, places=12)
            self.assertAlmostEqual(float(np.linalg.norm(e1)), 1.0, places=12)
            self.assertAlmostEqual(float(np.linalg.norm(e2)), 1.0, places=12)
        with self.assertRaises(ValueError):
            rt.bplane_basis([0.0, 0.0, 0.0])

    def test_analyze_dense_straight_line(self):
        # A 靜止於 (7000,0,0)，B 等速直線飛過：t=1234.5 s 時在 +Z 方向 2 km 處最接近
        v = np.array([0.0, 1.5, 0.0])
        t = np.concatenate([np.arange(0.0, 1200.0, 60.0), [1200.0, 1200.0], np.arange(1260.0, 1900.0, 60.0)])
        rows = []
        for ti in t:
            rA = np.array([7000.0, 0.0, 0.0])
            rB = rA + np.array([0.0, 0.0, 2.0]) + v * (ti - 1234.5)
            rows.append([ti, *rB, *v, *rA, 0.0, 0.0, 0.0])
        res = rt.analyze_dense(np.array(rows), t_plan=1200.0)
        self.assertAlmostEqual(res["d_min_km"], 2.0, places=6)
        self.assertAlmostEqual(res["t_cpa_sec"], 1234.5, delta=2e-3)
        self.assertAlmostEqual(res["d_at_plan_km"], math.hypot(2.0, 1.5 * 34.5), places=9)
        self.assertEqual(res["dv_rel_plan_kms"], v.tolist())
        self.assertFalse(res["stopped_early"])
        self.assertGreater(res["min_radius_before_intercept_km"], 7000.0)

    def test_read_dense_rows_skips_garbage(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "r.report"
            good = " ".join(["1.0"] * 13)
            p.write_text(f"header line\n{good}\n{' '.join(['nan'] * 13)}\n1 2 3\n{good}\n")
            self.assertEqual(rt.read_dense_rows(p).shape, (2, 13))


# ---------------------------------------------------------------- 判定（GMAT 替身）
def fake_runner(d_before=3.9, d_after=0.2, t_shift=1.5, dc_burn=None, converged=True,
                min_radius=6800.0, stopped=False):
    calls = []

    def replay(console, oa, ob, burns, times, env, folder, tag, deg):
        calls.append(("replay", tag, [list(b) for b in burns], list(times)))
        t_plan = sum(times)
        d = d_before if tag == "original_replay" else d_after
        return {"tag": tag, "d_min_km": d, "t_cpa_sec": t_plan + (0.0 if tag == "original_replay" else t_shift),
                "t_plan_sec": t_plan, "d_at_plan_km": d, "dr_plan_km": [d, 0, 0],
                "dv_rel_plan_kms": [0.0, 2.0, 0.5], "min_radius_before_intercept_km": min_radius,
                "stopped_early": stopped, "n_rows": 10}

    def dc(console, oa, ob, burns, times, env, idx, basis, folder, tag, deg):
        calls.append(("dc", idx, [list(b) for b in burns]))
        out = {"tag": tag, "converged": converged, "iterations": 3}
        if converged:
            out.update(burn_kms=list(dc_burn if dc_burn is not None else
                                     [burns[idx][0] + 0.0012, burns[idx][1], burns[idx][2]]),
                       bplane_residual_km=[0.0, 0.0])
        else:
            out["error"] = "did not converge"
        return out
    return {"replay": replay, "dc": dc}, calls


class DecisionTest(unittest.TestCase):
    def setUp(self):
        self.opt = ref_optimizer.MissionOptimizer(ranking_config())
        self.burns = [[0.2, 0.0, 0.0], [0.1, 0.01, 0.0]]
        self.times = [300.0, 400.0, 2500.0]

    def decide(self, runner, idx=-1, **over):
        kw = dict(config=ranking_config(), burns=self.burns, times=self.times, idx=idx,
                  env=resolve_gmat_env(ranking_config(), force_model="ranking_full"),
                  console="/nonexistent", folder="/tmp/unused", max_dv_mps=250.0,
                  min_interval_sec=100.0, max_total_dv_mps=3000.0, t_max_sec=self.opt.T_max,
                  min_radius_km=self.opt.MIN_PERIAPSIS, score_fn=self.opt.legality_fields,
                  runner=runner)
        kw.update(over)
        return rt.retarget_full_perturbation(**kw)

    def test_accept_shifts_final_coast_to_cpa(self):
        runner, calls = fake_runner(t_shift=-3.25)
        res = self.decide(runner)
        self.assertTrue(res["accepted"], res["reasons"])
        self.assertEqual(res["retarget_idx"], 1)
        self.assertEqual([c[0] for c in calls], ["replay", "dc", "replay"])
        r = res["retargeted"]
        self.assertEqual(r["times"], [300.0, 400.0, 2496.75])
        self.assertAlmostEqual(r["t_team_sec"], 3196.75)
        self.assertEqual(r["burns"][0], [0.2, 0.0, 0.0])
        self.assertAlmostEqual(r["burns"][1][0], 0.1012)
        self.assertAlmostEqual(r["burn_change"]["vector_change_mps"], 1.2, places=6)
        leg = r["legality"]
        self.assertFalse(leg["disqualified"])
        expect = calculate_score(0.2, 3196.75, leg["total_dv_mps"], 0, self.opt.k_t, self.opt.C_t,
                                 self.opt.k_v, self.opt.C_v)
        self.assertAlmostEqual(leg["official_score"], expect, places=9)
        # 第二次重播用的是 DC 改過的棒、原本的滑行時間
        self.assertAlmostEqual(calls[2][2][1][0], 0.1012)
        self.assertEqual(calls[2][3], self.times)

    def test_explicit_burn_index(self):
        runner, calls = fake_runner()
        res = self.decide(runner, idx=0)
        self.assertTrue(res["accepted"])
        self.assertEqual(calls[1][1], 0)
        with self.assertRaises(ValueError):
            self.decide(fake_runner()[0], idx=2)

    def test_single_burn_over_cap_is_rejected(self):
        # DC 給的值本身 250.0000099993 m/s（合法），但寫進腳本的 7 位小數四捨五入後是
        # 250.0000774 m/s > 250 + 1e-5：判定要看真正寫出去的值
        burn = [0.17677665, 0.17677675473439383, 0.0]
        self.assertLessEqual(math.hypot(*burn) * 1000.0, 250.00001)
        runner, _ = fake_runner(dc_burn=burn)
        res = self.decide(runner)
        self.assertFalse(res["accepted"])
        self.assertTrue(any("失格" in r and "單棒" in r for r in res["reasons"]), res["reasons"])
        self.assertTrue(res["retargeted"]["legality"]["disqualified"])
        self.assertIsNone(res["retargeted"]["legality"]["official_score"])

    def test_total_dv_over_cap_is_rejected(self):
        res = self.decide(fake_runner()[0], max_total_dv_mps=300.0)
        self.assertFalse(res["accepted"])
        self.assertTrue(any("總 Δv" in r for r in res["reasons"]), res["reasons"])

    def test_dc_not_converged(self):
        res = self.decide(fake_runner(converged=False)[0])
        self.assertFalse(res["accepted"])
        self.assertNotIn("retargeted", res)
        self.assertTrue(any("沒有收斂" in r for r in res["reasons"]))

    def test_miss_earth_and_tmax(self):
        res = self.decide(fake_runner(d_after=5.2)[0])
        self.assertFalse(res["accepted"])
        self.assertTrue(any("d_min" in r for r in res["reasons"]))
        res = self.decide(fake_runner(min_radius=6400.0)[0])
        self.assertFalse(res["accepted"])
        self.assertTrue(any("Earth-safe" in r for r in res["reasons"]))
        res = self.decide(fake_runner(stopped=True)[0])
        self.assertFalse(res["accepted"])
        res = self.decide(fake_runner(t_shift=5.0)[0], t_max_sec=3201.0)
        self.assertFalse(res["accepted"])
        self.assertTrue(any("T_max" in r for r in res["reasons"]))

    def test_interval_penalty_is_reported_not_disqualifying(self):
        res = self.decide(fake_runner()[0], min_interval_sec=500.0)
        self.assertTrue(res["accepted"], res["reasons"])
        self.assertEqual(res["retargeted"]["legality"]["penalty_count"], 1)

    def test_replay_failure(self):
        runner, _ = fake_runner()
        runner["replay"] = lambda *a: {"tag": a[7], "error": "GMAT exploded\nlast line"}
        res = self.decide(runner)
        self.assertFalse(res["accepted"])
        self.assertIn("last line", res["reasons"][0])


# ---------------------------------------------------------------- main.py 階段
class StageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="odc-retarget-")
        self.root = Path(self.tmp.name)
        self.config = ranking_config()
        opt = ref_optimizer.MissionOptimizer(self.config)
        self.burns = [(0.021482683192711106, 0.008781615388229944, 0.15137998610769107)]
        self.times = [300.0, 2900.0]
        self.mi = {"x": [300.0, 0.0, 0.0, 0.0, 0.0], "num_burns": 1,
                   "score": float(calculate_score(3.5, 3200.0, 153.15, 0, opt.k_t, opt.C_t, opt.k_v, opt.C_v)),
                   "miss_km": 3.5, "total_dv_mps": 153.15, "T_team": 3200.0, "penalty_count": 0,
                   "over_dv_count": 0, "disqualified": False, "dq_reasons": [], "dc_converged": True,
                   "earth_safe": True, "aim_point": [-6931.16, -1282.87, -709.14],
                   "final_burn_dv_mps": 153.15, "min_arc_radius_km": 7000.0}
        self.snapshot = self.root / "src_run" / "mission.json"
        save_mission(self.snapshot, self.config, self.burns, self.times, self.mi)
        self.snapshot_sha = hashlib.sha256(self.snapshot.read_bytes()).hexdigest()

    def tearDown(self):
        setup()
        self.tmp.cleanup()

    def run_main(self, name, *extra, runner=None, verify=None):
        runner = runner or fake_runner()[0]
        folder = self.root / name
        with patch.object(rt, "replay", runner["replay"]), patch.object(rt, "run_bplane_dc", runner["dc"]), \
                patch.object(ref_stages, "run_gmat_verification", verify or self.fake_verify):
            ref_stages.main(["--from-mission", str(self.snapshot), "--retarget-full-perturbation",
                      "--gmat-console", "/nonexistent/GmatConsole", "--run-dir", str(folder), *extra])
        return folder

    @staticmethod
    def fake_verify(console, script_path, artifacts_dir=None):
        return {"intercept_success": True, "final_burn_legal": True, "miss_km": 0.2,
                "t_team_sec": 3201.5, "final_burn_dv_mps": 154.0, "targeter_converged": False,
                "report_path": "x", "final_burn_vnb": (0, 0, 0),
                "earth_safe": True, "checks_passed": True}

    def test_accept_writes_ranking_full_submission(self):
        folder = self.run_main("ok")
        rec = json.loads((folder / "retarget.json").read_text())
        self.assertEqual(rec["status"], "accepted")
        sub = (folder / "output_submit.txt").read_text()
        self.assertIn("PotentialFile = 'EGM96.cof'", sub)
        self.assertIn("BurnB0.Element1 = 0.0226827;", sub)   # DC 改過的值（+1.2 m/s），7 位小數
        self.assertIn("{SC_Alien.ElapsedSecs = 2901.50000}", sub)  # 最後一段停在最近點
        self.assertNotIn("Target DC_Targeter", sub)
        run = json.loads((folder / "run.json").read_text())
        self.assertEqual((run["status"], run["last_stage"], run["checks_passed"]), ("completed", "retarget", True))
        self.assertEqual(hashlib.sha256(self.snapshot.read_bytes()).hexdigest(), self.snapshot_sha)
        self.assertEqual(rec["gmat_env"]["force_model"], "ranking_full")

    def test_reject_keeps_original_and_writes_no_submission(self):
        runner, _ = fake_runner(dc_burn=[0.26, 0.0, 0.0])
        folder = self.run_main("dq", runner=runner)
        self.assertIn("保留原方案", (folder / "run.log").read_text(encoding="utf-8"))
        rec = json.loads((folder / "retarget.json").read_text())
        self.assertEqual(rec["status"], "rejected")
        self.assertIsNone(rec["submission_script"])
        self.assertFalse((folder / "output_submit.txt").exists())
        self.assertFalse(json.loads((folder / "run.json").read_text())["checks_passed"])
        self.assertEqual(hashlib.sha256(self.snapshot.read_bytes()).hexdigest(), self.snapshot_sha)

    def test_failed_fixed_verification_rejects(self):
        def bad_verify(console, script_path, artifacts_dir=None):
            return dict(self.fake_verify(console, script_path), intercept_success=False, miss_km=6.0,
                        checks_passed=False)
        folder = self.run_main("fixedfail", verify=bad_verify)
        rec = json.loads((folder / "retarget.json").read_text())
        self.assertEqual(rec["status"], "rejected")
        self.assertFalse((folder / "output_submit.txt").exists())
        self.assertTrue((folder / "output_submit_REJECTED.txt").exists())

    def test_config_overrides_spacecraft(self):
        local = ranking_config(GMAT_SPACECRAFT={"DRY_MASS_KG": 321.0}, GMAT_EPOCH="27000",
                               FORCE_MODEL="contest_prelim")
        cfg_path = self.root / "local.json"
        cfg_path.write_text(json.dumps(local))
        folder = self.run_main("override", "--config", str(cfg_path))
        rec = json.loads((folder / "retarget.json").read_text())
        self.assertEqual(rec["gmat_env"]["sc_B"]["DRY_MASS_KG"], 321.0)
        self.assertEqual(rec["gmat_env"]["epoch"], "27000")
        self.assertEqual(rec["gmat_env"]["force_model"], "ranking_full")  # 開關不能被蓋掉
        self.assertIn("SC_Human.DryMass = 321;", (folder / "output_submit.txt").read_text())

    def test_gmat_unavailable_marks_verification_failed(self):
        runner, _ = fake_runner()
        runner["replay"] = lambda *a: {"tag": a[7], "error": "找不到 GmatConsole"}
        folder = self.run_main("nogmat", runner=runner)
        run = json.loads((folder / "run.json").read_text())
        self.assertEqual((run["verification_status"], run["checks_passed"]), ("failed", False))
        self.assertEqual(json.loads((folder / "retarget.json").read_text())["status"], "rejected")

    def test_cli_combinations(self):
        bad = [["--retarget-full-perturbation"],
               ["--from-mission", "m.json", "--retarget-burn", "1"],
               ["--from-mission", "m.json", "--retarget-full-perturbation", "--no-gmat"],
               ["--from-mission", "m.json", "--retarget-full-perturbation", "--stop-after", "export"],
               ["--from-winner", "w.json", "--retarget-full-perturbation"]]
        for argv in bad:
            with self.subTest(argv=argv), self.assertRaises(SystemExit), \
                    patch("sys.stderr"):
                ref_stages.parse_args(argv)
        args = ref_stages.parse_args(["--from-mission", "m.json", "--retarget-full-perturbation"])
        self.assertEqual(args.retarget_burn, -1)


if __name__ == "__main__":
    unittest.main()
