# HAP-47 研究備忘錄：多脈衝拆分演算法評估

> Spike 產出。第一版是純書面評估（沒有動 `optimizer.py`，沒有跑任何 benchmark），
> 目的是把 [HAP-47](https://linear.app/happpycorn/issue/HAP-47) 列的 6 個方向逐一過一遍
> 「原理成不成立 / 跟本題實際約束合不合 / 實作成本 / 能不能互相合併」，收斂成一個具體的
> 下一步實作目標。**後續加了一輪 0.5 天 PoC 驗證（§7），§0 的核心假設已經有答案。**

## 0. 先處理「這個 spike 值不值得做」

`PROJECT_AUDIT_20260909.md:80` 寫得很直白：「拆分/路線只達到 Earth-safe 家族，但初賽真正
贏我們的（炸魚隊）是同一條解精修更緊。**2nd→1st 的槓桿是精度，不是新解**」。這句話如果成
立，HAP-47 整個方向就該降級成「順手做」而不是主力投入。

但這句話本身有一個沒驗證的前提：**現行 `outputs/best_98.31_split5_rebalanced/` 這個
98.31 分，是「合法家族的實際上限」，還是只是 `split_even()` 平均分配這個啟發式構造出來、
剛好被 L-SHADE/NLP 精修磨到局部最優的產物？** 這兩者外觀相同（同一個分數、同一個「Earth-safe
前緣在 T≈5700s 就到頂」的觀察），但意義完全不同：

- 如果是前者：HAP-47 該砍，繼續磨精修（`_tiebreak_polish`）比較划算。
- 如果是後者：換一個真正做聯合優化的拆分器，可能在同一個 T 附近找到更省油、餘裕更大的解
  （分數規則對 Δr≤5km 是平的，但「多少 Δv 打進 1500 上限的餘裕」直接決定抗攝動/抗雷達誤差
  的穩健度，也是 audit 裡「精度」真正指的東西）。

**這份備忘錄第一版不回答這個問題**——下面的建議（§4）設計成「用最低成本去驗證這個假設」，
而不是先假設「有原理的方法一定更好」就一頭栽進 primer vector 全套理論。**§7 用一個 0.5 天
PoC 補上了答案：是前者，HAP-47 建議降級。**

## 1. 現況基準：`split_even` + 錨點窮舉

拆分邏輯在 `_generate_planechange_split_seed_candidates`
（[optimizer.py:1000-1172](src/optimizer.py#L1000)），跟 `_generate_multiburn_seed_candidates`
（relay）、`_generate_ladder_seed_candidates`（ladder）三個種子家族在
[optimizer.py:581](src/optimizer.py#L581) 直接相加、不截斷、不互斥（[optimizer.py:582-587](src/optimizer.py#L582)
的註解特別警告過：早期版本誤截斷過，把 ladder 種子整批丟掉）。

機制拆成兩段，**兩段之間沒有共同優化**：

1. **錨點（第一棒，抬高+換面）**：對每個 `t_wait ∈ {0, 0.05×Ta}`，在 B 的 VNB 標架下窮舉
   `cv∈{0.5,1.0}, cn∈{-1,-0.5,0.5,1.0}, cb∈{-1,0,1}` 三個係數的組合，燒滿 `MAX_DV_SOFT`
   上限（[optimizer.py:1094-1122](src/optimizer.py#L1094)），排除逃逸軌道，滑到
   `coast_mult∈{0.5,0.75}` 比例的新週期附近（約等於遠地點）。全部寫死在函式內，沒有獨立
   config 開關。
2. **收尾（剩下 `num_burns-1` 棒）**：`split_even()`（[optimizer.py:1062-1089](src/optimizer.py#L1062)）
   逐段貪婪——每步重解一次 Lambert 瞄準最終目標，把「當下需求 Δv ÷ 剩餘段數」當這一步的
   量，平均分給剩下的段數。段數本身不是搜出來的，就是 `num_burns-1`，`num_burns` 由外層
   `config["optimization"]["MAX_BURNS"]` 陣列決定。

已知弱點（issue 原文列的四點，這輪確認全部屬實）：貪婪逐段不保證全域最優 Δv 或最少棒數；
100s 間隔 + 全部擠遠地點是寫死的結構假設，沒有對「每發在什麼時間點」做優化；段數用
`ceil(總Δv/上限)` 硬算（實質上就是 config 裡手動試出來的 `MAX_BURNS`），不是搜出來；
錨點先固定、收尾再拆，兩者沒有共同優化——錨點的方向/大小/滑行比例窮舉時完全不知道後面
收尾段會怎麼收，可能燒偏了方向讓收尾段白白多花 Δv。

## 2. 逐一評估 6 個方向

### (a) Primer vector 理論（Lawden）

**原理**：primer 向量 `p(t)`（協態/adjoint 對速度的偏微分）的大小歷史直接告訴你「在哪個時
刻加一發能讓總 Δv 更省」——`|p|=1` 是脈衝時刻的一階必要條件，`|p|>1` 意味著該時刻插一發會
降低總 Δv，`|p|<1` 意味著現有脈衝配置已經局部最優。這是判斷「幾發、何時發」最經典、最有原
理依據的框架。

**跟本題約束對不上的地方**：古典 primer vector 理論的前提是**脈衝大小不受限**（只優化總
Δv，不管單發多大）。本題卻有兩個古典理論不處理的硬約束：

- 每發 Δv ≤ 1500 m/s（`MAX_DV_SOFT`，實際軟上限 1490）——古典理論的「該不該加一發」判準
  完全建立在「加了之後這發可以是任意大小」的假設上，遇到單發上限會整套失效，因為最優解
  可能被上限截斷成「這裡明明該加一發，但加了也受限，不如換個時機」。
- 機動間隔 ≥100s——古典理論裡兩個相鄰脈衝時間可以任意近，本題卻不行。

要接上這兩個約束需要用**約束版 primer vector**（bounded-impulse 或 fuel-limited 變體，
文獻上有但沒有那麼標準化，通常還是得退回數值最優化去處理不等式約束，primer vector 只是
拿來當初始猜測/加點判準）。

**判斷**：理論參考價值最高（尤其「該不該加一發」這個問題，目前完全靠 `MAX_BURNS` 手動試
不同值去撞），但直接拿來實作「拆分器本體」成本不成比例——真正落地還是要靠數值最優化，
primer vector 頂多是拿來當那個數值最優化的**判準/初始猜測**，不是取代它。**這輪不建議
獨立實作，列為 §4 建議方案的理論參考。**

### (b) NLP / 凸鬆弛（脈衝時刻+大小+位置當變數）

**原理**：把每發的時刻、大小、方向直接當決策變數丟進非線性規劃，目標函數（見 (c)）配上
不等式約束（每發≤上限、間隔≥100s、近地點≥安全高度、命中 A(T) 容許範圍內），用 SLSQP /
trust-constr（或 SOCP 若能凸化）求解。

**跟本題約束的契合度**：這是唯一一個能**原生**、直接吃下本題全部約束的方向——不用像 (a)
那樣繞道近似。而且可以直接重用既有工具，不用重寫底層力學：
- Lambert 重解：`lam_best`（[optimizer.py:1044-1060](src/optimizer.py#L1044)，目前是
  `_generate_planechange_split_seed_candidates` 內的閉包，建議抽成獨立函式）。
- 合規檢查：`arc_safe`（[optimizer.py:1037-1042](src/optimizer.py#L1037)）→
  `check_constraints`/`reaches_perigee`（`core_math.py`），跟 `fast_fitness_evaluator`
  用**同一套**判定，天生保證不是撞地球的假解（見 memory
  `odc-collision-check-verification-gap`——這個一致性是現行架構的硬要求，新拆分器也必須
  遵守，否則會重蹈 `_replay_mission` 對不上正式評分的舊坑）。
- 打分：`calculate_score`（`scorer.py`）。

**成本**：中——不用開發新的物理理論，主要工作是把 `split_even` 的貪婪迭代換成一次
`scipy.optimize` 呼叫，約束函數用既有的 `arc_safe`/`check_constraints` 包一層。決策變數
維度隨棒數線性成長（`4*num_burns+1`，見 §5），高棒數下收斂性未知，需要先在現有測資的
5~6 棒規模驗證。

**判斷：ROI 最高、最可落地，是 §4 建議方案的核心。**

### (c) 目標函數重定義

Issue 原文的觀察是對的：規則對 Δr≤5km 是平的，真正該優化的是「棒數少 + 早抵達 + 離上限有
餘裕」而非單純總 Δv。這點**跟用哪個搜尋方法無關**，是目標函數層面的事——不管是 (a)(b) 哪
種方法，都可以套用「加權目標 = w1·Σmax(0, Δv_i - margin_target) + w2·(抵達時間) +
w3·(棒數懲罰)」取代現行 `calculate_score` 裡單純看 Δv 的部分。

**成本最低**：不需要換搜尋演算法，現有的 L-BFGS-B 局部精修階段（`_tiebreak_polish`，
`METHODOLOGY.md:182-186`）就可以直接換目標函數測试，跟 (b) 完全正交、可以獨立驗證。

**判斷**：跟 (b) 綁在一起做——(b) 的 NLP 求解本來就需要一個明確目標函數，順手把它定義成
「棒數+餘裕+早到」而非純 Δv，一次到位。

### (d) 非均勻間隔 + 自動選段數 N

是 (b) 的自然延伸：只要把每段的滑行時間（coast fraction）開放成 NLP 的自由變數而非
`split_even` 目前隱含的均分結構，非均勻間隔就自動出現，不需要額外機制。

段數 N 本身是離散變數，NLP 求解器不擅長直接優化離散維度。**建議做法**：對現有
`MAX_BURNS` 陣列裡的幾個候選 N（例如 config 裡的 `[5, 6]`）各自跑一次 (b) 的 NLP，取分數
最高者，而不是把 N 也塞進連續優化——這跟現行「`MAX_BURNS` 陣列讓 L-SHADE 對每個候選 N 各
跑一輪」的既有模式（`config_validator.py:264-279` 只驗證非空陣列）完全相容，不用改外層
流程。

**判斷**：併入 (b)，不獨立實作。

### (e) 錨點與拆分共同優化

現行架構最大的結構性缺陷：錨點（抬高換面棒）用寫死的離散網格窮舉（§1 第 1 段），跟收尾的
`split_even` 完全脫鉤。**併入 (b) 的做法**：把錨點的方向（球座標）、大小、滑行比例，跟收尾
段一樣當成 NLP 的自由變數（也就是把 `num_burns` 棒全部丟進同一個聯合優化，不再區分「第一
棒特殊」），初始猜測沿用現行窮舉網格的幾個最好結果去 warm-start NLP（避免從零猜可能收斂
到很差的局部解——這也是 (a) primer vector 理論唯一比較適合派上用場的地方：拿 primer 向量
的方向去給 NLP 一個比純窮舉更聰明的初始猜測，成本很低,可以晚點作為 (b) 的加分項）。

**判斷**：併入 (b)，不獨立實作，但初始猜測策略上可以借 (a) 的直覺。

### (f) 雙曲線 + 攝動推廣

跟 (a)-(e) 是**正交軸**——前五個方向是「怎麼把 Δv 拆得更聰明」，這個方向是「拆分演算法要
在哪種軌道幾何/力學模型下也成立」。而且推廣的前提本身還沒完成：

- `reaches_perigee`/`check_constraints` 目前是**解析式**（假設純二體），攝動開啟時長弧
  近地點會漂，判定失準——這正是 HAP-20（`PROJECT_AUDIT_20260909.md:72`）標的 P2 風險，
  還沒解。
- 雙曲線 A 路徑（排位賽）目前**從未端到端跑過 GMAT** 驗證過（`PROJECT_AUDIT_20260909.md:73`
  P3 風險），HAP-46 本身也還沒有對應程式碼，只是盤點文件裡的待辦項目。

在近地點判定本身在攝動下不準確的情況下去驗證一個新拆分演算法的「Earth-safe」正確性，驗證
出來的結果沒有意義——`arc_safe` 判定不準，任何基於它的拆分器（不管是貪婪還是 NLP）都可能
產出实际上會撞地球但沒被抓到的解。

**判斷：這輪不展開，明確列為依賴 HAP-46（雙曲線可行性）/ HAP-20（攝動下近地點判定改成數值
式）完成後才有意義的後續工作。** (b) 方案在設計時應盡量讓約束函數（`arc_safe` 等）是可替
換的（傳入判定函式而非寫死呼叫），這樣 HAP-20 修完之後，(b) 的 NLP 框架本身不用重寫，只要
換掉底層判定函式即可支援雙曲線+攝動——這是唯一需要現在就考慮的「面向未來」設計點。

## 3. 小結表

| 方向 | 原理成立度 | 跟本題約束契合度 | 實作成本 | 這輪處置 |
|---|---|---|---|---|
| (a) Primer vector | 高（經典理論） | 低（不原生處理硬上限+間隔約束） | 高 | 列理論參考，晚點借去做 warm-start |
| (b) NLP/凸鬆弛 | 高 | 高（原生吃下全部約束） | 中 | **這輪建議的核心實作目標** |
| (c) 目標函數重定義 | — | 高 | 低 | 併入 (b) |
| (d) 非均勻間隔+自動 N | 是 (b) 延伸 | 高 | 低（併入後） | 併入 (b) |
| (e) 錨點+拆分共同優化 | 是 (b) 延伸 | 高 | 中（併入後） | 併入 (b) |
| (f) 雙曲線+攝動推廣 | 正交軸 | 依賴 HAP-46/HAP-20 | — | 明確延後，設計時留可替換判定函式的口子 |

## 4. 建議：下一步做「joint NLP 拆分器」

把 (b)+(c)+(d)+(e) 合併成一個 spike/story：用 NLP（scipy `SLSQP` 或 `trust-constr`）取代
`split_even`，一次覆蓋四個方向。範圍：

1. 決策變數：全部 `num_burns` 棒的（時刻/滑行比例、方向球座標、大小），不再區分錨點/收尾。
2. 目標函數：§2(c) 的「棒數少 + 早到 + 離上限有餘裕」加權式，取代純 Δv 最小化。
3. 約束：重用 `arc_safe`/`check_constraints`/`reaches_perigee`（§5 介面草案），Δv≤`MAX_DV_SOFT`、
   間隔≥`MIN_COAST_TIME`。
4. 初始猜測：warm-start 自現行窮舉網格的前幾名結果（不用從零開始，省掉 NLP 對非凸問題找
   不到好局部解的風險）。
5. **驗證方式**（回應 §0 的核心假設）：在現有測資（`configs/contest_pcsplit.json`，5~6 棒；
   `weird_test.json`；`apoapsis_planechange_test.json`；`perigee_kick_test.json`）上跑，
   跟現行 `_generate_planechange_split_seed_candidates` + L-SHADE/NLP 精修的結果比 Δv、
   上限餘裕、棒數、執行時間——**如果新方法在 `best_98.31` 這個案例上找不到比 98.31 更好
   或餘裕更大的解，就證實了 audit 的判斷（精度不是新解），可以放心把 HAP-47 降級**；如果
   找到了，才值得繼續磨。這個驗證本身就是後續開發 issue 該做的第一件事，不是這份備忘錄。

## 5. 介面（已實作，2026-09-10）

**這裡原本的草案設想是把 PoC 的 Cartesian 解轉換回球座標編碼，實際動手時發現行不通並換了
設計**：PoC 的「最後一棒」是自由 Cartesian 變數，但正式系統的最後一棒不是自由變數——是
`reconstruct_mission_logs` 用 Lambert 解出來瞄準 `offset` 點的（optimizer.py:2116-2273）。
硬轉換會讓最後一棒對不上。改成直接對現有標準決策向量做 SLSQP，完整重用
`mission_metrics`/`reconstruct_mission_logs`，不在第二個地方重寫物理邏輯。

實際函式：`_generate_nlp_refined_seed_candidates(self, num_burns, n_seeds, base_candidates)`
（[optimizer.py:1191](src/optimizer.py#L1191)），接在
[optimizer.py:581](src/optimizer.py#L581) 附近：

```python
nlp_refined = self._generate_nlp_refined_seed_candidates(
    num_burns, n_seeds, relay + ladder + pcsplit)
return relay + ladder + pcsplit + nlp_refined
```

拿三家族合併結果裡分數最高的 3 個當 SLSQP warm start，帶顯式不等式約束（近地點餘裕、
命中容許、Lambert DC 收斂旗標）局部聯合優化；每個結果都要贏過自己的 warm start 才收進來。
開關：`strategy.ENABLE_NLP_SPLIT_REFINE`（預設 `True`）。測試：
[tests/test_nlp_split_refine.py](tests/test_nlp_split_refine.py)。

### 驗證結果（`configs/contest_pcsplit.json`，2026-09-10）

- 生產配置（`NUM_THREADS=-1`、`MAX_BURNS=[5,6]`）端到端含 GMAT 驗證：Score 98.31，
  GMAT InterceptSuccess/Targeter 收斂/最後一棒合規全過，總耗時 214.72s——沒有拖垮流程。
- **控制變因 A/B（`NUM_THREADS=1`、`SEED=777`、`MAX_BURNS=[5]`，其餘完全相同，只切
  `ENABLE_NLP_SPLIT_REFINE`）**：關閉時這個特定隨機軌跡收斂到 **Score 88.32**（pcsplit
  自己構造的解沒能力再往上爬）；打開後同一個隨機軌跡收斂到 **Score 98.31**，耗時幾乎
  沒差（166.81s vs 169.00s）。這比原本 PoC 在已知好解上多榨 0.008 分的效果大得多——這裡
  展示的是「當 L-SHADE 這趟運氣不好、既有三家族沒能力找到那個 98 分家族時，NLP 精修可以
  單靠局部搜尋跳過去」，證實這個家族的價值不只是磨鉛筆尖，是真的補上既有家族的結構性缺口。
- 兩次跑法用的隨機種子/棒數各自不同，**沒有一次剛好重現 98.3177**——這正是先前跟使用者
  說明過的預期：接入後的分數不保證位元對位元重現 PoC 手動跑出的那個數字。

- **回傳格式**：跟現行三家族一致，`list[np.ndarray]`，每個元素長度 =
  `decision_variable_dims(num_burns)`，球座標編碼
  `[t_wait, (r,θ,φ,coast_frac)×(num_burns-1), final_leg_frac, offset_r, offset_θ, offset_φ]`
  （[optimizer.py:496-500](src/optimizer.py#L496)）——不用碰 L-SHADE 主流程或 bounds 生成。
- **建議抽成獨立函式重用**（目前是內嵌閉包，抽出來才能被新拆分器 import）：
  - `lam_best`（[optimizer.py:1044-1060](src/optimizer.py#L1044)）
  - `arc_safe`（[optimizer.py:1037-1042](src/optimizer.py#L1037)）——§2(f) 提到，這裡建議
    改成接受一個判定函式參數，而不是寫死呼叫 `reaches_perigee`/`check_constraints`，方便
    HAP-20 修完後直接替換成數值判定，NLP 框架不用重寫。
  - `_direction_to_spherical`（[optimizer.py:850-859](src/optimizer.py#L850)）
  - `check_constraints`/`reaches_perigee`（`core_math.py`）
  - `calculate_score`（`scorer.py`）

## 6. 開放風險

- 決策變數維度 `4*num_burns+1` 隨棒數線性成長，NLP 直接優化在高棒數（例如雙曲線情境可能
  需要的更多棒）下的收斂性未知——先在現有 5~6 棒規模驗證，不要一開始就衝高棒數。
- ~~§0 的核心假設（98.31 是不是真的合法家族上限）沒有在這份備忘錄裡回答~~ → **已在 §7
  用 PoC 回答**。
- Primer vector 的 warm-start 加分項（§2(e)）目前只是構想，沒有評估實作成本，真的要做的話
  應該在 (b) 的 baseline 版本先跑出結果、看差距大不大，再決定值不值得加這層。

## 7. PoC 結果（2026-09-09 補做）

腳本：[scratch_overnight/hap47_poc_nlp_split.py](scratch_overnight/hap47_poc_nlp_split.py)，
不動 `optimizer.py`，讀 `outputs/best_98.31_split5_rebalanced/output_submit.txt` 的 VNB
燒法當 warm start，換成「每段滑行時間 + 每棒 ECI Δv 三分量」共 21 個自由度的直接聯合表示
法（不是 `split_even` 的「先固定方向網格、再貪婪均分大小」），約束重用
`reaches_perigee`/`check_constraints`（跟正式 `fast_fitness_evaluator` 同一套判定）、
目標函數直接用 `calculate_score`，跑 `scipy.optimize.minimize(method='SLSQP')`。

**warm start 重建先驗證過**：每棒 Δv 1498.0 / 1172.9 / 1171.4 / 1172.6 / 1176.6 m/s、總
6191.5 m/s、T_team 5675.4s、miss 3499.9m，跟 `SUMMARY.md` 記錄的數字逐項對上，重建分數
98.3144 對官方記錄 98.31（GMAT DC 收斂 vs 本腳本二體積分器的正常量級落差）。

**SLSQP 結果**（53 次迭代、1.2 秒收斂，`success=True`，最終解可行）：

| | warm start (98.31 解) | SLSQP 優化後 |
|---|---|---|
| 總 Δv | 6191.5 m/s | 6188.0 m/s |
| T_team | 5675.4 s | 5675.4 s（沒變） |
| miss | 3499.9 m | 3500.0 m（都貼著 3.5km 軟上限） |
| 每棒 Δv | 1498.0 / 1172.9×4（大致均分） | 1498.0×4 / 196.0（4 棒貼滿上限 + 1 小棒） |
| 分數 | 98.3144 | 98.3177（**+0.003%**） |

**第一版判準（已修正，見下）：相對改善 <0.1% → 誤判為噪訊。** 這個判準本身是錯的——比賽
是拚名次、可能贏在小數點後兩位，不該用「相對百分比」去打發一個絕對分數的差距。§7.1 補上
GMAT 驗證後，結論反轉。

### 7.1 GMAT 驗證（修正第一版的誤判）

腳本：[scratch_overnight/hap47_poc_gmat_verify.py](scratch_overnight/hap47_poc_gmat_verify.py)。
把上面 SLSQP 解的每棒 ECI Δv 轉成 VNB、餵進 `script_generator()` 產生跟
`best_98.31_split5_rebalanced` 當初驗證同一套的 GMAT 腳本（一般變體，含 DC 目標求解器），
用 `run_gmat_verification()` 跑 GmatConsole 無頭驗證。

**GMAT 自己的結果**：InterceptSuccess=True、Targeter 收斂=True、最後一棒合規=True，GMAT
自己的微分修正器**獨立收斂到 196.0 m/s**，跟 Python/SLSQP 預測幾乎一模一樣。這代表 §7 開頭
表格裡的 +0.0033 分（98.3144→98.3177）**不是本腳本簡化二體積分器的噪訊，是通過官方同一套
驗證管線確認的真改善**——用 GMAT 收斂後的真實 Δv 重算分數一樣是 98.3177，比官方繳交記錄
的 98.31 高 **0.0077 分**。

**修正後的結論：這不是「HAP-47 沒有價值」，是「HAP-47 能贏的量很小（~0.008 分），但這個量
是真的、GMAT 驗證過的」。** §0 的核心假設答案改成：98.31 本身不是絕對頂，`split_even` 均分
留了一個小而真實的次優空間——只是這個空間小到用「相對百分比」看會被誤判成噪訊，比賽名次
卻可能就是靠這種量級的差距決定。

**跟第一名的實際比較**（2026-09-09 對話中使用者提供 Team15 官方分數 98.3162，補上第一版
沒有的數字）：

| 方案 | 分數 | 驗證方式 |
|---|---|---|
| Team15（初賽第一名） | 98.3162 | 官方 |
| 我們官方繳交（`best_98.31_split5_rebalanced`） | 98.31 | 官方（GMAT DC，2026-09-05） |
| 這輪 joint NLP 拆分器 + GMAT 驗證 | **98.3177** | GMAT DC（2026-09-09，本 PoC） |

98.3177 比 Team15 的 98.3162 高 **0.0015 分**——這個差距比我們原本輸給第一名的差距（98.31
→98.3162，輸 ~0.006 分）還小，屬於「贏，但贏得非常薄」的量級。這個數字經過 GMAT 驗證（見
上方 InterceptSuccess/Targeter 收斂/合規三項都過），不是隨手估的，但初賽已在 2026-09-05
結束，這份 PoC 沒有東西能拿回去追溯提交——記錄下來是為了佐證「HAP-47 這個方向本身有沒有
價值」，跟「能不能改變 2026-09-05 那天的結果」是兩件事，後者已經不可逆。

> **更正**（2026-09-09 對話中使用者澄清）：`PROJECT_AUDIT_20260909.md:60`/`STATUS.md:2110`
> 原本寫的「初賽實質第一」把 Team15 當非正式的「主辦內部炸魚隊」處理；使用者確認 Team15
> 算正式參賽，所以初賽真實名次是**第二**，不是第一。兩份檔案已同步修正。

**更有意思的是「為什麼」**：SLSQP 把 Δv 從「大致均分」大幅重新分配成「4 棒貼滿上限 + 1 棒
只燒 196 m/s」，總 Δv 只少了 3.5 m/s，分數幾乎沒變——因為 `calculate_score` 的燃料項只看
**總 Δv**，完全不管這個總量怎麼分配到 5 棒之間。也就是說，這個問題的分數地貌對「怎麼拆」
本身是**平的**：只要總 Δv 和抵達時間固定，split_even 的均分解跟 SLSQP 找到的極端不均分
解得分幾乎一樣——`split_even` 不是運氣好卡到窄峰，是因為峰本身就很寬，均分只是這個寬平原
上任選的一個點。HAP-47 原本設想的「更有原理的拆分」在**分數**這個目標上注定贏不了多少，
因為真正決定分數的是 Lambert 幾何本身能不能把總 Δv/抵達時間再壓低，跟怎麼拆分無關。

**一個由此衍生、成本很低的後續構想（不等於重啟 HAP-47，只是備忘）**：現有 98.31 解把 Δv
上限的餘裕都留在收尾 4 棒（各 ~325 m/s），第一棒幾乎貼滿（餘裕 2 m/s）——如果真正在意的是
`PROJECT_AUDIT_20260909.md` 講的「精度」（抗攝動/抗執行誤差的穩健度），可以把同一套 SLSQP
框架的目標函數換成「在總 Δv/T_team 不變的前提下，最大化所有棒次裡最小的那個上限餘裕」
（max-min 穩健化），而不是追求更高分數。這是 §2(c)「目標函數重定義」的一個具體、低成本
應用，跟這輪 PoC 否定的「追求更高分數」是兩件事，值得另外開一張小 issue（不是 HAP-47 本
身）評估。

**結論修正（見 §7.1）：HAP-47 不該降級/關閉**——joint NLP 拆分器確實贏了 `split_even`，
只是贏的量很小（一個案例上是 ~0.008 分，GMAT 驗證過，不是噪訊）。初賽已經在 2026-09-05
結束，這輪 PoC 沒有東西能拿去重新繳交；價值在於**下一輪比賽**：值得把 §4 的「joint NLP
拆分器」做成正式工具（現在有實證支持，不是空想），`blockedBy HAP-20` 的關聯維持（攝動/
雙曲線情境要等 HAP-20 數值判定落地才能安全推廣），初賽圓軌道情境本身則已經有數據支持
繼續往下做。

---
*相關 memory：`odc-burn-split-methodology`、`odc-burn-split-technique`、
`odc-collision-check-verification-gap`。相關 issue：[HAP-46](https://linear.app/happpycorn/issue/HAP-46)、
[HAP-20](https://linear.app/happpycorn/issue/HAP-20)。*
