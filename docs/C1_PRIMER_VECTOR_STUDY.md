# C1 — Primer Vector 導引：文獻探討與設計

**建立：2026-09-22。** backlog 主題 C（`docs/NEXT_ROUND_BACKLOG.md`）的前置研究。定位跟 backlog 一致：
**primer vector 不是 solver，是羅盤**——只回答「這條解缺不缺棒、該不該有更大節點、該加在哪」，
即目前用猜的問題（SPLIT_AWARE 該不該開、B1 的上界該放多寬、拆棒節點放哪）。

> 這份是**判據與可行性**文件，不是實作。動手前先讀，決定 C1 值不值得做、第一版做到哪。

---

## 0. 為什麼現在需要它（動機接上 2026-09-22 的發現）

跑 contest full budget 得到 **98.3037**（拆後、零違規），而已知同「3219 家族」的解散在
**98.30 ↔ 98.3177**（HAP-47 PoC）。查證後（見當日對話 / STATUS）：

- 拆棒器本身**確定性、已收斂、full-joint**（三個測試都指向這點），不是它拆爛。
- 0.014 的散布來自 **DE 在 SEED=None 下落到哪個近似最優路線實例**——最優解附近是**平坦、
  多峰的流形**（換面主導 → 一堆總 ΔV 只差 ~10–20 m/s 的等價路線；計分距離項在 Δr≤5km 是平台），
  而名次容差（初賽 1/2 名差 ~0.0002–0.0015）**比這些近似最優之間的縫還窄**。

問題於是變成：**我怎麼知道 DE 交出來的那條解是不是（局部）impulse-最優？缺不缺一發節點？**
這正是 primer vector 理論的本行——它給一張**最優性證書**，不必靠多撒種子碰運氣。

---

## 1. 問題精確陳述（跟教科書 rendezvous 的差異先講白）

- 動力：二體為主（決定性弧段短，J2 在該尺度動不了結論——同 `reaches_perigee` 的論證，
  `src/core_math.py`）。
- 目標：太空船 B 攔截 A。**固定末端位置**（打到 A(T) 的 5km 容許球內），**末端速度完全自由**
  ——`src/scorer.py` 無速度項（雙曲線紅利的來源）。這是**攔截 (intercept)**，不是
  **rendezvous (末端位置+速度都固定)**。
- 約束：每棒 Δv ≤ 1500 m/s（**硬上限**，不是為省油）；機動間隔 ≥ 100s；全程 Earth-safe。
- 目標函數：最小化總 ΔV（時間項次要、且在最優附近幾乎平）。

**兩個「自由度」讓我們的邊界條件跟標準 rendezvous primer 不同，務必分清：**
1. **末端速度自由**：transversality 給出 `p(t_f)` 的條件跟「末端速度固定」不一樣。我們的 scorer
   連速度成本都沒有 → 末端速度是**零成本自由**，是最乾淨的攔截變體。
2. **末端位置只需落在 5km 球內**（不是點）：嚴格說末端位置也有 5km 的鬆弛，但實務上把它當
   「固定點攔截」先做，5km 容差當二階修正。

---

## 2. Primer vector 理論回顧（Lawden → Lion-Handelsman）

**Lawden** 定義 primer vector `p(t) = -λ_v(t)`（速度的共態向量），並證明**燃料最優的脈衝軌道**
的四個必要條件：

1. `p(t)` 與其導數 `ṗ(t)` 全程連續；
2. `|p(t)| ≤ 1` 全程成立；
3. 在**每個脈衝時刻** `|p| = 1`，且**推力方向與 p 同向**（Δv ∥ p）；
4. 脈衝時刻 `d|p|/dt = 0`（|p| 在脈衝點取到極大值 1）。

直覺：`p` 是「此刻多燒一單位 Δv 對降低總成本的邊際效益方向」。`|p|=1` 代表「此處燒剛好值得」；
`|p|>1` 代表「此處燒**超值**、但你沒燒」→ 解不是最優，該在這裡插一發。

**Lion & Handelsman** 把它擴到**非最優軌道**：沿現有（次優）軌道算 `p(t)`，若某內部區間
`|p(t)| > 1`，就給出**在該處插入一發中途脈衝能降總成本**的判據，並導出插入位置/時刻的一階梯度
（往 `|p|` 峰值移動）。這就是「該不該加棒、加在哪」的嚴格答案。

---

## 3. 怎麼算 `p(t)`（STM 路線）

沿一段 coast 弧，`p(t)` 由二體變分方程（狀態轉移矩陣 STM `Φ(t,t0)`）傳播：把 STM 拆成
`Φ = [[Φrr, Φrv],[Φvr, Φvv]]`，則
```
p(t)  = Φvv(t0,t)^T p0 + Φrv(t0,t)^T ṗ0      （形式依推導慣例而定）
```
給定弧段兩端的 primer（由脈衝方向 `Δv/|Δv|` 定），中間 `|p(t)|` 就能算出來。閉式積分見
Complete Integral 那篇（中央引力場的 primer 方程有解析積分，可省掉數值 STM）。

**成本**：需要 STM（沿弧段積分或閉式）。對我們的決定性短弧，成本「中」——這也是 backlog 把 C1
標「中」不是「低」的原因之一。

---

## 4. 攔截變體的坑（backlog 明列、務必做對）

**不能直接抄 Lawden/Prussing 的 rendezvous primer 邊界公式。** 差在末端：

