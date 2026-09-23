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
  - **98.3190**（contest 幾何新高，> 初賽冠軍 98.3162）：強制 4 棒搜尋 SEED=7，拆**前**只有 88.30（比 88.32
    路線低）但拆後最高——**拆前最優 ≠ 拆後最優**，搜尋只看拆前分數所以預設走不到。封存於
    [docs/solutions/98.319_route4_split6.md](docs/solutions/98.319_route4_split6.md)（含繳交腳本）。
  - A1 後同盆地內各 SEED 拆後只差 ~1e-4（= 拆棒雜訊底線）；分數差距來自**盆地選擇**，不是拆法。
  - `burn_splitter.prune_null_burns`：剔除 NLP 壓到 mm/s 級的空燒，剔除後用真實約束重評才採用，繳交腳本只剩實燒。
  - `core_math.lambert_izzo`：Python 端 Lambert 唯一入口。原本 numba 冷/熱快取會讓 izzo 特化版本不同，
    同輸入拆出不同分（3e-5）；**Python 端不要直接呼叫 poliastro izzo**（見 memory odc-numba-cache-nondeterminism）。
- **末端速度匹配審查（D2，2026-09-22，純審查無改動）**：確認全管線是**純位置攔截**、無
  rendezvous 末端速度匹配殘留——`_lam_best`/終端 Lambert 三處 `vref` 都是載具自身燒前速度
  （非目標速度），scorer 的 `k_v/C_v` 罰的是總Δv預算不是速度差。雙曲線下不會浪費燃料去匹配
  近地點高速。
- 回歸：`uv run python run_regression.py`（8 支、~6 分鐘——C3 後量到 364s，其中 `test_hyperbolic_e2e` 246s；動任何東西前先跑）。拆棒管線有
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

**待辦（2026-09-23 晚更新，依優先序）**：
1. **拆後分數進路線選擇**（進行中，branch `post-split-selection`）：DE 前幾名候選各拆一次、依拆後分數挑，
   取代「多撞 SEED」——98.319 盆地在 10 顆 4 棒 SEED 裡只撞到 1 顆。
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
