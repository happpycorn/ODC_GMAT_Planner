# SPLIT_AWARE_SEARCH 大前導棒計分不一致：調查與修正

工作基準：`claude/oracle-phase2-20f0b0`，HEAD `14b7849`。

**整合時的調整（Claude 驗收時改）：新算法只在 `SPLIT_AWARE_SEARCH` 與 `SPLIT_LEADING` 都開時生效。** primer 條件式重搜會在預設設定（SPLIT_LEADING 關）下自動打開 SEARCH，若在那裡也換新算法，預設管線的結果就會變，四臂比較的臂 A（現行預設）也就不是原本的預設。所以 SPLIT_LEADING 關時保留舊算法（虛構加時、放寬 bounds、24 格 scalars），逐位元不變；這條路徑的不同尺問題列為已知問題，要不要修另案決定。下文第 2、5 點與「primer 重搜」一節描述的是 Codex 原始版本，以這段為準。

## 根因與重現數字

真正的 bug 是 `fast_fitness_evaluator` 在超標前導棒之後，只把 `current_time` 加上
`(ceil(dv/MAX_DV_SOFT)-1) × MIN_COAST_TIME`，卻沒有傳播對應的 r/v。這同時改變下一段
`coast_frac` 的解碼、Lambert 轉移時間及目標 A 的位置。同一個 x 因此在搜尋與重播代表不同軌跡。
`mission_metrics`、`_replay_mission`、`main.legalize_violating_winner` 都用沒有這段虛構加時的標準解碼。

另有政策不一致：scalar 14 只看 `SPLIT_AWARE_SEARCH`，不看下游是否開 `SPLIT_LEADING`，也不檢查
`LEADING_SPLIT_LIMIT`。因此 primer 只開 SEARCH 時，搜尋端仍把大前導棒當成可拆，下游卻判失格。
`SPLIT_AWARE_TERMINAL=False` 時也曾在搜尋端免除前導棒懲罰，但挑選用的原始分數仍扣分。

兩份原始 smoke JSON 均在同一行程直接建立 `MissionOptimizer`、呼叫 `_optimize_burn_case`，保留
MAXITER=600、POPSIZE=20、SEED=0、所有種子獨立精修；DE 設 `LAMBERT_MAX_REVS=0`。D 另外直接執行原始
高 REVS oracle 網格，取得相同 10 顆兩棒種子，連同原有種子共精修 12 顆。沒有使用 Manager 或 process pool。
OMP/OPENBLAS/MKL/NUMEXPR_NUM_THREADS 全設 1。

下表「搜尋分數」是 **−fitness**；原始 `fitness` 的符號相反。score 與 score_split_est 均為搜尋／排名值，
超標未拆的路線沒有官方交件分數。

| 修前階段 | 搜尋分數 | 重播 score | 重播拆後估計 | 總 Δv (m/s) | T_team (s) |
|---|---:|---:|---:|---:|---:|
| B/D，1 棒 | 85.248504427 | 75.215552412 | 85.215552412 | 851.240800 | 19968.255039 |
| B，2 棒 best_x | 86.732147980 | −18.019155219 | −18.022995863 | 5505.356121 | 19907.985745 |
| B，2 棒另行 refine 後 | 86.739042100 | −18.598942573 | −18.600856432 | 6548.812756 | 19908.315039 |
| D，2 棒 best_x | 86.743651880 | −18.618407059 | −18.620297540 | 6602.951063 | 19908.217189 |
| D，2 棒另行 refine 後 | 86.744014495 | −18.481953936 | −18.484233287 | 6277.355169 | 19908.237199 |

修前 B 的大前導棒為 490.361106 m/s，搜尋虛構加時 100 秒後，終端點火時刻為 15932.482467 s、
抵達 19972.556018 s；重播則為 15855.209045 s、19907.985745 s。重播終端棒變成 5014.995015 m/s，
超出可拆範圍 3472 m/s，且總燃料超過 3000 m/s，所以拆後估計落入失格層。
D 同樣虛構加時 100 秒：搜尋抵達 19972.807669 s、重播抵達 19908.217189 s，重播終端棒 6107.070863 m/s。

把舊 best_x 原封不動交給修後 evaluator：B 的搜尋分數從 86.732147980 變成 −18.180994567，
D 從 86.743651880 變成 −18.516717349，均正確辨識成失格。它們與攝動 DC 重播仍有 0.158、0.104 分差，
這是原有二體 Lambert 代理與 J2–J4 修正的差異；已沒有跨越合法／失格層的虛構好解。

