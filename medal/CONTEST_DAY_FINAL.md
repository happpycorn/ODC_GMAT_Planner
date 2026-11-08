# 金／銅牌賽當天作戰手冊（2026-11-09 @ 大臺南會展中心）

> **比賽中禁止網路與生成式 AI**，隊員照這份自己做完。指令都在 `~/Documents/Program/ODC_Program/medal` 執行，一律用
> `.venv/bin/python`。`<...>` 換成實際檔名。venv 壞了：有網路時跑 `uv sync --python 3.12`。

## 一、規則重點

| 項目 | 規則 | 規則檔／工具 |
|---|---|---|
| 出手 | 雙方**同時**在回合起點各推一發，互相看不到 | |
| 回合 | **6 回合**，每回合滑行 T_round | `window_sec` |
| 單發上限 | ΔV_lim；超過會被等比例縮放 | `max_dv_*_mps`；工具交 ΔV_lim − 0.05 以內 |
| 總 Δv | 不設上限 | |
| 攔截 | 任一時刻距離 ≤ R_cap，追方贏 | `capture_radius_km` |
| 撞地 | 高度 < 0 的一方輸 | 工具推完近地點至少留 30 km |
| 逃方勝利 | 撐完 6 回合**且**最後半長軸 a 在安全空域 [lo, hi] | `safe_sma_km` |
| 力學 | 純二體 | |
| 提交 | `角色, 回合, ΔvX, ΔvY, ΔvZ`（m/s、EarthMJ2000Eq） | 照抄工具最後一行 `提交：...` |
| 角色 | 公告後 **10 分鐘**分析，排位較優的一方選 | 第二節 |

---

## 二、題目公告後的 10 分鐘

**一個人做，GUI 為主**：瀏覽器開 GUI 的「金／銅牌賽 → 抄公告與選角色」。開始前先看「規則與時程」頁的設定檔名稱是 `day`（彩排時換過名字的話要切回來）。GUI 壞了才照下面的 CLI 做（每一步 GUI 都有對應指令）。

| 時間 | 做什麼 | GUI |
|---|---|---|
| 0–3 分 | 照投影片抄五項（四個數字＋雙方 epoch、r、v），單位用下拉選 | 一頁表單，按「存檔」；有警告就核對投影片再按「我確定」 |
| 3 分 | 角色選擇器自動開跑（完整版約 150 s） | 存檔後自動開始；趕時間勾「快速版」 |
| 3–6 分 | 對照「念回」卡看一次數字；有 USB 檔就拖進同一頁比對 | 不一致的格子會標紅，可按「以 USB 檔為準」 |
| 6–9 分 | 看選擇器建議、依下面三條決定 | |
| 9–10 分 | 告知工作人員、建 session | 按「我們選躲方」或「我們選追方」 |

**預設選躲方。** 以下任一種才改選追方：

1. 題目特徵說「6 發都推滿也到不了安全空域」。
2. 我方躲方對 capture_pursuer 勝率明顯低於 100%。
3. 安全證書比例 < 90%。

### CLI 備援

**1. 規則檔**（四個數字）
```bash
mkdir -p day && cp configs/rulesets/final_official.json day/announced.json
open -e day/announced.json
```
- `max_dv_pursuer_mps`、`max_dv_evader_mps` ← ΔV_lim（**m/s**；給 km/s 要乘 1000）
- `capture_radius_km` ← R_cap（km）
- `window_sec` ← T_round（**秒**；給分鐘要乘 60）
- `safe_sma_km` ← `[lo, hi]`（**半長軸** km；給高度要加 6378.137）

**2. 初始狀態**（14 格：雙方 epoch、r km、v km/s）
```bash
cp configs/initial_template.json day/initial.json
open -e day/initial.json
.venv/bin/python copilot.py final parse day/initial.json
```
|r| 應約 6700–8000 km、|v| 約 7–8 km/s；兩艘 epoch 不同時會印「已用二體傳播 N 秒對齊」。

- **有 USB 檔**：`.venv/bin/python copilot.py final parse day/<USB檔> --names pursuer=<船名>,evader=<船名>`，跟上面念回的數字比對。
  要改用 USB 檔：`.venv/bin/python ../gui/drl_state_to_json.py day/<USB檔> day/initial.json --names pursuer=<船名>,evader=<船名>`。
- **經緯高**：`.venv/bin/python tools/gmat_state_convert.py day/<經緯高.json> --out day/initial.json`
  （輸入 JSON 每艘寫 GMAT 欄位：`{"pursuer": {"DateFormat": "UTCGregorian", "Epoch": "09 Nov 2026 00:00:00.000",
  "CoordinateSystem": "EarthFixed", "DisplayStateType": "SphericalAZFPA", "RMAG": ..., "RA": 經度, "DEC": 緯度,
  "VMAG": ..., "AZI": ..., "FPA": ...}, "evader": {...}}`，FPA 水平 = 90°）。
- 範本也壞了：`.venv/bin/python copilot.py final manual --out day/initial.json`（沒有 epoch 欄位，兩艘 epoch 不同時不能用）。

**3. 角色選擇器**
```bash
.venv/bin/python tools/role_select.py day/initial.json --rules day/announced.json --workers 4 --budget-sec 150
```

**4. 建 session**
```bash
.venv/bin/python copilot.py final new --rules day/announced.json --initial day/initial.json --role evader --out day/session.json --names pursuer=<船名>,evader=<船名>
```
追方用 `--role pursuer`。船名是 `--names` 給的，**session 會記住**，之後每回合讀狀態檔自動套用，不用再給。

