# HAP-67：三段式拆棒管線（DE → Split → NLP）計劃

**狀態：Phase 1 完成並驗證（2026-09-11）；Phase 2+ 待做。**
起因見本次 session 的討論；背景研究承接 [HAP47_SPLIT_ALGORITHM_RESEARCH.md](HAP47_SPLIT_ALGORITHM_RESEARCH.md)。

## Phase 1 進度（2026-09-11 完成）

`src/burn_splitter.py` 已建：`legalize_intercept()` = 動態段數的終端攔截拆分器
（段數從 `ceil(|Δv|/cap)` 往上掃到成功，不再被 num_burns 綁死）。

**驗證（contest.json 幾何、84.3° 換面）**：把一個 **10,148 m/s（6.8× 上限）** 的終端單棒攔截
拆成 **10 段合法燒**（每段 ≤1498 m/s）、**命中誤差 0.000 km、全程 Earth-safe（最低半徑 6,791km
≥ 門檻）**。段數（10）遠超過 `MAX_BURNS=[1,2,3]` 能表達的——**核心論點證實**：段數是拆棒的
輸出、不是搜尋前要猜的輸入。

**設計發現**：`optimizer.split_even` 當年是「種子」，只需當個夠好的起點、精確命中交給下游
L-SHADE/L-BFGS 收尾，所以**它從不驗證真的打中**。獨立後處理器不能這樣——貪婪逐段的方向會在
Lambert 分支間翻動而漂掉（實測漂到上萬 km 卻仍通過 cap/Earth-safe）。故 `split_intercept`
**新增命中驗證**：最後一段打完傳播到 T、`|r_end - target| ≤ miss_tol` 才接受。這是本模組相對
split_even 的關鍵差別，也是為什麼 Stage 2 能獨立產出「可直接交出去」的解。

**注意**：Phase 1 的測試是手工建「開場抬高棒 + 滑到遠地點」當拆分器的輸入；正式管線裡這個輸入
要由 Stage 1（DE 的粗路線）提供。見下面 Phase 2。

## 為什麼要做（問題診斷）

現行架構把「拆棒」放在**種子生成**階段，這是錯的位置，會系統性漏掉需要拆棒的解：

1. **種子拆棒被 `num_burns` 綁死**：`_generate_planechange_split_seed_candidates` 裡
   `n_final = num_burns - 1`（[optimizer.py:1085](../src/optimizer.py)）——終端攔截最多只能拆成
   `(num_burns-1)` 段。contest.json 是 `MAX_BURNS=[1,2,3]`，終端 4691 m/s（3.1× 上限）要
   `ceil(4691/1500)=4` 段起跳、加 Earth-safe 需 ~6-7 棒，**根本超出搜尋會拜訪的棒數**。
   `split_even` 對 3 棒案例算出每段 2345 > 1500 → 回 `None` → pcsplit 一個種子都生不出來 →
   DE 只剩違規解可挑 → 交出 4691。
2. **要拆幾棒是拆棒的「輸出」，不是「輸入」**：把拆棒當種子，卻要在搜尋前就猜對棒數寫進
   `MAX_BURNS`，倒因為果。就算 `MAX_BURNS=[1..7]`：DE 得盲搜高維空間又慢又難中，且合法多棒解
   還要贏過只扣 −10 的違規解，可能照樣輸。
3. **違規只扣 −10 → 搜尋偏好違規解**：一個 ΔV/時間/距離都漂亮、只 −10 的違規解，分數常高過
   「合法但較貴」的拆分解，於是合法解在計分競爭裡被淘汰。

## 目標架構：三段，各司其職

| 段 | 職責 | 產出 |
|---|---|---|
| **Stage 1 · DE** | 找路線 topology（低邏輯棒數，允許違規） | 粗路線 + 鎖定的 A(T) |
| **Stage 2 · Split** | 把違規變合法（feasibility），段數動態算出 | 零違規、Earth-safe 的多棒解 |
| **Stage 3 · NLP** | 合法解內榨到最省（optimality） | 貼邊精修解 |

順序不可換：NLP 是固定維度局部優化、自己不能增減棒數，必須先由 Split 把棒數與合法暖啟定下來。

---

## Stage 1 · DE（修改現有搜尋）

- **可拆的燒不扣 −10**，改用**拆棒 surrogate** 計真實代價：被迫的 `(n_seg−1)×MIN_COAST` 時間 +
  ΔV overhead。→ 即現有 `SPLIT_AWARE_SEARCH`，**但要補終端棒**（現在只做中間棒；終端 Lambert
  超標時也要改成 surrogate、不是 −10）。
