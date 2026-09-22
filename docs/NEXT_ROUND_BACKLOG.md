# 下一輪（雙曲線攔截）Backlog

**建立：2026-09-22。** 單一真相來源；動手做的項目從這裡挑，做完把狀態更新在該項目底下。
定位：STATUS.md 只留「現在做到哪」，這份留「接下來要做什麼、為什麼、依賴誰」。

## 範圍界定（重要）

本輪設定：**攔截被動雙曲線目標 A**，暫不考慮追逐 / 躲閃（那是 differential game，另一個工具箱，
本 backlog 不涵蓋）。核心認知轉變：

- 圓軌道 A：永遠在、任何相位可攔、無限次機會 → 值得用 phasing 種子等它繞回。
- 雙曲線 A：**只飛掠一次**，近地點附近極快、時間上一閃即過，攔截窗是**單一窄窗**，
  由「A 何時過近地點 / 何時穿 B 平面」決定。
- **紅利**：攔截末端速度自由（`scorer` 無速度項，`src/scorer.py:15-30`）→ A 那可能 >10 km/s
  的近地點高速**完全不用匹配**。這是雙曲線題最大的優勢，所有設計都要吃到它。

架構現況：雙曲線輸入端已端到端跑過（含拆棒，STATUS 2026-09-12）。`is_hyperbolic_A` 分支存在
（`src/optimizer.py:525`），T_max 對雙曲線拒絕亂猜、要求 `rules.T_MAX_SEC`（:527-533）。
**所以本輪不是重寫，是把幾個為圓軌道 A 調校的假設換成對雙曲線飛掠對症。**

---

## 依賴鏈與建議順序

```
A5 (安全網) ──► A1, A2, A3 (雙曲線專用化)
C1 (primer 診斷) ──► B1 (energy_floor 上界) ──► C2 (primer 當 split-aware 開關)
D2 (快審查) 獨立、隨手做
D1 (Earth-safe 數值複驗) 交件前必過
```

**建議動手順序**：A5 → A1 → A2 →（C1 → B1 → C2）→ A3 / A4 → D1 / D2 / 前掃工具。

> 🔧 **前提（2026-09-22 修好）**：管線現在設 SEED 就真的可重現了（先前多執行緒 BLAS 讓
> before/after 對照噪音化，A1 調查時踩到、已根治，見 STATUS「可重現性」＋memory
> odc-blas-nondeterminism）。**任何「改了跑一遍看變好變爛」的對照都靠這個才可信**——小預算
> 單場景尤其容易被臨界翻盤騙到。手動 A/B 時仍建議固定 iters/pop、看 nburn 有沒有換盆地。

---

## 主題 A — 雙曲線攔截專用化（種子 & 幾何）〔本輪主線〕

### A1. 近地點中心種子家族 ★最高價值
- **現況**：relay/ladder 種子為週期性 A 設計，用 A 週期當窗口尺度
  （`src/optimizer.py:1153-1186`，`a_period = Ta_sec or T_max/4.0`，`t_wait ∈ (0, a_period*0.05)`）。
  雙曲線下 `Ta_sec = None`（:527），窗口全退化成 `T_max/4` 的**任意猜測**，對「只飛掠一次」不對症。
- **做法**：解析算 A 的近地點通過時刻 `t_p`，直接在 `[t_p − Δ, t_p + Δ]` 密集掃 (t_wait, ToF) 的
  單/雙棒 Lambert 當種子。新增一個 hyperbolic-specific 種子產生器，與現有三家族並列。
- **預期**：高（90 分鐘預算下種子品質＝成敗，直接命中窄窗）。**成本**：中（~半天）。
- ⚠️ **嘗試後回退（2026-09-22）**：實作了「近地點中心種子家族」（解析近地點時刻 `_time_to_perigee`
  已驗證到公尺級正確；沿真近點角均勻取樣，用 `energy_floor_dv≤cap` gate 與 ladder 家族互補）。
  但**乾淨確定性 A/B（BLAS pin 後）判定為淨負**：
  - `hyperbolic_smoke`（本該幫的旗艦場景）**變爛** 86.46→85.28（688→844 m/s，2 棒/miss0 → 1 棒/miss3500）
    ——近地點種子是「空燒前綴的偽單棒」，把 SHADE current-to-pbest 拉向較差的 1 棒盆地。
  - hyper_far/test 看似微好 +0.2~0.3，但那兩個場景被 gate 靜音（0 種子），差異是 ~1e-10 FP 擾動經
    混沌 DE 放大的**噪音**，不是真 benefit。
  - **前提在現有可驗證場景不成立**：雙曲線飛掠只要 T_max 內可攔，窗口都有數千秒寬，baseline 的
    400 點粗掃（250–400s 解析度）＋relay/ladder 早就抓得到。窄窗前提要真題或刻意極端幾何才成立。
  → **已 revert（`git stash`，可復原）**。`_time_to_perigee` 正確、若 A2 要用可再取。**A2/A3 同前提，
  動手前先確認有「baseline 真的漏掉的窄窗」場景，否則多半同樣是噪音/小 regression。**

