"""串接拆棒合法化、快取及合法備胎退路
主要入口為 _legalize_stage。
"""
import os
import math
import copy
import contextlib
import re
import numpy as np
from threadpoolctl import threadpool_limits
from odc.search.optimizer import MissionOptimizer
from odc.search.revs import run_study_over_revs
from odc.search.replay import reconstruct_mission_logs
from odc.search.ranking import _mission_rank_key, over_dv_count, is_disqualified
from odc.config.split_defaults import SPLIT_DEFAULTS
from odc.physics.core_math import propagate_dop853, fast_norm, to_vnb_frame
from odc.scoring.scorer import calculate_score, assess_legality, DV_LIMIT_TOL_MPS
from odc.split.burn_splitter import (legalize_route, _simulate_free, prune_null_burns,
                               presplit_leading, leading_arcs_min_radius)
from odc.runlog import log, setup as setup_logging


def split_options(config):
    """strategy 裡的拆棒旋鈕 → legalize_route 的關鍵字參數。

    缺鍵採比賽設定（SPLIT_DEFAULTS）；明確的 null／0 仍可關閉對應功能。"""
    st = config.get("strategy", {})
    reopt = st.get("SPLIT_PRUNE_REOPT_MPS", SPLIT_DEFAULTS["SPLIT_PRUNE_REOPT_MPS"])
    budget = st.get("SPLIT_WALL_BUDGET_SEC", SPLIT_DEFAULTS["SPLIT_WALL_BUDGET_SEC"])
    workers = int(st.get("SPLIT_WORKERS", SPLIT_DEFAULTS["SPLIT_WORKERS"]))
    return {
        "n_span": int(st.get("SPLIT_N_SPAN", 1)),
        "maxiter": int(st.get("SPLIT_NLP_MAXITER", 1000)),    # C3：1000
        "fast_fd": bool(st.get("SPLIT_FAST_FD", False)),
        "jacobian": st.get("SPLIT_JACOBIAN", SPLIT_DEFAULTS["SPLIT_JACOBIAN"]),
        "workers": max(1, min(workers, os.cpu_count() or 1)),
        "starts": st.get("SPLIT_MULTISTART", SPLIT_DEFAULTS["SPLIT_MULTISTART"]) or None,
        "prune_reopt_tol": None if not reopt else float(reopt) / 1000.0,
        "wall_budget": None if not budget else float(budget),
    }


