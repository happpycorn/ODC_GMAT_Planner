"""固定軌道檢查點：精度、fitness、關閉退路、spawn 與暖機後速度。

uv run python tests/test_ephem_cache.py
可用 --baseline-dir 指向改動前的 optimizer_before.py 與 hyper_far/ranking_round.npz，
在相同 Numba 編譯快取狀態下逐位元核對原程式。
"""
SLOW = True

import argparse
import copy
import importlib.util
import json
import multiprocessing
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from odc.physics.core_math import build_ephem_table, ephem_state, propagate_dop853
from odc.config.validator import ConfigValidationError, validate_config
from odc.search.optimizer import MissionOptimizer
from odc.search.fitness import fast_fitness_evaluator
from odc.split.burn_splitter import _simulate_free, _simulate_free_reuse, _terminal_state, _retarget_last, _fd_init, _fd_eval


def config(name):
    with (ROOT / f"configs/shared/{name}.json").open() as f:
        cfg = json.load(f)
    if name == "hyper_far":
        with (ROOT / "sweeps/splitspeed_par3_rec.json").open() as f:
            base = json.load(f)["base"]
        for key, value in base.items():
            section, field = key.split(".")
            cfg.setdefault(section, {})[field] = value
    return cfg


def spawn_probe(opt, x, n):
    # optimizer / packed arrays / NLP context all cross spawn via pickle.
    s, v = opt._scalar_params(), opt._vector_params()
    args = (opt.MU, opt.J2_VAL, opt.J3_VAL, opt.J4_VAL, opt.RE_VAL,
            opt.A_r0, opt.A_v0, opt.B_r0, opt.B_v0)
    xf = np.array([1234.5, 5678.9, 0.01, 0.02, 0.03])
    ctx = dict(zip(("mu", "j2", "j3", "j4", "re", "A_r0", "A_v0", "B_r0", "B_v0"), args))
    ctx.update(ephem=opt.ephem, cap=opt.MAX_DV_SOFT, min_periapsis=opt.MIN_PERIAPSIS,
               miss_tol=opt.MISS_TOLERANCE_SOFT, k_t=opt.k_t, C_t=opt.C_t, k_v=opt.k_v, C_v=opt.C_v)
    _fd_init(ctx)
    return (fast_fitness_evaluator(x, n, s, v), opt.state_B(1234.5), _fd_eval(1, xf))


