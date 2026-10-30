# 排位賽當天作業手冊（2026-11-09）

**比賽當天照著做的流程。** 規則摘要看 [RANKING_ROUND_RULES_20261006](RANKING_ROUND_RULES_20261006.md)，
攝動落差看 [PERTURBATION_GAP_20261019](../research/PERTURBATION_GAP_20261019.md)，工具用法看[專案 README](../../README.md)。
初賽的手冊 [prelim/CONTEST_DAY](../archive/prelim/CONTEST_DAY.md) 裡的團隊分工（§十）、雙機並行（§10.5）和已知地雷（§七）
大多還適用，這份只寫排位賽不一樣的地方和完整流程。

沒有標「官方」的判斷都是我們自己的推論，現場以工作人員說的為準。開賽前要問的問題整理在
[QUESTIONS_FOR_ORGANIZER](QUESTIONS_FOR_ORGANIZER.md)。

> **2026-10-20 演練過一次**（`configs/shared/ranking_round.json` 的佔位題，步驟 1–8 全通過，實測時間填在 §二）。
> 求解時間的依據：[RANKING_MC](../research/RANKING_MC_20261019.md)、[SPLITTER_SPEED](../research/SPLITTER_SPEED_20261020.md)。
> `--retarget-full-perturbation` 已合併。
>
> **TODO（等官方）**：比賽時長、地點、繳交方式、太空船參數。

---

## 一、跟初賽不同、會改變流程的五件事（官方規則）

1. **單棒 250 m/s，超過 250 + 10⁻⁵ m/s 直接失格**；總 Δv 超過 3 km/s 也失格。解會拆成 8–12 棒。
2. **T_max 開賽才知道**：A 過近地點後，地心距離第一次增加到任務邊界的時刻。工具不會自己猜，要用
   `odc.py tmax` 算出來填 `rules.T_MAX_SEC`。
3. **計分參數 `k_t, C_t, k_v, C_v` 比賽當下才公布**，要現場換單位。初賽官方的 `k_v`、`C_v` 是 km/s 制。
4. **官方驗證開全攝動**（EGM96 20×20、潮汐、NRLMSISE00、日月、SRP、相對論）。我們用 J2–J4 設計，
   短任務就差 0.5–1.3 km，長任務可以差上百公里。**要做全攝動 B 平面重瞄準**。
5. 穿越地球只有在**攔截前**才失格（攔截後可以）。

## 二、時間表（預估）

比賽時長還沒公布。每一步的預估時間如下，括號是遇到問題時的上限。

「演練實測」是 2026-10-20 用 `ranking_round.json` 佔位題（T_max 11.4 h、能量下限 637 m/s）在 8 核機器上量的
機器時間，不含人打字核對。

「Mac 實測」是 2026-10-28 在 M4 MacBook Air（4 效能核＋6 節能核、32 GB、無風扇）上量的同一題：
**省電模式開、用電池**，沒有降頻警告；步驟 5–7 電量 98% → 90%（約 17 分鐘耗 8%，滿載 60 分鐘估 30%）。

| 步驟 | 做什麼 | 預估 | 演練實測（Corn） | Mac 實測 | 依據 |
|---|---|---|---|---|---|
| 1 | 抄題目、建 config，兩人各抄一次核對 | 5–10 分 | — | — | 初賽實測 |
| 2 | 算 T_max 寫回 config | 1 分 | 7 s + 10 s（含 numba 編譯） | — | |
| 3 | 計分參數換算、驗算、寫回 config | 2–3 分 | < 1 s | — | 時間花在打字和核對 |
| 4 | `odc.py check` 體檢、`odc.py feasibility` 看能量下限 | 1–3 分 | 4 s + 13 s | — | |
| 5 | 3 顆種子並行求解 | **13–25 分**（40 分） | **12.6 分**（3 顆都合法、86.784 分、4 棒） | **16.5 分**（3 顆都合法、最佳 86.785 分） | 長飛掠 hyper_far 3 顆並行 22 分（SPLITTER_SPEED）；上限是預算 600 s 的拆棒長尾。Mac 約慢 30%，長飛掠估 29 分（未實測） |
| 6 | 全攝動 B 平面重瞄準（含固定燃燒版 GMAT） | 1 分（5 分） | 33 s | 14 s | DC 2 次迭代；+0.57 m/s；Mac 末棒 248.5 m/s、GMAT miss 6.7 m |
| 7 | GMAT 獨立驗證繳交腳本 | 1 分 | 8 s | 5 s | |
| 8 | 失格檢查清單 | 5 分 | — | — | |
| 9 | 繳交 | 5–10 分 | — | — | 初賽要在主辦機重跑、產 Report、上傳 |
| | **第一份能交的解合計** | **約 35–60 分** | 機器時間約 14 分 | 機器時間約 17 分 | 步驟 5 的不確定性最大 |

**步驟 5 的時間由題目決定**：佔位題 12.6 分鐘；長飛掠（hyper_far，T_max 45 h、要拆 8 棒）3 顆並行 22 分鐘，
其中搜尋最多 17 分、拆棒 2–7 分（[SPLITTER_SPEED](../research/SPLITTER_SPEED_20261020.md) §1）。拆棒有 600 s 預算當保險。

