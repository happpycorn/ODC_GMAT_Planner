# 全域對照：我們的解離真正的最佳有多遠（GLOBAL_ORACLE，2026-10-28～29）

研究碼與原始資料在遠端分支 `codex/e1-frequency`，未合進 Master。

**問題：** 同一套程式加大預算，只能量出「有沒有把自己的方法發揮完」，抓不到方法本身的盲點。
這份用跟管線搜尋無關的方法（兩棒窮舉、換最佳化器、換參數化）加上理論上界，對排位賽題庫比對。

**結論：**
1. **比賽當天設定離所有方法裡最好的：`hyperbolic_smoke`／`ranking_round` 差 0；`hyper_far` 差 0.215 分**
   （82.4327 vs 兩棒 oracle 82.6473）。大預算 20 顆種子最好 82.6030、中位數 82.5674，追回其中 0.17 分。
2. **有一個管線沒找到的路線家族，在 `hyper_far`**：第一棒放在任務中段（t ≈ 1.5–5.5 萬 s、585–680 m/s），
   終端棒走多圈 Lambert（M = 0–2），總 Δv 1,892–1,895 m/s，比當天設定的 1,920 m/s 省 28 m/s，抵達時刻幾乎相同（81,255 s）。
   另外，scipy DE 大預算找到一條拆前估 82.70 的路線（1,886 m/s），**拆棒器拆不出來**，見「hyper_far 的拆棒盲點」。
3. **天花板：** 證明上界很寬（`hyper_far` 88.81、`smoke` 92.80），只能說明還沒到物理極限。
   改用估計（抵達時刻取所有方法共同的值、Δv 取能量下限）：`smoke` 86.800，離最好的解 0.015；
   `hyper_far` 82.707，離最好的合法解 0.060。`hyperbolic_test_fuel` 所有方法都找不到總 Δv ≤ 3 km/s 的路線。

## 情境與尺

- 題庫：[`ranking_mc_v1`](../../sweeps/ranking_mc_v1.json) 的 `hyper_far`、`hyperbolic_test_fuel`、`hyperbolic_smoke`，
  加上 `ranking_round`。全部套排位賽覆寫（單棒 250 m/s、總 Δv 3 km/s）與
  [`splitspeed_par3_rec`](../../sweeps/splitspeed_par3_rec.json) 的拆棒建議設定，另加 `SPLIT_JACOBIAN="stm"`。
  **`hyperbolic_smoke` 套覆寫後跟 `ranking_round` 的設定完全相同**（軌道、T_max、計分參數），
  兩者在管線上的分數逐位元相同，第 1–3 項只跑一次，下表合成一列。
