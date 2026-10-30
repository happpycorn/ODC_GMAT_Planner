# 程式架構

## 檔案配置

各層 `__init__.py` 只提供套件說明，不重新匯出名稱。

```text
odc.py
odc/
  __init__.py
  cli.py
  paths.py
  runlog.py
  config/  # 讀取及驗證軌道、規則、搜尋策略與 GMAT 設定。
    __init__.py
    defaults.py
    gmat_env.py
    scoring_params.py
    split_defaults.py
    tmax.py
    validator.py
  gmat/  # 產生腳本、執行驗證及全攝動 B 平面重瞄準。
    __init__.py
    retarget.py
    script_generator.py
    verification.py
  physics/  # 提供座標轉換、軌道傳播、Lambert 與軌跡安全所需的數值運算。
    __init__.py
    core_math.py
    earth_gate.py
    propagator.py
    reference_propagators.py
  pipeline/  # 串接搜尋、合法化、存檔、輸出與報告階段。
    __init__.py
    artifacts.py
    checkpoints.py
    legalize.py
    primer_stage.py
    report.py
    solve.py
    stages.py
  scoring/  # 計算分數，判定單棒、機動間隔與總 Δv 的合法性。
    __init__.py
    scorer.py
  search/  # 產生種子、執行適應度搜尋、REVS 集成、primer 與 oracle。
    __init__.py
    fitness.py
    mission_eval.py
    optimizer.py
    oracle_twoburn.py
    oracle_worker.py
    primer.py
    ranking.py
    replay.py
    revs.py
    seeds.py
  split/  # 把超標脈衝拆成合法多棒方案並聯合精修。
    __init__.py
    burn_splitter.py
  tools/  # 提供情境檢查、批次實驗、回歸與本機成果管理工具。
    __init__.py
    check_problem.py
    check_scoring_params.py
    feasibility.py
    new_config.py
    output_inventory.py
    regression.py
    sweep_burns.py
    sweep_params.py
    tmax_from_boundary.py
scripts/research/
tests/
configs/shared/
configs/local/
```

`cli.py` 分派子命令，`paths.py` 提供根目錄與預設設定位置，`runlog.py` 統一日誌。

## 一次 solve 的呼叫順序

1. `odc.py` 呼叫 `odc.cli.main()`，翻譯位置參數後載入 `pipeline.stages.main()`。
2. `stages.main()` 解析選項、建立執行目錄；`_run_stages()` 使用 `config.defaults.load_or_create_config()` 讀取設定。
3. `solve.run_seed_portfolio()` 呼叫 `_solve_pipeline()`；啟用 oracle 時由 `_solve_with_oracle()` 建立 `search.oracle_worker.OracleJob` 背景行程。
4. `solve._search_stage()` 呼叫 `search.revs.run_study_over_revs()`；`MissionOptimizer` 使用 `seeds`、`fitness`、`physics`、`replay` 與 `mission_eval` 完成搜尋及重播。
5. `primer_stage.primer_guided_research()` 依既有條件診斷 primer，必要時插棒重搜。
6. `_solve_de_pipeline()` 保存 `checkpoints.save_winner_checkpoint()`，接 `legalize._legalize_stage()`／`split.burn_splitter.legalize_route()`，再執行合法備胎退路與候選比較。
7. `stages._run_stages()` 以 `artifacts.save_mission()` 保存最終 `mission.json`；`--stop-after solve` 在此停止。
8. `stages.run_output_stage()` 呼叫 `gmat.script_generator.script_generator()`，需要時接 `gmat.verification.run_gmat_verification()`，最後由 `pipeline.report` 保存紀錄。

## 版本驗證

`pipeline.artifacts.PHYSICS_FILES` 列出會影響存檔重用的 21 個來源與鎖檔。`save_mission()` 保存各檔案內容雜湊；`load_mission()` 在任一項變更時拒絕重用舊方案。
搬檔、拆模組或改動清單內的來源後，請重新求解，或用 `odc.py resume <winner.json>` 從拆前存檔重跑。winner 重播不檢查此程式版本雜湊。
`provenance()` 另外記錄腳本產生器、GMAT 環境、重瞄準與存檔模組的版本，供來源追溯。
