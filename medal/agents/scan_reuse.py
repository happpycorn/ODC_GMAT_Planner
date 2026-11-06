"""單次決策的純函式重用；只接受完全相同的狀態與參數，不改任何數值運算。"""
from contextlib import contextmanager
from contextvars import ContextVar
import copy
from dataclasses import dataclass, field
from functools import wraps
import os
import pickle
import struct

import numpy as np


SCAN_REUSE_ENV = "ODC_SCAN_REUSE"
_CURRENT = ContextVar("odc_decision_scan_reuse", default=None)


def scan_reuse_enabled():
    return os.environ.get(SCAN_REUSE_ENV, "1").strip().lower() not in ("0", "false", "off", "no")


def _state_key(game):
    # pickle 保留浮點位元、陣列 dtype/shape/完整內容，沒有四捨五入或近似比對。
    # 除 r/v、絕對時間、燃料外，也區分完整規則、mu、回合與多發窗口進度。
    rv = tuple(_parameter_key(values[side]) for values in (game._r, game._v) for side in ("pursuer", "evader"))
    return pickle.dumps((rv, game.t, game.t_max, game.used, game.mu,
                         vars(game.rules), game.mover, game.turn, game.outcome, game.min_dist,
                         game._win_len, game._win_elapsed, game._window_used()), protocol=5)


def _parameter_key(value):
    if isinstance(value, np.ndarray):
        return (np.ndarray, value.dtype, value.shape, value.strides, value.flags.writeable, value.tobytes())
    if type(value) in (float, np.float64):
        # 這些物理函式的 Numba 簽章皆為 float64；Python float 與 numpy.float64 是同一輸入型別。
        return (float, struct.pack("!d", value))
    return (type(value), pickle.dumps(value, protocol=5))


@dataclass
class _DecisionMemo:
    state: bytes
    values: dict = field(default_factory=dict)


@contextmanager
def decision_scope(game):
    """同一狀態的巢狀呼叫共用；推演到其他狀態時另開範圍，離開即清空。"""
    if not scan_reuse_enabled():
        token = _CURRENT.set(None)
        try:
            yield None
        finally:
            _CURRENT.reset(token)
        return
    key = _state_key(game)
    current = _CURRENT.get()
    if current is not None and current.state == key:
        yield current
        return
    memo = _DecisionMemo(key)
    token = _CURRENT.set(memo)
    try:
        yield memo
    finally:
        _CURRENT.reset(token)
        memo.values.clear()


def scoped_decision(func):
    """給 (self, game, ...) 方法使用，獨立 act 也有自己的短生命週期。"""
    @wraps(func)
    def scoped(self, game, *args, **kwargs):
        with decision_scope(game):
            return func(self, game, *args, **kwargs)
    return scoped


def reuse_call(func, *args):
    """鍵含函式身分與所有實際參數；儲存及取出的可變物件彼此隔離。"""
    memo = _CURRENT.get()
    if memo is None:
        return func(*args)
    key = (func, tuple(_parameter_key(arg) for arg in args))
    if key not in memo.values:
        result = func(*args)
        memo.values[key] = copy.deepcopy(result)
        return result
    # 用副本保持原本可寫陣列的 Numba 型別，避免 readonly 型別另行編譯。
    return copy.deepcopy(memo.values[key])


def reset_scan_reuse():
    """worker 啟動時清除 fork 可能繼承的父行程決策範圍。"""
    _CURRENT.set(None)
