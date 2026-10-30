"""C2 fast 回歸；支援 pytest 或直接執行（run_regression.py 自動發現）。"""
import copy
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import odc.config.defaults as ref_defaults
import odc.pipeline.primer_stage as ref_primer_stage
import odc.search.optimizer as om
import odc.search.fitness as ref_search_fitness
import odc.search.revs as ref_search_revs
import odc.tools.sweep_params as sp
from odc.config.validator import ConfigValidationError, validate_config


def config():
    return copy.deepcopy(ref_defaults.DEFAULT_CONFIG)


def mission(score=80, split_score=None, n=2, x=None):
    return {"score": score, "score_split_est": score if split_score is None else split_score,
            "miss_km": 0.001, "total_dv_mps": 1000., "T_team": 10000.,
            "num_burns": n, "x": np.ones(4 * n + 1) if x is None else x}


def winner():
    return SimpleNamespace(T_max=40000., MIN_COAST_TIME=100., LAMBERT_MAX_REVS=0,
                           TIEBREAK_SCORE_EPS=1e-9, SPLIT_AWARE_TERMINAL=True)


PROFILE = {"verdict": "add-node", "max_peak": 1.5, "worst_arc": 0,
           "arcs": [{"kind": "inter-impulse", "p_peak_frac": 0.5}]}
SEED = np.ones(13)


