# 模擬題對答案（全部跑完再看）

11-07 晚上 Claude 在 Mac 上用同一份題目跑出來的結果，設定檔和輸出都放在暫存區，沒有寫進 `configs/local/`、`outputs/runs/`、`medal/day/`。

## 題目裡埋的陷阱

| # | 地方 | 正確做法 |
|---|---|---|
| 1 | 排位賽邊界給**高度** 60,000 km | `tmax --boundary-alt-km 60000`（不是 `--boundary-km`） |
| 2 | `C_t` 給 11.5 **小時** | `--Ct 11.5 --Ct-unit h` → 41,400 s |
| 3 | `k_v`、`C_v` 給 km/s 制 | `--kv 2.2 --kv-unit "1/(km/s)" --Cv 1.75 --Cv-unit km/s` → 0.0022、1,750 |
| 4 | A 的 TA = 238°，起點在邊界外 | tmax 的「註」會說 A 先往內穿過邊界、過近地點再穿出；這是對的 |
| 5 | 曆元、太空船參數藏在 Script 裡 | 都要抄進 `strategy`（`GMAT_EPOCH`、`GMAT_EPOCH_FORMAT`、`GMAT_SPACECRAFT`） |
| 5b | 初始狀態只給位置速度，沒有六根數 | 用 GMAT 讀出六根數，見下面「從 Script 讀根數」 |
| 6 | 金牌賽 ΔV_lim 給 **0.2 km/s** | 規則檔填 **200**（m/s） |
| 7 | T_round 給 **15 分鐘** | `window_sec` 填 **900** |
| 8 | 安全空域給**高度** 1,050–1,110 km | `safe_sma_km` 填 **[7428.137, 7488.137]** |
| 9 | 船名是 SC_Red／SC_Blue，工具認不出來 | parse、new 都加 `--names pursuer=SC_Red,evader=SC_Blue` |
| 10 | 兩艘 epoch 差 1.5 小時 | parse 會印「pursuer 的 epoch 較早，已用二體傳播 5400.000 秒對齊」 |
| 11 | **USB 檔是 CSV，role_select 只吃 JSON**（見下面「手冊缺口」） | 先轉檔再跑角色選擇器（手冊步驟 3 已補） |

## 排位賽

**從 Script 讀根數**：GMAT 開 `RankingRound_Problem.script` → 左邊 Resources 雙擊 `SC_Alien` → Orbit 分頁的 State Type 改成 `Keplerian`，六個欄位就是要填的根數（`SC_Human` 同樣做）。
**只看不要存**：改 State Type 不影響狀態，但不要按 Apply／存檔覆蓋原檔。GMAT 讀回來的數字在小數第 7 位以後有雜訊，這樣是正常的，照抄或四捨五入都可以：

| | SMA | ECC | INC | RAAN | AOP | TA |
|---|---|---|---|---|---|---|
| SC_Alien | -58000.0000072 | 1.3499999998 | 37.4999999858 | 145.0000000403 | 61.9999999795 | 237.9999999887 |
| SC_Human | 6928.1369999 | 0.0011999999 | 23.5000000006 | 120.0000000072 | 89.9999983847 | 15.0000016082 |

抄完用 `check` 的平面夾角 18.639° 對：對得上就表示 INC／RAAN 沒抄錯。

**該填的值**

```json
"orbit_A": {"SMA": -58000.0, "ECC": 1.35, "INC": 37.5, "RAAN": 145.0, "AOP": 62.0, "TA": 238.0},
"orbit_B": {"SMA": 6928.137, "ECC": 0.0012, "INC": 23.5, "RAAN": 120.0, "AOP": 90.0, "TA": 15.0},
"rules": {"T_MAX_SEC": 56567, "k_t": 6e-05, "C_t": 41400.0, "k_v": 0.0022, "C_v": 1750.0, "C_r": 40.0, ...},
"strategy": {"GMAT_EPOCH": "09 Nov 2026 02:45:00.000", "GMAT_EPOCH_FORMAT": "UTCGregorian",
             "GMAT_SPACECRAFT": {"DRY_MASS_KG": 620, "CD": 2.2, "CR": 1.5, "DRAG_AREA_M2": 3.5, "SRP_AREA_M2": 5.0}, ...}
```

