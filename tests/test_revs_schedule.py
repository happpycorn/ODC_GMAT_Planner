"""固定 SEED 下，共用 REVS 行程池與原本逐趟搜尋的結果必須相同。"""
SLOW = True

import copy
import json
import os
import struct
import sys
import threading

import numpy as np
from threadpoolctl import threadpool_limits

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.optimizer import MissionOptimizer, _run_studies_unified


def exact(value):
    """保留浮點位元、陣列結構與文字，方便直接比較整份回傳值。"""
    if isinstance(value, np.ndarray):
        return exact(value.tolist())
    if isinstance(value, np.generic):
        return exact(value.item())
    if isinstance(value, float):
        return ("float64", struct.pack("!d", value).hex())
    if isinstance(value, dict):
        return {key: exact(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [exact(item) for item in value]
    return value


with open(os.path.join(os.path.dirname(__file__), "fixtures", "pipeline_smoke.json"),
          encoding="utf-8") as source:
    config = json.load(source)
config["optimization"].update(MAX_BURNS=[1, 2], MAXITER=12, POPSIZE=5, SEED=0)
config["strategy"]["REVS_ENSEMBLE"] = True
for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[name] = "1"


def optimizers():
    result = []
    for revs in (0, 4):
        cfg = copy.deepcopy(config)
        cfg["strategy"]["LAMBERT_MAX_REVS"] = revs
        result.append(MissionOptimizer(cfg))
    return result


thread_errors = []
original_excepthook = threading.excepthook


def capture_thread_error(args):
    thread_errors.append(args.exc_value)


threading.excepthook = capture_thread_error
try:
    with threadpool_limits(limits=1, user_api="blas"):
        sequential = [opt.run_study() for opt in optimizers()]
        parallel = _run_studies_unified((0, 4), optimizers(), seed_set=True)
finally:
    threading.excepthook = original_excepthook

assert not thread_errors, f"背景進度執行緒拋錯：{thread_errors!r}"
assert all(isinstance(result[2], dict) for result in sequential), "測試設定必須產生有效解"
assert exact(sequential) == exact(parallel), "共用排程改變了固定 SEED 的解或浮點位元"
print("  ✅ REVS=0/4 共用排程與逐趟搜尋的回傳值逐位元相同")
