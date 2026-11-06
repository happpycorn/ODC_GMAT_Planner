"""金／銅牌賽的官方初始狀態匯入：雙方 r0/v0（EarthMJ2000Eq，含 epoch）→ 第 1 回合起點的狀態。

規則寫「雙方初始狀態向量 r0, v0，EarthMJ2000Eq，含 epoch」。GMAT 教育訓練錄影 (4) 示範兩艘的 epoch
可以不同（差 15 小時）：GMAT 先讓早出發的那艘單獨傳播到晚出發的時刻，再一起傳播。這裡照做——早的那艘用
二體（點質量，同比賽的力學模型）傳播到較晚的 epoch，第 1 回合從那裡開始（待主辦確認，提問 20）。

局勢檔格式（每艘二選一：r_km + v_kms，或 elements 六根數；epoch 兩艘都給或都不給）：

    {"pursuer": {"epoch": "2026-11-09T00:00:00Z", "r_km": [x, y, z], "v_kms": [vx, vy, vz]},
     "evader":  {"epoch": "09 Nov 2026 15:00:00.000",
                 "elements": {"sma": 7000, "ecc": 0.001, "inc": 30, "raan": 0, "aop": 0, "ta": 0}}}

epoch 接受 ISO 8601（UTC）、GMAT UTCGregorian（`09 Nov 2026 15:00:00.000`）、數字（GMAT UTCModJulian，
JD − 2430000.0）。經緯高等地球固定座標的格式先用 tools/gmat_state_convert.py 轉成這個格式。
"""
import datetime as _dt
import json
import math
import os

import numpy as np

from physics import EARTH_MU, RE_VAL, get_r0_v0, propagate

SIDES = ("pursuer", "evader")
GMAT_MJD_ZERO = _dt.datetime(1941, 1, 5, 12, 0, 0, tzinfo=_dt.timezone.utc)   # GMAT ModJulian = JD − 2430000.0
_GMAT_GREGORIAN = "%d %b %Y %H:%M:%S.%f"
ELEMENT_KEYS = ("sma", "ecc", "inc", "raan", "aop", "ta")


def parse_epoch(x) -> _dt.datetime:
    """epoch → UTC datetime（aware）。接受 ISO 8601、GMAT UTCGregorian、數字（GMAT UTCModJulian）。"""
    if isinstance(x, _dt.datetime):
        return x if x.tzinfo else x.replace(tzinfo=_dt.timezone.utc)
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        if not math.isfinite(x):
            raise ValueError(f"epoch 不是有限數字：{x!r}")
        return GMAT_MJD_ZERO + _dt.timedelta(days=float(x))
    if isinstance(x, str):
        s = x.strip()
        try:
            d = _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
            return d if d.tzinfo else d.replace(tzinfo=_dt.timezone.utc)
        except ValueError:
            pass
        for fmt in (_GMAT_GREGORIAN, "%d %b %Y %H:%M:%S"):
            try:
                return _dt.datetime.strptime(s, fmt).replace(tzinfo=_dt.timezone.utc)
            except ValueError:
                pass
    raise ValueError(f"看不懂 epoch {x!r}：請用 ISO 8601（2026-11-09T00:00:00Z）、"
                     "GMAT UTCGregorian（09 Nov 2026 00:00:00.000）或 GMAT UTCModJulian 數字")


def _ship_state(name, entry, mu):
    if "r_km" in entry or "v_kms" in entry:
        r = np.asarray(entry["r_km"], dtype=np.float64).reshape(3)
        v = np.asarray(entry["v_kms"], dtype=np.float64).reshape(3)
    elif "elements" in entry:
        el = {k.lower(): float(val) for k, val in entry["elements"].items()}
        missing = [k for k in ELEMENT_KEYS if k not in el]
        if missing:
            raise ValueError(f"{name} 的 elements 缺 {missing}（要 {list(ELEMENT_KEYS)}，角度用度）")
        r, v = get_r0_v0(**{k: el[k] for k in ELEMENT_KEYS}, mu=mu)
    else:
        raise ValueError(f"{name} 要給 r_km + v_kms（EarthMJ2000Eq）或 elements")
    if not (np.all(np.isfinite(r)) and np.all(np.isfinite(v))):
        raise ValueError(f"{name} 狀態有非有限數值")
    rn, vn = float(np.linalg.norm(r)), float(np.linalg.norm(v))
    if rn > 1e6:
        raise ValueError(f"{name} 位置 |r|={rn:.3g}：看起來是公尺，要用 km")
    if vn > 100:
        raise ValueError(f"{name} 速度 |v|={vn:.3g}：看起來是 m/s，要用 km/s")
    if rn < RE_VAL:
        raise ValueError(f"{name} 距地心 {rn:.1f} km 在地表下（地球半徑 {RE_VAL} km）")
    return r, v


def align_initial_states(spec, mu=EARTH_MU) -> dict:
    """局勢檔（dict 或 JSON 路徑）→ 第 1 回合起點雙方的 (r, v)。

    回傳 {"epoch": 較晚的 datetime 或 None, "pursuer": (r, v), "evader": (r, v),
          "propagated_sec": {"pursuer": s, "evader": s}}——早出發的那艘被二體傳播了幾秒。"""
    if isinstance(spec, (str, os.PathLike)):
        with open(spec, encoding="utf-8") as f:
            spec = json.load(f)
    states, epochs = {}, {}
    for side in SIDES:
        if side not in spec:
            raise ValueError(f"局勢檔缺 {side!r}")
        states[side] = _ship_state(side, spec[side], mu)
        epochs[side] = parse_epoch(spec[side]["epoch"]) if spec[side].get("epoch") is not None else None
    if (epochs["pursuer"] is None) != (epochs["evader"] is None):
        raise ValueError("epoch 要兩艘都給或都不給（只給一艘無法對齊出發時刻）")
    prop = {s: 0.0 for s in SIDES}
    common = None
    if epochs["pursuer"] is not None:
        common = max(epochs.values())
        for side in SIDES:
            dt = (common - epochs[side]).total_seconds()
            if dt > 0.0:
                r, v = states[side]
                states[side] = propagate(mu, r, v, dt, 0)
                prop[side] = dt
    return {"epoch": common, "pursuer": states["pursuer"], "evader": states["evader"], "propagated_sec": prop}
