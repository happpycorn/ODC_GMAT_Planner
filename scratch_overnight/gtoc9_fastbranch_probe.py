"""GTOC-9 壓力測試裡那些「74 分」的配對，到底是快解不存在，還是工具沒找到？

觀察（2026-08-29）：40 組真實軌道配對裡，多數交出約 74 分——Δv 極省（45~520 m/s）
但抵達時間 21,000~24,000s（接近 T_max）。少數交出 93~96 分，抵達 1,600~3,100s。

用官方計分參數算一下這個取捨：
  燃料 45 -> 1,500 m/s ：分數只掉 3.0（24.23 -> 21.22）
  時間 21,500 -> 3,000s：分數從 0 拉到 22
=> **只要快解存在且總 Δv 在 3,000 m/s 以內，就該淨賺約 19 分。**

所以交出 74 分要嘛是「快解真的不存在」，要嘛是「工具沒找到」——這兩件事的處理方式
完全不同，必須分清楚。官方範例題目上就是後者（修 check_constraints 之前只找得到
73.84，修完 90.33）。

做法：對挑出來的配對，用 rules.T_MAX_SEC 硬把抵達時間上限壓到 4,000s，逼搜尋只能
在快解那一段找。找得到 -> 原本那 74 分是**沒找到**；找不到 -> 快解真的不存在。

跑法：uv run python scratch_overnight/gtoc9_fastbranch_probe.py
"""

import contextlib
import io as _io
import json
import math
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import warnings
warnings.filterwarnings("ignore")
from scratch_overnight.gtoc9_orbits import load
from scratch_overnight.gtoc9_stress import build_cfg, OUT
from src.optimizer import MissionOptimizer, effective_burns

KT, CT, KV, CV = 0.003982, 3763.526, 0.0011862, 2955.723
CAPS = [3000.0, 4000.0, 6000.0, 9000.0]


def score(dr_km, t, dv, pen=0):
    return (50.0 * math.exp(-(max(dr_km, 5.0) - 5.0) / 100.0)
            + 25.0 / (1.0 + math.exp(KT * (t - CT)))
            + 25.0 / (1.0 + math.exp(KV * (dv - CV))) - 10.0 * pen)


def run(cfg, threads):
    cfg = json.loads(json.dumps(cfg))
    cfg["optimization"]["NUM_THREADS"] = threads
    opt = MissionOptimizer(cfg)
    with contextlib.redirect_stdout(_io.StringIO()):
        out = opt.run_study()
    if out is None or out[0] is None:
        return None
    return out[2]


if __name__ == "__main__":
    deb = {d["id"]: d for d in load()}
    prev = json.load(open(OUT))
    slow = [r for r in prev if r.get("status") == "ok"
            and r.get("score", 0) < 80 and r.get("t_team", 0) > 15000]
    n_take = int(os.environ.get("N_TAKE", "4"))
    threads = int(os.environ.get("THREADS", "12"))
    slow = slow[:n_take]

    print("=" * 96)
    print("那些「74 分」的配對：快解不存在，還是沒找到？")
    print("=" * 96)
    print(f"從壓力測試裡挑 {len(slow)} 組（分數 < 80 且抵達 > 15,000s）\n", flush=True)

    for r in slow:
        A, B = deb[r["a_id"]], deb[r["b_id"]]
        print(f"--- A={A['id']} B={B['id']}  平面 {r['plane_deg']:.1f}°  "
              f"原本：{r['dv']:,.1f} m/s @ {r['t_team']:,.0f}s = {r['score']:.2f} 分 ---",
              flush=True)
        base = build_cfg(A, B)
        for cap in CAPS:
            cfg = json.loads(json.dumps(base))
            cfg["rules"]["T_MAX_SEC"] = cap
            cfg["rules"].pop("T_MAX_PERIOD_MULTIPLE", None)
            t0 = time.time()
            try:
                info = run(cfg, threads)
            except Exception as e:
                print(f"    上限 {cap:>6,.0f}s : 崩潰 {type(e).__name__}", flush=True)
                continue
            if info is None:
                print(f"    上限 {cap:>6,.0f}s : 找不到解", flush=True)
                continue
            dv, t, pen = info["total_dv_mps"], info["T_team"], info["penalty_count"]
            sc = score(info["miss_km"], t, dv, pen)
            gain = sc - r["score"]
            flag = "  <<< 比原本好" if gain > 0.5 else ""
            print(f"    上限 {cap:>6,.0f}s : {dv:>9,.1f} m/s @ {t:>8,.0f}s  "
                  f"違規 {pen}  -> {sc:>6.2f} 分 ({gain:+6.2f}){flag}  [{time.time()-t0:.0f}s]",
                  flush=True)
    print("\nFASTPROBE DONE")
