"""解析求解選項，依輸入方案分派求解、輸出與驗證階段
主要入口為 main。
"""
# 此模組承接既有任務求解、存檔與腳本輸出管線。
# 主要入口為 main(argv=None)，沿用原工具的選項與計算。

# 引入重構後的新模組
from odc.paths import default_config_path
import sys
import time
import json
import warnings
import argparse
import datetime
import multiprocessing
import copy
import cProfile
import pstats
from pathlib import Path
from odc.pipeline.artifacts import (create_run_dir, save_mission, load_mission,
                                    write_json, file_digest, provenance)
from odc.search.optimizer import MissionOptimizer
from odc.search.revs import run_study_over_revs
from odc.search.replay import reconstruct_mission_logs
from odc.search.ranking import _mission_rank_key, over_dv_count, is_disqualified
from odc.gmat.script_generator import script_generator
from odc.config.gmat_env import GMAT_ENV_KEYS, resolve_gmat_env, validate_gmat_env
from odc.gmat.retarget import retarget_full_perturbation
from odc.runlog import log, setup as setup_logging
from odc.config.defaults import GMAT_CONSOLE_DEFAULT, load_or_create_config
from odc.gmat.verification import run_gmat_verification
from odc.pipeline.checkpoints import EXIT_NO_LEGAL_ROUTE, NoLegalRouteError, load_winner_checkpoint, save_no_legal_route
from odc.pipeline.legalize import _fallback_to_legal_backup, _legalize_stage
from odc.pipeline.report import append_run_history, print_score_breakdown
from odc.pipeline.solve import run_seed_portfolio


# 是否開啟效能分析 (True: 顯示 Top 20 耗時函式)。預設關閉：這份報告主要反映的是主行程
# 「等待」子行程/執行緒的時間，不太能看出真正的運算熱點在哪，平常跑正式結果會被這一大
# 串洗版；真的要抓效能瓶頸時再手動打開。
ENABLE_PROFILING = False


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="軌道攔截設計賽 - 任務規劃與計分工具")
    parser.add_argument(
        "--config", default=None,
        help="設定檔路徑 (預設 configs/local/config.json)，方便在測試資料/正式測資之間切換而不用互相覆蓋"
    )
    parser.add_argument(
        "--gmat-console", default=None,
        help="GmatConsole 執行檔路徑，用來自動跑無頭驗證。不給的話依序改抓 config.json 的"
             "local.gmat_console_path、再來是這台機器上寫死的最後備援值"
    )
    parser.add_argument(
        "--no-gmat", action="store_true",
        help="跳過自動 GMAT 驗證這一步，只產生 script"
    )
    parser.add_argument(
        "--no-fixed-script", action="store_true",
        help="跳過『固定燃燒版本』的產生+驗證。預設：一般版本 (本次目錄的 output.txt，"
             "最後一棒靠 GMAT 的 DC 求解器收斂) 通過驗證後，會自動把 GMAT 收斂後的"
             "燃燒值寫死、產生一份不含任何求解器的版本 (output_submit.txt)，"
             "適合正式繳交——換一台電腦跑也不用擔心求解器行為不一致，因為根本沒有"
             "求解器在跑。開發/迭代時想省這幾秒可以加這個旗標跳過。"
    )
    sources = parser.add_mutually_exclusive_group()
    sources.add_argument(
        "--from-winner", default=None, metavar="JSON",
        help="跳過搜尋，從拆棒前贏家存檔（本次目錄的 winner_presplit_seed*.json，每次完整跑都會"
             "自動存）直接接拆棒合法化 + 產腳本 + GMAT。改拆棒器/驗證時用，幾分鐘一輪。"
             "此模式下軌道/規則一律取存檔內的 config，--config 只用來找 GmatConsole 路徑"
    )
    sources.add_argument("--from-mission", metavar="JSON",
                         help="讀拆棒後 mission.json，跳過搜尋與拆棒，接產腳本/GMAT；使用存檔設定")
    sources.add_argument("--verify-script", metavar="SCRIPT",
                         help="只用 GMAT 驗證既有腳本，在新目錄保存報表，不重新求解或產生任務")
    parser.add_argument(
        "--retarget-full-perturbation", action="store_true",
        help="搭配 --from-mission：在 GMAT 排位賽全攝動模型下用 B 平面 DifferentialCorrector 改一棒，"
             "重新判定命中/Earth-safe/單棒與總 Δv，通過才產生全攝動固定燃燒繳交腳本；"
             "失敗或失格時保留原方案並警告。輸出在新的執行目錄，不動原方案")
    parser.add_argument(
        "--retarget-burn", type=int, default=None, metavar="N",
        help="重瞄準要改哪一棒（0 起算，跟腳本的 BurnB<N> 同編號；負數從後面數）。預設 -1＝最後一棒")
    parser.add_argument("--stop-after", choices=("solve", "export", "verify"), default="verify",
                        help="停在求解存檔/產腳本/GMAT 驗證（預設 verify）")
    parser.add_argument("--run-dir", help="本次輸出目錄，必須尚不存在；預設 outputs/runs/<唯一識別碼>")
    parser.add_argument("--model-scale", type=float,
                        help="只調整產出腳本的飛船模型大小（0.001~1000），可與 --from-mission 一起使用")
    # 執行期輸出的詳略（HAP-68）。預設終端機只印事件級摘要，完整 DEBUG 一律寫進
    # outputs/run.log，事後要追細節去撈那個檔就好。
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="終端機印出完整 DEBUG（每趟完整報告、逐項比對、VNB 向量、scipy 迭代碎念）"
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true",
        help="終端機只印 WARNING 以上（適合排程/批次跑）；完整細節照樣寫進本次目錄的 run.log"
    )
    args = parser.parse_args(argv)
    if args.model_scale is not None and not 0.001 <= args.model_scale <= 1000:
        parser.error("--model-scale 必須介於 0.001 與 1000")
    if args.model_scale is not None and (args.verify_script or args.stop_after == "solve"):
        parser.error("--model-scale 只適用於產腳本階段")
    if args.verify_script and (args.no_gmat or args.stop_after != "verify" or args.no_fixed_script):
        parser.error("--verify-script 不可搭配停止/跳過驗證選項")
    if args.retarget_burn is not None and not args.retarget_full_perturbation:
        parser.error("--retarget-burn 只能搭配 --retarget-full-perturbation")
    if args.retarget_full_perturbation:
        if not args.from_mission:
            parser.error("--retarget-full-perturbation 需要 --from-mission（拆棒後的 mission.json）")
        if args.no_gmat or args.stop_after != "verify" or args.no_fixed_script:
            parser.error("--retarget-full-perturbation 一定要跑 GMAT，不可搭配 --no-gmat/--stop-after/"
                         "--no-fixed-script")
        if args.retarget_burn is None:
            args.retarget_burn = -1
    if args.no_gmat and args.stop_after == "verify":
        args.stop_after = "export"
    return args


