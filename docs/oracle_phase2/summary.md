# 階段 2 四臂比較（Corn，2026-10-29～30）

Corn：Ryzen 7 5800X（8 核 16 緒），WSL2。只求解，不跑 GMAT。共 120 個 run（6 題 × 4 臂 × 種子 0–4），每個 run 都是 status ok，沒有 Traceback，也沒有逾時。

## 設定

- `sweep_params.py --slots 2 --timeout 3600`，環境變數 `OMP/OPENBLAS/MKL/NUMEXPR_NUM_THREADS=1`、`NUMBA_NUM_THREADS=4`。規格檔是 `sweeps/phase2_arm{A,B,C,D}.json`。
- e1_r4/r5/r8、hyper_far、hyperbolic_smoke 套用排位賽 base（`codex/e1-frequency:sweeps/e1_anchors.json` 的 base）。contest 不套 base，只加各臂的旋鈕。
- 各臂旋鈕：A 不加；B 加 `SPLIT_LEADING`、`SPLIT_AWARE_SEARCH`、`SPLIT_AWARE_MAX_FACTOR=5`；C 加 `SPLIT_LEADING`、`ORACLE_TWOBURN`（其餘用預設）；D 是 B 再加 `ORACLE_TWOBURN_SEED_DE`。
- 執行順序：以種子為外層，每個種子依序跑各臂。每次呼叫 sweep 是一個臂、一個種子、6 題，兩個 slot 並行。每批最後一個 run 可能只剩自己在跑，少了互搶，所以牆鐘會略偏低。

### 各臂用的 commit

| 臂 | commit | 說明 |
|---|---|---|
| A | 14b7849 | 不受 ef87f65 影響（SPLIT_LEADING 關） |
| B | ef87f65 | 全部 30 個用 ef87f65 跑，含護欄那 2 個重跑 |
| C | 16 個用 14b7849，14 個用 ef87f65 | run.log 出現「開 SPLIT_AWARE + 插棒種子」（primer 重搜有觸發）的 14 個 run 用 ef87f65 重跑，取代舊結果；清單見下 |
| D | ef87f65 | 全部 30 個用 ef87f65 跑，含護欄那 2 個重跑 |

重跑的 C run 有 14 個：e1_r4 s1；e1_r5 s0、s4；e1_r8 s0–s4；hyper_far s0、s4；hyperbolic_smoke s0、s1、s2、s4。
重跑前後分數到小數第 4 位都相同（e1_r5 s0/s4 68.7463→68.7464、hyper_far s0 82.6445→82.6446，其餘不變）。舊結果放在 `sweeps/phase2_armC_results_replaced_14b7849.jsonl`。
B、D 在 14b7849 跑的護欄結果：smoke s0 B 86.7847、D 85.2034；contest s0 都是 98.3193。這些沒有計入下表，原始資料在 `sweeps/phase2_arm{B,D}_guard_14b7849_results.jsonl`。

## 每題每臂結果

合法的定義：sweep 狀態 ok、未失格、Earth-safe、miss ≤ 5 km。120 個 run 全部合法，penalty_count 也全部是 0。
「oracle 勝出」的判定：最終 mission 對得上 run.log「Oracle comparison」表裡某一列 oracle，且對不上 DE 那列。這只對臂 C 有意義；臂 D 只用 oracle 當 DE 種子，沒有候選比較。
「oracle 牆鐘」取自 `oracle_candidates_seed<S>.json` 的 `wall_sec`。臂 C 的 oracle 是在背景和 DE 並行跑的；臂 D 則是在 DE 之前，同步先跑一次網格。