**體檢應該看到**

| 項目 | 值 |
|---|---|
| tmax 解析解 | 56,567.573 s；點質量數值差 +1.2e-7 s；J2–J4 差 +0.052 s |
| A 近地點 | 20,300 km（高度 13,921.9 km），近地點時刻 42,662 s |
| A、B 平面夾角 | 18.639° |
| B 近地點高度 | 541.69 km |
| C_t / T_max | 0.732 |
| 能量下限 | 1,675.0 m/s，至少 7 棒；單棒最小 1,901.6 m/s（0 合法） |

**參考解**（`SEED=null`，你的分數差 ±0.1 屬正常）

| 項目 | 步驟 5 求解 | 步驟 6 重瞄準後 |
|---|---|---|
| 分數 | 74.8824 | **74.8809**（accepted） |
| 棒數 | 8 | 8，最大單棒 247.980 m/s |
| 總 Δv | 1,766.6 m/s | 1,766.82 m/s |
| T_team | 41,106 s | 41,101.2 s（離 T_max 15,466 s） |
| 命中 | — | 全攝動 d_min 0.020 km、GMAT Δr 0.020 km |
| 攔截前最低高度 | — | 541 km |

求解這次跑了 6 分 22 秒，但當時同一台 Mac 同時在跑金牌賽自我對打，**不能當計時**；你明天的時間才是準的（11-07 佔位題是 153 s）。
分數偏低（75 分）是因為 T 剛好落在 C_t 附近、Δv 1,767 m/s 也接近 C_v，時間項和燃料項都只拿一半左右，不是解不好。

## 金牌賽

**規則檔 `day/announced.json`**：`max_dv_pursuer_mps` 200、`max_dv_evader_mps` 200、`capture_radius_km` 8、`window_sec` 900、`safe_sma_km` [7428.137, 7488.137]。

**parse 應該看到**：追方高度 485.06 km、近地點高度 473.14 km；逃方高度 500.95 km、近地點高度 494.50 km；共同 epoch 2026-11-09 07:00:00 UTC。

**角色選擇器**（完整版 74 s，59 局）

| 項目 | 值 |
|---|---|
| 初始距離 | 329.5 km |
| 躲方初始 a | 6,878.1 km；安全空域中心偏移約 1.60 發容量 |
| 我方躲方 vs capture_pursuer | 100%（12 局全 escape） |
| 我方追方 vs safe_evader | 0% |
| 安全證書 | 6 回合都 23/23 |
| **建議** | **躲方** |

**對打**：選躲方時，第 1 回合 advise 這次給 `逃方, 1, -2.6180, 178.8761, -89.3110`，安全證書 margin 269 km（躲方會隨機挑近似最優的方向，你的數字不一樣是正常的）。
對手表是一場工具對工具的對局錄下來的：那場躲方 escape、最後 a = 7,429.64 km（在區間內，離下界只有 1.5 km）、全場最近 60.1 km。
第 6 回合交之前一定要看 `提交值推完 a = ...` 在 [7428.137, 7488.137] 裡。

## 手冊缺口（這次彩排順便找到的）

**CONTEST_DAY_FINAL 步驟 3 的角色選擇器只吃 JSON。** USB 檔是 CSV、GMAT 報表或純文字時會報「不是合法 JSON」。GUI 已經會自動轉檔，CLI 手冊沒寫。照 CLI 做時，在 `medal/` 下先轉：

```bash
.venv/bin/python ../gui/drl_state_to_json.py day/initial_state.csv day/initial_state.json --names pursuer=SC_Red,evader=SC_Blue
```

再把 `day/initial_state.json` 給 role_select。`final new --initial` 吃 CSV 沒問題，不用轉。11-07 已補進 CONTEST_DAY_FINAL 步驟 3（只改手冊，沒動程式）。