def legalize_violating_winner(config, burns, times, mission_info, optimizer):
    """HAP-67 Stage 2 接線：DE 贏家若有「超標但 Earth-safe」的違規棒，自動把它拆成合法
    多棒版（`burn_splitter.legalize_route`）並回傳新的 (burns_vnb, times, mission_info)；
    拆不出或沒違規就回 None（呼叫端沿用原解）。

    這是「先給大致路線(允許違規)、再拆分」方法論的正式接線：DE 只管找路線、允許違規，
    真正把違規合法化交給確定性拆分器 + joint NLP（目標函數=真實 calculate_score）。驗證
    見 docs/research/HAP67_SPLIT_PIPELINE_PLAN.md（contest.json：88.32 含 −10 → 98.31 零違規、
    GMAT 定燒命中、+9.99 分）。

    預設開；strategy.AUTO_SPLIT_LEGALIZE=false 可關（違規解原樣交出去——排位賽起單棒超標是
    失格，run_output_stage 會大聲擋下、不產生繳交腳本）。
    """
    if not bool(config.get("strategy", {}).get("AUTO_SPLIT_LEGALIZE", True)):
        return None
    if over_dv_count(mission_info) <= 0:
        return None  # 沒有單棒超標，沒東西要拆（總 Δv 超標拆棒救不了）

    opt = optimizer
    mu, j2, j3, j4, re = opt.MU, opt.J2_VAL, opt.J3_VAL, opt.J4_VAL, opt.RE_VAL
    mc, T_max = opt.MIN_COAST_TIME, opt.T_max
    x = np.asarray(mission_info["x"], dtype=np.float64)
    N0 = int(mission_info["num_burns"])

    def _p(r, v, tt):
        return propagate_dop853(r, v, float(tt), 60.0, mu, j2, j3, j4, re)

    def _sph(rr, th, ph):
        st = math.sin(th)
        return np.array([rr * st * math.cos(ph), rr * st * math.sin(ph), rr * math.cos(th)])

    # 解碼標準決策向量 → route（球座標慣例跟 reconstruct_mission_logs 逐字一致）
    t0 = float(x[0]); cur = t0
    r, v = opt.state_B(t0)
    leading_dvs, leading_coasts, idx = [], [], 1
    for _ in range(1, N0):
        dvv = _sph(x[idx], x[idx + 1], x[idx + 2]); cf = x[idx + 3]; idx += 4
        mx = T_max - cur - mc
        tco = mc + cf * (mx - mc) if mx > mc else mc
        leading_dvs.append(dvv); leading_coasts.append(tco)
        v = v + dvv; r, v = _p(r, v, tco); cur += tco
    flf = x[-4]; mxf = T_max - cur
    tfin = mc + flf * (mxf - mc) if mxf > mc else mc
    icpt = cur + tfin
    r_A, _ = opt.state_A(icpt)
    target = r_A + _sph(x[-3], x[-2], x[-1])

    if opt.SPLIT_LEADING and any(np.linalg.norm(dv) > opt.MAX_DV_SOFT for dv in leading_dvs):
        counts = [max(1, math.ceil(float(np.linalg.norm(dv)) / opt.MAX_DV_SOFT - 1e-12))
                  for dv in leading_dvs if np.linalg.norm(dv) > opt.MAX_DV_SOFT]
        route = presplit_leading(t0, leading_dvs, leading_coasts, tfin,
                                 cap=opt.MAX_DV_SOFT, min_coast=mc)
        if route is None:
            log.info("⚠️ 前導棒等分：拆開後時間不夠，沿用原解。")
            return None
        t0p, ldv, lco, _ = route
        radii = leading_arcs_min_radius(t0p, ldv, lco, mu=mu, j2=j2, j3=j3, j4=j4, re=re,
                                       B_r0=opt.B_r0, B_v0=opt.B_v0, ephem=opt.ephem)
        if float(np.min(radii)) < opt.MIN_PERIAPSIS - 1e-3:
            log.info("⚠️ 前導棒等分：等待弧或前導滑行弧不安全，沿用原解。")
            return None
        t0, leading_dvs, leading_coasts, tfin = route
        log.info(f"✂️ 前導棒等分：{len(counts)} 發超標前導棒，各拆成 "
                 + "、".join(str(n) for n in counts) + " 段。")

    options = split_options(config)
    res = legalize_route(
        t0=t0, leading_dvs=leading_dvs, leading_coasts=leading_coasts,
        terminal_coast=tfin, target=target,
        cap=opt.MAX_DV_SOFT, min_coast=mc, mu=mu, j2=j2, j3=j3, j4=j4, re=re,
        min_periapsis=opt.MIN_PERIAPSIS, max_revs=opt.LAMBERT_MAX_REVS,
        A_r0=opt.A_r0, A_v0=opt.A_v0, B_r0=opt.B_r0, B_v0=opt.B_v0,
        k_t=opt.k_t, C_t=opt.C_t, k_v=opt.k_v, C_v=opt.C_v, T_max=T_max,
        miss_tol=opt.MISS_TOLERANCE_SOFT, ephem=opt.ephem, **options)
    if res is None or not res["feasible"]:
        log.info("⚠️ HAP-67 自動拆分：這個違規解在段數上限內拆不出合法版，沿用原解。")
        return None
    if res.get("start_shift_sec"):
        log.info(f"🔀 多起點拆棒：終端棒起點提前 {res['start_shift_sec']:.0f} s 的那一組最好"
                 f"（{res['score']:.4f}，{res['N']} 棒）。")
    if res.get("budget_hit"):
        log.warning(f"⏱️ 拆棒牆鐘預算 {options['wall_budget']:g} s 到期：交目前最好的"
                    f"合法拆法（{res['score']:.4f}，{res['N']} 棒），後面的精修略過。")

    # free-ECI 結果 → 每棒「燒前狀態」→ VNB；組回 script_generator / mission_info 要的格式
    Nf = int(res["N"]); xf = np.asarray(res["x"], dtype=np.float64)
    # NLP 壓到 ~0 的段 / DE 留下的空燒不寫進繳交腳本：剔除後用真實約束重評，通過才換成剔除版
    # （分數/Δr/Δv 一律用剔除後重算的值，前後自洽；見 prune_null_burns）
    pr = prune_null_burns(xf, Nf, opt.MAX_DV_SOFT, opt.MIN_PERIAPSIS, mu, j2, j3, j4, re,
                          opt.A_r0, opt.A_v0, opt.B_r0, opt.B_v0,
                          opt.k_t, opt.C_t, opt.k_v, opt.C_v, opt.MISS_TOLERANCE_SOFT, ephem=opt.ephem)
    if pr is not None:
        log.debug(f"拆棒解剔除 {Nf - pr['N']} 發 Δv≈0 空燒：{Nf} → {pr['N']} 棒"
                  f"（重評 {res['score']:.6f} → {pr['score']:.6f}，Δr {res['miss_km']:.4f} → "
                  f"{pr['miss_km']:.4f} km）")
        res = pr
        Nf = int(res["N"]); xf = np.asarray(res["x"], dtype=np.float64)
    t0f = float(xf[0]); coastsf = xf[1:1 + Nf]; dvsf = xf[1 + Nf:].reshape(Nf, 3)
    rr, vv = opt.state_B(t0f); states = []
    for i in range(Nf):
        states.append((rr.copy(), vv.copy())); vv = vv + dvsf[i]; rr, vv = _p(rr, vv, coastsf[i])
    m = _simulate_free(xf, Nf, mu, j2, j3, j4, re, opt.A_r0, opt.A_v0, opt.B_r0, opt.B_v0, ephem=opt.ephem)
    burns_vnb = [tuple(float(c) for c in to_vnb_frame(rp, vp, dvsf[i]))
                 for i, (rp, vp) in enumerate(states)]
    times_new = [float(t0f)] + [float(c) for c in coastsf]
    # 拆完照最終交件規則重判一次（單棒用真實上限、機動間隔、總 Δv）。拆棒器用 MAX_DV_SOFT
    # 與 min_coast 當約束，正常一定零違規；總 Δv 上限它不知道，可能拆完反而超標 → 失格。
    burn_t = t0f + np.concatenate(([0.0], np.cumsum(coastsf[:-1])))
    leg = assess_legality(np.linalg.norm(dvsf, axis=1) * 1000.0, burn_t, opt.MAX_DV * 1000.0,
                          mc, opt.MAX_TOTAL_DV_MPS)
    T_new = float(m["T_team"])
    n_soft = leg["penalty_count"] + leg["over_dv_count"]
    score_new = (float(res["score"]) if n_soft == 0 and not leg["disqualified"] else
                 opt.search_score(leg, np.linalg.norm(dvsf, axis=1), float(res["miss_km"]), T_new,
                                  float(res["total_dv_mps"])))
    legality = opt.legality_fields(leg, float(res["miss_km"]), T_new)
    if not legality["disqualified"] and n_soft == 0:
        legality["official_score"] = score_new   # 跟 score 同一個數字，不讓重算的 ulp 差異混淆
    new_mi = {
        "x": xf, "num_burns": Nf,
        "score": score_new, "miss_km": float(res["miss_km"]),
        "total_dv_mps": float(res["total_dv_mps"]), "T_team": T_new,
        **legality,
        # 拆分解每棒都是直接算好的 ECI 燒、legalize_route 已驗證命中容許球內，沒有「Lambert
        # 猜測靠 DC 收斂」這回事，本來就自洽——對齊 dc_converged 語意設 True。
        "dc_converged": True,
        "aim_point": tuple(float(c) for c in m["r_final"]),
        "final_burn_dv_mps": float(fast_norm(dvsf[-1]) * 1000.0),
        "earth_safe": bool(float(np.min(m["arc_minr"])) >= opt.MIN_PERIAPSIS - 1e-3),
        "min_arc_radius_km": float(np.min(m["arc_minr"])),
    }
    verdict = ("🔴 仍失格：" + "；".join(new_mi["dq_reasons"]) if new_mi["disqualified"]
               else f"合法 {new_mi['score']:.4f}")
    log.info(f"\n🔧 HAP-67 自動拆分：超標解 {mission_info['score']:.4f}（{over_dv_count(mission_info)} 棒超標，失格）"
             f" → {verdict}（{Nf} 棒、總Δv {new_mi['total_dv_mps']:,.0f} m/s）"
             f"，搜尋用分數差 {new_mi['score']-mission_info['score']:+.4f}。")
    return burns_vnb, times_new, new_mi


