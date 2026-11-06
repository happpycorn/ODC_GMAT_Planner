# Mac advise 計時與完全相同計算重用（2026-11-01）

功能驗收通過，三個局勢的候選、推演分數與終局逐位元相同；這台 Mac 的端到端暖機時間沒有穩定改善。已依序保存改前基準、實作決策內重用、固定 BLAS 執行緒，再用同一支腳本完成改後計時。`ODC_SCAN_REUSE` 預設開啟，設 `0` 回到逐次計算。沒有新增依賴。

本機是 **MacBook Air、Mac16,12、Apple M4、32 GB、10 核心（4 效能＋6 節能）**，macOS 27.0.1、arm64；Python 3.12.12、NumPy 2.5.0、SciPy 1.18.1、Numba 0.67.0、stable-baselines3 2.9.0。`sysctl -n hw.perflevel0.physicalcpu` 在沙盒回報 `Operation not permitted`，效能核心數由 `system_profiler SPHardwareDataType` 確認。要求的 worker 設定 `1 / 4 / 效能核心數` 因而只有 **1、4 兩個不同設定**。

`numpy.show_config()` 的 BLAS 與 LAPACK 均為 **Accelerate**。父行程在匯入 NumPy 前覆寫 `OMP_NUM_THREADS`、`OPENBLAS_NUM_THREADS`、`MKL_NUM_THREADS`、`VECLIB_MAXIMUM_THREADS`、`ACCELERATE_MAX_THREADS`、`BLIS_NUM_THREADS`、`GOTO_NUM_THREADS`、`OMP_THREAD_LIMIT` 為 `1`；rollout 與 tournament worker initializer 再各自設定。Accelerate 的實際控制採 `VECLIB_MAXIMUM_THREADS=1`，並於支援的 macOS 呼叫 `BLASSetThreading(BLAS_THREADING_SINGLE_THREADED)`；Apple 說明此 API 為每個執行緒各自設定，因此父行程與 worker 都要呼叫。[Apple API 文件](https://developer.apple.com/documentation/accelerate/blassetthreading%28_%3A%29)、本機 `/usr/share/man/man7/Accelerate.7`。

已實際擷取父行程及 **4 個不同 PID** 的 worker：上述環境變數全部為 `1`，`BLASGetThreading()` 全部回傳 `1`（單執行緒模式）。原始設定與版本見 [before_meta.json](../../reports/mac_advise_20261101/before_meta.json)；執行緒證據見 [thread_limits.json](../../reports/mac_advise_20261101/thread_limits.json)。

三個局勢重建自 [E26 的計時配方](copilot_eval.md)：`make_games` 的 seed=1、第 0 局、scenario=`mixed`，家族為 `inclined`，規則使用既有 `ranking_like.json`／`ranking_like_2burn.json`。repo 沒有留存當時的獨立 state JSON，因此這次保存引擎產生的完整笛卡兒狀態；躲者局勢先讓既有 rollout 追者完成首回合。這次沒有重新跑 GMAT 彩排。

| 局勢檔 | 我方／輪到 | 已過秒數 | 每窗口發數 | 總時限秒數 |
|---|---|---:|---:|---:|
| [pursuer_1burn.json](mac_timing_states/pursuer_1burn.json) | 追者 | 0 | 1 | 22574.292346117934 |
| [evader_1burn.json](mac_timing_states/evader_1burn.json) | 躲者 | 300 | 1 | 22574.292346117934 |
| [pursuer_2burn.json](mac_timing_states/pursuer_2burn.json) | 追者 | 0 | 2，間隔 100 秒 | 22574.292346117934 |

每次都用新的 Python 行程執行 `copilot.py advise <state> --prune --json <暫存檔>`，沿用現有全部預設大腦、對手模型及已部署 RL 模型。牆鐘包含 Python／NumPy／模型載入、JIT、worker 啟動與輸出；`--json` 只額外保存原始結果。改前未設定 BLAS 限制及 `ODC_SCAN_REUSE`，其他策略開關也未設定（strict survival 預設開、gap survival 預設關）。計時期間未同時執行測試或稽核。

「首次」各跑 **3 次**，每次使用獨立、空的 `NUMBA_CACHE_DIR`；「暖機後」也各跑 **3 次**，沿用最後一次首次執行的磁碟快取。暖機樣本仍重啟 Python 與行程池，沒有把常駐行程的時間冒充 CLI 時間；沒有磁碟快取的 JIT 仍會重做。「首次」指 Numba 快取冷啟動，沒有清除 macOS 檔案頁面快取。前後各 36 筆，以下均為三次中位數、單位秒。

| 局勢 | workers | 改前首次 | 改前暖機 | 改後首次 | 改後暖機 | 暖機耗時變化 |
|---|---:|---:|---:|---:|---:|---:|
| 追者單發 | 1 | 23.423 | 18.408 | 23.415 | 18.606 | +1.1% |
| 追者單發 | 4 | 21.585 | 17.874 | 21.295 | 19.491 | +9.0% |
| 躲者單發 | 1 | 16.633 | 11.815 | 16.661 | 11.695 | -1.0% |
| 躲者單發 | 4 | 16.975 | 11.970 | 16.990 | 12.070 | +0.8% |
| 追者 2 發 | 1 | 47.295 | 42.161 | 47.707 | 42.690 | +1.3% |
| 追者 2 發 | 4 | 31.765 | 24.778 | 31.617 | 24.672 | -0.4% |

耗時變化正值表示較慢、負值表示較快。這批資料沒有顯示端到端穩定加速：除追者單發 4 workers 約慢 9.0% 外，其餘暖機變化約在 −1.0% 至 +1.3%。追者單發 4 workers 的三筆暖機值，改前為 17.942／17.874／16.115 秒、改後為 19.491／17.732／19.530 秒，也可見約 1.8 秒的樣本波動；不能僅憑三次樣本把小幅差異歸因於特定一項修改。

原始每次耗時、完整精度 JSON、★ 與推演表文字均保存於 [before.jsonl](../../reports/mac_advise_20261101/before.jsonl) 與 [after.jsonl](../../reports/mac_advise_20261101/after.jsonl)。各次數值與中位數另見 [before_summary.json](../../reports/mac_advise_20261101/before_summary.json)、[after_summary.json](../../reports/mac_advise_20261101/after_summary.json)；環境與程式 SHA-256 另存於各階段的 `*_meta.json`，包含新增模組的最終完整程式雜湊見 [source_manifest.json](../../reports/mac_advise_20261101/source_manifest.json)。

重用的範圍是一次 `advise` 的根局勢、一次 `_candidates` 的四權重候選，以及獨立 `LambertPursuer.act`。推演到其他狀態時建立自己的短期範圍，結束立即清空；worker 啟動時清除 fork 可能繼承的範圍。鍵包含雙方位置／速度的 dtype、shape、strides、可寫性與完整位元，絕對時間、總時限、雙方燃料、mu、完整規則、回合與多發進度，以及每個純函式的所有實際參數。儲存值與回傳值以深複製隔離，保持既有可寫陣列的 Numba 型別。

逐位元驗證分兩層進行：CLI JSON／文字逐次比較，以及單行程內部完整軌跡逐筆比較。只排除 `decide_sec`、`elapsed_sec` 與執行設定 `workers`；浮點數轉成 `float.hex()` 再用 `==`，連正負零也保留。CLI 文字只去除耗時與 worker 數字。未使用 `allclose`。

**72／72 筆 CLI 結果精確相同**，涵蓋改前／改後、1／4 workers、每次重啟行程、首次／暖機；見 [cli_check.json](../../reports/mac_advise_20261101/cli_check.json)。三個局勢的 ★ 依序保持為現有 RL 追者 `models/pursuer.zip`、`lazy_evader`、`rollout_pursuer`，各大腦的原始多發計畫、推演表狀態、各模型終局與排序分數均相同。

內部稽核使用同樣的預設大腦及 `--prune`，固定 workers=1，以包裝函式保存所有 Lambert `act` 的原始向量、所有 `RolloutPlanner.evaluate` 候選向量及每個模型分數，以及 `outcome_score` 的原始分數與完整終局摘要。改前、只加入重用、再固定 BLAS 三個階段，均逐筆 `==` 相同：

| 局勢 | Lambert act 筆數 | 候選評估組數 | 內部終局筆數 | 完整軌跡 SHA-256 前綴（各階段相同） |
|---|---:|---:|---:|---|
| 追者單發 | 13798 | 234 | 700 | `e2bfbba1053accb34` |
| 躲者單發 | 4827 | 47 | 218 | `61f363f2ec82c4f7` |
| 追者 2 發 | 64754 | 668 | 1528 | `02d937231c56fd79` |

合計 **83,379 次動作、949 組候選評估、2,446 筆內部終局**。比較紀錄見 [audit_check.txt](../../reports/mac_advise_20261101/audit_check.txt)，完整雜湊與呼叫次數見 [audit_summary.json](../../reports/mac_advise_20261101/audit_summary.json)。可直接審閱的全部內部候選／分數／終局另存為 `before_rollouts.json.gz`、`step1_final_rollouts.json.gz`、`after_rollouts.json.gz`。包含所有逐動作完整狀態的較大稽核檔留在 `/tmp/odc_mac_advise_20261101/{before,step1_final,after}_audit.json.gz`，避免把約 39 MB 原始追蹤檔放入 repo。

下表是單行程完整 advise 期間，**`agents.analytic` 的 Python 呼叫點**計數；不包含 Numba 編譯函式內部呼叫 `min_intercept`／`propagate` 的次數。只加入重用與最後 BLAS 固定後的計數相同。

| 局勢 | `intercept_scan` 改前 → 改後 | `closest_approach` 改前 → 改後 | `propagate` 改前 → 改後 |
|---|---:|---:|---:|
| 追者單發 | 7537 → 7174 | 7563 → 7199 | 699 → 342 |
| 躲者單發 | 3223 → 3112 | 3225 → 3114 | 221 → 115 |
| 追者 2 發 | 21765 → 21114 | 21880 → 21222 | 1094 → 466 |

三個局勢另外各測一次預設四權重 `_candidates`：`intercept_scan` 與純滑行最近接近都從 **4 次降為 1 次**。端點捕獲的專門測試也確認，同一個 300 秒目標原本在滑行檢查、J2 目標、命中檢查各傳播一次，現在 **3 次降為 1 次**，動作位元不變。整場還有大量獨立續行決策，不會因四權重掃描共用而得到整場四倍加速。

驗收已完成：

- `tests/test_scan_reuse.py`：18 passed。涵蓋預設四權重與 advise 根局勢共用、開關、連續／端點捕獲、二體／J2、單發／2 發、時間／燃料／位置／速度／規則／mu／窗口失效、全部掃描參數、陣列改寫隔離、決策結束釋放及同目標傳播去重。
- `tests/test_runtime_threads.py`：9 passed。涵蓋四個入口於 NumPy 匯入前設定、兩種 initializer、四個實際 worker，以及 workers=1／4 與重建行程池兩次後的 ★、向量、分數、終局逐位元相同。
- `.venv/bin/python -m pytest -q`：**200 passed、12 skipped、1 failed**（24.89 秒）。基準為 173 passed、12 skipped、1 failed；新增 27 項全過。唯一失敗仍是 `tests/test_rule_map.py::test_rule_ranges_sample_unchanged[seed0-None-want0]`（436.3546929501406 與既有期望 436.3546929501402 不同），依要求保留。完整紀錄見 [pytest_final.txt](../../reports/mac_advise_20261101/pytest_final.txt)。
- `evaluation.run_tournament` 另用 2 局短局勢實跑 workers=1／4，除決策耗時欄位外的終局資料逐位元相同，見 [evaluation_smoke.json](../../reports/mac_advise_20261101/evaluation_smoke.json)。

Mac 現場建議 **`COPILOT_WORKERS=4`** 作為需要兼顧未知規則的固定設定；本機效能核心也是 4。追者 2 發暖機由 1 worker 的 42.690 秒降至 4 workers 的 24.672 秒，約為 1.73 倍速度，這是既有行程平行化的收益。若已確定單發規則，這批暖機資料的 1 worker 反而略快（追者 18.606 vs 19.491、躲者 11.695 vs 12.070 秒），可用 1；沒有證據顯示本次重用／BLAS 修改本身讓整次 `advise --prune` 更快。

與 [E26 桌機數字](../EXPERIMENTS.md) 對照時，使用同樣的 `--prune` 欄位；E26 是 16 執行緒桌機、8 workers，本機為 4 workers。

| 局勢 | E26 `--prune`（w=8） | Mac 改前暖機（w=4） | Mac 改後暖機（w=4） |
|---|---:|---:|---:|
| 追者單發 | 18 s | 17.874 s | 19.491 s |
| 躲者單發 | 14 s | 11.970 s | 12.070 s |
| 追者 2 發 | 33 s | 24.778 s | 24.672 s |

E26 是近似參考數字，沒有保存當時完整套件／硬體與同一份狀態檔，這不是控制所有變因的跨機器加速比。

**手冊第二節第 11 列建議補 Mac 專用門檻**：現場先跑一次 advise 暖機；若 T 是還要包含核對／輸入的可用秒數，標準 `--prune` 建議單發 **T ≥ 30 s**、2 發 **T ≥ 40 s**，分別留出本次暖機最慢樣本之外約 10／15 秒。這是本批資料下的保守操作建議，不是最長耗時保證。原列 25–60 秒下限在 Mac 單發追者只剩約 5 秒餘裕，且 2 發應獨立列出；首次還要多約 2–7 秒，仍應開賽前先暖機。

完整 advise 的 **60／120 秒**門檻，以及 `< 15 s` 時 `--no-rollout` 的 Mac 耗時，本次未量，不能由 `--prune` 數字下修或保證。短於建議門檻時可沿用手冊的 `--budget-sec T−5` 退路；該預算不能中斷正在執行的大腦、也不含所有程式啟動成本，並非硬超時。本次只在本報告提出修訂建議，未直接修改手冊的跨機器通用數字。

重跑方式（使用現有 `.venv`，不需 `uv sync`）：

```bash
.venv/bin/python tools/bench_advise.py --label repeat --output /tmp/mac_advise_repeat \
  --states docs/notes/mac_timing_states/pursuer_1burn.json \
           docs/notes/mac_timing_states/evader_1burn.json \
           docs/notes/mac_timing_states/pursuer_2burn.json --workers 1 4 perf
.venv/bin/python tools/bench_advise.py --compare \
  reports/mac_advise_20261101/before.jsonl reports/mac_advise_20261101/after.jsonl
.venv/bin/python tools/audit_advise.py --compare \
  /tmp/odc_mac_advise_20261101/before_audit.json.gz \
  /tmp/odc_mac_advise_20261101/step1_final_audit.json.gz \
  /tmp/odc_mac_advise_20261101/after_audit.json.gz
# 現場退回逐次計算；BLAS 單執行緒設定仍生效。
ODC_SCAN_REUSE=0 COPILOT_WORKERS=4 .venv/bin/python copilot.py advise state.json --prune
```

修改檔案與用途：

- `agents/scan_reuse.py`（新增）：決策範圍、完整鍵、副本隔離與 `ODC_SCAN_REUSE`。
- `agents/analytic.py`、`agents/rollout.py`、`copilot.py`：接上重用及入口／worker 設定。
- `runtime_threads.py`（新增）、`agents/__init__.py`、`evaluate.py`、`evaluation/__init__.py`、`evaluation/tournament.py`：匯入前與 worker 的 BLAS 固定。
- `tools/bench_advise.py`、`tools/audit_advise.py`（新增）：可重用計時與內部精確稽核。
- `tests/test_scan_reuse.py`、`tests/test_runtime_threads.py`（新增）：27 項驗證。
- 本報告、`docs/notes/mac_timing_states/` 三個 JSON、`reports/mac_advise_20261101/` 計時／精確比對／驗收資料。

未改候選清單、時間權重、對手模型、策略預設參數、`physics/`、`models/`、`checkpoints/`；`pyproject.toml` 也不需修改。未執行任何 git 寫入指令。這次量測涵蓋一個 inclined 幾何、三個狀態與本機，沒有完整 advise／`--no-rollout` 的 Mac 計時、中盤／雙曲線局勢、躲者 2 發或 GMAT 全攝動彩排；不能將三次樣本的最大值視為任意局勢的最長時間保證。沙盒也無法讀取 `pmset -g therm` 的溫控／效能警告，報告未宣稱控制了溫度或核心排程。
