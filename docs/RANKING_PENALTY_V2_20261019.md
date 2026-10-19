# 排位賽搜尋懲罰 v2：失格層（2026-10-19）

**問題：** [排位賽蒙地卡羅](RANKING_MC_20261019.md)（在分支 `claude/quizzical-raman-e1c53a`，commit `c6b4480`）發現，
Master `1cd196d` 的搜尋端懲罰擋不住「超一點點」的失格路線：

- 總 Δv 超標扣 `10 + 0.01 × 超出量`，比陡的時間項便宜。佔位參數下「快、超標 3,500 m/s @ 2,000 s」搜尋分數 62.98，
  贏過「慢、合法 2,800 m/s @ 7,000 s」的 61.92；初賽式參數（`C_v` ≈ 9 km/s）下 4,000 m/s @ 3,000 s 拿 79.94，
  贏過合法的 2,900 m/s @ 7,000 s（78.05）。搜尋會選失格的那條，最後閘門擋下，結果是**沒有可交的檔案**。
- 單棒超標固定 −10，超 1 m/s 和超 1,300 倍扣一樣多（`hyperbolic_test_fuel` 5/5 交出 ~323,800 m/s 的直接撞擊）。
- `MAX_TOTAL_DV_MPS` 是選填，現場漏抄就完全沒有總 Δv 檢查。
- C4 的可拆上限固定 5 × cap，250 m/s 下只有 1,240 m/s；拆棒器實際能拆到 14 段 × 248 = 3,472 m/s。

本次照報告「建議」1–4 點修改，並跑回歸與 sweep 驗證。

## 改了什麼

### 1. 排位賽格式必填總 Δv 上限（`src/config_validator.py`、`check_problem.py`）

`rules.MAX_DV_MPS ≤ 250`（`RANKING_MAX_DV_MPS`）但 `MAX_TOTAL_DV_MPS` 沒填或是 `null` → 驗證錯誤，`main.py` 不開跑。
`check_problem.py` 原本不跑驗證（只初始化 `MissionOptimizer`），現在開頭先跑 `validate_config`，有錯就印出來、exit 1。
`MAX_DV_MPS = 1500`（初賽）照舊不用填。

只看單棒上限、不看「A 是雙曲線」：`hyperbolic_smoke` / `hyper_far` / `hyperbolic_test` 這幾個 1500 m/s 的雙曲線測試情境
沒填總上限，用雙曲線當條件會讓它們全部驗證失敗。

### 2. 失格層（`src/scorer.py`、`src/optimizer.py`）

**排位賽模式**＝有設 `MAX_TOTAL_DV_MPS`（`MissionOptimizer.RANKING_RULES`）。這個模式下，候選分三層：

| 層 | 條件 | 搜尋分數 |
|---|---|---|
| 合法層 | 總 Δv ≤ 上限，且單棒超標只出現在終端棒、而且 ≤ 拆棒範圍 | `calculate_score`（含可拆終端棒的 −10 或 C4 拆後估計），**≥ 0** |
| 失格層 | 總 Δv 超標，或單棒超出拆棒範圍，或前導棒超標 | `−10 − 10 · v / (v + 1000)`，**落在 [−20, −10)** |
| 搜尋失敗 | 撞地球、Lambert 解不出 | **−30** |

`v` 是違規量（m/s）＝總 Δv 超出量 ＋ 終端棒超出拆棒範圍的量 ＋ 前導棒超出 `MAX_DV_SOFT` 的量。

- **數學保證：** 合法層的地板是 `calculate_score` 的 `max(…, 0)`，失格層的上界是 −10，所以任何合法候選的搜尋分數都
  嚴格高於任何失格候選，跟 `k_t / C_t / k_v / C_v` 怎麼設無關，不靠調參。
- **DE 的梯度：** 失格層對 `v` 嚴格單調下降（`v/(v+1000)` 在 323,800 m/s 時斜率 ~10⁻⁷ 分/(m/s)，float64 在 20 附近的解析度
  ~4×10⁻¹⁵，仍分得開），整群都失格時 DE 會往違規量小的方向走，不會卡在常數平台。
- **失格層只看 `v`、不看時間/燃料項**（Deb 的可行性法則）：如果失格層裡還保留時間分，DE 會停在「超一點點但很快」，
  永遠不往可行區走。
- **搜尋失敗降到 −30：** 舊值 0 在合法層的底部，但高於整個失格層。全族群都失格時，撞地球的 0 分平台反而比較高，
  DE 會往那裡跑。初賽模式仍回 0。
