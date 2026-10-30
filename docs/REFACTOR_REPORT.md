# ODC 重構驗收報告

日期：2026-10-30。依使用者追加指示，階段 0 至 6 依序完成；每階段正式驗收通過後才套用下一階段。

## 驗收證據

| 案例 | 階段 0（兩次） | 階段 1 | 階段 2 | 階段 3 | 階段 4 | 階段 5 |
|---|---|---|---|---|---|---|
| smoke_full | 相同 | 相同 | 相同 | 相同 | 相同 | 相同 |
| prelim_split | 相同 | 相同 | 相同 | 相同 | 相同 | 相同 |
| ranking_oracle | 相同 | 相同 | 相同 | 相同 | 相同 | 相同 |
| hyperbolic | 相同 | 相同 | 相同 | 相同 | 相同 | 相同 |
| from_winner | 相同 | 相同 | 相同 | 相同 | 相同 | 相同 |
| from_mission | 相同 | 相同 | 相同 | 相同 | 相同 | 相同 |
| tool_feasibility | 相同 | 相同 | 相同 | 相同 | 相同 | 相同 |
| tool_check | 相同 | 相同 | 相同 | 相同 | 相同 | 相同 |
| tool_tmax | 相同 | 相同 | 相同 | 相同 | 相同 | 相同 |
| tool_scoring | 相同 | 相同 | 相同 | 相同 | 相同 | 相同 |
| sweep_dry | 相同 | 相同 | 相同 | 相同 | 相同 | 相同 |

