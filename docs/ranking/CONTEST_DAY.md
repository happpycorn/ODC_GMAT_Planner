# 排位賽當天作業手冊（2026-11-09）

**比賽當天照著做的流程。** 規則摘要看 [RANKING_ROUND_RULES_20261006](../RANKING_ROUND_RULES_20261006.md)，
攝動落差看 [PERTURBATION_GAP_20261019](../PERTURBATION_GAP_20261019.md)，工具用法看[專案 README](../../README.md)。
初賽的手冊 [prelim/CONTEST_DAY](../prelim/CONTEST_DAY.md) 裡的團隊分工（§十）、雙機並行（§10.5）和已知地雷（§七）
大多還適用，這份只寫排位賽不一樣的地方和完整流程。

沒有標「官方」的判斷都是我們自己的推論，現場以工作人員說的為準。開賽前要問的問題整理在
[QUESTIONS_FOR_ORGANIZER](QUESTIONS_FOR_ORGANIZER.md)。

> **TODO（等資料）**
> - 求解的計時數據：ranking-mc session 會產生 `docs/RANKING_MC_20261019.md`（250 m/s、8–12 棒的多種子
>   蒙地卡羅）。寫這份文件時那份還沒出來，下表「求解」一列先用初賽與 budget_v1 的數字估，出來後要改。
> - `--retarget-full-perturbation`：另一個 session 正在實作，寫這份文件時還沒合併。§6 兩種情況都寫了。
> - 比賽時長、地點、繳交方式：官方還沒公布。

---

## 一、跟初賽不同、會改變流程的五件事（官方規則）

1. **單棒 250 m/s，超過 250 + 10⁻⁵ m/s 直接失格**；總 Δv 超過 3 km/s 也失格。解會拆成 8–12 棒。
2. **T_max 開賽才知道**：A 過近地點後，地心距離第一次增加到任務邊界的時刻。工具不會自己猜，要用
   `scripts/tmax_from_boundary.py` 算出來填 `rules.T_MAX_SEC`。
3. **計分參數 `k_t, C_t, k_v, C_v` 比賽當下才公布**，要現場換單位。初賽官方的 `k_v`、`C_v` 是 km/s 制。
4. **官方驗證開全攝動**（EGM96 20×20、潮汐、NRLMSISE00、日月、SRP、相對論）。我們用 J2–J4 設計，
   短任務就差 0.5–1.3 km，長任務可以差上百公里。**要做全攝動 B 平面重瞄準**。
5. 穿越地球只有在**攔截前**才失格（攔截後可以）。

## 二、時間表（預估）

比賽時長還沒公布。每一步的預估時間如下，括號是遇到問題時的上限。

| 步驟 | 做什麼 | 預估 | 依據 |
|---|---|---|---|
| 1 | 抄題目、建 config，兩人各抄一次核對 | 5–10 分 | 初賽實測 |
| 2 | 算 T_max 寫回 config | 1 分 | CLI 實測：含 numba 編譯約 5 s |
| 3 | 計分參數換算、驗算、寫回 config | 2–3 分 | CLI 是秒級；時間花在打字和核對 |
| 4 | `check_problem.py` 體檢、`feasibility.py` 看最少棒數 | 2–5 分 | 初賽實測；`feasibility.py` 前兩層幾十秒到幾分鐘 |
| 5 | 第一次求解（拿到能交的東西） | **TODO**（先估 10–40 分） | 見下方說明 |
| 6 | 全攝動 B 平面重瞄準 + 重播 | 2–5 分（15 分） | 單次 DC 2–15 s，hyper_far 定時對齊 58 s；重播 50 組蒙地卡羅約 10 分（4 個 GMAT） |
| 7 | GMAT 驗證固定燃燒版 | 1–3 分 | 初賽完整流程含 GMAT 約 80 s；全攝動積分較慢，未實測 |
| 8 | 失格檢查清單 | 5 分 | |
| 9 | 繳交 | 5–10 分 | 初賽要在主辦機重跑、產 Report、上傳 |
| | **第一份能交的解合計** | **約 35–80 分** | 步驟 5 的不確定性最大 |

**步驟 5 的估法（TODO：用 RANKING_MC 的數字取代）：** 初賽的經驗是「搜尋時間由 T_max 決定」，
小時級 T_max 一輪約 2 分鐘，天級要數十分鐘（[初賽手冊](../prelim/CONTEST_DAY.md) §4.1）。
排位賽 A 是雙曲線，佔位情境的 T_max 是 11 h（hyperbolic_smoke）到 45 h（hyper_far）；另外 250 m/s 會讓
拆棒段數變多，拆棒時間還沒在 8–12 棒量過。RANKING_MC 出來之後，把這列換成「中位／最差」兩個數字，
並決定 §5 要不要一開始就降級。

