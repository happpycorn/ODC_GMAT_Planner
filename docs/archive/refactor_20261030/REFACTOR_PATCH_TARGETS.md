# 測試 patch 目標逐項對照

每列是原有測試的一個 patch 呼叫；名稱以匯入來源解析。實例方法及標準函式庫共享物件另外說明實際讀取位置。
函式內 from-import 的名稱是在執行該行時取值，因此 OracleJob 仍須 patch 來源模組；retarget 的 runner 則會引用被替換的函式。
資料狀態（ROOT、stderr、_report_level）不套用函式呼叫條件，均查核讀取位置。

## 階段 2

| 測試位置 | 舊目標 | 新目標 | 查核結果 |
|---|---|---|---|
| `tests/test_earth_safe_gate.py:59` | `main.subprocess.run` | `odc.pipeline.main.subprocess.run` | 原始碼呼叫：odc/pipeline/main.py:335 _run_gmat_verification: subprocess.run |
| `tests/test_earth_safe_gate.py:186` | `main.subprocess.run` | `odc.pipeline.main.subprocess.run` | 原始碼呼叫：odc/pipeline/main.py:335 _run_gmat_verification: subprocess.run |
| `tests/test_earth_safe_gate.py:206` | `main._run_gmat_verification` | `odc.pipeline.main._run_gmat_verification` | 原始碼呼叫：odc/pipeline/main.py:263 run_gmat_verification: _run_gmat_verification |
| `tests/test_force_model.py:365` | `src.retarget.replay` | `odc.gmat.retarget.replay` | retarget_full_perturbation 將此綁定放入 runner 字典，再呼叫 runner[replay]。 |
| `tests/test_force_model.py:365` | `src.retarget.run_bplane_dc` | `odc.gmat.retarget.run_bplane_dc` | retarget_full_perturbation 將此綁定放入 runner 字典，再呼叫 runner[dc]。 |
| `tests/test_force_model.py:366` | `main.run_gmat_verification` | `odc.pipeline.main.run_gmat_verification` | 原始碼呼叫：odc/pipeline/main.py:1293 _run_stages: run_gmat_verification |
| `tests/test_force_model.py:441` | `sys.stderr` | `sys.stderr` | 標準函式庫的輸出串流狀態，供 argparse／print 使用；非函式 mock。 |
| `tests/test_odc_cli.py:44` | `新增測試` | `odc.cli.importlib.import_module` | 原始碼呼叫：odc/cli.py:72 main: importlib.import_module |
| `tests/test_odc_cli.py:69` | `新增測試` | `odc.cli.importlib.import_module` | 原始碼呼叫：odc/cli.py:72 main: importlib.import_module |
| `tests/test_odc_cli.py:92` | `新增測試` | `odc.cli.Path.cwd` | 原始碼呼叫：odc/cli.py:62 main: Path.cwd |
| `tests/test_odc_cli.py:40` | `新增測試` | `odc.cli.importlib.import_module` | 原始碼呼叫：odc/cli.py:72 main: importlib.import_module |
| `tests/test_odc_cli.py:66` | `新增測試` | `odc.cli.importlib.import_module` | 原始碼呼叫：odc/cli.py:72 main: importlib.import_module |
| `tests/test_odc_cli.py:55` | `新增測試` | `odc.cli.importlib.import_module` | 原始碼呼叫：odc/cli.py:72 main: importlib.import_module |
| `tests/test_oracle_twoburn.py:134` | `src.config_validator.log.warning` | `odc.config.validator.log.warning` | 原始碼呼叫：odc/config/validator.py:322 _validate_strategy: log.warning |
| `tests/test_oracle_twoburn.py:153` | `src.oracle_worker.OracleJob` | `odc.search.oracle_worker.OracleJob` | _solve_with_oracle 在函式內 from-import 後呼叫 OracleJob；必須在匯入前 patch 來源模組的綁定。 |
| `tests/test_oracle_twoburn.py:154` | `main._search_stage` | `odc.pipeline.main._search_stage` | 原始碼呼叫：odc/pipeline/main.py:1056 _fallback_to_legal_backup: _search_stage |
| `tests/test_oracle_twoburn.py:155` | `main.save_winner_checkpoint` | `odc.pipeline.main.save_winner_checkpoint` | 原始碼呼叫：odc/pipeline/main.py:1105 _solve_de_pipeline: save_winner_checkpoint |
| `tests/test_oracle_twoburn.py:155` | `main.save_mission` | `odc.pipeline.main.save_mission` | 原始碼呼叫：odc/pipeline/main.py:1114 _solve_de_pipeline: save_mission |
| `tests/test_oracle_twoburn.py:156` | `main._legalize_stage` | `odc.pipeline.main._legalize_stage` | 原始碼呼叫：odc/pipeline/main.py:1058 _fallback_to_legal_backup: _legalize_stage |
| `tests/test_oracle_twoburn.py:157` | `main._fallback_to_legal_backup` | `odc.pipeline.main._fallback_to_legal_backup` | 原始碼呼叫：odc/pipeline/main.py:1113 _solve_de_pipeline: _fallback_to_legal_backup |
| `tests/test_oracle_twoburn.py:196` | `src.oracle_worker.OracleJob` | `odc.search.oracle_worker.OracleJob` | _solve_with_oracle 在函式內 from-import 後呼叫 OracleJob；必須在匯入前 patch 來源模組的綁定。 |
| `tests/test_oracle_twoburn.py:197` | `main._solve_de_pipeline` | `odc.pipeline.main._solve_de_pipeline` | 原始碼呼叫：odc/pipeline/main.py:1087 _solve_pipeline: _solve_de_pipeline |
| `tests/test_oracle_twoburn.py:198` | `main.save_winner_checkpoint` | `odc.pipeline.main.save_winner_checkpoint` | 原始碼呼叫：odc/pipeline/main.py:1105 _solve_de_pipeline: save_winner_checkpoint |
| `tests/test_oracle_twoburn.py:198` | `main.save_mission` | `odc.pipeline.main.save_mission` | 原始碼呼叫：odc/pipeline/main.py:1114 _solve_de_pipeline: save_mission |
| `tests/test_oracle_twoburn.py:239` | `src.optimizer._run_studies_unified` | `odc.search.optimizer._run_studies_unified` | 原始碼呼叫：odc/search/optimizer.py:2877 run_study_over_revs: _run_studies_unified |
| `tests/test_oracle_twoburn.py:218` | `opt._generate_seed_candidates` | `opt._generate_seed_candidates` | 實例方法；_optimize_burn_case 呼叫 self._generate_seed_candidates，實例上的替換仍優先於類別與 mixin。 |
| `tests/test_oracle_twoburn.py:219` | `src.optimizer.L_SHADE` | `odc.search.optimizer.L_SHADE` | 原始碼呼叫：odc/search/optimizer.py:1748 _optimize_burn_case: L_SHADE |
| `tests/test_oracle_twoburn.py:174` | `src.oracle_worker.OracleJob` | `odc.search.oracle_worker.OracleJob` | _solve_with_oracle 在函式內 from-import 後呼叫 OracleJob；必須在匯入前 patch 來源模組的綁定。 |
| `tests/test_oracle_twoburn.py:176` | `main._solve_de_pipeline` | `odc.pipeline.main._solve_de_pipeline` | 原始碼呼叫：odc/pipeline/main.py:1087 _solve_pipeline: _solve_de_pipeline |
| `tests/test_oracle_twoburn.py:177` | `main.save_winner_checkpoint` | `odc.pipeline.main.save_winner_checkpoint` | 原始碼呼叫：odc/pipeline/main.py:1105 _solve_de_pipeline: save_winner_checkpoint |
| `tests/test_oracle_twoburn.py:177` | `main.save_mission` | `odc.pipeline.main.save_mission` | 原始碼呼叫：odc/pipeline/main.py:1114 _solve_de_pipeline: save_mission |
| `tests/test_oracle_twoburn.py:146` | `src.oracle_worker.os.cpu_count` | `odc.search.oracle_worker.os.cpu_count` | 原始碼呼叫：odc/search/oracle_worker.py:25 oracle_core_budget: os.cpu_count |
| `tests/test_pipeline_stages.py:73` | `main.run_seed_portfolio` | `odc.pipeline.main.run_seed_portfolio` | 原始碼呼叫：odc/pipeline/main.py:1326 _run_stages: run_seed_portfolio |
| `tests/test_pipeline_stages.py:75` | `main.run_seed_portfolio` | `odc.pipeline.main.run_seed_portfolio` | 原始碼呼叫：odc/pipeline/main.py:1326 _run_stages: run_seed_portfolio |
| `tests/test_pipeline_stages.py:76` | `main._legalize_stage` | `odc.pipeline.main._legalize_stage` | 原始碼呼叫：odc/pipeline/main.py:1058 _fallback_to_legal_backup: _legalize_stage |
| `tests/test_pipeline_stages.py:77` | `main.primer_guided_research` | `odc.pipeline.main.primer_guided_research` | 原始碼呼叫：odc/pipeline/main.py:1021 _search_stage: primer_guided_research |
| `tests/test_pipeline_stages.py:78` | `main.load_or_create_config` | `odc.pipeline.main.load_or_create_config` | 原始碼呼叫：odc/pipeline/main.py:1283 _run_stages: load_or_create_config |
| `tests/test_pipeline_stages.py:79` | `main.run_gmat_verification` | `odc.pipeline.main.run_gmat_verification` | 原始碼呼叫：odc/pipeline/main.py:1293 _run_stages: run_gmat_verification |
| `tests/test_pipeline_stages.py:92` | `main.run_seed_portfolio` | `odc.pipeline.main.run_seed_portfolio` | 原始碼呼叫：odc/pipeline/main.py:1326 _run_stages: run_seed_portfolio |
| `tests/test_pipeline_stages.py:93` | `main._legalize_stage` | `odc.pipeline.main._legalize_stage` | 原始碼呼叫：odc/pipeline/main.py:1058 _fallback_to_legal_backup: _legalize_stage |
| `tests/test_pipeline_stages.py:94` | `main.script_generator` | `odc.pipeline.main.script_generator` | 原始碼呼叫：odc/pipeline/main.py:1409 run_output_stage: script_generator |
| `tests/test_pipeline_stages.py:109` | `main.run_study_over_revs` | `odc.pipeline.main.run_study_over_revs` | 原始碼呼叫：odc/pipeline/main.py:1016 _search_stage: run_study_over_revs |
| `tests/test_pipeline_stages.py:110` | `main.primer_guided_research` | `odc.pipeline.main.primer_guided_research` | 原始碼呼叫：odc/pipeline/main.py:1021 _search_stage: primer_guided_research |
| `tests/test_pipeline_stages.py:111` | `main._legalize_stage` | `odc.pipeline.main._legalize_stage` | 原始碼呼叫：odc/pipeline/main.py:1058 _fallback_to_legal_backup: _legalize_stage |
| `tests/test_pipeline_stages.py:142` | `main.subprocess.run` | `odc.pipeline.main.subprocess.run` | 原始碼呼叫：odc/pipeline/main.py:335 _run_gmat_verification: subprocess.run |
| `tests/test_pipeline_stages.py:154` | `main.subprocess.run` | `odc.pipeline.main.subprocess.run` | 原始碼呼叫：odc/pipeline/main.py:335 _run_gmat_verification: subprocess.run |
| `tests/test_pipeline_stages.py:155` | `main.run_seed_portfolio` | `odc.pipeline.main.run_seed_portfolio` | 原始碼呼叫：odc/pipeline/main.py:1326 _run_stages: run_seed_portfolio |
| `tests/test_pipeline_stages.py:156` | `main._legalize_stage` | `odc.pipeline.main._legalize_stage` | 原始碼呼叫：odc/pipeline/main.py:1058 _fallback_to_legal_backup: _legalize_stage |
| `tests/test_pipeline_stages.py:157` | `main.script_generator` | `odc.pipeline.main.script_generator` | 原始碼呼叫：odc/pipeline/main.py:1409 run_output_stage: script_generator |
| `tests/test_pipeline_stages.py:167` | `main.subprocess.run` | `odc.pipeline.main.subprocess.run` | 原始碼呼叫：odc/pipeline/main.py:335 _run_gmat_verification: subprocess.run |
| `tests/test_pipeline_stages.py:176` | `main.subprocess.run` | `odc.pipeline.main.subprocess.run` | 原始碼呼叫：odc/pipeline/main.py:335 _run_gmat_verification: subprocess.run |
| `tests/test_pipeline_stages.py:198` | `main.subprocess.run` | `odc.pipeline.main.subprocess.run` | 原始碼呼叫：odc/pipeline/main.py:335 _run_gmat_verification: subprocess.run |
| `tests/test_pipeline_stages.py:188` | `main.subprocess.run` | `odc.pipeline.main.subprocess.run` | 原始碼呼叫：odc/pipeline/main.py:335 _run_gmat_verification: subprocess.run |
| `tests/test_primer_fast.py:115` | `main._primer_diagnose_winner` | `odc.pipeline.main._primer_diagnose_winner` | 原始碼呼叫：odc/pipeline/main.py:584 primer_guided_research: _primer_diagnose_winner |
| `tests/test_primer_fast.py:116` | `main.insert_node_seed` | `odc.pipeline.main.insert_node_seed` | 原始碼呼叫：odc/pipeline/main.py:609 primer_guided_research: insert_node_seed |
| `tests/test_primer_fast.py:117` | `main.MissionOptimizer` | `odc.pipeline.main.MissionOptimizer` | 原始碼呼叫：odc/pipeline/main.py:1135 _solve_with_oracle: MissionOptimizer |
| `tests/test_primer_fast.py:118` | `main.run_study_over_revs` | `odc.pipeline.main.run_study_over_revs` | 原始碼呼叫：odc/pipeline/main.py:1016 _search_stage: run_study_over_revs |
| `tests/test_primer_fast.py:119` | `main.log.info` | `odc.pipeline.main.log.info` | 原始碼呼叫：odc/pipeline/main.py:1142 _solve_with_oracle: log.info |
| `tests/test_primer_fast.py:185` | `src.optimizer.time` | `odc.search.optimizer.time` | 原始碼呼叫：odc/search/optimizer.py:1747 _optimize_burn_case: time.monotonic |
| `tests/test_primer_fast.py:186` | `src.optimizer.fast_fitness_evaluator` | `odc.search.optimizer.fast_fitness_evaluator` | 原始碼呼叫：odc/search/optimizer.py:1706 _optimize_burn_case: fast_fitness_evaluator |
| `tests/test_primer_fast.py:187` | `opt._generate_seed_candidates` | `opt._generate_seed_candidates` | 實例方法；_optimize_burn_case 呼叫 self._generate_seed_candidates，實例上的替換仍優先於類別與 mixin。 |
| `tests/test_primer_fast.py:198` | `src.optimizer.fast_fitness_evaluator` | `odc.search.optimizer.fast_fitness_evaluator` | 原始碼呼叫：odc/search/optimizer.py:1706 _optimize_burn_case: fast_fitness_evaluator |
| `tests/test_primer_fast.py:217` | `src.optimizer.time` | `odc.search.optimizer.time` | 原始碼呼叫：odc/search/optimizer.py:1747 _optimize_burn_case: time.monotonic |
| `tests/test_primer_fast.py:218` | `src.optimizer.fast_fitness_evaluator` | `odc.search.optimizer.fast_fitness_evaluator` | 原始碼呼叫：odc/search/optimizer.py:1706 _optimize_burn_case: fast_fitness_evaluator |
| `tests/test_primer_fast.py:246` | `opt._optimize_burn_case` | `opt._optimize_burn_case` | run_study 將實例的 _optimize_burn_case 傳給 executor.submit；替換的是送入執行器的 bound method。 |
| `tests/test_primer_fast.py:247` | `opt._pick_best_case` | `opt._pick_best_case` | 實例方法；run_study 呼叫 self._pick_best_case。 |
| `tests/test_primer_fast.py:248` | `opt._replay_mission` | `opt._replay_mission` | 實例方法；refine_trajectory／save_no_legal_route 呼叫實例的 _replay_mission。 |
| `tests/test_primer_fast.py:249` | `opt.refine_trajectory` | `opt.refine_trajectory` | 實例方法；run_study／搜尋收尾呼叫實例的 refine_trajectory。 |
| `tests/test_primer_fast.py:166` | `main._primer_diagnose_winner` | `odc.pipeline.main._primer_diagnose_winner` | 原始碼呼叫：odc/pipeline/main.py:584 primer_guided_research: _primer_diagnose_winner |
| `tests/test_primer_fast.py:168` | `main.run_study_over_revs` | `odc.pipeline.main.run_study_over_revs` | 原始碼呼叫：odc/pipeline/main.py:1016 _search_stage: run_study_over_revs |
| `tests/test_primer_fast.py:236` | `src.optimizer.MissionOptimizer` | `odc.search.optimizer.MissionOptimizer` | 原始碼呼叫：odc/search/optimizer.py:2861 run_study_over_revs: MissionOptimizer |
| `tests/test_primer_fast.py:237` | `src.optimizer.time` | `odc.search.optimizer.time` | 原始碼呼叫：odc/search/optimizer.py:1747 _optimize_burn_case: time.monotonic |
| `tests/test_primer_fast.py:82` | `main._primer_diagnose_winner` | `odc.pipeline.main._primer_diagnose_winner` | 原始碼呼叫：odc/pipeline/main.py:584 primer_guided_research: _primer_diagnose_winner |
| `tests/test_primer_fast.py:83` | `main.insert_node_seed` | `odc.pipeline.main.insert_node_seed` | 原始碼呼叫：odc/pipeline/main.py:609 primer_guided_research: insert_node_seed |
| `tests/test_primer_fast.py:84` | `main.MissionOptimizer` | `odc.pipeline.main.MissionOptimizer` | 原始碼呼叫：odc/pipeline/main.py:1135 _solve_with_oracle: MissionOptimizer |
| `tests/test_primer_fast.py:85` | `main.run_study_over_revs` | `odc.pipeline.main.run_study_over_revs` | 原始碼呼叫：odc/pipeline/main.py:1016 _search_stage: run_study_over_revs |
| `tests/test_ranking_penalty_v2.py:268` | `main.run_seed_portfolio` | `odc.pipeline.main.run_seed_portfolio` | 原始碼呼叫：odc/pipeline/main.py:1326 _run_stages: run_seed_portfolio |
| `tests/test_ranking_penalty_v2.py:283` | `main.run_seed_portfolio` | `odc.pipeline.main.run_seed_portfolio` | 原始碼呼叫：odc/pipeline/main.py:1326 _run_stages: run_seed_portfolio |
| `tests/test_ranking_rules.py:151` | `pre._report_level` | `pre._report_level` | optimizer 實例的日誌層級狀態，由 log.log 讀取；非函式 mock。 |
| `tests/test_ranking_rules.py:156` | `wide._report_level` | `wide._report_level` | optimizer 實例的日誌層級狀態，由 log.log 讀取；非函式 mock。 |
| `tests/test_ranking_rules.py:174` | `main.log.warning` | `odc.pipeline.main.log.warning` | 原始碼呼叫：odc/pipeline/main.py:1051 _fallback_to_legal_backup: log.warning |
| `tests/test_ranking_rules.py:175` | `main.log.info` | `odc.pipeline.main.log.info` | 原始碼呼叫：odc/pipeline/main.py:1142 _solve_with_oracle: log.info |
| `tests/test_search_coast_rtol.py:84` | `src.optimizer.L_SHADE` | `odc.search.optimizer.L_SHADE` | 原始碼呼叫：odc/search/optimizer.py:1748 _optimize_burn_case: L_SHADE |
| `tests/test_search_coast_rtol.py:84` | `src.optimizer.fast_fitness_evaluator` | `odc.search.optimizer.fast_fitness_evaluator` | 原始碼呼叫：odc/search/optimizer.py:1706 _optimize_burn_case: fast_fitness_evaluator |
| `tests/test_search_coast_rtol.py:85` | `src.optimizer.minimize` | `odc.search.optimizer.minimize` | 原始碼呼叫：odc/search/optimizer.py:1579 _generate_nlp_refined_seed_candidates: minimize |
| `tests/test_search_coast_rtol.py:86` | `opt._generate_seed_candidates` | `opt._generate_seed_candidates` | 實例方法；_optimize_burn_case 呼叫 self._generate_seed_candidates，實例上的替換仍優先於類別與 mixin。 |
| `tests/test_split_aware_terminal.py:120` | `opt.mission_metrics` | `opt.mission_metrics` | 實例方法；搜尋候選評估呼叫 self.mission_metrics。 |
| `tests/test_split_aware_terminal.py:188` | `main._search_stage` | `odc.pipeline.main._search_stage` | 原始碼呼叫：odc/pipeline/main.py:1056 _fallback_to_legal_backup: _search_stage |
| `tests/test_split_aware_terminal.py:189` | `main._legalize_stage` | `odc.pipeline.main._legalize_stage` | 原始碼呼叫：odc/pipeline/main.py:1058 _fallback_to_legal_backup: _legalize_stage |
| `tests/test_split_defaults.py:23` | `os.cpu_count` | `os.cpu_count` | legalize.split_options 呼叫 os.cpu_count；各模組持有同一個 os 模組物件，此 patch 會改到實際呼叫的屬性。 |
| `tests/test_split_defaults.py:48` | `os.cpu_count` | `os.cpu_count` | legalize.split_options 呼叫 os.cpu_count；各模組持有同一個 os 模組物件，此 patch 會改到實際呼叫的屬性。 |
| `tests/test_split_defaults.py:62` | `os.cpu_count` | `os.cpu_count` | legalize.split_options 呼叫 os.cpu_count；各模組持有同一個 os 模組物件，此 patch 會改到實際呼叫的屬性。 |
| `tests/test_split_defaults.py:71` | `main.threadpool_limits` | `odc.pipeline.main.threadpool_limits` | 原始碼呼叫：odc/pipeline/main.py:650 _primer_fast_research: threadpool_limits |
| `tests/test_split_defaults.py:72` | `main.legalize_violating_winner` | `odc.pipeline.main.legalize_violating_winner` | 原始碼呼叫：odc/pipeline/main.py:925 _legalize_stage: legalize_violating_winner |
| `tests/test_split_leading.py:99` | `main.legalize_route` | `odc.pipeline.main.legalize_route` | 原始碼呼叫：odc/pipeline/main.py:787 legalize_violating_winner: legalize_route |
| `tests/test_split_leading.py:113` | `main.presplit_leading` | `odc.pipeline.main.presplit_leading` | 原始碼呼叫：odc/pipeline/main.py:771 legalize_violating_winner: presplit_leading |
| `tests/test_split_leading.py:141` | `main.legalize_route` | `odc.pipeline.main.legalize_route` | 原始碼呼叫：odc/pipeline/main.py:787 legalize_violating_winner: legalize_route |
| `tests/test_split_leading.py:146` | `main.legalize_route` | `odc.pipeline.main.legalize_route` | 原始碼呼叫：odc/pipeline/main.py:787 legalize_violating_winner: legalize_route |
| `tests/test_split_leading.py:235` | `main.legalize_violating_winner` | `odc.pipeline.main.legalize_violating_winner` | 原始碼呼叫：odc/pipeline/main.py:925 _legalize_stage: legalize_violating_winner |
| `tests/test_split_leading.py:205` | `main._primer_diagnose_winner` | `odc.pipeline.main._primer_diagnose_winner` | 原始碼呼叫：odc/pipeline/main.py:584 primer_guided_research: _primer_diagnose_winner |
| `tests/test_split_leading.py:206` | `main.insert_node_seed` | `odc.pipeline.main.insert_node_seed` | 原始碼呼叫：odc/pipeline/main.py:609 primer_guided_research: insert_node_seed |
| `tests/test_split_leading.py:207` | `main.MissionOptimizer` | `odc.pipeline.main.MissionOptimizer` | 原始碼呼叫：odc/pipeline/main.py:1135 _solve_with_oracle: MissionOptimizer |
| `tests/test_split_leading.py:208` | `main.run_study_over_revs` | `odc.pipeline.main.run_study_over_revs` | 原始碼呼叫：odc/pipeline/main.py:1016 _search_stage: run_study_over_revs |
| `tests/test_split_leading.py:209` | `main.legalize_violating_winner` | `odc.pipeline.main.legalize_violating_winner` | 原始碼呼叫：odc/pipeline/main.py:925 _legalize_stage: legalize_violating_winner |
| `tests/test_split_leading.py:160` | `opt._replay_mission` | `opt._replay_mission` | 實例方法；refine_trajectory／save_no_legal_route 呼叫實例的 _replay_mission。 |
| `tests/test_split_leading.py:161` | `main.log.error` | `odc.pipeline.main.log.error` | 原始碼呼叫：odc/pipeline/main.py:1239 run_seed_portfolio: log.error |
| `tests/test_split_stm.py:126` | `src.burn_splitter.joint_nlp_split` | `odc.split.burn_splitter.joint_nlp_split` | 原始碼呼叫：odc/split/burn_splitter.py:876 prune_reopt: joint_nlp_split |
| `tests/test_split_stm.py:207` | `src.burn_splitter.FDPool.jacobian` | `odc.split.burn_splitter.FDPool.jacobian` | 原始碼呼叫：odc/split/burn_splitter.py:599 jac_all: fd_map.jacobian |
| `tests/test_sweep_params.py:189` | `sweep_params._run_sweep` | `odc.tools.sweep_params._run_sweep` | 原始碼呼叫：odc/tools/sweep_params.py:361 run_sweep: _run_sweep |
| `tests/test_sweep_params.py:164` | `sweep_params.subprocess.Popen` | `odc.tools.sweep_params.subprocess.Popen` | 原始碼呼叫：odc/tools/sweep_params.py:287 start_job: subprocess.Popen |
| `tests/test_tiebreak.py:135` | `src.optimizer.log.warning` | `odc.search.optimizer.log.warning` | 原始碼呼叫：odc/search/optimizer.py:1867 preflight_report: log.warning |
| `tests/test_tiebreak.py:145` | `src.optimizer.log.warning` | `odc.search.optimizer.log.warning` | 原始碼呼叫：odc/search/optimizer.py:1867 preflight_report: log.warning |