def main(argv=None):
    multiprocessing.freeze_support()
    warnings.filterwarnings("ignore")
    args = parse_args(argv)
    run_dir = create_run_dir(args.run_dir)
    setup_logging(verbose=args.verbose, quiet=args.quiet,
                  logfile=str(run_dir / "run.log"))
    log.info(f"📂 本次輸出：{run_dir}")
    start_time = time.perf_counter()
    manifest = {"schema_version": 1, "status": "running", "arguments": vars(args).copy(),
                "provenance": provenance(), "timings_sec": {}}
    write_json(run_dir / "run.json", manifest)
    profiler = cProfile.Profile() if ENABLE_PROFILING else None
    if profiler:
        profiler.enable()
    try:
        _run_stages(args, run_dir, manifest)
        manifest["status"] = "completed"
    except BaseException as exc:
        manifest["status"] = "no_legal_route" if isinstance(exc, NoLegalRouteError) else "failed"
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        manifest["elapsed_sec"] = time.perf_counter() - start_time
        write_json(run_dir / "run.json", manifest)
        if profiler:
            profiler.disable()
            pstats.Stats(profiler).sort_stats("tottime").print_stats(20)


def _run_stages(args, run_dir, manifest):
    # Replay needs no default config file. Explicit --config on replay supplies
    # the local GMAT path only; physics always comes from the snapshot.
    local_config = {}
    if args.config:
        if (args.from_winner or args.from_mission or args.verify_script) and not Path(args.config).is_file():
            raise ValueError(f"找不到指定的本機設定檔：{args.config}")
        local_config = load_or_create_config(args.config)
    config = local_config
    source_path = args.from_mission or args.from_winner or args.verify_script
    source = ({"path": str(Path(source_path).resolve()), "sha256": file_digest(source_path)}
              if source_path else None)
    manifest["source"] = source
    if args.verify_script:
        console = (args.gmat_console or local_config.get("local", {}).get("gmat_console_path")
                   or GMAT_CONSOLE_DEFAULT)
        started = time.perf_counter()
        result = run_gmat_verification(console, args.verify_script, artifacts_dir=run_dir / "gmat")
        manifest["timings_sec"]["verify"] = time.perf_counter() - started
        manifest["verification"] = result
        if result is None:
            raise RuntimeError("GMAT 執行失敗；詳見本次驗證目錄。")
        evidence = json.loads((run_dir / "gmat" / "verification.json").read_text(encoding="utf-8"))
        manifest["verification_status"] = "completed"
        manifest["checks_passed"] = evidence["checks_passed"]
        if evidence["checks_passed"]:
            log.info("✅ GMAT 獨立驗證通過（命中、末棒合規、最低半徑及必要的 DC 收斂檢查）。")
        else:
            log.warning("⚠️ GMAT 已執行，但命中、末棒合規、最低半徑或 DC 收斂檢查未通過；不可繳交，詳見 verification.json。")
        manifest["last_stage"] = "verify"
        return

    started = time.perf_counter()
    if args.from_mission:
        payload = load_mission(args.from_mission)
        config = payload["config"]
        burns, times, mission_info = payload["burns"], payload["times"], payload["mission_info"]
        optimizer = MissionOptimizer(config)
        source["artifact_id"] = payload["artifact_id"]
        log.info("♻️ 讀取拆棒後方案：跳過搜尋與拆棒。")
    elif args.from_winner:
        config, burns, times, mission_info, optimizer = load_winner_checkpoint(args.from_winner)
        log.info(f"♻️ 從拆棒前存檔重播：{args.from_winner}")
        burns, times, mission_info = _legalize_stage(config, burns, times, mission_info, optimizer)
        # 存檔不含搜尋時的合法備胎，拆不出時退路會直接走「旗標關重搜」（一輪完整搜尋）
        burns, times, mission_info, optimizer = _fallback_to_legal_backup(
            config, burns, times, mission_info, optimizer)
    else:
        if not args.config:
            config = load_or_create_config(default_config_path())
        burns, times, mission_info, optimizer = run_seed_portfolio(config, output_dir=run_dir)

    if burns is None or times is None:
        if getattr(optimizer, "no_legal_route", None) is not None:
            path = save_no_legal_route(run_dir / "no_legal_route.json", optimizer)
            manifest["no_legal_route"] = str(path)
            raise NoLegalRouteError(f"找不到合法路線；最接近的失格候選存在 {path}")
        raise RuntimeError("求解失敗，沒有可保存的方案。")
    config = optimizer.config  # retain actual winning seed, REVS and primer settings
    manifest["timings_sec"]["load_mission" if args.from_mission else "solve"] = time.perf_counter() - started
    artifact_id = save_mission(run_dir / "mission.json", config, burns, times, mission_info, source)
    manifest["mission_id"] = artifact_id
    manifest["last_stage"] = "solve"
    write_json(run_dir / "run.json", manifest)
    log.info(f"💾 求解結果已保存：{run_dir / 'mission.json'}")
    if args.stop_after == "solve":
        return
    console = (args.gmat_console
               or local_config.get("local", {}).get("gmat_console_path")
               or config.get("local", {}).get("gmat_console_path")
               or GMAT_CONSOLE_DEFAULT)
    args.no_gmat = args.stop_after == "export"
    export_config = copy.deepcopy(config)
    if args.model_scale is not None:
        export_config.setdefault("strategy", {})["GMAT_MODEL_SCALE"] = args.model_scale
    if args.retarget_full_perturbation:
        run_retarget_stage(export_config, burns, times, mission_info, optimizer, args=args,
                           run_dir=run_dir, gmat_console_path=console, manifest=manifest,
                           local_config=local_config)
        return
    run_output_stage(export_config, burns, times, mission_info, optimizer,
                     args=args, run_dir=run_dir, gmat_console_path=console, manifest=manifest)