def check_config(name, baseline_dir):
    cfg = config(name)
    # Warm builder independently so reported construction seconds exclude JIT.
    cold = copy.deepcopy(cfg)
    cold.setdefault("strategy", {})["EPHEM_CACHE"] = False
    off = MissionOptimizer(cold)
    physical = (off.MU, off.J2_VAL, off.J3_VAL, off.J4_VAL, off.RE_VAL)
    build_ephem_table(off.A_r0, off.A_v0, 60.0, 60.0, *physical)
    on = MissionOptimizer(cfg)
    s_on, v_on = on._scalar_params(), on._vector_params()
    s_off, v_off = off._scalar_params(), off._vector_params()
    assert on.EPHEM_CACHE and not off.EPHEM_CACHE
    assert off.ephem is None and off.ephem_build_seconds == 0.0
    assert v_off.shape == (4, 3) and np.array_equal(v_on[:4], v_off)
    assert on.ephem_end_time >= (2*(max(on.burns)-1) + 14 + 1)*on.T_max
    rng = np.random.default_rng(491)
    times = rng.uniform(0.0, on.T_max, 500)
    worst_r = worst_v = 0.0
    mission_r = mission_v = 0.0
    for body in (0, 1):
        table = on.ephem[body + 1]
        r0, v0 = v_off[2*body:2*body+2]
        last = (len(table)//2 - 1)*on.ephem[0]
        # 500 random mission times for EACH body, plus extended NLP trial times.
        probes = np.r_[times, rng.uniform(on.T_max, last, 16)]
        for index, t in enumerate(probes):
            rc, vc = ephem_state(0.0, on.ephem[0], table, t, *physical)
            rd, vd = propagate_dop853(r0, v0, t, 60.0, *physical)
            dr, dv = np.linalg.norm(rc-rd)*1000, np.linalg.norm(vc-vd)*1000
            # Acceptance is on the mission window; extended probes also report/assert it.
            worst_r, worst_v = max(worst_r, dr), max(worst_v, dv)
            if index < len(times):
                mission_r, mission_v = max(mission_r, dr), max(mission_v, dv)
            assert dr < 1.0, (name, body, t, dr)
            assert dv < 1e-3, (name, body, t, dv)
        # Exact checkpoints (including last), adjacent floats, negative and overflow.
        for k in (0, 1, len(table)//4, len(table)//2-1):
            t = k*on.ephem[0]
            r, v = ephem_state(0.0, on.ephem[0], table, t, *physical)
            assert np.array_equal(r, table[2*k]) and np.array_equal(v, table[2*k+1])
            r[0] += 1.0
            assert not np.array_equal(r, table[2*k]), "query must not mutate table"
            for near in (np.nextafter(t, -np.inf), np.nextafter(t, np.inf)):
                if near < 0 or near > last:
                    continue
                j = min(int(np.floor(near/on.ephem[0])), len(table)//2-1)
                while j*on.ephem[0] > near:
                    j -= 1
                while j+1 < len(table)//2 and (j+1)*on.ephem[0] <= near:
                    j += 1
                want = propagate_dop853(table[2*j], table[2*j+1], near-j*on.ephem[0], 60.0, *physical)
                got = ephem_state(0.0, on.ephem[0], table, near, *physical)
                assert all(np.array_equal(a,b) for a,b in zip(got, want))
        for t in (-60.0, np.nextafter(last, np.inf), last + 100.0):
            got = ephem_state(0.0, on.ephem[0], table, t, *physical)
            want = propagate_dop853(r0, v0, t, 60.0, *physical)
            assert all(np.array_equal(a,b) for a,b in zip(got, want))
        for t in times[:10]:
            got = (off.state_A if body == 0 else off.state_B)(t)
            want = propagate_dop853(r0, v0, t, 60.0, *physical)
            assert all(np.array_equal(a,b) for a,b in zip(got, want))
    print(f"  ✅ {name} mission state max: {mission_r:.9g} m, {mission_v:.9g} m/s", flush=True)
    print(f"  ✅ {name} extended state max: {worst_r:.9g} m, {worst_v:.9g} m/s", flush=True)
    worst_abs = worst_rel = 0.0
    reference = None if baseline_dir is None else np.load(Path(baseline_dir)/f"{name}.npz")
    if reference is not None:
        # Compare against untouched source under the SAME Numba cache/compilation state.
        # The original program itself differs by 1 ulp between cold and cached izzo.
        source = Path(baseline_dir)/"optimizer_before.py"
        spec = importlib.util.spec_from_file_location("optimizer_before", source)
        original_module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = original_module
        spec.loader.exec_module(original_module)
        original_opt = original_module.MissionOptimizer(cold)
        original_s = original_opt._scalar_params()
        original_v = np.vstack([original_opt.A_r0, original_opt.A_v0,
                                original_opt.B_r0, original_opt.B_v0])
    for n in (1, 2, 3):
        if reference is None:
            lo, hi = map(np.asarray, on._generate_bounds(n))
            xs = lo + rng.random((500, len(lo)))*(hi-lo)
        else:
            xs = reference[f"x{n}"]
        # Warm all paths; alternate complete batches, taking median of three runs.
        fast_fitness_evaluator(xs[0], n, s_on, v_on)
        fast_fitness_evaluator(xs[0], n, s_off, v_off)
        elapsed = {False: [], True: []}
        for repeat in range(3):
            for enabled in ((False, True) if repeat%2 == 0 else (True, False)):
                s, v = (s_on, v_on) if enabled else (s_off, v_off)
                started = time.perf_counter()
                values = np.array([fast_fitness_evaluator(x, n, s, v) for x in xs])
                elapsed[enabled].append((time.perf_counter()-started)*1000/len(xs))
                if enabled:
                    cached = values
                else:
                    direct = values
        diffs = np.abs(cached-direct)
        rel = diffs/np.maximum(np.abs(direct), np.finfo(float).tiny)
        worst_abs, worst_rel = max(worst_abs, diffs.max()), max(worst_rel, rel.max())
        assert np.all((diffs < 1e-6) | (rel < 1e-9)), (name, n, diffs.max(), rel.max())
        # Legacy packed arrays still mean exactly the original direct integration path.
        legacy = np.array([fast_fitness_evaluator(x, n, s_off[:21], v_off) for x in xs])
        assert np.array_equal(direct.view(np.uint64), legacy.view(np.uint64))
        if reference is not None:
            original = np.array([original_module.fast_fitness_evaluator(x, n, original_s, original_v)
                                 for x in xs])
            assert np.array_equal(direct.view(np.uint64), original.view(np.uint64)), (
                name, n, "original bitwise mismatch", np.max(np.abs(direct-original)),
                np.count_nonzero(direct.view(np.uint64) != original.view(np.uint64)))
            print(f"  ✅ {name} {n} burns: cache off vs original source bitwise identical; "
                  f"original cold/cached drift={np.max(np.abs(original-reference[f'y{n}'])):.9g}", flush=True)
        print(f"  ✅ {name} {n} burns: off={np.median(elapsed[False]):.6f} ms, "
              f"on={np.median(elapsed[True]):.6f} ms; max abs={diffs.max():.9g}, rel={rel.max():.9g}", flush=True)
    print(f"  ✅ {name} build={on.ephem_build_seconds:.6f} s; "
          f"end={on.ephem_end_time:.1f} s; max fitness abs={worst_abs:.9g}, rel={worst_rel:.9g}", flush=True)

    # Splitter simulations, both FD paths, and retarget setup all use the same ephemeris.
    args = (*physical, on.A_r0, on.A_v0, on.B_r0, on.B_v0)
    xf = np.array([1234.5, 5678.9, 0.01, 0.02, 0.03])
    a = _simulate_free(xf, 1, *args, ephem=on.ephem)
    b = _simulate_free_reuse(xf, 1, *args, ephem=on.ephem)
    assert all(np.array_equal(a[k], b[k]) for k in a)
    r, v, t = _terminal_state(xf[0], [], [], mu=on.MU, j2=on.J2_VAL, j3=on.J3_VAL,
                              j4=on.J4_VAL, re=on.RE_VAL, B_r0=on.B_r0, B_v0=on.B_v0, ephem=on.ephem)
    assert all(np.array_equal(a,b) for a,b in zip((r,v), on.state_B(t)))
    target = a["r_final"]
    assert _retarget_last(xf, 1, target, 10.0, *physical, on.B_r0, on.B_v0, ephem=on.ephem) is not None
    x = np.asarray(on._generate_bounds(2)).mean(axis=0)
    expected = spawn_probe(on, x, 2)
    with multiprocessing.get_context("spawn").Pool(1) as pool:
        got = pool.apply(spawn_probe, (on, x, 2))
    assert got[0] == expected[0]
    assert all(np.array_equal(a,b) for a,b in zip(got[1], expected[1]))
    assert np.array_equal(got[2], expected[2])
    print(f"  ✅ {name} splitter / spawn optimizer, fitness and FD context", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-dir")
    args = parser.parse_args()
    for name in ("hyper_far", "ranking_round"):
        check_config(name, args.baseline_dir)
    cfg = config("ranking_round")
    for field, values in (("EPHEM_CACHE", (0, "true", None)),
                          ("EPHEM_CACHE_STEP_SEC", (0, -1, True, float("nan"), float("inf"), "60"))):
        for value in values:
            bad = copy.deepcopy(cfg)
            bad["strategy"][field] = value
            try:
                validate_config(bad)
            except ConfigValidationError:
                pass
            else:
                raise AssertionError((field, value))
    for step in (45.5, 120.0):
        custom = copy.deepcopy(cfg)
        custom["strategy"]["EPHEM_CACHE_STEP_SEC"] = step
        validate_config(custom)
        opt = MissionOptimizer(custom)
        assert opt.ephem[0] == step
        r, v = opt.state_B(step*13)
        assert np.array_equal(r, opt.ephem[2][26]) and np.array_equal(v, opt.ephem[2][27])
    print("  ✅ cache config validation and custom step")


if __name__ == "__main__":
    main()
