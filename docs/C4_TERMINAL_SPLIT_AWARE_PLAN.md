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

## 6. 結果（2026-09-24，遠端機，commit `a4b4bec`）

**結論：E4 `hyper_far` 退步 −9.6 分 → 依 §5 保持預設關。** 二體情境（contest 系列、`hyperbolic_test`）全部
通過且 E2 大幅改善；失敗集中在 J2–J4 攝動 + 長終端段，根因是拆棒器、不是目標函數本身（見 6.2）。

設定：`configs/c4/*.json`（可由版控中的 `sweeps/c4_v1.json` 與 `configs/shared/` 重建；旗標開/關各一份、同一份程式碼、E2 含 SEED 0–8，其餘為 SEED 0，BLAS 由 `run_study` 依 SEED 自動 pin）。
輸出與彙整：`outputs/c4/`（`scripts/c4_runner.py` 可續跑排程、`scripts/c4_summary.py` 彙整表；用法見 [實驗腳本](../scripts/README.md)）。C4 runner 使用 Linux `/proc`，需在 Linux 執行。表中「拆後」= 拆棒 + 剔除空燒後
的最終分數；GMAT 欄為一般版(DC)/固定燃燒版。

### 6.1 各實驗

| # | 情境 | 旗標關 | 旗標開 | 判定 |
|---|---|---|---|---|
| E0 | 回歸 | 10/10 + 新測試 23 項 | — | ✅ |
| E1 | contest `[1,2,3]` | 拆前 88.3219 → **98.3191**（6 棒）GMAT ✅✅ | 88.3219 → **98.3191**（7 棒）GMAT ✅✅ | ✅ |
| E2 | 強制 4 棒 SEED 0–8 | 見下表：min 82.27、2/9 < 98 | 見下表：**9/9 ∈ [98.3162, 98.3192]** | ✅ |
| E3 | contest `[1,2,3,4]` | 各案例 84.90/88.32/88.32/88.32 → 採 4 棒 → **98.3191** | 94.90/98.32/98.32/98.32 → 採 3 棒 → **98.3190** | ✅（SEED 0 旗標關也沒掉進 89.25，本實驗沒重現原問題） |
| E4 | `hyperbolic_test`（二體） | 87.5616 → **97.1261**（5 棒）✅✅ | 同左，逐項相同 | ✅ |
| E4 | `hyperbolic_smoke`（J2–J4） | **86.7854**（合法 2 棒）✅✅ | **86.7858**（合法 3 棒）✅✅ | ✅ |
| E4 | `hyper_far`（J2–J4） | **82.2953**（合法 4 棒）✅✅ | 72.6870 **拆不出、帶 1 次違規交出** ❌❌ | ❌ **−9.61** |
| E5 | `official_sample` | 90.4410（3 棒）✅✅ | 90.4412（3 棒）✅✅ | ⚠️ 分數未退步，但**非逐位元相同**（1 棒案例目標 80.40→90.40 改變了搜尋路徑） |
| E5 | `playground` | 90.6692（1 棒）✅✅ | 90.6692（2 棒）✅✅ | ⚠️ 同分，1/2 棒平手的 tie-break 選到不同棒數，輸出檔不同 |

E2 逐 SEED（最終拆後分數；括號 = 拆前真實分數）：

| SEED | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|---|
| 關 | 98.0190 (72.43) | **82.2683** (82.27，留 1 違規) | 98.3174 | 98.3190 | **89.2523** (89.25 家族) | 98.3186 | 98.3190 | 98.3175 | 98.3176 |
| 開 | 98.3191 | 98.3176 | 98.3188 | 98.3192 | 98.3162 | 98.3180 | 98.3168 | 98.3190 | 98.3188 |

旗標開時 DE 目標值在第一輪就到 98.0～98.3（關：88.0～90.8）；SEED 4 不再收在 89.25、SEED 1 不再留違規。
關的中位數 98.3175 / 開 98.3188。

### 6.2 E4 `hyper_far` 失敗根因（已用 `--from-winner` 重播 + 診斷腳本確認）

- 開旗標時贏家是 2 棒解（第 2 棒空燒），終端棒 1,758 m/s = **1.17× cap**，終端段長 **30,256 s（~8.4 h）**，
  搜尋估「可拆」→ 拆後估計 82.69，比合法解 82.30 高，所以被選中。