def run_output_stage(config, burns, times, mission_info, optimizer, *, args, run_dir,
                     gmat_console_path, manifest):
    """Export/verify a solved mission without invoking search, primer or splitting."""
    start_time = time.perf_counter()

    # Earth-safe 硬性閘門 (2026-09-09, HAP-48)：初賽證實「軌跡穿過地表」是官方失格線
    # (撞地球的隊伍被判 F)。搜尋端 (fast_fitness_evaluator) 本來就會避開撞地球的解，
    # 但當 T_max 內根本沒有 Earth-safe 合法解時，搜尋只能回報「最不爛」的違規解，那有
    # 可能是鑽地球的。這裡在繳交路徑上再擋一次（對最終勝出解印一次）：撞地球就不產生
    # 繳交腳本、大聲標記，避免重演「分數漂亮但物理不成立、送出去被失格」(見作廢的 99.996)。
    earth_safe = bool(mission_info.get("earth_safe", False))
    if not earth_safe:
        alt = mission_info.get("min_arc_radius_km", float("nan")) - 6378.137
        log.warning("\n" + "🔴" * 30
                    + f"\n  警告：這個解的軌跡會穿過地球 (全程最低高度 {alt:,.0f} km，低於地表)。"
                    + "\n  官方會判此類軌跡失格 (初賽已證實)，**不會產生繳交腳本，絕對不可繳交**。"
                    + "\n  通常代表 T_max 內沒有 Earth-safe 合法解 —— 用 feasibility.py 確認，"
                    + f"\n  或放寬 T_max / 調整棒數再重跑。仍會產出 {run_dir / 'output.txt'} 供診斷。"
                    + "\n" + "🔴" * 30)

    # 失格閘門 (2026-10-19，排位賽規則)：單棒 Δv > MAX_DV_MPS + 1e-5 m/s、或總 Δv >
    # MAX_TOTAL_DV_MPS 直接失格（初賽的單棒超標是扣 10 分，現在不是）。搜尋時這些只是軟懲罰、
    # 讓 DE 能找超標路線交給拆棒器；拆不出合法版時走到這裡就要大聲擋，跟 Earth-safe 閘門一樣
    # 不產生固定燃燒的繳交腳本。
    disqualified = is_disqualified(mission_info)
    manifest["disqualified"] = disqualified
    if disqualified:
        reasons = mission_info.get("dq_reasons") or [f"{over_dv_count(mission_info)} 棒單棒 Δv 超標"]
        log.warning("\n" + "🔴" * 30
                    + "\n  警告：這個解違反排位賽硬性限制，官方會直接判失格："
                    + "".join(f"\n    • {r}" for r in reasons)
                    + "\n  **不會產生繳交腳本，絕對不可繳交**。報表裡的分數只是搜尋用分數。"
                    + "\n  單棒超標：確認 AUTO_SPLIT_LEGALIZE 有開、或放寬 T_max / 棒數重跑；"
                    + "\n  總 Δv 超標：拆棒救不了，要換路線（feasibility.py 看能量下界）。"
                    + f"\n  仍會產出 {run_dir / 'output.txt'} 供診斷。"
                    + "\n" + "🔴" * 30)

    # 分數拆解 + 交換率（純加印，不改計算；見 print_score_breakdown）
    print_score_breakdown(mission_info, optimizer)

    # GMAT 端環境（力學模型/太空船參數/曆元；全部沒設時跟以前逐位元相同，見 odc/config/gmat_env.py）
    gmat_env = resolve_gmat_env(config)
    if gmat_env["force_model"] == "ranking_full":
        log.warning("⚠️ FORCE_MODEL=ranking_full：一般版腳本的 DC 是「預定時刻位置對齊」，在全攝動下"
                    "可能很貴（hyper_far 實測 +272 m/s、末棒 361 m/s → 失格），Python 端也還是 J2–J4，"
                    "兩邊對不上是預期的。建議 FORCE_MODEL 維持 contest_prelim，產出 mission.json 後再用 "
                    "--from-mission <mission.json> --retarget-full-perturbation。")

    # 2. 產出 GMAT 腳本 (打靶邊界跟著規則的 ΔV_lim 走，避免 GMAT 端偷偷超標)
    script_path = script_generator(
        config["orbit_A"]["SMA"], config["orbit_A"]["ECC"], config["orbit_A"]["INC"],
        config["orbit_A"]["RAAN"], config["orbit_A"]["AOP"], config["orbit_A"]["TA"],
        config["orbit_B"]["SMA"], config["orbit_B"]["ECC"], config["orbit_B"]["INC"],
        config["orbit_B"]["RAAN"], config["orbit_B"]["AOP"], config["orbit_B"]["TA"],
        burns, times, aim_point=mission_info["aim_point"],
        max_dv=optimizer.MAX_DV, gravity_degree=optimizer.GRAVITY_DEGREE,
        model_scale=config.get("strategy", {}).get("GMAT_MODEL_SCALE", 0.5),
        output_dir=run_dir, **gmat_env,
    )

    end_time = time.perf_counter()
    execution_time = end_time - start_time

    minute_note = f" (約 {execution_time / 60:.2f} 分鐘)" if execution_time > 60 else ""
    manifest["timings_sec"]["export"] = execution_time
    manifest["last_stage"] = "export"
    write_json(run_dir / "run.json", manifest)
    log.info(f"\n⏳ 產腳本時間: {execution_time:.2f} 秒{minute_note}")

    # 3. 自動呼叫 GMAT 做無頭驗證，不用再手動開 GUI 點來點去
    gmat_result = None
    if args.no_gmat:
        log.info(f"（尚未 GMAT 驗證；可用 --verify-script {script_path} 單獨執行）")
    else:
        started = time.perf_counter()
        gmat_result = run_gmat_verification(gmat_console_path, script_path,
                                             artifacts_dir=run_dir / "gmat_dc")
        manifest["timings_sec"]["gmat_dc"] = time.perf_counter() - started
        if gmat_result:
            match = "✅" if gmat_result["intercept_success"] else "❌"
            dv_match = "✅" if gmat_result["final_burn_legal"] else "❌"
            # 一般版本 (DC) 結果：終端機給一行事件摘要 (命中/Targeter/最後一棒)；GMAT vs Python
            # 的逐項比對表是診斷細節，收進 DEBUG（-v 或 outputs/run.log 看，見準則：GMAT 表 → -v）。
            d_miss = abs(gmat_result['miss_km'] - mission_info['miss_km']) * 1000.0
            d_dv = abs(gmat_result['final_burn_dv_mps'] - mission_info['final_burn_dv_mps'])
            log.info(f"🛰️ GMAT 一般版(DC)：命中 {match} {'成功' if gmat_result['intercept_success'] else '失敗'}"
                     f"   Targeter {'✅收斂' if gmat_result['targeter_converged'] else '⚠️未收斂'}"
                     f"   最後一棒 {dv_match} {'合規' if gmat_result['final_burn_legal'] else '超過上限'}"
                     f"   (Δr {gmat_result['miss_km']*1000:,.0f}m)")
            log.debug(
                f"── GMAT 驗證：一般版本 (含 DC 求解器) {'─' * 22}\n"
                f"  {'':<12}{'GMAT':>14}{'Python':>14}{'差距':>12}\n"
                f"  {'Δr_min':<12}{gmat_result['miss_km']*1000:>13,.3f}m"
                f"{mission_info['miss_km']*1000:>13,.3f}m{d_miss:>11,.3f}m\n"
                f"  {'最後一棒 Δv':<10}{gmat_result['final_burn_dv_mps']:>13,.1f}m/s"
                f"{mission_info['final_burn_dv_mps']:>11,.1f}m/s{d_dv:>9,.1f}m/s\n"
                f"  {'T_team':<12}{gmat_result['t_team_sec']:>13,.2f}s"
                f"{mission_info['T_team']:>13,.2f}s\n"
                f"  報表：{gmat_result['report_path']}")

    # 3.5 產生「固定燃燒版本」(不含任何求解器，單純傳播+施加燃燒)。
    #
    # 燃燒值來源分兩種情況：
    # (a) 一般版本 (DC) 驗證乾淨通過 → 用 GMAT 自己收斂出的值 (最可信，GMAT 高精度模型
    #     自己找到的答案)。
    # (b) 一般版本沒有乾淨通過 (DC 沒收斂 / 命中失敗) → 改用 Python 自己 (refine_lambert_burn)
    #     算出的值當 fallback。這個分支存在的理由：DC 的 Vary 邊界寫死卡在合法 Δv 範圍
    #     (script_generator 的 max_dv 參數)，如果真正需要的燃燒本來就超過規則上限，DC
    #     不管怎樣都不可能收斂到那個值——這不代表 Python 找到的方案是垃圾，只代表「透過
    #     GMAT DC 求解」這條路線走不通。初賽規則第 5 節：單次燃燒超標只是每次扣 10 分，
    #     所以「命中但超標」當時仍值得跑出來看分數。排位賽起超標直接失格——Python 端判定
    #     失格的解在上面的失格閘門就不會走到這裡；Python 判合法、GMAT 卻說末棒超標的，
    #     fallback 照樣跑，但結果會標成「失格、不可繳交」。用 Python 自己的值繞過 DC 直接驗證，才知道這個方案實際上能不能重現、
    #     真正的 Δv 是多少。
    #
    # 兩種情況都需要先確認 mission_info["dc_converged"] (Python 端 refine_lambert_burn
    # 有沒有在它自己的模型內收斂到瞄準點)——如果連 Python 自己都沒收斂，代表這組解本身
    # 就沒有一個自洽的燃燒值可以拿來 fallback，兩條路都走不通。
    fixed_script_result = None
    fixed_script_source = None  # "gmat_dc" | "python_fallback" | None，寫進 run_history 方便回頭查
    if not earth_safe:
        # Earth-safe 閘門擋下 (HAP-48)：撞地球的解不產生繳交腳本，避免手滑送出去被失格。
        log.warning("⛔ Earth-safe 閘門：此解撞地球，跳過『固定燃燒版本』繳交腳本的產生。")
    elif disqualified:
        log.warning("⛔ 失格閘門：此解違反單棒/總 Δv 上限，跳過『固定燃燒版本』繳交腳本的產生。")
    elif not args.no_gmat and not args.no_fixed_script:
        clean_dc = bool(
            gmat_result and gmat_result["intercept_success"]
            and gmat_result["targeter_converged"] and gmat_result["final_burn_legal"]
        )
        final_burn_vnb = None
        if clean_dc:
            fixed_script_source = "gmat_dc"
            final_burn_vnb = gmat_result["final_burn_vnb"]
            log.info("🔒 一般版本 (GMAT DC) 驗證乾淨通過，用 GMAT 收斂後的值產生固定燃燒版本...")
        elif mission_info["dc_converged"]:
            fixed_script_source = "python_fallback"
            final_burn_vnb = tuple(burns[-1])
            reason = "GMAT 呼叫失敗/找不到 GmatConsole" if gmat_result is None else (
                "Targeter 未收斂" if not gmat_result["targeter_converged"] else
                "命中失敗 (Δr > 5km)" if not gmat_result["intercept_success"] else
                "最後一棒超過 Δv 上限"
            )
            # 為什麼要 fallback（DC 的 Vary 邊界搆不到需求量級等）寫在上面這段區塊註解裡。
            log.info(f"⚠️ 一般版本 (GMAT DC) 沒有乾淨通過（{reason}），改用 Python 自算的燃燒值"
                     f"產生固定燃燒版本...")
        else:
            log.warning("⚠️ 一般版本沒有通過，Python 自己的模型也沒收斂到瞄準點——這組解本身"
                        "沒有可信的燃燒值可以拿來當 fallback，先處理好再重跑。")

        if final_burn_vnb is not None:
            fixed_path = script_generator(
                config["orbit_A"]["SMA"], config["orbit_A"]["ECC"], config["orbit_A"]["INC"],
                config["orbit_A"]["RAAN"], config["orbit_A"]["AOP"], config["orbit_A"]["TA"],
                config["orbit_B"]["SMA"], config["orbit_B"]["ECC"], config["orbit_B"]["INC"],
                config["orbit_B"]["RAAN"], config["orbit_B"]["AOP"], config["orbit_B"]["TA"],
                burns, times, aim_point=mission_info["aim_point"],
                max_dv=optimizer.MAX_DV, gravity_degree=optimizer.GRAVITY_DEGREE,
                final_burn_fixed_vnb=final_burn_vnb,
                output_filename="output_submit.txt",
                model_scale=config.get("strategy", {}).get("GMAT_MODEL_SCALE", 0.5),
                output_dir=run_dir, **gmat_env,
            )
            started = time.perf_counter()
            fixed_script_result = run_gmat_verification(
                gmat_console_path, fixed_path, artifacts_dir=run_dir / "gmat_fixed"
            )
            manifest["timings_sec"]["gmat_fixed"] = time.perf_counter() - started
            if fixed_script_result:
                fmatch = "✅" if fixed_script_result["intercept_success"] else "❌"
                fdv_match = "✅" if fixed_script_result["final_burn_legal"] else "⚠️"
                src_label = "GMAT DC 收斂後的值" if fixed_script_source == "gmat_dc" \
                    else "Python 自己算的值 (DC fallback)"
                # 這是要繳交的那份，結果留一行事件級摘要（命中/合規/Δr）；細節(檔名/來源/Δr精確值)
                # 收進 DEBUG。
                submission_label = "建議繳交" if fixed_script_result.get("checks_passed", False) else "不可繳交"
                log.info(f"📤 固定燃燒版({submission_label})：命中 {fmatch} "
                         f"{'成功' if fixed_script_result['intercept_success'] else '失敗'}"
                         f"   最後一棒 {fdv_match} {'合規' if fixed_script_result['final_burn_legal'] else '超過每棒上限'}"
                         f"   (Δr {fixed_script_result['miss_km']*1000:,.0f}m, "
                         f"Δv {fixed_script_result['final_burn_dv_mps']:,.0f} m/s)")
                log.debug(f"  檔案：{fixed_path}　燃燒值來源：{src_label}")
                if not fixed_script_result.get("earth_safe", False):
                    log.warning("  🔴 固定燃燒版未通過獨立半徑檢查，官方會判失格，**不可繳交**。")
                elif fixed_script_result["intercept_success"] and fixed_script_result["final_burn_legal"]:
                    log.info("  👉 命中且合規，可以直接繳交。")
                elif fixed_script_result["intercept_success"]:
                    log.warning("  🔴 命中但最後一棒超過每棒上限：排位賽單棒超標直接失格，不可繳交。"
                                "先用 feasibility.py / sweep_burns.py 找合法解。")
                else:
                    log.warning("  ⚠️ 沒有命中：DC 來源不該發生；Python fallback 代表這組解站不住腳，不建議採用。")
            else:
                log.warning("  ⚠️ 固定版本沒有跑成功 (GMAT 呼叫失敗)，半徑未驗證，不可繳交。")

    # 4. 附加寫入執行紀錄，方便之後比較不同設定/軌道跑出來的分數
    append_run_history(config, mission_info, time.perf_counter() - start_time,
                        gmat_result=gmat_result, fixed_script_result=fixed_script_result,
                        fixed_script_source=fixed_script_source,
                        path=str(run_dir / "run_history.jsonl"))
    manifest["verification"] = {"dc": gmat_result, "fixed": fixed_script_result,
                                "fixed_source": fixed_script_source}
    if not args.no_gmat:
        manifest["last_stage"] = "verify"
        manifest["verification_status"] = (
            "completed" if gmat_result is not None and
            (args.no_fixed_script or not earth_safe or disqualified or fixed_script_result is not None)
            else "failed")