修前兩組 `_pick_best_case()` 都選 1 棒，符合重播分數排序。這次不是分桶或 tiebreak 把好解丟掉。
兩組皆無 `legal_backup`：1 棒的 851 m/s 也不是直接合法解。備胎與拆棒失敗退路發生在後續合法化階段，
不是本次 2 棒在挑選前被淘汰的原因。`SPLIT_AWARE_TERMINAL` 開啟時，挑選確實有使用 `score_split_est`。

`_narrow_tolerance_bounds` 不會強迫這些大棒歸零：原始 x 都在放寬的 bounds 內，精修後仍為大前導棒。
它的窄時間界不能修復解碼差異；修前額外精修 2 棒只是在錯誤目標上繼續改善。
`_tiebreak_polish` 也沿用同一 evaluator，本次 1／2 棒分數未打平，挑選前不會對它們啟動平手精修。

## 修改與取捨

修改 `src/optimizer.py`：

1. SEARCH 開時取消虛構加時。`presplit_leading` 的既有策略是以原節點為中心把小棒排開、固定原抵達時刻，
   所以額外增加任務時間不是正確的成本模型。保留前導棒 2% 燃料預付，與 `split_est_score` 相同。
2. SEARCH 開時的 scalars 增加 24/25 兩格：真實單棒上限與下游前導可拆上限；後者為 0 代表不能拆。
   前導棒的可拆分類、超出範圍的失格量與重播對齊。缺新欄位的舊呼叫端保守視為不能拆前導棒。
3. SEARCH 開時，單棒超標判定使用真實 cap 及 `assess_legality` 的 1e-5 m/s 浮點容許量。
   搜尋 bounds 仍保留 MAX_DV_SOFT 安全邊界；避免 248–250 m/s 區間在兩邊被分到不同類。
4. 前導棒可拆但 `SPLIT_AWARE_TERMINAL=False` 時，搜尋保留每發 −10 的原始軟懲罰，不收只屬於拆後估計的 overhead，
   因為挑選此時使用原始 score。拆後估計欄位仍照原設計可供參考。
5. SEARCH 開、SPLIT_LEADING 關（含 AUTO_SPLIT_LEGALIZE 關）時，前導搜尋上界保持 MAX_DV_SOFT。
   對外部傳入的大棒，排位賽 evaluator 也會判入失格層，不能靠繞過 bounds 取得高分。

SEARCH 關時保留舊的 24 格 scalars、bounds、SOFT 門檻與計分路徑；沒有改重播、挑選、精修或備胎演算法。

這仍是拆後估計，不是拆解成功證明。間隔是否排得下、拆後弧是否 Earth-safe、重新解終端棒後是否還有足夠燃料，
由實拆階段檢查；對這些條件加入更完整的搜尋 surrogate 是另一項設計工作。

## 修後 smoke

同樣完整跑 600 代、單行程、REVS=0，B/D 的 `_pick_best_case` **都選中 2 棒**，均沒有直接合法備胎。