- 貪婪拆棒器 `split_intercept` 的最後一段用**二體 Lambert** 瞄準，再用 **J2–J4** 傳播驗命中（`miss_tol` 3.5 km）。
  8.4 h 後攝動讓它偏 **338～377 km**（nseg 2～5 全部），全被拒；同一個起點改二體傳播，nseg 2～5 **全部 miss 0.0 km**。
  貪婪版是 joint NLP 的入口（N-finder / warm start），它失敗 joint NLP 根本不會跑。
- 不拆的單棒解之所以能交：GMAT DC 會在 J2–J4 下修終端棒。拆棒器沒有這一步。
- **→ 在 `GRAVITY_DEGREE > 0` 且終端段長的情境，「可拆」判定系統性過度樂觀。** contest 是二體所以沒事。
- **2.3 退路在這個情境無效**：旗標開後搜尋不再懲罰終端超標，各案例全是違規解，log「沒有零違規備胎」→ 照舊交違規解。

### 6.3 其他發現

- **預付成本 1.00 在 `hyperbolic_test` 低估**：拆後估計 97.5616 vs 實拆 97.1261，差 **0.435 分**（contest 只差 ~0.003）。
  這次沒改變贏家，但兩個候選差 < 0.4 分時可能挑錯。
- **記憶體洩漏根因**：`fast_fitness_evaluator` 在 numba 內 try/except 接 poliastro `izzo` 的例外（多圈 M 分支
  時間不夠時丟 ValueError/RuntimeError），numba nopython 的 raise+catch 會漏記憶體。直接迴圈呼叫 30k 次：
  `LAMBERT_MAX_REVS=0` RSS 325→325 MB、`=4` 325→378 MB（~1.8 KB/次）；contest `[1,2,3,4]` 單 run 約 1.5 GB/min。
  只影響牆鐘不影響分數。本輪驗證改成一次只跑一個大 run（`uv run python scripts/c4_runner.py --slots 4`）。
  **2026-09-26 已修**：`core_math.izzo_max_revs` 呼叫前預檢 M_max，跳過必丟分支（保守判定，拿不準照呼叫）。
  E3 單 run 系統用量：修前 2 分鐘 1.5→4.7 GB、6 分鐘吃滿 12 GB 進 swap（峰值 swap 7.7 GB）；修後搜尋期間持平。
  逐位元驗證與 numba 快取的插曲見 STATUS 待辦 A。

### 6.4 建議下一步（待討論）

1. **拆棒器終端段加 shooting 修正**（根治）：最後一段 Lambert 猜測後，在 J2–J4 下用 Newton/差分修正 Δv 讓傳播
   真的命中（等同 GMAT DC 做的事；350 km 的偏差在可修範圍內）。修完重跑 E4 `hyper_far` 開。
2. 短期保險：`SPLIT_AWARE_TERMINAL` 只在 `GRAVITY_DEGREE == 0` 生效；或預付成本依終端段長/攝動加碼。
3. 讓 2.3 退路真的有備胎：拆失敗時用旗標關再跑一輪搜尋取合法解（或搜尋時另外記「零違規最佳」，不受旗標影響）。
4. 修 izzo 例外洩漏：呼叫前先做可行性預檢（M ≤ floor(T/π)、T ≥ T_min(M)，poliastro `_compute_T_min`），
   跳過必丟例外的分支；需驗證修前修後分數逐位元一致。
5. 1 修好後重跑 E4 全部 + E2 抽樣；E5 的「逐位元相同」要求建議放寬為「分數不退步」（旗標改了超標候選的目標值，
   搜尋路徑本來就會變）。

### 6.5 拆棒器終端段 shooting 修正後重跑（2026-09-25）

6.4 第 1 項已做：`burn_splitter._shoot_final`——`split_intercept` 最後一段先用二體 Lambert 當猜測，
**有攝動時**（J2/J3/J4 任一非零）在 J2–J4 傳播下用 Newton（有限差分 Jacobian + 回溯線搜尋）修燒後速度到
命中（< 0.1 m），再照原本驗 cap / Earth-safe / miss。二體時完全不走這段，contest 系列與 `hyperbolic_test`
逐位元不變，不重跑。新測試（`tests/test_burn_splitter.py`）：J2–J4、8.3 h 終端段，二體 Lambert 偏 472 km →
修正後 0.004 m、2 段拆成功。回歸 10/10。

J2–J4 情境全部重跑（`outputs/c4fix/`，同設定同 SEED）：

