"""HAP-32 / CP6 第二關：把 sweep 旗標的落後案例查清楚。

sweep 的 oracle 用**二體** Lambert 算 ΔV、假設精確命中（Δr=0）——那是**上界**，J2 下不一定
可達。所以 sweep 的「落後」可能是三種：
  (a) 真搜尋失敗——J2 重播後 oracle 仍遠高於最佳化器；
  (b) oracle 樂觀——二體格子在 J2 下飛會偏，真實可達分數其實 ≈ 最佳化器；
  (c) 預算/REVS 假象——sweep 用 MAXITER=120、REVS=4（CP5 發現 REVS=4 有時更差），
      拉高預算或改 best-of REVS{0,4} 就追平。

這支對每個旗標幾何：
  1. 重算網格，取分數前 K 格用**真傳播器 J2 重播**（porkchop_verify 的手法）→ 誠實 oracle。
  2. 用更高預算（MAXITER=400）重跑 REVS=4 跟 REVS=0，取 max → best-of 最佳化器。
  3. 判定：誠實 oracle 減 best-of 最佳化器 > 2 分 → (a) 真搜尋失敗；否則是 (b)/(c)。

跑法：uv run python scratch_overnight/porkchop_verify_flagged.py
"""

import json
import math
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import warnings
warnings.filterwarnings("ignore")
import numpy as np
from poliastro.core.iod import izzo

from src.optimizer import MissionOptimizer
from src.core_math import propagate_dop853, fast_norm
from src.scorer import calculate_score
from porkchop_grid import build_ephemeris, porkchop
from porkchop_oracle_sweep import build_config, GRID_H, MAX_REVS

RESULTS = os.path.join(REPO, "scratch_overnight", "porkchop_oracle_results.json")
OUT = os.path.join(REPO, "scratch_overnight", "porkchop_verify_flagged_results.json")
TOPK = 25
EPS = 2.0


def honest_oracle(opt, h=GRID_H, max_revs=MAX_REVS, topk=TOPK):
    """網格分數前 K 格，用 J2 真傳播器重播，回傳真實可達的最佳單棒分數。"""
    times = np.arange(0.0, opt.T_max + 1e-9, h)
    n = len(times)
    grav = (opt.J2_VAL, opt.J3_VAL, opt.J4_VAL, opt.RE_VAL)
    RB, VB = build_ephemeris(opt.B_r0, opt.B_v0, times, 60.0, opt.MU, *grav)
    RA, VA = build_ephemeris(opt.A_r0, opt.A_v0, times, 60.0, opt.MU, *grav)
    min_tof_steps = max(1, int(math.ceil(opt.MIN_COAST_TIME / h)))
    DV, MREV, NSOL, TANG = porkchop(RB, VB, RA, h, max_revs, min_tof_steps)
    valid = np.isfinite(DV)
    ARR = times[None, :] * np.ones((n, 1))
    S = np.where(valid,
                 50.0
                 + 25.0 / (1.0 + np.exp(np.clip(opt.k_t * (ARR - opt.C_t), -700, 700)))
                 + 25.0 / (1.0 + np.exp(np.clip(opt.k_v * (DV * 1000.0 - opt.C_v), -700, 700)))
                 - 10.0 * (DV > opt.MAX_DV), -np.inf)
    two_body_best = float(np.nanmax(S))
    flat = np.argsort(S, axis=None)[::-1][:topk]

    def state(r0, v0, t):
        return propagate_dop853(r0, v0, float(t), 60.0, opt.MU, *grav)

    best_real = -1e9
    for f in flat:
        i, j = np.unravel_index(f, S.shape)
        if not np.isfinite(S[i, j]):
            continue
        t_dep, t_arr = float(times[i]), float(times[j])
        tof = t_arr - t_dep
        r1, v1 = state(opt.B_r0, opt.B_v0, t_dep)
        r2, _ = state(opt.A_r0, opt.A_v0, t_arr)
        best = None
        for mv in range(0, max_revs + 1):
            for lp in (0, 1):
                if mv == 0 and lp == 1:
                    continue
                for pg in (0, 1):
                    try:
                        vt, _ = izzo(opt.MU, r1, r2, tof, M=mv, prograde=(pg == 0),
                                     lowpath=(lp == 0), numiter=35, rtol=1e-8)
                    except Exception:
                        continue
                    dv = fast_norm(vt - v1)
                    if best is None or dv < best[0]:
                        best = (dv, vt)
        if best is None:
            continue
        dv, vt = best
        rf, _ = state(r1, vt, tof)                       # 燒完真的飛一遍（J2）
        miss = float(np.linalg.norm(rf - r2))
        pen = 1 if dv > opt.MAX_DV else 0
        sc = calculate_score(miss, t_arr, dv * 1000.0, pen, opt.k_t, opt.C_t, opt.k_v, opt.C_v)
        best_real = max(best_real, float(sc))
    return two_body_best, (None if best_real < -1e8 else round(best_real, 3))


def optimize(A, B, seed, revs, maxiter):
    cfg = build_config(A, B, seed)
    cfg["optimization"]["MAXITER"] = maxiter
    cfg["optimization"]["POPSIZE"] = 20
    cfg["strategy"]["LAMBERT_MAX_REVS"] = revs
    _b, _t, mi = MissionOptimizer(cfg).run_study()
    return None if mi is None else round(float(mi["score"]), 3)


def main():
    data = json.load(open(RESULTS))
    flagged = [r for r in data if r.get("violation")]
    print(f"=== 查清 {len(flagged)} 組 sweep 旗標的落後案例 ===")
    print(f"{'idx':>4} {'opt_120r4':>9} {'2body':>7} {'j2_orac':>8} "
          f"{'opt400r4':>9} {'opt400r0':>9} {'best':>6}  判定")

    out = []
    for r in flagged:
        A, B, idx = r["A"], r["B"], r["idx"]
        opt = MissionOptimizer(build_config(A, B, 20260903 + idx))
        two_body, j2_orac = honest_oracle(opt)
        o4 = optimize(A, B, 20260903 + idx, revs=4, maxiter=400)
        o0 = optimize(A, B, 20260903 + idx, revs=0, maxiter=400)
        best_opt = max(x for x in (o4, o0, r["opt_score"]) if x is not None)
        real_gap = None if j2_orac is None else round(j2_orac - best_opt, 3)
        if real_gap is None:
            verd = "? oracle 重播失敗"
        elif real_gap > EPS:
            verd = f"❌ 真搜尋失敗（誠實 oracle 仍高 {real_gap}）"
        else:
            verd = "✅ 已解釋（oracle 樂觀 / 預算/REVS）"
        print(f"{idx:>4} {r['opt_score']:>9} {two_body:>7.2f} "
              f"{'--' if j2_orac is None else j2_orac:>8} {str(o4):>9} {str(o0):>9} {best_opt:>6}  {verd}")
        out.append({"idx": idx, "opt_sweep": r["opt_score"], "oracle_2body": round(two_body, 3),
                    "oracle_j2": j2_orac, "opt400_revs4": o4, "opt400_revs0": o0,
                    "best_opt": best_opt, "real_gap": real_gap,
                    "real_search_failure": bool(real_gap is not None and real_gap > EPS)})

    with open(OUT, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    n_real = sum(1 for o in out if o["real_search_failure"])
    print(f"\n  真搜尋失敗 {n_real}/{len(out)}；其餘由 oracle 樂觀或預算/REVS 解釋。")
    print(f"  已寫入 {os.path.basename(OUT)}")


if __name__ == "__main__":
    main()
