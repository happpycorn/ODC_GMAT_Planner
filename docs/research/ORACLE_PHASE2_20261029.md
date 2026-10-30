# 階段 2：兩棒 oracle 接進管線，四臂比較結果（2026-10-29～30）

依據：`docs/research/ORACLE_INTEGRATION_PLAN_20261029.md` §3.4。分支 `claude/oracle-phase2-20f0b0`，未合併 Master。

## 1. 結論

- **建議比賽預設開臂 C**：`SPLIT_LEADING=true`、`ORACLE_TWOBURN=true`，其他 oracle 旋鈕用預設（K=10、WALL_SEC=600、GRID_DIV=100）。
- `SPLIT_AWARE_SEARCH`（臂 B）和 `ORACLE_TWOBURN_SEED_DE`（臂 D）**維持關閉**。
- 前導棒等分拆法目前**不必改**。

預設值還沒改，程式裡這幾個旋鈕仍然是關的。要不要改由使用者決定。

理由見 §4。

## 2. 改了什麼（commit）

| commit | 內容 |
|---|---|
| 355e400 | 拆棒階段也拆前導棒（`SPLIT_LEADING`），階段 1 |
| 14b7849 | 兩棒 oracle 移植到 `src/oracle_twoburn.py`，含 `vallado_safe` 修正；背景行程 `src/oracle_worker.py`；`main._solve_with_oracle` 讓 oracle 的前 K 名與 DE 贏家走同一條下游，用 §6 排序鍵比較；`ORACLE_TWOBURN_SEED_DE` 把 oracle 解塞進 DE 初始族群；驗證器與 README 同步更新 |
| ef87f65 | `SPLIT_AWARE_SEARCH` 與 `SPLIT_LEADING` 同時開時，搜尋改用跟重播一樣的計分方式。這兩個旋鈕同時開時，B/D 臂原本會丟掉 2 棒大前導棒解；ef87f65 修掉這個問題。修正只在兩者同開時生效，所以臂 A 預設逐位元不變。細節見 `docs/research/SPLIT_AWARE_SEARCH_FIX_20261029.md` |
| 9808cbc | Corn 四臂比較的原始結果，放在 `docs/research/oracle_phase2/` |

Mac 驗收結果：
- 完整回歸全過。
- 旋鈕全關時，smoke 的結果與分支起點逐位元相同（14b7849、ef87f65 各比一次，numba 快取清空後重跑）。
- 新單元測試通過。
- hyper_far 開 `ORACLE_TWOBURN`（seed 0）拆後拿到 82.6445，驗收門檻是 ≥ 82.64。

## 3. 結果

### 3.1 設定

- 機器：Corn，Ryzen 7 5800X（8 核 16 緒），WSL2。
- 每個 run 只求解，`--slots 2`。執行緒：BLAS 類都設 1，`NUMBA_NUM_THREADS=4`。
- 規模：6 題 × 4 臂 × 種子 0–4，共 120 個 run。全部 ok、合法，沒有崩潰也沒有逾時。
- 題目設定：e1_r4/r5/r8、hyper_far、hyperbolic_smoke 套排位賽 base；contest 用它自己的規則。

各臂用的 commit：
- A：14b7849。ef87f65 只動到 B/D 會走的路徑，A 不受影響。
- B、D：ef87f65。
- C：primer 重搜有觸發的 14 個 run 用 ef87f65 重跑，其餘 16 個用 14b7849。重跑前後分數差 ≤ 1e-4。

設定細節見 `docs/research/oracle_phase2/summary.md`。

### 3.2 每題每臂分數（Corn 求解，拆後合法分數）

| 題目 | A 最好／中位 | B 最好／中位 | C 最好／中位 | D 最好／中位 | C 的 oracle 勝出 |
|---|---|---|---|---|---|
| e1_r4 | 78.5084／78.3720 | 78.3720／78.3720 | **78.6077／78.6077** | 78.6034／78.3720 | 5/5 |
| e1_r5 | 68.6633／68.5243 | 68.5243／68.5243 | **68.7464／68.7463** | 68.7464／68.5243 | 5/5 |
| e1_r8 | 76.3562／76.3313 | 76.3313／76.3313 | **76.5343／76.5343** | 76.3313／76.3313 | 5/5 |
| hyper_far | 82.4327／82.4327 | 82.5777／82.5461 | **82.6446／82.6445** | 82.5826／82.5826 | 5/5 |
| hyperbolic_smoke | **86.7864**／86.7847 | 86.7847／86.7847 | 86.7847／86.7847 | 86.7847／86.7834 | 5/5（平手） |
| contest | 98.3193／98.3193 | 98.3193／98.3193 | 98.3193／98.3193 | 98.3193／98.3193 | 5/5（平手） |

