# 流程必要性與效率審計（2026-09-23）

## 結論先行

目前正式求解流程沒有一段可以在**不驗證效果**的前提下直接刪除。最昂貴的重複主要是刻意用計算量換搜尋穩定性或提交可信度，不是單純重算錯誤；但開關與使用情境混在同一條預設流程裡，導致日常迭代、完整求解、最終提交三種需求付出相近成本。

最值得先做的不是改物理或最佳化器，而是把流程分成三個明確層級：

1. **快速開發**：快速回歸、單一 REVS、跳過 GMAT，目標是數十秒到數分鐘。
2. **候選求解**：多棒數搜尋、條件式 primer、必要時拆棒；REVS 集成依情境開啟。
3. **最終提交**：固定 seed/必要的集成、完整拆棒收斂、GMAT DC + 固定燃燒版雙驗證。

在目前程式中，以下機制應保留：真實分數重播、Earth-safe 閘門、違規贏家的拆棒合法化、固定燃燒版 GMAT 驗證、條件式 primer 診斷。最應優先降成本的是測試分層、REVS 集成的執行方式，以及對種子局部精修做消融。

## 目前正式流程與成本放大

```text
每顆 SEED
  └─ REVS=0 / REVS=max 各跑一次（預設約 1.8×）
       └─ 每個 MAX_BURNS 案例平行
            ├─ 產生多家族種子
            ├─ 部分種子先做 SLSQP 精修
            ├─ L-SHADE
            └─ 所有送入族群的種子再各做 L-BFGS-B 精修
       ├─ 每個棒數候選做真實任務重播並依規則挑選
       └─ 勝出候選再做 NLP／平手微調／重播
  ├─ primer 診斷；只有 |p|>1 才整條 N+1 重搜
  └─ 若贏家違規但 Earth-safe，跑兩個段數的拆棒 SLSQP（每個最多 1000 iter）

最終輸出
  ├─ Python 高精度預測
  ├─ GMAT DC 版驗證
  └─ 產生固定燃燒版，再跑一次 GMAT（實際繳交件）
```

`SEED_PORTFOLIO_N > 1` 時，上述整棵樹會再串行重跑 N 次。預設值為 1，因此目前不是預設成本。

## 實測基線

本分支執行：

```bash
uv run python run_regression.py -q
```

結果為 8/8 通過，總耗時 **481.5 秒**。

| 測試 | 耗時 | 佔總時間 |
|---|---:|---:|
| `test_hyperbolic_e2e.py` | 314.1s | 65.2% |
| `test_nlp_split_refine.py` | 52.6s | 10.9% |
| `test_burn_splitter.py` | 41.3s | 8.6% |
| `test_tiebreak.py` | 33.8s | 7.0% |
| 其餘 4 支 | 39.8s | 8.3% |

前三支慢測試合計約 85%。歷史 `outputs/run_history.jsonl` 顯示完整求解曾介於約 26 秒至 5,556 秒；差異主要來自 MAXITER/POPSIZE、棒數範圍、REVS 集成、seed 單執行緒與拆棒 SLSQP，而不是輸出或日誌。

## 發現與建議

### P1：測試沒有 fast / slow 分層，日常回歸固定支付 8 分鐘

`run_regression.py` 會順序執行全部 `test_*.py`。逐支子行程隔離是合理的：測試會 `sys.exit`、有模組狀態、也會觸發 Numba；不建議為省啟動時間改成同一行程。

真正的問題是 `test_hyperbolic_e2e.py` 同時包含秒級結構檢查和 5 分鐘級搜尋＋拆棒 e2e。前者適合每次執行，後者適合提交前或夜間執行。

建議：

- `run_regression.py --quick` 預設排除明確標記的 slow/e2e 測試。
- `run_regression.py --full` 保留目前 8 支完整行為。
- 把 hyperbolic 結構煙霧和昂貴 e2e 拆成不同檔案，讓篩選不依賴函式內部邏輯。
- CI 若存在：每次提交跑 quick，排程或 release gate 跑 full。

這是低風險、高確定性的節省；沒有刪測試覆蓋。

### P2：REVS 集成有真實品質價值，但串行完整重跑是最大預設倍率

`run_study_over_revs()` 預設依序完整跑 REVS=0 與 REVS=max，文件量測約 **1.8×**。它不是無效重複：既有研究在 3/8 幾何看到 REVS=0 勝過 REVS=4，且偶爾可避免 1–2 分的壞盆地。另一方面，C3 對 contest 同一路線的拆棒結果顯示 REVS 0/4 逐位元相同。

因此不建議直接刪除或全域關閉。建議順序：

1. 先以現有 scenario suite 做消融，記錄每個情境兩趟的「勝者、分差、牆鐘」。
2. 若大部分新題型同解，把預設改成單跑，僅在候選品質不足或最終提交時開 ensemble。
3. 若集成仍必要，將工作單位從「每個 REVS 串行包一整次 run_study」改成 `(REVS, burn_count)` 案例統一排程；總 CPU 工作不變，但可降低尾端等待。要同時重算每案例 thread 配額，避免過度訂閱核心。

### P3：seed portfolio 應維持實驗開關，不應成為常態流程

目前預設 `SEED_PORTFOLIO_N=1`，做法正確。C3 已顯示舊版多 seed 的主要收益來自替被 maxiter=80 截斷的拆棒 SLSQP 多抽幾次；maxiter=1000 後，同一路線散布縮到約 0.0001 分，而 N=3 會把完整流程成本乘三。

建議：完成 STATUS 已列的 A1 後 seed 1/2 量測。若分差仍在 1e-4 級，將 portfolio 明確標成「探索不同路線用」，不要用來修補同一路線數值抖動；最終預設仍為 1。

