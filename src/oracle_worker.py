"""Disposable oracle process and hard wall-clock supervision.

Spawn is explicit on every platform. Atomic files avoid a full multiprocessing
pipe blocking a worker while DE is busy; a killed candidate never looks complete.
The worker owns a POSIX session, including splitter fork children, so timeout and
exception cleanup cannot leave orphan computation running beside DE.
"""
import copy
import multiprocessing
import os
import pickle
import signal
import tempfile
import threading
import time
from pathlib import Path

from src.runlog import log


def oracle_core_budget(config):
    """Match optimizer._run_studies_unified's case pool allocation."""
    cores = os.cpu_count() or 4
    st = config.get("strategy", {})
    high = max(0, int(st.get("LAMBERT_MAX_REVS", 4)))
    revs = 2 if high and st.get("REVS_ENSEMBLE", True) else 1
    jobs = revs * len(config["optimization"]["MAX_BURNS"])
    seeded = config["optimization"].get("SEED") is not None
    slots = min(jobs, max(1, cores if seeded else cores // 2))
    return max(1, cores - slots)


def _atomic_dump(folder, name, value):
    path = Path(folder) / name
    with path.with_suffix(".tmp").open("wb") as f:
        pickle.dump(value, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(path.with_suffix(".tmp"), path)


def _oracle_worker(config, cores, deadline, folder, routes, grid_only):
    os.setsid()
    try:
        # Never change the parent's env or runtime thread/BLAS state.
        for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
            os.environ[key] = "1"
        import numba
        from threadpoolctl import threadpool_limits
        from src.optimizer import MissionOptimizer
        from src.oracle_twoburn import run_twoburn_oracle, standard_x_from_route
        from main import _legalize_stage, patch_report_level

        numba.set_num_threads(min(cores, numba.config.NUMBA_NUM_THREADS))
        cfg = copy.deepcopy(config)
        st = cfg.setdefault("strategy", {})
        started = time.monotonic()
        with threadpool_limits(limits=1):
            opt = MissionOptimizer(cfg)  # original high-REVS search settings
            if routes is None:
                routes = run_twoburn_oracle(opt, K=st.get("ORACLE_TWOBURN_K", 10),
                                           grid_div=st.get("ORACLE_TWOBURN_GRID_DIV", 100),
                                           deadline=deadline)
            if time.monotonic() >= deadline:
                return
            _atomic_dump(folder, "routes.pkl", routes)
            if grid_only:
                return
            # Grid and splitting do not overlap. Only one candidate at a time;
            # its splitter may use up to the entire spare budget, deterministically.
            numba.set_num_threads(1)
            st["SPLIT_WORKERS"] = min(max(1, cores - 1), max(1, int(st.get("SPLIT_WORKERS", 1))))
            for route in routes:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                one_start = time.monotonic()
                try:
                    opts = copy.deepcopy(cfg)
                    split_wall = opts["strategy"].get("SPLIT_WALL_BUDGET_SEC")
                    opts["strategy"]["SPLIT_WALL_BUDGET_SEC"] = (
                        min(float(split_wall), remaining) if split_wall else remaining)
                    candidate_opt = MissionOptimizer(opts)
                    x, n = standard_x_from_route(candidate_opt, route["t1"], route["dv1"], route["t2"], route["t3"])
                    with patch_report_level(candidate_opt):
                        b, t, mi = candidate_opt._replay_mission(x, n)
                    pre = b, t, mi
                    b, t, mi = _legalize_stage(opts, b, t, mi, candidate_opt)
                    result = dict(route=route, x=x, N=n, presplit=pre,
                                  candidate=(b, t, mi, candidate_opt),
                                  wall_sec=time.monotonic() - one_start,
                                  elapsed_sec=time.monotonic() - started)
                    if time.monotonic() < deadline:
                        _atomic_dump(folder, f"candidate_{route['rank']:06d}.pkl", result)
                except Exception as exc:
                    _atomic_dump(folder, f"error_{route['rank']:06d}.pkl", str(exc))
    except BaseException as exc:
        _atomic_dump(folder, "crash.pkl", f"{type(exc).__name__}: {exc}")


class OracleJob:
    def __init__(self, config, *, cores, deadline, routes=None, grid_only=False):
        self.started_at = time.monotonic()
        self.finished_at = None
        self.deadline = deadline
        self.folder = tempfile.TemporaryDirectory(prefix="odc-oracle-")
        self.done = threading.Event()
        self.timed_out = False
        self.process = multiprocessing.get_context("spawn").Process(
            target=_oracle_worker,
            args=(config, cores, deadline, self.folder.name, routes, grid_only))
        try:
            self.process.start()
        except BaseException:
            self.folder.cleanup()
            raise
        self.watcher = threading.Thread(target=self._supervise, daemon=True)
        self.watcher.start()

    def _stop(self):
        try:
            os.killpg(self.process.pid, signal.SIGKILL)
        except ProcessLookupError:
            if self.process.is_alive():
                self.process.kill()  # startup before setsid

    def _supervise(self):
        # Watch while DE is running too: its runtime cannot extend oracle's wall.
        while not self.done.wait(min(0.1, max(0.0, self.deadline - time.monotonic()))):
            if not self.process.is_alive():
                self.finished_at = time.monotonic()
                return
            if time.monotonic() >= self.deadline:
                self.timed_out = True
                self.finished_at = self.deadline
                self._stop()
                return

    def collect(self):
        try:
            self.process.join(max(0.0, self.deadline - time.monotonic()))
            if self.process.is_alive():
                self.timed_out = True
                self._stop()
            self.process.join(timeout=1)
            if self.finished_at is None:
                self.finished_at = min(time.monotonic(), self.deadline)
            self.wall_sec = max(0.0, self.finished_at - self.started_at)
            root = Path(self.folder.name)
            def read(path):
                with path.open("rb") as f:
                    return pickle.load(f)
            routes = read(root / "routes.pkl") if (root / "routes.pkl").exists() else []
            candidates = [read(p) for p in sorted(root.glob("candidate_*.pkl"))]
            for path in sorted(root.glob("*error*.pkl")) + list(root.glob("crash.pkl")):
                log.warning("Oracle worker: %s", read(path))
            if self.timed_out:
                log.warning("Oracle deadline exceeded; keeping %d completed candidates", len(candidates))
            elif self.process.exitcode:
                log.warning("Oracle worker exited with code %s; DE result remains available", self.process.exitcode)
            return routes, candidates
        finally:
            self.close()

    def close(self):
        self.done.set()
        self.watcher.join(timeout=1)
        self._stop()
        self.process.join(timeout=1)
        self.folder.cleanup()