| 題目 | 臂 | 種子 0–4 合法分數 | 最好 | 中位 | 合法數 | 牆鐘中位／最大 (s) | oracle 勝出 | oracle 牆鐘中位 (s) | commit |
|---|---|---|---|---|---|---|---|---|---|
| e1_r4 | A | 78.5084 78.3720 78.3720 78.3720 78.3720 | 78.5084 | 78.3720 | 5/5 | 126／225 | — | — | 14b7849 |
| e1_r4 | B | 78.3720 78.3720 78.3720 78.3720 78.3720 | 78.3720 | 78.3720 | 5/5 | 94／200 | — | — | ef87f65 |
| e1_r4 | C | 78.6077 78.6077 78.6077 78.6077 78.6077 | 78.6077 | 78.6077 | 5/5 | 195／266 | 5/5 | 177 | 14b7849/ef87f65 |
| e1_r4 | D | 78.3720 78.6034 78.3720 78.6034 78.3720 | 78.6034 | 78.3720 | 5/5 | 159／264 | — | 67 | ef87f65 |
| e1_r5 | A | 68.6633 68.5241 68.5243 68.5243 68.6633 | 68.6633 | 68.5243 | 5/5 | 113／265 | — | — | 14b7849 |
| e1_r5 | B | 68.5243 68.5241 68.5241 68.5243 68.5243 | 68.5243 | 68.5243 | 5/5 | 103／104 | — | — | ef87f65 |
| e1_r5 | C | 68.7464 68.7463 68.7463 68.7463 68.7464 | 68.7464 | 68.7463 | 5/5 | 287／327 | 5/5 | 258 | 14b7849/ef87f65 |
| e1_r5 | D | 68.7464 68.5241 68.5241 68.5243 68.5243 | 68.7464 | 68.5243 | 5/5 | 178／314 | — | 67 | ef87f65 |
| e1_r8 | A | 76.3562 76.3313 76.3313 76.3313 76.3313 | 76.3562 | 76.3313 | 5/5 | 360／367 | — | — | 14b7849 |
| e1_r8 | B | 76.3313 76.3313 76.3313 75.7968 76.3313 | 76.3313 | 76.3313 | 5/5 | 195／331 | — | — | ef87f65 |
| e1_r8 | C | 76.5343 76.5343 76.5343 76.5343 76.5343 | 76.5343 | 76.5343 | 5/5 | 256／377 | 5/5 | 208 | ef87f65 |
| e1_r8 | D | 76.3313 76.3313 76.3313 75.7968 76.3313 | 76.3313 | 76.3313 | 5/5 | 265／400 | — | 65 | ef87f65 |
| hyper_far | A | 82.4327 82.4327 82.4327 82.4327 82.4327 | 82.4327 | 82.4327 | 5/5 | 272／513 | — | — | 14b7849 |
| hyper_far | B | 82.5461 82.1095 82.5777 82.4327 82.5777 | 82.5777 | 82.5461 | 5/5 | 401／451 | — | — | ef87f65 |
| hyper_far | C | 82.6446 82.6445 82.6445 82.6445 82.6446 | 82.6446 | 82.6445 | 5/5 | 406／601 | 5/5 | 326 | 14b7849/ef87f65 |
| hyper_far | D | 82.5826 82.5826 82.5826 82.5826 82.5826 | 82.5826 | 82.5826 | 5/5 | 443／450 | — | 63 | ef87f65 |
| hyperbolic_smoke | A | 86.7847 86.7847 86.7847 86.7847 86.7864 | 86.7864 | 86.7847 | 5/5 | 190／191 | — | — | 14b7849 |
| hyperbolic_smoke | B | 86.7834 86.7847 86.7847 86.7834 86.7847 | 86.7847 | 86.7847 | 5/5 | 144／181 | — | — | ef87f65 |
| hyperbolic_smoke | C | 86.7847 86.7847 86.7847 86.7847 86.7847 | 86.7847 | 86.7847 | 5/5 | 197／204 | 0/5 | 157 | 14b7849/ef87f65 |
| hyperbolic_smoke | D | 86.7847 86.7834 86.7834 86.7847 86.7834 | 86.7847 | 86.7834 | 5/5 | 210／225 | — | 66 | ef87f65 |
| contest | A | 98.3193 98.3193 98.3193 98.3193 98.3193 | 98.3193 | 98.3193 | 5/5 | 200／206 | — | — | 14b7849 |
| contest | B | 98.3193 98.3193 98.3193 98.3192 98.3192 | 98.3193 | 98.3193 | 5/5 | 194／207 | — | — | ef87f65 |
| contest | C | 98.3193 98.3193 98.3193 98.3193 98.3193 | 98.3193 | 98.3193 | 5/5 | 255／300 | 1/5 | 237 | 14b7849 |
| contest | D | 98.3192 98.3193 98.3193 98.3193 98.3193 | 98.3193 | 98.3193 | 5/5 | 255／259 | — | 69 | ef87f65 |

每題每臂最好的 run（Mac 拿它的 mission.json 做全攝動重瞄準＋GMAT）：

