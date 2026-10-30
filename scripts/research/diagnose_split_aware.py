"""In-process DE/replay diagnostic; no Manager, process pool, or GMAT.

Example: uv run python scripts/research/diagnose_split_aware.py CONFIG -o trace.json
Set OMP/OPENBLAS/MKL/NUMEXPR_NUM_THREADS=1 before invoking.
"""
import argparse
import copy
import json
from pathlib import Path
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from odc.search.optimizer import MissionOptimizer
from odc.runlog import setup


def plain(obj):
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.generic):
        return obj.item()
    raise TypeError(type(obj).__name__)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("config")
    parser.add_argument("-o", required=True)
    parser.add_argument("--maxiter", type=int)
    parser.add_argument("--oracle-cache", help="Cache the original high-REVS oracle grid")
    args = parser.parse_args()
    setup(quiet=True, logfile=args.o + ".log")
    cfg = json.loads(Path(args.config).read_text())
    if args.maxiter is not None:
        cfg["optimization"]["MAXITER"] = args.maxiter
    result = {"config_path": args.config, "config": copy.deepcopy(cfg), "cases": {}}

    def save():
        Path(args.o).write_text(json.dumps(result, default=plain, indent=2) + "\n")

    seeds = {}
    if cfg.get("strategy", {}).get("ORACLE_TWOBURN_SEED_DE", False):
        from odc.search.oracle_twoburn import run_twoburn_oracle, standard_x_from_route
        opt = MissionOptimizer(cfg)
        cache = Path(args.oracle_cache) if args.oracle_cache else None
        if cache is not None and cache.exists():
            routes = json.loads(cache.read_text())
        else:
            st = cfg["strategy"]
            routes = run_twoburn_oracle(opt, K=st.get("ORACLE_TWOBURN_K", 10),
                                       grid_div=st.get("ORACLE_TWOBURN_GRID_DIV", 100))
            if cache is not None:
                cache.write_text(json.dumps(routes, default=plain, indent=2))
        for r in routes:
            x, n = standard_x_from_route(opt, r["t1"], r["dv1"], r["t2"], r["t3"])
            if n in opt.burns:
                seeds.setdefault(n, []).append(x)
        result["oracle_routes"] = routes
        result["oracle_seed_counts"] = {n: len(s) for n, s in seeds.items()}
        save()
    cfg.setdefault("strategy", {})["LAMBERT_MAX_REVS"] = 0
    opt = MissionOptimizer(cfg)
    opt.oracle_seeds = seeds
    result["effective_config"] = cfg
    opt.burn_case_results = {}
    started = time.monotonic()
    for n in cfg["optimization"]["MAX_BURNS"]:
        _, x, fitness, epochs, note = opt._optimize_burn_case(
            n, opt._scalar_params(), opt._vector_params())
        opt.burn_case_results[n] = {"best_x": x, "fitness": fitness}
        _, _, replay = opt._replay_mission(x, n)
        _, _, refined = opt.refine_trajectory(x, n, fitness)
        result["cases"][n] = dict(x=x, fitness=fitness, epochs=epochs, note=note,
                                 metrics=opt.mission_metrics(x, n), replay=replay,
                                 refined=refined,
                                 refined_fitness=float(opt._fitness_wrapper(n)(refined["x"])),
                                 refined_metrics=opt.mission_metrics(refined["x"], n))
        result["wall_sec"] = time.monotonic() - started
        save()
        print(f"{n} burns: fast={-fitness:.9f}, replay={replay['score_split_est']:.9f}", flush=True)
    picked = opt._pick_best_case()
    result["picked"] = None if picked is None else dict(burns=picked[0], x=picked[1], fitness=picked[2])
    result["legal_backup_burns"] = None if opt.legal_backup is None else opt.legal_backup["burns"]
    if picked is not None:
        _, _, result["winner"] = opt.refine_trajectory(picked[1], picked[0], picked[2])
    result["wall_sec"] = time.monotonic() - started
    save()
    print(f"picked={None if picked is None else picked[0]}, trace={args.o}", flush=True)


if __name__ == "__main__":
    main()
