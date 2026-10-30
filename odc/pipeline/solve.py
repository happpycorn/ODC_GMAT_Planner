"""執行搜尋、primer、oracle 比較與多種子挑選
主要入口為 run_seed_portfolio。
"""
import os
import time
import copy
from odc.pipeline.artifacts import (create_run_dir, save_mission, load_mission,
                                    write_json, file_digest, provenance)
import numpy as np
from odc.search.optimizer import MissionOptimizer
from odc.search.revs import run_study_over_revs
from odc.search.replay import reconstruct_mission_logs
from odc.search.ranking import _mission_rank_key, over_dv_count, is_disqualified
from odc.runlog import log, setup as setup_logging
from odc.pipeline.checkpoints import _to_jsonable, save_winner_checkpoint
from odc.pipeline.legalize import _fallback_to_legal_backup, _legalize_stage
from odc.pipeline.primer_stage import primer_guided_research


def _search_stage(config, oracle_seeds=None):
    """搜尋 + C2 primer 條件式重搜（拆棒之前的部分）。回傳 (burns, times, mission_info, optimizer)；
    搜尋失敗回 (None, None, None, optimizer)——optimizer 可能帶著 no_legal_route（排位賽模式下
    最接近合法的失格候選）。`_solve_pipeline` 與 C4 退路重搜共用。"""
    if oracle_seeds:
        burns, times, mi, opt = run_study_over_revs(config, oracle_seeds=oracle_seeds)
    else:
        burns, times, mi, opt = run_study_over_revs(config)
    if burns is None or times is None:
        return None, None, None, opt
    _c2 = primer_guided_research(config, burns, times, mi, opt)
    if _c2 is not None:
        burns, times, mi, opt = _c2
    return burns, times, mi, opt


def _final_rank_key(mi, eps=None):
    """拆棒之後（交件前）比兩個候選用的排名鍵：失格的一律排在不失格的後面，其餘照§6。
    拆棒前的路線仍用拆後估計；SPLIT_LEADING 開時 C2 先拆兩邊，再用這裡比較。"""
    return (is_disqualified(mi),) + _mission_rank_key(mi, eps=eps)


def _solve_pipeline(config, output_dir="outputs"):
    st = config.get("strategy", {})
    if st.get("ORACLE_TWOBURN", False) or st.get("ORACLE_TWOBURN_SEED_DE", False):
        return _solve_with_oracle(config, output_dir)
    return _solve_de_pipeline(config, output_dir)


def _solve_de_pipeline(config, output_dir="outputs", oracle_seeds=None):
    """一顆 SEED 的完整求解：搜尋 → C2 primer 條件式重搜 →（Earth-safe 時）拆棒合法化。
    回傳 (burns, times, mission_info, optimizer)；搜尋失敗回 (None, None, None, None)。
    **不印 Earth-safe 警告**——那只該對最終勝出解印一次（見 main / run_seed_portfolio），
    不然 seed-portfolio 會對每顆中間候選都吼一次。

    拆棒前的贏家會存到本次執行目錄的 `winner_presplit_seed<SEED>.json`（見 save_winner_checkpoint）。"""
    if oracle_seeds:
        burns, times, mi, opt = _search_stage(config, oracle_seeds=oracle_seeds)
    else:
        burns, times, mi, opt = _search_stage(config)
    if burns is None or times is None:
        return None, None, None, opt
    seed = config.get("optimization", {}).get("SEED")
    try:
        save_winner_checkpoint(
            os.path.join(output_dir, f"winner_presplit_seed{'none' if seed is None else seed}.json"),
            opt, burns, times, mi)
    except (OSError, TypeError) as exc:            # 存檔失敗不該擋管線
        log.warning(f"⚠️ 拆棒前贏家存檔失敗（不影響本次結果）：{exc}")
    if config.get("strategy", {}).get("ORACLE_TWOBURN", False):
        opt._oracle_presplit_leading_mps = float(np.linalg.norm(burns[0]) * 1000) if len(burns) > 1 else 0.0
    burns, times, mi = _legalize_stage(config, burns, times, mi, opt)
    burns, times, mi, opt = _fallback_to_legal_backup(config, burns, times, mi, opt)
    save_mission(os.path.join(output_dir, f"mission_seed{'none' if seed is None else seed}.json"),
                 opt.config, burns, times, mi)
    return burns, times, mi, opt


