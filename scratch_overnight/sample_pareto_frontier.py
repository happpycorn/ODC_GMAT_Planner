"""官方範例題目的解空間地圖：把「攔截時間 vs 最省 Δv」的取捨曲線量出來。

為什麼要做這個：官方規則第 5 節寫明 k_t/C_t/k_v/C_v「will be announced before each
competition」，也就是**當天才知道**。而這題的取捨很大——實測單棒 412 m/s 但要 6,121s，
官方參考解 2,241 m/s 只要 3,212s。哪個分數高完全取決於當天公告的參數。

所以正確的準備方式不是猜參數，是**先把整條取捨曲線量出來**：當天拿到 k_t/C_t，直接
在曲線上算哪一點分數最高，不用現場重新搜尋。

做法：用 rules.T_MAX_SEC 當**硬性**的抵達時間上限（這個欄位本來是給雙曲線排位賽用的，
拿來當時間上限剛好），計分只留燃料項有梯度（k_t 設到 1e-9 讓時間項在全範圍是常數，
不會干擾），就等於在解「時間 <= cap 的前提下最省要多少 Δv」。

每個時間上限都跑 MAX_BURNS=[1,2,3]，順便看**幾棒**才是那個時間尺度的正確答案。
"""

import copy
import json
import os
import sys
import time
import io
import contextlib

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import warnings
warnings.filterwarnings("ignore")
from src.optimizer import MissionOptimizer, effective_burns

BASE = json.load(open(os.path.join(REPO_ROOT, "configs", "official_sample.json")))
REF_DV, REF_T = 2241.427, 3211.737          # 官方參考解
T_MAX_FULL = 23204.2                         # 4 x A 的週期

# 時間上限：密集鋪在參考解附近（那是勝負分水嶺），稀疏鋪到完整 T_max
CAPS = [2000.0, 2500.0, 3000.0, REF_T, 3600.0, 4200.0, 5000.0,
        5600.0, 6200.0, 7000.0, 9000.0, 12000.0, T_MAX_FULL]


def run_cap(cap, maxiter=300, max_revs=0):
    cfg = copy.deepcopy(BASE)
    cfg["rules"]["T_MAX_SEC"] = float(cap)
    cfg["rules"].pop("T_MAX_PERIOD_MULTIPLE", None)
    # 時間項全範圍常數（k_t -> 0），只留燃料項有梯度 = 純粹「最省油」
    cfg["rules"].update({"k_t": 1e-9, "C_t": 1.0, "k_v": 0.002, "C_v": 1000.0})
    cfg["strategy"]["LAMBERT_MAX_REVS"] = int(max_revs)
    cfg["optimization"].update({"MAX_BURNS": [1, 2, 3], "MAXITER": maxiter,
                                "POPSIZE": 20, "NUM_THREADS": 12, "MAX_EARLY_STOP": 40})
    cfg.pop("local", None)

    opt = MissionOptimizer(cfg)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):          # run_study 很吵，這裡只要數字
        out = opt.run_study()
    if out is None or out[0] is None:
        return None, None

    rows = []
    for b, r in sorted(opt.burn_case_results.items()):
        if r.get("best_x") is None or r["fitness"] >= 0.0:
            continue
        try:
            m = opt.mission_metrics(r["best_x"], b)
        except Exception:
            continue
        m["burns"] = b
        m["eff"] = effective_burns(b, r["best_x"])
        rows.append(m)
    # 只留**合法**解。搜尋在無解的時間上限下會去買違規（每次只扣 10 分，而最後一棒是
    # Lambert 反算出來的、沒有上界），實測 cap=2,000s 交出 23,052 m/s——那不是「最省」，
    # 是「違規解裡分數最高」。這條曲線要的是能真的交出去的方案。
    legal = [m for m in rows if m["penalty_count"] == 0]
    if not legal:
        return None, rows
    return min(legal, key=lambda m: m["dv_mps"]), rows


if __name__ == "__main__":
    print("=" * 96, flush=True)
    print("官方範例題目：攔截時間 vs 最省 Δv 的取捨曲線", flush=True)
    print("=" * 96, flush=True)
    print(f"對照組 — 官方參考解：2 棒、{REF_DV:,.1f} m/s、抵達 {REF_T:,.1f}s\n", flush=True)
    print(f"{'時間上限(s)':>12}{'最省 ΔV(m/s)':>15}{'實際抵達(s)':>13}"
          f"{'名目棒數':>9}{'實際棒數':>9}{'Δr(m)':>10}{'vs 參考解':>12}", flush=True)
    print("-" * 96, flush=True)

    import os as _os
    MAX_REVS = int(_os.environ.get("PARETO_MAX_REVS", "0"))
    print(f"LAMBERT_MAX_REVS = {MAX_REVS}"
          f"（設環境變數 PARETO_MAX_REVS 可改；0 = 只看不繞圈的轉移）\n", flush=True)

    t0 = time.time()
    results = []
    for cap in CAPS:
        out = run_cap(cap, max_revs=MAX_REVS)
        if out is None:
            print(f"{cap:>12,.0f}{'搜尋整個失敗':>15}", flush=True)
            results.append((cap, None, None))
            continue
        best, rows = out
        if best is None:
            worst = min(rows, key=lambda m: m["dv_mps"]) if rows else None
            extra = (f"（最好的違規解 {worst['dv_mps']:,.0f} m/s，"
                     f"{worst['penalty_count']} 次違規）" if worst else "")
            print(f"{cap:>12,.0f}{'沒有合法解':>15}   {extra}", flush=True)
            results.append((cap, None, rows))
            continue
        ratio = REF_DV / best["dv_mps"]
        print(f"{cap:>12,.0f}{best['dv_mps']:>15,.1f}{best['t_team']:>13,.1f}"
              f"{best['burns']:>9d}{best['eff']:>9d}{best['miss_km']*1000:>10,.1f}"
              f"{ratio:>11.2f}x", flush=True)
        results.append((cap, best, rows))

    print("-" * 96)
    print(f"總耗時 {time.time()-t0:.1f}s")

    print("\n=== 每個時間上限下，各燃燒次數各自能做到多省 ===")
    print(f"{'時間上限(s)':>12}{'1 棒':>12}{'2 棒':>12}{'3 棒':>12}")
    print("-" * 50)
    print("（括號 = 該解違規，不能交）")
    for cap, _best, rows in results:
        if not rows:
            print(f"{cap:>12,.0f}{'—':>12}{'—':>12}{'—':>12}")
            continue
        by = {r["burns"]: (r["dv_mps"], r["penalty_count"]) for r in rows}
        cells = ""
        for b in (1, 2, 3):
            if b not in by:
                cells += f"{'—':>12}"
            else:
                dv, pen = by[b]
                cells += f"{('(%s)' % format(dv, ',.0f')) if pen else format(dv, ',.1f'):>12}"
        print(f"{cap:>12,.0f}{cells}")

    with open(os.path.join(REPO_ROOT, "scratch_overnight",
                           "sample_pareto_frontier.json"), "w") as f:
        json.dump([{"cap": c, "best": b, "all": r} for c, b, r in results],
                  f, indent=2, default=float)
    print("\n📄 數字存到 scratch_overnight/sample_pareto_frontier.json")
