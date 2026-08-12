# 這個工具怎麼算出任務規劃的

給想知道「這個分數/這組燃燒方案是怎麼跑出來的」的人看。怎麼**用**這個工具（安裝、設定、執行、看輸出）請看 [README.md](README.md)，這份只講背後的原理跟為什麼這樣設計。

規則本身的正式定義以 `rules/` 裡的官方 PDF 為準，這份文件只是把「規則 → 程式碼怎麼實作」這條路徑講清楚。

---

## 1. 問題是什麼

- **太空船 A**：只受重力（可選 J2 攝動）影響，被動、不機動。
- **太空船 B**（我方）：可以執行多次瞬時脈衝機動 Δv_k。
- **目標**：在時間上限 `T_max = T_MAX_PERIOD_MULTIPLE × A的軌道週期` 內，讓 B 跟 A 的相對距離 Δr 降到 ≤ 5 km（視為攔截成功），同時兼顧燃料消耗（ΔV_team）跟任務時間（T_team）。
- **限制**：單次機動 Δv ≤ `MAX_DV_MPS`、兩次機動間至少間隔 `MIN_MANEUVER_INTERVAL_SEC` 秒。
- **關鍵細節**：規則只要求 Δr ≤ 5 km，超過門檻的精準度**不會多加分**——`Δr_min = max(實際距離, 5)`。這一點對整個設計策略影響很大，後面第 5 節會再展開。

這些數字全部是 `config.json` 的 `rules` 區塊，見 README。

---

## 2. 整體流程

```
config.json (軌道六根數 + 規則參數)
        │
        ▼
① 軌道初始化：poliastro 算出 A/B 在 t=0 的 (r₀, v₀)
        │
        ▼
② L-SHADE 全域搜尋（粗略但快，JIT 加速，數千次評估探索解空間）
        │
        ▼
③ L-BFGS-B 局部微調（在②找到的解附近精修，有安全回退）
        │
        ▼
④ 高精度重播：含 J2 的 Lambert 微分修正，算出最終燃燒清單跟預估分數
        │
        ▼
⑤ 產生 GMAT script → 自動呼叫 GmatConsole 無頭驗證
        │
        ▼
outputs/output.txt (GMAT script) + 終端機印出 Python 預測 vs GMAT 實測對照
```

②③④ 都在 [`src/optimizer.py`](src/optimizer.py) 的 `MissionOptimizer` 裡；①用 [`src/propagator.py`](src/propagator.py)；⑤在 [`src/script_generator.py`](src/script_generator.py) + `main.py` 的 `run_gmat_verification`。

---

## 3. 物理模型：軌道怎麼傳播

核心是 [`src/core_math.py`](src/core_math.py) 的 `propagate_rk4`：

- **動力學方程**（`fast_dynamics`）：二體重力 `-μr/|r|³` 加上 J2 攝動項（地球扁率造成的重力場二階項）。`USE_J2=false` 時 J2 項係數直接設 0，退化成純點質量模型。
- **積分方法**：RK4（四階 Runge-Kutta），固定 **60 秒**步長。
- **為什麼是固定步長，不是自適應步長**：查證過對 LEO 型軌道大概有 ~108 m 的積分誤差，但因為第 6 節提到的安全邊界（1.5 km）遠大於目前觀察到的最大落差（~900 m），評估後決定先不做自適應步長，把複雜度留到真的需要的時候。

這整套是純 Numba JIT（`@njit`）編譯的，本身跑起來很快；真正的計算量來自「這個傳播器會被叫幾百萬次」（下面第 6 節），不是傳播器本身慢。

---

## 4. 決策變數怎麼編碼成一個最佳化問題

`fast_fitness_evaluator`（`optimizer.py`）吃的是 mealpy 丟進來的一維陣列 `x`，結構是：

```
[t_wait, (r, θ, φ, coast_frac) × (N-1), final_leg_frac, offset_r, offset_θ, offset_φ]
```

