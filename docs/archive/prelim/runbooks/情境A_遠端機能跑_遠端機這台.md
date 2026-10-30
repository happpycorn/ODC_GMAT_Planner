# 情境 A（遠端機能跑）── 遠端機這台的操作卡

> 前提：開賽時問過工作人員、**確認可以連自己的遠端計算機**（見 [CONTEST_DAY.md](../CONTEST_DAY.md) §10.4）。
> 這台是 Linux 16 核 + 已裝 GMAT（`config` 裡的 `local.gmat_console_path` 是這台的路徑）。
> 配對文件：同情境下 Mac 這台看 [情境A_遠端機能跑_Mac這台.md](情境A_遠端機能跑_Mac這台.md)。

## 這台的定位：**驗證機 + 提交來源機**

遠端機是「有 GMAT、算得快、可信」的那台。**最終要繳交的 `output_submit.txt` 從這台產出**，
GMAT 驗證也在這台做。Mac 負責同時探索另一條分支、餵分數回來比。

分工一句話：**遠端機跑「會被採用」的那條 + 做 GMAT 驗證；Mac 跑「另一條」搶時間探索。**

---

## 一、賽前一晚檢查（今晚就做，別留到當天）

```bash
cd ~/ODC_GMAT_Planner
git pull --rebase
uv sync
```

- [ ] `uv run python main.py --config configs/official_sample.json` 完整跑一次，最後看到
      **違規次數 = 0**、GMAT 三個 ✅（命中/收斂/合規）、印出 Score ≈ 90。
- [ ] `GmatConsole` 路徑還在：`ls /home/corn/software/GMAT/GMAT/R2026a/bin/GmatConsole`
      （若搬過，改 `configs/*.json` 的 `local.gmat_console_path`）。
- [ ] 從 Mac SSH 進得來這台（讓 Mac 端測，指令在 Mac 卡）。記下這台的**對外位址/使用者**寫進 Mac 卡。
- [ ] 確認網路穩：這台在賽場是靠 Mac SSH 進來的，斷線就等於這台消失 → 所以 **Mac 必須能單機自足**
      （那是情境 B）。這台是紅利，不是命脈。

---

## 二、開賽流程（時間軸見 CONTEST_DAY.md §四）

### 0–8 分：抄題 → 建 config → 體檢

1. 隊友 A 抄一份、你抄一份 A/B 六根數 + `k_t/C_t/k_v/C_v`，**逐字元對**。
   ⚠️ 單位陷阱：`k_v = 官方 kv ÷ 1000`、`C_v = 官方 Cv × 1000`（CONTEST_DAY.md §四）。
2. 建 `configs/contest.json`（範本見 CONTEST_DAY.md §5.1；`local.gmat_console_path` 用這台的 Linux 路徑）。
3. 體檢，數字不對就是抄錯，回頭核對、別硬跑：
   ```bash
   uv run python check_problem.py --config configs/contest.json
   ```
   看 T_max（初賽圓軌道應是小時級）、A/B 平面夾角、近地點高度、`C_t/T_max`。

### 8–15 分：基準解（含 GMAT 驗證）

先在這台跑一次完整流程，手上先有能交的東西（防交白卷）：
```bash
uv run python feasibility.py --config configs/contest.json     # 先知道最少幾棒、單棒可不可行
uv run python main.py --config configs/contest.json            # 完整搜尋 + GMAT 驗證
```
- 單棒不可行 → config 的 `optimization.MAX_BURNS` 往上加（`[1,2,3]` 起）。

### 15–60 分：兩條分支對打（**這台跑省油/預設分支**）

- 這台跑 **省油/預設分支**（全旋鈕 + 預設 `REVS_ENSEMBLE:true`），命名 `configs/econ.json`：
  ```bash
  uv run python main.py --config configs/econ.json
  ```
- Mac 同時跑 **快解分支**（`rules.T_MAX_SEC`）。兩邊 Score 由隊友 A 記進計分表比。
- 提醒：範例題上「快 vs 省油」差到 90 vs 74，**哪條贏完全看當天 `k_t/C_t`**，不要用猜的。

### 60–75 分：定案 → 這台產出最終 `output_submit.txt`

1. 用勝出的 config，在這台跑**同 config、換 `SEED` 各一次**（best-of-2 seed，抗 seed 脆弱），取
   規則§6 較好的那趟。
2. 最終那趟完整跑（含 GMAT 驗證），確認：
   ```bash
   uv run python main.py --config configs/<勝出>.json
   ```
   - 產物：`outputs/output.txt`（含求解器）、**`outputs/output_submit.txt`（繳交用，寫死無求解器）**、
     GMAT Report 在 `~/software/GMAT/GMAT/R2026a/output/GMAT_InterceptReport.txt`。
3. **把 `outputs/output_submit.txt`（+ GMAT Report）傳回 Mac**（Mac 卡有 `scp` 指令），因為
   **正式提交是在主辦機做**（見 CONTEST_DAY.md §10.2），主辦機在賽場、Mac 是橋。

### 75–90 分：交給 Mac / 隊友 A 走提交流程

這台的任務到「產出已驗證的 `output_submit.txt` 並傳給 Mac」為止。提交在主辦機上做。

---

## 三、繳交前檢查清單（CONTEST_DAY.md §六，這台先跑過一遍）

- [ ] 違規次數 = 0
- [ ] GMAT：命中 ✅ / Targeter ✅ 收斂 / 最後一棒 ✅ 合規
- [ ] **固定燃燒版 `output_submit.txt` 也通過驗證**（印「👉 命中且合規，可以直接繳交」）
- [ ] `Δr_min` < 5,000 m、`T_team` < T_max
- [ ] GMAT 跟 Python 落差在公尺級（差到公里就要查）
- [ ] 記下 `Δr_min / ΔV_team / T_team`（同分時比這三個）

---

## 四、這台卡關時的備援

- **GMAT Targeter 卡住**：先看 stdout 的 `Variance`；若第一次 nominal pass 已在 0.01 km 內就別亂調。
  真要救，在 `Create DifferentialCorrector DC_Targeter;` 後插一行：
  `GMAT DC_Targeter.Algorithm = 'Broyden';`（細節 CONTEST_DAY.md §七第 5 點）。
- **搜尋跑不完**（T_max 天級才會發生，初賽圓軌道不會）：降級順序 `REVS_ENSEMBLE:false` →
  `MAX_BURNS` 砍 → popsize/iters 砍（CONTEST_DAY.md §4.1 降級表）。
- **這台整台連不上/被判不能連網** → 立刻切 [情境B_遠端機不能跑_Mac單機.md](情境B_遠端機不能跑_Mac單機.md)，
  Mac 接手全部。這就是為什麼 Mac 一定要離線自足。