- **挑候選的每一層都自動套用：** 失格層直接寫在搜尋分數裡，各棒數案例（`_pick_best_case`）、REVS 集成
  （`pick_best_across_revs`）、C2 primer 重搜、C4 拆後估計都比 `score` / `score_split_est`，所以都自動排成
  「合法 > 失格」。拆棒後的 C4 退路與 seed-portfolio 原本就用 `_final_rank_key`，不變。
- **找不到合法路線時明講：** `_pick_best_case` 只收 fitness < 0（分數 > 0）的案例，失格層本來就進不去。
  排位賽模式下所有案例都在失格層時，不再輸出失格解、也不再觸發 C4 退路重搜，改走下面第 5 節的專用結束路徑。

實作上 `fast_fitness_evaluator` 多一格 scalar（索引 20 = 拆棒範圍，km/s）；Python 端的 `mission_metrics`、
`_replay_mission`、`split_est_score`、`main.legalize_violating_winner` 都改走 `MissionOptimizer.search_score`
（`_search_score_terms` 把 `assess_legality` 的結果分成「−10 次數」與「失格量」），跟 evaluator 同一套分類。

### 3. 單棒超標（同上兩檔）

- 終端棒超標、且 ≤ 拆棒範圍：維持原本的軟懲罰（C4 開時預付拆棒燃料、關時 −10），讓 DE 繼續探索可拆的大棒。
- 終端棒超過拆棒範圍：進失格層，違規量 = 超過範圍的部分，超越多分數越低。
- 前導棒超標：拆棒器（`legalize_route`）只拆終端棒，前導棒超標拆不掉，進失格層。正常參數化下前導棒被 bounds 夾在
  `MAX_DV_SOFT` 以內，不會發生（`SPLIT_AWARE_SEARCH` 開時例外，見「限制」）。
- `AUTO_SPLIT_LEGALIZE` 關：不會拆棒，任何超標都拆不掉，拆棒範圍 = `MAX_DV_SOFT`。

### 4. C4 可拆倍數由拆棒器推出（`src/optimizer.py`）

`SPLITTER_MAX_SEG` 直接讀 `burn_splitter.legalize_route` 的 `max_seg` 預設值（14；`main.legalize_violating_winner`
就是用預設值呼叫），排位賽模式下 `SPLIT_AWARE_TERMINAL_MAX_FACTOR` 預設 = 14，拆棒範圍 = 14 × `MAX_DV_SOFT`
（250 m/s 時 3,472 m/s）。拆棒器改段數上限時，搜尋端自動跟著變。config 有寫 `SPLIT_AWARE_TERMINAL_MAX_FACTOR` 就照 config。

**初賽模式維持 5 倍。** 1500 m/s 下 14 倍是 21 km/s，DE 族群裡會有不少終端棒落在 7.5–21 km/s 的候選，改掉就會改變
contest 的搜尋軌跡，違反「初賽分數逐位元不變」。5 倍是 E1–E4 在 1500 m/s 下定的經驗值，初賽情境不需要動它。

### 5. 找不到合法路線的結束路徑（`main.py`、`src/optimizer.py`）

比賽當天「沒有合法解」跟「程式壞了」要分得出來，而且要留得下東西給人看：

- `_pick_best_case` 記下最接近合法的失格候選（失格層分數最高 = 違規量最小）到 `optimizer.no_legal_route`；
  REVS 集成、seed-portfolio 都把違規最小的那個往上傳（`_search_stage` / `_solve_pipeline` 失敗時改回傳 optimizer，
  不是 `None`）。
- `main.py` 把它重播後存成本次 run 目錄的 **`no_legal_route.json`**：config、各棒 VNB、時刻、mission_info，加上
  `violations`（每棒 Δv、哪幾棒超過 250 m/s 多少、是否在拆棒範圍內、總 Δv 與超出量、失格原因、搜尋分數）和
  `next_steps`。`stage = "no_legal_route"`，`--from-mission` 讀不進去，所以**不會產生任何腳本**（固定燃燒或一般版都不會），
  也沒有 `mission.json`。
- 結束訊息明講「找不到合法路線」，逐棒列違規量，並給下一步：加大 `MAXITER` / `POPSIZE`、多跑種子、放寬 `MAX_BURNS`、
  用 `check_problem.py` 核對 `T_MAX_SEC` 與計分參數、用 `feasibility.py` 看 Δv 下限。
- 拋 `NoLegalRouteError`，`run.json` 的 `status = "no_legal_route"`，**結束碼 3**（`EXIT_NO_LEGAL_ROUTE`；一般錯誤仍是 1）。
- 沒有失格候選的一般搜尋失敗（例如全部撞地球、初賽模式）照舊是通用的「求解失敗」RuntimeError。