### A2. 粗掃改近地點加密 / true-anomaly-uniform
- **現況**：`n_coarse=400` **時間均勻**掃 [0, T_max]（`src/optimizer.py:662-664`）。雙曲線飛掠在時間上
  極不均勻，大量點浪費在 A 還很遠處，真正窄窗可能只落到個位數格點。
- **做法**：沿 hyperbolic anomaly（或近地點時刻附近）加密取樣。同樣點數，有用窗口密度提升數倍。
- **預期**：中高。**成本**：低（改取樣分佈，不改邏輯）。

### A3. multi-rev 邏輯與「A 週期」脫鉤
- **現況**：`revs = max(1, max_final / a_period)`（`src/optimizer.py:1032-1033`），雙曲線下 `a_period`
  退化成 `max_final/4`，無意義。繞圈的是 B 不是 A。
- **做法**：多圈改綁 B 週期；final leg 對雙曲線 A 幾乎不需 multi-rev（A 不繞回），考慮 final-leg
  預設 `revs=0` 省算力，multi-rev 只留給 B 等待階段。
- **預期**：低-中（省算力＋去雜訊）。**成本**：低。

### A4. config_validator 補雙曲線 TA asymptote 檢查（P4）
- **現況**：STATUS P4——`|TA| ≥ arccos(−1/e)` 未擋，給錯要到 poliastro 才炸。本輪 A 必為雙曲線。
- **做法**：`src/config_validator.py` 加一條 validator。
- **成本**：低（半天）。

### A5. 雙曲線 e2e 回歸測試〔先做，當安全網〕
- **現況**：STATUS 明列——`run_regression.py` / `tests/` **無任何雙曲線案例**，改拆棒或雙曲線輸入端
  沒有自動防護。
- **做法**：`tests/test_hyperbolic_e2e.py`，性質式斷言（合法 / 命中 / Earth-safe / 動態段數）。
- **成本**：低-中。**先做**——後面 A1/A2/A3 改動才有防護。
- ✅ **完成（2026-09-22）**：`tests/test_hyperbolic_e2e.py` 上線。兩層——A. 結構煙霧（雙曲線
  輸入端＋三種種子產生器對雙曲線輸入不炸，無 DE、秒級，直接守 A1/A2/A3 改種子時的 crash 回歸）；
  B. 拆棒 e2e（run_study_over_revs → legalize，小預算 DE，性質式斷言零違規/Earth-safe/命中）。
  回歸 6→7 支全綠。config 走程式內建（configs/ 被 gitignore，測試不依賴檔案）。

---

## 主題 B — Δv 上限 / 大節點搜尋

**問題根源**：規則的每棒上限是對「最終解」的合法性約束，被誤當成「搜尋變數的自然邊界」。
中間棒 bounds 硬夾 `[0, MAX_DV_SOFT]`（`src/optimizer.py:554`）→ DE 無法提出 >1500 的中間棒，
大燒只能發生在不受約束的 final leg。`SPLIT_AWARE_SEARCH` 放寬到 `MAX_FACTOR × MAX_DV`
（:555-556，預設關、factor=3）但那個 factor 是猜的：設低漏解、設高稀釋 DE 解析度。
`SPLIT_AWARE` 目前關的依據是圓軌道輪「0/14 場景需要超標中間棒」，**memory 已註明下輪雙曲線重驗**。

### B1. `energy_floor_dv` 動態上界取代固定 MAX_FACTOR
- **做法**：`dv_ub = min(MAX_FACTOR × MAX_DV, ⌈energy_floor_dv / cap⌉ × cap + margin)`。
  上界由情境實際能量差決定（`energy_floor_dv()` 已存在，`src/optimizer.py:886`，封閉解、微秒級），
  不再是永遠 3×1500。低能量差自動收窄（不稀釋搜尋），高能量差（雙曲線飛掠很可能）自動放寬到夠用。
- **預期**：中高（**直接消掉「上限不好設定」**——變成算出來的，不是調參）。**成本**：低-中。
- ✅ **完成（2026-09-22）**：`_split_aware_dv_ub()`（optimizer.py，接在 `energy_floor_dv` 後），
  `_generate_bounds` 開 SPLIT_AWARE 時改呼叫它。公式 `clamp(⌈floor/cap⌉·cap + cap, MAX_DV_SOFT,
  MAX_FACTOR·MAX_DV)`。實測上界：contest/smoke/test/narrow（floor<cap）4500→**3000**（收窄不稀釋）、
  hyper_far（floor 1885>cap）維持 **4500**（真需要）。**預設 SPLIT_AWARE 關 → 完全 inert、零回歸**
  （回歸 7/7 綠）；強制開跑 smoke 也產出合法解（85.28、2 棒、maxdv<cap、Earth-safe），新上界與拆棒
  路徑相容。**真正效益要等 C2 把 SPLIT_AWARE 適應性打開才顯現**——B1 只是把那個旋鈕從「猜」變「算」。

### B2. warped / normalized magnitude 編碼（選配）
- **做法**：magnitude 編到非線性尺度（靠近 cap 密、遠高於 cap 稀），DE 在常用區有細解析度。
  緩解「開大範圍稀釋搜尋」。**成本**：低-中。