「oracle 勝出」以 run.log 出現兩次「拆棒前贏家已存檔」判定，因為只有選中 oracle 候選時才會再存一次。smoke 和 contest 的分數差 ≤ 1.1e-5，算是平手，由 §6 排序鍵改比 Δr／ΔV 分出勝負，分數和 A 一樣。（10-30 更正：第一版把這些平手判成 DE 勝出，寫成 0/5 與 1/5。）

護欄：smoke 必須 ≥ 86.7847、contest 必須 ≥ 98.3193。四臂的最好值都過。

但最差值有掉：
- smoke：B 有 2 顆種子、D 有 3 顆種子是 86.7834。
- contest：B 有 2 顆、D 有 1 顆是 98.3192，差 1e-4，在噪音底線上。

另外 B 在 hyper_far s1 只有 82.1095，e1_r8 s3 則是 B 和 D 都只有 75.7968。

### 3.3 牆鐘（Corn，整個 run，中位／最大，秒）

| 題目 | A | B | C | D |
|---|---|---|---|---|
| e1_r4 | 126／225 | 94／200 | 195／266 | 159／264 |
| e1_r5 | 113／265 | 103／104 | 287／327 | 178／314 |
| e1_r8 | 360／367 | 195／331 | 256／377 | 265／400 |
| hyper_far | 272／513 | 401／451 | 406／601 | 443／450 |
| hyperbolic_smoke | 190／191 | 144／181 | 197／204 | 210／225 |
| contest | 200／206 | 194／207 | 255／300 | 255／259 |

C 的 oracle 在背景跑，牆鐘中位 157–326 s，大致決定了 C 的總牆鐘。D 的同步網格每次約 65 s。

Mac 只量過一個 C run：hyper_far C s0 求解 678 s（10 核，其中 4 顆效能核；oracle 分到 6 核）。這比 Corn 的 406 s 慢，但仍遠低於排位賽的 60 分鐘。

### 3.4 Mac 全攝動重瞄準＋GMAT（每題每臂最好的那個 run）

做法：
- 排位賽題：`main.py --from-mission <mission.json> --retarget-full-perturbation`，GMAT R2026a。
- contest：只跑一般的 `--from-mission` GMAT 驗證，因為 contest 不是排位賽全攝動規則。

每個解都用它求解時的 commit 來驗證，因為 `load_mission` 的版本防呆要求兩者一致。14b7849 的解是在 detached worktree 裡跑的。原始結果在 `docs/research/oracle_phase2/mac_retarget.json`。

**24/24 全部通過**：重瞄準 accepted；固定燃燒版 GMAT 命中、Earth-safe，單棒與總 Δv 都合法。

| 題目 | 臂（種子） | Corn 拆後分數 | 重瞄準後官方分數估計 | GMAT 固定燃燒 Δr (m) | 總 Δv (m/s) | 最大單棒 (m/s) |
|---|---|---|---|---|---|---|
| e1_r4 | A (s0) | 78.5084 | 78.5105 | 12.5 | 1501.8 | 247.98 |
| e1_r4 | B (s0) | 78.3720 | 78.3686 | 14.3 | 1513.9 | 247.98 |
| e1_r4 | C (s0) | 78.6077 | **78.6077** | 10.3 | 1494.4 | 248.05 |
| e1_r4 | D (s1) | 78.6034 | 78.6038 | 7.5 | 1494.7 | 247.98 |
| e1_r5 | A (s4) | 68.6633 | 68.6361 | 78.3 | 2197.0 | 247.98 |
| e1_r5 | B (s3) | 68.5243 | 68.5398 | 86.3 | 2206.5 | 247.98 |
| e1_r5 | C (s0) | 68.7464 | **68.7634** | 88.8 | 2185.4 | 247.98 |
| e1_r5 | D (s0) | 68.7464 | **68.7634** | 87.1 | 2185.4 | 247.98 |
| e1_r8 | A (s0) | 76.3562 | 76.3461 | 22.6 | 1869.4 | 248.91 |
| e1_r8 | B (s0) | 76.3313 | 76.3214 | 7.9 | 1871.7 | 247.98 |
| e1_r8 | C (s0) | 76.5343 | **76.5266** | 12.7 | 1852.9 | 247.98 |
| e1_r8 | D (s0) | 76.3313 | 76.3214 | 7.9 | 1871.7 | 247.98 |
| hyper_far | A (s0) | 82.4327 | 82.4173 | 471.5 | 1921.7 | 247.98 |
| hyper_far | B (s4) | 82.5777 | 82.5626 | 142.6 | 1902.9 | 249.32 |
| hyper_far | C (s0) | 82.6446 | **82.6362** | 320.6 | 1893.4 | 247.98 |
| hyper_far | D (s0) | 82.5826 | 82.5739 | 250.1 | 1901.5 | 247.98 |
| hyperbolic_smoke | A (s4) | 86.7864 | **86.7825** | 4.1 | 639.7 | 248.51 |
| hyperbolic_smoke | B (s2) | 86.7847 | 86.7807 | 3.8 | 639.9 | 247.98 |
| hyperbolic_smoke | C (s0) | 86.7847 | 86.7807 | 3.7 | 639.9 | 247.98 |
| hyperbolic_smoke | D (s0) | 86.7847 | 86.7807 | 3.7 | 639.9 | 247.98 |
| contest | A (s3) | 98.3193 | GMAT 合計 98.32 | 3,496 | 6182.9 | — |
| contest | B (s0) | 98.3193 | GMAT 合計 98.32 | 3,495 | 6182.9 | — |
| contest | C (s1) | 98.3193 | GMAT 合計 98.32 | 3,496 | 6182.9 | — |
| contest | D (s2) | 98.3193 | GMAT 合計 98.32 | 3,495 | 6182.9 | — |

