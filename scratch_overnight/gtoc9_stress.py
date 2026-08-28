"""拿 GTOC-9 的真實 LEO 碎片軌道當外部測資，壓力測試整條流程。

目的不是「拿到好分數」，是回答：**對我沒設計過的幾何，工具會不會崩、會不會交出爛解。**
自製測資的盲點在於編測資的人跟寫程式的人是同一個，這裡用外部軌道打破那個相關性。

軌道來源與限制見 gtoc9_orbits.py 的說明（相對相位是任意的、不能拿來比 GTOC-9 的答案）。

計分用**官方公布的真實參數**（範例題目那組）。合理性：碎片週期 5,824~6,174s，
T_max = 4xT_A 約 23,900s，跟官方範例的 23,204s 幾乎一樣，所以那組參數的尺度是對的。

分層抽樣：依「兩軌道平面夾角」分 5 層，每層各抽 N 組，確保不會全是相似幾何。

跑法：uv run python scratch_overnight/gtoc9_stress.py
輸出：scratch_overnight/gtoc9_stress_results.json（每跑完一組就寫一次，中途掛掉不會全丟）
"""

import contextlib
import io as _io
import json
import math
import os
import sys
import time
import traceback

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import warnings
warnings.filterwarnings("ignore")
from scratch_overnight.gtoc9_orbits import load, period, MU
from src.optimizer import MissionOptimizer, effective_burns

# 官方 2026-08-28 公布的計分參數（已換算成 m/s 制，見 SCENARIOS.md 的單位陷阱說明）
OFFICIAL = {"k_t": 0.003982, "C_t": 3763.526, "k_v": 0.0011862, "C_v": 2955.723}
# 結果檔可以用環境變數換名字，方便做「同一批配對、不同設定」的 A/B
TAG = os.environ.get("STRESS_TAG", "")
OUT = os.path.join(REPO, "scratch_overnight",
                   f"gtoc9_stress_results{TAG}.json")


def h_hat(d):
    i, W = math.radians(d["INC"]), math.radians(d["RAAN"])
    return np.array([math.sin(W) * math.sin(i), -math.cos(W) * math.sin(i), math.cos(i)])


def plane_angle(a, b):
    return math.degrees(math.acos(float(np.clip(np.dot(h_hat(a), h_hat(b)), -1, 1))))


def make_pairs(deb, per_bin=8, seed=20260829):
    """依平面夾角分層抽樣，避免整批都是相似幾何。"""
    rng = np.random.default_rng(seed)
    bins = [(0, 10), (10, 30), (30, 60), (60, 120), (120, 180)]
    buckets = {b: [] for b in bins}
    idx = list(range(len(deb)))
    for _ in range(20000):
        a, b = rng.choice(idx, 2, replace=False)
        ang = plane_angle(deb[a], deb[b])
        for lo, hi in bins:
            if lo <= ang < hi and len(buckets[(lo, hi)]) < per_bin:
                buckets[(lo, hi)].append((int(a), int(b), ang))
                break
        if all(len(v) >= per_bin for v in buckets.values()):
            break
    pairs = []
    for b in bins:
        pairs.extend(buckets[b])
    return pairs


def build_cfg(A, B):
    return {
        "orbit_A": {k: A[k] for k in ("SMA", "ECC", "INC", "RAAN", "AOP", "TA")},
        "orbit_B": {k: B[k] for k in ("SMA", "ECC", "INC", "RAAN", "AOP", "TA")},
        "rules": dict({"MAX_DV_MPS": 1500.0, "MIN_MANEUVER_INTERVAL_SEC": 100.0,
                       "T_MAX_PERIOD_MULTIPLE": 4.0}, **OFFICIAL),
        "strategy": {"GRAVITY_DEGREE": 4, "MISS_TOLERANCE_KM": 5.0,
                     "LAMBERT_MAX_REVS": int(os.environ.get("STRESS_REVS", "4"))},
        "optimization": {"MAX_BURNS": [1, 2, 3], "MAXITER": 600, "POPSIZE": 20,
                         "NUM_THREADS": 12, "MAX_EARLY_STOP": 60, "TOL": 0.01,
                         "SEED": None},
    }


