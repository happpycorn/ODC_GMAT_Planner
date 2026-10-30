固定軌道星曆快取完成紀錄（2026-10-28）

已實作 A 全程、B 第一棒前的檢查點快取，預設啟用。查詢只從不晚於目標時刻的檢查點呼叫原本的 `propagate_dop853` 補積分，沒有插值。`propagate_dop853` 的函式內容、容差、scorer、GMAT 腳本產生器及指定禁止修改的文件均未改動；沒有 commit。完整回歸為 16/22 通過，未通過項目列在下方。

修改檔案與呼叫端：

| 檔案 | 變更 |
|---|---|
| `src/core_math.py` | 新增 `ephem_state`、逐段建表的 `build_ephem_table`、Python 共用入口 `fixed_orbit_state`。檢查點及相鄰浮點時刻、負時間、表外時間都有測試；回傳陣列不會與表共用可修改內容。 |
| `src/optimizer.py` | 建構時各建一張 A/B 表；fitness 的 B 初始等待與 A 攔截點、單棒粗／細掃、ladder 與 plane-change 種子、`reconstruct_mission_logs` 及兩個重播入口均接入。統一 vectors 打包，涵蓋 wrapper、細搜及 unified multiprocessing 排程。新增 `state_A/B`。 |
| `src/burn_splitter.py` | `_simulate_free`、`_simulate_free_reuse` 的 A/B 固定軌道，以及 `_terminal_state`、`_legalize_route_core`、`_retarget_last` 的 B 初始等待改用快取。`legalize_route`、joint NLP、FD worker context、多起點、prune/reopt 與重評一路傳遞 `ephem`。 |
| `src/config_validator.py` | 驗證 `strategy.EPHEM_CACHE` 為 bool，`EPHEM_CACHE_STEP_SEC` 為有限正數。 |
| `main.py` | 預設設定增加兩個欄位；primer 診斷、拆棒 route 解碼的 A/B 狀態、拆後剔棒與重播均傳遞／查詢快取。 |
| `feasibility.py` | 單棒掃描、多棒存在性探測的 A/B 固定軌道改用 optimizer 查詢。 |
| `scripts/research/porkchop_grid.py` | 網格星曆接收 optimizer 已建立的表；不重建表。未傳表時保留原路徑。 |
| `scripts/research/porkchop_oracle_sweep.py` | A/B 網格查詢傳入各自的表。 |
| `scripts/research/porkchop_verify.py` | 固定軌道重播改用 `state_A/B`。 |
| `scripts/research/porkchop_verify_flagged.py` | 網格與固定軌道重播均傳入快取。 |
| `scripts/research/probe_hyperbolic_A.py` | 展示傳播與 Lambert 掃描各先建表再查詢。 |
| `scripts/research/sweep_hyperbolic_limits.py` | 每個獨立二體 Lambert 掃描各建一次 A/B 表。 |
| `scripts/research/hap47_poc_nlp_split.py` | 使用符合該 PoC 重力設定的 optimizer 建表，經 scipy args 傳至模擬與約束。 |
| `scripts/research/hap47_poc_gmat_verify.py` | 接收前述表，供第一棒前狀態查詢；腳本產生器未改。 |
| `tests/test_ephem_cache.py` | 新增精度、fitness、舊參數佈局、關閉退路、spawn、FD context、自訂間距、設定驗證及速度測試。 |
| `tests/test_split_aware_terminal.py` | 只把結構性長度檢查由 21 格更新為 23 格；數值完全相等的斷言保留。 |
| `docs/research/EPHEM_CACHE_20261028.md` | 本完成紀錄。 |

刻意維持直接傳播的部分：所有燃燒後的滑行、Lambert shooting／有限差分、Earth-safe 弧傳播，因為狀態依賴決策變數；獨立精度基準（兩支 hyperbolic 研究腳本的 `prop_accuracy`、`src/tmax.py` 的數值邊界驗證及既有傳播器測試），因為這些是在檢查傳播器本身；另外保留所有停用快取、舊呼叫端未提供表及表外查詢的退路。使用者提供的 `/private/tmp/.../bench_fitness.py` 沒有修改。

`fast_fitness_evaluator(x, num_burns, scalars, vectors)` 的 Numba 簽名維持原樣。`scalars[0:21]` 與 vectors 前四列的意義不變；新增索引 21 為間距（0 表示停用）、22 為檢查點數 n。後面依序附 A、B 表，各佔 2n 列，每個檢查點以 r/v 兩列、每列三欄存放。這避免查詢時複製或 reshape 整張表。既有只傳四列的呼叫端會安全退回直接積分；暫時替換 optimizer 初始狀態的旋轉測試也走該退路。

預設間距 60 秒。範圍依現有拆棒器的實際試探邊界推導：原始最大棒數 b 的前導棒補空位後最多 2(b−1) 棒，終端最多 14 段；N 棒 NLP 的 t0 與每段 coast 各自可達 T_max，因此上界是 `(2(b−1)+14+1)*T_max`，另加一步餘裕，並涵蓋一般搜尋被迫加入最短 coast 的情況。兩個驗收場景分別建至至少 3,088,890 秒、680,060 秒。表跟著 optimizer、vectors 或顯式 worker context 傳遞，spawn 測試已驗證；沒有新增只存在父行程的全域星曆表。

精度測試對每個場景、每個天體各抽 500 個 [0,T_max] 隨機時刻，另各抽 16 個延伸至建表末點的 NLP 試探時刻。單位已由 km／km/s 換成 m／m/s。