共 112 項；92 項直接找到函式內呼叫，其餘依上列實例方法、間接分派或資料讀取位置核對。

## 階段 4

| 測試位置 | 舊目標 | 新目標 | 查核結果 |
|---|---|---|---|
| `tests/test_earth_safe_gate.py:61` | `odc.pipeline.main.subprocess.run` | `odc.gmat.verification.subprocess.run` | 原始碼呼叫：odc/gmat/verification.py:115 _run_gmat_verification: subprocess.run |
| `tests/test_earth_safe_gate.py:188` | `odc.pipeline.main.subprocess.run` | `odc.gmat.verification.subprocess.run` | 原始碼呼叫：odc/gmat/verification.py:115 _run_gmat_verification: subprocess.run |
| `tests/test_earth_safe_gate.py:208` | `odc.pipeline.main._run_gmat_verification` | `odc.gmat.verification._run_gmat_verification` | 原始碼呼叫：odc/gmat/verification.py:43 run_gmat_verification: _run_gmat_verification |
| `tests/test_force_model.py:367` | `odc.gmat.retarget.replay` | `odc.gmat.retarget.replay` | retarget_full_perturbation 將此綁定放入 runner 字典，再呼叫 runner[replay]。 |
| `tests/test_force_model.py:367` | `odc.gmat.retarget.run_bplane_dc` | `odc.gmat.retarget.run_bplane_dc` | retarget_full_perturbation 將此綁定放入 runner 字典，再呼叫 runner[dc]。 |
| `tests/test_force_model.py:368` | `odc.pipeline.main.run_gmat_verification` | `odc.pipeline.stages.run_gmat_verification` | 原始碼呼叫：odc/pipeline/stages.py:169 _run_stages: run_gmat_verification |
| `tests/test_force_model.py:443` | `sys.stderr` | `sys.stderr` | 標準函式庫的輸出串流狀態，供 argparse／print 使用；非函式 mock。 |
| `tests/test_odc_cli.py:48` | `odc.cli.importlib.import_module` | `odc.cli.importlib.import_module` | 原始碼呼叫：odc/cli.py:73 main: importlib.import_module |
| `tests/test_odc_cli.py:73` | `odc.cli.importlib.import_module` | `odc.cli.importlib.import_module` | 原始碼呼叫：odc/cli.py:73 main: importlib.import_module |
| `tests/test_odc_cli.py:96` | `odc.cli.Path.cwd` | `odc.cli.Path.cwd` | 原始碼呼叫：odc/cli.py:63 main: Path.cwd |
| `tests/test_odc_cli.py:44` | `odc.cli.importlib.import_module` | `odc.cli.importlib.import_module` | 原始碼呼叫：odc/cli.py:73 main: importlib.import_module |
| `tests/test_odc_cli.py:70` | `odc.cli.importlib.import_module` | `odc.cli.importlib.import_module` | 原始碼呼叫：odc/cli.py:73 main: importlib.import_module |
| `tests/test_odc_cli.py:118` | `新增測試` | `odc.tools.new_config.ROOT` | new_config.main 讀取的路徑常數；以暫存根目錄代換，非函式 mock。 |
| `tests/test_odc_cli.py:59` | `odc.cli.importlib.import_module` | `odc.cli.importlib.import_module` | 原始碼呼叫：odc/cli.py:73 main: importlib.import_module |
| `tests/test_oracle_twoburn.py:137` | `odc.config.validator.log.warning` | `odc.config.validator.log.warning` | 原始碼呼叫：odc/config/validator.py:322 _validate_strategy: log.warning |
| `tests/test_oracle_twoburn.py:156` | `odc.search.oracle_worker.OracleJob` | `odc.search.oracle_worker.OracleJob` | _solve_with_oracle 在函式內 from-import 後呼叫 OracleJob；必須在匯入前 patch 來源模組的綁定。 |
| `tests/test_oracle_twoburn.py:157` | `odc.pipeline.main._search_stage` | `odc.pipeline.solve._search_stage` | 原始碼呼叫：odc/pipeline/solve.py:56 _solve_de_pipeline: _search_stage |
| `tests/test_oracle_twoburn.py:158` | `odc.pipeline.main.save_winner_checkpoint` | `odc.pipeline.solve.save_winner_checkpoint` | 原始碼呼叫：odc/pipeline/solve.py:149 _solve_with_oracle: save_winner_checkpoint |
| `tests/test_oracle_twoburn.py:158` | `odc.pipeline.main.save_mission` | `odc.pipeline.solve.save_mission` | 原始碼呼叫：odc/pipeline/solve.py:151 _solve_with_oracle: save_mission |
| `tests/test_oracle_twoburn.py:159` | `odc.pipeline.main._legalize_stage` | `odc.pipeline.solve._legalize_stage` | 原始碼呼叫：odc/pipeline/solve.py:70 _solve_de_pipeline: _legalize_stage |
| `tests/test_oracle_twoburn.py:160` | `odc.pipeline.main._fallback_to_legal_backup` | `odc.pipeline.solve._fallback_to_legal_backup` | 原始碼呼叫：odc/pipeline/solve.py:71 _solve_de_pipeline: _fallback_to_legal_backup |
| `tests/test_oracle_twoburn.py:199` | `odc.search.oracle_worker.OracleJob` | `odc.search.oracle_worker.OracleJob` | _solve_with_oracle 在函式內 from-import 後呼叫 OracleJob；必須在匯入前 patch 來源模組的綁定。 |
| `tests/test_oracle_twoburn.py:200` | `odc.pipeline.main._solve_de_pipeline` | `odc.pipeline.solve._solve_de_pipeline` | 原始碼呼叫：odc/pipeline/solve.py:108 _solve_with_oracle: _solve_de_pipeline |
| `tests/test_oracle_twoburn.py:201` | `odc.pipeline.main.save_winner_checkpoint` | `odc.pipeline.solve.save_winner_checkpoint` | 原始碼呼叫：odc/pipeline/solve.py:149 _solve_with_oracle: save_winner_checkpoint |
| `tests/test_oracle_twoburn.py:201` | `odc.pipeline.main.save_mission` | `odc.pipeline.solve.save_mission` | 原始碼呼叫：odc/pipeline/solve.py:151 _solve_with_oracle: save_mission |
| `tests/test_oracle_twoburn.py:242` | `odc.search.optimizer._run_studies_unified` | `odc.search.optimizer._run_studies_unified` | 原始碼呼叫：odc/search/optimizer.py:2877 run_study_over_revs: _run_studies_unified |
| `tests/test_oracle_twoburn.py:221` | `opt._generate_seed_candidates` | `opt._generate_seed_candidates` | 實例方法；_optimize_burn_case 呼叫 self._generate_seed_candidates，實例上的替換仍優先於類別與 mixin。 |
| `tests/test_oracle_twoburn.py:222` | `odc.search.optimizer.L_SHADE` | `odc.search.optimizer.L_SHADE` | 原始碼呼叫：odc/search/optimizer.py:1748 _optimize_burn_case: L_SHADE |
| `tests/test_oracle_twoburn.py:177` | `odc.search.oracle_worker.OracleJob` | `odc.search.oracle_worker.OracleJob` | _solve_with_oracle 在函式內 from-import 後呼叫 OracleJob；必須在匯入前 patch 來源模組的綁定。 |
| `tests/test_oracle_twoburn.py:179` | `odc.pipeline.main._solve_de_pipeline` | `odc.pipeline.solve._solve_de_pipeline` | 原始碼呼叫：odc/pipeline/solve.py:108 _solve_with_oracle: _solve_de_pipeline |
| `tests/test_oracle_twoburn.py:180` | `odc.pipeline.main.save_winner_checkpoint` | `odc.pipeline.solve.save_winner_checkpoint` | 原始碼呼叫：odc/pipeline/solve.py:149 _solve_with_oracle: save_winner_checkpoint |
| `tests/test_oracle_twoburn.py:180` | `odc.pipeline.main.save_mission` | `odc.pipeline.solve.save_mission` | 原始碼呼叫：odc/pipeline/solve.py:151 _solve_with_oracle: save_mission |
| `tests/test_oracle_twoburn.py:149` | `odc.search.oracle_worker.os.cpu_count` | `odc.search.oracle_worker.os.cpu_count` | 原始碼呼叫：odc/search/oracle_worker.py:25 oracle_core_budget: os.cpu_count |
| `tests/test_pipeline_stages.py:77` | `odc.pipeline.main.run_seed_portfolio` | `odc.pipeline.stages.run_seed_portfolio` | 原始碼呼叫：odc/pipeline/stages.py:202 _run_stages: run_seed_portfolio |
| `tests/test_pipeline_stages.py:79` | `odc.pipeline.main.run_seed_portfolio` | `odc.pipeline.stages.run_seed_portfolio` | 原始碼呼叫：odc/pipeline/stages.py:202 _run_stages: run_seed_portfolio |
| `tests/test_pipeline_stages.py:80` | `odc.pipeline.main._legalize_stage` | `odc.pipeline.stages._legalize_stage` | 原始碼呼叫：odc/pipeline/stages.py:195 _run_stages: _legalize_stage |
| `tests/test_pipeline_stages.py:81` | `odc.pipeline.main.primer_guided_research` | `odc.pipeline.solve.primer_guided_research` | 原始碼呼叫：odc/pipeline/solve.py:29 _search_stage: primer_guided_research |
| `tests/test_pipeline_stages.py:82` | `odc.pipeline.main.load_or_create_config` | `odc.pipeline.stages.load_or_create_config` | 原始碼呼叫：odc/pipeline/stages.py:159 _run_stages: load_or_create_config |
| `tests/test_pipeline_stages.py:83` | `odc.pipeline.main.run_gmat_verification` | `odc.pipeline.stages.run_gmat_verification` | 原始碼呼叫：odc/pipeline/stages.py:169 _run_stages: run_gmat_verification |
| `tests/test_pipeline_stages.py:96` | `odc.pipeline.main.run_seed_portfolio` | `odc.pipeline.stages.run_seed_portfolio` | 原始碼呼叫：odc/pipeline/stages.py:202 _run_stages: run_seed_portfolio |
| `tests/test_pipeline_stages.py:97` | `odc.pipeline.main._legalize_stage` | `odc.pipeline.stages._legalize_stage` | 原始碼呼叫：odc/pipeline/stages.py:195 _run_stages: _legalize_stage |
| `tests/test_pipeline_stages.py:98` | `odc.pipeline.main.script_generator` | `odc.pipeline.stages.script_generator` | 原始碼呼叫：odc/pipeline/stages.py:285 run_output_stage: script_generator |
| `tests/test_pipeline_stages.py:113` | `odc.pipeline.main.run_study_over_revs` | `odc.pipeline.solve.run_study_over_revs` | 原始碼呼叫：odc/pipeline/solve.py:24 _search_stage: run_study_over_revs |
| `tests/test_pipeline_stages.py:114` | `odc.pipeline.main.primer_guided_research` | `odc.pipeline.solve.primer_guided_research` | 原始碼呼叫：odc/pipeline/solve.py:29 _search_stage: primer_guided_research |
| `tests/test_pipeline_stages.py:115` | `odc.pipeline.main._legalize_stage` | `odc.pipeline.solve._legalize_stage` | 原始碼呼叫：odc/pipeline/solve.py:70 _solve_de_pipeline: _legalize_stage |
| `tests/test_pipeline_stages.py:146` | `odc.pipeline.main.subprocess.run` | `odc.gmat.verification.subprocess.run` | 原始碼呼叫：odc/gmat/verification.py:115 _run_gmat_verification: subprocess.run |
| `tests/test_pipeline_stages.py:158` | `odc.pipeline.main.subprocess.run` | `odc.gmat.verification.subprocess.run` | 原始碼呼叫：odc/gmat/verification.py:115 _run_gmat_verification: subprocess.run |
| `tests/test_pipeline_stages.py:159` | `odc.pipeline.main.run_seed_portfolio` | `odc.pipeline.stages.run_seed_portfolio` | 原始碼呼叫：odc/pipeline/stages.py:202 _run_stages: run_seed_portfolio |
| `tests/test_pipeline_stages.py:160` | `odc.pipeline.main._legalize_stage` | `odc.pipeline.stages._legalize_stage` | 原始碼呼叫：odc/pipeline/stages.py:195 _run_stages: _legalize_stage |
| `tests/test_pipeline_stages.py:161` | `odc.pipeline.main.script_generator` | `odc.pipeline.stages.script_generator` | 原始碼呼叫：odc/pipeline/stages.py:285 run_output_stage: script_generator |
| `tests/test_pipeline_stages.py:171` | `odc.pipeline.main.subprocess.run` | `odc.gmat.verification.subprocess.run` | 原始碼呼叫：odc/gmat/verification.py:115 _run_gmat_verification: subprocess.run |
| `tests/test_pipeline_stages.py:180` | `odc.pipeline.main.subprocess.run` | `odc.gmat.verification.subprocess.run` | 原始碼呼叫：odc/gmat/verification.py:115 _run_gmat_verification: subprocess.run |
| `tests/test_pipeline_stages.py:202` | `odc.pipeline.main.subprocess.run` | `odc.gmat.verification.subprocess.run` | 原始碼呼叫：odc/gmat/verification.py:115 _run_gmat_verification: subprocess.run |
| `tests/test_pipeline_stages.py:192` | `odc.pipeline.main.subprocess.run` | `odc.gmat.verification.subprocess.run` | 原始碼呼叫：odc/gmat/verification.py:115 _run_gmat_verification: subprocess.run |
| `tests/test_primer_fast.py:116` | `odc.pipeline.main._primer_diagnose_winner` | `odc.pipeline.primer_stage._primer_diagnose_winner` | 原始碼呼叫：odc/pipeline/primer_stage.py:66 primer_guided_research: _primer_diagnose_winner |
| `tests/test_primer_fast.py:117` | `odc.pipeline.main.insert_node_seed` | `odc.pipeline.primer_stage.insert_node_seed` | 原始碼呼叫：odc/pipeline/primer_stage.py:91 primer_guided_research: insert_node_seed |
| `tests/test_primer_fast.py:118` | `odc.pipeline.main.MissionOptimizer` | `odc.pipeline.primer_stage.MissionOptimizer` | 原始碼呼叫：odc/pipeline/primer_stage.py:131 _primer_fast_research: MissionOptimizer |
| `tests/test_primer_fast.py:119` | `odc.pipeline.main.run_study_over_revs` | `odc.pipeline.primer_stage.run_study_over_revs` | 原始碼呼叫：odc/pipeline/primer_stage.py:155 _primer_fast_research: run_study_over_revs |
| `tests/test_primer_fast.py:120` | `odc.pipeline.main.log.info` | `odc.pipeline.primer_stage.log.info` | 原始碼呼叫：odc/pipeline/primer_stage.py:112 primer_guided_research: log.info |
| `tests/test_primer_fast.py:186` | `odc.search.optimizer.time` | `odc.search.optimizer.time` | 原始碼呼叫：odc/search/optimizer.py:1747 _optimize_burn_case: time.monotonic |
| `tests/test_primer_fast.py:187` | `odc.search.optimizer.fast_fitness_evaluator` | `odc.search.optimizer.fast_fitness_evaluator` | 原始碼呼叫：odc/search/optimizer.py:1706 _optimize_burn_case: fast_fitness_evaluator |
| `tests/test_primer_fast.py:188` | `opt._generate_seed_candidates` | `opt._generate_seed_candidates` | 實例方法；_optimize_burn_case 呼叫 self._generate_seed_candidates，實例上的替換仍優先於類別與 mixin。 |
| `tests/test_primer_fast.py:199` | `odc.search.optimizer.fast_fitness_evaluator` | `odc.search.optimizer.fast_fitness_evaluator` | 原始碼呼叫：odc/search/optimizer.py:1706 _optimize_burn_case: fast_fitness_evaluator |
| `tests/test_primer_fast.py:218` | `odc.search.optimizer.time` | `odc.search.optimizer.time` | 原始碼呼叫：odc/search/optimizer.py:1747 _optimize_burn_case: time.monotonic |
| `tests/test_primer_fast.py:219` | `odc.search.optimizer.fast_fitness_evaluator` | `odc.search.optimizer.fast_fitness_evaluator` | 原始碼呼叫：odc/search/optimizer.py:1706 _optimize_burn_case: fast_fitness_evaluator |
| `tests/test_primer_fast.py:247` | `opt._optimize_burn_case` | `opt._optimize_burn_case` | run_study 將實例的 _optimize_burn_case 傳給 executor.submit；替換的是送入執行器的 bound method。 |
| `tests/test_primer_fast.py:248` | `opt._pick_best_case` | `opt._pick_best_case` | 實例方法；run_study 呼叫 self._pick_best_case。 |
| `tests/test_primer_fast.py:249` | `opt._replay_mission` | `opt._replay_mission` | 實例方法；refine_trajectory／save_no_legal_route 呼叫實例的 _replay_mission。 |
| `tests/test_primer_fast.py:250` | `opt.refine_trajectory` | `opt.refine_trajectory` | 實例方法；run_study／搜尋收尾呼叫實例的 refine_trajectory。 |
| `tests/test_primer_fast.py:167` | `odc.pipeline.main._primer_diagnose_winner` | `odc.pipeline.primer_stage._primer_diagnose_winner` | 原始碼呼叫：odc/pipeline/primer_stage.py:66 primer_guided_research: _primer_diagnose_winner |
| `tests/test_primer_fast.py:169` | `odc.pipeline.main.run_study_over_revs` | `odc.pipeline.primer_stage.run_study_over_revs` | 原始碼呼叫：odc/pipeline/primer_stage.py:155 _primer_fast_research: run_study_over_revs |
| `tests/test_primer_fast.py:237` | `odc.search.optimizer.MissionOptimizer` | `odc.search.optimizer.MissionOptimizer` | 原始碼呼叫：odc/search/optimizer.py:2861 run_study_over_revs: MissionOptimizer |
| `tests/test_primer_fast.py:238` | `odc.search.optimizer.time` | `odc.search.optimizer.time` | 原始碼呼叫：odc/search/optimizer.py:1747 _optimize_burn_case: time.monotonic |
| `tests/test_primer_fast.py:83` | `odc.pipeline.main._primer_diagnose_winner` | `odc.pipeline.primer_stage._primer_diagnose_winner` | 原始碼呼叫：odc/pipeline/primer_stage.py:66 primer_guided_research: _primer_diagnose_winner |
| `tests/test_primer_fast.py:84` | `odc.pipeline.main.insert_node_seed` | `odc.pipeline.primer_stage.insert_node_seed` | 原始碼呼叫：odc/pipeline/primer_stage.py:91 primer_guided_research: insert_node_seed |
| `tests/test_primer_fast.py:85` | `odc.pipeline.main.MissionOptimizer` | `odc.pipeline.primer_stage.MissionOptimizer` | 原始碼呼叫：odc/pipeline/primer_stage.py:131 _primer_fast_research: MissionOptimizer |
| `tests/test_primer_fast.py:86` | `odc.pipeline.main.run_study_over_revs` | `odc.pipeline.primer_stage.run_study_over_revs` | 原始碼呼叫：odc/pipeline/primer_stage.py:155 _primer_fast_research: run_study_over_revs |
| `tests/test_ranking_penalty_v2.py:269` | `odc.pipeline.main.run_seed_portfolio` | `odc.pipeline.stages.run_seed_portfolio` | 原始碼呼叫：odc/pipeline/stages.py:202 _run_stages: run_seed_portfolio |
| `tests/test_ranking_penalty_v2.py:284` | `odc.pipeline.main.run_seed_portfolio` | `odc.pipeline.stages.run_seed_portfolio` | 原始碼呼叫：odc/pipeline/stages.py:202 _run_stages: run_seed_portfolio |
| `tests/test_ranking_rules.py:153` | `pre._report_level` | `pre._report_level` | optimizer 實例的日誌層級狀態，由 log.log 讀取；非函式 mock。 |
| `tests/test_ranking_rules.py:158` | `wide._report_level` | `wide._report_level` | optimizer 實例的日誌層級狀態，由 log.log 讀取；非函式 mock。 |
| `tests/test_ranking_rules.py:176` | `odc.pipeline.main.log.warning` | `odc.pipeline.report.log.warning` | 原始碼呼叫：odc/pipeline/report.py:148 print_score_breakdown: log.warning |
| `tests/test_ranking_rules.py:177` | `odc.pipeline.main.log.info` | `odc.pipeline.report.log.info` | 原始碼呼叫：odc/pipeline/report.py:143 print_score_breakdown: log.info |
| `tests/test_search_coast_rtol.py:84` | `odc.search.optimizer.L_SHADE` | `odc.search.optimizer.L_SHADE` | 原始碼呼叫：odc/search/optimizer.py:1748 _optimize_burn_case: L_SHADE |
| `tests/test_search_coast_rtol.py:84` | `odc.search.optimizer.fast_fitness_evaluator` | `odc.search.optimizer.fast_fitness_evaluator` | 原始碼呼叫：odc/search/optimizer.py:1706 _optimize_burn_case: fast_fitness_evaluator |
| `tests/test_search_coast_rtol.py:85` | `odc.search.optimizer.minimize` | `odc.search.optimizer.minimize` | 原始碼呼叫：odc/search/optimizer.py:1579 _generate_nlp_refined_seed_candidates: minimize |
| `tests/test_search_coast_rtol.py:86` | `opt._generate_seed_candidates` | `opt._generate_seed_candidates` | 實例方法；_optimize_burn_case 呼叫 self._generate_seed_candidates，實例上的替換仍優先於類別與 mixin。 |
| `tests/test_split_aware_terminal.py:121` | `opt.mission_metrics` | `opt.mission_metrics` | 實例方法；搜尋候選評估呼叫 self.mission_metrics。 |
| `tests/test_split_aware_terminal.py:189` | `odc.pipeline.main._search_stage` | `odc.pipeline.solve._search_stage` | 原始碼呼叫：odc/pipeline/solve.py:56 _solve_de_pipeline: _search_stage |
| `tests/test_split_aware_terminal.py:190` | `odc.pipeline.main._legalize_stage` | `odc.pipeline.legalize._legalize_stage` | 原始碼呼叫：odc/pipeline/legalize.py:244 _fallback_to_legal_backup: _legalize_stage |
| `tests/test_split_defaults.py:24` | `os.cpu_count` | `os.cpu_count` | legalize.split_options 呼叫 os.cpu_count；各模組持有同一個 os 模組物件，此 patch 會改到實際呼叫的屬性。 |
| `tests/test_split_defaults.py:49` | `os.cpu_count` | `os.cpu_count` | legalize.split_options 呼叫 os.cpu_count；各模組持有同一個 os 模組物件，此 patch 會改到實際呼叫的屬性。 |
| `tests/test_split_defaults.py:63` | `os.cpu_count` | `os.cpu_count` | legalize.split_options 呼叫 os.cpu_count；各模組持有同一個 os 模組物件，此 patch 會改到實際呼叫的屬性。 |
| `tests/test_split_defaults.py:72` | `odc.pipeline.main.threadpool_limits` | `odc.pipeline.legalize.threadpool_limits` | 原始碼呼叫：odc/pipeline/legalize.py:202 _legalize_stage: threadpool_limits |
| `tests/test_split_defaults.py:73` | `odc.pipeline.main.legalize_violating_winner` | `odc.pipeline.legalize.legalize_violating_winner` | 原始碼呼叫：odc/pipeline/legalize.py:203 _legalize_stage: legalize_violating_winner |
| `tests/test_split_leading.py:102` | `odc.pipeline.main.legalize_route` | `odc.pipeline.legalize.legalize_route` | 原始碼呼叫：odc/pipeline/legalize.py:108 legalize_violating_winner: legalize_route |
| `tests/test_split_leading.py:116` | `odc.pipeline.main.presplit_leading` | `odc.pipeline.legalize.presplit_leading` | 原始碼呼叫：odc/pipeline/legalize.py:92 legalize_violating_winner: presplit_leading |
| `tests/test_split_leading.py:144` | `odc.pipeline.main.legalize_route` | `odc.pipeline.legalize.legalize_route` | 原始碼呼叫：odc/pipeline/legalize.py:108 legalize_violating_winner: legalize_route |
| `tests/test_split_leading.py:149` | `odc.pipeline.main.legalize_route` | `odc.pipeline.legalize.legalize_route` | 原始碼呼叫：odc/pipeline/legalize.py:108 legalize_violating_winner: legalize_route |
| `tests/test_split_leading.py:238` | `odc.pipeline.main.legalize_violating_winner` | `odc.pipeline.legalize.legalize_violating_winner` | 原始碼呼叫：odc/pipeline/legalize.py:203 _legalize_stage: legalize_violating_winner |
| `tests/test_split_leading.py:208` | `odc.pipeline.main._primer_diagnose_winner` | `odc.pipeline.primer_stage._primer_diagnose_winner` | 原始碼呼叫：odc/pipeline/primer_stage.py:66 primer_guided_research: _primer_diagnose_winner |
| `tests/test_split_leading.py:209` | `odc.pipeline.main.insert_node_seed` | `odc.pipeline.primer_stage.insert_node_seed` | 原始碼呼叫：odc/pipeline/primer_stage.py:91 primer_guided_research: insert_node_seed |
| `tests/test_split_leading.py:210` | `odc.pipeline.main.MissionOptimizer` | `odc.pipeline.primer_stage.MissionOptimizer` | 原始碼呼叫：odc/pipeline/primer_stage.py:131 _primer_fast_research: MissionOptimizer |
| `tests/test_split_leading.py:211` | `odc.pipeline.main.run_study_over_revs` | `odc.pipeline.primer_stage.run_study_over_revs` | 原始碼呼叫：odc/pipeline/primer_stage.py:155 _primer_fast_research: run_study_over_revs |
| `tests/test_split_leading.py:212` | `odc.pipeline.main.legalize_violating_winner` | `odc.pipeline.legalize.legalize_violating_winner` | 原始碼呼叫：odc/pipeline/legalize.py:203 _legalize_stage: legalize_violating_winner |
| `tests/test_split_leading.py:163` | `opt._replay_mission` | `opt._replay_mission` | 實例方法；refine_trajectory／save_no_legal_route 呼叫實例的 _replay_mission。 |
| `tests/test_split_leading.py:164` | `odc.pipeline.main.log.error` | `odc.pipeline.checkpoints.log.error` | 原始碼呼叫：odc/pipeline/checkpoints.py:123 save_no_legal_route: log.error |
| `tests/test_split_stm.py:126` | `odc.split.burn_splitter.joint_nlp_split` | `odc.split.burn_splitter.joint_nlp_split` | 原始碼呼叫：odc/split/burn_splitter.py:876 prune_reopt: joint_nlp_split |
| `tests/test_split_stm.py:207` | `odc.split.burn_splitter.FDPool.jacobian` | `odc.split.burn_splitter.FDPool.jacobian` | 原始碼呼叫：odc/split/burn_splitter.py:599 jac_all: fd_map.jacobian |
| `tests/test_sweep_params.py:189` | `odc.tools.sweep_params._run_sweep` | `odc.tools.sweep_params._run_sweep` | 原始碼呼叫：odc/tools/sweep_params.py:361 run_sweep: _run_sweep |
| `tests/test_sweep_params.py:164` | `odc.tools.sweep_params.subprocess.Popen` | `odc.tools.sweep_params.subprocess.Popen` | 原始碼呼叫：odc/tools/sweep_params.py:287 start_job: subprocess.Popen |
| `tests/test_tiebreak.py:135` | `odc.search.optimizer.log.warning` | `odc.search.optimizer.log.warning` | 原始碼呼叫：odc/search/optimizer.py:1867 preflight_report: log.warning |
| `tests/test_tiebreak.py:145` | `odc.search.optimizer.log.warning` | `odc.search.optimizer.log.warning` | 原始碼呼叫：odc/search/optimizer.py:1867 preflight_report: log.warning |