**原則跟初賽一樣：先交得出東西，再求更好。** 步驟 5 第一輪跑完、做完 6–8，就先把那一份存好當保底，
剩下的時間再跑第二台機器的分支或多 seed。

---

## 三、賽前一晚

- [ ] `git pull`、`uv sync`；確認 `src/tmax.py`、`src/scoring_params.py` 都在。
- [ ] 跑單元測試（都不到 1 分鐘）：
  ```bash
  uv run python tests/test_tmax.py
  ```
  ```bash
  uv run python tests/test_scoring_params.py
  ```
  ```bash
  uv run python tests/test_ranking_rules.py
  ```
- [ ] 看 `--retarget-full-perturbation` 合併了沒有，決定 §6 走哪條：
  ```bash
  uv run python main.py --help
  ```
- [ ] GMAT：`GmatConsole` 跑得起來，`data/gravity/earth/EGM96.cof` 和 CSSI 太空天氣檔都在（全攝動重播要用）。
- [ ] 用 `configs/shared/ranking_round.json` 從頭到尾演練一次 §四的步驟 1–8，**計時**，把實際時間填回 §二。
- [ ] 筆電充飽、行動電源、延長線、USB、證件；上太空中心官網確認組別。

---

## 四、逐步流程

### 步驟 1：建 config（5–10 分）

`configs/` 除了 `shared/` 都不進 git，當天自己複製一份：

```bash
cp configs/shared/ranking_round.json configs/ranking.json
```

改 `orbit_A`、`orbit_B` 的六根數。`rules` 裡這幾個是排位賽規則，**不要動**：

| 欄位 | 值 | 來源 |
|---|---|---|
| `MAX_DV_MPS` | 250.0 | 官方，超過 250 + 10⁻⁵ 失格 |
| `MAX_TOTAL_DV_MPS` | 3000.0 | 官方，超過失格 |
| `MIN_MANEUVER_INTERVAL_SEC` | 100.0 | 官方，違規每次扣 10 分 |
| `T_MAX_SEC` | 步驟 2 寫入 | |
| `k_t`、`C_t`、`k_v`、`C_v` | 步驟 3 寫入 | |

`strategy.GRAVITY_DEGREE` 維持 4（J2–J4）。`_comment_*` 欄位是佔位說明，可以刪。

**抄根數的注意事項：**
- 雙曲線的 SMA 是**負的**（GMAT 慣例），ECC > 1。
- TA 寫 [0, 360) 或 (−180, 180] 都可以，工具會折算；但**正負號決定 A 是在往近地點飛還是已經飛過**，抄錯 T_max 會完全不同。
- 兩個人各抄一次，逐字元核對（初賽手冊 §10.3 隊友 A 的工作）。

### 步驟 2：算 T_max（1 分）

拿到任務邊界後：

```bash
uv run python scripts/tmax_from_boundary.py --config configs/ranking.json --boundary-km <邊界地心距離>
```

官方給的如果是**高度**，改用 `--boundary-alt-km`（會加上 R_E = 6378.137 km）。這兩者差 6,378 km，
選錯 T_max 會差很多；不確定就問工作人員（[問題 9–11](QUESTIONS_FOR_ORGANIZER.md)）。

輸出要看三件事：

1. **點質量數值解跟解析解差 < 1 ms。** 不是的話，根數抄錯或程式有問題，先不要填。
2. **J2–J4 跟解析解差多少。** 在共用情境實測是 +0.15～+0.29 s，差到幾秒以上就要查。
3. **「註」那幾行**：A 是不是已經過了近地點、一開始在邊界內還是外。跟題目描述對得起來才往下。

確認無誤後加 `--write` 寫回 config。寫入的值是「解析與 J2–J4 數值取早的、捨去到整秒」。
**主辦單位如果直接公布 T_max 秒數，用官方數字**，不要用工具算的。

工具會擋下的情況（都會印原因，`echo $?` 不是 0）：

