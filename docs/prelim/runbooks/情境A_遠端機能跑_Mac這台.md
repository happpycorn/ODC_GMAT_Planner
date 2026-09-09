# 情境 A（遠端機能跑）── Mac 這台的操作卡

> 前提：已確認可連遠端機。這台（Mac）在賽場，是**探索機 + 對主辦機的橋 + 提交機**。
> 配對文件：遠端機那台看 [情境A_遠端機能跑_遠端機這台.md](情境A_遠端機能跑_遠端機這台.md)。
> 遠端機一旦連不上或被判不能用，**立刻改走** [情境B_遠端機不能跑_Mac單機.md](情境B_遠端機不能跑_Mac單機.md)。

## 這台的定位：**探索機 + 橋 + 提交機**

- **探索**：跟遠端機同時跑「另一條分支」搶時間（遠端跑省油/預設，這台跑快解）。
- **橋**：SSH 進遠端機下指令、把遠端機產出的 `output_submit.txt` 拉回來。
- **提交**：這台在賽場、離主辦機最近，最終把檔案搬上**主辦機**提交（正式提交必須在主辦機做）。

---

## 一、賽前一晚檢查（Mac 上做）

```bash
cd <Mac 上的專案路徑>
git pull --rebase
uv sync
```

- [ ] **Mac 能離線單機跑**：拔網路，`uv run python main.py --config configs/official_sample.json --no-gmat`
      要能跑完、印出 Score。（這證明就算遠端機掛了，Mac 也能靠自己找解——見情境 B。）
- [ ] **Mac 上 GMAT 裝了沒？** 有 → 記下 Mac 的 GmatConsole 路徑（**不是** config 裡那個 Linux 路徑），
      跑時用 `--gmat-console <mac路徑>` 覆蓋。沒有 → Mac 只做 `--no-gmat` 搜尋，GMAT 驗證交給遠端機或主辦機。
- [ ] **SSH 進得去遠端機**：`ssh <user>@<remote-host>`（把 `<user>@<remote-host>` 換成實際的，今晚就填進這張卡）。
      進去後 `cd ~/ODC_GMAT_Planner && git pull --rebase && uv sync` 確認遠端也是最新。
- [ ] **對主辦機的搬檔方式想好**：帶 **USB 隨身碟**（賽場主辦機不一定能上網）。確認 Mac 能寫 USB。
- [ ] 充飽電 + 行動電源 + 延長線（官方不保證有插座）。

---

## 二、開賽流程

### 0–8 分：抄題（你抄一份，隊友 A 抄一份互相對）→ 建 config

- 六根數 + 計分參數逐字元對；單位陷阱 `k_v ÷1000`、`C_v ×1000`（CONTEST_DAY.md §四）。
- 建 `configs/contest.json`。**兩台要用同一份**：在 Mac 建好後 `scp` 給遠端機，或反之。
  ```bash
  scp configs/contest.json <user>@<remote-host>:~/ODC_GMAT_Planner/configs/
  ```

### 8–15 分：遠端機跑基準解，你在 Mac 準備兩條分支的 config

- 遠端機跑 `feasibility.py` + 基準 `main.py`（見遠端機卡）。
- 你在 Mac 準備：
  - `configs/econ.json` = 省油/預設（不動 `T_MAX_SEC`）——**交給遠端機跑**。
  - `configs/fast.json` = 快解 = contest.json 加一行 `rules.T_MAX_SEC: <想要的抵達上限秒數>`
    （例如壓在參考解 3,212s 或 `C_t` 附近）。**這台跑這條。**

### 15–60 分：這台跑快解分支（搜尋）

Mac 有 GMAT：
```bash
uv run python main.py --config configs/fast.json --gmat-console <mac-gmat-path>
```
Mac 沒 GMAT（只搜尋、不驗證）：
```bash
uv run python main.py --config configs/fast.json --no-gmat
```
- 把印出的 **Score / Δr_min / ΔV_team / T_team** 唸給隊友 A 記進計分表，跟遠端機那條比。
- 這台跑的同時，遠端機在跑 econ.json。**兩條並行、Score 直接比，不要猜。**

### 60–75 分：定案 → 從遠端機把最終檔拉回 Mac

1. 勝出分支確定後，讓**遠端機**跑最終那趟（best-of-2 seed + GMAT 驗證，見遠端機卡），
   因為遠端機一定有 GMAT、可信。
2. 把遠端機產出的檔拉回 Mac：
   ```bash
   scp <user>@<remote-host>:~/ODC_GMAT_Planner/outputs/output_submit.txt ./outputs/
   scp <user>@<remote-host>:~/software/GMAT/GMAT/R2026a/output/GMAT_InterceptReport.txt ./outputs/
   ```

### 75–90 分：搬上主辦機 → 提交

1. `output_submit.txt`（+ Report）拷到 **USB** → 插上**主辦機**。
2. 在主辦機的 GMAT 裡產生官方 Report 並提交（見下「提交步驟」）。
3. 隊友 A 盯到「提交成功」。

---

## 三、提交步驟（在主辦機上，CONTEST_DAY.md §10.2）

初賽是「改 Script」制：下載題目 Script → 改 Spacecraft B → 存檔模擬產生 Report → 上傳 Script + Report。

**我們的 `output_submit.txt` 是一份完整 GMAT script（ASCII、無求解器、燃燒值寫死）。** 兩條路，
**開賽時先問工作人員哪種可接受**（併進 CONTEST_DAY.md §10.1 提問）：

1. **可直接上傳自己的 script** → 在主辦機 GMAT 開 `output_submit.txt`、跑一次產生 Report、上傳兩者。
2. **必須改他們給的 Script 的 Spacecraft B** → 從 `output_submit.txt` 讀出 **burn table**
   （每棒的時間 + dVx/dVy/dVz），把這些值填進主辦 Script 的 Spacecraft B 機動，跑一次產生 Report、上傳。

**不論哪種，可攜的核心產物是「burn table」**——時間 + 三軸 dV。這張表抄對，就能在任何 GMAT 重現。
**這一步賽前一定要在主辦機類似環境彩排一次**（沒 GMAT 的話至少手動演練填 burn）。

⚠️ 主辦機 GMAT script **不能有非 ASCII 字元**（中文註解會讓解析失敗，歷史踩過三次）。手改別打中文。

---

## 四、卡關備援

- **SSH 斷線 / 遠端機沒回應** → 別等，直接切 [情境B_遠端機不能跑_Mac單機.md](情境B_遠端機不能跑_Mac單機.md)，
  Mac 靠自己把兩條分支都跑掉。這就是賽前一晚要驗「Mac 拔網路能跑」的原因。
- **Mac 沒 GMAT，不確定 Python 解對不對** → 搜尋照跑（`--no-gmat`），把 `output_submit.txt` 帶到
  主辦機做唯一一次 GMAT 驗證；主辦機驗過就是官方認的。
- **Claude 掛了**（你平常靠 Claude 下指令/判斷）→ 切 [情境C_Claude壞掉_改用Gemini.md](情境C_Claude壞掉_改用Gemini.md)，
  工具是純 Python、不需要 Claude，照那張卡逐行敲、判斷用 Gemini。