def _solve_with_oracle(config, output_dir):
    # Imported only on the enabled path: no numba/runtime or output changes off.
    from odc.search.oracle_worker import OracleJob, oracle_core_budget
    from odc.search.oracle_twoburn import standard_x_from_route

    st = config.get("strategy", {})
    started = time.monotonic()
    deadline = started + float(st.get("ORACLE_TWOBURN_WALL_SEC", 600))
    routes, entries, seeds, job = None, [], {}, None
    oracle_wall = 0.0
    try:
        if st.get("ORACLE_TWOBURN_SEED_DE", False):
            # Same grid feeds both arms. No external_seeds / primer fast flag.
            sync = OracleJob(config, cores=os.cpu_count() or 4, deadline=deadline, grid_only=True)
            routes, _ = sync.collect()
            oracle_wall += sync.wall_sec
            seed_opt = MissionOptimizer(config)
            for route in routes:
                x, n = standard_x_from_route(seed_opt, route["t1"], route["dv1"], route["t2"], route["t3"])
                if n in seed_opt.burns:
                    seeds.setdefault(n, []).append(x)
        if st.get("ORACLE_TWOBURN", False) and time.monotonic() < deadline:
            spare = oracle_core_budget(config)
            log.info("Oracle background core budget: %d", spare)
            if spare == 1:
                log.info("Oracle spare=1：可能與 DE 搶一個核心")
            job = OracleJob(config, cores=spare, deadline=deadline, routes=routes)
    except Exception as exc:
        log.warning("Oracle startup/grid failed (DE continues): %s", exc)

    try:
        result = _solve_de_pipeline(config, output_dir, oracle_seeds=seeds)
        if job is not None:
            try:
                routes, entries = job.collect()
                oracle_wall += job.wall_sec
            except Exception as exc:
                log.warning("Oracle collection failed (DE continues): %s", exc)
    finally:
        if job is not None:
            job.close()

    b, t, mi, opt = result
    table = ["Oracle comparison: source / pre-rank / leading m/s / post-score / burns / total m/s / DQ"]
    if b is not None:
        de_leading = getattr(opt, "_oracle_presplit_leading_mps", np.linalg.norm(b[0])*1000 if len(b)>1 else 0.)
        table.append(f"DE / - / {de_leading:.3f} / "
                     f"{mi['score']:.6f} / {mi['num_burns']} / {mi['total_dv_mps']:.3f} / {is_disqualified(mi)}")
    selected = None
    for entry in entries:
        cb, ct, cm, co = entry["candidate"]
        route = entry["route"]
        leading = 0.0 if route["dv1"] is None else float(np.linalg.norm(route["dv1"]) * 1000)
        table.append(f"oracle / {route['rank']} / {leading:.3f} / {cm['score']:.6f} / "
                     f"{cm['num_burns']} / {cm['total_dv_mps']:.3f} / {is_disqualified(cm)}")
        eps = opt.TIEBREAK_SCORE_EPS if opt is not None else co.TIEBREAK_SCORE_EPS
        # Earth-unsafe candidates cannot win even if their score is high.
        if bool(cm.get("earth_safe", True)) and (b is None or
                _final_rank_key(cm, eps=eps) < _final_rank_key(mi, eps=eps)):
            b, t, mi, opt = cb, ct, cm, co
            selected = entry
    log.info("\n".join(table))
    seed = config.get("optimization", {}).get("SEED")
    suffix = 'none' if seed is None else seed
    try:
        payload = dict(routes=routes or [], seeds=seeds, wall_sec=oracle_wall,
                       pipeline_wall_sec=time.monotonic() - started,
                       candidates=[dict(route=e["route"], x=e["x"], N=e["N"],
                                        post_mission=e["candidate"][2], wall_sec=e["wall_sec"],
                                        elapsed_sec=e["elapsed_sec"]) for e in entries])
        write_json(os.path.join(output_dir, f"oracle_candidates_seed{suffix}.json"), _to_jsonable(payload))
        if selected is not None:
            save_winner_checkpoint(os.path.join(output_dir, f"winner_presplit_seed{suffix}.json"),
                                   opt, *selected["presplit"])
            save_mission(os.path.join(output_dir, f"mission_seed{suffix}.json"), opt.config, b, t, mi)
    except (OSError, TypeError) as exc:
        log.warning("Oracle artifact save failed (result remains available): %s", exc)
    return b, t, mi, opt


