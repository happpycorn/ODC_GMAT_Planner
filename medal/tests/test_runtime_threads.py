"""父行程匯入順序、兩種 worker 初始化、Accelerate 模式及精確的平行／重啟驗證。"""
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

import copilot
import agents.rollout as rollout
from evaluation.tournament import _initialize_worker as tournament_initialize_worker
from game.core import Game
from game.rules import Rules
from runtime_threads import BLAS_THREAD_ENV
from tools.bench_advise import exact_result


ROOT = Path(__file__).resolve().parents[1]


def accelerate_mode():
    if sys.platform != "darwin":
        return None
    lib = ctypes.CDLL("/System/Library/Frameworks/Accelerate.framework/Accelerate")
    try:
        getter = lib.BLASGetThreading
    except AttributeError:
        return None
    getter.argtypes = []
    getter.restype = ctypes.c_uint
    return getter()


@pytest.mark.parametrize("module", ["copilot", "evaluate", "evaluation.tournament", "agents.rollout"])
def test_limits_precede_numpy_in_fresh_process(module):
    probe = """
import importlib.abc, json, os, sys
from runtime_threads import BLAS_THREAD_ENV
seen = []
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'numpy':
            assert all(os.environ[k] == '1' for k in BLAS_THREAD_ENV)
            seen.append(fullname)
sys.meta_path.insert(0, Guard())
__import__(sys.argv[1])
assert seen == ['numpy']
print(json.dumps({k: os.environ[k] for k in BLAS_THREAD_ENV}))
"""
    env = {**os.environ, **{k: "8" for k in BLAS_THREAD_ENV}}
    result = subprocess.run([sys.executable, "-c", probe, module], cwd=ROOT, env=env,
                            capture_output=True, text=True, check=True)
    assert set(json.loads(result.stdout).values()) == {"1"}


@pytest.mark.parametrize("initialize", [rollout._initialize_worker, tournament_initialize_worker])
def test_initializer_overwrites_limits(monkeypatch, initialize):
    for name in BLAS_THREAD_ENV:
        monkeypatch.setenv(name, "8")
    initialize()
    assert all(os.environ[k] == "1" for k in BLAS_THREAD_ENV)
    assert accelerate_mode() in (None, 1)


def _probe_worker(directory):
    directory = Path(directory)
    (directory / f"{os.getpid()}.ready").touch()
    deadline = time.monotonic() + 30.0
    while len(list(directory.glob("*.ready"))) < 4:
        if time.monotonic() > deadline:
            raise TimeoutError("四個 worker 未全部啟動")
        time.sleep(0.01)
    return {"pid": os.getpid(), "env": {k: os.environ[k] for k in BLAS_THREAD_ENV},
            "accelerate_mode": accelerate_mode()}


def close_pool():
    if rollout._POOL["pool"] is not None:
        rollout._POOL["pool"].shutdown(cancel_futures=True)
        rollout._POOL.update(pool=None, n=0)


def test_all_four_actual_workers_have_single_thread_limits(tmp_path):
    try:
        snapshots = list(rollout._pool(4).map(_probe_worker, [str(tmp_path)] * 4))
        assert len({s["pid"] for s in snapshots}) == 4
        assert all(set(s["env"].values()) == {"1"} for s in snapshots)
        assert all(s["accelerate_mode"] in (None, 1) for s in snapshots)
    finally:
        close_pool()


@pytest.mark.parametrize("burns", [1, 2])
def test_workers_one_four_and_restarted_pool_are_bit_identical(burns):
    p = dict(sma=6978.0, ecc=0.0, inc=51.6, raan=10.0, aop=0.0, ta=0.0)
    e = dict(sma=7010.0, ecc=0.001, inc=51.8, raan=10.3, aop=0.0, ta=4.0)
    g = Game.from_elements(Rules(t_max_sec=1800.0, burns_per_turn=burns), p, e)
    st = copilot.state_from_game(g, "pursuer")
    brains = ["rollout_pursuer", {"name": "lambert_pursuer", "time_weight_mps": 60.0}]
    serial = copilot.advise(st, brains, ["coast", "dv_evader_fast"], prune=True, workers=1)
    for _ in range(2):
        try:
            parallel = copilot.advise(st, brains, ["coast", "dv_evader_fast"], prune=True, workers=4)
            assert exact_result(serial) == exact_result(parallel)
        finally:
            close_pool()