- DE 只搜低邏輯棒數（1~3），**不再**用棒數逼近拆完段數。
- **接縫①：handoff 結構**——交給 Stage 2 的不只是決策向量，要含：每發燒大小/方向/時機、
  哪幾發超標、**鎖定的 A(T)**（抵達時刻 + 瞄準點）。

## Stage 2 · Split（= joint NLP 拆分器，Stage 2/3 合併）

**重要修正（2026-09-11，重讀 HAP47_SPLIT_ALGORITHM_RESEARCH §4/§7 後）**：正確的核心演算法
不是貪婪 `split_even`，而是 **HAP-47 §4 建議、PoC 驗證過的 joint NLP 拆分器**——把貪婪逐段
換成一次 SLSQP，所以原本分「Stage 2 貪婪 + Stage 3 NLP」**合併成一個 joint NLP**。

- **決策變數**：全部 `num_burns` 棒的（時刻/滑行比例、方向球座標、大小）一起優化，**不再區分
  錨點/收尾**（§2e：錨點+拆分共同優化，修掉現行「錨點寫死網格、跟收尾脫鉤」的缺陷）。
- **原生約束**（SLSQP ineq）：每發 ≤`MAX_DV_SOFT`、間隔 ≥`MIN_COAST`、`arc_safe`（近地點）、
  命中 A(T) ≤容許。約束函式用既有 `arc_safe`/`check_constraints`/`reaches_perigee`，跟
  `fast_fitness_evaluator` 同一套（collision-check 一致性是硬要求）。**設計成判定函式可替換**
  （傳入而非寫死），HAP-20 攝動/雙曲線落地後不用重寫。
- **目標函數**（§2c）：「棒數少 + 早到 + 離上限有餘裕」，不是純總 Δv。
- **段數 N**（§2d）：離散，NLP 不直接優化——對候選 N 各跑一次取最好。**N 的候選由貪婪
  `burn_splitter`（Phase 1）動態掃出**（`ceil(dv/cap)` 起跳），不必人手改 MAX_BURNS。
- **warm start**：貪婪 `burn_splitter` 的合法解 + 現行錨點網格的幾個最好結果（避免 NLP 從零
  猜收斂到爛局部解）。
- **接縫③：失敗要誠實**——NLP 不可行就回報，**絕不靜靜吐違規解**。

**貪婪 `burn_splitter`（Phase 1 已建）的定位**：降級為 **N-finder + warm-start 產生器**，不是
最終演算法。它保證「找得到一組合法+命中+Earth-safe 的分解」，joint NLP 再從它出發優化。

### PoC 挖到、必須記住的事實（§7.1）——注意別把它用錯（2026-09-11 修正）

**唯一「平」的是**：在**總 Δv 固定**的前提下，把它怎麼分配到各棒——均分 vs 極端不均分，得分
幾乎一樣（`calculate_score` 燃料項只看總 Δv、不管分配）。

**但拆分器的工作不是分配固定的總 Δv，是決定總 Δv 本身**，所以拆分器對分數**非常重要**：
- 兌換率 **每省 1 m/s ≈ +0.000918 分**（contest.json 工作點）。PoC 那 +0.0033 分就是總 Δv
  省 3.5 m/s 換來的。
- 貪婪等量分會替 splitting 自己墊高總 Δv（壓力測試 6.8× 案例：10,148 → ~13,000 m/s，多噴
  ~2,800）。回收其中一部分 = 零點幾分，量級遠大於 0.008。
- **0.008 在這個比賽是名次級的量**：初賽我們 98.31 輸 Team15 的 98.3162 是 0.0062；joint NLP
  的 98.3177 足以把第一、二對調。研究備忘錄 §328 明說「HAP-47 不該降級」。

推論：**Stage 1（DE）決定總 Δv 的地板，拆分器決定合法化時會不會把地板又墊高**——兩個都是
分數主戰場，不是「只有 Stage 1 重要」。

## 橫跨全管線（易爆接縫）

1. **棒數變動態** → 下游全要能吃事後才定的棒數：GMAT script 生成、分數拆解、規則§6 平手判定、報告。
2. **Earth-safe 重驗兩次**：Stage 2 拆完、Stage 3 精修完，各跑一次 `fast_fitness_evaluator`
   （唯一抓得到撞地球，見 collision-check-verification-gap 記憶）。拆棒會製造中途近地點下潛。
