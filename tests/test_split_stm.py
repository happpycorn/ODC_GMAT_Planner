"""STM propagation and the complete split NLP Jacobian against independent FD.

Run as a script; fixed RNG, five perturbed warm starts per scenario. Full
regression discovers this file automatically. No GMAT or worker sockets needed.
"""
import copy
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

import numpy as np
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import burn_splitter as bs
from src.core_math import (propagate_dop853, propagate_dop853_stm,
                           acceleration_jacobian, fast_dynamics, build_ephem_table,
                           build_wait_prefix)
from src.config_validator import validate_config, ConfigValidationError
from src.optimizer import MissionOptimizer

SLOW = True
_BLAS1 = threadpool_limits(limits=1, user_api="blas")


def context(opt):
    return dict(mu=opt.MU, j2=opt.J2_VAL, j3=opt.J3_VAL, j4=opt.J4_VAL, re=opt.RE_VAL,
                A_r0=opt.A_r0, A_v0=opt.A_v0, B_r0=opt.B_r0, B_v0=opt.B_v0,
                ephem=opt.ephem)


def central_jacobian(fun, x, steps):
    cols = []
    for k, h in enumerate(steps):
        d = np.zeros_like(x)
        d[k] = h
        cols.append((672*(fun(x+d) - fun(x-d)) - 168*(fun(x+2*d) - fun(x-2*d))
                     + 32*(fun(x+3*d) - fun(x-3*d)) - 3*(fun(x+4*d) - fun(x-4*d)))/(840*h))
    return np.array(cols).T


def check_jac(label, got, ref, rtol, atol):
    error = np.abs(got-ref)
    scaled = error / np.maximum(np.abs(ref), atol/rtol)
    worst = np.unravel_index(np.argmax(scaled), scaled.shape)
    print(f"  {label}: max mixed relative error={scaled[worst]:.3e}, "
          f"abs={error[worst]:.3e}, index={worst}, "
          f"STM={got[worst]:.9g}, FD={ref[worst]:.9g}", flush=True)
    assert np.max(scaled) < rtol, label
    return float(np.max(scaled))


def test_propagator(opt):
    c = context(opt)
    phys = tuple(c[k] for k in ('mu', 'j2', 'j3', 'j4', 're'))
    y = np.r_[opt.B_r0, opt.B_v0]
    for t in (600., 6000., 40000.):
        fun = lambda y: np.concatenate(propagate_dop853(y[:3], y[3:], t, 60., *phys))
        r, v, phi = propagate_dop853_stm(y[:3], y[3:], t, 60., *phys)
        equal = np.array_equal(np.r_[r, v], fun(y))
        state_error = np.max(abs(np.r_[r, v]-fun(y))/np.maximum(1., abs(fun(y))))
        print(f"  tof={t:g}: state bitwise equal={equal}, mixed relative error={state_error:.3e}")
        assert state_error < 1e-12
        # A high-order central reference avoids O(h^2) orbit-phase errors.
        ref = central_jacobian(fun, y, [0.02]*3 + [5e-4]*3)
        check_jac(f"Phi {t:g}s", phi, ref, 1e-6, 1e-6)
        column_error = np.max(np.linalg.norm(phi-ref, axis=0)/np.linalg.norm(ref, axis=0))
        print(f"  Phi {t:g}s: maximum column relative norm error={column_error:.3e}", flush=True)
        assert column_error < 1e-6
    for t in (0., -1.):
        r, v, phi = propagate_dop853_stm(y[:3], y[3:], t, 0., *phys)
        assert np.array_equal(np.r_[r, v], y) and np.array_equal(phi, np.eye(6))
    # Exercise zonal gradients individually, inclined geometry, and two-body.
    yp = np.array([7000., -2100., 3400., 1., 6., -2.])
    for zonals in ((0., 0., 0.), (phys[1], 0., 0.), (0., phys[2], 0.),
                   (0., 0., phys[3]), phys[1:4]):
        args = (phys[0], *zonals, phys[4])
        fun = lambda r: fast_dynamics(0., np.r_[r, yp[3:]], *args)[3:]
        ref = central_jacobian(fun, yp[:3], [0.1]*3)
        check_jac(f"gravity gradient {zonals}", acceleration_jacobian(yp[:3], *args),
                  ref, 1e-7, 1e-14)


def test_perigee_branches(mu):
    for label, y in (
        ("bound", np.array([7000., -1000., 500., 1., 7., 2.])),
        ("incoming unbound", np.array([12000., 2000., -1500., -10., 3., 1.])),
        ("outgoing unbound", np.array([12000., 2000., -1500., 10., 3., 1.]))):
        fun = lambda y: np.array([bs._osc_perigee(y[:3], y[3:], mu)])
        ref = central_jacobian(fun, y, [0.02]*3 + [1e-4]*3)
        check_jac(f"perigee {label}", bs._perigee_gradient(y[:3], y[3:], mu)[None, :],
                  ref, 1e-6, 1e-7)