def run_seed_portfolio(config, output_dir="outputs"):
    """Seed-portfolio 小模式（2026-09-22）：跑 N 顆 SEED 各自完整求解（含拆棒合法化），
    照規則§6 留**拆後**分最高的那顆。

    動機（本 session contest 分析）：單一 SEED 是決定性的，但可能抽到「低籤」——落在略差
    的盆地 / 拆棒後差那 0.01。跑幾顆再留拆後最高分，幾乎免費穩拿家族高端（實測 +0.008）。
    這是繳交前的品質旋鈕，不是搜尋演算法改動。

    N = strategy.SEED_PORTFOLIO_N（預設 1 = 關，行為與單跑逐位元相同）。基準 SEED 取
    optimization.SEED（沒設用 0），跑 base..base+N-1 保證可重現。回傳勝出的
    (burns, times, mission_info, optimizer)。"""
    N = max(1, int(config.get("strategy", {}).get("SEED_PORTFOLIO_N", 1)))
    if N == 1:
        return _solve_pipeline(config, output_dir)

    base = config.get("optimization", {}).get("SEED")
    base = 0 if base is None else int(base)
    best, nlr_opt = None, None
    table = [f"\n🎰 Seed-portfolio：跑 {N} 顆 SEED，§6 留拆後分最高（避開低籤）",
             f"   {'SEED':>6}{'Score':>10}{'Δr_min(m)':>13}{'ΔV_team(m/s)':>15}{'棒數':>6}"]
    for i in range(N):
        sd = base + i
        cfg = copy.deepcopy(config)
        cfg.setdefault("optimization", {})["SEED"] = sd
        log.info(f"\n🎰 Seed-portfolio 第 {i + 1}/{N} 顆（SEED={sd}）")
        b, t, mi, opt = _solve_pipeline(cfg, output_dir)
        if b is None or not isinstance(mi, dict):
            table.append(f"   {sd:>6}   （全軍覆沒，不列入挑選）")
            nlr = getattr(opt, "no_legal_route", None)
            if nlr is not None and (nlr_opt is None
                                    or nlr["fitness"] < nlr_opt.no_legal_route["fitness"]):
                nlr_opt = opt
            continue
        key = _final_rank_key(mi, eps=opt.TIEBREAK_SCORE_EPS)
        table.append(f"   {sd:>6}{mi['score']:>10.4f}{mi['miss_km'] * 1000:>13,.1f}"
                     f"{mi['total_dv_mps']:>15,.1f}{mi['num_burns']:>6}"
                     + ("   🔴失格" if is_disqualified(mi) else ""))
        if best is None or key < best[0]:
            best = (key, sd, b, t, mi, opt)
    if best is None:
        log.error("Seed-portfolio：所有 SEED 都沒跑出可用解。")
        return None, None, None, nlr_opt
    table.append(f"   → 採用 SEED={best[1]}（Score {best[4]['score']:.4f}，{best[4]['num_burns']} 棒）")
    log.info("\n".join(table))
    return best[2], best[3], best[4], best[5]
