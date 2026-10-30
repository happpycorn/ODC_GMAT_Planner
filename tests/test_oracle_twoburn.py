"""Oracle kernels, configuration, independent DE seeds and pipeline arbitration."""
import copy
import json
import os
from pathlib import Path
import pickle
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np
import numba

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import main as app
import src.optimizer as om
import src.oracle_twoburn as oracle
from src.oracle_worker import OracleJob, oracle_core_budget, _atomic_dump
from src.config_validator import ConfigValidationError, validate_config
from poliastro.core.propagation import vallado


def config(**st):
    cfg = copy.deepcopy(app.DEFAULT_CONFIG)
    cfg["strategy"].update(GRAVITY_DEGREE=0, EPHEM_CACHE=False,
                           PRIMER_GUIDED_RESEARCH=False, **st)
    cfg["optimization"]["SEED"] = 0
    return cfg


def candidate(cfg, score=80.):
    opt = SimpleNamespace(config=cfg, TIEBREAK_SCORE_EPS=1e-9)
    mi = dict(score=score, miss_km=.001, total_dv_mps=1000., T_team=10000.,
              num_burns=2, x=np.zeros(9), earth_safe=True, disqualified=False,
              penalty_count=0)
    return [(.1, 0., 0.), (.1, 0., 0.)], [100., 1000., 1000.], mi, opt


def entry(cfg, score=90.):
    c = candidate(cfg, score)
    route = dict(rank=0, t1=100., t2=1100., t3=2100., dv1=[.6, 0., 0.],
                 dv_mps=1000., est_score=80., M=0, structure="2-burn")
    return dict(route=route, x=np.zeros(9), N=2, candidate=c,
                presplit=c[:3], wall_sec=.1, elapsed_sec=.2)