## 驗證

### 單元測試

- `tests/test_ranking_penalty_v2.py`（新）：
  - 隨機 20,000 組計分參數：最差合法 0.0000 > 最好失格 −10.0000；失格層對總 Δv 與單棒超出量嚴格單調。
  - 報告的兩個反例：舊算法分別給 62.98 > 61.92、79.94 > 78.05（選超標），v2 給 61.92 > −13.33、78.05 > −15.00（選合法）。
  - 單棒分類、`AUTO_SPLIT_LEGALIZE` 關、K 的推導（排位賽 14、初賽 5、config 覆寫）。
  - evaluator：contest 拆棒前存檔在 cap 250 下終端 4,691 m/s > 3,472 → 失格層；總 Δv 6,200 → 失格層；兩者都超分數更低；
    逆向燒滑過近地點撞地球 → −30（初賽模式 0）。
  - validator：250 沒填 / `null` → 擋；100 也擋；1500 不擋。
  - 找不到合法路線：`_pick_best_case` 記下候選、`no_legal_route.json` 的違規量與下一步、`load_mission` 拒讀、
    `main()` 拋 `NoLegalRouteError`、`run.json` 狀態、run 目錄沒有 `mission.json` 或腳本；一般失敗仍是 RuntimeError。
- `tests/test_no_legal_route_e2e.py`（新，SLOW）：子行程真的跑一次 `main.py`（`hyperbolic_test` 幾何、總 Δv 上限 300 m/s，
  低於能量下限 697 m/s），結束碼 3、沒有 traceback、log 有「找不到合法路線」與建議、run 目錄只有
  `no_legal_route.json` / `run.json` / `run.log`。17.6 s。
- `tests/test_ranking_rules.py`：總 Δv 軟懲罰的檢查改成失格層；新增「21 格 scalars 跟 20 格 / 19 格逐位元相同」。
- `tests/test_split_aware_terminal.py`：scalars 長度 20 → 21；初賽模式 K = 5。

### 回歸與初賽逐位元

- 失格層與 K 推導那個 commit（`f9bb816`）：quick 12/12（108.7 s）、完整 16/16（350.7 s），2026-10-19 23:32–23:40，
  開跑前確認沒有其他 worktree 的 python 長工作。
- 找不到合法路線那個 commit（`4fc8256`）之後重跑：quick 12/12（100.2 s）、完整 **17/17**（372.9 s，多了
  `test_no_legal_route_e2e.py` 16.1 s），2026-10-20 00:21–00:29。
- **contest replay**（[`sweeps/revs_unified_v1.json`](../sweeps/revs_unified_v1.json)：contest、SEED 0、600×20、
  `MAX_BURNS=[1,2,3]`、完整拆棒管線、`--slots 1`、sweep 暖身後讀快取）：

  | 程式 | 執行位置 | 拆後分數 | 棒數 | 拆前贏家總 Δv（m/s） |
  |---|---|---|---|---|
  | 本分支 `f9bb816` | 本 worktree | **98.31908070668248** | 6 | 6,189.372620917897 |
  | Master `6d2f134` | 全新 worktree（暖身冷編 → 讀快取） | 98.31907096892051 | 7 | 6,189.37260871791 |
  | 本分支 `4fc8256` | 同一個全新 worktree（同流程） | 98.31907096892051 | 7 | 6,189.37260871791 |

  **同一個 worktree、同一套快取流程下，本分支與 Master 逐位元相同**（拆後分數、棒數、拆前贏家全部一樣），
  所以初賽情境的分數沒有被這次修改動到。本 worktree 的結果 98.31908070668248 印到小數 5 位就是 98.31908；它跟全新
  worktree 的 98.31907096892051 不一樣，差異來自 worktree 之間的 numba 快取 / 編譯狀態，不是程式碼：
  - 另外直接比 `fast_fitness_evaluator`：contest config、1–4 棒、12,000 組隨機決策向量，Master 與本分支回傳值
    **0 筆不同**（逐位元比 `float.hex`）。
  - 拆前贏家的總 Δv 在 10⁻⁸ m/s 就分岔，L-SHADE 對 1 ulp 敏感（見記憶 numba-cache-state-breaks-seed-repro：
    冷編與讀快取會差 1 ulp）。這次兩邊 sweep 的 run 本身都沒有冷編（`numba_cache_written` 都是空的），
    差別在快取是哪個行程、什麼時候編出來的，根因這次沒有追。
  - 結論：要拿 98.31908 當逐位元基準，必須在同一個 worktree、同一個快取狀態下 before/after 對照；
    跨 worktree 只能比到小數 4 位（98.3191）。