class PrimerFastTests(unittest.TestCase):
    def test_validator_accepts_legal_values_and_defaults(self):
        cfg = config()
        before = copy.deepcopy(cfg)
        validate_config(cfg)
        self.assertEqual(cfg, before)  # 驗證不注入預設值、不改既有 full config。
        for mode in ("full", "fast"):
            for frac in (0.001, 0.33, 1):
                for wall in (None, 0, 0.01, 300):
                    cfg["strategy"].update(PRIMER_RESEARCH_MODE=mode,
                                           PRIMER_RESEARCH_ITER_FRAC=frac,
                                           PRIMER_RESEARCH_WALL_SEC=wall)
                    validate_config(cfg)

    def test_validator_rejects_invalid_types_and_ranges(self):
        invalid = {
            "PRIMER_RESEARCH_MODE": ["fas", "FAST", None, True, 1, []],
            "PRIMER_RESEARCH_ITER_FRAC": [0, -0.1, 1.01, None, True, "0.33", float("nan")],
            "PRIMER_RESEARCH_WALL_SEC": [-1, True, "300", [], float("inf")],
        }
        for field, values in invalid.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    cfg = config()
                    cfg["strategy"][field] = value
                    with self.assertRaisesRegex(ConfigValidationError, field):
                        validate_config(cfg)

    def test_full_passes_exact_legacy_config_and_seed(self):
        for mode in (None, "full"):
            with self.subTest(mode=mode):
                cfg = config()
                if mode is not None:
                    cfg["strategy"]["PRIMER_RESEARCH_MODE"] = mode
                before = copy.deepcopy(cfg)
                expected = copy.deepcopy(cfg)
                expected["strategy"]["SPLIT_AWARE_SEARCH"] = True
                expected["optimization"]["MAX_BURNS"] = [3]
                opt = winner()
                result = ([3], [4], mission(81, n=3), opt)
                with patch.object(ref_primer_stage, "_primer_diagnose_winner", return_value=PROFILE), \
                     patch.object(ref_primer_stage, "insert_node_seed", return_value=SEED), \
                     patch.object(ref_primer_stage, "MissionOptimizer", side_effect=AssertionError("local ran in full")), \
                     patch.object(ref_primer_stage, "run_study_over_revs", return_value=result) as run:
                    actual = ref_primer_stage.primer_guided_research(cfg, [1], [2], mission(), opt)
                    self.assertEqual(actual[:2], result[:2])
                    self.assertIs(actual[2], result[2])
                    self.assertIs(actual[3], result[3])
                self.assertEqual(run.call_args.args, (expected,))
                self.assertEqual(list(run.call_args.kwargs), ["external_seeds"])
                np.testing.assert_array_equal(run.call_args.kwargs["external_seeds"][3][0], SEED)
                self.assertEqual(cfg, before)

    def fast_call(self, old=None, local=None, glob=None, frac=None, budget=600):
        cfg = config()
        cfg["strategy"]["PRIMER_RESEARCH_MODE"] = "fast"
        if frac is not None:
            cfg["strategy"]["PRIMER_RESEARCH_ITER_FRAC"] = frac
        cfg["optimization"]["MAXITER"] = budget
        before = copy.deepcopy(cfg)
        local = mission(81, n=3, x=SEED * 2) if local is None else local
        glob = mission(82, n=3, x=SEED * 3) if glob is None else glob
        old = mission() if old is None else old
        local_opt = Mock()
        local_opt._generate_nlp_refined_seed_candidates.return_value = [SEED * 1.5]
        local_opt.refine_trajectory.return_value = ([3], [30], local)
        global_opt = winner()
        global_result = ([4], [40], glob, global_opt)
        # snapshot：cfg2 在 local 建構後才縮減代數，避免 mock 的參照掩蓋這件事。
        local_configs = []
        def make_local(c):
            local_configs.append(copy.deepcopy(c))
            return local_opt
        with patch.object(ref_primer_stage, "_primer_diagnose_winner", return_value=PROFILE), \
             patch.object(ref_primer_stage, "insert_node_seed", return_value=SEED), \
             patch.object(ref_primer_stage, "MissionOptimizer", side_effect=make_local), \
             patch.object(ref_primer_stage, "run_study_over_revs", return_value=global_result) as run, \
             patch.object(ref_primer_stage.log, "info") as info:
            result = ref_primer_stage.primer_guided_research(cfg, [1], [2], old, winner())
        self.assertEqual(cfg, before)
        return result, run, local_opt, local_configs[0], info

    def test_fast_reduces_iterations_inherits_revs_and_injects_local_x(self):
        result, run, local, local_cfg, info = self.fast_call()
        cfg2 = run.call_args.args[0]
        self.assertEqual(cfg2["optimization"]["MAXITER"], 198)
        self.assertEqual(local_cfg["optimization"]["MAXITER"], 600)
        for c in (cfg2, local_cfg):
            self.assertEqual(c["optimization"]["MAX_BURNS"], [3])
            self.assertTrue(c["strategy"]["SPLIT_AWARE_SEARCH"])
            self.assertFalse(c["strategy"]["REVS_ENSEMBLE"])
            self.assertEqual(c["strategy"]["LAMBERT_MAX_REVS"], 0)
        seeds = run.call_args.kwargs["external_seeds"][3]
        self.assertEqual(len(seeds), 2)
        np.testing.assert_array_equal(seeds[0], SEED)
        np.testing.assert_array_equal(seeds[1], SEED * 2)
        np.testing.assert_array_equal(local.refine_trajectory.call_args.args[0], SEED * 1.5)
        self.assertEqual(result[0], [4])
        self.assertIn("winner=global", info.call_args.args[0])
        self.assertIn("split_est=", info.call_args.args[0])

    def test_fast_minimum_and_per_burn_iteration_budgets(self):
        for budget, frac, expected in ((2, 0.01, 1), ({2: 600, 3: 100}, 0.5, {2: 300, 3: 50})):
            _, run, _, _, _ = self.fast_call(budget=budget, frac=frac)
            self.assertEqual(run.call_args.args[0]["optimization"]["MAXITER"], expected)

    def test_fast_selects_using_split_estimate_and_can_keep_original(self):
        result, _, _, _, _ = self.fast_call(old=mission(80, 90), local=mission(85, 89, n=3))
        self.assertIsNone(result)
        result, _, _, _, _ = self.fast_call(local=mission(79, 91, n=3))
        self.assertEqual(result[0], [3])

    def test_fast_failure_still_keeps_local_or_original(self):
        result, run, _, _, _ = self.fast_call(glob=False)
        self.assertEqual(result[0], [3])
        self.assertEqual(len(run.call_args.kwargs["external_seeds"][3]), 2)
        result, run, _, _, _ = self.fast_call(local=False, glob=False)
        self.assertIsNone(result)
        self.assertEqual(len(run.call_args.kwargs["external_seeds"][3]), 1)

    def test_no_add_node_or_disabled_does_not_search(self):
        for disabled in (True, False):
            cfg = config()
            cfg["strategy"].update(PRIMER_RESEARCH_MODE="fast", PRIMER_GUIDED_RESEARCH=not disabled)
            with patch.object(ref_primer_stage, "_primer_diagnose_winner", return_value={
                "verdict": "optimal-ish", "max_peak": 1.0}), \
                 patch.object(ref_primer_stage, "run_study_over_revs") as run:
                self.assertIsNone(ref_primer_stage.primer_guided_research(cfg, [1], [2], mission(), winner()))
                run.assert_not_called()

    def test_deadline_stops_real_mealpy_during_initialization_and_keeps_best(self):
        # 真正的 L-SHADE，小型假目標；每次評估讓 mock 時鐘前進一秒，不等待牆鐘。
        opt = om.MissionOptimizer.__new__(om.MissionOptimizer)
        opt._generate_bounds = lambda n: ([0.], [1.])
        opt.burns, opt.maxiter, opt.popsize, opt.num_threads = [3], 100, 1, 1
        opt.seed, opt.early_stop_enabled, opt.SEED_LBFGS_POLISH = 1, False, True
        opt._primer_fast_research, opt._primer_search_deadline = True, 5.
        opt.external_seeds = {3: [np.array([0.5])]}
        clock, seen = [0.], []
        def objective(x, *args):
            clock[0] += 1
            seen.append(np.array(x).copy())
            return -clock[0]
        with patch.object(om, "time", SimpleNamespace(monotonic=lambda: clock[0])), patch.object(ref_search_fitness, "time", SimpleNamespace(monotonic=lambda: clock[0])), \
             patch.object(om, "fast_fitness_evaluator", side_effect=objective), \
             patch.object(opt, "_generate_seed_candidates", side_effect=AssertionError("seed scan ran")):
            b, x, fitness, epochs, note = opt._optimize_burn_case(3, None, None)
        self.assertEqual((b, fitness, epochs), (3, -5., 0))
        self.assertEqual(len(seen), 5)
        np.testing.assert_array_equal(x, seen[-1])
        self.assertIn("牆鐘到期", note)

    def test_deadline_before_first_evaluation_returns_empty_candidate(self):
        opt = om.MissionOptimizer(config())
        opt._primer_fast_research, opt._primer_search_deadline = True, 0.
        opt.external_seeds = {1: [np.ones(5)]}
        with patch.object(om, "fast_fitness_evaluator", side_effect=AssertionError("expired evaluation ran")):
            _, x, fitness, epochs, note = opt._optimize_burn_case(1, None, None)
        self.assertIsNone(x)
        self.assertEqual(fitness, float("inf"))
        self.assertEqual(epochs, 0)
        self.assertIn("牆鐘到期", note)

    def test_native_mealpy_time_limit_stops_generations(self):
        opt = om.MissionOptimizer.__new__(om.MissionOptimizer)
        opt._generate_bounds = lambda n: ([0.], [1.])
        opt.burns, opt.maxiter, opt.popsize, opt.num_threads = [3], 100, 1, 1
        opt.seed, opt.early_stop_enabled, opt.SEED_LBFGS_POLISH = 1, False, True
        opt._primer_fast_research = True
        opt.external_seeds = {3: [np.array([0.5])]}
        opt._primer_search_deadline = time.monotonic() + 0.1
        def objective(x, *args):
            time.sleep(0.001)
            return float(x[0] ** 2 - 80)
        # Guard 時鐘保持在期限之前，讓 mealpy 的原生 max_time 獨立觸發。
        with patch.object(om, "time", SimpleNamespace(monotonic=lambda: opt._primer_search_deadline - 0.1)), patch.object(ref_search_fitness, "time", SimpleNamespace(monotonic=lambda: opt._primer_search_deadline - 0.1)), \
             patch.object(om, "fast_fitness_evaluator", side_effect=objective):
            _, x, fitness, epochs, _ = opt._optimize_burn_case(3, None, None)
        self.assertIsNotNone(x)
        self.assertLess(fitness, 0)
        self.assertGreater(epochs, 0)
        self.assertLess(epochs, 100)

    def test_run_study_over_revs_only_caps_external_fast_search(self):
        for mode, ext, wall, active in (("fast", None, 300, False),
                                        ("full", {3: [SEED]}, 300, False),
                                        ("fast", {3: [SEED]}, 300, True),
                                        ("fast", {3: [SEED]}, 0, True),
                                        ("fast", {3: [SEED]}, None, True)):
            cfg = config()
            cfg["strategy"].update(PRIMER_RESEARCH_MODE=mode, PRIMER_RESEARCH_WALL_SEC=wall,
                                   REVS_ENSEMBLE=False)
            cfg["optimization"]["SEED"] = None
            opt = SimpleNamespace(run_study=lambda: ([1], [2], mission()))
            with patch.object(ref_search_revs, "MissionOptimizer", return_value=opt), \
                 patch.object(ref_search_revs, "time", SimpleNamespace(monotonic=lambda: 10.)):
                ref_search_revs.run_study_over_revs(cfg, external_seeds=ext)
            self.assertEqual(getattr(opt, "_primer_fast_research", False), active)
            self.assertEqual(getattr(opt, "_primer_search_deadline", None), 310. if active and wall else None)

    def test_fast_run_study_replays_anytime_winner_without_final_nlp(self):
        opt = om.MissionOptimizer(config())
        opt._primer_fast_research = True
        opt.burns = [3]
        with patch.object(opt, "_optimize_burn_case", return_value=(3, SEED, -82, 4, "timeout")), \
             patch.object(opt, "_pick_best_case", return_value=(3, SEED, -82)), \
             patch.object(opt, "_replay_mission", return_value=([1], [2], mission())) as replay, \
             patch.object(opt, "refine_trajectory", side_effect=AssertionError("post-deadline NLP ran")):
            self.assertEqual(opt.run_study()[0], [1])
            self.assertEqual(replay.call_args.args[0].tobytes(), SEED.tobytes())

    def test_sweep_expands_exact_requested_jobs_and_valid_configs(self):
        spec = json.loads((ROOT / "sweeps/primer_fast_v1.json").read_text())
        jobs = sp.plan_jobs(spec)
        expected = {(sc, v, seed)
                    for sc, seeds in (("hyperbolic_smoke", [1, 2, 3]), ("hyper_far", [0, 2]))
                    for seed in seeds for v in ("full", "fast")}
        self.assertEqual({(j["scenario"], j["variant"], j["seed"]) for j in jobs}, expected)
        self.assertEqual(len(jobs), 10)
        for job in jobs:
            validate_config(sp.build_config(job))


if __name__ == "__main__":
    unittest.main(verbosity=2)
