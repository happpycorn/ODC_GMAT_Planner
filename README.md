# 🚀 軌道攔截設計賽 - 任務規劃工具 (Rocket Trajectory Calculator)

本程式用於「軌道攔截設計賽」初賽：讓太空船 B（地球）以多次瞬時脈衝機動，在時間限制內攔截太空船 A（外星人，被動、只受重力影響），同時兼顧燃料消耗與任務效率。底層採用多核心 (Multiprocessing + Threading) 與 JIT (Numba) 技術加速運算，並用 L-SHADE 全域搜尋 + L-BFGS-B 局部微調找解，最後產出可直接匯入 GMAT 的任務腳本。

為了確保最佳的執行效能與最簡便的安裝體驗，本專案使用新一代極速套件管理工具 `uv`，不需要手動設定虛擬環境。

---

## ⚠️ 系統環境需求

請確認您的電腦已安裝 **Python 3.8 或以上版本**。
（若尚未安裝，請至 [Python 官方網站](https://www.python.org/downloads/) 下載安裝）

---

## 步驟一：安裝 `uv` 工具

請打開終端機 (Mac) 或 命令提示字元/PowerShell (Windows)，輸入以下指令：

```bash
pip install uv
```

---

## 步驟二：設定 `configs/config.json`

程式第一次執行時，如果找不到設定檔會自動生成一份預設範例，但**正式提交前務必手動確認以下欄位是主辦方公布的正式數字**，不是範例值：

config 分四大塊，各自對應「誰決定這個數字」：`orbit_A`/`orbit_B`（軌道六根數）、`rules`（主辦方規定/公告的數字，我們不能改）、`strategy`（我們自己的任務設計選項，不是規則要求）、`optimization`（純演算法搜尋設定，只影響找不找得到好解/要跑多久，不影響規則本身）。

| 欄位 | 說明 |
|---|---|
| `orbit_A` / `orbit_B` | 太空船 A / B 的軌道六根數 (SMA, ECC, INC, RAAN, AOP, TA) |
| `rules.MAX_DV_MPS` / `MIN_MANEUVER_INTERVAL_SEC` / `T_MAX_PERIOD_MULTIPLE` | 規則規定的數字（規則第 2、3 節）：單次機動 Δv 上限 (m/s)、兩次機動間隔下限 (秒)、`T_max` 是 A 軌道週期的幾倍。預設值就是目前初賽規則的 1500 / 100 / 4，晉級賽如果規則數字不一樣，改這裡就好 |
| `rules.k_t` / `C_t` / `k_v` / `C_v` | 主辦方公告的計分參數（規則第 5 節），跟軌道分布狀況有關，每次比賽前會公告 |
| `strategy.USE_J2` | 不確定某一輪/場景有沒有 J2 擾動時用這個切換，Python 端跟產生的 GMAT script 會同步套用，不用改程式碼 |
| `strategy.MISS_TOLERANCE_KM` | 規則只要求 Δr ≤ 這個值 (預設對齊規則的 5km)，可以彈性調小 (甚至設 0 退回精準瞄準)，讓最後一棒 Lambert 在容許範圍內找最省油的落點，而不是死盯著 A 的精確位置 |
| `optimization.MAX_BURNS` | 要嘗試的燃燒次數列表，例如 `[1, 2, 3]` 會三種都跑，選分數最高的 |
| `optimization.MAXITER` / `POPSIZE` | 搜尋精細度。`POPSIZE` 是「每個決策變數維度分配幾個個體」(族群大小 = 維度數 × POPSIZE)，不是總數，越大越準但越久 |
| `optimization.NUM_THREADS` | 每個燃燒次數案例要用幾條執行緒平行評估族群；設 `-1` 或 0 以下會自動用「可用核心數 ÷ 燃燒次數案例數」估一個合理值 |
| `optimization.SEED` | 設一個整數可以讓同一組設定每次重現一模一樣的結果，方便比較「改了東西到底有沒有用」。**注意：設了 SEED 會自動退回單執行緒**（多執行緒下亂數搶用有 race condition，seed 保證不了重現性），犧牲速度換可重現性；不設 (`null`，預設) 就照樣用多執行緒換速度，兩者只能選一個 |

規則摘要（詳見 `rules/` 裡的正式規則文件）：單次機動 Δv ≤ 1500 m/s、兩次機動間隔 ≥ 100 秒、任務時間上限 T_max = 4×(A 的軌道週期)、相對距離 ≤ 5 km 視為攔截成功。這幾個數字現在都能在 config 裡調，程式不用改。

想在多份設定間切換（例如測試資料 vs. 正式測資）不用互相覆蓋，可以用 `--config` 指到不同的檔案（見下）。

---

## 步驟三：執行計算程式

```bash
uv run main.py
```

或是指定其他設定檔（預設是 `configs/config.json`）：

```bash
uv run main.py --config configs/my_scenario.json
```

執行完後會依序做三件事：

1. **Python 端高精度預覽**：終端機直接印出這組解的預估成績（用含 J2 的高精度模型算出來的真實 Δr_min / ΔV_team / T_team / 違規次數 / Score），不用等 GMAT 就能先判斷這組解值不值得。
2. **產出 GMAT 任務腳本**：寫到 `outputs/output.txt`。
3. **自動呼叫 GMAT 做無頭驗證**：透過 `GmatConsole --exit --run` 在背景直接把腳本跑一次（不會跳出 GMAT 視窗），讀回 GMAT 自己算出來的 `InterceptSuccess`/`MissDistance`/`T_team`，跟 Python 的預測印在一起對照。**整個流程一次跑完，不用手動開 GMAT。**

GMAT 相關參數：

```bash
uv run main.py --gmat-console "/path/to/GMAT R2026a/bin/GmatConsole"  # 換一台機器/重灌過時指定路徑
uv run main.py --no-gmat                                              # 只要 Python 端結果，跳過自動驗證
```

若沒裝 GMAT 或路徑不對，這步只會印警告，不會讓程式中斷；Python 算出來的結果跟 `output.txt` 照樣正常產出。

---

## 📂 資料夾讀寫說明

* **輸入資料：** 軌道參數與計分參數放在 `configs/config.json`（找不到會自動生成範例）。
* **GMAT 任務腳本：** 計算完成後，`outputs/output.txt` 永遠是最新一次的結果，可直接匯入 GMAT 執行；同樣的內容也會備份一份帶時間戳記的版本到 `outputs/history/`，避免之後的測試跑動不小心把先前的好結果蓋掉。
* **GMAT 攔截報表：** 預設會被 `main.py` 自動讀取並印出對照，不用手動找。原始檔案在 GMAT 安裝資料夾下的 `output/GMAT_InterceptReport.txt`（如果想自己手動在 GMAT 裡開 `output.txt` 執行也完全可以，看 `InterceptSuccess` 欄位：1 = 成功、0 = 失敗）。3D 視角 `View_Intercept` 會自動用紅/綠/灰區分 ShipA/ShipB/地球。
* **執行紀錄：** 每次執行都會把這次用的設定跟結果（時間戳、分數、ΔV、T_team、違規次數、GMAT 實際驗證結果…）附加一行 JSON 到 `outputs/run_history.jsonl`，方便之後比較不同設定/軌道跑出來的分數，以及 Python 預測跟 GMAT 實測差多少。

---

## ✅ 正式提交前

規則附則：「所有結果以主辦單位驗證程式為準；若結果無法重現，主辦單位得取消其成績。」`main.py` 現在每次執行都會自動跑 GMAT 驗證，**正式提交前還是建議再手動確認一次**：`outputs/output.txt` 對應的 `run_history.jsonl` 那筆記錄裡，`gmat_verified.intercept_success` 是 `true`、`targeter_converged` 是 `true`，且沒有任何一次燃燒超過 1500 m/s。

（補充：這份規則 PDF 裡沒有明確寫「繳交格式」是腳本還是別的，「所有結果以主辦單位驗證程式為準」比較像是主辦方會自己重新執行驗證，建議另外跟主辦方確認實際的繳交方式。）
