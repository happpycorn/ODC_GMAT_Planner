# C4：搜尋改用「拆後估計分數」——終端棒可拆時不扣 10 分

**狀態：計畫（2026-09-24 撰）。尚未動碼。預定在遠端機執行（需跑數小時搜尋）。**
上游：[C3_CONVEX_SPLITTER_PLAN.md](C3_CONVEX_SPLITTER_PLAN.md) §6、STATUS 待辦第 0 項。

本文件回答：**問題是什麼 / 為什麼要改 / 改什麼 / 怎麼驗證 / 風險與退路 / 時程**。

---

## 1. 問題

拆棒管線（HAP-67 + C3）已經能把「終端棒超標」的違規解，以約 **0.003 分**的代價拆成合法解。但搜尋的
目標函數還不知道這件事：

- `optimizer.fast_fitness_evaluator` 對**終端棒**超標一律 `penalty_count += 1`（−10 分，
  [optimizer.py ~L224](../src/optimizer.py)）。
- 挑贏家的各階段也都用扣過罰分的真實分數比：`_pick_best_case`（~L1906）、`pick_best_across_revs`
  （~L2186，經 `_mission_rank_key` → `tiebreak_rank_key`）、C2 `primer_guided_research` 的新舊比較。

所以搜尋拿**錯的尺**在比家族（contest 幾何實測）：

| 家族 | 搜尋看到的 | 拆後真實可拿 | 內容 |
|---|---|---|---|
| 88.32（早到、多燒油） | **88.32**（含 −10） | **98.32** | T 5,677 s、Δv 6,182 m/s、終端 4,691 m/s 超標 |
| 89.25（省油、晚到） | **89.25** ← 搜尋偏好這個 | 89.25 | T 6,430 s、Δv 4,480 m/s、全合法；時間分只 14.36 |

已觀察到的後果：強制 4 棒搜尋（C3 §6）SEED 4 收斂在 89.25；多數 SEED 停在「2 次違規 78.x」這種被
罰分扭曲的區域。預設 `MAX_BURNS=[1,2,3]` 目前沒出事，**只是剛好沒有案例找到 89.25 家族**——換一個
幾何、或加 4 棒，挑贏家就會選錯，最後交出 89 分級的解。

現有 `SPLIT_AWARE_SEARCH` 只處理**中間棒**超標（改預付時間 + `SPLIT_AWARE_DV_OVERHEAD`），終端棒沒處理。

## 2. 改什麼

### 2.1 DE 目標函數（`fast_fitness_evaluator`）

新旗標 `strategy.SPLIT_AWARE_TERMINAL`（**`AUTO_SPLIT_LEGALIZE` 開時預設開**——拆棒本來就會發生，
搜尋應該用同一把尺）。開啟時，終端棒超標且 `dv_final ≤ K × cap`：

- **不計 penalty**，改預付拆棒成本：`total_dv += dv_final × (TERMINAL_DV_OVERHEAD − 1)`。
  - 實測拆前總 Δv 6,189 → 拆後 6,180～6,190，幾乎不增 → `SPLIT_AWARE_TERMINAL_DV_OVERHEAD` 預設 **1.00**（可調）。
  - **不加時間**：拆棒器鎖定 A(T)，抵達時刻不變。
- 超過 `K × cap` 仍照舊扣 10 分。`SPLIT_AWARE_TERMINAL_MAX_FACTOR` 預設 **5**（contest 是 3.13×；
  拆棒器 `max_seg=14` 是理論上限，但段數多時 greedy 暖啟與 Earth-safe 越難保證）。
- 實作：`scalars` 陣列加索引 16/17/18（旗標、K、overhead），既有索引不動；**三處組 scalars 的地方要同步**
  （`optimizer.py` ~L1601、~L1736、~L1827）。`fast_fitness_evaluator` 是 `cache=True`，改簽名後快取自動失效。
- 報表（`_replay_mission` / 任務規劃）照舊顯示「違規次數 1」——那是拆前的事實；另加一行「拆後估計」。

### 2.2 挑贏家換尺

`mission_info` 新增欄位 `score_split_est` = 真實分數 + 10 ×（可拆的終端違規數）− 預付成本。旗標開時：

- `_pick_best_case`：用 `score_split_est` 分桶比較（目前用 `metrics[b]["score"]`）。
- `pick_best_across_revs` / `_mission_rank_key`：rank key 的 score 換成 `score_split_est`。
- C2 `primer_guided_research` 新舊比較、seed-portfolio：同上（portfolio 已經是比拆後真實分數，不用改）。
- **只有 Earth-safe 的候選**可以用拆後估計（撞地球的本來就不拆，見 HAP-48 閘門）。