| 場景 | 任務範圍最大位置差 | 任務範圍最大速度差 | 含延伸試探最大位置差 | 含延伸試探最大速度差 |
|---|---:|---:|---:|---:|
| hyper_far + splitspeed_par3_rec base | 0.00369375812 m | 1.07028993e-7 m/s | 0.186575748 m | 2.01732772e-4 m/s |
| ranking_round | 0.00180006909 m | 1.27799632e-7 m/s | 0.0335970323 m | 8.17128783e-6 m/s |

每個場景另對 1／2／3 棒各抽 500 個決策向量。完成兩組不同亂數樣本（一般回歸與改動前基準樣本），各組皆通過絕對差 <1e-6 或相對差 <1e-9。所有實測樣本的 fitness 最大絕對差為 hyper_far 1.02117781e-9、ranking_round 3.07561265e-9；最大相對差分別為 2.55259189e-11、7.63137675e-11。

關閉快取時，在相同 Numba 編譯狀態下與改動前保存的未修改 optimizer 原始碼逐位元相同：兩個場景、各 1／2／3 棒、每類 500 筆，共 3,000 筆。兩種 splitter 模擬也各對照未修改原始碼，共 80 次，結果逐位元相同。原程式自身在 Numba 冷編譯與讀編譯快取時會出現最高 3.55271368e-15 分的差異；此差異也能在未修改原始碼重現，故原始碼對照使用相同編譯狀態，沒有放寬逐位元判定。

速度數字是相同 500 筆 x、先暖機、交替開關各跑三輪，取每輪每次評估平均值的中位數。下表取獨立基準對照那一趟；建表時間不含首次 Numba JIT。

| 場景 | 棒數 | 關閉 ms/次 | 啟用 ms/次 | 加速 |
|---|---:|---:|---:|---:|
| hyper_far | 1 | 3.568486 | 0.013551 | 263.3× |
| hyper_far | 2 | 5.158974 | 1.553143 | 3.32× |
| hyper_far | 3 | 5.967558 | 2.478028 | 2.41× |
| ranking_round | 1 | 1.180196 | 0.014238 | 82.9× |
| ranking_round | 2 | 1.612477 | 0.389950 | 4.14× |
| ranking_round | 3 | 1.816235 | 0.624158 | 2.91× |

建表：hyper_far 0.494948 秒，ranking_round 0.111660 秒。拆棒器 `_simulate_free_reuse` 另以 500 個隨機初始等待、兩棒小推力、200／400 秒滑行測三輪：hyper_far 3.679006 → 0.135961 ms/次（27.1×），ranking_round 1.223744 → 0.136918 ms/次（8.94×）。這是軌跡模擬成本，沒有把它當作整趟 SLSQP 加速倍數。

完整回歸實際執行：

```sh
UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/odc-uv-cache \
MPLCONFIGDIR=/private/tmp/odc-mpl PYTHONUNBUFFERED=1 \
uv run python run_regression.py
```

原本的 uv 同步步驟在此 sandbox 會因 macOS system-configuration panic 失敗，因此使用既有虛擬環境、停用同步。最終 16/22 支通過，耗時 288.4 秒；新增的 `test_ephem_cache.py` 通過，耗時 68.4 秒。未通過項目如下，未修改其數值門檻：

| 測試 | 結果／差值 |
|---|---|
| `test_ranking_rules.py` | 快取開啟的 mission_metrics 分數 88.32193207922883；直接積分舊算法 88.32193207922312；差 +5.7127635955112055e-12，完全相等斷言失敗。 |
| `test_split_aware_terminal.py` | 舊 16 格參數 fitness −88.32193207922312；預設快取 wrapper −88.32193207922883；差 −5.7127635955112055e-12，完全相等斷言失敗。該測試的「旗標關」指 SPLIT_AWARE_TERMINAL，未關閉新加的 EPHEM_CACHE。 |
| `test_hyperbolic_e2e.py` | sandbox 禁止 multiprocessing.Manager listener 綁定 socket，PermissionError，後續 EOFError。 |
| `test_no_legal_route_e2e.py` | 同一個 Manager socket 權限問題，尚未進到待測的任務結果處理。 |
| `test_retarget_gmat_e2e.py` | GMAT Mission run failed／DC 未收斂，輸出含 GMAT log 路徑不可寫錯誤，之後測試讀取不存在的 legality 失敗。另以 EPHEM_CACHE=false 重跑，重現相同失敗；不是快取開關造成的結果差異。 |
| `test_revs_schedule.py` | 使用者已註明的 macOS spawn 問題，仍失敗。 |

另以小網格檢查 porkchop 快取／直接路徑，以及 hyperbolic Lambert scan；以 warm start、模擬、約束與第一棒前重播檢查兩支 HAP47 PoC，均通過。研究掃描未跑完整的大型網格或完整 PoC 優化。

尚待外部環境驗證的部分：能綁定 Manager socket、能正常執行 GMAT 的環境下，重跑上述端到端測試與整趟 600 秒拆棒預算實驗。快取開啟後的極小軌道差異可能改變 SLSQP 的有限差分與局部收斂路徑，因此不宣稱優化結果逐位元不變；只有關閉快取的退路做此保證。建表成本與任務長度、設定最大棒數成正比；外部呼叫若自行提高 max_seg／棒數超過建表時設定，表外查詢仍安全退回直接積分，但失去該次查詢的加速。

原始測試輸出與改動前基準保存在 `/private/tmp/odc-ephem-baseline/`：`test-final.log`（原始碼逐位元對照與獨立計時）、`regression-final.log`、`diagnostics.log`、`split-speed.log`、`research.log`、`poc.log`、`gmat-off.log`，以及 `optimizer_before.py`、`burn_splitter_before.py`、兩個場景的基準 npz。此目錄是暫存驗證材料，不屬於程式執行依賴。