3. **可行性閘門**：進管線前用能量下限 `min_burns=ceil(floor/cap)`（[optimizer.py:1520](../src/optimizer.py)
   已有雛形）先判有沒有合法解，免得白拆。

## 收尾

- 種子端 pcsplit / split_even-as-seed 變冗餘 → 移除或降級（relay/ladder 當找路線種子可留）。
- 修 doc/code 矛盾：「HAP-47 預設關」vs `default=True`、「HAP-47」一名三義、`split_even` 是第四個拆分器。

---

## 執行順序（低風險優先）

- **Phase 1（已完成）：貪婪 `burn_splitter`（N-finder + warm start）+ contest.json 試金石。**
  ✅ 動態段數、命中驗證、Earth-safe 都過（10,148 m/s → 10 段合法、命中 0km）。
- **Phase 2（核心已驗證 2026-09-11）：joint NLP 拆分器**（= 合併後的 Stage 2，`burn_splitter.
  joint_nlp_split`）。free-ECI 全棒自由變數、原生約束（cap/近地點/命中）、目標函數 = 真實
  `calculate_score`（總 Δv + 早到），warm-start 用貪婪解。
  ✅ 壓力測試（6.8× 案例、N=11）：總 Δv **13,123 → 12,516 m/s（省 607）**、命中 2.72km（軟容許
  3.5 內、留 GMAT 餘裕）、全棒 ≤1498、**分數 +0.2085**、13.8s。證實「省 Δv 直接換分」、拆分器對
  分數很重要（遠大於 0.008）。
  **待補**：(a) 對候選 N（N−1/N/N+1）各跑取最好；(b) GMAT 定燒驗證；(c) 接真 DE 路線（Phase 3）。
- **Phase 3（核心已驗證 2026-09-11，含 GMAT）：DE 贏家 → route handoff → 拆分 → joint NLP → GMAT。**
  解碼標準決策向量成 route（前導 ECI 棒 + 終端攔截）餵給 `legalize_route`。
  ✅ **端到端頭條結果**（contest.json，快速縮減 DE）：DE 贏家 **88.3219（4691 m/s 終端、1 違規、
  −10）→ 拆成 5 棒合法、98.3121、違規=0、總 Δv 6187（甚至比原本 6189 低）**，GmatConsole 定燒
  驗證 Δr_min=3499.9m、InterceptSuccess=True、全棒合規 → **交得出去**。**淨賺 +9.99 分**（拿回
  −10、拆棒幾乎不加 Δv，印證「分數對怎麼拆是平的」）。
  期間修掉 `legalize_route` 一個 bug：NLP 把可行暖啟推到不可行時會把 greedy 解一起丟；改成暖啟
  也當候選、取 feasible 最高分（`_eval_free`）。
  **結論修正**：DE 贏家的 4691 終端**可拆**（不是之前一度誤判的「不可拆」）——split-aware DE 從
  「必要」降為「錦上添花」（能找到更好的可拆路線，但現行 DE 的贏家拆分器已能救到 98.31）。
- **Phase 4（已完成 2026-09-11）：接進 main.py。** `legalize_violating_winner()` 在 Earth-safe 閘門
  後、產腳本前自動觸發（DE 贏家有違規且 Earth-safe 時）：解碼標準決策向量 → `legalize_route` →
  換掉 burns/times/mission_info，後面產腳本/GMAT/紀錄全用合法版。旗標 `strategy.AUTO_SPLIT_LEGALIZE`
  （預設 True，設 false 退回舊行為）。
  ✅ **端到端 `main.py --config`（縮減版）實跑**：DE 88.32 → 🔧 自動拆分 98.31（零違規）→ GMAT
  一般版 DC 收斂+命中+合規、定燒版命中+合規 **「👉 可以直接繳交」**、run_history 寫入、regression 5/5。
  **剩餘（非阻塞收尾）**：移除種子端冗餘 pcsplit/split_even-as-seed、修 doc/code 矛盾（HAP-47 一名
  三義、ENABLE_NLP_SPLIT_REFINE 預設值）、把 scratchpad 驗證收斂成正式回歸測試。

## 驗證

- `run_regression.py` 全綠（管線預設關時零改變）。
- contest.json 端到端：4691 → 合法多棒、Earth-safe、GMAT 命中、違規=0。