- rendezvous：`r(t_f)`、`v(t_f)` 都固定 → `p(t_f)` 由兩端狀態唯一定出。
- **我們（攔截，末端速度自由、且零速度成本）**：transversality 要求**末端 primer 滿足自由速度
  對應的橫截條件**——直觀上「末端不需要為匹配速度而燒」，末端脈衝純粹為**位置命中**服務，
  `p(t_f)` 的方向/大小條件因此放鬆。這會改變「末端那發該多大、primer 在末端讀數」的判讀。
- 具體橫截條件要**自己重推**（或抄對攔截的文獻，如 arXiv:1807.00285 兩脈衝攔截），不是套 rendezvous。

**另一個務必**：第一版**只在二體模型當診斷**（決定性弧段短、J2 動不了結論），定位是羅盤不是
失格線。讀數合理再談要不要上 J2/長弧。

---

## 5. 另一支線：per-burn cap 強制拆分（primer 之外）

我們拆棒**不是為省油**，是**每棒 1500 m/s 硬上限**逼的——這是 primer 之外的另一類問題
（bounded-impulse / input-constrained impulsive control）。文獻兩個要點：

- 在**anchor 位置**把大衝量分成小發，理論上**可以不損 ΔV**；我們多花的 ~20 m/s 純粹是 100s
  最短間隔逼它離開 anchor（見當日 contest 拆解：4691 → 4×~1175，+20 m/s = 0.43%）。
- 這類「上限下的最優拆分」有**凸優化 (convex) formulation**，能拿**全域最優**，直接消掉我們
  SLSQP 的局部最優/種子變異。

**兩支合起來的分工**：primer vector 說「**該不該拆、拆在哪**」（燃料最優性）；bounded-impulse
convex 說「**在上限下怎麼拆到全域最優**」。我們現在的拆棒器（平均分 + SLSQP）**兩者都不是**——
能用、但會卡局部最優，這正是 0.014 散布的來源之一。

---

## 6. 接進管線的方式（C1 → C2）

- **C1（本文件的目標）**：對 DE 贏家算 `|p(t)|`，**純診斷、不改搜尋行為**：
  - `|p| ≤ 1` 全程 → 結構已（局部）最優、不需加棒 → SPLIT_AWARE 沒開的必要（cap-bound 沒害到你，
    這就是圓軌道輪 0/14 的物理原因，見 memory `odc-split-aware-not-needed`）。
  - `|p| > 1` 區間 → 該處缺一發節點 / 現有節點位置不對 → 值得開 SPLIT_AWARE 並在該處 seeding。
- **C2（依賴 B1 + C1）**：先跑預設（中間棒夾 cap，便宜穩健）→ 對贏家算 primer →
  `|p|≤1` 收工；`|p|>1` 才用 **B1 的 energy_floor 動態上界**（已完成，2026-09-22）打開
  SPLIT_AWARE、用 primer 指的位置 seeding。**只在理論說會賺時才付昂貴寬範圍搜尋。**

---

## 7. C1 第一版建議範圍（de-risk）

1. **純二體 STM primer 計算器**：吃一條解（burns + coasts + 命中點），輸出各 coast 弧的 `|p(t)|`
   曲線與峰值。
2. **攔截末端橫截條件**：先自己推「末端速度自由 + 零速度成本」的 `p(t_f)` 條件（或抄攔截文獻），
   **單元測試**：對一個已知最優兩脈衝攔截，`|p|` 應全程 ≤1 且脈衝點 =1。
3. **對贏家診斷**：contest 贏家（含那發被拆的大棒）算 `|p|`——**預期**該大棒附近若 `|p|>1`，
   就證實「該處需要更多節點」的物理；若 `|p|≤1`，代表大棒其實在對的位置，拆只是為 cap。
4. **先當純讀數輸出**（log / 一張圖），確認合理再接 C2。不改任何搜尋行為。

**驗證資產**：用 `tests/test_hyperbolic_e2e.py` 的既有幾何 + 一個手算最優兩脈衝案例當 primer 的
golden test。BLAS 已可 pin（2026-09-22），primer 的 SLSQP/線代若有隨機性記得比照 pin。

---

## 8. 開放問題 / 風險

- 攔截橫截條件的推導要小心（別套 rendezvous）——這是 C1 成本「中」的主因。
- STM 成本：閉式積分（arXiv:2508.03075）可省數值 STM，但要驗證我們的座標/單位對得上。
- 拆棒後的多棒解算 primer 應讀到 `|p|≈1`（若拆得好）——可當拆棒器品質的**事後檢查**。
- 5km 命中容差 + 末端位置鬆弛：第一版當固定點，之後再談容差的橫截修正。

---

## 參考文獻

- Primer vector theory 綜述：<https://www.researchgate.net/publication/286848963_Primer_vector_theory_and_applications>
- Improving a Nonoptimal Impulsive Trajectory（Prussing, Oxford；Lion-Handelsman 加棒判據）：
  <https://oxford.universitypressscholarship.com/view/10.1093/oso/9780198811084.001.0001/oso-9780198811084-chapter-6>
- Mid-Course Corrections 最優化（Springer；primer 插中途棒的現代流程）：
  <https://link.springer.com/chapter/10.1007/978-3-319-23986-6_9>
- Optimal Two-impulse Space Interception（arXiv:1807.00285；**攔截變體**，末端速度非固定）：
  <https://arxiv.org/pdf/1807.00285>
- Complete Integral of Primer-Vector Equations（arXiv:2508.03075；central-field 閉式積分，算 p(t)）：
  <https://arxiv.org/pdf/2508.03075>
- Bounded-impulse convex：Collision Avoidance Multiple-Impulse Convex（arXiv:2101.07403）
  <https://arxiv.org/pdf/2101.07403>；Input-Constrained Impulsive Optimal Control（arXiv:2510.03423）
  <https://arxiv.org/pdf/2510.03423>