def _legalize_stage(config, burns, times, mi, opt):
    """拆棒合法化那一段（Earth-safe 才拆）。`_solve_pipeline` 與 `--from-winner` 重播共用。

    設了 SEED（或開了 SPLIT_FAST_FD / STM）時跟搜尋階段一樣把 BLAS 鎖單執行緒（見 run_study_over_revs 的重現性說明）：
    joint NLP（SLSQP）在父行程跑、原本沒鎖，多執行緒 BLAS 讓同一個拆棒前贏家拆出不同結果
    （2026-09-25 實測 contest：鎖 98.319106／7 棒 vs 不鎖 98.318995／6 棒）。"""
    # primer 先拆過的候選直接取回；快取掛在 optimizer，不進拆前 checkpoint。
    cache_key = None
    if getattr(opt, "SPLIT_LEADING", False):
        cache_key = (int(mi["num_burns"]), np.asarray(mi["x"], dtype=np.float64).tobytes())
        if not hasattr(opt, "_legalize_cache"):
            opt._legalize_cache = {}
        if cache_key in opt._legalize_cache:
            return opt._legalize_cache[cache_key]
    if bool(mi.get("earth_safe", True)):
        seed_set = config.get("optimization", {}).get("SEED") is not None
        # SPLIT_FAST_FD 開時不論有沒有 SEED 都鎖：SLSQP 的問題只有幾十維，多執行緒 BLAS 不會更快、
        # 只會空轉（10-20 實測每個行程吃 ~650% CPU、慢 1.7×），3 顆種子並行時會互搶核心。
        lock = (seed_set or bool(config.get("strategy", {}).get("SPLIT_FAST_FD", False))
                or config.get("strategy", {}).get(
                    "SPLIT_JACOBIAN", SPLIT_DEFAULTS["SPLIT_JACOBIAN"]) == "stm")
        with (threadpool_limits(limits=1, user_api="blas") if lock else contextlib.nullcontext()):
            _legal = legalize_violating_winner(config, burns, times, mi, opt)
        if _legal is not None:
            burns, times, mi = _legal
    result = burns, times, mi
    if cache_key is not None:
        opt._legalize_cache[cache_key] = result
    return result