| 階段 | 搜尋分數 | 重播 score | 拆後估計 | 前導 Δv (m/s) | 終端 Δv (m/s) | 總 Δv (m/s) | T_team (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| B，2 棒 best_x | 86.648034183 | 76.695359541 | 86.629906582 | 495.482438 | 157.813838 | 653.296276 | 19970.913343 |
| B，選中並精修 | 86.733841244 | 76.774306097 | 86.706642619 | 520.816269 | 120.158959 | 640.975227 | 19972.949842 |
| D，2 棒 best_x | 86.668515341 | 66.679136787 | 86.645354156 | 255.741013 | 399.941186 | 655.682199 | 19971.841937 |
| D，選中並精修 | 86.731661209 | 66.738886064 | 86.703441127 | 271.662592 | 374.890655 | 646.553246 | 19971.769914 |

1 棒拆後估計仍為 85.215552412。修後搜尋／重播的剩餘差約 0.018–0.028 分，來自既有二體 Lambert 與 J2–J4
高精度 DC 的模型差異；不是錯把時間加進去。單元測試用無攝動案例隔離計分政策，避免用寬容差掩蓋本次 bug。

另外把兩組勝出的精修 x 交給 `_legalize_stage`，只把 SPLIT_WORKERS 從 3 改為 1，維持其他拆棒設定，實拆結果：

| 組別 | 合法棒數 | 官方 Python 分數 | 總 Δv (m/s) | T_team (s) | 最大單棒 (m/s) | 間隔違規 | Earth-safe |
|---|---:|---:|---:|---:|---:|---:|---|
| B | 4 | 86.783421730 | 639.557209 | 19972.984310 | 247.980000 | 0 | 是 |
| D | 4 | 86.784741310 | 639.351562 | 19972.990863 | 247.980000 | 0 | 是 |

兩組 `disqualified=False`、`official_score=score`。拆分後 joint NLP 可再微調時刻，所以上表不強求等於拆前 T_team。
D 實拆分數回到題目中 A 的約 86.7847；沒有宣稱此修改讓 D 超過 A 或保證得到全域最佳。

## 測試與相容性

新增 `tests/test_split_aware_search.py`，23 個檢查全部通過。固定 600 m/s 大前導棒二體案例：

- fast 與 mission_metrics 的拆後估計均為 **83.817556618**，重播與 mission_metrics 完全相同。
- `_pick_best_case` 用真實重建的 1 棒與 2 棒候選，選中 2 棒；沒有 mock mission_metrics。
- （原始版本）SPLIT_LEADING 關時兩邊均為 −12.603550296；整合版改成斷言 SPLIT_LEADING 關時維持舊 ABI 與放寬 bounds。
- 涵蓋 AUTO_SPLIT_LEGALIZE 關、TERMINAL 關、非預設 overhead、soft/真實 cap 間隙、超出前導上限、
  前導／終端同時超標、兩發大前導棒、預付燃料超總量上限，以及舊 ABI 與 SEARCH 關閉的欄位相容性。
- 分數容差 2e-6：只容納二體 Lambert、DOP853 與 DC 的積分／求解浮點誤差；實測上述主要案例到九位小數一致。

另外保存修前完整 optimizer，與修後實作做 SEARCH=False 的逐位元比較：32 組設定，涵蓋初賽／排位賽、
GRAVITY_DEGREE=0/4、星曆快取開／關、TERMINAL 開／關、LEADING 開／關、1/2/3 棒，
共 768 個固定亂數向量（321 個不是硬失敗值），**0 個 fitness 位元差異**；scalars 與 bounds 也相同。

`uv run python run_regression.py --quick`：**23/23 支通過，總耗時 378.6 s，exit 0**。
包含新增 SEARCH 測試、split_leading、split_aware_terminal、primer／primer_fast、oracle_twoburn、
ranking_rules／ranking_penalty_v2、tiebreak、搜尋容差及管線測試。`git diff --check` 亦通過。
這裡的 quick 不代表本次兩條贏家已通過 GMAT；本次沒有對贏家執行 GMAT。

## primer 重搜與尚未驗證部分

primer 仍只負責開 SEARCH、插入節點種子；沒有自動開 SPLIT_LEADING。未允許前導拆分時，重搜現在只在合法單棒範圍內
找新增節點；超標外部種子會按既有種子流程 clip 回 bounds，外部直接評分超標 x 也不能取得合法層高分。
若要搜尋 600 m/s 等前導節點，必須明確開 SPLIT_LEADING 並允許 AUTO_SPLIT_LEGALIZE。

這排除了「搜尋假設可拆、下游卻不拆」的政策差異，但不能證明 hyper_far 先前 7 次插棒變成 0 都由此造成。
沒有重跑那 7 次原始重搜；小棒最佳解仍可能合理地歸零。

未跑完整 CLI、REVS=4 的修後 DE／跨 REVS 集成、完整 primer 條件式重搜與退路重搜，亦未對本次兩條贏家做 GMAT 驗證。
目前驗證範圍為原始 smoke 設定的完整 REVS=0 DE、每候選精修與重播、挑選，以及單 worker 實拆。

## 重現與原始證據

新增 `scripts/research/diagnose_split_aware.py`，接受設定路徑與 `-o`，逐案例保存 best_x、fast、metrics、replay、
refine 後 x／fast／metrics、挑選結果與備胎；D 可用 `--oracle-cache` 重用相同網格種子。預設不縮小 MAXITER。

本機 uv 的依賴同步階段在沙盒觸發 macOS system-configuration NULL object panic；設定 UV_NO_SYNC=1，使用已安裝的
repo `.venv` 後可執行。沒有改 lockfile 或安裝依賴。

```sh
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export UV_OFFLINE=1 UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/odc-uv-cache
export MPLCONFIGDIR=/private/tmp/odc-mpl
uv run python tests/test_split_aware_search.py
uv run python run_regression.py --quick
uv run python scripts/research/diagnose_split_aware.py /path/to/smoke_B.json -o /private/tmp/B_trace.json
uv run python scripts/research/diagnose_split_aware.py /path/to/smoke_D.json -o /private/tmp/D_trace.json \
  --oracle-cache /private/tmp/oracle_routes.json
```

各階段 JSON、實拆結果、oracle 網格與兩份設定檔複製在 [`docs/split_aware_fix/`](split_aware_fix/)（log 與修前 optimizer 副本沒有保留）。

其中 `B_before.json`、`D_before.json`、`B_after.json`、`D_after.json` 保留了各階段完整 x，
可以直接比較精修前後每個分量，無須從文字摘要反推。