| 情況 | 訊息 | 怎麼辦 |
|---|---|---|
| 邊界 ≤ 近地點距離 | 「A 的距離永遠不會小於近地點」 | 多半是把高度當成地心距離；工具會提示改用 `--boundary-alt-km` |
| A 已過近地點而且已經在邊界外 | 「雙曲線不會再回來」 | 檢查 TA 正負號 |
| TA 在漸近線外 | 「\|TA\| 必須 < …」 | TA 或 ECC 抄錯 |
| 橢圓 A、邊界 > 遠地點 | 「A 永遠在邊界內」 | 規則定義不適用，問主辦單位（初賽是 4 × 週期） |
| 圓軌道、拋物線 | 沒有定義 | 問主辦單位 |

A 一開始就已經過了近地點、但還在邊界內的情況，工具照算（T_max = 往外飛出邊界的時刻），附註會提醒；
這種情況要跟主辦單位確認他們的定義也接受「近地點在任務開始前」。

**關於 T_max 的模型誤差：** 官方用什麼模型算 T_max 不知道。如果官方對 A 也開日月引力，
長時間飛掠的穿越時刻可能跟我們差到分鐘等級（量級估計，未實測：hyper_far 的日月項在 22 h 累積 297 km，
除以約 2 km/s 的徑向速度是 2–3 分鐘）。所以除非官方公布秒數，**不要把攔截排在 T_max 前 5 分鐘以內**。
時間分在 T_max 附近通常已經很小，這個限制幾乎不會犧牲分數。

**跟舊共用情境的 T_MAX_SEC 不同的地方：** `configs/shared/` 的雙曲線情境是用「2 × 到近地點的時間」編的，
等於假設任務邊界剛好是 A 的初始地心距離（雙曲線對稱，飛出去回到同一個距離剛好是 2 × t_p）。精確值和檔案的差：

| 檔案 | 2 × t_p（精確） | J2–J4 數值 | 檔案的 T_MAX_SEC | 差 |
|---|---|---|---|---|
| hyperbolic_smoke、ranking_round | 39,947.192 s | 39,947.423 s | 40,000 | +52.8 s（進位） |
| hyper_far | 162,512.936 s | 162,513.082 s | 162,570 | +57.1 s |
| hyperbolic_test | 9,360.615 s | 9,360.825 s | 8,000 | −1,360.6 s（不是用這條規則編的） |

這些檔案是佔位用的，不改它們（改了會讓過去的實驗不能重現）；`tests/test_tmax.py` 記錄了這張表。
真正的邊界不一定等於 A 的初始距離：A 一開始在邊界外，T_max 會比 2 × t_p 短；在邊界內就比較長。

### 步驟 3：計分參數（2–3 分）

```bash
uv run python scripts/check_scoring_params.py --config configs/ranking.json \
    --kt <k_t> --kt-unit 1/s --Ct <C_t> --Ct-unit s \
    --kv <k_v> --kv-unit "<官方單位>" --Cv <C_v> --Cv-unit <官方單位>
```

`--kv-unit`、`--Cv-unit` **沒有預設值，一定要照官方寫的單位填**：`1/(km/s)` 或 `1/(m/s)`、`km/s` 或 `m/s`。
官方如果有給參考解，加上 `--ref-dv <總Δv> --ref-dv-unit <單位> --ref-t <攔截時刻>`。

**驗算方法：參考解大概會落在整數分。** 初賽主辦單位是照參考解校準參數的：參考解
ΔV = 2.241427 km/s、T = 3,211.737 s 換對單位剛好 50 + 22.50 + 17.50 = **90.00 分**；照抄 km/s 制的數字
只有 72.50 分（燃料項 0）。工具會：

- 算參考解的分項與總分，看總分是不是整數、分項是不是 0.5 的倍數；
- 把 `k_v`、`C_v` 的四種單位解讀都算一次，標出哪一種落在整數；
- 時間或燃料項貼在 0 或 25（飽和）時直接警告，因為那樣錯的單位也可能湊出整數。

看一次示範：

```bash
uv run python scripts/check_scoring_params.py --demo-prelim
```

**沒有參考解時**，看「數量級檢查」：C_v 在 m/s 制應該是幾百到幾千，C_v < 50 幾乎一定還是 km/s；
`k_v·C_v` 和 `k_t·C_t` 是無單位的，單位一致地換算時不會變（初賽 3.506、14.99），只換了其中一個會差 1000 倍。
另外看 `C_t / T_max`：< 0.30 主攻快解，> 0.70 省油解可能有戲（初賽手冊 §七第 6 點）。

沒有警告、參考解落在整數，就加 `--write` 寫回 config。

### 步驟 4：體檢與可行性（2–5 分）