def _fallback_to_legal_backup(config, burns, times, mi, opt):
    """C4 退路（2.3）：拆後估計落空時——贏家仍失格（段數上限內拆不出、拆後不 Earth-safe、或總 Δv
    超標）——找一個替代解。排位賽起失格解一律輸給不失格的解；兩邊都失格才比搜尋用分數（§6）。
    沒失格、或旗標關時原樣回傳。

    替代解依序：
    1. 搜尋時記下的「最佳零違規候選」（`optimizer.legal_backup`，未精修）精修出來，要合法才算。
    2. 沒有備胎（旗標開時搜尋不懲罰終端超標，各案例贏家常全是違規解——C4 E4 `hyper_far` 就是這樣）
       或備胎精修後不合法：**用旗標關重跑一輪搜尋 + 拆棒**。同 SEED 下它就是旗標關的結果，所以
       退路保證不比旗標關差；代價是拆棒失敗時多一輪搜尋，正常路徑不花時間。

    回傳 (burns, times, mission_info, optimizer)：替代解可能來自 REVS 集成的另一趟或重搜，要換成
    它自己的 optimizer（LAMBERT_MAX_REVS／旗標不同），產腳本/存檔才對得上。"""
    from odc.pipeline.solve import _search_stage, _final_rank_key
    if not getattr(opt, "SPLIT_AWARE_TERMINAL", False) or not is_disqualified(mi):
        return burns, times, mi, opt
    cand, src = None, None
    bk = getattr(opt, "legal_backup", None)
    if bk is not None:
        b_opt = bk["opt"]
        b_burns, b_times, b_mi = b_opt.refine_trajectory(bk["x"], bk["burns"], bk["fitness"])
        if b_burns is not None and isinstance(b_mi, dict) and not is_disqualified(b_mi) \
                and bool(b_mi.get("earth_safe", True)):
            cand, src = (b_burns, b_times, b_mi, b_opt), "合法備胎"
        else:
            log.warning("⚠️ C4：拆後估計落空，合法備胎精修後也不合法。")
    if cand is None:
        log.warning("⚠️ C4：拆後估計落空且沒有可用的零違規備胎——改用旗標關重跑一輪搜尋當退路。")
        cfg_off = copy.deepcopy(config)
        cfg_off.setdefault("strategy", {})["SPLIT_AWARE_TERMINAL"] = False
        r_burns, r_times, r_mi, r_opt = _search_stage(cfg_off)
        if r_burns is not None:
            r_burns, r_times, r_mi = _legalize_stage(cfg_off, r_burns, r_times, r_mi, r_opt)
            if bool(r_mi.get("earth_safe", True)):
                cand, src = (r_burns, r_times, r_mi, r_opt), "旗標關重搜"
    if cand is None:
        log.warning("⚠️ C4：退路也沒有可用的替代解——照舊交違規解。")
        return burns, times, mi, opt
    c_burns, c_times, c_mi, c_opt = cand
    eps = opt.TIEBREAK_SCORE_EPS
    use_cand = (not bool(mi.get("earth_safe", True))
                or _final_rank_key(c_mi, eps=eps) < _final_rank_key(mi, eps=eps))
    c_tag = "失格" if is_disqualified(c_mi) else "合法"
    log.warning(f"⚠️ C4：拆後估計落空——失格解搜尋用分數 {mi['score']:.4f}（{over_dv_count(mi)} 棒超標）"
                f" vs {src} {c_mi['score']:.4f}（{c_mi['num_burns']} 棒、{c_tag}）"
                f"→ 交{src if use_cand else f'失格解（{src}更差）'}。")
    if use_cand:
        return c_burns, c_times, c_mi, c_opt
    return burns, times, mi, opt
