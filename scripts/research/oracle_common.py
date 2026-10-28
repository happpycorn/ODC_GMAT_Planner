"""GLOBAL_ORACLE（2026-10-28）共用：排位賽題庫情境、統一的「J2–J4 精修 + 拆棒合法化」尺。

每個獨立方法（兩棒窮舉、換最佳化器、free-ECI 多起點）找出來的路線，都用 `finalize_route`
換算成**最終合法分數**，跟 main.py 管線同一把尺：
  1. 前導棒超過 MAX_DV_SOFT 的，先等分成 ⌈|Δv|/cap⌉ 段、間隔 MIN_COAST（以原時刻為中心）。
     main.py 的拆棒器只拆終端棒，前導大棒得先在這裡拆開。
  2. 交給 `burn_splitter.legalize_route`（拆棒建議設定，`main.split_options`）：
     終端棒在 J2–J4 下從實際狀態重新瞄準 A(T)、拆成合法段，joint NLP 用真實計分精修整條路線。
  3. `prune_null_burns` 剔空燒，`assess_legality` 照交件規則重判（單棒、間隔、總 Δv 3 km/s）。
不改任何既有程式；只 import。
"""
import copy
import json
import math
import os
import sys
import time

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
import warnings  # noqa: E402
warnings.filterwarnings("ignore")

from src.optimizer import MissionOptimizer                     # noqa: E402
from src.burn_splitter import legalize_route, prune_null_burns, _simulate_free  # noqa: E402
from src.scorer import assess_legality, calculate_score         # noqa: E402

# 排位賽覆寫 + splitspeed_par3_rec 的拆棒建議設定（與 sweeps/global_oracle_*.json 相同）
RANKING_BASE = {
    "rules.MAX_DV_MPS": 250.0,
    "rules.MAX_TOTAL_DV_MPS": 3000.0,
    "optimization.MAXITER": 600,
    "optimization.POPSIZE": 20,
    "optimization.NUM_THREADS": 5,
    "strategy.SPLIT_FAST_FD": True,
    "strategy.SPLIT_WORKERS": 3,
    "strategy.SPLIT_MULTISTART": [0, 0.75, 1],
    "strategy.SPLIT_PRUNE_REOPT_MPS": 1.0,
    "strategy.SPLIT_WALL_BUDGET_SEC": 600,
}
SCENARIOS = {
    "hyper_far": ("configs/shared/hyper_far.json", {}),
    "hyperbolic_test_fuel": ("configs/shared/hyperbolic_test.json",
                             {"rules.k_v": 0.002, "rules.C_v": 2500.0}),
    "hyperbolic_smoke": ("configs/shared/hyperbolic_smoke.json", {}),
    "ranking_round": ("configs/shared/ranking_round.json", {}),
}


def _set(d, dotted, val):
    keys = dotted.split(".")
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = val


def load_scenario(name, seed=0, extra=None):
    """回傳 (config, MissionOptimizer)。覆寫順序同 sweep_params：情境 → base → 情境覆寫 → extra。"""
    path, ov = SCENARIOS[name]
    with open(os.path.join(REPO, path), encoding="utf-8") as f:
        cfg = json.load(f)
    for k, v in {**RANKING_BASE, **ov, **(extra or {}), "optimization.SEED": seed}.items():
        _set(cfg, k, copy.deepcopy(v))
    return cfg, MissionOptimizer(cfg)


def split_options(config):
    # 與 main.split_options 相同（不 import main，避免拖進 GMAT/腳本產生器）
    st = config.get("strategy", {})
    reopt = st.get("SPLIT_PRUNE_REOPT_MPS")
    return {
        "n_span": int(st.get("SPLIT_N_SPAN", 1)),
        "maxiter": int(st.get("SPLIT_NLP_MAXITER", 1000)),
        "fast_fd": bool(st.get("SPLIT_FAST_FD", False)),
        "workers": int(st.get("SPLIT_WORKERS", 1)),
        "starts": st.get("SPLIT_MULTISTART") or None,
        "prune_reopt_tol": None if not reopt else float(reopt) / 1000.0,
        "wall_budget": (None if not st.get("SPLIT_WALL_BUDGET_SEC")
                        else float(st["SPLIT_WALL_BUDGET_SEC"])),
    }