- **重瞄準後名次不變。** 4 題排位賽題都是 C 最高。C 比 A 多的分數：e1_r4 +0.097、e1_r5 +0.127、e1_r8 +0.181、hyper_far +0.219。smoke 是 A 的 s4 比 C 高 0.0018；A 其他種子是 86.7847，與 C 相同（見 §5）。
- 重瞄準只改最後一棒。各解改動後的總 Δv 差都 < 3 m/s，分數變化在 ±0.03 以內。
- 有 4 個解的最大單棒超過 248 m/s 的軟上限：e1_r4 C、e1_r8 A、hyper_far B、smoke A。四個都 < 250 m/s，所以合法。

### 3.5 B、D 臂的拆棒失敗分類（使用者要的表）

分類的判定方法見 `docs/research/oracle_phase2/classify_split_failures.py` 開頭說明。等分後的終端需求是 log 裡沒印的數字，用產品程式自己算：
1. `route_from_standard_x` 解碼路線。
2. `presplit_leading` 等分前導棒。
3. J2–J4 傳播到終端起點。
4. `_lam_best`＋`_shoot_final` 求出終端需求。

驗算：用同樣方法重算拆前終端棒，與 mission 的值差 ≤ 0.001 m/s。

| 臂 | 前導棒等分後終端需求暴增 | 終端棒本身拆不開 | 無前導棒等分 | 需要拆棒的 run | 有超標前導棒的 run |
|---|---|---|---|---|---|
| B | 0 | 0 | 2 | 30 | 10 |
| D | 0 | 0 | 1 | 30 | 12 |

| run | 前導棒 (m/s) | 拆前終端棒 (m/s) | 結果 |
|---|---|---|---|
| e1_r4 B s0 | 0.0 | 1517.1 | HAP-67 拆不出，C4 旗標關重搜救回，最後 78.3720 |
| e1_r8 B s4 | 0.0；0.0 | 1866.3 | 同上，最後 76.3313 |
| e1_r8 D s4 | 0.0；0.0 | 1866.3 | 同上，最後 76.3313 |

- **兩類失敗都是 0 筆。** 3 筆失敗的拆前路線都是一發大終端棒，沒有前導棒，所以不是等分拆法造成的。
- 有超標前導棒的 22 個贏家全部拆成功。前導棒大小：smoke 283–528 m/s、e1_r4 595.5 m/s、contest 1500 m/s。等分後終端需求是拆前的 0.93–1.03 倍，沒有暴增。明細在 `docs/research/oracle_phase2/leading_presplit_ok.csv`。
- 結論：這批資料沒有證據顯示前導棒等分拆法有問題，目前不值得改。

已知的反例在別處：規劃文件 §2.2 記過，有一條終端 286 m/s 的路線，等分後終端要 4–7 km/s。它出現在 hyper_far 的分層抽樣路線裡，不在管線實際選出的贏家中。

## 4. 建議的比賽預設與理由