| 題目 | 臂 | 種子 | 分數 | 棒數 | 總 Δv (m/s) | 檔案 |
|---|---|---|---|---|---|---|
| e1_r4 | A | s0 | 78.5084 | 7 | 1501.9 | `runs/e1_r4_A_s0/mission.json` |
| e1_r4 | B | s0 | 78.3720 | 7 | 1513.5 | `runs/e1_r4_B_s0/mission.json` |
| e1_r4 | C | s0 | 78.6077 | 7 | 1494.3 | `runs/e1_r4_C_s0/mission.json` |
| e1_r4 | D | s1 | 78.6034 | 7 | 1494.6 | `runs/e1_r4_D_s1/mission.json` |
| e1_r5 | A | s4 | 68.6633 | 10 | 2194.3 | `runs/e1_r5_A_s4/mission.json` |
| e1_r5 | B | s3 | 68.5243 | 9 | 2207.7 | `runs/e1_r5_B_s3/mission.json` |
| e1_r5 | C | s0 | 68.7464 | 9 | 2186.7 | `runs/e1_r5_C_s0/mission.json` |
| e1_r5 | D | s0 | 68.7464 | 9 | 2186.7 | `runs/e1_r5_D_s0/mission.json` |
| e1_r8 | A | s0 | 76.3562 | 8 | 1868.5 | `runs/e1_r8_A_s0/mission.json` |
| e1_r8 | B | s0 | 76.3313 | 8 | 1870.7 | `runs/e1_r8_B_s0/mission.json` |
| e1_r8 | C | s0 | 76.5343 | 8 | 1852.2 | `runs/e1_r8_C_s0/mission.json` |
| e1_r8 | D | s0 | 76.3313 | 8 | 1870.7 | `runs/e1_r8_D_s0/mission.json` |
| hyper_far | A | s0 | 82.4327 | 8 | 1920.3 | `runs/hyper_far_A_s0/mission.json` |
| hyper_far | B | s4 | 82.5777 | 8 | 1901.6 | `runs/hyper_far_B_s4/mission.json` |
| hyper_far | C | s0 | 82.6446 | 8 | 1892.9 | `runs/hyper_far_C_s0/mission.json` |
| hyper_far | D | s0 | 82.5826 | 8 | 1900.9 | `runs/hyper_far_D_s0/mission.json` |
| hyperbolic_smoke | A | s4 | 86.7864 | 3 | 639.1 | `runs/hyperbolic_smoke_A_s4/mission.json` |
| hyperbolic_smoke | B | s2 | 86.7847 | 4 | 639.4 | `runs/hyperbolic_smoke_B_s2/mission.json` |
| hyperbolic_smoke | C | s0 | 86.7847 | 4 | 639.4 | `runs/hyperbolic_smoke_C_s0/mission.json` |
| hyperbolic_smoke | D | s0 | 86.7847 | 4 | 639.4 | `runs/hyperbolic_smoke_D_s0/mission.json` |
| contest | A | s3 | 98.3193 | 6 | 6182.9 | `runs/contest_A_s3/mission.json` |
| contest | B | s0 | 98.3193 | 6 | 6182.9 | `runs/contest_B_s0/mission.json` |
| contest | C | s1 | 98.3193 | 6 | 6182.9 | `runs/contest_C_s1/mission.json` |
| contest | D | s2 | 98.3193 | 6 | 6182.9 | `runs/contest_D_s2/mission.json` |

## 重點

- **臂 C 最好。** e1_r4、e1_r5、e1_r8、hyper_far 這 4 題，C 的 5 顆種子都比 A 的最好值還高，而且每顆都是 oracle 勝出：
  - e1_r4：C 78.6077，A 最好 78.5084
  - e1_r5：C 68.7464，A 最好 68.6633
  - e1_r8：C 76.5343，A 最好 76.3562
  - hyper_far：C 82.6446，A 最好 82.4327

  勝出的 oracle 候選，拆前前導棒依序是 804.9、254.1、1130.4、643.5 m/s；同一批 run 中 DE 自己的拆前前導棒多半是 0。smoke 和 contest 上 C 與 A 打平：smoke 的 oracle 最好就是 86.7847，contest 是 98.3193，有 1 次以 ulp 級差異勝出。
- **C 的代價是牆鐘。** 中位數 C 比 A：e1_r4 195 s 對 126 s、e1_r5 287 s 對 113 s、hyper_far 406 s 對 272 s、contest 255 s 對 200 s。e1_r8 反而是 C 較快（256 s 對 360 s）。最長的 run 是 hyper_far C s0，601 s，其中 oracle 占 325 s。背景 oracle 的牆鐘中位數在 157–326 s 之間，大致決定了 C 的總牆鐘。
- **臂 D 不穩定。** e1_r4 只有 s1、s3 到 78.6034，e1_r5 只有 s0 到 68.7464，其餘種子和 B 差不多。hyper_far 5 顆都是 82.5826，比 B 的中位 82.5461 穩，但仍低於 C。D 的同步網格每次約 65 s。
- **臂 B（ef87f65）沒有比 A 好**，只有 hyper_far 例外（中位 82.5461、最好 82.5777，A 是 82.4327）。B 也出現兩個低分：hyper_far s1 82.1095，以及 e1_r8 s3 75.7968（D s3 也是 75.7968）。
- smoke 全場最好的是 A s4 的 86.7864（3 棒）。其他臂的最好值都是 86.7847（4 棒），B/D 有幾顆種子是 86.7834。