- `t_wait`：任務開始後等多久才開第一槍。
- 中間 N-1 次燃燒（如果燒 N 次）：每次是 **球座標** `(r, θ, φ)` + 這次燃燒後要滑行多久（`coast_frac`，映射到實際秒數）。
  - **為什麼用球座標，不是直角座標 `(x, y, z)`**：球座標的 `r` 本身就是 Δv 大小，把 `r` 的上下界直接夾在 `[0, MAX_DV_SOFT]`，天生保證每一組解都合規。舊版用直角座標 `(x,y,z)` 各自 `±MAX_DV`，會留下「三軸合成起來超標」的無效角落，靠事後扣分排除，浪費搜尋預算在不合法的解上。
- 最後一次燃燒不是直接給 Δv 向量，而是 `final_leg_frac`（決定這一段飛多久）+ `offset_r, offset_θ, offset_φ`（決定「瞄準 A 附近哪一點」），實際的 Δv 交給 Lambert 反推——見下一節。

---

## 5. 最後一棒：Lambert 攔截 + 命中容許範圍的利用

最後一次機動用的是 **Lambert 問題**求解：已知出發點 `r_curr`、抵達點 `r_aim`、飛行時間 `t_final_leg`，反推需要多大的初速度才能剛好在那個時間點抵達那個位置。用的是 poliastro 的 `izzo` 演算法（純 Numba，速度很快）。

**這裡的關鍵設計是命中容許範圍的利用**：規則只要求 Δr ≤ 5 km 就算成功，且 `Δr_min` 會被地板夾在 5（`max(實際距離, 5)`），所以瞄準 A 的**精確位置**跟瞄準 A 附近容許球內隨便一點，只要都在 5 km 內，得到的距離分數完全一樣——但需要的 Δv 可能差很多。所以最後一棒不是死盯著 A 的真實位置打，而是讓 `offset_r/θ/φ` 這三個決策變數自己去找「容許球內最省油的落點」：

```
r_aim = A在intercept_time的位置 + offset向量
```

`offset_r` 的上界是 `MISS_TOLERANCE_SOFT`（見第 6 節的安全邊界），保證最終瞄準點一定落在規則允許的範圍內。

其他兩個實作細節：

- **順向/逆向都算，取 Δv 較小的**：`izzo` 分 `prograde`/`retrograde` 兩種轉移方向，A/B 兩軌道傾角差大時，逆向解常常明顯省油（實測省一半以上），只算順向會漏掉更好的解。
- **`refine_lambert_burn` 的 J2 差分修正**：`izzo` 給的是「無擾動二體」下的理想解，但真實世界有 J2。這個函式把 `izzo` 的猜測值丟進含 J2 的 `propagate_rk4` 裡，用牛頓法（三個座標軸各自做一次有限差分算 Jacobian）反覆修正，直到收斂到「加入 J2 後仍然準確命中瞄準點」的 Δv。邏輯上等同 GMAT 的 `Target/Vary/Achieve`（DC1）在做的事，只是搬進 Python 裡先做一次，不用真的開 GMAT 就能高精度預覽分數。

---

## 6. 安全邊界：為什麼不卡在規則的精確邊界上

搜尋跟微調階段用的「內部目標」都比規則的真實上限更嚴一點，理由是**避免數值誤差/模型落差把解推過合法邊界**：

| 邊界 | 內部值 | 真實規則 | 為什麼要留 |
|---|---|---|---|
| Δv 上限 | `MAX_DV_SOFT = MAX_DV - 10 m/s` | `MAX_DV_MPS` | 避免 L-BFGS-B 微調的數值梯度在邊界上把解推過真正的 ΔV_lim 才被扣分 |
| 命中容許範圍 | `MISS_TOLERANCE_SOFT = MISS_TOLERANCE_KM - 1.5 km` | `MISS_TOLERANCE_KM`（≤5km） | GMAT 打靶的 `Achieve` 每軸容許誤差只有 0.01 km，理論最差合起來 ~17m，但實測跨多種軌道幾何做壓力測試後發現，J2 以外的殘餘模型落差不是穩定的幾十公分等級——SMA 差距懸殊（LEO 對到接近 GEO 高度）的情境實測落差衝到 863 m。1.5 km 留了將近一倍的緩衝 |

