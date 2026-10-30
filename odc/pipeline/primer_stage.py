"""診斷 primer 並依既有條件執行插棒重搜
主要入口為 primer_guided_research。
"""
import time
import copy
import contextlib
import re
import numpy as np
from threadpoolctl import threadpool_limits
from odc.search.optimizer import MissionOptimizer
from odc.search.revs import run_study_over_revs
from odc.search.replay import reconstruct_mission_logs
from odc.search.ranking import _mission_rank_key, over_dv_count, is_disqualified
from odc.search.primer import intercept_primer_profile, insert_node_seed
from odc.runlog import log, setup as setup_logging
from odc.gmat.verification import patch_report_level
from odc.pipeline.legalize import _legalize_stage


def _primer_diagnose_winner(mission_info, opt):
    """對 DE 贏家（標準決策向量、未拆棒前）算 primer 剖面（C1 診斷）。

    重播用 `reconstruct_mission_logs` 拿到每發脈衝的絕對時刻與 ECI Δv（跟計分同一條
    路徑，保證診斷的就是被評分的那條解），再餵 `intercept_primer_profile`。回傳 profile
    dict（含 verdict / worst_arc / 各弧 p_peak / p_peak_frac），無法診斷時回 None。
    """
    x = mission_info.get("x")
    N = int(mission_info.get("num_burns", 0))
    if x is None or N < 1:
        return None
    mu, j2, j3, j4, re = opt.MU, opt.J2_VAL, opt.J3_VAL, opt.J4_VAL, opt.RE_VAL
    try:
        logs, times, *_ = reconstruct_mission_logs(
            np.asarray(x, dtype=np.float64), N, opt.MIN_COAST_TIME, opt.T_max,
            opt.A_r0, opt.A_v0, opt.B_r0, opt.B_v0, mu, j2, j3, j4, re,
            lambert_max_revs=opt.LAMBERT_MAX_REVS, ephem=opt.ephem)
    except Exception as exc:                       # 重播偶發 Lambert 不收斂等，診斷不該擋管線
        log.debug(f"primer 診斷重播失敗，略過：{exc}")
        return None
    t0 = float(logs[0]["time"])
    r0, v0 = opt.state_B(t0)
    impulses = [(float(bl["time"]), np.asarray(bl["dv_vec"], dtype=np.float64)) for bl in logs]
    return intercept_primer_profile(r0, v0, impulses, float(times[-1]), mu)


def primer_guided_research(config, burns, times, mission_info, optimizer):
    """C2（2026-09-22）：primer 引導的條件式重搜。

    先跑預設（中間棒夾 cap，便宜穩健，已在 run_study_over_revs 跑完）→ 對贏家算 primer：
      - `|p|≤1` 全程（verdict=optimal-ish）→ 結構已（局部）最優，**收工不重搜**。這是圓
        軌道攔截 0/14 的物理原因（見 memory odc-split-aware-not-needed），也是本函式對
        當前題型的預設行為：只多印一行最優性證書，不改結果、不加成本。
      - `|p|>1`（verdict=add-node）→ 該處缺節點 / 節點放錯 → 才付昂貴的寬範圍搜尋：開
        `SPLIT_AWARE_SEARCH`（中間棒上界由 B1 的 energy_floor 動態算）、在 primer 指的弧
        用 `insert_node_seed` 注入一顆插棒種子、以 N+1 棒重搜，最後照規則§6 取兩者較優的。

    只在理論（primer）說會賺時才重搜——把「SPLIT_AWARE 該不該開、種子放哪」從用猜的
    變成 primer 指的。回傳勝出的 (burns, times, mission_info, optimizer)；沿用原解時回 None。
    旗標 strategy.PRIMER_GUIDED_RESEARCH=false 可整個關掉（連診斷都不跑）。
    """
    strat = config.get("strategy", {})
    if not bool(strat.get("PRIMER_GUIDED_RESEARCH", True)):
        return None
    if not isinstance(mission_info, dict) or mission_info.get("x") is None:
        return None

    prof = _primer_diagnose_winner(mission_info, optimizer)
    if prof is None:
        return None

    N = int(mission_info["num_burns"])
    if prof["verdict"] == "optimal-ish":
        log.info(f"🧭 primer 診斷：全程 |p|≤1（max|p|={prof['max_peak']:.3f}）"
                 f"——結構已（局部）最優，不需加棒、不重搜。")
        return None

    warc = prof["worst_arc"]
    a = prof["arcs"][warc]
    frac = a["p_peak_frac"]
    log.info(f"🧭 primer 診斷：max|p|={prof['max_peak']:.3f}>1（add-node）——第 {warc} 段"
             f"（{a['kind']}）峰值落在 {frac*100:.0f}% 處，該插一發中途棒。開 SPLIT_AWARE "
             f"+ 插棒種子，以 {N + 1} 棒重搜。")

    # 重搜設定：開 SPLIT_AWARE（B1 動態上界自動生效）、鎖定 N+1 棒（是否真的比原解好交給
    # §6 比較把關，不好就沿用原解）。其餘設定沿用。
    cfg2 = copy.deepcopy(config)
    s2 = cfg2.setdefault("strategy", {})
    s2["SPLIT_AWARE_SEARCH"] = True
    cfg2["optimization"] = dict(cfg2.get("optimization", {}))
    cfg2["optimization"]["MAX_BURNS"] = [N + 1]

    seed = insert_node_seed(np.asarray(mission_info["x"], dtype=np.float64), N,
                            warc, frac, optimizer.T_max, optimizer.MIN_COAST_TIME)

    if strat.get("PRIMER_RESEARCH_MODE", "full") == "fast":
        return _primer_fast_research(cfg2, seed, burns, times, mission_info, optimizer)

    b2, t2, mi2, opt2 = run_study_over_revs(cfg2, external_seeds={N + 1: [seed]})
    if b2 is None or not isinstance(mi2, dict):
        log.info("🧭 primer 重搜這趟沒跑出可用解，沿用原解。")
        return None

    eps = optimizer.TIEBREAK_SCORE_EPS
    # C4：SPLIT_AWARE_TERMINAL 開時新舊都比拆後估計（同一把尺），關時就是真實分數。
    se = optimizer.SPLIT_AWARE_TERMINAL
    if getattr(optimizer, "SPLIT_LEADING", False):
        key_old = _primer_post_rank_key((burns, times, mission_info, optimizer), eps)
        key_new = _primer_post_rank_key((b2, t2, mi2, opt2), eps)
    else:
        key_old = _mission_rank_key(mission_info, eps=eps, split_est=se)
        key_new = _mission_rank_key(mi2, eps=eps, split_est=se)
    if key_new < key_old:
        log.info(f"🧭 primer 重搜勝出：{mission_info['score']:.4f} → {mi2['score']:.4f}"
                 f"（{N} → {N + 1} 棒，Δv {mission_info['total_dv_mps']:,.0f} → "
                 f"{mi2['total_dv_mps']:,.0f} m/s），採用重搜解。")
        return b2, t2, mi2, opt2
    log.info(f"🧭 primer 重搜未勝過原解（重搜 {mi2['score']:.4f} vs 原 "
             f"{mission_info['score']:.4f}），沿用原解。")
    return None