### sweep：[`sweeps/ranking_mc_v2_penalty.json`](../sweeps/ranking_mc_v2_penalty.json)

`hyperbolic_test_fuel`（[ranking_mc_v1](RANKING_MC_20261019.md) 裡 5/5 交出失格解）與 `hyperbolic_smoke`（對照）×
SEED 0–2，全部 `MAX_DV_MPS=250`、`MAX_TOTAL_DV_MPS=3000`、600×20、`--slots 1`。程式 `f9bb816`，
2026-10-19 23:47–10-20 00:04，機器上沒有其他 python 長工作。原始結果在本機 `outputs/sweeps/ranking_mc_v2_penalty/`（不進版控）。

| | `hyperbolic_test_fuel` s0 / s1 / s2 | `hyperbolic_smoke` s0 / s1 / s2 |
|---|---|---|
| 結果 | **找不到合法路線** ×3（明確回報，不交檔） | 合法 ×3 |
| 分數 | — | 86.7829 / 86.7835 / 86.7820 |
| 棒數、總 Δv | 最接近合法：2 棒、3,824 m/s、T 8,000 s（三顆一樣） | 4 棒、639.6 / 639.6 / 639.8 m/s |
| 牆鐘（s） | 77 / 76 / 76 | 162 / 225 / 362 |
| v1（`d5afcff`，沒設總上限）同種子 | 65.00 失格 ×3（~323,800 m/s、T 200 s），99–101 s | 85.2033 / 86.7845 / 86.7839 |

- **`hyperbolic_test_fuel`：** 搜尋不再停在「T = 200 s、32 萬 m/s」的直接撞擊，最接近合法的候選縮到 3,824 m/s
  （超 824 m/s），抵達時刻是 T_max（失格層只看違規量，DE 會犧牲時間去省油）。仍然在失格層，所以照設計明確回報
  「找不到合法路線」，不交失格解、也不跑 C4 退路重搜（牆鐘 76–77 s；v1 是 99–101 s，當時多跑一次退路重搜，
  但兩版中間還有別的改動，不當成加速量測）。
  `feasibility.py`（同 config）：T_max 內最便宜的**單棒**轉移就要 3,496.7 m/s（> 3,000），能量下限 697 m/s；
  這組佔位幾何在 T_max = 8,000 s 內很可能根本沒有總 Δv ≤ 3 km/s 的路線（多棒沒有證明）。注意 3,824 比單棒的 3,497 還貴：
  `hyperbolic_test` 的 `MAX_BURNS=[2,3]` 沒有 1 棒，失格層裡 DE 也沒把前導棒壓到 0——失格層只保證排序與單調，
  不保證找到最小違規量。
- **`hyperbolic_smoke`：** 3/3 合法，三顆都落在 v1 的高群（~86.78），SEED 0 從 v1 的 85.20 升到 86.78；
  SEED 1/2 比 v1 少 0.0010–0.0019 分（拆棒雜訊級）。v1 是 `d5afcff`、沒設總上限，中間還隔了 `1cd196d` 的改動，
  這不是乾淨的 A/B，只說明 v2 在可行情境下沒有變差。
- 找不到合法路線時 sweep 記成 `error`（`main.py` 非 0 結束）。這次跑的是 `f9bb816`，當時還是通用的「求解失敗」；
  `4fc8256` 起改成結束碼 3 與 `no_legal_route.json`（見第 5 節）。

## 限制與後續

- `SPLIT_AWARE_SEARCH`（中間棒拆棒感知，預設關）開啟時，evaluator 對超標中間棒是預付拆棒代價、算合法層；Python 端
  的 `_search_score_terms` 照拆棒器的實際能力把前導棒超標算進失格層，兩邊不一致。這個旗標預設關、拆棒器也還不拆前導棒，
  要開之前得先讓拆棒器支援前導棒。
- 失格層用的 `total_dv` 含 C4 / `SPLIT_AWARE_SEARCH` 的燃料預付（預設 C4 overhead = 1.0，不影響）。總 Δv 貼近 3,000 m/s
  的路線，拆棒後的重力損失可能讓實際總量超過上限；最終判定仍由 `assess_legality` 把關。
- evaluator 的總 Δv 用二體 Lambert 的終端棒，重播用 J2 修正後的值，兩者可能差幾 m/s；貼著上限的候選可能在搜尋端合法、
  重播後失格（此時它在 `mission_metrics` 會被排到失格層，挑贏家時排在合法候選後面）。