每次數值子行程均固定 OMP、OPENBLAS、MKL、NUMBA、NUMEXPR 執行緒為 1，PYTHONHASHSEED=0，並使用新建的空 NUMBA_CACHE_DIR。
GMAT 腳本逐位元比較；燃燒、滑行與 mission_info 所有數值完全相等，沒有套用數值容忍度。
排除環境資料的實際鍵路徑見 [基準報告](../outputs/equivalence/baseline/equivalence_report.md#正規化時排除的鍵)：時間戳、絕對路徑、run_dir、provenance、artifact_id、來源存檔雜湊與牆鐘時間欄位。
oracle 會把剩餘時間寫回贏家 config.strategy.SPLIT_WALL_BUDGET_SEC，因此此時間衍生欄位也排除；原始快照與設定副本均保留。
備份檔名 history/output_YYYYMMDD_HHMMSS.txt 只在檔名比對時正規化；其內容仍逐位元檢查。
ranking_oracle 的候選 JSON 證明 spawn 完成，audit hook 記錄父行程及 oracle worker 的 fork 建立事件，且沒有觸發牆鐘期限。

| 階段 | quick 通過 | 正式紀錄 |
|---|---|---|
| 0 | 22/22；242.5 s | [原始紀錄](../outputs/equivalence/baseline/regression.txt) |
| 1 | 22/22；244.9 s | [原始紀錄](../outputs/equivalence/stage1_regression.txt) |
| 2 | 23/23；306.4 s | [原始紀錄](../outputs/equivalence/stage2_regression.txt) |
| 3 | 23/23；228.2 s | [原始紀錄](../outputs/equivalence/stage3_regression.txt) |
| 4 | 23/23；238.5 s | [原始紀錄](../outputs/equivalence/stage4_regression.txt) |
| 5 | 23/23；223.3 s | [原始紀錄](../outputs/equivalence/stage5_regression.txt) |

以上均排除 test_retarget_gmat_e2e；runner 的實際指令與篩選名稱寫在各紀錄第一行。
另有一次階段 4 的 8 項針對性檢查漏設固定執行緒，雖為 8/8 通過但耗時 2660.6 s；不作正式效能或等價判定，正式驗收已另以固定環境執行。

### 牆鐘差異超過 30%

差異只供觀察，不影響數值與腳本判定。

| 階段 | 案例 | 基準中位秒數 | 本次秒數 | 差異 |
|---|---|---|---|---|
| 2 | smoke_full | 59.242 | 80.161 | +35.3% |

## 階段 0：比對基準

- 新增 tests/equivalence/run_equivalence.py 與 README.md，支援兩種入口、案例選擇、重複執行及逐項報告。
- 執行 legacy --repeat 2 產生全部 11 個案例，並以 --out 與 --compare 同指基準目錄完成自我比對。
- 初版曾把備份檔名時間戳及 oracle 剩餘預算當成差異；修正正規化後，以保留的原始產物重新整理快照並自我比對，結果 0 不同、0 不穩定。
- 用記憶體內的 1e-12 數值差、單一腳本位元組、退出碼及缺檔變更確認比對器確實會擋下差異。
- 當階段完成時 git status 只有新增的 tests/equivalence/ 兩個檔案，既有程式未變動。

## 階段 1：套件搬移

| 舊路徑 | 新路徑 |
|---|---|
| `src/runlog.py` | `odc/runlog.py` |
| `src/config_validator.py` | `odc/config/validator.py` |
| `src/split_defaults.py` | `odc/config/split_defaults.py` |
| `src/scoring_params.py` | `odc/config/scoring_params.py` |
| `src/tmax.py` | `odc/config/tmax.py` |
| `src/gmat_env.py` | `odc/config/gmat_env.py` |
| `src/core_math.py` | `odc/physics/core_math.py` |
| `src/propagator.py` | `odc/physics/propagator.py` |
| `src/_reference_propagators.py` | `odc/physics/reference_propagators.py` |
| `src/earth_gate.py` | `odc/physics/earth_gate.py` |
| `src/scorer.py` | `odc/scoring/scorer.py` |
| `src/optimizer.py` | `odc/search/optimizer.py` |
| `src/primer.py` | `odc/search/primer.py` |
| `src/oracle_twoburn.py` | `odc/search/oracle_twoburn.py` |
| `src/oracle_worker.py` | `odc/search/oracle_worker.py` |
| `src/burn_splitter.py` | `odc/split/burn_splitter.py` |
| `src/script_generator.py` | `odc/gmat/script_generator.py` |
| `src/retarget.py` | `odc/gmat/retarget.py` |
| `src/pipeline_artifacts.py` | `odc/pipeline/artifacts.py` |

建立 odc 與各子套件的 __init__.py，內容只含一行說明字串；新增的模組檔頭為繁體中文責任與入口說明。
刪除空 src 與其快取；188 個頂層函式／類別在套用 import／模組路徑替換後逐字相同。
artifacts.ROOT 配合套件深度改成 parents[2]，sweep 的 Numba 快取 glob 改查 odc 子套件；PHYSICS_FILES 維持原 7 項對應。
匯入 optimizer、burn_splitter、retarget、artifacts 成功；未新增循環 import 處理。

舊路徑檢查：

```bash
rg -n 'src\.' --glob '*.py' --glob '!.venv/**' --glob '!outputs/**' --glob '!docs/research/**' --glob '!docs/archive/**' --glob '!docs/log/**' .
rg -n 'src/' --glob '*.py' --glob '*.sh' --glob '*.json' --glob '!.venv/**' --glob '!outputs/**' --glob '!docs/research/**' --glob '!docs/archive/**' --glob '!docs/log/**' .
```

src/ 為 0 筆；src. 只有 test_retarget_gmat_e2e.py 的區域變數 src.read_bytes()，不是舊模組引用，依禁止重新命名規則保留。
階段 1 明列的 docs/research/oracle_phase2/*.py 僅更新模組引用；歷史 JSON、CSV 等結果未變動。

### 使用者核准的腳本註解例外

使用者選擇更新 src/gmat_env.py 與 src/script_generator.py 的生成註解路徑，接受這兩段文字差異。
額外以原版產生器對照 ranking_full、全攝動 replay 與 B 平面 DC 三種腳本，確認僅這兩處路徑註解不同，其餘位元組相同；見 [紀錄](../outputs/equivalence/authorized_script_comment_check.json)。

## 階段 2：單一入口

| 舊路徑 | 階段 2 路徑 |
|---|---|
| `main.py` | `odc/pipeline/main.py` |
| `feasibility.py` | `odc/tools/feasibility.py` |
| `check_problem.py` | `odc/tools/check_problem.py` |
| `sweep_burns.py` | `odc/tools/sweep_burns.py` |
| `sweep_params.py` | `odc/tools/sweep_params.py` |
| `run_regression.py` | `odc/tools/regression.py` |
| `scripts/tmax_from_boundary.py` | `odc/tools/tmax_from_boundary.py` |
| `scripts/check_scoring_params.py` | `odc/tools/check_scoring_params.py` |
| `scripts/output_inventory.py` | `odc/tools/output_inventory.py` |

新增根目錄 odc.py、odc/cli.py、odc/paths.py 與 tests/test_odc_cli.py；根目錄舊入口全部移除，沒有相容殼。
CLI 只翻譯位置參數與分派，沿用原工具 parser，選定子命令才 import；工作目錄錯誤回傳 2，工具 SystemExit 及找不到合法路線的 3 原樣傳遞。
既有工具 main／parse_args 加入 argv=None 並傳給 parse_args(argv)；以腳本位置找根目錄的敘述改用 ROOT，sweep 及研究子行程改呼叫 odc.py。
原 6 項 CLI 測試通過；完整 patch 對照見 [階段 2 表](REFACTOR_PATCH_TARGETS.md#階段-2)。

### 當時的完整 --help 輸出

```text
usage: odc [-h] 子命令 ...

軌道攔截設計賽：任務規劃與驗證工具

positional arguments:
  子命令
    solve        搜尋任務並依序產出方案與腳本
    resume       讀取拆棒前贏家，接續合法化與輸出
    export       讀取任務方案，產出 GMAT 腳本
    retarget     在全攝動模型下重新瞄準已存方案
    verify       使用 GMAT 驗證既有腳本
    check        檢查情境的軌道、規則與參數
    feasibility  評估情境可行性與合法解稀有程度
    sweep-burns  粗掃燃燒次數並精查候選範圍
    sweep        執行情境、種子與搜尋參數的批次實驗
    test         執行獨立腳本形式的回歸測試
    tmax         由任務邊界計算可用時間
    scoring      換算與驗算官方計分參數
    outputs      索引、封存及還原本機執行成果

options:
  -h, --help     show this help message and exit

常用範例：
  uv run python odc.py solve configs/shared/ranking_round.json --no-gmat
  uv run python odc.py resume winner_presplit_seed0.json --no-gmat
  uv run python odc.py test --quick -q
```

## 階段 3：設定檔分流

.gitignore 改為整個 configs/shared 放行、configs/local 忽略；default_config_path() 支援新路徑與舊檔提示，原自動建立預設檔的行為保留。
新增 odc/tools/new_config.py 與 new-config 子命令；另補一項暫存目錄測試，涵蓋原樣複製、GMAT 覆寫、既存檔保留與驗證失敗清理。
17 個根目錄設定與 33 個 C4 本機檔案共 50 檔以搬移方式保存，SHA256 全部不變；C4 預設路徑跟著改到 configs/local/c4。
共用情境與本機檔案的 Git 檢查：

```text
On branch Master
Your branch is up to date with 'origin/Master'.

Ignored files:
  (use "git add -f <file>..." to include in what will be committed)
	configs/local/

nothing to commit, working tree clean
configs/shared/contest.json
configs/shared/e1_r4.json
configs/shared/e1_r5.json
configs/shared/e1_r8.json
configs/shared/hard_mode_test.json
configs/shared/hyper_far.json
configs/shared/hyperbolic_smoke.json
configs/shared/hyperbolic_test.json
configs/shared/official_sample.json
configs/shared/playground.json
configs/shared/ranking_round.json
configs/shared/weird_test.json
```

### 本機檔案搬移清單

| 舊路徑 | 新路徑 | SHA256 前 12 碼 |
|---|---|---|
| `configs/config.json` | `configs/local/config.json` | `3d6edd9c4d6f` |
| `configs/contest.json` | `configs/local/contest.json` | `92a85cbc81ac` |
| `configs/contest_6burns.json` | `configs/local/contest_6burns.json` | `55a94fc8168e` |
| `configs/contest_check.json` | `configs/local/contest_check.json` | `0da935f9fd14` |
| `configs/contest_heavy_split.json` | `configs/local/contest_heavy_split.json` | `efa2fb59d3a4` |
| `configs/contest_moreburns.json` | `configs/local/contest_moreburns.json` | `58c145577505` |
| `configs/contest_pcsplit.json` | `configs/local/contest_pcsplit.json` | `72fab3d66650` |
| `configs/contest_portfolio.json` | `configs/local/contest_portfolio.json` | `71f09c5c89a6` |
| `configs/contest_slow_legal.json` | `configs/local/contest_slow_legal.json` | `0fcf2ac04605` |
| `configs/final_rehearsal_1.json` | `configs/local/final_rehearsal_1.json` | `5a54342b90ac` |
| `configs/hyper_far.json` | `configs/local/hyper_far.json` | `07994bc10a98` |
| `configs/hyper_narrow.json` | `configs/local/hyper_narrow.json` | `217075b58514` |
| `configs/hyperbolic_smoke.json` | `configs/local/hyperbolic_smoke.json` | `f15553092f7e` |
| `configs/hyperbolic_test.json` | `configs/local/hyperbolic_test.json` | `c497ae9f02ad` |
| `configs/practice_scenario.json` | `configs/local/practice_scenario.json` | `8af5abaf74b7` |
| `configs/practice_scenario_suggested.json` | `configs/local/practice_scenario_suggested.json` | `7ccbcce7e0b0` |
| `configs/weird_test.json` | `configs/local/weird_test.json` | `194cd29779af` |
| `configs/c4/E1_contest_off.json` | `configs/local/c4/E1_contest_off.json` | `4d1145469eb2` |
| `configs/c4/E1_contest_on.json` | `configs/local/c4/E1_contest_on.json` | `70f130e46a99` |
| `configs/c4/E2_force4_s0_off.json` | `configs/local/c4/E2_force4_s0_off.json` | `616358ac81e9` |
| `configs/c4/E2_force4_s0_on.json` | `configs/local/c4/E2_force4_s0_on.json` | `2cd91b84db97` |
| `configs/c4/E2_force4_s1_off.json` | `configs/local/c4/E2_force4_s1_off.json` | `c3ba3b9cbb04` |
| `configs/c4/E2_force4_s1_on.json` | `configs/local/c4/E2_force4_s1_on.json` | `7e4ec81a8221` |
| `configs/c4/E2_force4_s2_off.json` | `configs/local/c4/E2_force4_s2_off.json` | `2df380733b5a` |
| `configs/c4/E2_force4_s2_on.json` | `configs/local/c4/E2_force4_s2_on.json` | `189c489ee2f6` |
| `configs/c4/E2_force4_s3_off.json` | `configs/local/c4/E2_force4_s3_off.json` | `d2f1c0e078f8` |
| `configs/c4/E2_force4_s3_on.json` | `configs/local/c4/E2_force4_s3_on.json` | `e71de2533bfc` |
| `configs/c4/E2_force4_s4_off.json` | `configs/local/c4/E2_force4_s4_off.json` | `2e2257565415` |
| `configs/c4/E2_force4_s4_on.json` | `configs/local/c4/E2_force4_s4_on.json` | `b94278c08afe` |
| `configs/c4/E2_force4_s5_off.json` | `configs/local/c4/E2_force4_s5_off.json` | `a844a29907bd` |
| `configs/c4/E2_force4_s5_on.json` | `configs/local/c4/E2_force4_s5_on.json` | `eff2fd8bfa0d` |
| `configs/c4/E2_force4_s6_off.json` | `configs/local/c4/E2_force4_s6_off.json` | `8efffead530f` |
| `configs/c4/E2_force4_s6_on.json` | `configs/local/c4/E2_force4_s6_on.json` | `bd7681d3e941` |
| `configs/c4/E2_force4_s7_off.json` | `configs/local/c4/E2_force4_s7_off.json` | `841d20d69ed8` |
| `configs/c4/E2_force4_s7_on.json` | `configs/local/c4/E2_force4_s7_on.json` | `82e3fb09a52f` |
| `configs/c4/E2_force4_s8_off.json` | `configs/local/c4/E2_force4_s8_off.json` | `bc30afbe63b8` |
| `configs/c4/E2_force4_s8_on.json` | `configs/local/c4/E2_force4_s8_on.json` | `661037f72ee7` |
| `configs/c4/E3_contest4_off.json` | `configs/local/c4/E3_contest4_off.json` | `ae2c6a7de027` |
| `configs/c4/E3_contest4_on.json` | `configs/local/c4/E3_contest4_on.json` | `4926312cf70d` |
| `configs/c4/E4_hyper_far_off.json` | `configs/local/c4/E4_hyper_far_off.json` | `11d40033608b` |
| `configs/c4/E4_hyper_far_on.json` | `configs/local/c4/E4_hyper_far_on.json` | `ea77efb61bd2` |
| `configs/c4/E4_hyperbolic_smoke_off.json` | `configs/local/c4/E4_hyperbolic_smoke_off.json` | `581086027e92` |
| `configs/c4/E4_hyperbolic_smoke_on.json` | `configs/local/c4/E4_hyperbolic_smoke_on.json` | `effc9eb4f3eb` |
| `configs/c4/E4_hyperbolic_test_off.json` | `configs/local/c4/E4_hyperbolic_test_off.json` | `6e885b975ac5` |
| `configs/c4/E4_hyperbolic_test_on.json` | `configs/local/c4/E4_hyperbolic_test_on.json` | `602a37d0e71f` |
| `configs/c4/E5_official_sample_off.json` | `configs/local/c4/E5_official_sample_off.json` | `9a60a710993d` |
| `configs/c4/E5_official_sample_on.json` | `configs/local/c4/E5_official_sample_on.json` | `cb80344994a8` |
| `configs/c4/E5_playground_off.json` | `configs/local/c4/E5_playground_off.json` | `090a3b48526f` |
| `configs/c4/E5_playground_on.json` | `configs/local/c4/E5_playground_on.json` | `969fd1f3a6eb` |
| `configs/c4/E6_contest_default.json` | `configs/local/c4/E6_contest_default.json` | `8c2028036383` |

完整 SHA256 見 [搬移紀錄](../outputs/equivalence/stage3_config_moves.json)。

## 階段 4：主管線拆分

| 新模組 | 當時行數 |
|---|---|
| `odc/config/defaults.py` | 122 |
| `odc/gmat/verification.py` | 187 |
| `odc/pipeline/checkpoints.py` | 124 |
| `odc/pipeline/legalize.py` | 260 |
| `odc/pipeline/primer_stage.py` | 181 |
| `odc/pipeline/report.py` | 149 |
| `odc/pipeline/solve.py` | 201 |
| `odc/pipeline/stages.py` | 581 |

刪除 odc/pipeline/main.py；30 個函式／類別本體逐字相同，只有以下兩處必要的函式內 import。沒有表外的模組層級名稱需要額外分派。
- legalize._fallback_to_legal_backup 內匯入 solve._search_stage 與 _final_rank_key，避免 solve 與 legalize 循環。
- primer_stage._primer_post_rank_key 內匯入 solve._final_rank_key，避免 solve 與 primer_stage 循環。
PHYSICS_FILES 加入原主管線拆出的全部 8 個模組，成為 15 項；provenance 不再列已刪除的 main 模組。
patch 對照與每個呼叫位置見 [階段 4 表](REFACTOR_PATCH_TARGETS.md#階段-4)。

## 階段 5：搜尋器拆分

| 模組 | 當時行數 |
|---|---|
| `odc/search/fitness.py` | 415 |
| `odc/search/mission_eval.py` | 266 |
| `odc/search/optimizer.py` | 1160 |
| `odc/search/ranking.py` | 128 |
| `odc/search/replay.py` | 213 |
| `odc/search/revs.py` | 231 |
| `odc/search/seeds.py` | 793 |

MissionOptimizer 的方法分為本體 18 個、SeedCandidatesMixin 10 個、MissionEvalMixin 8 個；兩個 mixin 無 __init__ 或資料類別屬性。
36 個方法名稱與 inspect.getsource 完全相同，三組方法名稱互不重疊。MRO：

```text
odc.search.optimizer.MissionOptimizer → odc.search.seeds.SeedCandidatesMixin → odc.search.mission_eval.MissionEvalMixin → builtins.object
```

| 方法 | 拆分後定義位置 | 原始碼比對 |
|---|---|---|
| `__init__` | `MissionOptimizer` | 逐字相同 |
| `_attach_progress_reporting` | `MissionOptimizer` | 逐字相同 |
| `_best_lambert` | `MissionOptimizer` | 逐字相同 |
| `_direction_to_spherical` | `SeedCandidatesMixin` | 逐字相同 |
| `_fitness_wrapper` | `MissionOptimizer` | 逐字相同 |
| `_generate_bounds` | `MissionOptimizer` | 逐字相同 |
| `_generate_ladder_seed_candidates` | `SeedCandidatesMixin` | 逐字相同 |
| `_generate_multiburn_seed_candidates` | `SeedCandidatesMixin` | 逐字相同 |
| `_generate_nlp_refined_seed_candidates` | `SeedCandidatesMixin` | 逐字相同 |
| `_generate_planechange_split_seed_candidates` | `SeedCandidatesMixin` | 逐字相同 |
| `_generate_seed_candidates` | `SeedCandidatesMixin` | 逐字相同 |
| `_log_no_legal_route` | `MissionOptimizer` | 逐字相同 |
| `_maxiter_for` | `MissionOptimizer` | 逐字相同 |
| `_narrow_tolerance_bounds` | `SeedCandidatesMixin` | 逐字相同 |
| `_optimize_burn_case` | `MissionOptimizer` | 逐字相同 |
| `_orbit_radius_range` | `SeedCandidatesMixin` | 逐字相同 |
| `_pick_best_case` | `MissionOptimizer` | 逐字相同 |
| `_replay_mission` | `MissionEvalMixin` | 逐字相同 |
| `_scalar_params` | `MissionOptimizer` | 逐字相同 |
| `_search_scalar_params` | `MissionOptimizer` | 逐字相同 |
| `_search_score_terms` | `MissionEvalMixin` | 逐字相同 |
| `_split_aware_dv_ub` | `SeedCandidatesMixin` | 逐字相同 |
| `_tiebreak_polish` | `MissionOptimizer` | 逐字相同 |
| `_vector_params` | `MissionOptimizer` | 逐字相同 |
| `assess_burn_logs` | `MissionEvalMixin` | 逐字相同 |
| `energy_floor_dv` | `SeedCandidatesMixin` | 逐字相同 |
| `legality_fields` | `MissionEvalMixin` | 逐字相同 |
| `mission_metrics` | `MissionEvalMixin` | 逐字相同 |
| `preflight_report` | `MissionOptimizer` | 逐字相同 |
| `ranking_score` | `MissionEvalMixin` | 逐字相同 |
| `refine_trajectory` | `MissionOptimizer` | 逐字相同 |
| `run_study` | `MissionOptimizer` | 逐字相同 |
| `search_score` | `MissionEvalMixin` | 逐字相同 |
| `split_est_score` | `MissionEvalMixin` | 逐字相同 |
| `state_A` | `MissionOptimizer` | 逐字相同 |
| `state_B` | `MissionOptimizer` | 逐字相同 |

19 個頂層定義／常數（含 njit 裝飾器參數）亦逐字相同。PHYSICS_FILES 加入 6 個新搜尋模組後共 21 項。
兩處原 optimizer.time 時鐘 mock 展開為 optimizer.time 與 fitness.time，覆蓋分開後的兩個實際呼叫模組，原時鐘值及斷言未改。
其他測試只更新 import、必要的名稱引用與 patch 目標；見 [階段 5 表](REFACTOR_PATCH_TARGETS.md#階段-5)。

## 階段 6：文件與最終檢查

- 新增 [ARCHITECTURE.md](ARCHITECTURE.md)，94 行，包含實際檔案樹、套件職責、solve 順序與版本驗證。
- 新增 REFACTOR_REPORT.md 與 REFACTOR_PATCH_TARGETS.md，保存階段報告與每個 patch 的對照。
- 新增 [CLI.md](CLI.md)，14 個子命令各提供 2 至 3 個範例與舊指令對照；30 個範例的 help 退出碼均為 0，所有選項均出現在原工具 help。
- README、STATUS、比賽當天手冊與工具導覽只機械式更新指令、路徑及必要索引。
- 使用者核准歷史 Markdown 只修改連結目標；目前共 39 個目標更新，正文、標籤與歷史指令經去除 URL 後逐字相同。
- 原先受保護的 29 個依賴設定、fixture、解與規則檔案之 SHA256 全部不變；50 個本機設定亦再驗雜湊一致。

連結檢查包含 Markdown 檔案目標、標題 anchor 及 Python #L 行號；排除 .venv、outputs、.git，結果見 [檢查紀錄](../outputs/equivalence/stage6_link_check.json)。
CLI 範例驗證採各實際指令附加 --help，再將範例的旗標逐個與原工具 help 比對，沒有執行新增設定、成果索引、封存或覆寫操作；見 [驗證紀錄](../outputs/equivalence/stage6_cli_validation.json)。

## 非搬移程式碼調整

以下列出 import／模組路徑字串之外的程式調整；行號以最終檔案為準。新模組檔頭及套件說明依規格新增，計算函式原文檢查見各階段。

| 檔案 | 行號 | 原因 |
|---|---|---|
| `odc/tools/feasibility.py` | 161 | 階段 2 明定加入 argv=None；傳給既有 parse_args(argv)，不更動選項或計算。 參數傳遞位置：167 行。 |
| `odc/tools/check_problem.py` | 69 | 階段 2 明定加入 argv=None；傳給既有 parse_args(argv)，不更動選項或計算。 參數傳遞位置：72 行。 |
| `odc/tools/sweep_burns.py` | 106 | 階段 2 明定加入 argv=None；傳給既有 parse_args(argv)，不更動選項或計算。 參數傳遞位置：136 行。 |
| `odc/tools/sweep_burns.py` | 198 | 階段 2 明定加入 argv=None；傳給既有 parse_args(argv)，不更動選項或計算。 參數傳遞位置：201 行。 |
| `odc/tools/sweep_params.py` | 510 | 階段 2 明定加入 argv=None；傳給既有 parse_args(argv)，不更動選項或計算。 參數傳遞位置：523 行。 |
| `odc/tools/regression.py` | 66 | 階段 2 明定加入 argv=None；傳給既有 parse_args(argv)，不更動選項或計算。 參數傳遞位置：71 行。 |
| `odc/tools/output_inventory.py` | 303 | 階段 2 明定加入 argv=None；傳給既有 parse_args(argv)，不更動選項或計算。 參數傳遞位置：310 行。 |
| `odc/cli.py` | 62 | 新增子命令翻譯、延遲分派、工作目錄檢查與結束碼傳遞。 |
| `odc/paths.py` | 10 | 階段 3 新增本機設定路徑選擇與舊檔警告。 |
| `odc/config/defaults.py` | 92 | 階段 3 將預設 filename 運算改用 default_config_path()；參數名稱及讀檔流程保留。 |
| `odc/pipeline/stages.py` | 153 | 階段 3 的無指定設定分支改呼叫 default_config_path()。 |
| `odc/tools/new_config.py` | 13 | 階段 3 新增共用設定複製、可選 GMAT 路徑、驗證與僅刪本次新檔的失敗清理。 |
| `odc/search/optimizer.py` | 37 | 階段 5 依指定方案加入兩個 mixin 基底，所有方法原始碼完全相同。 |
| `odc.py` | 1 | 階段 2 新增唯一入口及 CLI 回傳結束碼的 bootstrap。 |
| `tests/equivalence/run_equivalence.py` | 1 | 階段 0 新增基準執行、環境隔離、正規化、逐位元及完全相等比較工具。 |
| `tests/test_odc_cli.py` | 1 | 階段 2、3 新增 CLI 與 new-config 測試；原有測試斷言未改。 |
| `tests/test_primer_fast.py` | 188 | 階段 5 僅將時鐘 patch 目標展開為 optimizer.time 與 fitness.time，維持原單一模組的覆蓋範圍。 |
| `tests/test_primer_fast.py` | 220 | 階段 5 僅將時鐘 patch 目標展開為 optimizer.time 與 fitness.time，維持原單一模組的覆蓋範圍。 |

ROOT 深度、預設設定提示、快取 glob、子行程入口及 PHYSICS_FILES／provenance 皆屬搬移必要的路徑或清單調整；未修改數值常數、迴圈或亂數取用順序。

## 驗證範圍與使用者後續操作

本次按要求執行 quick 與 11 個等價案例；指定的 GMAT 端到端測試留待外部執行，Windows 未做實機驗證。既有 POSIX 工具的限制保留，新 CLI／路徑／設定建立程式使用 pathlib 與參數清單子行程。
舊 mission.json 的版本相容性處理見 [版本驗證](ARCHITECTURE.md#版本驗證)。

依指示未執行任何寫入 Git 的指令。請在外部補跑 GMAT 測試，檢閱變更後加入版控並提交：

```bash
uv run python tests/test_retarget_gmat_e2e.py
git add -A
git commit -m "refactor: reorganize ODC pipeline and CLI"
```

完整基準、各階段產物與原始 stdout／stderr 保留在 outputs/equivalence；該目錄依既有規則不進版控。