**Mac 跑 hyper_far（2026-10-28，同 `sweeps/splitspeed_par3_rec.json` 設定，省電模式＋電池）超出時間盒**：
搜尋約 23 分，拆棒兩顆都用滿 600 s 預算。最快的 seed 1 花 33.4 分（82.4327 分），seed 2 花 48.5 分。
seed 0 觸發 primer 重搜（4 棒、1200 代），估計還要 40 分鐘，所以在 48.6 分時手動停掉。
seed 2 也觸發了重搜，多花約 14 分，拆後分數只差 0.0003。
用 seed 1 做全攝動重瞄準 31 s（DC 4 次迭代，82.417 分），GMAT 驗證 7 s（miss 0.47 km、末棒 185.8 m/s），全部合法。
電量 90% → 74%（49 分鐘），沒有降頻警告，負載峰值 28.6。
→ 當天設定待定：關掉 `PRIMER_GUIDED_RESEARCH` 或幫它設時間上限；第一顆合法種子跑完就先重瞄準當保底，不等全部；Mac 上試 2 顆並行。
降級旋鈕見[初賽手冊](../archive/prelim/CONTEST_DAY.md) §4.1：第一個退 `REVS_ENSEMBLE`，代數比族群重要，不要加大 POPSIZE。

**原則跟初賽一樣：先交得出東西，再求更好。** 步驟 5 第一輪跑完、做完 6–8，就先把那一份存好當保底，
剩下的時間再跑第二台機器的分支或多 seed。

---

## 三、賽前一晚

- [ ] `git pull`、`uv sync`；確認 `odc/config/tmax.py`、`odc/config/scoring_params.py` 都在。
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
- [ ] 確認 `odc.py solve --help` 有 `--retarget-full-perturbation`：
  ```bash
  uv run python odc.py solve --help
  ```
- [ ] GMAT：`GmatConsole` 跑得起來，`data/gravity/earth/EGM96.cof` 和 CSSI 太空天氣檔都在（全攝動重播要用）。
- [ ] 用 `configs/shared/ranking_round.json` 從頭到尾演練一次 §四的步驟 1–8，**計時**，把實際時間填回 §二。
- [ ] 筆電充飽、行動電源、延長線、USB、證件；上太空中心官網確認組別。

---

## 四、逐步流程

### 步驟 1：建 config（5–10 分）

`configs/` 除了 `shared/` 都不進 git，當天自己複製一份：

```bash
cp configs/shared/ranking_round.json configs/local/ranking.json
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
uv run python odc.py tmax --config configs/local/ranking.json --boundary-km <邊界地心距離>
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
uv run python odc.py scoring --config configs/local/ranking.json \
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
uv run python odc.py scoring --demo-prelim
```

**沒有參考解時**，看「數量級檢查」：C_v 在 m/s 制應該是幾百到幾千，C_v < 50 幾乎一定還是 km/s；
`k_v·C_v` 和 `k_t·C_t` 是無單位的，單位一致地換算時不會變（初賽 3.506、14.99），只換了其中一個會差 1000 倍。
另外看 `C_t / T_max`：< 0.30 主攻快解，> 0.70 省油解可能有戲（初賽手冊 §七第 6 點）。

沒有警告、參考解落在整數，就加 `--write` 寫回 config。

### 步驟 4：體檢與可行性（2–5 分）

```bash
uv run python odc.py check configs/local/ranking.json
```

```bash
uv run python odc.py feasibility configs/local/ranking.json
```

- `odc.py check`：A/B 的近地點、平面夾角、T_max、`C_t / T_max` 有沒有離譜。排位賽格式不做初賽的
  「參考解 90 分」對照（步驟 3 已經驗過單位）。
- `odc.py feasibility`：**能量下限**。拆棒後至少 ⌈能量下限 / 250⌉ 棒；能量下限接近或超過 3,000 m/s，
  總 Δv 上限下可能無解，第一輪就要知道。**`MAX_BURNS` 維持範本的 [1, 2]**：它是拆棒前的路線棒數，
  DE 先找路線、拆棒器再拆，不要照下限放大。

### 步驟 5：3 顆種子並行求解（演練 12.6 分）

做 3 份只差 `optimization.SEED` 的 config（`SEED: null` 會讓搜尋開多執行緒，3 個行程互搶核心）：

```bash
for s in 0 1 2; do python3 -c "import json;d=json.load(open('configs/local/ranking.json'));d['optimization']['SEED']=$s;json.dump(d,open('configs/local/ranking_s$s.json','w'),ensure_ascii=False,indent=2)"; done
```

開 3 個終端各跑一顆（或一行背景跑完再 `wait`）：

```bash
for s in 0 1 2; do uv run python odc.py solve configs/local/ranking_s$s.json  --stop-after solve --run-dir outputs/runs/rank-s$s -q & done; wait
```

