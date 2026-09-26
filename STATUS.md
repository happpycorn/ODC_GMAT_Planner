# 專案狀態筆記（交接用）

給下一個 session（不管是我自己回來還是你自己看）快速抓回上下文用的：「現在做到哪、還缺什麼、為什麼」。
**怎麼用這個工具看 [README.md](README.md)；演算法/物理模型原理看 [METHODOLOGY.md](docs/METHODOLOGY.md)**；
初賽的逐日開發日誌封存在 [docs/log/DEVLOG_prelim.md](docs/log/DEVLOG_prelim.md)；更細的技術決策看 commit log 跟程式碼註解。

**最後更新：2026-09-23（晚）——contest 幾何新高 98.3190（4 棒路線家族 + A1 拆棒，GMAT 驗證）；繳交腳本剔除空燒；修 numba 快取非確定性；併入 Codex 分段管線。**

## 分段管線第一版（2026-09-23）

- 原本 `uv run main.py` 一路跑到底仍可使用；新入口與命令範例見 [README 分段執行](README.md#分段執行修改後不用每次從搜尋重跑)。
- `--stop-after solve` 保存拆棒後的 `mission.json`；`--from-mission` 跳過搜尋、primer 與拆棒，重跑產檔／驗證。
- `--verify-script` 只驗證現有腳本。每次使用新的 `outputs/runs/<run-id>/`，保存實際執行副本、隔離報表、stdout/stderr、雜湊與驗證結果；舊 `outputs/` 產物不覆寫。
- 方案存檔驗證內容雜湊與物理程式版本；修改求解／物理程式後拒用舊方案，需重新求解或從拆棒前存檔重播。Python 求解成功不等於 GMAT 通過。
- 實測小預算案例（`tests/fixtures/pipeline_smoke.json`）：全流程 36.2 秒，從 `mission.json` 重跑下游 5.0 秒；兩份一般版／固定燃燒版腳本逐位元相同，真實 GMAT 皆命中且合規。這是單次煙霧測試，不是普遍加速倍率。
- 既有拆棒前存檔實測：拆棒 413.6 秒，保存六棒方案後重播下游 3.5 秒；一般版與固定燃燒版 GMAT 皆通過。產物位於本機 `outputs/runs/stage-refactor-validation*`（不納入 Git）。
- 新增 `tests/test_pipeline_stages.py`，測階段跳過、舊存檔相容、快照完整性、每種子保留、輸出不覆蓋、報表隔離與失敗、安全閘門。
- 本版未拆開搜尋內部候選集與 primer 診斷；修改搜尋／拆棒演算法仍須跑對應測試，不應拿下游重播取代物理回歸。

## 這是什麼

TASA／淡江大學辦的「第一屆軌道設計競賽」的任務規劃工具。太空船 B（我方，機動）要在時間／燃料限制下攔截
太空船 A。`rules/` 有官方文件（正式規則 PDF ×2、0510 說明會簡報、參賽選手注意事項）。

- **初賽**：A 是圓軌道、被動（只受重力），單純攔截。**已結束。**
- **下一輪（排位賽起）**：官方簡報說是**完全不同玩法**——A 變雙曲線、即時追逐戰。工具的雙曲線輸入端
  已端到端跑過、含 HAP-67 拆棒管線（見下面 P3），但沒鎖進回歸測試。玩法／計分細節要等官方發題才知道。

規則要點（初賽）：Δv ≤ 1500 m/s/次、機動間隔 ≥100s、T_max=4×A 週期、**Δr ≤ 5km 即算成功且以內同分**
（這點很關鍵，計分對命中位置是平的，決定策略）、繳交「Script + 至少模擬一次的 Report」。

## 🏁 初賽結果（2026-09-05）

**第二名。** 我們官方繳交 `docs/solutions/98.32_champion_team19.md` 那份（GMAT DC 驗證 98.31、零違規、
Earth-safe 的五棒解）。第一名 Team15 以 98.3162 奪冠；兩隊因撞地球失格。

事後補記（不影響已定結果）：2026-09-09 用 HAP-47 的 joint NLP 拆分器對同一組解重新聯合優化、GMAT 驗證後
得 98.3177，理論上會以 0.0015 分之差贏過 Team15——但初賽已結束、無法追溯提交，價值在下一輪。
細節見 [HAP47_SPLIT_ALGORITHM_RESEARCH.md](docs/HAP47_SPLIT_ALGORITHM_RESEARCH.md) §7.1。

初賽的解與教訓都封存在 [docs/solutions/](docs/solutions/)（各解 SUMMARY、冠軍繳交件、重力模型 bug 與
撞地球教訓）。初賽當天手冊／站別卡在 [docs/prelim/](docs/prelim/)。

## 下一輪準備：現況與待辦

**已就位、可跨輪沿用：**
- 力學引擎：DOP853 積分器（`rtol=1e-12, atol=1e-9`）、可設定重力場 `GRAVITY_DEGREE`(0/2/3/4)。
- GMAT 整合：`GmatConsole --exit --run` 無頭驗證、自動讀報表對照、雙曲線相機／radius-range 已加。
- Config 驗證：`config_validator` 已放寬 SMA/ECC、支援雙曲線輸入。
- 種子機制四家族：relay／ladder／pcsplit／joint NLP 精修（HAP-47）。
- **拆棒管線（HAP-67，2026-09-11 上線，預設開）**：`src/burn_splitter.py` + `main.py` 的
  `legalize_violating_winner()`。DE 挑完贏家後，若有「超標但 Earth-safe」的違規棒，自動拆成
  合法多棒版（**段數動態算出、不再被 MAX_BURNS 綁死** → joint NLP 用真實 `calculate_score`
  壓低總 Δv），後面產腳本/GMAT/紀錄全用合法版。旗標 `strategy.AUTO_SPLIT_LEGALIZE`（設 false
  退回舊行為）。實證：contest.json **88.32（含 −10 違規）→ 98.31（零違規、GMAT 定燒命中、可交）**，
  +9.99 分。設計/驗證全記在 [HAP67_SPLIT_PIPELINE_PLAN.md](docs/HAP67_SPLIT_PIPELINE_PLAN.md)。
  注意：種子端的 pcsplit/split_even-as-seed **疑似冗餘但別急著移除**——拆棒雖改由後處理，
  但那些種子仍可能幫 DE 找到**更好的路線**（PoC 冠軍 98.3177 vs 後處理自動解 98.31，差在路線
  不在拆法），移除前要先驗證「拿掉後 DE 分數不掉」，不是無腦刪。
  **搜尋端 `SPLIT_AWARE_SEARCH`（放寬中間棒上界）維持預設關**：調查 14 個場景 0/14 需要 >cap
  中間棒（大機動都被節線攔截閃掉、或落終端棒已處理），故「中間棒拆分器」不做、此旗標休眠別刪，
  下一輪雙曲線 A 真題出來再重驗。完整調查見
  [HAP67_SPLIT_AWARE_INVESTIGATION.md](docs/HAP67_SPLIT_AWARE_INVESTIGATION.md)。
- **primer 引導的條件式重搜（C2，2026-09-22 上線，預設開）**：`main.primer_guided_research()`
  在拆棒合法化前對 DE 贏家算 primer——`|p|≤1`（optimal-ish）就收工不重搜（圓軌道輪 0/14 的
  物理，contest 贏家實測 max|p|=1.000）；`|p|>1`（add-node）才用 B1 的 energy_floor 動態上界
  打開 `SPLIT_AWARE_SEARCH`、用 `primer.insert_node_seed()` 在 primer 指的弧注入插棒種子
  （經新增的 `optimizer.external_seeds` 注入初始族群）、以 N+1 棒重搜，最後照§6 取優。
  「SPLIT_AWARE 該不該開、種子放哪」從用猜的變成 primer 指的。旗標
  `strategy.PRIMER_GUIDED_RESEARCH`（設 false 連診斷都不跑）。對當前圓軌道題型零行為改變、
  零額外成本（只多印一行證書）。設計/實證見 [C1_PRIMER_VECTOR_STUDY.md](docs/C1_PRIMER_VECTOR_STUDY.md) §6。
- **Seed-portfolio 小模式（2026-09-22，預設關）**：`main.run_seed_portfolio()` +
  `_solve_pipeline()`。`strategy.SEED_PORTFOLIO_N>1` 時跑 N 顆 SEED（base..base+N-1）各自
  完整求解（含 C2 + 拆棒），照§6 留**拆後**分最高的那顆，避開單一 SEED 抽到低籤（本 session
  contest 分析：幾乎免費 +0.008）。預設 1 = 單跑、逐位元同舊行為。繳交前的品質旋鈕，成本 N 倍。
  **⚠️ 2026-09-23 C3 查明**：那 +0.008 主要是替被截斷的拆棒 SLSQP 多抽幾次籤，A1 修掉後價值大減；
  是否退役待量 A1 後的 SEED 間散布。
- **拆棒跑到收斂 + 拆棒前贏家存檔/重播（C3，2026-09-23）**：拆後分數 0.01 級抖動的主因是
  `joint_nlp_split` 的 SLSQP 被 maxiter=80 截斷（每次都 status=9），擦邊解被判不可行、退回 greedy
  暖啟。A1：maxiter 預設 1000 + SLSQP 對略緊約束求解（cap −0.02 m/s、miss −5 m、近地點 +1 m），
  feasible 仍用真實約束判。contest SEED=0 同一路線 **98.3121 → 98.3174**，GMAT 一般版/固定燃燒版
  皆命中、收斂、合規。另：每次完整跑自動存本次目錄的 `winner_presplit_seed<SEED>.json`，
  **`main.py --from-winner <檔>` 跳過搜尋、只重跑拆棒 + 產腳本 + GMAT（~4 分鐘）——改拆棒器時用它，
  不要重跑整條管線**。完整診斷與數據見 [C3_CONVEX_SPLITTER_PLAN.md](docs/C3_CONVEX_SPLITTER_PLAN.md) §6。
- **路線家族 + 空燒剔除 + numba 非確定性（C3 續，2026-09-23）**：
  - **98.3190**（contest 幾何新高，> 初賽冠軍 98.3162）：最初靠強制 4 棒搜尋 SEED=7 撞到；追查後是**第一棒貼 cap、
    需要後面 100 s 有空位讓 NLP 分擔溢出**。`burn_splitter._slot_after_capped` 自動補空位後，**預設管線直接 98.3188**。封存於
    [docs/solutions/98.319_route4_split6.md](docs/solutions/98.319_route4_split6.md)（含繳交腳本）。
  - A1 後同盆地內各 SEED 拆後只差 ~1e-4（= 拆棒雜訊底線）；分數差距來自**盆地選擇**，不是拆法。
  - `burn_splitter.prune_null_burns`：剔除 NLP 壓到 mm/s 級的空燒，剔除後用真實約束重評才採用，繳交腳本只剩實燒。
  - `core_math.lambert_izzo`：Python 端 Lambert 唯一入口。原本 numba 冷/熱快取會讓 izzo 特化版本不同，
    同輸入拆出不同分（3e-5）；**Python 端不要直接呼叫 poliastro izzo**（見 memory odc-numba-cache-nondeterminism）。
- **末端速度匹配審查（D2，2026-09-22，純審查無改動）**：確認全管線是**純位置攔截**、無
  rendezvous 末端速度匹配殘留——`_lam_best`/終端 Lambert 三處 `vref` 都是載具自身燒前速度
  （非目標速度），scorer 的 `k_v/C_v` 罰的是總Δv預算不是速度差。雙曲線下不會浪費燃料去匹配
  近地點高速。
- 回歸：`uv run python run_regression.py`（11 支、~6 分鐘——2026-09-26 量到 370s，其中 `test_hyperbolic_e2e` 278s；動任何東西前先跑）。拆棒管線有
  `tests/test_burn_splitter.py`；**雙曲線 A 端到端有 `tests/test_hyperbolic_e2e.py`（2026-09-22 補，
  A5）**——結構煙霧（雙曲線輸入端＋種子產生器不炸）＋拆棒 e2e（違規→自動拆分→零違規/命中/
  Earth-safe），性質式斷言。這補上了 STATUS 舊列的 P3 缺口。
- **可重現性（2026-09-22 修）**：管線設了 SEED 現在**真的**可重現了。原本 `seed→單執行緒` 只鎖
  mealpy 的 RNG，沒鎖 scipy SLSQP 種子精修走的**多執行緒 BLAS**——多執行緒 BLAS 浮點歸約
  run-to-run 順序不同，會讓種子/DE 在臨界點翻盤（2 vs 3 棒、分數 ±1）。修法：`run_study_over_revs`
  偵測到 SEED 時，spawn 前 pin BLAS env（子行程繼承）＋ `threadpool_limits` 包父行程 polish
  （新增 `threadpoolctl` 依賴）。**任何 before/after 對照都靠這個才可信**（見 memory
  odc-blas-nondeterminism）。

**開始下一輪前要處理的風險**（出自 [PROJECT_AUDIT_20260909.md](docs/PROJECT_AUDIT_20260909.md)）：
- 🟠 **P2 Earth-safe 判定是點質量解析式**（`reaches_perigee`/`check_constraints`）。下一輪若開攝動，
  長弧近地點會漂、解析判定不再精確——而它是失格線。→ HAP-20（攝動開時切數值密集取樣）。
- ✅ **P3 雙曲線 A 端到端已重驗（2026-09-12）**。這條審計當時寫「從未跑過」時已經過時——
  2026-08-15 就跑過 `hyperbolic_smoke`/`hyper_far`/`hyper_fast` 三組（見
  [SCENARIOS.md](docs/SCENARIOS.md)），只是那次在 HAP-67 拆棒管線之前，沒測到「贏家違規時
  自動拆分合法化」這條新路徑。09-12 用 `hyperbolic_test`（見 SCENARIOS.md 同節）逼 DE 交出
  違規解，確認 `AUTO_SPLIT_LEGALIZE` 在雙曲線幾何下正常拆成合法解、GMAT 一般版/固定燃燒版
  都收斂命中。回歸測試已於 2026-09-22 補上（`tests/test_hyperbolic_e2e.py`，A5）。
- ✅ **P4 雙曲線 A 的 TA 漸近線檢查已補（2026-09-22，A4）**：`config_validator._validate_orbit`
  對 ECC>1 檢查 `|TA| < arccos(−1/e)`（TA 折到 (−180,180] 再比，容 [0,360) 寫法），漸近線外
  直接報錯、不再拖到 poliastro 算位置才炸。回歸 `tests/test_hyperbolic_e2e.py`。
- ⚠️ **計分參數與 A/B 六根數要等官方發題**（`k_t/C_t/k_v/C_v`）。

**待辦（2026-09-26 更新，依優先序）**：
A. **✅ izzo 例外記憶體洩漏已修（2026-09-26）**：`core_math.izzo_max_revs` 在 `fast_fitness_evaluator` 呼叫 izzo 前
   預檢 M_max，跳過「飛行時間不夠繞 M 圈」必丟 ValueError 的分支（numba 內 raise+catch 每次漏 ~1.8 KB）。
   洩漏 1.85 → 0.03 KB/eval、評估速度不變；E3（contest 4 棒、2000 代）系統用量修前 6 分鐘吃滿 12 GB 進 swap，
   修後搜尋全程持平。**大 run 不必再限一次一個。**
   - 預檢**刻意保守**（邊界放寬 1e-9、近共線回「不確定」交給 izzo）：izzo 自己的兩種編譯特化在退化幾何上丟不丟
     就不一致，求逐位元一致的第一版在 run_regression 底下翻車。`tests/test_izzo_max_revs.py` 對兩種特化驗「誤跳 0 次」。
   - 逐位元驗證：隨機 ~10 萬點（6 組情境）修前修後相同；E3 搜尋實錄 280 萬次評估，新程式在**同樣快取狀態**下逐位元相同。
   - **⚠️ 順帶查出：同 SEED 的可重現性還綁 numba 快取冷熱。** `fast_fitness_evaluator` 冷編譯 vs 讀快取，同輸入最後
     一位不同（1 ulp，改前的舊程式本身就這樣），DE 軌跡隨之分岔——E3 同 SEED 一次採 3 棒一次採 4 棒（拆後 98.3191 vs
     98.3190）。之前「修前修後逐位元比對」都隱含這個前提。**參數實驗與任何 before/after 對照要先固定快取狀態**
     （例如先暖快取、或各自指定乾淨 `NUMBA_CACHE_DIR`）。根因（冷熱為何連結到不同浮點行為）未查。
B. **參數正式實驗**（2026-09-26 新增；現行 MAXITER/POPSIZE 等是憑感覺設的）。參數分四類、調法不同：
   規則（照題目填）／安全餘量（`MISS_TOLERANCE_KM`、`MAX_DV_MARGIN_MPS`、拆棒 `_NLP_*_MARGIN`——**不拿分數調**，
   放寬必加分但踩失格線，只看 GMAT 驗證失敗率）／搜尋預算（MAXITER、POPSIZE、MAX_EARLY_STOP、TOL、MAX_BURNS——
   目標是「限時內分數」不是最高分）／演算法開關（REVS 集成、種子雙重精修——即待辦 3，併進來做消融）。
   做法：先寫掃描工具（情境 × SEED × 參數組 → jsonl），情境要涵蓋圓軌道／換面／雙曲線、至少兩組計分權重（計分參數
   是佔位值，只調 contest.json 會過擬合），每組 ≥5 顆 SEED 看中位數與最差值。先粗掃再細掃，粗估兩晚批次。
   - **掃描工具已就緒（2026-09-26）：`sweep_params.py <規格.json>`**（規格格式見檔頭；`--dry-run`／`--slots N`／
     `--summary`；可中斷續跑、開跑前暖 numba 快取、每次 run 偵測冷編譯）。結果在 `outputs/sweeps/<name>/results.jsonl`，
     每筆有拆後/拆前分數、違規、各案例代數、牆鐘/CPU、**搜尋與拆棒分段秒數**。
   - 冒煙測試已看到的兩件事：(1) contest 預算壓到 MAXITER=10 時**拆棒比搜尋久得多**（搜尋 ~30s、拆棒 ~290s）——
     拆前解越爛拆得越久，「限時內分數」要把拆棒時間算進去；(2) contest 拆棒器很會救：MAXITER=10 拆前 77.31 →
     拆後 98.3177，但另一顆 SEED 掉到 89.06（另一個合法家族）——預算小的代價是最差值，不是中位數。
   - SEED 相同時 slot 之間不互相影響結果（BLAS 已鎖、快取已暖），`--slots` 只影響牆鐘；contest 求解幾乎單核
     （CPU 秒 ≈ 牆鐘），這台 16 執行緒可以開 3～5 個 slot。
C. C4 後續：中間棒超標也納入拆後估計；預付拆棒成本依幾何校正（`hyperbolic_test` 低估 0.435）。
0. **✅ C4 結案（2026-09-25）：`SPLIT_AWARE_TERMINAL` 已改為預設開**；contest 預設管線 98.3191 GMAT ✅✅（與旗標開逐位元相同），
   拆棒階段補鎖 BLAS（同 SEED 拆出不同結果的漏洞），見計劃書 §6.7。以下為過程紀錄。
   2026-09-24 初次驗證（`a4b4bec`，當時維持預設關）：二體情境全過、強制 4 棒 SEED 0–8
   開旗標 9/9 ∈ [98.316, 98.319]（關：82.27、89.25 各一）；但 **E4 `hyper_far`（J2–J4）開旗標 72.69 vs 關 82.30**——
   貪婪拆棒器終端段用二體 Lambert、J2–J4 傳播 8.4 h 後偏 ~350 km 被拒，退路也沒有合法備胎。
   **2026-09-25 已修**：`burn_splitter._shoot_final`（攝動時終端段 Newton 修到命中）→ `hyper_far` 開旗標
   **82.6904 合法、GMAT ✅✅**（關 82.2953）；其他 J2–J4 情境不變。E1–E4 全過、E5 分數不退步但非逐位元相同。
   退路已補（拆不出且無合法備胎 → 旗標關重搜，最差 = 旗標關；端到端驗過）。見計劃書 §6.5–6.6。
   另：搜尋 worker 記憶體暴漲根因是 numba 內接 `izzo` 例外（REVS>0 才漏），見計劃書 §6.3——**2026-09-26 已修**（待辦 A）。
   （以下為原計劃摘要）
   **完整計劃書：[docs/C4_TERMINAL_SPLIT_AWARE_PLAN.md](docs/C4_TERMINAL_SPLIT_AWARE_PLAN.md)**（以下為摘要）。
   - **問題**：搜尋目標函數（`optimizer.fast_fitness_evaluator`）對**終端棒**超標一律 `penalty_count += 1`（−10）。
     但我們會拆它、代價只 ~0.003 分。所以 DE 看到 88.32 家族（拆後真實 98.32）＜ 合法的 89.25 家族
     （省油 4,480 m/s 但晚到 T=6,430 s、時間分只 14.36），**會往錯的家族收斂**：強制 4 棒 SEED 4 就收在 89.25，
     其他 4 棒 SEED 多停在「2 次違規 78.x」。預設 `MAX_BURNS=[1,2,3]` 目前沒出事只是沒有案例找到 89.25。
   - 現有 `SPLIT_AWARE_SEARCH` 只處理**中間棒**（超標改預付時間 + `SPLIT_AWARE_DV_OVERHEAD`），終端棒沒處理。
   - **設計**：(1) 新旗標 `strategy.SPLIT_AWARE_TERMINAL`（建議 `AUTO_SPLIT_LEGALIZE` 開時預設開）：終端棒超標且
     ≤K×cap（K 可設，例如 5；contest 是 3.13×）時不計 penalty，改預付拆棒成本——實測 Δv 幾乎不增
     （拆前 6,189 → 拆後 6,180～6,190），係數預設 1.00；抵達時刻不變（拆棒器鎖 A(T)），不加時間。
     scalars 陣列加新索引（16），三處組 scalars 的地方（`optimizer.py` ~1601/1736/1827）同步。
     (2) **挑贏家也要換尺**：`_pick_best_case`、`pick_best_across_revs`、C2 比較都用扣過罰分的真實分數，
     要改成「加回可拆違規的罰分」的拆後估計分數。
   - **驗收**：contest 預設管線仍 ~98.319（GMAT）；強制 4 棒搜尋不再收在 89.25/78.x；`test_hyperbolic_e2e` 過；
     回歸全過。對照用 `docs/solutions/checkpoints/` 的兩個拆棒前存檔 + `--from-winner`。
1. ~~拆後分數進路線選擇~~ → **已解（2026-09-23 晚）**：98.319 其實是拆棒器沒處理「貼 cap 的前導棒」，
   `_slot_after_capped` 補空位後**預設管線從頭跑就是 98.3188**（GMAT ✅）。多候選各拆暫不需要，雙曲線真題再評估。
2. **測試 quick/full 分層**（[FLOW_EFFICIENCY_AUDIT](docs/FLOW_EFFICIENCY_AUDIT_20260923.md) P1）：`run_regression.py --quick`
   排除 slow e2e；`test_hyperbolic_e2e` 拆結構煙霧／e2e 兩支。
3. **REVS 集成消融**（審計 P2，~1.8× 成本）與**種子雙重局部精修消融**（審計 P4）：固定 SEED 多情境跑數據再決定預設。
4. seed-portfolio 定位改為「探索不同盆地」（同盆地散布已 1e-4）；預設維持 1。
5. 等官方：計分參數與六根數；雙曲線真題出來後重驗 SPLIT_AWARE / C2；P2 Earth-safe（攝動開時數值取樣）。
6. 凸拆棒器（C3 B 檔）擱置——拆棒雜訊已 1e-4。

## 環境（本機、不進 git）

- **目前開發機：Mac（Darwin）。** GMAT R2026a 在 `/Users/corn/Documents/GMAT R2026a/bin/GmatConsole`
  （已存在，寫進各 `configs/*.json` 的 `local.gmat_console_path`，或帶 `--gmat-console`）。
- `configs/` 整個被 gitignore、換機器不會帶過來。**設定檔的完整重建參數記在 [SCENARIOS.md](docs/SCENARIOS.md)**
  （configs/ 遺失就靠這份重建）。
- 2026-08-15 曾在 WSL2+Ryzen 上開發，那套 GMAT-on-WSL 修補若日後回 WSL 用得上，記在 DEVLOG_prelim.md 末段。
