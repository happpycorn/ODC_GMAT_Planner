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

| 時間 | 誰 | 做什麼 |
|---|---|---|
| 0–2 分 | 記錄 | USB 檔複製到 `day/`，填規則檔 |
| 2–3 分 | 主控 | parse 初始狀態 |
| 3–6 分 | 主控 | 角色選擇器（約 2 分鐘；`--fast` 約 40 s） |
| 6–9 分 | 全隊 | 看結果 |
| 9–10 分 | 主控 | 決定角色、告知工作人員、建 session |

**1. 規則檔**（只改四個數字）
```bash
mkdir -p day && cp configs/rulesets/final_official.json day/announced.json
open -e day/announced.json
```
- `max_dv_pursuer_mps`、`max_dv_evader_mps` ← ΔV_lim（**m/s**）
- `capture_radius_km` ← R_cap（km）
- `window_sec` ← T_round（**秒**）
- `safe_sma_km` ← `[lo, hi]`（**半長軸** km；給高度要加 6378.137）

**2. 初始狀態**
```bash
.venv/bin/python copilot.py final parse day/<USB檔>
```
|r| 應約 6700–8000 km、|v| 約 7–8 km/s。船名認不出來加 `--names pursuer=<船名>,evader=<船名>` 或 `--order pursuer,evader`。

- **經緯高**：先轉檔再 parse：
  ```bash
  .venv/bin/python tools/gmat_state_convert.py day/<經緯高.json> --out day/initial.json
  ```
  輸入 JSON 每艘寫 GMAT 欄位：`{"pursuer": {"DateFormat": "UTCGregorian", "Epoch": "09 Nov 2026 00:00:00.000",
  "CoordinateSystem": "EarthFixed", "DisplayStateType": "SphericalAZFPA", "RMAG": ..., "RA": 經度, "DEC": 緯度,
  "VMAG": ..., "AZI": ..., "FPA": ...}, "evader": {...}}`（FPA 水平 = 90°）。
- 都讀不了：`.venv/bin/python copilot.py final manual --out day/initial.json`，手動輸入 12 個數字。

**3. 角色選擇器**
```bash
.venv/bin/python tools/role_select.py day/<初始狀態.json> --rules day/announced.json --workers 4 --budget-sec 150
```

**預設選躲方。** 以下任一種才改選追方：

1. 題目特徵說「6 發都推滿也到不了安全空域」。
2. 我方躲方對 capture_pursuer 勝率明顯低於 100%。
3. 安全證書比例 < 90%。

**4. 建 session**
```bash
.venv/bin/python copilot.py final new --rules day/announced.json --initial day/<初始狀態.json> --role evader --out day/session.json
```
追方用 `--role pursuer`。兩艘 epoch 不同時會印傳播秒數，要跟公告對得上。

---

## 三、每回合流程（10 分鐘 × 6）

| 時間 | 誰 | 做什麼 |
|---|---|---|
| 0–2 分 | 記錄 | 回合起點狀態檔複製到 `day/` |
| 2–6 分 | 主控＋驗證 | `advise`，看三件事 |
| 6–8 分 | 記錄 | 手寫提交行；驗證唸數字核對 |
| 8–9 分 | 記錄 | 交出，留抄本 |
| 公告後 | 主控 | `announce` |

**advise**
```bash
.venv/bin/python copilot.py final advise day/session.json --state day/<本回合狀態檔>
```
第 1 回合不加 `--state`。讀不了改 `--manual`；趕時間加 `--fast`。

**交之前看三件事**
1. `重驗：通過`。沒通過就交工具最後一行給的替代值。
2. 躲方：`安全證書：成立`；最後一回合 `提交值推完 a = ...` 在 [lo, hi] 內。追方：照交。
3. `一致性檢查：通過`（第 2 回合起）。「疑似錯誤」→ 核對單位、角色有沒有對調、座標系、時間；仍以官方狀態為準。

**提交行**：照抄 `提交：` 後面那串，例如 `逃方, 3, 135.3134, -46.4445, -204.9590`。抄完用「手寫核對」那行逐個對正負號。

**announce**
```bash
.venv/bin/python copilot.py final announce day/session.json --opponent-dv <X> <Y> <Z> --our-dv <X> <Y> <Z> --state day/<下一回合狀態檔>
```
填主辦公告的實際 Δv；`--state` 沒有可省略。

整場摘要：`.venv/bin/python copilot.py final show day/session.json`

---

## 四、分工

| 角色 | 工作 |
|---|---|
| 主控 | 操作 Mac、決定採用 |
| 記錄 | 複製 USB 檔、填規則檔、手寫提交行、留抄本 |
| 驗證 | 唸數字核對、看重驗與一致性檢查、第 6 分鐘提醒時間 |

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
| `parse` 讀不了 | 看錯誤訊息；加 `--names`／`--order`；再不行用 `final manual` |
| 數字像公尺或 m/s | 換單位重填 |
| 經緯高狀態 | 用 `tools/gmat_state_convert.py` 轉；找不到 GMAT 就加 `--gmat-console "/Users/corn/Documents/GMAT R2026a/bin/GmatConsole"` |
| 重驗未通過 | 交工具最後一行 |
| 工具當掉 | 重開終端機重跑同一指令；不行就換備機（session 檔用 USB 帶過去） |
| 對手 Δv 被縮放 | 正常，`announce` 填公告值 |
| 時間不夠 | `advise --fast`；最壞情況躲方照上一回合方向推、追方不推，但一定要交 |
