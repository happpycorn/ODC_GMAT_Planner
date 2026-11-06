"""copilot／批次評測使用行程平行化，每個行程的 BLAS 固定單執行緒。

入口必須在匯入 numpy 前呼叫；worker initializer 再呼叫一次。只用標準函式庫。
"""
import ctypes
import os
import sys


BLAS_THREAD_ENV = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                   "VECLIB_MAXIMUM_THREADS", "ACCELERATE_MAX_THREADS", "BLIS_NUM_THREADS",
                   "GOTO_NUM_THREADS", "OMP_THREAD_LIMIT")
_ACCELERATE_SET = None


def limit_blas_threads():
    # 必須覆寫既有值，setdefault 會留下使用者／shell 原本的多執行緒設定。
    for name in BLAS_THREAD_ENV:
        os.environ[name] = "1"
    if sys.platform != "darwin":
        return
    global _ACCELERATE_SET
    if _ACCELERATE_SET is None:
        try:
            lib = ctypes.CDLL("/System/Library/Frameworks/Accelerate.framework/Accelerate")
            _ACCELERATE_SET = lib.BLASSetThreading
            _ACCELERATE_SET.argtypes = [ctypes.c_uint]
            _ACCELERATE_SET.restype = ctypes.c_int
        except (OSError, AttributeError):
            # macOS < 15 無此 API，仍由匯入前的 VECLIB_MAXIMUM_THREADS=1 控制。
            _ACCELERATE_SET = False
    if _ACCELERATE_SET:
        # Apple thread_api.h：BLAS_THREADING_SINGLE_THREADED = 1。
        # 此設定是 thread-local，父行程與每個 worker 都要各自設定。
        _ACCELERATE_SET(1)
