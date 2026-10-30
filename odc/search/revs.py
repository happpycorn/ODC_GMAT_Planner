"""建立共用搜尋行程池並挑選 REVS 集成贏家
主要入口為 run_study_over_revs。
"""
import os
import copy
import logging
import concurrent.futures
import contextlib
import multiprocessing
import queue
import threading
import time
from threadpoolctl import threadpool_limits
from odc.runlog import log, is_verbose
from tqdm import tqdm
from odc.search.optimizer import MissionOptimizer
from odc.search.ranking import mission_rank_score, pick_best_across_revs


def _run_studies_unified(revs_values, optimizers, seed_set):
    """把所有 (REVS, burn_count) 案例放進同一個行程池，依 REVS 順序收尾。"""
    jobs = [(revs, opt, b) for revs, opt in zip(revs_values, optimizers)
            for b in sorted(opt.burns, reverse=True)]
    cores = os.cpu_count() or 4
    # 未設 SEED 時每個案例還會使用 mealpy thread 模式，至少留兩核心給每個行程。
    worker_slots = min(len(jobs), max(1, cores if seed_set else cores // 2))
    for opt in optimizers:
        log.log(opt._report_level,
                f"🚀 L-SHADE 軌道最佳化：REVS={opt.LAMBERT_MAX_REVS}，"
                f"推進次數 {sorted(opt.burns)}，{len(opt.burns)} 個案例進共用行程池")
        opt.preflight_report()

    budgets = {(revs, b): opt._maxiter_for(b) for revs, opt, b in jobs}
    pbar = tqdm(total=sum(budgets.values()), desc="REVS 集成搜尋世代進度", unit="gen")
    case_progress = {}
    progress_lock = threading.Lock()
    stop_draining = threading.Event()

    def bump(case_id, epoch):
        with progress_lock:
            epoch = min(epoch, budgets[case_id])
            delta = epoch - case_progress.get(case_id, 0)
            if delta > 0:
                pbar.update(delta)
                case_progress[case_id] = epoch

    def drain(progress_queue):
        while not stop_draining.is_set():
            try:
                case_id, epoch = progress_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            except (EOFError, OSError, BrokenPipeError):
                break
            bump(case_id, epoch)

    try:
        with multiprocessing.Manager() as manager:
            progress_queue = manager.Queue()
            drain_thread = threading.Thread(target=drain, args=(progress_queue,), daemon=True)
            drain_thread.start()
            try:
                with concurrent.futures.ProcessPoolExecutor(max_workers=worker_slots) as executor:
                    futures = {}
                    for revs, opt, b in jobs:
                        scalars = opt._scalar_params()
                        vectors = opt._vector_params()
                        future = executor.submit(opt._optimize_burn_case, b, scalars, vectors,
                                                 progress_queue, worker_slots, (revs, b))
                        futures[future] = (revs, opt, b)
                    for future in concurrent.futures.as_completed(futures):
                        revs, opt, b = futures[future]
                        try:
                            b_count, best_x, best_score, epochs_run, note = future.result()
                            log.info(f"✅ REVS={revs} 推進 {b_count} 次完成：目標值 {best_score:.4f}，"
                                     f"跑了 {epochs_run}/{opt._maxiter_for(b_count)} 代{note}")
                            opt.burn_case_results[b_count] = {
                                "fitness": best_score, "epochs_run": epochs_run,
                                "note": note, "best_x": best_x,
                            }
                        except Exception as exc:
                            log.error(f"❌ [核心錯誤] REVS={revs} 推進 {b} 次案例崩潰: {exc}")
                        finally:
                            bump((revs, b), budgets[(revs, b)])
            finally:
                stop_draining.set()
                drain_thread.join(timeout=2.0)
    finally:
        pbar.close()

    results = []
    for opt in optimizers:
        picked = opt._pick_best_case()
        if picked is None:
            results.append((None, None, (None, None)))
        else:
            b, best_x, fitness = picked
            results.append(opt.refine_trajectory(best_x, b, fitness))
    return results


def run_study_over_revs(config, external_seeds=None, oracle_seeds=None):
    """（決策 3 / 2026-09-03）在多個 LAMBERT_MAX_REVS 值上搜尋，
    照規則第 6 節挑最好的那趟交出去，換掉 seed×REVS 相依的搜尋脆弱性。

    為什麼：多圈 Lambert（REVS>0）對**單點**評估是嚴格更大的搜尋空間、不可能更差，
    但它把適應度地形變複雜，L-SHADE 這種隨機搜尋偶爾會落到更差的盆地——實測同 SEED
    下 REVS=4 的最佳解比 REVS=0 少 1.45 分、完整 600 代救不回
    （scripts/research/monotonicity_harness.py），porkchop 對拍又獨立看到 3/8 幾何 REVS=0 贏 REVS=4。
    同 SEED 各跑 REVS=0 與 REVS=LAMBERT_MAX_REVS 再取兩者較好的，就把這條脆弱性換成
    額外搜尋成本。早期串行兩趟約需單趟的 1.8 倍時間；共用案例池縮短牆鐘，CPU 工作量仍相近。

    每趟內部仍自洽用單一 REVS；集成時把 (REVS, burn_count) 案例放進同一個行程池，
    全部搜尋完後依原本 REVS 順序挑選與精修。

    退回單跑：strategy.REVS_ENSEMBLE=false → 只用 strategy.LAMBERT_MAX_REVS
    （預設 4）跑一次。這是大 SMA／高離心率（T_max 天級）跑不完 90 分鐘時降級的
    第一段（§4.1 降級旋鈕）。LAMBERT_MAX_REVS=0 時也自動退成單跑（沒有第二個值可比）。

    回傳 (burns, times, mission_info, optimizer)——最後那個是**勝出那趟**的
    MissionOptimizer 實例，main.py 產腳本／印拆解都要用它（MAX_DV、GRAVITY_DEGREE
    等）。全部失敗時回傳最後一趟的 (None, None, (None, None), optimizer)。
    """
    # 重現性 (2026-09-22)：設了 SEED 代表「要可重現」，但這條保證原本有漏——mealpy 的
    # seed 只鎖到它自己的 RNG（optimizer.py 內另有全域 np.random 補丁），**scipy SLSQP 種子
    # 精修 / L-BFGS-B polish 走的多執行緒 BLAS 沒鎖**。多執行緒 BLAS 浮點歸約 run-to-run
    # 順序不同 → 種子值差在 ~1e-10 → 混沌的 L-SHADE 放大成臨界翻盤（2 vs 3 棒、分數 ±1），
    # 實測同 SEED 同 config 跑兩次 seed pool 不一樣。這裡在 spawn 子行程「之前」pin 住 BLAS
    # 執行緒數；子行程（種子生成＋DE 都在裡面）於 spawn 繼承這份 env、重新 import numpy 時
    # 就吃到單執行緒 BLAS，整條管線才真的可重現。沒設 SEED（要隨機探索）就不動，保留多核速度。
    # 這個 pipeline 是 numba(nogil) 評估為主、BLAS 只有種子精修那點，pin 成 1 的速度代價可忽略。
    #
    # 兩層都要 pin，缺一不可（實測過）：
    #   1. env 設在 spawn「之前」→ 子行程（_optimize_burn_case：種子生成＋DE 都在裡面）繼承、
    #      重新 import numpy 時吃到單執行緒 BLAS。
    #   2. threadpool_limits 包住父行程的搜尋與收尾（收子行程結果後還會做 tiebreak/L-BFGS-B
    #      polish，那段在父行程跑）——父行程的 numpy/BLAS 早在本函式被呼叫前就 import 了，env
    #      這時才設已經來不及，只能用 threadpoolctl 在 runtime 重新限制已載入的 BLAS。
    seed_set = config.get("optimization", {}).get("SEED") is not None
    if seed_set:
        for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
            os.environ[_v] = "1"

    def _blas_ctx():
        # 搜尋與兩趟收尾共用一個 context；seed 沒設就不限制、保留多核。
        return threadpool_limits(limits=1, user_api="blas") if seed_set else contextlib.nullcontext()

    strategy = config.get("strategy", {})
    # 只對明確注入外部種子的 fast 重搜啟用；首次搜尋即使選 fast 仍照舊完整跑。
    primer_fast = bool(external_seeds) and strategy.get("PRIMER_RESEARCH_MODE", "full") == "fast"
    wall = strategy.get("PRIMER_RESEARCH_WALL_SEC", 300) if primer_fast else None
    deadline = time.monotonic() + float(wall) if wall else None
    high_revs = max(0, int(strategy.get("LAMBERT_MAX_REVS", 4)))
    ensemble = bool(strategy.get("REVS_ENSEMBLE", True))

    revs_values = [high_revs] if (not ensemble or high_revs == 0) else sorted({0, high_revs})

    optimizers = []   # 保留每趟的 optimizer 實例給呼叫端用
    multi = len(revs_values) > 1
    for idx, revs in enumerate(revs_values):
        if multi:
            random_note = "同 SEED，只差這個" if seed_set else "各自隨機探索"
            log.info(f"\n🎲 REVS 集成 案例組 {idx + 1}/{len(revs_values)}："
                     f"LAMBERT_MAX_REVS={revs}（{random_note}）")
        cfg = copy.deepcopy(config)
        cfg.setdefault("strategy", {})["LAMBERT_MAX_REVS"] = revs
        opt = MissionOptimizer(cfg)
        if primer_fast:
            opt._primer_fast_research = True
            opt._primer_search_deadline = deadline
        if external_seeds:                       # C2：primer 指路的插棒種子（見 main）
            opt.external_seeds = external_seeds
        if oracle_seeds:
            opt.oracle_seeds = oracle_seeds
        # 集成時把每趟的大塊報告壓成 DEBUG（console 預設不印、-v/log 檔仍看得到），
        # 避免同一份報告在 console 上印每一趟——只在下面把勝出趟以 INFO 重印一次。
        if multi:
            opt._report_level = logging.DEBUG
        optimizers.append(opt)

    with _blas_ctx():
        if multi:
            results = _run_studies_unified(revs_values, optimizers, seed_set)
        else:
            results = [optimizers[0].run_study()]
    candidates = [(revs, *result) for revs, result in zip(revs_values, results)]

    if len(candidates) == 1:
        _, burns, times, mission_info = candidates[0]
        return burns, times, mission_info, optimizers[0]

    split_est = optimizers[0].SPLIT_AWARE_TERMINAL
    best_i, floor_disagrees = pick_best_across_revs(
        candidates, eps=optimizers[0].TIEBREAK_SCORE_EPS, split_est=split_est)

    # C4 退路：各趟的「最佳零違規候選」取真實分數最高的，掛到勝出那趟 optimizer 上
    # （備胎自己帶著它的 optimizer，拆棒失敗時用它自己的 REVS 精修）。
    backups = [o.legal_backup for o in optimizers if o.legal_backup is not None]
    if backups:
        optimizers[best_i].legal_backup = max(backups, key=lambda bk: bk["score"])

    # 集成對照表：把每趟的成績並排攤開，選了誰、差多少都講白（這是集成的決策，留 INFO）。
    est_hdr = f"{'拆後估計':>10}" if split_est else ""
    table = [f"\n🏁 REVS 集成結果（規則第 6 節：Score → Δr_min → ΔV_team → T_team"
             f"{'；Score 用拆後估計' if split_est else ''}）",
             f"   {'REVS':>5}{'Score':>10}{est_hdr}{'Δr_min(m)':>13}{'ΔV_team(m/s)':>15}{'T_team(s)':>13}"]
    for i, (revs, _b, _t, mi) in enumerate(candidates):
        if isinstance(mi, dict):
            mark = "  ← 採用" if i == best_i else ""
            est_col = f"{mission_rank_score(mi, True):>10.4f}" if split_est else ""
            table.append(f"   {revs:>5}{mi['score']:>10.4f}{est_col}{mi['miss_km'] * 1000:>13,.1f}"
                         f"{mi['total_dv_mps']:>15,.1f}{mi['T_team']:>13,.1f}{mark}")
        else:
            table.append(f"   {revs:>5}   （這趟全軍覆沒，不列入挑選）")
    log.info("\n".join(table))
    if floor_disagrees:
        log.warning("⚠️ §6優先序1的另一種讀法（Δr_min 套 max(Δr,5) 地板）會選出不同贏家"
                    "——上表數字自己看了定案（見 tiebreak_rank_key）。")

    _, burns, times, mission_info = candidates[best_i]
    if burns is None:
        # 全部失敗：排位賽模式下各趟可能各留一個「最接近合法」的失格候選，取違規最少的掛到
        # 回傳的 optimizer 上 (main 存成 no_legal_route.json)。它帶著自己那趟的 optimizer。
        nlr = [(o.no_legal_route["fitness"], i) for i, o in enumerate(optimizers)
               if o.no_legal_route is not None]
        if nlr:
            return None, None, None, optimizers[min(nlr)[1]]
    # 勝出那趟的任務規劃 + Python 預測，以 INFO 重印一次（每趟跑的時候是 DEBUG）。
    if isinstance(mission_info, dict) and mission_info.get("report_text"):
        log.info(mission_info["report_text"])
    return burns, times, mission_info, optimizers[best_i]