def test_score_branches(opt):
    """Independent scalar FD checks for flat distance and exponential clamps."""
    eye = np.eye(8)
    dm = dict(miss_km=eye[0], T_team=eye[1], total_dv=eye[2],
              dv_mags=eye[3:5], arc_minr=eye[5:])
    def metrics(z):
        return dict(miss_km=z[0], T_team=z[1], total_dv=z[2],
                    dv_mags=z[3:5], arc_minr=z[5:])
    score = (opt.k_t, opt.C_t, opt.k_v, opt.C_v)
    fun = lambda z: bs._nlp_stack(metrics(z), opt.MAX_DV_SOFT, opt.MIN_PERIAPSIS,
                                 opt.MISS_TOLERANCE_SOFT, *score)
    for miss, clamped in ((4., False), (6., False), (6., True)):
        z = np.array([miss, 10000., 1.5, .7, .8, 7000., 7100., 7200.])
        if clamped:
            z[1] = opt.C_t + 701./opt.k_t
            z[2] = (opt.C_v + 701./opt.k_v)/1000.
        got = bs._nlp_stm_jacobian(metrics(z), dm, *score)
        ref = central_jacobian(fun, z, [1e-3, 1., 1e-5, 1e-4, 1e-4, 1., 1., 1.])
        check_jac(f"score miss={miss:g}, clamped={clamped}", got, ref, 1e-7, 1e-9)


def capture_warm_start(opt, t0, leading_dvs, leading_coasts, terminal_coast, target):
    captured = []
    def capture(x, N, **kw):
        captured.append((x.copy(), N))
        return bs._eval_free(x, N, **{k: kw[k] for k in (
            'cap', 'min_periapsis', 'mu', 'j2', 'j3', 'j4', 're', 'A_r0', 'A_v0',
            'B_r0', 'B_v0', 'k_t', 'C_t', 'k_v', 'C_v', 'miss_tol', 'ephem')})
    with patch.object(bs, 'joint_nlp_split', capture):
        bs.legalize_route(t0, leading_dvs, leading_coasts, terminal_coast, target,
                          cap=opt.MAX_DV_SOFT, min_coast=opt.MIN_COAST_TIME,
                          min_periapsis=opt.MIN_PERIAPSIS, max_revs=opt.LAMBERT_MAX_REVS,
                          k_t=opt.k_t, C_t=opt.C_t, k_v=opt.k_v, C_v=opt.C_v,
                          T_max=opt.T_max, miss_tol=opt.MISS_TOLERANCE_SOFT,
                          n_span=0, **context(opt))
    assert captured, "greedy warm start must exist"
    return captured[0]


def test_full_jacobian(opt, x0, N, label):
    c = context(opt)
    score = (opt.k_t, opt.C_t, opt.k_v, opt.C_v)
    stack = lambda x: bs._nlp_stack(bs._simulate_free_reuse(x, N, **c),
            opt.MAX_DV_SOFT, opt.MIN_PERIAPSIS, opt.MISS_TOLERANCE_SOFT, *score)
    rng = np.random.default_rng(7341)
    largest = 0.
    for sample in range(5):
        x = x0.copy()
        x[:N+1] += rng.uniform(0.05, 0.2, N+1)
        x[N+1:] += rng.normal(0., 2e-3, 3*N)
        m, dm = bs._simulate_free_stm(x, N, **c)
        old = bs._simulate_free_reuse(x, N, **c)
        for key in old:
            np.testing.assert_allclose(m[key], old[key], rtol=1e-12, atol=1e-12)
        got = bs._nlp_stm_jacobian(m, dm, *score)
        steps = np.r_[[0.01]*(N+1), np.repeat(np.minimum(1e-5, 0.1*m["dv_mags"]), 3)]
        # The score has a kink at miss=5 km. Keep every stencil on the
        # selected branch, and small relative to the miss norm's curvature.
        _, va = opt.state_A(m["T_team"])
        relative_sensitivity = np.linalg.norm(dm["r_final"] - np.outer(va, dm["T_team"]), axis=0)
        margin = min(m["miss_km"], abs(m["miss_km"] - 5.0))
        smooth_steps = steps.copy()
        steps = np.minimum(steps, 0.1*margin / np.maximum(relative_sensitivity, 1e-12))
        print(f"  {label} sample {sample+1}: miss={m['miss_km']:.6g} km", flush=True)
        ref = central_jacobian(stack, x, smooth_steps)
        branch_ref = central_jacobian(stack, x, steps)
        ref[0] = branch_ref[0]
        radius_ref = central_jacobian(stack, x, [0.01]*(N+1) + [1e-5]*(3*N))
        ref[N+1:-1] = radius_ref[N+1:-1]
        # Miss itself is smooth across the scorer's 5-km boundary, and
        # needs no small norm-of-kick stencil at empty burn slots.
        miss_steps = np.minimum(np.r_[[0.1]*(N+1), [1e-4]*(3*N)],
                                0.05*m["miss_km"]/np.maximum(relative_sensitivity, 1e-12))
        ref[-1] = -central_jacobian(lambda x: np.array([bs._simulate_free_reuse(x, N, **c)["miss_km"]]),
                                   x, miss_steps)[0]
        largest = max(largest, check_jac(f"{label} sample {sample+1}", got, ref, 1e-5, 2e-5))
        # Check all metric derivatives, including position, T and total delta-v.
        dflat = np.vstack((dm['r_final'], dm['T_team'], dm['total_dv'],
                          dm['miss_km'], dm['dv_mags'], dm['arc_minr']))
        # Position is smooth even at a zero kick and tolerates larger FD
        # steps. Norms/miss need the smaller steps used for the stack above.
        position_time = central_jacobian(
            lambda x: np.r_[bs._simulate_free_reuse(x, N, **c)["r_final"],
                            float(x[0] + np.sum(x[1:N+1]))], x,
            [0.1]*(N+1) + [1e-4]*(3*N))
        rflat = np.vstack((position_time, -np.sum(ref[1:N+1], axis=0),
                           -ref[-1], -ref[1:N+1], ref[N+1:-1]))
        check_jac(f"{label} metrics {sample+1}", dflat, rflat, 1e-5, 2e-5)
    print(f"  {label} maximum over five points: {largest:.3e}", flush=True)