```bash
uv run python check_problem.py --config configs/ranking.json
```

```bash
uv run python feasibility.py --config configs/ranking.json
```

- `check_problem.py`：A/B 的近地點、平面夾角、T_max、`C_t / T_max` 有沒有離譜。最後那行
  「單位換算檢查」是初賽範例專用的，排位賽**忽略**（步驟 3 已經驗過）。
- `feasibility.py`：**能量下限**。至少要 ⌈能量下限 / 250⌉ 棒；能量下限接近或超過 3,000 m/s，
  總 Δv 上限下可能無解，第一輪就要知道。

### 步驟 5：求解（TODO：計時見 RANKING_MC）

```bash
uv run python main.py --config configs/ranking.json --stop-after solve --run-dir outputs/runs/rank-a
```

先停在 solve，拿到 `mission.json` 再做重瞄準和驗證，搜尋就不用重跑。
DE 會先找少棒數的路線，再由 `AUTO_SPLIT_LEGALIZE`（預設開）拆成每棒 ≤ 250 − 2 m/s（`MAX_DV_MARGIN_MPS` = 2）。

跑完看終端機最後的「分數拆解」：

- 有 `🔴 失格` 就**不能交**。單棒超標：確認 `AUTO_SPLIT_LEGALIZE` 沒被關、放寬棒數或 T_max 重跑；
  總 Δv 超標：拆棒救不了，換路線（看 `feasibility.py` 的能量下限）。
- 記下 Δr_min、ΔV_team、T_team、棒數、最大單棒。

**TODO（RANKING_MC 出來後補）：**
- 每輪牆鐘中位與最差，決定要不要一開始就降級（降級旋鈕見[初賽手冊](../prelim/CONTEST_DAY.md) §4.1；
  第一個退 `REVS_ENSEMBLE`，代數比族群重要，不要加大 POPSIZE）。
- 8–12 棒拆棒的收斂率，以及失敗時該怎麼辦。
- 多 seed 的分數散布：兩台機器同 config 不同 `SEED` 取好的那個值不值得（跨 seed best-of-N，HAP-35）。

### 步驟 6：全攝動 B 平面重瞄準（2–5 分）

為什麼要做：我們瞄 Δr ≈ 3.5 km，離 5 km 只剩 1.5 km；J2–J4 → 全攝動在 1.6 h 以內的任務就偏 0.5–1.3 km，
22.6 h 的 hyper_far 偏 263 km（[PERTURBATION_GAP](../PERTURBATION_GAP_20261019.md) §2）。
B 平面重瞄準只要多花 0.04–4.6 m/s，所有試過的解都收斂。

**做法要點（兩條路都一樣）：**
- 只消垂直於相對速度的兩個分量（B 平面），**不要用定時位置對齊**：hyper_far 會多花 272 m/s、
  最後一棒變 361 m/s，直接失格。
- 改有餘裕的那一棒（通常是最後的微調棒）。拆出來的棒大多貼著 248 m/s，改那種棒會超標。
- 力學模型用全攝動；官方公布曆元和太空船參數之後換成官方的（[問題 1–6](QUESTIONS_FOR_ORGANIZER.md)）。

**若 `--retarget-full-perturbation` 已合併：** 照那個 PR 的說明用，例如

```bash
uv run python main.py --from-mission outputs/runs/rank-a/mission.json --retarget-full-perturbation --run-dir outputs/runs/rank-a-rt
```

（旗標名稱與用法以合併後的 `main.py --help` 為準。）

**若還沒合併：** 用研究腳本手動做。在 `scripts/research/perturbation_gap.py` 的 `SOLUTIONS` 加一筆
`"today": dict(kind="mission", label="today", path="<mission.json 的絕對路徑>")`，然後

```bash
uv run python scripts/research/perturbation_gap.py retarget --mode bplane --solutions today --mc 20
```

結果在 `outputs/research/perturbation_gap/retarget_bplane.json`：挑最後一棒（或 `delta_vec_mps` 最小）且
`replay.hit` 為真的那筆，`new_burns` 是修正後各棒的 VNB Δv（km/s）。手動把那一棒寫進 `output_submit.txt`
對應的 `ImpulsiveBurn`（只改那三個數字，**不要打中文**），再用步驟 7 驗證。這條路沒有演練過，
預估 15 分鐘以上；時間不夠就至少跑 `ladder` 看全攝動下 d_min 還有沒有在 5 km 內。