def run_retarget_stage(config, burns, times, mission_info, optimizer, *, args, run_dir,
                       gmat_console_path, manifest, local_config):
    """全攝動 B 平面重瞄準（2026-10-19，docs/research/PERTURBATION_GAP_20261019.md §4–5）。

    已保存的拆棒後方案 → GMAT 排位賽全攝動下 DC 改一棒（只消垂直於相對速度的兩個分量）→
    重新判定命中、Earth-safe、T_max、單棒/總 Δv 失格與機動間隔 → 通過才產生全攝動固定燃燒
    繳交腳本並再用 GMAT 驗一次。任何一步不過：保留原方案（原執行目錄一個檔都不動），本次目錄
    只留診斷檔與 retarget.json，終端機大聲警告。

    太空船參數與曆元取存檔 config 的 strategy.GMAT_*；有給 --config 時，那份設定 strategy 裡的
    GMAT_SPACECRAFT / GMAT_SPACECRAFT_A / GMAT_EPOCH / GMAT_EPOCH_FORMAT 會蓋過存檔（主辦單位
    開賽才公布這些值，那時方案通常已經解好了）。這些只影響 GMAT 端，不影響 Python 物理。"""
    started = time.perf_counter()
    cfg = copy.deepcopy(config)
    overrides = {k: v for k, v in (local_config.get("strategy") or {}).items()
                 if k in GMAT_ENV_KEYS and k != "FORCE_MODEL"}
    if overrides:
        cfg.setdefault("strategy", {}).update(copy.deepcopy(overrides))
        log.info(f"🛠️ 用 --config 的 GMAT 設定蓋過存檔：{', '.join(sorted(overrides))}")
    env = resolve_gmat_env(cfg, force_model="ranking_full")
    n = len(burns)
    idx = args.retarget_burn % n if -n <= args.retarget_burn < n else args.retarget_burn
    log.info(f"\n🎯 全攝動 B 平面重瞄準：改第 {idx} 棒（共 {n} 棒，0 起算）。曆元 {env['epoch_format']} "
             f"{env['epoch']}；B 質量 {env['sc_B']['DRY_MASS_KG']:g} kg、Cd {env['sc_B']['CD']:g}、"
             f"Cr {env['sc_B']['CR']:g}、阻力面積 {env['sc_B']['DRAG_AREA_M2']:g} m²、"
             f"SRP 面積 {env['sc_B']['SRP_AREA_M2']:g} m²")
    res = retarget_full_perturbation(
        config=cfg, burns=[list(b) for b in burns], times=list(times), idx=args.retarget_burn,
        env=env, console=gmat_console_path, folder=run_dir / "gmat_retarget",
        max_dv_mps=optimizer.MAX_DV * 1000.0, min_interval_sec=optimizer.MIN_COAST_TIME,
        max_total_dv_mps=optimizer.MAX_TOTAL_DV_MPS, t_max_sec=optimizer.T_max,
        min_radius_km=optimizer.MIN_PERIAPSIS, score_fn=optimizer.legality_fields,
        gravity_degree=optimizer.GRAVITY_DEGREE)
    manifest["timings_sec"]["retarget"] = time.perf_counter() - started

    orig = res["original"]
    rep = orig.get("replay", {})
    lines = [f"── 全攝動重瞄準 {'─' * 40}"]
    if "d_min_km" in rep:
        ol = orig["legality"]
        lines.append(f"  原方案（全攝動重播）  d_min {rep['d_min_km'] * 1000:>12,.1f} m   "
                     f"總Δv {ol['total_dv_mps']:>9,.2f} m/s   T {rep['t_plan_sec']:>10,.1f} s   "
                     f"官方分數估計 {ol['official_score'] if ol['official_score'] is not None else '失格'}")
    if "retargeted" in res:
        rt = res["retargeted"]
        rl, bc = rt["legality"], rt["burn_change"]
        lines.append(f"  重瞄準後              d_min {rt['d_min_km'] * 1000:>12,.1f} m   "
                     f"總Δv {rl['total_dv_mps']:>9,.2f} m/s   T {rt['t_team_sec']:>10,.1f} s   "
                     f"官方分數估計 {rl['official_score'] if rl['official_score'] is not None else '失格'}")
        lines.append(f"  第 {res['retarget_idx']} 棒 {bc['old_mps']:,.3f} → {bc['new_mps']:,.3f} m/s"
                     f"（向量修正 {bc['vector_change_mps']:,.3f} m/s，總 Δv {bc['total_dv_change_mps']:+,.3f} m/s）；"
                     f"DC {res['dc'].get('iterations')} 次迭代；最近點時刻比原預定 "
                     f"{rt['t_team_sec'] - rep['t_plan_sec']:+,.2f} s")
        if rl["penalty_count"]:
            lines.append(f"  ⚠️ 機動間隔違規 {rl['penalty_count']} 次（每次 −10 分；重瞄準不改點火時刻，原方案就有）")
    log.info("\n".join(lines))

    fixed = None
    submit_path = None
    if res["accepted"]:
        rt = res["retargeted"]
        nb = [tuple(b) for b in rt["burns"]]
        submit_path = script_generator(
            cfg["orbit_A"]["SMA"], cfg["orbit_A"]["ECC"], cfg["orbit_A"]["INC"],
            cfg["orbit_A"]["RAAN"], cfg["orbit_A"]["AOP"], cfg["orbit_A"]["TA"],
            cfg["orbit_B"]["SMA"], cfg["orbit_B"]["ECC"], cfg["orbit_B"]["INC"],
            cfg["orbit_B"]["RAAN"], cfg["orbit_B"]["AOP"], cfg["orbit_B"]["TA"],
            nb, rt["times"], aim_point=mission_info["aim_point"],
            max_dv=optimizer.MAX_DV, gravity_degree=optimizer.GRAVITY_DEGREE,
            final_burn_fixed_vnb=nb[-1], output_filename="output_submit.txt",
            model_scale=cfg.get("strategy", {}).get("GMAT_MODEL_SCALE", 0.5),
            output_dir=run_dir, **env)
        t0 = time.perf_counter()
        fixed = run_gmat_verification(gmat_console_path, submit_path,
                                      artifacts_dir=run_dir / "gmat_fixed")
        manifest["timings_sec"]["gmat_fixed"] = time.perf_counter() - t0
        if not (fixed and fixed.get("checks_passed", False)):
            res["accepted"] = False
            why = ("GMAT 執行失敗" if fixed is None else
                   f"命中 {fixed['intercept_success']}、末棒合規 {fixed['final_burn_legal']}、"
                   f"Δr {fixed['miss_km'] * 1000:,.1f} m")
            res["reasons"].append(f"全攝動固定燃燒繳交腳本驗證沒過（{why}）")
            rejected = Path(submit_path).with_name("output_submit_REJECTED.txt")
            Path(submit_path).replace(rejected)
            submit_path = str(rejected)
    res["fixed_script_verification"] = fixed

    write_json(run_dir / "retarget.json", {
        "schema_version": 1, "stage": "retarget", "provenance": provenance(),
        "saved_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "source": manifest.get("source"), "gmat_env": env, "gmat_console": gmat_console_path,
        "status": "accepted" if res["accepted"] else "rejected",
        "submission_script": submit_path if res["accepted"] else None,
        "result": res,
    })
    manifest["retarget"] = {"status": "accepted" if res["accepted"] else "rejected",
                            "retarget_idx": res["retarget_idx"], "reasons": res["reasons"],
                            "submission_script": submit_path if res["accepted"] else None}
    manifest["checks_passed"] = bool(res["accepted"])
    manifest["last_stage"] = "retarget"
    # GMAT 連原方案都重播不了（找不到 GmatConsole、腳本錯誤）算驗證失敗，不是「跑完但沒過」
    manifest["verification_status"] = "failed" if "error" in rep else "completed"

    if res["accepted"]:
        d_after = res["retargeted"]["d_min_km"]
        if d_after > 1.0:
            # B 平面是在預定時刻線性化：相對速度低（百 m/s 級）時最近點會偏離預定時刻、d_min 壓不到 0
            log.warning(f"⚠️ 重瞄準後 d_min {d_after:,.3f} km，離 5 km 只剩 {5.0 - d_after:,.3f} km 餘裕；"
                        "太空船參數不確定時可能不夠（研究報告 §3：B 長時間停在低軌時散布可達數 km）。")
        log.info(f"✅ 全攝動重瞄準通過：命中、Earth-safe、單棒/總 Δv 合法，固定燃燒版 GMAT 驗證 "
                 f"Δr {fixed['miss_km'] * 1000:,.1f} m。\n  👉 繳交腳本：{submit_path}"
                 f"\n  細節：{run_dir / 'retarget.json'}")
        return
    src = (manifest.get("source") or {}).get("path", "（原 mission.json）")
    hint = ""
    if "legality" in orig:
        head = orig["legality"]["headroom_mps"]
        order = sorted(range(len(head)), key=lambda i: -head[i])[:3]
        hint = ("\n  單棒餘裕最大的幾棒（可用 --retarget-burn N 改試）："
                + "、".join(f"第 {i} 棒 {head[i]:,.2f} m/s" for i in order))
    miss = rep.get("d_min_km")
    log.warning("\n" + "🔴" * 30
                + "\n  全攝動重瞄準沒有通過，**保留原方案，不產生新的繳交腳本**："
                + "".join(f"\n    • {r}" for r in res["reasons"])
                + (f"\n  原方案在全攝動下的 d_min = {miss:,.3f} km"
                   + ("（> 5 km，照原樣繳交會打偏！）" if miss > 5.0 else "（仍在 5 km 內）")
                   if miss is not None else "")
                + f"\n  原方案：{src}{hint}"
                + f"\n  診斷檔：{run_dir / 'gmat_retarget'}、{run_dir / 'retarget.json'}"
                + "\n" + "🔴" * 30)


if __name__ == '__main__':
    try:
        main()
    except NoLegalRouteError:
        sys.exit(EXIT_NO_LEGAL_ROUTE)   # 訊息與下一步建議 save_no_legal_route 已經印過
