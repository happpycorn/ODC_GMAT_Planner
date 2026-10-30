# 中段大燒路線：問題、已知事實與實作規劃（2026-10-29）

狀態：規劃已定，程式還沒動。依據：Corn 的 GLOBAL_ORACLE 報告（`origin/codex/global-oracle` 1f6c739 的
`docs/research/GLOBAL_ORACLE_20261028.md`，尚未合併）與本文 §2 的 Mac 量測。

## 1. 問題

`hyper_far` 最好的路線家族是「任務中段燒一發 585–680 m/s 的前導棒，終端棒約 1,300 m/s（多圈 Lambert）」，
兩棒 oracle 拆後 82.6473。管線當天設定只拿 82.4327：前導棒幾乎不燒，終端棒約 1,900 m/s 拆成 8 段。差的 0.215 分全在燃料。

管線拿不到的原因：

- **搜尋對兩種棒的規則不對稱。** 排位賽模式下，前導棒的上界是 248 m/s；終端棒允許到 14 × cap，用拆後估計評分
  （`SPLIT_AWARE_TERMINAL`，`src/optimizer.py:565`）。600 m/s 的前導棒要用三發合法小棒湊，方向、時刻、大小都得對上，DE 幾乎湊不到。
- **放寬前導棒的開關有，但沒在用。** `SPLIT_AWARE_SEARCH` 放寬前導棒上界（`_split_aware_dv_ub`，上限
  `SPLIT_AWARE_MAX_FACTOR` × cap，預設 3），並預付 2% 燃料加間隔時間。它預設關，只在 primer 判定要插棒時由短重搜打開；
  hyper_far 的 7 次重搜，插進去的前導棒都是 0.0 m/s。從頭放寬、跑完整搜尋還沒人試過。
- **拆棒器只拆終端棒。** `main.legalize_violating_winner` 不拆超標前導棒，重播直接判失格。oracle 拿得到，是靠
  `oracle_common.presplit_leading` 先把前導棒等分成間隔 MIN_COAST 的幾段。

未知：smoke、contest 沒有這個家族；排位賽規則下其他題目多常出現，沒有資料。9 月「0/14 不需要中段大棒」
（`docs/research/HAP67_SPLIT_AWARE_INVESTIGATION.md`）是初賽 1,500 m/s 上限下的結論，不適用。

## 2. 已量到的事實

### 2.1 oracle 在 Mac 上的時間（Codex 實測，numba 快取已暖）

| 情境 | 網格 | 前 10 名精修＋拆棒 | 合計 | 最好的合法分數 | Corn |
|---|---|---|---|---|---|
| hyperbolic_smoke（h=350） | 32 s | 34 s | 65 s | 86.7847 | 106 s，86.7847 |
| hyper_far（h=1,626） | 23 s | 168 s | 192 s | 82.6473 | 225 s，82.6473 |

精修＋拆棒每條約 17 s、平均 1.7 核，可平行分給閒置核心。hyper_far 最好的那條拆前排第 4，K 不能低於 5。冷啟動 numba 編譯約 17 s。

### 2.2 可拆性（hyper_far，80 條分層抽樣的兩棒路線實拆，32 條成功）

原始資料在本 session scratchpad 的 `codex-splitmap.md`、`splitmap/results.csv`。

| 情況 | 成功 |
|---|---|
| 兩棒都 ≤ 約 1,900 m/s | 22/25 |
| 終端棒 > 2,000 m/s | 2/22，幾乎都是末段仍超過 248 m/s |
| 前導棒 > 約 1,900 m/s | 多數失敗，多半是拆後總 Δv 超過 3 km/s 或要超過 14 段 |

- 失敗不是傳播不準：末段超限時瞄準殘差約 1e-8 km；失敗的挑 15 條改二體重拆，仍有 14 條失敗。原因是容量：段數多、
  燒的時間拉長（(N−1)×100 s），後面的段離最佳位置越遠。
- 前導棒 ≤ 1,000 m/s 的樣本沒有一條因前導棒而失敗。沒有「兩棒都 ≤ 1,000」的樣本，因為 hyper_far 總共至少要約 1,900 m/s。
- 前導棒等分後終端需求會變（例：終端 286 m/s 的路線，等分後要 4–7 km/s），所以拆前數字預測不準，要實拆才知道。
- Corn 報告的 1,886 m/s「拆棒盲點」：原始 x 沒存，照摘要重建的路線四種組合都拆得出來，但只有 82.560，低於 82.6473。不再追。

### 2.3 拆棒成本

沒有乾淨的「棒大小 → 多花多少燃料」曲線。零散資料：contest 終端棒拆前 6,189 → 拆後 6,180–6,190 m/s；
`hyperbolic_test` 拆後估計高估 0.435 分；oracle 的 600 m/s 前導棒拆 3 段後，精修總量 1,892 m/s 反而低於拆前二體估計 1,910 m/s。
前導棒的 2% 預付是猜的。

## 3. 規劃

```
階段 0（同時開始）  E1 頻率測試（Corn）      第 1 步 拆棒也拆前導棒（Mac）
                         \                         /
階段 1                    依 E1 結果決定（§3.3）
                                   |
階段 2                    第 2 步＋多臂比較（§3.4）
```

### 3.1 E1：中段大燒家族在排位賽規則下多常出現（Corn，不改程式）