先停在 solve，拿到 `mission.json` 再做重瞄準和驗證，搜尋就不用重跑。
DE 先找少棒數的路線，再由 `AUTO_SPLIT_LEGALIZE`（預設開）拆成每棒 ≤ 250 − 2 m/s（`MAX_DV_MARGIN_MPS` = 2）。
拆棒設定（stm、三起點、剔空棒、600 s 預算、3 行程）已是預設，不需手動填入；覆寫與退回方式見 [README 的 strategy 參數表](../../README.md#strategy-裡幾個值得知道的開關)。

跑完比三顆的 `mission.json`（`score`、`disqualified`），挑分數最高、沒失格的那顆：

```bash
for s in 0 1 2; do python3 -c "import json;d=json.load(open('outputs/runs/rank-s$s/mission.json'))['mission_info'];print($s,d['score'],d['disqualified'],d['num_burns'],round(d['total_dv_mps'],1))"; done
```

- 失格（`disqualified: true`）就**不能交**。結束碼 3 =「找不到合法路線」：看 `no_legal_route.json`
  裡最接近的候選超標多少，照終端機的建議（加 MAXITER、加種子、檢查 T_max 與能量下限）重跑。
- 記下 Δr_min、ΔV_team、T_team、棒數、最大單棒。

### 步驟 6：全攝動 B 平面重瞄準（2–5 分）

為什麼要做：我們瞄 Δr ≈ 3.5 km，離 5 km 只剩 1.5 km；J2–J4 → 全攝動在 1.6 h 以內的任務就偏 0.5–1.3 km，
22.6 h 的 hyper_far 偏 263 km（[PERTURBATION_GAP](../research/PERTURBATION_GAP_20261019.md) §2）。
B 平面重瞄準只要多花 0.04–4.6 m/s，所有試過的解都收斂。

**做法要點（兩條路都一樣）：**
- 只消垂直於相對速度的兩個分量（B 平面），**不要用定時位置對齊**：hyper_far 會多花 272 m/s、
  最後一棒變 361 m/s，直接失格。
- 改有餘裕的那一棒（通常是最後的微調棒）。拆出來的棒大多貼著 248 m/s，改那種棒會超標。
- 力學模型用全攝動；官方公布曆元和太空船參數之後換成官方的（[問題 1–6](QUESTIONS_FOR_ORGANIZER.md)）。

把步驟 5 挑中的那顆（下例是 seed 2）拿來重瞄準：

```bash
uv run python odc.py retarget outputs/runs/rank-s2/mission.json --config configs/local/ranking.json   --run-dir outputs/runs/rank-rt
```

演練結果（33 s）：原方案在全攝動下 d_min 3,787 m（還在 5 km 內），重瞄準後 3.2 m，總 Δv +0.57 m/s；
終端機印 `✅ 全攝動重瞄準通過` 和繳交腳本的路徑。失敗或失格時會保留原方案並警告，**不會產生繳交腳本**。

- **看改的那一棒還剩多少餘裕。** 預設改最後一棒，演練時從 247.98 變成 248.55 m/s（離 250 剩 1.45 m/s）。
  拆出來的棒多半貼著 248 m/s，修正量大時可能超標而被拒；這時用 `--retarget-burn N` 改一棒有餘裕的
  （演練的第 2 棒只有 97 m/s）。
- 太空船參數用的是我們的預設（850 kg、Cd 2.2、Cr 1.8、阻力面積 6 m²、SRP 面積 8 m²），官方公布後要換。
  在官方公布之前，長時間停在低軌的任務要另外評估命中率
  （`scripts/research/perturbation_gap.py` 的 `--mc`，見 [PERTURBATION_GAP](../research/PERTURBATION_GAP_20261019.md)）。

### 步驟 7：GMAT 驗證（1–3 分）

```bash
uv run python odc.py verify outputs/runs/rank-rt/output_submit.txt --config configs/local/ranking.json  --run-dir outputs/runs/rank-verify
```

- 固定燃燒版（`output_submit.txt`）才是繳交用的，跟初賽一樣。演練 8 s，印 `✅ GMAT 獨立驗證通過`。
- 重瞄準產的腳本用全攝動模型（`FORCE_MODEL = ranking_full`：EGM96、日月、NRLMSISE00、SRP、相對論），
  也帶著我們的太空船參數。**繳交時要不要保留這些設定**，看[問題 6、12](QUESTIONS_FOR_ORGANIZER.md) 的答案。
- 沒做重瞄準的腳本是 J2–J4（`JGM2.cof`、`Drag = None`、`SRP = Off`），全攝動下會差公里等級，不要直接交。

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
改 B 的設定與機動、至少模擬一次產生 Report，再把 Script + Report 上傳（[初賽手冊](../archive/prelim/CONTEST_DAY.md) §10.2）。
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
7. **`odc.py check` 最後的「參考解 90 分」只對初賽範例有意義**，排位賽忽略。
8. **共用情境的 T_MAX_SEC 是編的**，不要拿它們的值當排位賽的參考（步驟 2 的表）。
9. GMAT 腳本不能有非 ASCII 字元；`configs/` 不進 git；同分先比 d_min（同初賽手冊 §七）。