## 2b. B、D 臂的拆棒失敗分類

腳本是 `classify_split_failures.py`，算法寫在腳本開頭的說明裡。

失敗的判定：DE 贏家（`winner_presplit_seed<S>.json`）有超標棒，而且 run.log 出現 C4 退路，或最終 mission 仍超標、失格或不 Earth-safe。

等分後終端需求是自己算的，因為 log 沒有印這個數字。做法：
1. 用 `route_from_standard_x` 解碼路線。
2. 用 `presplit_leading` 等分前導棒，cap 用 MAX_DV_SOFT。
3. 用 `_terminal_state` 以 J2–J4 傳播到終端起點。
4. 用 `_lam_best` 加 `_shoot_final` 求命中 target 所需的終端 Δv。這和拆棒器的貪婪段走同一套程式。

驗算：用同一個方法重算拆前終端棒，和 mission 的值相差 ≤ 0.001 m/s。

| 臂 | 前導棒等分後終端需求暴增 | 終端棒本身拆不開 | 無前導棒等分 | 需要拆棒的 run | 有超標前導棒的 run |
|---|---|---|---|---|---|
| B | 0 | 0 | 2（e1_r4 s0、e1_r8 s4） | 30 | 10 |
| D | 0 | 0 | 1（e1_r8 s4） | 30 | 12 |

- 3 筆失敗的拆前贏家都是單發大終端棒，沒有前導棒，或只有 0 m/s 的空前導棒。e1_r4 的終端棒是 1517 m/s，e1_r8 是 1866 m/s。log 原文是「HAP-67 自動拆分：這個違規解在段數上限內拆不出合法版」。3 筆都被 C4 的「旗標關重搜」救回，最後是合法解（78.3720／76.3313）。前導棒大小範圍：不適用（全為 0）。
- **前導棒等分本身沒有失敗。** B、D 共 22 個贏家有超標前導棒，全部拆棒成功。明細在 `leading_presplit_ok.csv`，前導棒範圍如下：
  - smoke：283–528 m/s
  - e1_r4（只有 D）：595.5 m/s
  - contest：1500 m/s，剛好等於 contest 的單棒上限，所以也會被等分

  等分後的終端需求是拆前的 0.93–1.03 倍，沒有暴增。
- 結論：這批資料裡，「前導棒等分」沒有造成任何失敗。拆不出來的都是沒有前導棒的單發大終端棒。

## 異常與注意

- contest C s0 的 run 期間有 numba 冷編譯（第一次跑 oracle），牆鐘 300 s 偏高。其他 run 沒有冷編譯。
- 臂 D 在 run.log Oracle comparison 表裡的「DE leading」欄，是拆後的第一棒，不是拆前前導棒；main 只在臂 C 設 `_oracle_presplit_leading_mps`。所以 `runs.csv` 的 `de_leading_mps` 只填臂 C。臂 D 的拆前前導棒請看 `presplit_leading_mps`。
- 臂 C 中 oracle 勝出的 run，`winner_presplit_seed<S>.json` 是 oracle 候選的拆前路線（被 `_solve_with_oracle` 覆寫），不是 DE 的。
- `cpu_sec` 和搜尋／拆棒分段秒數在 `sweeps/phase2_arm<X>_results.jsonl`，以及 `sweep_params.py --summary` 的輸出 `sweeps/phase2_arm<X>_summary.txt`。

## 檔案

- `runs.csv`：每個 run 一列。欄位有合法性、分數、棒數、總 Δv、牆鐘、拆前前導棒和終端棒、oracle 牆鐘、oracle 最佳拆後分數、oracle 是否勝出、commit。
- `runs/<題>_<臂>_s<種子>/`：mission.json、winner_presplit_seed*.json、oracle_candidates_seed*.json。
- `sweeps/`：四臂的 results.jsonl 與 --summary 輸出、C 被取代的舊結果、B/D 在 14b7849 的護欄結果。
- `split_failures.csv`、`leading_presplit_ok.csv`、`classify_split_failures.py`、`collect_results.py`、`tables.md`。
- 規格檔在 `sweeps/phase2_arm{A,B,C,D}.json`（repo 根目錄的 sweeps/）。
