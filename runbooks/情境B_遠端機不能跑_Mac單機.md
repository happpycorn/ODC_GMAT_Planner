# 情境 B（遠端機不能跑）── Mac 單機完成全部

> 什麼時候切到這張：遠端機**連不上**、**被工作人員判定不能連網**、或**現場網路爛掉**。
> 別跟遠端機耗——Mac 一台就能把整場打完，只是少了並行、時間排得緊一點。
> 這是整套策略的**命脈**，所以賽前一晚**一定要驗過 Mac 能離線自足**。

## 核心事實：搜尋不需要 GMAT，也不需要遠端機

- **找 burn（搜尋）＝純 Python**，Mac 本機就能跑，可離線（`--no-gmat`）。
- **GMAT 只用在「驗證 + 產 Report」**。就算 Mac 沒 GMAT 也不致命——**官方最終驗證本來就在主辦機做**。
- 初賽 A 是圓軌道（T_max 小時級），**一輪只要 ~2 分鐘**。單機把好幾輪排成序列跑，90 分鐘綽綽有餘。

---

## 一、賽前一晚檢查（Mac，拔網路做）

```bash
cd <Mac 上的專案路徑>
git pull --rebase      # 先連網更新
uv sync
# —— 然後拔掉網路 ——
uv run python main.py --config configs/official_sample.json --no-gmat
```
- [ ] 拔網路後上面這行**能跑完、印出 Score**（證明離線自足）。
- [ ] Mac 有沒有 GMAT？
  - **有** → 記下 Mac 的 GmatConsole 路徑，本機也能驗證：`--gmat-console <mac路徑>`。
  - **沒有** → 沒關係，全程 `--no-gmat`，GMAT 驗證留到主辦機。**把這件事當常態、不要當意外。**
- [ ] USB 隨身碟能寫（要把檔搬去主辦機）。

---

## 二、開賽流程（單機序列，不並行）

### 0–8 分：抄題 → 建 config → 體檢

1. 你抄一份、隊友 A 抄一份，逐字元對。單位陷阱 `k_v ÷1000`、`C_v ×1000`（CONTEST_DAY.md §四）。
2. 建 `configs/contest.json`（範本 CONTEST_DAY.md §5.1）。
   - Mac 有 GMAT → 把 `local.gmat_console_path` 改成 Mac 的路徑；或每次用 `--gmat-console`。
   - Mac 沒 GMAT → 一律加 `--no-gmat`。
3. 體檢：
   ```bash
   uv run python check_problem.py --config configs/contest.json
   ```
   看 T_max、平面夾角、近地點高度、`C_t/T_max`；數字不對＝抄錯，回頭核對別硬跑。

### 8–15 分：可行性 + 基準解

```bash
uv run python feasibility.py --config configs/contest.json
uv run python main.py --config configs/contest.json --no-gmat     # 有 GMAT 就拿掉 --no-gmat
```
- 單棒不可行 → `optimization.MAX_BURNS` 往上加。

### 15–55 分：兩條分支「序列」跑（單機沒得並行，就一條接一條）

因為一輪 ~2 分鐘，序列跑完全來得及：
```bash
# 省油/預設分支
uv run python main.py --config configs/contest.json --no-gmat
# 快解分支：contest.json 複製成 fast.json，加一行 rules.T_MAX_SEC: <抵達上限秒數>
uv run python main.py --config configs/fast.json --no-gmat
```
- 隊友 A 把兩條的 **Score / Δr_min / ΔV_team / T_team** 記下來比。哪條贏看當天 `k_t/C_t`。

### 55–70 分：定案 + best-of-seed（序列）

勝出 config 換 `SEED` 再跑 1–2 次，取規則§6 較好的那趟：
```bash
uv run python main.py --config configs/<勝出>.json --no-gmat        # SEED 改幾個值各跑一次
```
最後一趟務必產出 `outputs/output_submit.txt`（工具自動產）。

### 70–90 分：搬上主辦機 → 唯一一次 GMAT 驗證 + 提交

**這是關鍵**：若 Mac 沒 GMAT，`output_submit.txt` 到目前**還沒被任何 GMAT 驗證過**（只有 Python 端算過）。
所以主辦機那一步同時扮演「驗證」+「產 Report」+「提交」：

1. `outputs/output_submit.txt` 拷到 USB → 插主辦機。
2. 主辦機 GMAT 開 `output_submit.txt` **跑一次**：
   - 看 **MissDistance / Δr** 是否 < 5 km、最後一棒是否 ≤ 1500 m/s。
   - Python 跟 GMAT 落差應在公尺級；**若差到公里級，代表某處抄錯或幾何不對，回頭查、別硬交。**
3. 產生 Report，依 §10.2 兩種提交路（上傳自己 script / 或把 burn table 填進主辦 script）擇一，
   **開賽時先問工作人員哪種可接受**。
4. 隊友 A 盯到「提交成功」。

> 若 Mac **有** GMAT：15–70 分那幾趟就順手拿掉 `--no-gmat` 本機先驗過，主辦機那步就只是重現 + 提交，
> 心裡更有底。

---

## 三、單機版時間預算（初賽圓軌道，實測 ~2 分鐘/輪）

| 段 | 內容 | 累計 |
|---|---|---|
| 0–8 | 抄題 + config + 體檢 | 8 |
| 8–15 | 可行性 + 基準 | 15 |
| 15–55 | 省油 + 快 各一輪 + 看分數 | ~25（其餘是判斷/記錄的緩衝）|
| 55–70 | best-of-seed | ~10 |
| 70–90 | 主辦機驗證 + 提交 | 20 |

算力完全不是瓶頸，**瓶頸是抄題正確性 + 提交流程順不順**。所以隊友 A 的核對、和賽前彩排提交，
比多跑幾輪重要得多。

---

## 四、卡關備援

- **搜尋跑不完**（初賽圓軌道幾乎不會）：`REVS_ENSEMBLE:false` → 砍 `MAX_BURNS` → 砍 popsize/iters
  （CONTEST_DAY.md §4.1）。
- **主辦機 GMAT 驗不過 / Δr 差到公里**：多半是 config 抄錯或 A/B 弄反，回 `check_problem.py` 對數字。
- **連 Claude 也掛了**：切 [情境C_Claude壞掉_改用Gemini.md](情境C_Claude壞掉_改用Gemini.md)。工具純 Python 不需要 Claude。
- ⚠️ 手改主辦機 script **不可打中文**（非 ASCII 會讓 GMAT 解析失敗）。