def presplit_leading(opt, t0, dvs, coasts):
    """前導棒（除最後一棒外）超過 MAX_DV_SOFT 的等分成多段、間隔 MIN_COAST，以原時刻為中心。

    dvs: N 個 ECI Δv（km/s）；coasts: N 個「該棒之後」的滑行秒數（最後一個 = 終端滑行）。
    回傳 (t0, leading_dvs, leading_coasts, terminal_coast)，終端棒的 Δv 交給拆棒器重算。"""
    cap, mc = opt.MAX_DV_SOFT, opt.MIN_COAST_TIME
    times = [float(t0)]
    for c in coasts[:-1]:
        times.append(times[-1] + float(c))
    T_arr = times[-1] + float(coasts[-1])
    burns = []                                   # (t, dv)
    for i, dv in enumerate(dvs[:-1]):
        dv = np.asarray(dv, dtype=np.float64)
        mag = float(np.linalg.norm(dv))
        if mag < 1e-9:
            continue
        n = max(1, math.ceil(mag / cap - 1e-12))
        start = max(0.0, times[i] - 0.5 * (n - 1) * mc)
        if burns:
            start = max(start, burns[-1][0] + mc)
        for k in range(n):
            burns.append((start + k * mc, dv / n))
    t_term = max(times[-1], (burns[-1][0] + mc) if burns else 0.0)
    if T_arr - t_term < mc:
        return None
    if not burns:
        return t_term, [], [], T_arr - t_term
    lead_dvs = [b[1] for b in burns]
    lead_coasts = [burns[k + 1][0] - burns[k][0] for k in range(len(burns) - 1)]
    lead_coasts.append(t_term - burns[-1][0])
    return burns[0][0], lead_dvs, lead_coasts, T_arr - t_term


def finalize_route(opt, config, t0, dvs, coasts, tag=""):
    """任一路線 → J2–J4 精修 + 拆棒合法化後的最終合法分數（與管線同一把尺）。"""
    t_start = time.time()
    ps = presplit_leading(opt, t0, dvs, coasts)
    if ps is None:
        return {"tag": tag, "ok": False, "reason": "前導棒拆開後時間不夠"}
    t0p, ldv, lco, tcoast = ps
    T_arr = t0p + sum(lco) + tcoast
    if T_arr > opt.T_max:
        return {"tag": tag, "ok": False, "reason": "超過 T_max"}
    r_A, _ = opt.state_A(T_arr)
    mu, j2, j3, j4, re = opt.MU, opt.J2_VAL, opt.J3_VAL, opt.J4_VAL, opt.RE_VAL
    try:
        res = legalize_route(
            t0=t0p, leading_dvs=ldv, leading_coasts=lco, terminal_coast=tcoast, target=r_A,
            cap=opt.MAX_DV_SOFT, min_coast=opt.MIN_COAST_TIME, mu=mu, j2=j2, j3=j3, j4=j4, re=re,
            min_periapsis=opt.MIN_PERIAPSIS, max_revs=opt.LAMBERT_MAX_REVS,
            A_r0=opt.A_r0, A_v0=opt.A_v0, B_r0=opt.B_r0, B_v0=opt.B_v0,
            k_t=opt.k_t, C_t=opt.C_t, k_v=opt.k_v, C_v=opt.C_v, T_max=opt.T_max,
            miss_tol=opt.MISS_TOLERANCE_SOFT, ephem=opt.ephem, **split_options(config))
    except Exception as e:                       # noqa: BLE001
        return {"tag": tag, "ok": False, "reason": f"拆棒例外 {type(e).__name__}: {e}"}
    if res is None or not res["feasible"]:
        return {"tag": tag, "ok": False, "reason": "拆不出合法解",
                "sec": round(time.time() - t_start, 1)}
    pr = prune_null_burns(np.asarray(res["x"]), int(res["N"]), opt.MAX_DV_SOFT, opt.MIN_PERIAPSIS,
                          mu, j2, j3, j4, re, opt.A_r0, opt.A_v0, opt.B_r0, opt.B_v0,
                          opt.k_t, opt.C_t, opt.k_v, opt.C_v, opt.MISS_TOLERANCE_SOFT, ephem=opt.ephem)
    if pr is not None:
        res = pr
    return summarize_free(opt, np.asarray(res["x"], dtype=np.float64), int(res["N"]), tag=tag,
                          sec=time.time() - t_start)