def test_fd_and_options(opt, x, N):
    from main import split_options
    c = context(opt)
    kw = dict(cap=opt.MAX_DV_SOFT, min_coast=opt.MIN_COAST_TIME,
              min_periapsis=opt.MIN_PERIAPSIS, k_t=opt.k_t, C_t=opt.C_t,
              k_v=opt.k_v, C_v=opt.C_v, T_max=opt.T_max,
              miss_tol=opt.MISS_TOLERANCE_SOFT, maxiter=3, **c)
    legacy = bs.joint_nlp_split(x, N, **kw)
    explicit = bs.joint_nlp_split(x, N, jacobian='fd', **kw)
    np.testing.assert_array_equal(legacy['x'], explicit['x'])
    assert legacy['score'] == explicit['score']
    ctx = dict(cap=kw['cap'], min_periapsis=kw['min_periapsis'], miss_tol=kw['miss_tol'],
               k_t=opt.k_t, C_t=opt.C_t, k_v=opt.k_v, C_v=opt.C_v, **c)
    with bs.FDPool(1, ctx) as pool:
        fast = bs.joint_nlp_split(x, N, jacobian='fd', fd_map=pool, **kw)
    np.testing.assert_array_equal(legacy['x'], fast['x'])
    assert legacy['score'] == fast['score']
    # In STM mode even an FDPool object must never be used for derivatives.
    with patch.object(bs.FDPool, 'jacobian', side_effect=AssertionError('FD used')):
        bs.joint_nlp_split(x, N, jacobian='stm', fd_map=pool, **kw)
    for mode in ('fd', 'stm'):
        cfg = copy.deepcopy(opt.config)
        cfg['strategy']['SPLIT_JACOBIAN'] = mode
        validate_config(cfg)
        assert split_options(cfg)['jacobian'] == mode
    assert split_options({})['jacobian'] == 'fd'
    for mode in (None, 'STm', 1, [], {}):
        cfg = copy.deepcopy(opt.config)
        cfg['strategy']['SPLIT_JACOBIAN'] = mode
        try:
            validate_config(cfg)
        except ConfigValidationError:
            pass
        else:
            raise AssertionError(f'accepted invalid mode {mode!r}')
    print('  FD default/explicit/stacked results bitwise identical; config wiring passed', flush=True)


def main():
    os.chdir(ROOT)
    routes = json.loads((ROOT/'tests/fixtures/split_stm_routes.json').read_text())
    data = routes['hyper_far']
    opt = MissionOptimizer(data['config'])
    test_propagator(opt)
    test_score_branches(opt)
    test_perigee_branches(opt.MU)
    route = lambda d: {k: np.asarray(v) if k == 'target' else v
                       for k, v in d.items() if k not in ('config', 'source')}
    x, N = capture_warm_start(opt, **route(data))
    test_full_jacobian(opt, x, N, 'hyper_far')
    test_fd_and_options(opt, x, N)
    rank = MissionOptimizer(json.loads((ROOT/'configs/shared/ranking_round.json').read_text()))
    xr, Nr = capture_warm_start(rank, **route(routes['ranking_round']))
    test_full_jacobian(rank, xr, Nr, 'ranking_round')
    # Exercise cached waiting-prefix branches and checkpoint-based target evaluation.
    step = 600.
    c = context(rank)
    phys = tuple(c[k] for k in ('mu', 'j2', 'j3', 'j4', 're'))
    A = build_ephem_table(rank.A_r0, rank.A_v0, step, 40000., *phys)
    B = build_ephem_table(rank.B_r0, rank.B_v0, step, 40000., *phys)
    rank.ephem = (step, A, B, build_wait_prefix(B, step, rank.MU))
    test_full_jacobian(rank, xr, Nr, 'ranking_round ephem')
    print('✅ test_split_stm: all checks passed', flush=True)


if __name__ == '__main__':
    main()