class OracleTests(unittest.TestCase):
    def test_vallado_normal_bitwise(self):
        rng = np.random.default_rng(713)
        for _ in range(30):
            r = np.array([7000., 0., 0.]) + rng.normal(size=3) * 100
            v = np.array([0., 7.5, .1]) + rng.normal(size=3) * .2
            dt = float(rng.uniform(1, 8000))
            self.assertEqual(np.asarray(oracle.vallado_safe(398600.4418, r, v, dt, 350)).tobytes(),
                             np.asarray(vallado(398600.4418, r, v, dt, 350)).tobytes())

    def test_vallado_nonfinite_psi_timeout_guard(self):
        # Finite inputs deliberately overflow Newton's initial hyperbolic guess.
        code = ('import numpy as np; from src.oracle_twoburn import vallado_safe; '
                'r=vallado_safe(398600.4418,np.array([7000.,0.,0.]),'
                'np.array([1e150,0.,0.]),1e150,350); '
                'assert np.all(np.isnan(r)), r; print("NaN returned")')
        p = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True,
                           text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_route_roundtrip(self):
        opt = SimpleNamespace(T_max=40000., MIN_COAST_TIME=100.)
        for dv in (None, np.array([.6, -.03, .02]), np.zeros(3)):
            x, n = oracle.standard_x_from_route(opt, 4000., dv, 5200., 10800.)
            t0, dvs, coasts = oracle.route_from_standard_x(opt, x, n)
            self.assertEqual(t0, 4000.)
            self.assertAlmostEqual(t0 + sum(coasts), 10800.)
            if n == 2:
                np.testing.assert_allclose(dvs[0], dv, rtol=1e-15, atol=1e-16)
                self.assertAlmostEqual(t0 + coasts[0], 5200.)
            else:
                self.assertEqual(n, 1)
                np.testing.assert_array_equal(dvs[0], np.zeros(3))

    def test_small_grid_sort_dedupe_threads_and_deadline_batches(self):
        cfg = json.loads((ROOT / "configs/shared/hyperbolic_smoke.json").read_text())
        cfg["rules"].update(MAX_DV_MPS=250., MAX_TOTAL_DV_MPS=3000.)
        opt = om.MissionOptimizer(cfg)
        kwargs = dict(K=3, grid_div=10, maxev=30, refine_top=1, fine_div=2)
        old = numba.get_num_threads()
        try:
            numba.set_num_threads(1)
            first = oracle.run_twoburn_oracle(opt, **kwargs)
            numba.set_num_threads(min(2, numba.config.NUMBA_NUM_THREADS))
            second = oracle.run_twoburn_oracle(opt, **kwargs)
            batched = oracle.run_twoburn_oracle(opt, deadline=time.monotonic()+120, **kwargs)
        finally:
            numba.set_num_threads(old)
        self.assertEqual(len(first), 3)
        self.assertEqual(pickle.dumps(first), pickle.dumps(second))
        self.assertEqual(pickle.dumps(first), pickle.dumps(batched))
        self.assertEqual([r['rank'] for r in first], list(range(3)))
        keys = [(r['dv_mps'] > 3000, -r['est_score']) for r in first]
        self.assertEqual(keys, sorted(keys))
        h = opt.T_max / 10
        for i, a in enumerate(first):
            for b in first[i+1:]:
                self.assertTrue(abs(a['t1']-b['t1']) > h or abs(a['t3']-b['t3']) > h
                                or a['structure'] != b['structure'])
        self.assertEqual(oracle.run_twoburn_oracle(opt, deadline=0., **kwargs), [])

    def test_validator(self):
        invalid = {"ORACLE_TWOBURN": [1, "true", None],
                   "ORACLE_TWOBURN_SEED_DE": [0, "false", None],
                   "ORACLE_TWOBURN_K": [0, -1, 1.5, True, "10"],
                   "ORACLE_TWOBURN_GRID_DIV": [9, 1.5, True, "100"],
                   "ORACLE_TWOBURN_WALL_SEC": [0, -1, True, "600", float('nan'), float('inf')]}
        for k, values in invalid.items():
            for v in values:
                with self.subTest(key=k, value=v):
                    with self.assertRaisesRegex(ConfigValidationError, k):
                        validate_config(config(**{k: v}))
        with self.assertRaisesRegex(ConfigValidationError, 'SPLIT_LEADING'):
            validate_config(config(ORACLE_TWOBURN=True))
        cfg = config(ORACLE_TWOBURN=True, SPLIT_LEADING=True, ORACLE_TWOBURN_K=1,
                     ORACLE_TWOBURN_GRID_DIV=10, ORACLE_TWOBURN_WALL_SEC=.001,
                     SPLIT_AWARE_MAX_FACTOR=5)
        before = copy.deepcopy(cfg)
        validate_config(cfg)
        self.assertEqual(cfg, before)
        opt = om.MissionOptimizer(cfg)
        self.assertEqual(opt.LEADING_SPLIT_LIMIT, 5 * opt.MAX_DV)
        with patch('src.config_validator.log.warning') as warning:
            validate_config(config(ORACLE_TWOBURN_SEED_DE=True))
            warning.assert_called_once()

    def test_core_budget_matches_unified_pool(self):
        for cores in (1, 2, 8):
            for seed in (0, None):
                for high in (0, 4):
                    cfg = config(LAMBERT_MAX_REVS=high)
                    cfg['optimization'].update(SEED=seed, MAX_BURNS=[1, 2])
                    jobs = 2 * (2 if high else 1)
                    slots = min(jobs, max(1, cores if seed is not None else cores//2))
                    with patch('src.oracle_worker.os.cpu_count', return_value=cores):
                        self.assertEqual(oracle_core_budget(cfg), max(1, cores-slots))

    def test_disabled_does_not_start_oracle_or_add_artifact(self):
        cfg = config()
        c = candidate(cfg)
        with tempfile.TemporaryDirectory() as folder, \
             patch('src.oracle_worker.OracleJob', side_effect=AssertionError('oracle started')), \
             patch.object(app, '_search_stage', return_value=c), \
             patch.object(app, 'save_winner_checkpoint'), patch.object(app, 'save_mission'), \
             patch.object(app, '_legalize_stage', return_value=c[:3]), \
             patch.object(app, '_fallback_to_legal_backup', return_value=c):
            self.assertIs(app._solve_pipeline(cfg, folder)[3], c[3])
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_pipeline_winner_tie_unsafe_timeout_and_crash(self):
        cfg = config(ORACLE_TWOBURN=True, SPLIT_LEADING=True)
        for mode in ('better', 'tie', 'unsafe', 'timeout', 'crash', 'startup_crash'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as folder:
                de = candidate(cfg)
                e = entry(cfg, 80. if mode == 'tie' else 90.)
                if mode == 'unsafe':
                    e['candidate'][2]['earth_safe'] = False
                job = Mock()
                job.wall_sec = .2
                job.collect.return_value = ([e['route']], [] if mode == 'timeout' else [e])
                if mode == 'crash':
                    job.collect.side_effect = RuntimeError('worker crashed')
                with patch('src.oracle_worker.OracleJob', return_value=job,
                           side_effect=RuntimeError('spawn failed') if mode == 'startup_crash' else None), \
                     patch.object(app, '_solve_de_pipeline', return_value=de) as search, \
                     patch.object(app, 'save_winner_checkpoint'), patch.object(app, 'save_mission'):
                    result = app._solve_pipeline(cfg, folder)
                self.assertIs(result[3], e['candidate'][3] if mode == 'better' else de[3])
                search.assert_called_once()
                payload = json.loads((Path(folder)/'oracle_candidates_seed0.json').read_text())
                self.assertIn('routes', payload)

    def test_both_switches_share_grid_and_filter_burn_cases(self):
        cfg = config(ORACLE_TWOBURN=True, ORACLE_TWOBURN_SEED_DE=True, SPLIT_LEADING=True)
        cfg['optimization']['MAX_BURNS'] = [2]
        e = entry(cfg)
        single = dict(e['route'], dv1=None, rank=1, structure='1-burn')
        routes = [e['route'], single]
        jobs = [Mock(), Mock()]
        for job in jobs:
            job.wall_sec = .2
        jobs[0].collect.return_value = (routes, [])
        jobs[1].collect.return_value = (routes, [e])
        with tempfile.TemporaryDirectory() as folder, \
             patch('src.oracle_worker.OracleJob', side_effect=jobs) as start, \
             patch.object(app, '_solve_de_pipeline', return_value=candidate(cfg)) as search, \
             patch.object(app, 'save_winner_checkpoint'), patch.object(app, 'save_mission'):
            app._solve_pipeline(cfg, folder)
        self.assertEqual(start.call_count, 2)
        self.assertTrue(start.call_args_list[0].kwargs['grid_only'])
        self.assertIs(start.call_args_list[1].kwargs['routes'], routes)
        seeds = search.call_args.kwargs['oracle_seeds']
        self.assertEqual(list(seeds), [2])
        self.assertEqual(len(seeds[2]), 1)

    def test_seed_initial_population_front_clipped_no_primer_fast(self):
        for aware in (False, True):
            cfg = config(SPLIT_AWARE_SEARCH=aware, SPLIT_AWARE_MAX_FACTOR=5,
                         PRIMER_RESEARCH_MODE='fast')
            opt = om.MissionOptimizer(cfg)
            lb, ub = opt._generate_bounds(2)
            x = np.array(ub) * 2 + 1
            x[0] = -100.
            opt.oracle_seeds = {2: [x]}
            model = Mock()
            model.solve.side_effect = StopIteration('captured initial population')
            with patch.object(opt, '_generate_seed_candidates', return_value=[np.array(lb)]), \
                 patch.object(om, 'L_SHADE', return_value=model):
                with self.assertRaises(StopIteration):
                    opt._optimize_burn_case(2, opt._scalar_params(), opt._vector_params())
            initial = model.solve.call_args.kwargs['starting_solutions']
            np.testing.assert_array_equal(initial[0], np.clip(x, lb, ub))
            np.testing.assert_array_equal(initial[1], lb)
            self.assertFalse(getattr(opt, '_primer_fast_research', False))
            self.assertIsNone(model.solve.call_args.kwargs['termination'])

    def test_both_revs_receive_independent_seed_channel(self):
        cfg = config(PRIMER_RESEARCH_MODE='fast', LAMBERT_MAX_REVS=4, REVS_ENSEMBLE=True)
        seeds = {2: [np.zeros(9)]}
        def inspect(revs, opts, seeded):
            self.assertEqual(revs, [0, 4])
            for opt in opts:
                self.assertIs(opt.oracle_seeds, seeds)
                self.assertEqual(opt.external_seeds, {})
                self.assertFalse(getattr(opt, '_primer_fast_research', False))
                self.assertFalse(hasattr(opt, '_primer_search_deadline'))
            raise StopIteration('inspected')
        with patch.object(om, '_run_studies_unified', side_effect=inspect):
            with self.assertRaises(StopIteration):
                om.run_study_over_revs(cfg, oracle_seeds=seeds)

    def test_worker_replays_and_legalizes_with_product_settings(self):
        cfg = config(SPLIT_LEADING=True, LAMBERT_MAX_REVS=4,
                     SPLIT_N_SPAN=0, SPLIT_NLP_MAXITER=1, SPLIT_MULTISTART=None,
                     SPLIT_PRUNE_REOPT_MPS=0, SPLIT_WORKERS=1, SPLIT_WALL_BUDGET_SEC=0)
        for name in ('orbit_A', 'orbit_B'):
            cfg[name].update(SMA=12000., ECC=0., INC=0., RAAN=0., AOP=0., TA=0.)
        cfg['rules'].update(MAX_DV_MPS=250., MAX_TOTAL_DV_MPS=3000., T_MAX_SEC=6000.)
        route = dict(rank=0, t1=500., dv1=[.6, 0., 0.], t2=1100., t3=2600.,
                     dv_mps=1000., est_score=80., M=0, structure='2-burn')
        opt = om.MissionOptimizer(cfg)
        x, n = oracle.standard_x_from_route(opt, route['t1'], route['dv1'], route['t2'], route['t3'])
        with app.threadpool_limits(limits=1):
            with app.patch_report_level(opt):
                pre = opt._replay_mission(x, n)
            expected = app._legalize_stage(cfg, *pre, opt)
        job = OracleJob(cfg, cores=1, deadline=time.monotonic()+60, routes=[route])
        _, entries = job.collect()
        self.assertEqual(len(entries), 1)
        got = entries[0]['candidate']
        # Fresh compilation versus a spawned process loading numba cache may
        # differ by an ulp in the splitter (independent of oracle grid threads).
        np.testing.assert_allclose(got[0], expected[0], rtol=1e-12, atol=1e-13)
        np.testing.assert_array_equal(got[1], expected[1])
        for key in ('score', 'total_dv_mps', 'miss_km', 'T_team'):
            self.assertAlmostEqual(got[2][key], expected[2][key], places=9)
        self.assertEqual(got[2]['num_burns'], expected[2]['num_burns'])
        self.assertEqual(got[3].LAMBERT_MAX_REVS, opt.LAMBERT_MAX_REVS)
        self.assertIn('GRAVITY_DEGREE', got[3].config['strategy'])
        self.assertEqual(got[2]['penalty_count'], 0)

    def test_hard_deadline_process_supervisor(self):
        start = time.monotonic()
        job = OracleJob(config(), cores=1, deadline=start+.2, grid_only=True)
        _, candidates = job.collect()
        self.assertLess(time.monotonic()-start, 4.)
        self.assertEqual(candidates, [])
        self.assertFalse(job.process.is_alive())

    def test_completed_candidates_survive_timeout(self):
        job = OracleJob(config(), cores=1, deadline=time.monotonic()+.2, grid_only=True)
        # Simulate an atomic completion followed by the next candidate hanging.
        _atomic_dump(job.folder.name, 'routes.pkl', [dict(rank=0)])
        _atomic_dump(job.folder.name, 'candidate_000000.pkl', dict(wall_sec=.01))
        routes, candidates = job.collect()
        self.assertEqual(routes, [dict(rank=0)])
        self.assertEqual(candidates, [dict(wall_sec=.01)])


if __name__ == '__main__':
    unittest.main(verbosity=2)