### 2.3 退路：估計會落空時

`score_split_est` 只是估計，真正拆可能失敗（段數上限內拆不出、拆後弧段不 Earth-safe）。目前
`_solve_pipeline` 拆失敗就沿用違規解交出去（−10）。改為：**保留「最佳合法候選」當備胎**（各棒數案例
裡真實分數最高且零違規者），拆失敗時改交備胎，並大聲 log。

## 3. 驗證計畫（遠端機）

所有對照前 pin BLAS：`OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1`
（memory odc-blas-nondeterminism；另注意 numba 冷/熱快取，見 C3 §6——已修，但改 optimizer.py 後第一次跑仍會重編譯）。
`configs/` 不在 git：contest（SCENARIOS.md `contest` 節，2026-09-24 補）等設定照 [SCENARIOS.md](SCENARIOS.md) 重建，GMAT 路徑填 `local.gmat_console_path`。

| # | 實驗 | 改前（已知） | 通過條件 | 估時 |
|---|---|---|---|---|
| E0 | 回歸 `run_regression.py` | 9/9 | 9/9 + 新測試 | 3 分 |
| E1 | contest 預設管線 SEED 0（`MAX_BURNS [1,2,3]`、REVS 關） | 98.3188 GMAT ✅ | **≥ 98.318**、GMAT ✅ | 30 分 |
| E2 | 強制 4 棒 SEED 0–8（MAXITER 200、SPLIT_AWARE 開、C2 關；3 顆平行） | 89.25 / 78.x / 98.26～98.32 混雜 | **不再收在 89.25 / 78.x**；多數 ≥ 98.31 | 40 分 |
| E3 | contest `MAX_BURNS [1,2,3,4]`（驗「挑贏家換尺」） | 未測（風險：可能挑到 89.25） | 贏家是 98.3 級、非 89.25 | 40 分 |
| E4 | 雙曲線：`hyperbolic_test`、`hyperbolic_smoke`、`hyper_far`（SCENARIOS.md） | 各自既有分數 | 不低於改前；違規解能拆合法；GMAT ✅ | 60 分 |
| E5 | 合法解本來就最優的情境（`official_sample`、`playground`，SCENARIOS.md） | 各自既有分數 | **完全不變**（沒有超標終端棒時旗標不該有任何作用） | 20 分 |

E1–E5 各自記「改前 / 改後」分數、棒數、牆鐘；E2/E3 另記每個候選的 `score` 與 `score_split_est`。
改前數字若沒有現成的，用旗標關（`SPLIT_AWARE_TERMINAL=false`）跑同一設定當對照——同一份程式碼、只差旗標。

新增測試（`tests/`）：
- 目標函數單元測試：同一個終端超標決策向量，旗標開/關的分數差 = 10 − 預付成本；超過 K×cap 仍扣。
- `pick_best_across_revs` / `_pick_best_case`：餵假 mission_info（違規 88.32 vs 合法 89.25），旗標開選前者、關選後者。
- 退路：拆棒失敗時交出最佳合法候選。

## 4. 風險

- **估計與真實拆後分數的落差**：預付成本 1.00 是 contest 單一幾何的實測。雙曲線或換面更大的幾何，拆棒可能真的
  貴（多段、Earth-safe 繞路）。E4 要特別看「估計 vs 實拆」差多少；差太多就把 overhead 調高或改成依超標倍數分段。
- **搜尋被拉進「拆不出來」的區域**：旗標讓大超標終端棒變得很有吸引力，DE 可能偏好 4～5× cap 的極端解，結果拆
  棒失敗。靠 K 上限 + 2.3 退路擋；E2/E4 記錄拆棒失敗率。
- **種子家族的交互**：pcsplit / split_even 種子原本是為了在搜尋端就產出「已拆好」的解；旗標開後它們的價值可能下降
  （STATUS 已註記「疑似冗餘但別急著移除」）。本計畫不動它們，只記錄贏家來自哪個種子家族。
- **行為改變面大**：這是核心目標函數的改動。旗標關時必須逐位元等同舊行為（E0 的舊測試 + 一個「旗標關 = 舊分數」的斷言）。

## 5. 時程與分段

1. **實作**（本機即可，~1–2 小時）：2.1 → 2.2 → 2.3 + 新測試，E0 通過就 commit（旗標**先預設關**）。
2. **驗證**（遠端機，~3 小時 CPU）：E1–E5，旗標開/關各跑。
3. **決定預設**：E1–E5 全過 → 翻成「`AUTO_SPLIT_LEGALIZE` 開時預設開」、更新 STATUS/README；
   任一項退步 → 保持預設關、把數據寫進本文件 §6 再討論。

## 6. 結果

（待填）