def summarize_free(opt, x, N, tag="", sec=None):
    """free-ECI 解 → 照交件規則重判的摘要（分數、棒數、總 Δv、T_team、最大單棒、合法與否）。"""
    mu, j2, j3, j4, re = opt.MU, opt.J2_VAL, opt.J3_VAL, opt.J4_VAL, opt.RE_VAL
    m = _simulate_free(x, N, mu, j2, j3, j4, re, opt.A_r0, opt.A_v0, opt.B_r0, opt.B_v0,
                       ephem=opt.ephem)
    coasts = x[1:1 + N]
    dvs = x[1 + N:].reshape(N, 3)
    mags = np.linalg.norm(dvs, axis=1) * 1000.0
    burn_t = x[0] + np.concatenate(([0.0], np.cumsum(coasts[:-1])))
    leg = assess_legality(mags, burn_t, opt.MAX_DV * 1000.0, opt.MIN_COAST_TIME, opt.MAX_TOTAL_DV_MPS)
    miss = float(m["miss_km"])
    safe = bool(float(np.min(m["arc_minr"])) >= opt.MIN_PERIAPSIS - 1e-3)
    score = calculate_score(min_distance_km=miss, total_time_sec=float(m["T_team"]),
                            total_dv_mps=float(mags.sum()), penalty_count=int(leg["penalty_count"]),
                            k_t=opt.k_t, C_t=opt.C_t, k_v=opt.k_v, C_v=opt.C_v)
    legal = (not leg["disqualified"]) and safe and miss <= opt.MISS_TOLERANCE_KM + 1e-9
    return {
        "tag": tag, "ok": True, "legal": bool(legal), "score": float(score),
        "num_burns": int(N), "total_dv_mps": float(mags.sum()), "T_team": float(m["T_team"]),
        "max_burn_mps": float(mags.max()), "miss_km": miss, "earth_safe": safe,
        "penalty_count": int(leg["penalty_count"]), "disqualified": bool(leg["disqualified"]),
        "sec": None if sec is None else round(float(sec), 1),
        "x": [float(v) for v in x],
    }


def route_from_standard_x(opt, x, N):
    """main.py 標準決策向量（球座標、coast_frac、final_leg_frac、瞄準偏移）→ (t0, dvs, coasts)。
    解碼慣例跟 main.legalize_violating_winner 逐字一致；終端棒 Δv 用 None（拆棒器重算）。"""
    mc, T_max = opt.MIN_COAST_TIME, opt.T_max
    x = np.asarray(x, dtype=np.float64)

    def sph(rr, th, ph):
        st = math.sin(th)
        return np.array([rr * st * math.cos(ph), rr * st * math.sin(ph), rr * math.cos(th)])
    t0 = float(x[0]); cur = t0; dvs, coasts, idx = [], [], 1
    for _ in range(1, N):
        dvv = sph(x[idx], x[idx + 1], x[idx + 2]); cf = x[idx + 3]; idx += 4
        mx = T_max - cur - mc
        tco = mc + cf * (mx - mc) if mx > mc else mc
        dvs.append(dvv); coasts.append(tco); cur += tco
    flf = x[-4]; mxf = T_max - cur
    tfin = mc + flf * (mxf - mc) if mxf > mc else mc
    dvs.append(np.zeros(3)); coasts.append(tfin)
    return t0, dvs, coasts


def standard_x_from_route(opt, t1, dv1, t2, t3):
    """兩棒路線（t1 燒 dv1、t2 終端 Lambert、t3 攔截）→ 標準決策向量（N=2）；dv1=None → N=1。"""
    mc, T_max = opt.MIN_COAST_TIME, opt.T_max
    if dv1 is None:
        mxf = T_max - t1
        flf = 0.0 if mxf <= mc else (t3 - t1 - mc) / (mxf - mc)
        return np.array([t1, min(max(flf, 0.0), 1.0), 0.0, 0.0, 0.0]), 1
    r = float(np.linalg.norm(dv1))
    th = math.acos(max(-1.0, min(1.0, dv1[2] / r))) if r > 0 else 0.0
    ph = math.atan2(dv1[1], dv1[0]) % (2 * math.pi)
    mx = T_max - t1 - mc
    cf = 0.0 if mx <= mc else (t2 - t1 - mc) / (mx - mc)
    mxf = T_max - t2
    flf = 0.0 if mxf <= mc else (t3 - t2 - mc) / (mxf - mc)
    return np.array([t1, r, th, ph, min(max(cf, 0.0), 1.0), min(max(flf, 0.0), 1.0),
                     0.0, 0.0, 0.0]), 2


def jdump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


OUT = os.path.join(REPO, "outputs", "research", "global_oracle")