這些都是「目前測過的情境」歸納出來的經驗值，不是嚴謹的數學上界。正式測資公布後拿到真實軌道參數，最好針對那組實際場景再測一次確認邊界仍然夠用（見 STATUS.md 的待辦）。

---

## 7. 最佳化演算法

### 全域搜尋：L-SHADE
[mealpy](https://github.com/thieu1995/mealpy) 的 L-SHADE（差分演化的一種自適應變種）。目標函式（`fast_fitness_evaluator`）裡有好幾處硬跳躍（撞地球直接判 0 分），不連續、不可微，比起需要梯度資訊的方法，DE 類的演化演算法比較適合。

- **族群大小**：`n_dims × POPSIZE`（決策變數維度數 × config 設的倍數），不是固定總數。舊版公式在低燃燒次數時會嚴重超編（1 次燃燒只有 2 維決策變數，舊公式卻給 360 個個體，等於 180 倍維度，遠超過 DE 類演算法常見的 10~20 倍維度經驗值，純粹浪費運算時間）。
- **早停**：`MAX_EARLY_STOP` 代沒有改善（超過 `TOL` 的量）就提前結束，不用每次都跑滿 `MAXITER` 代。

### 平行化
兩層平行：
1. **跨燃燒次數（process 層級）**：`config.optimization.MAX_BURNS`（例如 `[1,2,3]`）每個數字各自開一個獨立 process（`ProcessPoolExecutor`），互不干擾，同時搜尋，最後比較三者的最佳解，選分數最高的。
2. **單一燃燒次數內（thread 層級）**：`fast_fitness_evaluator` 標記 `nogil=True`（純數值運算，沒碰任何 Python 物件），mealpy 用 `mode='thread'` 讓同一代族群的評估平行跑在多條執行緒上，真的能吃到多核心而不是被 GIL 卡住。

`NUM_THREADS <= 0`（含預設 `-1`）時自動用「可用核心數 ÷ 燃燒次數案例數」估一個合理的執行緒數。

### 可重現性 vs 速度的取捨
設了 `SEED` 就會自動退回單執行緒。原因：mealpy 的 `seed=` 只控制它自己建的 RNG，但 L-SHADE 內部算突變參數用的是 `scipy.stats.cauchy.rvs`，沒有帶 `random_state`，實際上吃的是 numpy 的全域隨機狀態；而多執行緒下好幾個執行緒同時搶同一個全域 RNG，誰先誰後看 OS 排程，即使種子固定，每次跑到的執行順序還是不同——這是實測驗證過的（同 seed 關執行緒完全重現、開執行緒就對不上）。所以「要重現性」跟「要速度」二選一，沒法兩者兼得。

### 局部微調：L-BFGS-B + 安全回退
L-SHADE 找到的解丟進 `scipy.optimize.minimize`（L-BFGS-B）在窄範圍內精修（角度/方向類參數給較寬容忍度，時間類參數給較嚴格容忍度，避免微調打亂已經算好的攔截時序）。

**安全回退**：L-BFGS-B 的 `success` 只代表「收斂了」，不代表「比原本的解更好」——目標函式裡的硬跳躍讓數值梯度在不連續處不可靠，微調完分數反而變差是真的會發生的。所以一定會實際比一次微調前後的 fitness，沒有變好就退回微調前的解，並且區分「沒有改善」（scipy 自己覺得收斂了，但退步）跟「沒有收斂」（撞到 maxiter 之類，scipy 自己都不信任這個結果）兩種訊息，不要混為一談。

---

## 8. 計分公式怎麼實作的

規則第 5 節的公式（`src/scorer.py` 的 `calculate_score`）：

```
Δr = max(Δr_min, 5)
Score = 50·exp(-(Δr-5)/100)                       # 距離分：Δr=5(剛好合格) 時滿分 50，越大越衰減
      + 25 / (1 + exp(k_t·(T_team - C_t)))          # 時間分：T_team < C_t 時接近滿分 25，超過就快速衰減
      + 25 / (1 + exp(k_v·(ΔV_team - C_v)))          # Δv分：ΔV_team < C_v 時接近滿分 25，超過就快速衰減
      - 10 × 違規次數                                # 每次 Δv 超過 MAX_DV_MPS 扣 10 分
```

`k_t/C_t/k_v/C_v` 是主辦方每次比賽前才公告的環境參數（`config.rules`），跟軌道分布狀況有關；跟軌道六根數一樣，目前 repo 裡的數字都是還沒等到公告前的測試值。

`_optimize_burn_case`（搜尋階段）跟 `_replay_mission`（最終重播）都呼叫同一個 `calculate_score`，唯一差別是搜尋階段用比較粗的模型快速估分，重播階段用含 J2 微分修正過的高精度解算真實分數。

---

## 9. GMAT 驗證在做什麼、為什麼需要

Python 端（第 3~8 節）已經能自己估出一個相當準的分數，**但這不是主辦方認可的計分依據**——規則附則明講「所有結果以主辦單位驗證程式為準」。GMAT 是業界標準的任務分析工具，用的是比 Python 這邊更高階的積分器（`RungeKutta89`）跟真實重力場模型（`JGM2.cof`），所以每次執行都會自動把產生的 script 丟給 GMAT 無頭跑一次（`GmatConsole --exit --run`，不開 GUI），拿它的結果跟 Python 的預測對照。

GMAT script（[`script_generator.py`](src/script_generator.py)）裡幾個值得知道的設計：

- **`Target/Vary/Achieve`（DifferentialCorrector）**：最後一棒的燃燒方向/大小，GMAT 自己還會再修一次，讓 `ShipB` 的最終位置精準命中 `Achieve` 指定的目標點。這個目標點**必須是 Python 算好的 `aim_point`（第 5 節那個容許球內的省油偏移點），不能是 A 的精確位置**——早期版本這裡曾經是個真 bug：GMAT 的打靶目標寫死瞄準 `ShipA` 的精確位置，會讓 GMAT 自己的 DC 悄悄把 Python 刻意設計出來的「打偏一點比較省油」的方案修正掉，等於白做了第 5 節的優化。修成瞄準絕對座標的 `aim_point` 之後才修好。
- **`FinalBurnDvMps`/`FinalBurnLegal`**：GMAT 的 DC 可以自由調整最後一棒的方向/大小去命中目標點，所以它實際收斂後的 Δv 不一定等於 Python 預測的那個值。`InterceptSuccess` 只檢查距離，不檢查這個——GMAT 自己的打靶器完全可能悄悄修出一把超過規則上限的燃燒而沒人發現。所以額外算了 `FinalBurnDvMps`（真實收斂後大小）跟 `FinalBurnLegal`（是否 ≤ `MAX_DV_MPS`），兩者都要看才能確認這一棒真的合規。
- **裝飾用參數**：`DryMass`/`Cd`/`Cr`/`DragArea`/`SRPArea`/`Isp`/`GravitationalAccel` 這些欄位不影響任何計算結果——`ForceModel` 的 `Drag=None`、`SRP=Off`（阻力/太陽輻射壓根本沒開），`BurnB*.DecrementMass=false`（質量不會因燃燒減少）。純粹是 GMAT 建立物件的必填欄位，填一艘典型中型化學推進衛星的量級讓腳本看起來完整。
- **script 內容全程限定 ASCII**：GMAT 的解析器碰到中文/非 ASCII 字元會直接報錯，所以 script 裡（不是 Python 端的 print/註解，是實際寫進 `outputs/output.txt` 的內容）一律用英文。

---

## 10. 已知限制

比較完整的待辦/評估過程見 [STATUS.md](STATUS.md)，這裡只列跟這份文件內容直接相關、值得知道的限制：

- 固定 60 秒 RK4 步長（第 3 節），沒有自適應步長。
- 只探索單圈 Lambert（`M=0`），評估過多圈 Lambert (`M>0`) 但決定暫不整合（見 STATUS.md）。
- 第 6 節的安全邊界數字是從目前測過的軌道情境歸納出來的經驗值，換了完全不同的軌道幾何（例如正式測資公布後）最好重新驗證一次。