| 情境 | 旗標關 | 旗標開（修正前） | 旗標開（修正後） | GMAT（修正後開） |
|---|---|---|---|---|
| `hyper_far` | 82.2953 | 72.6870（留 1 違規）❌ | **82.6904**（3 棒、零違規，+0.395 vs 關） | ✅ DC 3,495 m 收斂 / 定燒 3,494 m |
| `hyperbolic_smoke` | 86.7854 | 86.7858 | 86.7858（不變） | ✅✅ |
| `official_sample` | 90.4410 | 90.4412 | 90.4412（不變） | ✅✅ |
| `playground` | 90.6692 | 90.6692 | 90.6692（不變） | ✅✅ |

旗標關的四個結果也與修正前逐項相同（這些 run 沒有需要拆的違規解）。

**現況：E1–E4 全過；E5 分數不退步但非逐位元相同（見 6.1）。** 還沒處理、決定預設前要考慮的：
- 2.3 退路仍然沒有合法備胎（6.2 最後一點）——這次靠拆棒器修好過關，不是靠退路。
- 預付成本在 `hyperbolic_test` 低估 0.435 分（6.3）。
- 預設要不要翻開（§5 第 3 步）待討論。

### 6.6 退路補強：沒有合法備胎時旗標關重搜（2026-09-25）

`main._fallback_to_legal_backup` 改為：拆棒失敗（贏家仍違規）時先試搜尋記下的合法備胎；**沒有備胎、或
備胎精修後不合法，就用旗標關重跑一輪 `_search_stage` + 拆棒**，跟違規解比真實分數交好的。同 SEED 下重搜
就是旗標關的結果，所以**旗標開的最差情況 = 旗標關**。代價只在拆棒失敗時多一輪搜尋。`--from-winner` 重播也走退路。

- 單元測試（`tests/test_split_aware_terminal.py` §4）：重搜較好/較差/失敗/不 Earth-safe、備胎精修後不合法 → 改重搜。回歸 10/10。
- 端到端（`outputs/c4fix/FB_hyper_far_forced_fail`）：hyper_far 開旗標存檔，執行期把 `_shoot_final` 換成不修正
  （= 修正前的拆棒器）→ 拆不出 → 退路重搜 → **82.2953（4 棒零違規）**，與旗標關 run 逐位元相同（GMAT DC Δr
  38.2 m 同值），GMAT DC/定燒 ✅✅。多花 ~20 分鐘。

### 6.7 翻成預設開 + 拆棒階段鎖 BLAS（2026-09-25）

- **`SPLIT_AWARE_TERMINAL` 預設改為開**（`optimizer.py` 預設值、`main.DEFAULT_CONFIG`、README 開關表）。依據：
  E1–E4 通過（E4 靠 6.5 的 shooting）、E2 9/9 ≥98.316、退路最差 = 旗標關（6.6）。E5 分數不退步、非逐位元相同，
  視為可接受（旗標改變超標候選的目標值，搜尋路徑本來就會變）。
- `_pick_best_case` 取分數改走 `mission_rank_score`（缺 `score_split_est` 時退回 `score`，與 REVS 挑選同規則）；
  `test_tiebreak` 的假 metrics 補齊 `earth_safe` / `split_terminal_count`（真實 `mission_metrics` 一定有）。
- **重現性漏洞**：驗證時發現同一個拆棒前贏家拆出不同結果（E1_on 98.3191/7 棒 vs E3_on 98.3190/6 棒，兩者都是
  `a4b4bec`、拆棒前 x 逐位元相同）。原因：BLAS 只在搜尋階段鎖單執行緒，拆棒 joint NLP 在父行程沒鎖。重播 3 次：
  不鎖 ×2 = 98.318995／6 棒，鎖 = 98.319106／7 棒。修法：`main._legalize_stage` 設了 SEED 時包
  `threadpool_limits(1, "blas")`（同搜尋階段）。修後重播 ×2 都是 98.319106／7 棒。
- **E6：contest 設定不寫旗標（= 預設）完整管線** → **98.3191**（7 棒零違規），GMAT DC/定燒 ✅✅，
  `output_submit.txt` 與 E1 旗標開 **md5 相同**。回歸 10/10。

**C4 結案。** 後續可做（未排）：中間棒超標（`SPLIT_AWARE_SEARCH` 開時）也納入拆後估計——目前 E2 這類
「中間 + 終端都超標」的解拆前估計低 10 分（例 88.26 → 實拆 98.32），不影響最終結果但挑贏家時被低估；
預付成本依幾何校正（6.3，`hyperbolic_test` 低估 0.435）；~~izzo 例外記憶體洩漏（6.3）~~ 2026-09-26 已修。