| 旋鈕 | 建議 | 理由 |
|---|---|---|
| `SPLIT_LEADING` | 開 | C 臂必須開（驗證器強制）；單開不影響沒有超標前導棒的解，有的話照等分拆，22/22 成功 |
| `ORACLE_TWOBURN` | 開 | 4 題排位賽題 5/5 種子都由 oracle 勝出，重瞄準＋GMAT 後仍比 A 高 0.10–0.22 分。5 顆種子分數相同，等於把「抽到好種子」變成必然。smoke、contest 也是 5/5 選中 oracle，但只是平手，分數與 A 相同。代價是 Corn 牆鐘中位比 A 多 −104～+174 s（e1_r8 反而較快）、最多 601 s，Mac 上 hyper_far 678 s，都遠低於 60 分鐘 |
| `ORACLE_TWOBURN_K` / `_WALL_SEC` / `_GRID_DIV` | 維持 10 / 600 / 100 | oracle 最長 325 s，沒碰到 600 s 上限；Mac 上 hyper_far 勝出的那條拆前排 index 5（第 6 名），K=10 有餘裕，再小就有風險 |
| `SPLIT_AWARE_SEARCH`（B） | 關 | 只在 hyper_far 比 A 好（仍低於 C），而且有 82.1095、75.7968 兩個低分；跨機器非確定性（smoke s0 Mac 86.6855 vs Corn 86.7847，修正前） |
| `ORACLE_TWOBURN_SEED_DE`（D） | 關 | 不穩定：e1_r4 只有 2/5、e1_r5 只有 1/5 達到 oracle 水準，其餘種子跟 B 差不多；C 全面不輸 D |

## 5. 沒驗證到的地方

- **題目只有 6 題。** e1 系列是人工題，正式賽題的軌道未知。oracle 只在有「中段大前導棒」路線家族的題目上占優，smoke 和 contest 都沒有這個家族。
- **smoke s4 的 86.7864 是種子運氣，SPLIT_LEADING 只在這顆種子上改變了結果。** Corn 對 A、SL（只開 `SPLIT_LEADING`）、C 各跑種子 0–9。3 棒 86.7864 只有 A 的種子 4 拿到（1/10），SL、C 都是 0/10，其餘種子都是 86.7847（SL 種子 5 是 86.7834）。
  - 種子 4 上，primer 重搜會打開 `SPLIT_AWARE_SEARCH`。C 本來就開 `SPLIT_LEADING`，所以重搜的 DE 目標走 `split_leading_abi` 分支：超標前導棒只預付燃料，不判失格。結果 DE 走到大前導棒盆地，3 棒解根本沒被產生。
  - SL 與 C 逐值相同，所以和 oracle 無關。14b7849 的舊 C 也一樣，所以和 ef87f65 的修正也無關。
  - 1/10 對 0/10 無法區分是不是系統性擋掉；差距 0.0017 分。
  - 查的時候順便發現：拆後估計把兩條路線排反了。A 路線估 86.4464、實際 86.7864；C 路線估 86.6377、實際 86.7847。也就是終端棒拆棒的預付（`SPLIT_AWARE_TERMINAL_DV_OVERHEAD`）相對偏重，前導棒的 2% 預付相對偏輕。這只在 smoke 一題上看到，沒驗證其他題，也沒調參。
  - 詳見 `docs/research/oracle_phase2/smoke_s4_diff/summary.md`。
- **Mac 牆鐘只量過 hyper_far C s0 一個 run。** 其他題在 Mac 上的 C 臂牆鐘，以及比賽當天 Mac 的核心分配，都沒量。
- **oracle 逾時被砍的路徑**（超過 WALL_SEC 時 killpg、保留已完成候選）沒在實跑中觸發過，只有單元測試覆蓋。
- **重瞄準＋GMAT 只驗了每題每臂最好的那 1 個 run**，不是 120 個全驗。
- **primer 重搜在 `SPLIT_LEADING` 關時**（臂 A 預設）搜尋與重播仍不同尺。這是已知問題，刻意保留以維持預設逐位元不變，要另外決定要不要修。
- **臂 B 跨機器非確定性**沒有在 ef87f65 之後重新量。
- **Mac 上 contest 的 B/C/D 護欄不能採用**：那些 run 跑的時候 Codex 正在改程式，所以結果作廢。contest 護欄以 Corn 的 98.3193 為準。
- **Linux 實機只在 Corn（WSL2）跑過。** 120 個 run 沒有崩潰，也沒有孤兒行程的跡象；但沒有特別檢查子行程清理。

## 6. 原始資料

- `docs/research/oracle_phase2/summary.md`：Corn 的完整摘要，含各臂 commit、重跑清單、異常與注意事項。
- `docs/research/oracle_phase2/runs.csv`：每個 run 一列。
- `docs/research/oracle_phase2/runs/<題>_<臂>_s<種子>/`：mission.json、winner_presplit、oracle_candidates。
- `docs/research/oracle_phase2/sweeps/`：四臂的 results.jsonl 與 summary，含被取代的舊 C 結果與 14b7849 護欄。
- `docs/research/oracle_phase2/split_failures.csv`、`leading_presplit_ok.csv`、`classify_split_failures.py`。
- `docs/research/oracle_phase2/smoke_s4_diff/`：smoke 種子 4 差異調查（A／SL／C 各 10 顆種子）。
- `docs/research/oracle_phase2/mac_retarget.json`：§3.4 的 Mac 重瞄準＋GMAT 結果。
- `sweeps/phase2_arm{A,B,C,D}.json`：sweep 規格。
