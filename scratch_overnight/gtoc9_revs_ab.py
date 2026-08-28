"""LAMBERT_MAX_REVS 0 vs 4 的**受控** A/B：同一批配對、同一個 SEED。

為什麼需要（2026-08-29）：40 組真實軌道的無 seed 比較顯示 REVS=4 淨負 7.55 分
（4 好 / 3 壞 / 33 持平，最差一組 -9.94）。但那兩批是各自獨立跑的（SEED: null），
分不出「多圈害的」還是「重跑變異」。

兩個互斥的假設：
  (a) 純粹是重跑變異 -> 受控 A/B 下兩邊應該幾乎相同
  (b) 多圈讓**慢解變便宜**，把搜尋吸引到慢解盆地，而陡峭的時間項讓慢解是陷阱
      -> 受控 A/B 下 REVS=4 會系統性地偏向較慢、分數較低的解

結構論證只保證「同一個決策向量下多圈不會更差」，**不保證搜尋會落在同一個盆地**。
所以 (b) 是真的有可能，不能用論證打發。

設 SEED 會讓工具退回單執行緒（見 _optimize_burn_case 的說明），所以會比較慢。
"""
import contextlib, io as _io, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import warnings; warnings.filterwarnings("ignore")
from scratch_overnight.gtoc9_orbits import load
from scratch_overnight.gtoc9_stress import build_cfg
from src.optimizer import MissionOptimizer

if __name__ == "__main__":
    deb = {d["id"]: d for d in load()}
    base = json.load(open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "scratch_overnight", "gtoc9_stress_results_revs0.json")))
    pairs = [(r["a_id"], r["b_id"], r["plane_deg"])
             for r in base if r.get("status") == "ok"]
    n = int(os.environ.get("N_PAIRS", "8"))
    seed = int(os.environ.get("AB_SEED", "12345"))
    # 平均取樣涵蓋各種平面夾角
    step = max(1, len(pairs) // n)
    pairs = pairs[::step][:n]

    print("=" * 84)
    print(f"LAMBERT_MAX_REVS 受控 A/B（{len(pairs)} 組配對，SEED={seed}，單執行緒）")
    print("=" * 84)
    print(f"{'A':>4}{'B':>5}{'平面°':>8}{'REVS=0':>10}{'REVS=4':>10}{'差':>8}"
          f"{'T0(s)':>10}{'T4(s)':>10}", flush=True)
    print("-" * 84)
    tot = 0.0
    for a_id, b_id, ang in pairs:
        row = {}
        for revs in (0, 4):
            cfg = build_cfg(deb[a_id], deb[b_id])
            cfg["strategy"]["LAMBERT_MAX_REVS"] = revs
            cfg["optimization"]["SEED"] = seed
            cfg["optimization"]["MAXITER"] = 400
            try:
                opt = MissionOptimizer(cfg)
                with contextlib.redirect_stdout(_io.StringIO()):
                    out = opt.run_study()
                row[revs] = out[2] if out and out[0] is not None else None
            except Exception as e:
                row[revs] = None
        if row.get(0) is None or row.get(4) is None:
            print(f"{a_id:>4}{b_id:>5}{ang:>8.1f}{'  一邊失敗':>20}", flush=True)
            continue
        d = row[4]["score"] - row[0]["score"]
        tot += d
        print(f"{a_id:>4}{b_id:>5}{ang:>8.1f}{row[0]['score']:>10.2f}"
              f"{row[4]['score']:>10.2f}{d:>+8.2f}"
              f"{row[0]['T_team']:>10,.0f}{row[4]['T_team']:>10,.0f}", flush=True)
    print("-" * 84)
    print(f"總計 {tot:+.2f} 分")
    print("解讀：接近 0 -> 先前的淨負是重跑變異；系統性為負 -> 多圈把搜尋吸到慢解盆地")
    print("AB DONE")