if __name__ == "__main__":
    deb = load()
    pairs = make_pairs(deb, per_bin=int(os.environ.get("PER_BIN", "8")))
    print("=" * 100)
    print("GTOC-9 真實軌道壓力測試（官方計分參數）")
    print("=" * 100)
    print(f"{len(pairs)} 組配對，分層依平面夾角\n", flush=True)
    print(f"{'#':>3} {'A':>4} {'B':>4} {'平面°':>7} {'棒數':>5} {'實用':>5} "
          f"{'ΔV(m/s)':>10} {'T(s)':>10} {'Δr(m)':>9} {'違規':>5} {'Score':>8} {'秒':>6}", flush=True)
    print("-" * 100, flush=True)

    # 續跑：已經跑過的組別直接沿用（被中斷過一次，不想每次都從頭）
    results, done = [], set()
    if os.path.exists(OUT):
        try:
            results = json.load(open(OUT))
            done = {(r["a_id"], r["b_id"]) for r in results if r.get("status") == "ok"}
            print(f"（續跑：{OUT} 已有 {len(done)} 組成功結果，會跳過）\n", flush=True)
        except Exception:
            results, done = [], set()

    crashes = [r for r in results if r.get("status") == "crash"]
    for n, (ia, ib, ang) in enumerate(pairs, 1):
        if (deb[ia]["id"], deb[ib]["id"]) in done:
            continue
        A, B = deb[ia], deb[ib]
        cfg = build_cfg(A, B)
        rec = {"n": n, "a_id": A["id"], "b_id": B["id"], "plane_deg": ang,
               "T_max": 4 * period(A)}
        t0 = time.time()
        try:
            opt = MissionOptimizer(cfg)
            buf = _io.StringIO()
            with contextlib.redirect_stdout(buf):
                out = opt.run_study()
            if out is None or out[0] is None:
                rec.update(status="無解", elapsed=time.time() - t0)
                print(f"{n:>3} {A['id']:>4} {B['id']:>4} {ang:>7.1f}  "
                      f"{'全部撞毀或違規':>28}", flush=True)
            else:
                _burns, _times, info = out
                b = int(info["num_burns"])
                rec.update(status="ok", burns=b,
                           eff=effective_burns(b, info["x"]),
                           dv=info["total_dv_mps"], t_team=info["T_team"],
                           miss_m=info["miss_km"] * 1000.0,
                           viol=int(info["penalty_count"]), score=info["score"],
                           dc_converged=bool(info.get("dc_converged", True)),
                           elapsed=time.time() - t0)
                print(f"{n:>3} {A['id']:>4} {B['id']:>4} {ang:>7.1f} {b:>5} {rec['eff']:>5} "
                      f"{rec['dv']:>10,.1f} {rec['t_team']:>10,.0f} "
                      f"{rec['miss_m']:>9,.1f} {rec['viol']:>5} "
                      f"{rec['score']:>8.2f} {rec['elapsed']:>6.0f}", flush=True)
        except Exception as exc:
            rec.update(status="crash", error=f"{type(exc).__name__}: {exc}",
                       tb=traceback.format_exc()[-1500:], elapsed=time.time() - t0)
            crashes.append(rec)
            print(f"{n:>3} {A['id']:>4} {B['id']:>4} {ang:>7.1f}  🔴 崩潰 "
                  f"{type(exc).__name__}: {str(exc)[:50]}", flush=True)
        results.append(rec)
        with open(OUT, "w") as f:
            json.dump(results, f, indent=1, default=float)

    print("-" * 100)
    ok = [r for r in results if r.get("status") == "ok"]
    print(f"完成 {len(results)} 組：成功 {len(ok)}、無解 "
          f"{sum(1 for r in results if r.get('status')=='無解')}、崩潰 {len(crashes)}")
    if ok:
        sc = [r["score"] for r in ok if "score" in r]
        vi = [r for r in ok if r.get("viol", 0) > 0]
        el = [r["elapsed"] for r in ok]
        print(f"  Score  min {min(sc):.2f}  中位 {sorted(sc)[len(sc)//2]:.2f}  max {max(sc):.2f}")
        print(f"  有違規的：{len(vi)}/{len(ok)}")
        print(f"  耗時   min {min(el):.0f}s  中位 {sorted(el)[len(el)//2]:.0f}s  max {max(el):.0f}s")
        deg = [r for r in ok if r.get("eff", 0) < r.get("burns", 0)]
        print(f"  退化解（實用棒數 < 名目）：{len(deg)}/{len(ok)}")
    print(f"\n🔴 崩潰 {len(crashes)} 組" + ("（詳見 json 的 tb 欄位）" if crashes else ""))
    print(f"📄 {OUT}")
    print("GTOC9 STRESS DONE")
