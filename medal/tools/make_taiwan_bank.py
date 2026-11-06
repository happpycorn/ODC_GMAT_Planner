"""用 GMAT 產生台灣上空入軌的金／銅牌賽題庫。

兩艘船都以 EarthFixed + SphericalAZFPA 指定台灣上空的近圓軌道；較早的船依
game.initial_state.align_initial_states 以二體模型傳播到較晚的 UTC 曆元。

用法：
    .venv/bin/python tools/make_taiwan_bank.py --n 120 --seed 0 \
        --out configs/scenarios/taiwan_launch_bank.json
"""
import argparse
import datetime as dt
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.initial_state import align_initial_states  # noqa: E402
from physics import EARTH_MU, RE_VAL, get_r0_v0  # noqa: E402
from physics.frames import rv2coe  # noqa: E402
from tools.gmat_state_convert import run_convert  # noqa: E402
from tools.gmat_verify import GMAT_CONSOLE  # noqa: E402

BASE_EPOCH = dt.datetime(2026, 11, 9, tzinfo=dt.timezone.utc)
EARTH_OMEGA_RAD_S = 7.2921158553e-5
LATITUDE_DEG = 23.5
LONGITUDE_DEG = 120.0
MAX_ATTEMPTS_PER_PAIR = 2000


def _gmat_epoch(epoch):
    """UTC datetime → GMAT UTCGregorian；輸入曆元固定到毫秒。"""
    return epoch.strftime("%d %b %Y %H:%M:%S.%f")[:-3]


def _spacecraft_input(rng, epoch):
    """台灣上空一艘船的 GMAT Spacecraft 欄位。"""
    rmag = RE_VAL + rng.uniform(470.0, 530.0)
    v_circular = math.sqrt(EARTH_MU / rmag)
    v_rotation = EARTH_OMEGA_RAD_S * rmag * math.cos(math.radians(LATITUDE_DEG))
    return {
        "DateFormat": "UTCGregorian",
        "Epoch": _gmat_epoch(epoch),
        "CoordinateSystem": "EarthFixed",
        "DisplayStateType": "SphericalAZFPA",
        "RMAG": float(rmag),
        "DEC": LATITUDE_DEG,
        "RA": LONGITUDE_DEG,
        "AZI": float(90.0 + rng.uniform(-3.0, 3.0)),
        "FPA": float(90.0 + rng.uniform(-0.2, 0.2)),
        "VMAG": float((v_circular - v_rotation) * rng.uniform(0.995, 1.005)),
    }


def _valid_leo(state):
    """對齊後的六根數需符合決賽 LEO 範圍，且重建位置誤差小於 1 mm。"""
    r, v = state
    el = rv2coe(r, v)
    if not (math.isfinite(el["sma"]) and 0.0 <= el["ecc"] <= 0.01
            and RE_VAL + 400.0 <= el["sma"] <= RE_VAL + 1500.0
            and el["sma"] * (1.0 - el["ecc"]) >= RE_VAL + 300.0):
        return False
    r2, v2 = get_r0_v0(**el)
    return (np.linalg.norm(r2 - r) < 1e-6
            and np.linalg.norm(v2 - v) < 1e-9)


def _one_pair(rng, index, console):
    """產生並檢查一對；GMAT 執行失敗直接回報，不重試相同的環境錯誤。"""
    for _ in range(MAX_ATTEMPTS_PER_PAIR):
        gap_ms = round(rng.uniform(0.0, 24.0) * 3600000.0)
        gap = dt.timedelta(milliseconds=gap_ms)
        later = BASE_EPOCH + gap
        if index % 2 == 0:
            epochs = {"pursuer": BASE_EPOCH, "evader": later}
        else:
            epochs = {"pursuer": later, "evader": BASE_EPOCH}
        gmat_input = {side: _spacecraft_input(rng, epochs[side]) for side in ("pursuer", "evader")}
        converted = run_convert(gmat_input, console=console)
        aligned = align_initial_states(converted)
        if not all(_valid_leo(aligned[side]) for side in ("pursuer", "evader")):
            continue
        dist0 = np.linalg.norm(aligned["pursuer"][0] - aligned["evader"][0])
        if dist0 < 40.0:
            # R_cap 最大 20 km；避免任何規則抽樣在開局就捕獲。
            continue
        pair = {
            side: {"r_km": aligned[side][0].tolist(), "v_kms": aligned[side][1].tolist()}
            for side in ("pursuer", "evader")
        }
        pair.update({
            "epoch": aligned["epoch"].isoformat().replace("+00:00", "Z"),
            "epoch_gap_h": gap_ms / 3600000.0,
            "propagated": aligned["propagated_sec"],
            "gmat_input": gmat_input,
        })
        return pair
    raise RuntimeError(f"第 {index + 1} 對重抽 {MAX_ATTEMPTS_PER_PAIR} 次仍無法符合 LEO／距離條件")


def make_bank(n=120, seed=0, console=GMAT_CONSOLE):
    """回傳可直接寫成 JSON 的題庫；每對狀態均由 GmatConsole 換算。"""
    if n < 1:
        raise ValueError("--n 必須是正整數")
    console = os.path.abspath(os.path.expanduser(console))
    rng = np.random.default_rng(seed)
    pairs = []
    for index in range(n):
        pairs.append(_one_pair(rng, index, console))
        if (index + 1) % 20 == 0 or index + 1 == n:
            print(f"GMAT 已產生 {index + 1}/{n} 對", file=sys.stderr, flush=True)
    return {
        "pairs": pairs,
        "generated": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "gmat_console": console,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=120, help="題庫配對數（預設 120）")
    ap.add_argument("--seed", type=int, default=0, help="亂數種子（預設 0）")
    ap.add_argument("--out", default="configs/scenarios/taiwan_launch_bank.json", help="輸出 JSON 路徑")
    ap.add_argument("--gmat-console", default=GMAT_CONSOLE, help="GmatConsole 執行檔路徑")
    args = ap.parse_args()
    bank = make_bank(args.n, args.seed, args.gmat_console)
    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(bank, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"→ {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