---

## 三、每回合流程（10 分鐘 × 6）

GUI「每回合」頁只有一條路，畫面上永遠只有下一步：

| 時間 | 做什麼 | GUI |
|---|---|---|
| 0–1 分 | 主辦發下上一回合結束的狀態檔 → 拖進頁面（第 1 回合沒有這步） | 自動反推雙方 Δv、核對、記錄；倒數自動開始 |
| 1–4 分 | 建議自動跑 | 6 分鐘還沒出來會自動改快速版 |
| 4–7 分 | 照大字提交行手寫；再把紙上寫的打進「照紙上打一次」框 | 不一樣的字元標紅；X／Y／Z 正號綠、負號紅 |
| 7–8 分 | 交出，按「已交出」 | 8:30 倒數轉紅、9:00 跳「現在就交」 |

主辦有唸或秀出對手 Δv 時，可以在放檔前填進「選填」三格，只拿來比對；以檔案反推值為準。

**交之前看三件事**（GUI 已經判好，❌ 時提交行會自動換成該交的那行）
1. `重驗：通過`。沒通過就交工具最後一行給的替代值。
2. 躲方：`安全證書：成立`；最後一回合 `提交值推完 a = ...` 在 [lo, hi] 內。追方：照交。
3. `反推：通過`（第 2 回合起）。警告時看下表。

### 放檔後的訊息

| 訊息 | 意思 | 做什麼 |
|---|---|---|
| 這份檔第 N 回合已經用過了 | 放到舊檔 | 放主辦剛發的那份 |
| 這是本回合起點的狀態，不是回合末 | 放錯檔 | 同上 |
| 回不到本回合起點／超過上限 | 檔不是本回合結束、船名對調、單位錯，或 T_round／ΔV_lim 抄錯 | 核對後再放；確定要用加 `--force`（GUI 有按鈕） |
| 主辦執行的我方 Δv 跟提交行差 … | 主辦抄錯或我們手寫錯 | 馬上找工作人員核對 |
| 檔案時間比回合起點晚 … 但 T_round 是 … | T_round 抄錯，或主辦提早結束本回合 | 看主辦公告；工具已用檔案時間反推 |
| 比賽應已結束 | 依檔案推算本回合已攔截／撞地 | 以主辦公告為準 |
| 你打的對手 Δv 跟檔案反推差 … | 手打值抄錯，或主辦唸錯 | 以檔案為準，不用處理 |

### CLI 備援：每回合兩行

```bash
.venv/bin/python copilot.py final advise day/session.json
```
照抄最後一行 `提交：...`，用「手寫核對」那行逐個對正負號。交出後，主辦發下回合末狀態檔：
```bash
.venv/bin/python copilot.py final announce day/session.json --state day/<回合末狀態檔>
```
每份狀態檔只給這一次；下一回合 `advise` 不用 `--state`。要比對手打的對手 Δv 加 `--opponent-dv X Y Z`。
**沒有狀態檔、只有公告 Δv**：`announce day/session.json --opponent-dv X Y Z`（舊用法，工具自己推下一回合起點）。

整場摘要：`.venv/bin/python copilot.py final show day/session.json`

---

## 四、一個人做三個人的事

| 原本 | 現在 |
|---|---|
| 複製 USB 檔 | 拖進 GUI，自動複製到 `day/` |
| 手寫提交行、留抄本 | 仍要手寫；GUI 記下每回合提交行與交出時刻（`day/submissions.json`） |
| 唸數字核對 | 公告用「念回」卡；提交行用「照紙上打一次」 |
| 看重驗、一致性 | GUI 自動判斷，沒過時直接換成該交的那行 |
| 提醒時間 | 倒數＋8:30 轉紅＋9:00「現在就交」 |

---

## 五、提交格式要改時

改 `configs/final_format.json` 後要**重建 session**（或建 session 時加 `--format <檔>`）：
```json
{"role_names": {"pursuer": "追方", "evader": "逃方"}, "round_base": 1, "decimals": 4, "dv_margin_mps": 0.05,
 "template": "{role}, {round}, {dvx}, {dvy}, {dvz}"}
```
英文角色名改 `role_names`；回合從 0 算改 `"round_base": 0`；兩位小數改 `"decimals": 2`。

---

## 六、戰術

- **躲方**：照工具交。不要手動改成每回合推同一個方向。
- **追方**：抓不到會算證書的躲方；機會在對手犯錯（閃法太直覺、最後 a 不在安全空域）。照工具交。

---

## 七、故障應變

| 狀況 | 做法 |
|---|---|
| 狀態檔船名認不出 | GUI 會問哪個是追方；CLI 加 `--names pursuer=<船名>,evader=<船名>`（之後 session 會記住） |
| `parse` 讀不了 | 看錯誤訊息；加 `--names`／`--order`；再不行照範本手打 `day/initial.json` |
| 數字像公尺或 m/s | 換單位重填 |
| 經緯高狀態 | 用 `tools/gmat_state_convert.py` 轉；找不到 GMAT 就加 `--gmat-console "/Users/corn/Documents/GMAT R2026a/bin/GmatConsole"` |
| 重驗未通過 | 交工具最後一行 |
| 工具當掉 | 重開終端機重跑同一指令；不行就換備機（session 檔用 USB 帶過去） |
| 對手 Δv 被縮放 | 正常；反推值就是實際執行值 |
| 時間不夠 | `advise --fast`；最壞情況躲方照上一回合方向推、追方不推，但一定要交 |
