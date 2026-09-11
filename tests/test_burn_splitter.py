"""拆棒後處理器的回歸測試（HAP-67）。

斷言**性質**（合法：每棒 ≤cap；命中：miss≤容許；Earth-safe；段數動態 ≥ ceil(dv/cap)），
不賭確切數字——joint NLP 走 SLSQP、換 scipy 版本數字會飄，但性質必須守得住。

貪婪 `legalize_intercept` 是啟發式、對個別幾何會拆不動（這是已知性質，不是 bug），所以測試
掃一組固定的抵達時機、斷言「**至少能合法化一個**超標終端攔截」，而不是賭單一幾何——確定性
（純幾何傳播，不涉 DE/亂數），又不會因為某個難搞幾何誤報失敗。

被 run_regression.py 自動發現（tests/test_*.py）。全過 exit 0，任一不過 exit 1。
"""
import os
import sys
import json
import math

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.optimizer import MissionOptimizer
from src.core_math import propagate_dop853, fast_norm
from src.burn_splitter import legalize_intercept, legalize_route, _lam_best

_FAILED = []


def check(desc, ok):
    print(f"  {'✅' if ok else '❌'} {desc}")
    if not ok:
        _FAILED.append(desc)


def main():
    cfg = json.load(open(os.path.join("configs", "contest.json")))
    opt = MissionOptimizer(cfg)
    mu = opt.MU
    j2, j3, j4, re = opt.J2_VAL, opt.J3_VAL, opt.J4_VAL, opt.RE_VAL
    cap, mc, mp, mr = opt.MAX_DV_SOFT, opt.MIN_COAST_TIME, opt.MIN_PERIAPSIS, opt.LAMBERT_MAX_REVS
    ap, T_max = opt.Ta_sec, opt.T_max

    def prop(r, v, t):
        return propagate_dop853(r, v, float(t), 60.0, mu, j2, j3, j4, re)

    # 固定造「抬高+換面 → 遠地點」起點（不掃描，確定性）
    rb, vb = prop(opt.B_r0, opt.B_v0, 0.0)
    Vh = vb / fast_norm(vb)
    Nh = np.cross(rb, vb); Nh = Nh / fast_norm(Nh)
    k = (Vh - Nh); k = k / fast_norm(k) * cap
    vb1 = vb + k
    sp = fast_norm(vb1) ** 2 / 2.0 - mu / fast_norm(rb)
    a_new = -mu / (2.0 * sp)
    tc = 0.75 * 2.0 * math.pi * math.sqrt(a_new ** 3 / mu)
    rm, vm = prop(rb, vb1, tc)

    # 掃一組固定抵達時機，收集「超標且貪婪拆得出」的第一個案例
    found = None
    over_seen = False
    for frac in (0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1):
        Tarr = tc + ap * frac
        if Tarr >= T_max:
            continue
        r_a, _ = prop(opt.A_r0, opt.A_v0, float(Tarr))
        vneed, single = _lam_best(rm, r_a, Tarr - tc, vm, mu, mr)
        if vneed is None or single <= cap:
            continue
        over_seen = True
        g = legalize_intercept(rm, vm, tc, r_a, Tarr, cap=cap, min_coast=mc, mu=mu,
                               j2=j2, j3=j3, j4=j4, re=re, min_periapsis=mp, max_revs=mr,
                               miss_tol=opt.MISS_TOLERANCE_SOFT, max_seg=14)
        if g is not None:
            found = (frac, Tarr, r_a, single, g)
            break

    print("\n── 拆棒後處理器回歸 ──")
    check("掃到超標終端攔截（否則沒在測拆棒）", over_seen)
    check("貪婪 legalize_intercept 至少能合法化一個超標終端", found is not None)

    if found is not None:
        frac, Tarr, r_a, single, g = found
        print(f"  （採用 frac={frac}：單棒 {single*1000:.0f} m/s ({single/cap:.1f}×) → {g['nseg']} 段）")
        check(f"段數 {g['nseg']} ≥ 理論下限 ceil(dv/cap)={math.ceil(single/cap)}",
              g["nseg"] >= math.ceil(single / cap))
        check("每段 ≤ 上限", max(g["seg_dv_mps"]) <= cap * 1000.0 + 1e-6)
        # 獨立重驗：從 (rm,vm,tc) 串各段，確認命中 + 全程 Earth-safe
        r, v, t = rm.copy(), vm.copy(), tc
        minr = fast_norm(r)
        for i, kk in enumerate(g["kicks"]):
            v = v + kk
            dtt = g["coasts"][i] if i < len(g["coasts"]) else (Tarr - t)
            r, v = prop(r, v, dtt); t += dtt
            minr = min(minr, fast_norm(r))
        check("獨立重驗命中 ≤ 容許", fast_norm(r - r_a) <= opt.MISS_TOLERANCE_SOFT + 1e-3)
        check(f"獨立重驗全程 Earth-safe（最低 r={minr:.0f}≥{mp:.0f}）", minr >= mp - 1e-3)

        # legalize_route 入口：同案例應回傳 feasible、零違規、命中的解
        res = legalize_route(
            t0=0.0, leading_dvs=[k], leading_coasts=[tc],
            terminal_coast=Tarr - tc, target=r_a,
            cap=cap, min_coast=mc, mu=mu, j2=j2, j3=j3, j4=j4, re=re,
            min_periapsis=mp, max_revs=mr,
            A_r0=opt.A_r0, A_v0=opt.A_v0, B_r0=opt.B_r0, B_v0=opt.B_v0,
            k_t=opt.k_t, C_t=opt.C_t, k_v=opt.k_v, C_v=opt.C_v, T_max=T_max,
            miss_tol=opt.MISS_TOLERANCE_SOFT, n_span=1, maxiter=60)
        check("legalize_route 回傳 feasible 解", res is not None and res["feasible"])
        if res is not None:
            check("legalize_route 每棒 ≤ 上限", max(res["dv_mps"]) <= cap * 1000.0 + 1.0)
            check("legalize_route 命中 ≤ 容許", res["miss_km"] <= opt.MISS_TOLERANCE_SOFT + 1e-3)

    print("\n── 收工 ──")
    if _FAILED:
        print(f"❌ {len(_FAILED)} 項未通過：{_FAILED}")
        sys.exit(1)
    print("✅ 拆棒後處理器回歸全過")


if __name__ == "__main__":
    main()