共 113 項；92 項直接找到函式內呼叫，其餘依上列實例方法、間接分派或資料讀取位置核對。

## 階段 5

| 測試位置 | 舊目標 | 新目標 | 查核結果 |
|---|---|---|---|
| `tests/test_earth_safe_gate.py:62` | `odc.gmat.verification.subprocess.run` | `odc.gmat.verification.subprocess.run` | 原始碼呼叫：odc/gmat/verification.py:115 _run_gmat_verification: subprocess.run |
| `tests/test_earth_safe_gate.py:189` | `odc.gmat.verification.subprocess.run` | `odc.gmat.verification.subprocess.run` | 原始碼呼叫：odc/gmat/verification.py:115 _run_gmat_verification: subprocess.run |
| `tests/test_earth_safe_gate.py:209` | `odc.gmat.verification._run_gmat_verification` | `odc.gmat.verification._run_gmat_verification` | 原始碼呼叫：odc/gmat/verification.py:43 run_gmat_verification: _run_gmat_verification |
| `tests/test_force_model.py:367` | `odc.gmat.retarget.replay` | `odc.gmat.retarget.replay` | retarget_full_perturbation 將此綁定放入 runner 字典，再呼叫 runner[replay]。 |
| `tests/test_force_model.py:367` | `odc.gmat.retarget.run_bplane_dc` | `odc.gmat.retarget.run_bplane_dc` | retarget_full_perturbation 將此綁定放入 runner 字典，再呼叫 runner[dc]。 |
| `tests/test_force_model.py:368` | `odc.pipeline.stages.run_gmat_verification` | `odc.pipeline.stages.run_gmat_verification` | 原始碼呼叫：odc/pipeline/stages.py:170 _run_stages: run_gmat_verification |
| `tests/test_force_model.py:443` | `sys.stderr` | `sys.stderr` | 標準函式庫的輸出串流狀態，供 argparse／print 使用；非函式 mock。 |
| `tests/test_odc_cli.py:48` | `odc.cli.importlib.import_module` | `odc.cli.importlib.import_module` | 原始碼呼叫：odc/cli.py:73 main: importlib.import_module |
| `tests/test_odc_cli.py:73` | `odc.cli.importlib.import_module` | `odc.cli.importlib.import_module` | 原始碼呼叫：odc/cli.py:73 main: importlib.import_module |
| `tests/test_odc_cli.py:96` | `odc.cli.Path.cwd` | `odc.cli.Path.cwd` | 原始碼呼叫：odc/cli.py:63 main: Path.cwd |
| `tests/test_odc_cli.py:44` | `odc.cli.importlib.import_module` | `odc.cli.importlib.import_module` | 原始碼呼叫：odc/cli.py:73 main: importlib.import_module |
| `tests/test_odc_cli.py:70` | `odc.cli.importlib.import_module` | `odc.cli.importlib.import_module` | 原始碼呼叫：odc/cli.py:73 main: importlib.import_module |
| `tests/test_odc_cli.py:118` | `odc.tools.new_config.ROOT` | `odc.tools.new_config.ROOT` | new_config.main 讀取的路徑常數；以暫存根目錄代換，非函式 mock。 |
| `tests/test_odc_cli.py:59` | `odc.cli.importlib.import_module` | `odc.cli.importlib.import_module` | 原始碼呼叫：odc/cli.py:73 main: importlib.import_module |
| `tests/test_oracle_twoburn.py:138` | `odc.config.validator.log.warning` | `odc.config.validator.log.warning` | 原始碼呼叫：odc/config/validator.py:322 _validate_strategy: log.warning |
| `tests/test_oracle_twoburn.py:157` | `odc.search.oracle_worker.OracleJob` | `odc.search.oracle_worker.OracleJob` | _solve_with_oracle 在函式內 from-import 後呼叫 OracleJob；必須在匯入前 patch 來源模組的綁定。 |
| `tests/test_oracle_twoburn.py:158` | `odc.pipeline.solve._search_stage` | `odc.pipeline.solve._search_stage` | 原始碼呼叫：odc/pipeline/solve.py:57 _solve_de_pipeline: _search_stage |
| `tests/test_oracle_twoburn.py:159` | `odc.pipeline.solve.save_winner_checkpoint` | `odc.pipeline.solve.save_winner_checkpoint` | 原始碼呼叫：odc/pipeline/solve.py:150 _solve_with_oracle: save_winner_checkpoint |
| `tests/test_oracle_twoburn.py:159` | `odc.pipeline.solve.save_mission` | `odc.pipeline.solve.save_mission` | 原始碼呼叫：odc/pipeline/solve.py:152 _solve_with_oracle: save_mission |
| `tests/test_oracle_twoburn.py:160` | `odc.pipeline.solve._legalize_stage` | `odc.pipeline.solve._legalize_stage` | 原始碼呼叫：odc/pipeline/solve.py:71 _solve_de_pipeline: _legalize_stage |
| `tests/test_oracle_twoburn.py:161` | `odc.pipeline.solve._fallback_to_legal_backup` | `odc.pipeline.solve._fallback_to_legal_backup` | 原始碼呼叫：odc/pipeline/solve.py:72 _solve_de_pipeline: _fallback_to_legal_backup |
| `tests/test_oracle_twoburn.py:200` | `odc.search.oracle_worker.OracleJob` | `odc.search.oracle_worker.OracleJob` | _solve_with_oracle 在函式內 from-import 後呼叫 OracleJob；必須在匯入前 patch 來源模組的綁定。 |
| `tests/test_oracle_twoburn.py:201` | `odc.pipeline.solve._solve_de_pipeline` | `odc.pipeline.solve._solve_de_pipeline` | 原始碼呼叫：odc/pipeline/solve.py:109 _solve_with_oracle: _solve_de_pipeline |
| `tests/test_oracle_twoburn.py:202` | `odc.pipeline.solve.save_winner_checkpoint` | `odc.pipeline.solve.save_winner_checkpoint` | 原始碼呼叫：odc/pipeline/solve.py:150 _solve_with_oracle: save_winner_checkpoint |
| `tests/test_oracle_twoburn.py:202` | `odc.pipeline.solve.save_mission` | `odc.pipeline.solve.save_mission` | 原始碼呼叫：odc/pipeline/solve.py:152 _solve_with_oracle: save_mission |
| `tests/test_oracle_twoburn.py:243` | `odc.search.optimizer._run_studies_unified` | `odc.search.revs._run_studies_unified` | 原始碼呼叫：odc/search/revs.py:183 run_study_over_revs: _run_studies_unified |
| `tests/test_oracle_twoburn.py:222` | `opt._generate_seed_candidates` | `opt._generate_seed_candidates` | 實例方法；_optimize_burn_case 呼叫 self._generate_seed_candidates，實例上的替換仍優先於類別與 mixin。 |
| `tests/test_oracle_twoburn.py:223` | `odc.search.optimizer.L_SHADE` | `odc.search.optimizer.L_SHADE` | 原始碼呼叫：odc/search/optimizer.py:513 _optimize_burn_case: L_SHADE |
| `tests/test_oracle_twoburn.py:178` | `odc.search.oracle_worker.OracleJob` | `odc.search.oracle_worker.OracleJob` | _solve_with_oracle 在函式內 from-import 後呼叫 OracleJob；必須在匯入前 patch 來源模組的綁定。 |
| `tests/test_oracle_twoburn.py:180` | `odc.pipeline.solve._solve_de_pipeline` | `odc.pipeline.solve._solve_de_pipeline` | 原始碼呼叫：odc/pipeline/solve.py:109 _solve_with_oracle: _solve_de_pipeline |
| `tests/test_oracle_twoburn.py:181` | `odc.pipeline.solve.save_winner_checkpoint` | `odc.pipeline.solve.save_winner_checkpoint` | 原始碼呼叫：odc/pipeline/solve.py:150 _solve_with_oracle: save_winner_checkpoint |
| `tests/test_oracle_twoburn.py:181` | `odc.pipeline.solve.save_mission` | `odc.pipeline.solve.save_mission` | 原始碼呼叫：odc/pipeline/solve.py:152 _solve_with_oracle: save_mission |
| `tests/test_oracle_twoburn.py:150` | `odc.search.oracle_worker.os.cpu_count` | `odc.search.oracle_worker.os.cpu_count` | 原始碼呼叫：odc/search/oracle_worker.py:25 oracle_core_budget: os.cpu_count |
| `tests/test_pipeline_stages.py:77` | `odc.pipeline.stages.run_seed_portfolio` | `odc.pipeline.stages.run_seed_portfolio` | 原始碼呼叫：odc/pipeline/stages.py:203 _run_stages: run_seed_portfolio |
| `tests/test_pipeline_stages.py:79` | `odc.pipeline.stages.run_seed_portfolio` | `odc.pipeline.stages.run_seed_portfolio` | 原始碼呼叫：odc/pipeline/stages.py:203 _run_stages: run_seed_portfolio |
| `tests/test_pipeline_stages.py:80` | `odc.pipeline.stages._legalize_stage` | `odc.pipeline.stages._legalize_stage` | 原始碼呼叫：odc/pipeline/stages.py:196 _run_stages: _legalize_stage |
| `tests/test_pipeline_stages.py:81` | `odc.pipeline.solve.primer_guided_research` | `odc.pipeline.solve.primer_guided_research` | 原始碼呼叫：odc/pipeline/solve.py:30 _search_stage: primer_guided_research |
| `tests/test_pipeline_stages.py:82` | `odc.pipeline.stages.load_or_create_config` | `odc.pipeline.stages.load_or_create_config` | 原始碼呼叫：odc/pipeline/stages.py:160 _run_stages: load_or_create_config |
| `tests/test_pipeline_stages.py:83` | `odc.pipeline.stages.run_gmat_verification` | `odc.pipeline.stages.run_gmat_verification` | 原始碼呼叫：odc/pipeline/stages.py:170 _run_stages: run_gmat_verification |
| `tests/test_pipeline_stages.py:96` | `odc.pipeline.stages.run_seed_portfolio` | `odc.pipeline.stages.run_seed_portfolio` | 原始碼呼叫：odc/pipeline/stages.py:203 _run_stages: run_seed_portfolio |
| `tests/test_pipeline_stages.py:97` | `odc.pipeline.stages._legalize_stage` | `odc.pipeline.stages._legalize_stage` | 原始碼呼叫：odc/pipeline/stages.py:196 _run_stages: _legalize_stage |
| `tests/test_pipeline_stages.py:98` | `odc.pipeline.stages.script_generator` | `odc.pipeline.stages.script_generator` | 原始碼呼叫：odc/pipeline/stages.py:286 run_output_stage: script_generator |
| `tests/test_pipeline_stages.py:113` | `odc.pipeline.solve.run_study_over_revs` | `odc.pipeline.solve.run_study_over_revs` | 原始碼呼叫：odc/pipeline/solve.py:25 _search_stage: run_study_over_revs |
| `tests/test_pipeline_stages.py:114` | `odc.pipeline.solve.primer_guided_research` | `odc.pipeline.solve.primer_guided_research` | 原始碼呼叫：odc/pipeline/solve.py:30 _search_stage: primer_guided_research |
| `tests/test_pipeline_stages.py:115` | `odc.pipeline.solve._legalize_stage` | `odc.pipeline.solve._legalize_stage` | 原始碼呼叫：odc/pipeline/solve.py:71 _solve_de_pipeline: _legalize_stage |
| `tests/test_pipeline_stages.py:146` | `odc.gmat.verification.subprocess.run` | `odc.gmat.verification.subprocess.run` | 原始碼呼叫：odc/gmat/verification.py:115 _run_gmat_verification: subprocess.run |
| `tests/test_pipeline_stages.py:158` | `odc.gmat.verification.subprocess.run` | `odc.gmat.verification.subprocess.run` | 原始碼呼叫：odc/gmat/verification.py:115 _run_gmat_verification: subprocess.run |
| `tests/test_pipeline_stages.py:159` | `odc.pipeline.stages.run_seed_portfolio` | `odc.pipeline.stages.run_seed_portfolio` | 原始碼呼叫：odc/pipeline/stages.py:203 _run_stages: run_seed_portfolio |
| `tests/test_pipeline_stages.py:160` | `odc.pipeline.stages._legalize_stage` | `odc.pipeline.stages._legalize_stage` | 原始碼呼叫：odc/pipeline/stages.py:196 _run_stages: _legalize_stage |
| `tests/test_pipeline_stages.py:161` | `odc.pipeline.stages.script_generator` | `odc.pipeline.stages.script_generator` | 原始碼呼叫：odc/pipeline/stages.py:286 run_output_stage: script_generator |
| `tests/test_pipeline_stages.py:171` | `odc.gmat.verification.subprocess.run` | `odc.gmat.verification.subprocess.run` | 原始碼呼叫：odc/gmat/verification.py:115 _run_gmat_verification: subprocess.run |
| `tests/test_pipeline_stages.py:180` | `odc.gmat.verification.subprocess.run` | `odc.gmat.verification.subprocess.run` | 原始碼呼叫：odc/gmat/verification.py:115 _run_gmat_verification: subprocess.run |
| `tests/test_pipeline_stages.py:202` | `odc.gmat.verification.subprocess.run` | `odc.gmat.verification.subprocess.run` | 原始碼呼叫：odc/gmat/verification.py:115 _run_gmat_verification: subprocess.run |
| `tests/test_pipeline_stages.py:192` | `odc.gmat.verification.subprocess.run` | `odc.gmat.verification.subprocess.run` | 原始碼呼叫：odc/gmat/verification.py:115 _run_gmat_verification: subprocess.run |
| `tests/test_primer_fast.py:118` | `odc.pipeline.primer_stage._primer_diagnose_winner` | `odc.pipeline.primer_stage._primer_diagnose_winner` | 原始碼呼叫：odc/pipeline/primer_stage.py:67 primer_guided_research: _primer_diagnose_winner |
| `tests/test_primer_fast.py:119` | `odc.pipeline.primer_stage.insert_node_seed` | `odc.pipeline.primer_stage.insert_node_seed` | 原始碼呼叫：odc/pipeline/primer_stage.py:92 primer_guided_research: insert_node_seed |
| `tests/test_primer_fast.py:120` | `odc.pipeline.primer_stage.MissionOptimizer` | `odc.pipeline.primer_stage.MissionOptimizer` | 原始碼呼叫：odc/pipeline/primer_stage.py:132 _primer_fast_research: MissionOptimizer |
| `tests/test_primer_fast.py:121` | `odc.pipeline.primer_stage.run_study_over_revs` | `odc.pipeline.primer_stage.run_study_over_revs` | 原始碼呼叫：odc/pipeline/primer_stage.py:156 _primer_fast_research: run_study_over_revs |
| `tests/test_primer_fast.py:122` | `odc.pipeline.primer_stage.log.info` | `odc.pipeline.primer_stage.log.info` | 原始碼呼叫：odc/pipeline/primer_stage.py:100 primer_guided_research: log.info |
| `tests/test_primer_fast.py:188` | `odc.search.optimizer.time` | `odc.search.optimizer.time` | 原始碼呼叫：odc/search/optimizer.py:296 __init__: time.perf_counter |
| `tests/test_primer_fast.py:188` | `odc.search.optimizer.time` | `odc.search.fitness.time` | 原始碼呼叫：odc/search/fitness.py:37 __call__: time.monotonic；原單一模組的時鐘 mock 拆為兩個呼叫模組，時鐘值及斷言不變。 |
| `tests/test_primer_fast.py:189` | `odc.search.optimizer.fast_fitness_evaluator` | `odc.search.optimizer.fast_fitness_evaluator` | 原始碼呼叫：odc/search/optimizer.py:471 _optimize_burn_case: fast_fitness_evaluator |
| `tests/test_primer_fast.py:190` | `opt._generate_seed_candidates` | `opt._generate_seed_candidates` | 實例方法；_optimize_burn_case 呼叫 self._generate_seed_candidates，實例上的替換仍優先於類別與 mixin。 |
| `tests/test_primer_fast.py:201` | `odc.search.optimizer.fast_fitness_evaluator` | `odc.search.optimizer.fast_fitness_evaluator` | 原始碼呼叫：odc/search/optimizer.py:471 _optimize_burn_case: fast_fitness_evaluator |
| `tests/test_primer_fast.py:220` | `odc.search.optimizer.time` | `odc.search.optimizer.time` | 原始碼呼叫：odc/search/optimizer.py:296 __init__: time.perf_counter |
| `tests/test_primer_fast.py:220` | `odc.search.optimizer.time` | `odc.search.fitness.time` | 原始碼呼叫：odc/search/fitness.py:37 __call__: time.monotonic；原單一模組的時鐘 mock 拆為兩個呼叫模組，時鐘值及斷言不變。 |
| `tests/test_primer_fast.py:221` | `odc.search.optimizer.fast_fitness_evaluator` | `odc.search.optimizer.fast_fitness_evaluator` | 原始碼呼叫：odc/search/optimizer.py:471 _optimize_burn_case: fast_fitness_evaluator |
| `tests/test_primer_fast.py:249` | `opt._optimize_burn_case` | `opt._optimize_burn_case` | run_study 將實例的 _optimize_burn_case 傳給 executor.submit；替換的是送入執行器的 bound method。 |
| `tests/test_primer_fast.py:250` | `opt._pick_best_case` | `opt._pick_best_case` | 實例方法；run_study 呼叫 self._pick_best_case。 |
| `tests/test_primer_fast.py:251` | `opt._replay_mission` | `opt._replay_mission` | 實例方法；refine_trajectory／save_no_legal_route 呼叫實例的 _replay_mission。 |
| `tests/test_primer_fast.py:252` | `opt.refine_trajectory` | `opt.refine_trajectory` | 實例方法；run_study／搜尋收尾呼叫實例的 refine_trajectory。 |
| `tests/test_primer_fast.py:169` | `odc.pipeline.primer_stage._primer_diagnose_winner` | `odc.pipeline.primer_stage._primer_diagnose_winner` | 原始碼呼叫：odc/pipeline/primer_stage.py:67 primer_guided_research: _primer_diagnose_winner |
| `tests/test_primer_fast.py:171` | `odc.pipeline.primer_stage.run_study_over_revs` | `odc.pipeline.primer_stage.run_study_over_revs` | 原始碼呼叫：odc/pipeline/primer_stage.py:156 _primer_fast_research: run_study_over_revs |
| `tests/test_primer_fast.py:239` | `odc.search.optimizer.MissionOptimizer` | `odc.search.revs.MissionOptimizer` | 原始碼呼叫：odc/search/revs.py:167 run_study_over_revs: MissionOptimizer |
| `tests/test_primer_fast.py:240` | `odc.search.optimizer.time` | `odc.search.revs.time` | 原始碼呼叫：odc/search/revs.py:152 run_study_over_revs: time.monotonic |
| `tests/test_primer_fast.py:85` | `odc.pipeline.primer_stage._primer_diagnose_winner` | `odc.pipeline.primer_stage._primer_diagnose_winner` | 原始碼呼叫：odc/pipeline/primer_stage.py:67 primer_guided_research: _primer_diagnose_winner |
| `tests/test_primer_fast.py:86` | `odc.pipeline.primer_stage.insert_node_seed` | `odc.pipeline.primer_stage.insert_node_seed` | 原始碼呼叫：odc/pipeline/primer_stage.py:92 primer_guided_research: insert_node_seed |
| `tests/test_primer_fast.py:87` | `odc.pipeline.primer_stage.MissionOptimizer` | `odc.pipeline.primer_stage.MissionOptimizer` | 原始碼呼叫：odc/pipeline/primer_stage.py:132 _primer_fast_research: MissionOptimizer |
| `tests/test_primer_fast.py:88` | `odc.pipeline.primer_stage.run_study_over_revs` | `odc.pipeline.primer_stage.run_study_over_revs` | 原始碼呼叫：odc/pipeline/primer_stage.py:156 _primer_fast_research: run_study_over_revs |
| `tests/test_ranking_penalty_v2.py:269` | `odc.pipeline.stages.run_seed_portfolio` | `odc.pipeline.stages.run_seed_portfolio` | 原始碼呼叫：odc/pipeline/stages.py:203 _run_stages: run_seed_portfolio |
| `tests/test_ranking_penalty_v2.py:284` | `odc.pipeline.stages.run_seed_portfolio` | `odc.pipeline.stages.run_seed_portfolio` | 原始碼呼叫：odc/pipeline/stages.py:203 _run_stages: run_seed_portfolio |
| `tests/test_ranking_rules.py:155` | `pre._report_level` | `pre._report_level` | optimizer 實例的日誌層級狀態，由 log.log 讀取；非函式 mock。 |
| `tests/test_ranking_rules.py:160` | `wide._report_level` | `wide._report_level` | optimizer 實例的日誌層級狀態，由 log.log 讀取；非函式 mock。 |
| `tests/test_ranking_rules.py:178` | `odc.pipeline.report.log.warning` | `odc.pipeline.report.log.warning` | 原始碼呼叫：odc/pipeline/report.py:149 print_score_breakdown: log.warning |
| `tests/test_ranking_rules.py:179` | `odc.pipeline.report.log.info` | `odc.pipeline.report.log.info` | 原始碼呼叫：odc/pipeline/report.py:144 print_score_breakdown: log.info |
| `tests/test_search_coast_rtol.py:84` | `odc.search.optimizer.L_SHADE` | `odc.search.optimizer.L_SHADE` | 原始碼呼叫：odc/search/optimizer.py:513 _optimize_burn_case: L_SHADE |
| `tests/test_search_coast_rtol.py:84` | `odc.search.optimizer.fast_fitness_evaluator` | `odc.search.optimizer.fast_fitness_evaluator` | 原始碼呼叫：odc/search/optimizer.py:471 _optimize_burn_case: fast_fitness_evaluator |
| `tests/test_search_coast_rtol.py:85` | `odc.search.optimizer.minimize` | `odc.search.optimizer.minimize` | 原始碼呼叫：odc/search/optimizer.py:579 _optimize_burn_case: minimize |
| `tests/test_search_coast_rtol.py:86` | `opt._generate_seed_candidates` | `opt._generate_seed_candidates` | 實例方法；_optimize_burn_case 呼叫 self._generate_seed_candidates，實例上的替換仍優先於類別與 mixin。 |
| `tests/test_split_aware_terminal.py:122` | `opt.mission_metrics` | `opt.mission_metrics` | 實例方法；搜尋候選評估呼叫 self.mission_metrics。 |
| `tests/test_split_aware_terminal.py:190` | `odc.pipeline.solve._search_stage` | `odc.pipeline.solve._search_stage` | 原始碼呼叫：odc/pipeline/solve.py:57 _solve_de_pipeline: _search_stage |
| `tests/test_split_aware_terminal.py:191` | `odc.pipeline.legalize._legalize_stage` | `odc.pipeline.legalize._legalize_stage` | 原始碼呼叫：odc/pipeline/legalize.py:245 _fallback_to_legal_backup: _legalize_stage |
| `tests/test_split_defaults.py:24` | `os.cpu_count` | `os.cpu_count` | legalize.split_options 呼叫 os.cpu_count；各模組持有同一個 os 模組物件，此 patch 會改到實際呼叫的屬性。 |
| `tests/test_split_defaults.py:49` | `os.cpu_count` | `os.cpu_count` | legalize.split_options 呼叫 os.cpu_count；各模組持有同一個 os 模組物件，此 patch 會改到實際呼叫的屬性。 |
| `tests/test_split_defaults.py:63` | `os.cpu_count` | `os.cpu_count` | legalize.split_options 呼叫 os.cpu_count；各模組持有同一個 os 模組物件，此 patch 會改到實際呼叫的屬性。 |
| `tests/test_split_defaults.py:72` | `odc.pipeline.legalize.threadpool_limits` | `odc.pipeline.legalize.threadpool_limits` | 原始碼呼叫：odc/pipeline/legalize.py:203 _legalize_stage: threadpool_limits |
| `tests/test_split_defaults.py:73` | `odc.pipeline.legalize.legalize_violating_winner` | `odc.pipeline.legalize.legalize_violating_winner` | 原始碼呼叫：odc/pipeline/legalize.py:204 _legalize_stage: legalize_violating_winner |
| `tests/test_split_leading.py:102` | `odc.pipeline.legalize.legalize_route` | `odc.pipeline.legalize.legalize_route` | 原始碼呼叫：odc/pipeline/legalize.py:109 legalize_violating_winner: legalize_route |
| `tests/test_split_leading.py:116` | `odc.pipeline.legalize.presplit_leading` | `odc.pipeline.legalize.presplit_leading` | 原始碼呼叫：odc/pipeline/legalize.py:93 legalize_violating_winner: presplit_leading |
| `tests/test_split_leading.py:144` | `odc.pipeline.legalize.legalize_route` | `odc.pipeline.legalize.legalize_route` | 原始碼呼叫：odc/pipeline/legalize.py:109 legalize_violating_winner: legalize_route |
| `tests/test_split_leading.py:149` | `odc.pipeline.legalize.legalize_route` | `odc.pipeline.legalize.legalize_route` | 原始碼呼叫：odc/pipeline/legalize.py:109 legalize_violating_winner: legalize_route |
| `tests/test_split_leading.py:238` | `odc.pipeline.legalize.legalize_violating_winner` | `odc.pipeline.legalize.legalize_violating_winner` | 原始碼呼叫：odc/pipeline/legalize.py:204 _legalize_stage: legalize_violating_winner |
| `tests/test_split_leading.py:208` | `odc.pipeline.primer_stage._primer_diagnose_winner` | `odc.pipeline.primer_stage._primer_diagnose_winner` | 原始碼呼叫：odc/pipeline/primer_stage.py:67 primer_guided_research: _primer_diagnose_winner |
| `tests/test_split_leading.py:209` | `odc.pipeline.primer_stage.insert_node_seed` | `odc.pipeline.primer_stage.insert_node_seed` | 原始碼呼叫：odc/pipeline/primer_stage.py:92 primer_guided_research: insert_node_seed |
| `tests/test_split_leading.py:210` | `odc.pipeline.primer_stage.MissionOptimizer` | `odc.pipeline.primer_stage.MissionOptimizer` | 原始碼呼叫：odc/pipeline/primer_stage.py:132 _primer_fast_research: MissionOptimizer |
| `tests/test_split_leading.py:211` | `odc.pipeline.primer_stage.run_study_over_revs` | `odc.pipeline.primer_stage.run_study_over_revs` | 原始碼呼叫：odc/pipeline/primer_stage.py:156 _primer_fast_research: run_study_over_revs |
| `tests/test_split_leading.py:212` | `odc.pipeline.legalize.legalize_violating_winner` | `odc.pipeline.legalize.legalize_violating_winner` | 原始碼呼叫：odc/pipeline/legalize.py:204 _legalize_stage: legalize_violating_winner |
| `tests/test_split_leading.py:163` | `opt._replay_mission` | `opt._replay_mission` | 實例方法；refine_trajectory／save_no_legal_route 呼叫實例的 _replay_mission。 |
| `tests/test_split_leading.py:164` | `odc.pipeline.checkpoints.log.error` | `odc.pipeline.checkpoints.log.error` | 原始碼呼叫：odc/pipeline/checkpoints.py:124 save_no_legal_route: log.error |
| `tests/test_split_stm.py:126` | `odc.split.burn_splitter.joint_nlp_split` | `odc.split.burn_splitter.joint_nlp_split` | 原始碼呼叫：odc/split/burn_splitter.py:876 prune_reopt: joint_nlp_split |
| `tests/test_split_stm.py:207` | `odc.split.burn_splitter.FDPool.jacobian` | `odc.split.burn_splitter.FDPool.jacobian` | 原始碼呼叫：odc/split/burn_splitter.py:599 jac_all: fd_map.jacobian |
| `tests/test_sweep_params.py:189` | `odc.tools.sweep_params._run_sweep` | `odc.tools.sweep_params._run_sweep` | 原始碼呼叫：odc/tools/sweep_params.py:361 run_sweep: _run_sweep |
| `tests/test_sweep_params.py:164` | `odc.tools.sweep_params.subprocess.Popen` | `odc.tools.sweep_params.subprocess.Popen` | 原始碼呼叫：odc/tools/sweep_params.py:287 start_job: subprocess.Popen |
| `tests/test_tiebreak.py:136` | `odc.search.optimizer.log.warning` | `odc.search.revs.log.warning` | 原始碼呼叫：odc/search/revs.py:217 run_study_over_revs: log.warning |
| `tests/test_tiebreak.py:146` | `odc.search.optimizer.log.warning` | `odc.search.revs.log.warning` | 原始碼呼叫：odc/search/revs.py:217 run_study_over_revs: log.warning |

共 115 項；94 項直接找到函式內呼叫，其餘依上列實例方法、間接分派或資料讀取位置核對。