### P4：種子可能被連續局部精修兩次，需要消融，不可直接刪

多棒種子中的前三名會先經 `_generate_nlp_refined_seed_candidates()` 的 SLSQP；組成 `seed_candidates` 後，`_optimize_burn_case()` 又對每顆種子跑一次 L-BFGS-B。兩者並非完全等價：前者有 Earth-safe／命中／DC 顯式約束，後者只有 box bounds 並以帶懲罰的 fitness 最佳化，所以不能只因「都是局部最佳化」就刪一層。

但這是明確的重疊區，且 `test_nlp_split_refine.py` 單支就需 52.6 秒。建議用固定 seed 對至少圓軌道、換面、雙曲線三類情境做四組消融：

- 無局部種子精修；
- 只有 SLSQP；
- 只有 L-BFGS-B；
- 目前兩者都有。

比較拆後最終分數、合法率、找到不同路線的比例與牆鐘。只有在「SLSQP 後再 L-BFGS-B」沒有增加勝率時，才跳過已 SLSQP 精修種子的第二次 L-BFGS-B。

### P5：能量下限警告與 route-first 拆棒方法論互相矛盾（已修正）

修正前，`preflight_report()` 和 README 把低於能量合法棒數的 `MAX_BURNS` 描述為「注定違規、建議拿掉、浪費搜尋時間」。但 HAP-67 的核心正是允許低邏輯棒數先找到高品質違規路線，再由 `legalize_violating_winner()` 動態拆成合法多棒解；contest 的 88.32 → 98.31 就證明這條路有價值。

因此**不能自動剪掉**這些案例，也不應再一概稱為浪費。建議把訊息改成兩種語意：

- `AUTO_SPLIT_LEGALIZE=false`：低於下限的案例不可能直接合法，建議移除。
- `AUTO_SPLIT_LEGALIZE=true`：低棒數案例只能作為 route-first 候選，會額外支付拆棒成本；是否保留取決於它能否找到較好的路線。

這是流程認知問題，會直接影響使用者是否錯誤地移除最有價值的候選。

已在本分支修正：`preflight_report()` 會依 `AUTO_SPLIT_LEGALIZE` 分流提示，開啟時明確要求
保留 route-first 候選且絕不修改 `MAX_BURNS`；README 與回歸測試也已同步。

### P6：拆棒兩個段數 × 1000 iter 很貴，但目前有分數證據支持

`legalize_route(..., n_span=1)` 實際會測 `nseg0` 與 `nseg0+1` 兩個段數，每個各跑一次最高 1000 iter 的 SLSQP。現有量測約 85 秒／NLP、每顆 seed 約 3 分鐘。這不是 off-by-one 浪費：C3 顯示不同暖啟下 6/7 棒皆可能成為最佳，而 maxiter=80/300 會截斷或留下擦邊不可行結果；1000 使分數由 98.3121 提升至 98.3174 並通過 GMAT。

建議保留正式模式的 1000 iter 與兩段數候選。日常開發應使用 `--from-winner` 重播，或新增明確的 `SPLIT_NLP_MAXITER` 開發設定；不要降低正式預設來換速度。

### P7：兩次 GMAT 驗證不是純重複，但應只放在提交層

第一次 GMAT 跑含 DifferentialCorrector 的一般版，用來取得 GMAT 模型下收斂的末棒；第二次跑真正要繳交的固定燃燒版，確認移除求解器後仍命中、合規。兩者驗證的是不同失敗模式，因此最終提交時都有必要。

日常搜尋已有 `--no-gmat`，中間驗證可用 `--no-fixed-script`。建議在文件中直接將它們定位成「開發／候選模式」，最終提交才跑雙驗證。

### P8：真實重播與平手微調的重算應保留，僅可做資料重用

`_pick_best_case()` 對每個棒數做 `mission_metrics()`，勝出後 `refine_trajectory()` 又做 NLP、tiebreak polish、`_replay_mission()`。表面上有重播，但用途不同：搜尋 fitness 是代理值，文件已有長弧情境代理 80.72、真實 72.33 的反例；不重播會選錯贏家。

可做的優化只有快取／共用重建結果，以及消除 `mission_metrics` 與 `_replay_mission` 內重複的彙總程式碼。不可用代理分數取代真實重播。

### P9：`sweep_burns.py` 是一次性校準工具，不該接在每次正式流程前

它先粗掃、再對窗口精掃，刻意重跑部分棒數。README 已正確寫明：範圍只有 3–4 個時應跳過；只有十幾個候選棒數時才可能省時間。這不是程式缺陷，但操作手冊應把它標成「建立／更新情境設定時跑一次」，產生建議 config 後直接用 `main.py`，不要每輪都 sweep。

## 建議實作順序

1. 加入 quick/full 測試分層，先把日常反饋從 8 分鐘降下來。
2. ~~修正能量下限警告與 README，避免和 AUTO_SPLIT route-first 策略互相衝突。~~（本分支已完成）
3. 建立固定 seed 的 REVS、seed 局部精修消融表；沒有數據前不刪品質保險。
4. 依消融結果決定 REVS 預設策略，以及是否跳過已經 SLSQP 的種子之 L-BFGS-B。
5. 若 REVS 必須保留，再改成 `(REVS, burn_count)` 統一排程；這是較大的併發重構，需完整回歸與可重現性測試。

## 不建議做的事

- 不要因為能量下限警告就自動刪除低棒數 route-first 候選。
- 不要把拆棒 maxiter 從 1000 降回 80/300；已有品質與可行性反例。
- 不要省略固定燃燒版 GMAT 驗證後直接提交 DC 版。
- 不要用搜尋代理分數取代真實重播挑贏家。
- 不要把 slow e2e 整支刪掉；應分層執行。