- 用 `origin/codex/global-oracle` 的研究碼，對約 10 題排位賽規則的題目（每發 250 m/s、總 Δv 3 km/s、J2–J4），
  每題跑管線當天設定（`configs/shared/ranking_round.json`，種子 0–2，各行程不同 SEED）與兩棒 oracle（K=10，網格步長 T_max/100）。
- 題目：hyper_far、hyperbolic_smoke 當錨點（要重現 82.4327／82.6473 與 86.7847），其餘隨機產生 B／A 軌道，
  範圍貼近排位賽題庫（含雙曲線 A）；產生方式要寫清楚並存檔。
- 每題回報：管線最好合法分數、oracle 最好合法分數、差值、oracle 贏家的前導棒與終端棒大小、兩邊牆鐘、oracle 前 10 名的拆前排名與拆後分數。

### 3.2 第 1 步：拆棒階段也拆前導棒（Mac，交 Codex 實作）

- 新旋鈕 `strategy.SPLIT_LEADING`（預設關）。開啟時，`legalize_violating_winner` 之前把超過 MAX_DV_SOFT 的前導棒
  等分成 ⌈|Δv|/cap⌉ 段、間隔 MIN_COAST、以原時刻為中心（移植 `presplit_leading`，不 import 研究碼），再交給既有的 `legalize_route`。
- 重播與挑贏家：前導棒超標但開了 `SPLIT_LEADING` 的，算「可拆」而不是失格，跟終端棒一樣用拆後結果參與比較；primer 重搜的新舊比較改成兩邊都拆完再比。
- `SPLIT_AWARE_MAX_FACTOR` 確認可設 4（1,000 m/s），設定驗證器同步。
- 驗收：完整回歸全過（目前 27/27）；旋鈕關閉時 smoke fixture 跟 Master 逐位元相同；新單元測試涵蓋「600 m/s 前導棒路線開旋鈕後合法」與「等分後各弧撞地球檢查」；
  hyper_far 用 oracle 最好的那條路線（`standard_x_from_route` 轉成 x）走一次產品下游，拆後 ≥ 82.64。

### 3.3 階段 1 的決策規則

「oracle 贏」= oracle 最好合法分數比管線高 ≥ 0.05。E1 的非錨點題目裡：

| oracle 贏的題數 | 下一步 |
|---|---|
| ≥ 3 | 階段 2 全部四臂 |
| 1–2 | 階段 2 只做 A、C（oracle 當附加候選，不投資放寬搜尋） |
| 0 | 停在第 1 步（預設關），oracle 不接進管線 |

### 3.4 階段 2：第 2 步與多臂比較（Corn 跑比較）

第 2 步：oracle 跟 DE 同時跑，用 DE 沒用到的核心；前 K 名（K=10）經 `standard_x_from_route`（N=2）轉成 x，
走跟 DE 贏家完全相同的下游（重播 → 拆棒 → §6 排名鍵 → 全攝動重瞄準 → GMAT）。旋鈕 `ORACLE_TWOBURN`、`ORACLE_TWOBURN_WALL_SEC`、`ORACLE_TWOBURN_K`。

| 臂 | 設定 |
|---|---|
| A | 現行預設 |
| B | `SPLIT_LEADING` + `SPLIT_AWARE_SEARCH` 從頭開、`SPLIT_AWARE_MAX_FACTOR`=4 |
| C | `SPLIT_LEADING` + `ORACLE_TWOBURN` |
| D | B + oracle 前 K 名放進 DE 初始族群當種子 |

題目：E1 裡 oracle 贏的題目、hyper_far、hyperbolic_smoke、contest，種子 0–4。比：合法分數、牆鐘、最好的解通過全攝動重瞄準＋GMAT。
smoke 與 contest 分數不能掉（86.7847、98.3193）。

## 4. Session 分工

| Session | 地點 | 內容 | 交付 |
|---|---|---|---|
| E1 | SSH 主機 Corn | §3.1 | 報告檔＋每題原始結果，不改程式 |
| 第 1 步 | Mac，獨立 worktree | §3.2，Codex 實作、session 驗收 | 分支 `codex/split-leading`，不合併 Master |
| 階段 2 | E1 與第 1 步都回報後再開 | §3.3 決策、§3.4 | — |

## 5. 先不做

- **終端可拆上限 14 倍降到約 8 倍**：§2.2 顯示 > 2,000 m/s 幾乎拆不掉，降下來能少追拆不掉的路線；但跟中段大燒無關，另案。
- **拆前估分不準**：80 條裡 19 條拆前總 Δv 在 3 km/s 內、拆後超過；B 臂會受影響，先看 B 臂結果再說。
- **加大 MAXITER**：同樣時間跑 oracle 更划算（225 s 就超過 20 顆大預算的最好結果）。
- **族群整批 prange**、**SEARCH_COAST_RTOL 改預設**（維持 1e-12，1e-9 當長 T_max 加速旋鈕）。

## 6. 風險

- 只在 hyper_far 證實有 0.215 分；E1 就是用來確認值不值得。最壞情況是第 1 步預設關、oracle 不接，程式行為不變。
- 前導棒拆成多段，段數變多，joint NLP 變大、拆棒時間變長；拆棒牆鐘預算（600 s）仍是保險。