- 同一把尺（[`oracle_common.finalize_route`](https://github.com/happpycorn/ODC_GMAT_Planner/blob/codex/e1-frequency/scripts/research/oracle_common.py)）：任何方法找出的路線，
  前導棒超過 248 m/s 的先等分成間隔 100 s 的多段（管線的拆棒器只拆終端棒），再交給 `burn_splitter.legalize_route`：
  終端棒在 J2–J4 下重新瞄準 A(T)、拆成合法段，joint NLP 用真實計分精修整條路線，最後剔空燒、照交件規則重判。
  拿管線的拆前贏家來驗證，這把尺重算出 86.7838，管線是 86.7835。
- 程式版本：第 1–3 項與第 4 項都在 `db7d1c2`（= `origin/Master` `fb0ff12` + 本分支新增檔案；含星曆快取、撞地球補洞、
  拆棒 STM）。比賽設定另有一份舊程式 `ff24404`（星曆快取、沒有 STM、fd 拆棒）的對照，見表註。

## 結果

分數都是拆棒後、照交件規則判定合法的最終分數。路線摘要是「棒數／總 Δv／T_team／終端 Lambert 圈數 M」；
管線的 M 沒有存在 sweep 結果裡，記「—」。

### `hyper_far`（T_max 162,570 s，能量下限 1,884.7 m/s）

| 方法 | 最佳 | 中位數 | 路線摘要（最佳那顆） |
|---|---|---|---|
| 比賽當天設定（MAXITER 600，種子 0–2）¹ | 82.4327 | 82.4327 | 8 棒／1,920.3 m/s／81,252 s／—（拆前 3 棒） |
| 大預算參考解（MAXITER 1800，種子 0–19） | 82.6030 | 82.5674 | 9 棒／1,898.3 m/s／81,255 s／—（拆前 4 棒；最差 82.4474） |
| **兩棒 oracle**（前 10 名精修＋拆棒） | **82.6473** | 82.5734 | 8 棒／1,892.5 m/s／81,255 s／M=2（t1=14,634 s 燒 635 m/s，t2=29,918 s 終端） |
| scipy DE 相當預算（3 種子 × N=2/3） | 82.4327 | — | 8 棒／1,920.3 m/s／81,252 s |
| scipy DE 大預算（10 倍） | 拆不出 | — | 拆前估 82.7178（N=2：135 m/s＋1,751 m/s 終端），見下節 |
| CMA-ES 相當預算 | 拆不出 | — | 拆前最好 79.47 |
| CMA-ES 大預算 | 82.4472 | — | 8 棒／1,918.4 m/s／81,252 s |
| free-ECI 多起點（8 個隨機單棒起點） | 82.2927 | 79.65（5 個合法） | 8 棒／1,938.0 m/s／81,261 s；3 個起點拆不出 |
| 天花板（證明） | 88.81 | | Δv ≥ 1,884.7 m/s、T ≥ 18,211 s（兩個下界不一定能同時達到） |
| 天花板（估計） | 82.707 | | T = 81,255 s（所有方法的共同抵達時刻）、Δv = 能量下限 |

¹ 舊程式 `ff24404`：3 顆也都是 82.4327，同一條路線；新程式（STM）牆鐘中位數 262 s，舊程式 497 s（兩者都是 2 slot 並行）。

### `hyperbolic_smoke` = `ranking_round`（T_max 40,000 s，能量下限 637.0 m/s）

| 方法 | 最佳 | 中位數 | 路線摘要（最佳那顆） |
|---|---|---|---|
| 比賽當天設定（種子 0–2）² | 86.7847 | 86.7847 | 4 棒／639.4 m/s／19,973 s／—（拆前 2 棒） |
| 大預算參考解（種子 0–19，兩個情境各 20 顆） | 86.7847 | 86.7847 | 4 棒／639.4 m/s／19,973 s；40 顆裡 4 顆落在 86.7620（3 棒、642.9 m/s） |
| 兩棒 oracle | 86.7847 | 86.7840 | 4 棒／639.4 m/s／19,973 s／M=0（t1=2,520 s 燒 303 m/s，t2=16,520 s 終端） |
| scipy DE 相當／大預算 | 86.6855／86.7847 | — | 3 棒 654.7 m/s／4 棒 639.4 m/s |
| CMA-ES 相當／大預算 | 86.7620／86.7620 | — | 3 棒／642.9 m/s |
| free-ECI 多起點（8 個起點） | 85.2033 | 77.45（7 個合法） | 9 棒／852.7 m/s／19,968 s（另一個家族：單棒 855 m/s 那條） |
| 天花板（證明） | 92.80 | | Δv ≥ 637.0 m/s、T ≥ 6,570 s |
| 天花板（估計） | 86.800 | | T = 19,973 s、Δv = 能量下限 |

² 舊程式 `ff24404`：86.7839／86.7847／86.6855（種子 2 停在 3 棒 654.7 m/s 的家族）；新程式 3 顆都是 86.7847。

### `hyperbolic_test_fuel`（T_max 8,000 s，純二體，能量下限 697.4 m/s）

**沒有任何方法找到總 Δv ≤ 3 km/s 的路線。**

- 單棒網格（步長 50 s）最省 3,496.7 m/s；兩棒網格最省也是 3,496.7 m/s，多一棒沒有更省。
- DE、CMA-ES 兩種預算都停在失格層，拆棒拆不出。管線 26 次（舊程式 3 顆、新程式 3 顆、大預算 20 顆）都以結束碼 3 結束。
- 天花板（證明）99.34 沒有意義：兩個下界都達不到。這不是「無解」的證明，三棒以上的結構沒窮舉。

## `hyper_far` 的路線家族

- **管線（當天設定）**：拆前 3 棒、1,920 m/s。單棒網格最好的點就是 1,920 m/s（t1 = 8,537 s，M=3），管線的路線基本上是這一條。
- **兩棒 oracle**：前 10 名中有 3 條精修後 ≥ 82.63，共通點是第一棒放在任務中段（t1 = 14,634–54,959 s）、585–680 m/s，第二棒才是大的終端棒
  （多圈 Lambert，M = 0–2）。精修後 8–9 棒、1,892–1,895 m/s。大預算 20 顆種子裡最好的那顆（82.6030，1,898 m/s）
  也是 4 棒結構，往這個方向靠，但沒完全到。
- 時間項幾乎沒差（抵達都是 81,252–81,255 s，A 過近地點附近），**分數差全在燃料**：每省 10 m/s 約 +0.07 分。

### `hyper_far` 的拆棒盲點

scipy DE 大預算（6 次裡 4 次）收斂到同一條 N=2 路線：t = 20,308 s 燒 135 m/s，t = 51,066 s 終端燒 1,751 m/s，
滑行 30,190 s 攔截，總 1,886 m/s、拆前估 82.70。這比所有合法解都省，但 `legalize_route`（含關掉牆鐘預算、`n_span=2`）
6 秒內就回報拆不出來。把那發 1,751 m/s 當前導棒先等分、只留一段短終端修正：終端留 6,000 s 時合法 82.5599（9 棒、1,904 m/s），
留 600–3,000 s 時總 Δv 衝到 3.3–4.3 km/s 而失格。**這條 1,886 m/s 的路線拆完能拿多少分還不知道**；
如果拆得出 ~1,890 m/s，`hyper_far` 會再高 ~0.05 分。原因沒查（猜測是貪婪拆棒在 3 萬秒長滑行、多圈的終端段找不到合法的段數）。

## 方法細節

- **兩棒 oracle**（[`oracle_twoburn.py`](https://github.com/happpycorn/ODC_GMAT_Planner/blob/codex/e1-frequency/scripts/research/oracle_twoburn.py)）：
  - 單棒子空間：t1 × t3 網格窮舉（步長 T_max/320～/80），每格掃 Lambert 全分支（M 0–4 × 順／逆 × 高／低路徑）。
  - 兩棒子空間：t1 × t2 × t3 三維網格（`hyper_far` 1,626 s、`smoke` 350 s、`test_fuel` 100 s），每格用 Nelder–Mead 解第一棒的
    3 維 Δv，兩個起點（dv1 = 0、dv1 = 從 t1 直接 Lambert 打 A(t3)）；前 6 個區域 ±1 格、步長 1/5 加密。
    B(t1)、A(t3) 用 J2–J4 星曆，兩段弧用二體（`vallado`）；**忽略 250 m/s 上限**，保留近地點檢查；先排總 Δv ≤ 3 km/s 的，再依拆前估分取前 10 名精修。
  - 內層只是局部最小化，不是完整窮舉；兩棒最好的拆前估計（二體）在 `smoke` 是 689 m/s、`hyper_far` 1,910 m/s，
    都比精修後的 639／1,892 m/s 貴，J2–J4 精修與多棒 joint NLP 還能再省。
  - 耗時：`smoke` 106 s、`hyper_far` 225 s（含精修 10 條）。
- **換最佳化器**（[`oracle_solvers.py`](https://github.com/happpycorn/ODC_GMAT_Planner/blob/codex/e1-frequency/scripts/research/oracle_solvers.py)）：同一個 `fast_fitness_evaluator` 與邊界，
  scipy `differential_evolution`（rand1bin、LHS 初始、不 polish）與 CMA-ES（`cma` 4.5.0，[0,1] 正規化、IPOP 重啟），
  不用管線的任何種子產生器。相當預算 = MAXITER × POPSIZE × 2 = 24,000 次評估／案例，大預算 = 10 倍。
  每個 solver × 預算取拆前分數最高的那顆種子去精修＋拆棒。
- **free-ECI 多起點**：起點是單棒網格中 Δv ≤ 3 km/s 的格子隨機抽 8 個，整發當前導棒等分、留一小段終端修正，
  交給 joint NLP（每棒 ECI Δv 向量＋滑行秒數，真實計分，J2–J4）。決策變數不經過球座標、coast_frac 與 Lambert 終端；
  NLP 引擎跟拆棒器是同一個 `joint_nlp_split`，只是起點跟 DE 無關。局部法，結果很看起點。
- **天花板**（[`oracle_ceiling.py`](https://github.com/happpycorn/ODC_GMAT_Planner/blob/codex/e1-frequency/scripts/research/oracle_ceiling.py)）：
  - Δv 下界：`energy_floor_dv()`，B 的半徑範圍要碰到 A 的半徑範圍的最少衝量（**證明**，點質量）。
  - T 下界：任何時刻 |v_B| ≤ U = √(2(ε_B + μ/r_min)) + ΔV_max（每發最多讓「r ≥ r_min 處的最大速率」增加該發 Δv），
    所以 |r_A(T) − r_B(0)| − 5 ≤ U·T；U 再乘 1.01 吸收 J2–J4 位能（**證明**，點質量，很寬）。
  - 估計（**不是證明**）：抵達時刻取所有方法共同的值（`smoke` 19,973 s、`hyper_far` 81,255 s），Δv 取能量下限。
    原本打算用兩棒 oracle 的二體 Pareto 前緣當估計，但它比精修後的合法解還低（`smoke` 86.47、`hyper_far` 82.51），不能當上界，沒採用。
- **大預算與當天設定**：[`global_oracle_bigbudget.json`](https://github.com/happpycorn/ODC_GMAT_Planner/blob/codex/e1-frequency/sweeps/global_oracle_bigbudget.json)、
  [`global_oracle_contest.json`](https://github.com/happpycorn/ODC_GMAT_Planner/blob/codex/e1-frequency/sweeps/global_oracle_contest.json)，`sweep_params.py --slots 2`，只求解到拆棒。

## 量測條件與過程

- Corn（Ryzen 7 5800X，8 核 16 執行緒，WSL2）。批次 [`run_global_oracle_overnight.sh`](https://github.com/happpycorn/ODC_GMAT_Planner/blob/codex/e1-frequency/scripts/research/run_global_oracle_overnight.sh)：
  先第 1–3 項，最後才跑第 4 項（10-28 21:33 → 10-29 04:46）。舊程式的比賽設定在 10-28 15:30 前跑完。
- `smoke` 的兩棒網格第一次（步長 250 s）跑了 5 小時沒結束：平行化依 t1 靜態分塊，最重的一段落在同一個執行緒。
  改成 (t1, t3) 配對隨機分派、步長 350 s 後 45 s 跑完。這次停掉的結果沒有用。
- 原始資料在本機 `outputs/research/global_oracle/`（各方法 json、log）與 `outputs/sweeps/global_oracle_*`，不進 git。