def _primer_fast_research(cfg2, seed, burns, times, mission_info, optimizer):
    """C2 fast：插棒種子局部精修 → 繼承贏家 REVS 的短 DE → 同尺挑三者。"""
    n = int(mission_info["num_burns"]) + 1
    st = cfg2["strategy"]
    # 插棒向量繼承原贏家的 Lambert 路線；局部與短全域都用同一趟 REVS。
    st["REVS_ENSEMBLE"] = False
    st["LAMBERT_MAX_REVS"] = optimizer.LAMBERT_MAX_REVS
    candidates = [("original", (burns, times, mission_info, optimizer))]
    seeds = [seed]
    start = time.monotonic()
    local_opt = MissionOptimizer(cfg2)
    ctx = (threadpool_limits(limits=1, user_api="blas")
           if cfg2["optimization"].get("SEED") is not None else contextlib.nullcontext())
    try:
        with ctx, patch_report_level(local_opt):
            # SLSQP 有顯式可行性約束，且能從插入的零 Δv 節點移動；再沿用正式
            # refine_trajectory 的 L-BFGS-B、安全回退、§6 polish 與任務重播。
            refined = local_opt._generate_nlp_refined_seed_candidates(n, 1, [seed])
            x0 = refined[0] if refined else seed
            b, t, mi = local_opt.refine_trajectory(x0, n)
        if b is not None and t is not None and isinstance(mi, dict):
            candidates.append(("local", (b, t, mi, local_opt)))
            if mi.get("x") is not None:
                seeds.append(np.asarray(mi["x"], dtype=np.float64).copy())
    except Exception as exc:
        log.warning(f"🧭 primer fast 局部精修失敗，繼續短重搜：{exc}")
    local_sec = time.monotonic() - start

    frac = st.get("PRIMER_RESEARCH_ITER_FRAC", 0.33)
    budget = cfg2["optimization"]["MAXITER"]
    cfg2["optimization"]["MAXITER"] = (
        {k: max(1, int(v * frac)) for k, v in budget.items()}
        if isinstance(budget, dict) else max(1, int(budget * frac)))
    start = time.monotonic()
    b, t, mi, opt = run_study_over_revs(cfg2, external_seeds={n: seeds})
    global_sec = time.monotonic() - start
    if b is not None and t is not None and isinstance(mi, dict):
        candidates.append(("global", (b, t, mi, opt)))
    se, eps = optimizer.SPLIT_AWARE_TERMINAL, optimizer.TIEBREAK_SCORE_EPS
    if getattr(optimizer, "SPLIT_LEADING", False):
        winner, result = min(candidates, key=lambda c: _primer_post_rank_key(c[1], eps))
    else:
        winner, result = min(candidates, key=lambda c: _mission_rank_key(
            c[1][2], eps=eps, split_est=se))
    score_by_stage = {
        name: f"{r[2]['score']:.4f}"
        + (f" (split_est={r[2].get('score_split_est', r[2]['score']):.4f})" if se else "")
        for name, r in candidates}
    scores = ", ".join(f"{name}={score_by_stage.get(name, 'unavailable')}"
                       for name in ("original", "local", "global"))
    log.info(f"🧭 primer fast：winner={winner}，local={local_sec:.2f}s，"
             f"global={global_sec:.2f}s，{scores}")
    return None if winner == "original" else result


def _primer_post_rank_key(candidate, eps):
    """拆後比同一把尺，候選本身仍保留拆前資料供 checkpoint 使用。"""
    from odc.pipeline.solve import _final_rank_key
    burns, times, mi, opt = candidate
    _, _, post_mi = _legalize_stage(opt.config, burns, times, mi, opt)
    return (not bool(post_mi.get("earth_safe", True)),) + _final_rank_key(post_mi, eps)