### B3. 兩階段自適應 magnitude 邊界（選配）
- **做法**：沿用 `sweep_burns.py` 對「棒數」的粗掃→精掃哲學，用在「棒 magnitude」：階段一寬邊界＋
  低 iters 探需求，階段二收邊界再花真正預算。**成本**：中。

---

## 主題 C — Primer vector 導引（不是 solver，是羅盤）

**定位**：不取代 L-SHADE 管線，只回答「這條解缺不缺棒、該不該有更大節點、該加在哪」——
即目前用猜的問題。這也是把啟發式拆棒錨定到最優性判據（Lion-Handelsman）的方式。

### C1. 攔截版二體 primer 診斷健檢 ★解鎖後面
- 📚 **前置文獻+設計探討已寫（2026-09-22）**：[C1_PRIMER_VECTOR_STUDY.md](C1_PRIMER_VECTOR_STUDY.md)
  ——Lawden/Lion-Handelsman 判據、攔截末端(速度自由)橫截條件的坑、STM 算 p(t)、bounded-impulse
  convex 支線、C1→C2 接法、第一版範圍與 golden test。動手前先讀。
- **做法**：對贏家算 `|p(t)|`。`|p| ≤ 1` → 結構已（局部）最優、不需加棒；`|p| > 1` 區間 → 該插棒 / 位置不對。
- **兩個坑（務必）**：
  1. 需 STM。**第一版只在二體模型算當診斷**（決定性弧段短、J2 在該尺度動不了結論，同 `reaches_perigee`
     的論證，`src/core_math.py:65`）。定位是羅盤不是失格線。
  2. **攔截末端速度自由 → transversality 與 rendezvous 不同**，不能直接抄 Lawden/Prussing 的
     rendezvous primer 公式，要用攔截變體（末端 p 橫截條件放鬆）。成本因此是「中」不是「低」。
- **輸出**：先當純診斷（不改搜尋行為），確認讀數合理再接 C2。**成本**：中。

### C2. primer 當 split-aware 自動開關（依賴 B1 + C1）
- **做法**：先跑預設（中間棒夾 cap，便宜穩健）→ 對贏家算 primer →
  `|p| ≤ 1` 就收工（cap-bound 沒害到你，這就是 0/14 的物理原因）；
  `|p| > 1` 才用 B1 的 energy_floor 上界打開 split-aware、並用 primer 指的位置 seeding。
- **效益**：只在理論說會賺時才付昂貴寬範圍搜尋，且知道去哪找。同時解決「搜不到 >1500」與
  「上限不好設定」。**對雙曲線特別及時**——飛掠能量差大，很可能就是「真的需要大節點」的情境。
- **成本**：中（黏合 C1+B1）。

---

## 主題 D — Earth-safe / 驗證強化

### D1. 攝動開時 Earth-safe 數值密集複驗（HAP-20，本輪提優先級）
- **現況**：`reaches_perigee`/`check_constraints` 是點質量解析式（`src/core_math.py:50-118`）。雙曲線 A
  近地點低 → 最省油攔截幾何把 B 轉移弧壓向地球 → keep-out 從偶爾碰到變成經常是失格線；開 J2/J3/J4
  時長弧近地點會漂，而這是**失格線**（STATUS P2）。
- **做法**：至少交件前對贏家做一次數值密集取樣的 keep-out 複驗（呼應 memory
  `odc-collision-check-verification-gap`：GMAT/_replay 不抓撞地球，只有 fast_fitness 抓）。
- **成本**：中。**交件前必過。**

### D2. 審查：確認管線無 rendezvous 末端速度匹配殘留
- **做法**：grep 種子產生器與 `burn_splitter`，確認 final leg 永遠是純 Lambert 位置攔截、末端不加
  匹配棒。雙曲線下匹配近地點高速的 Δv 可能是攔截本身數倍，是致命浪費。
- **成本**：低（審查）。

---

## 跨主題工具（選配）

### Δv-vs-攔截時刻 Pareto 前掃
- **做法**：擴 `feasibility.py` / `sweep_burns.py`，沿 intercept time 掃 min-Δv，顯式化「早攔截省時間
  vs 晚一點省 Δv」的陡 Pareto，告訴你 score 甜蜜點落在近地點前或後，指導 seeding 與選解。
- **預期**：中（多目標權衡顯式化）。**成本**：中。

---

## 不要動的（已經對）
- **T_max 處理**：拒絕 4×週期公式、要求 `rules.T_MAX_SEC`（`src/optimizer.py:525-533`）。別加猜測公式。
- **scorer**：純位置攔截、無速度項——雙曲線紅利所在。別碰。
- **拆棒管線**：09-12 已在雙曲線幾何下驗過會自動合法化。保留。

---

## 待官方發題才能定案
- 計分參數 `k_t / C_t / k_v / C_v`（雙曲線輪數值未知）。
- T_max 的官方定義（雙曲線無週期，等公告填 `rules.T_MAX_SEC`）。