**太空船參數沒公布時：** 加 `--mc 20`～`50`，看重瞄準後的命中率。命中率不夠，讓 B 少在低軌停留、
或縮短最後一段滑行再求解一次。

### 步驟 7：GMAT 驗證（1–3 分）

```bash
uv run python main.py --verify-script <修正後的 output_submit.txt> --run-dir outputs/runs/rank-a-verify
```

- 固定燃燒版（`output_submit.txt`）才是繳交用的，跟初賽一樣。
- 現有 `script_generator` 產的腳本力學模型是 J2–J4（`JGM2.cof`、`Drag = None`、`SRP = Off`）。
  **繳交的腳本要不要換成官方力學模型、要不要帶我們的太空船參數**，看[問題 6、12](QUESTIONS_FOR_ORGANIZER.md) 的答案。
- GMAT 和 Python（J2–J4）的落差在公尺等級是正常的；全攝動重播跟 J2–J4 差公里等級也是正常的，那是步驟 6 要修的東西。

### 步驟 8：失格檢查清單（5 分）

**每一項都要打勾才能交。** 用步驟 6 的全攝動重播結果，不是 J2–J4 的。

- [ ] **每一棒 ≤ 250 m/s**（超過 250 + 10⁻⁵ 失格）。看重瞄準後的每一棒，不只最後一棒；建議留 ≥ 1 m/s 餘裕。
- [ ] **總 Δv ≤ 3,000 m/s**（超過失格）。重瞄準會加幾 m/s，要用加完之後的總和。
- [ ] **相鄰兩棒間隔 ≥ 100 s**（違規每次扣 10 分）。終端機的「機動間隔違規」= 0。
- [ ] **攔截前不穿越地球**。Python 端 Earth-safe 閘門沒擋（有擋就不會產生 `output_submit.txt`）；
      全攝動重播的攔截前最低高度 > 0（建議 > 100 km）。
- [ ] **全攝動下 d_min ≤ 5 km**，最好 < 4 km 留餘裕。
- [ ] T_team < T_max，而且離 T_max 有 5 分鐘以上（步驟 2 的模型誤差）。
- [ ] 腳本全 ASCII（中文註解會讓 GMAT 解析失敗，初賽踩過三次）。
- [ ] 記下 **d_min、ΔV_team、T_team**：同分時依序比這三個。
- [ ] `rules` 裡 `T_MAX_SEC`、`k_t/C_t/k_v/C_v` 是今天的官方值，不是佔位值（佔位值是 40000 / 0.0001 / 25000 / 0.002 / 1500）。

### 步驟 9：繳交（5–10 分）

繳交格式官方還沒公布（[問題 12–14](QUESTIONS_FOR_ORGANIZER.md)）。初賽的做法是：在主辦機的 GMAT 開題目 Script、
改 B 的設定與機動、至少模擬一次產生 Report，再把 Script + Report 上傳（[初賽手冊](../prelim/CONTEST_DAY.md) §10.2）。
如果排位賽一樣：

1. 把 `output_submit.txt` 帶到主辦機（USB），在那台的 GMAT 跑一次，確認結果跟自己機器一致。
2. 產 Report，檔名照官方要求。
3. 上傳。三個人都要會這套步驟，主控卡住時隊友能把上一份驗過的檔案交出去。

---

## 五、已知地雷

1. **`k_v`、`C_v` 的單位。** 初賽官方給 km/s 制，照抄燃料項整個錯（72.50 vs 90.00）。步驟 3 的工具強制要寫單位。
2. **任務邊界是地心距離還是高度。** 差 6,378 km。步驟 2 選錯參數會差很多，工具只能在「邊界 < 近地點」時提醒。
3. **TA 的正負號。** 決定 A 是往近地點飛還是飛離，T_max 會完全不同。
4. **`T_MAX_SEC` 從 epoch 起算**，不是從近地點起算。
5. **定時位置對齊的 DC 在長任務會爆 Δv。** 重瞄準一定用 B 平面（步驟 6）。
6. **改棒時看每一棒的上限**，不是只看最後一棒；拆出來的棒都貼著上限。
7. **`check_problem.py` 最後的「參考解 90 分」只對初賽範例有意義**，排位賽忽略。
8. **共用情境的 T_MAX_SEC 是編的**，不要拿它們的值當排位賽的參考（步驟 2 的表）。
9. GMAT 腳本不能有非 ASCII 字元；`configs/` 不進 git；同分先比 d_min（同初賽手冊 §七）。
