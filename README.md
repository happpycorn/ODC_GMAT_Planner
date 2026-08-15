# 🚀 軌道攔截設計賽 - 任務規劃工具 (Rocket Trajectory Calculator)

本程式用於「軌道攔截設計賽」初賽：讓太空船 B（地球）以多次瞬時脈衝機動，在時間限制內攔截太空船 A（外星人，被動、只受重力影響），同時兼顧燃料消耗與任務效率。底層採用多核心 (Multiprocessing + Threading) 與 JIT (Numba) 技術加速運算，並用 L-SHADE 全域搜尋 + L-BFGS-B 局部微調找解，最後產出可直接匯入 GMAT 的任務腳本。

為了確保最佳的執行效能與最簡便的安裝體驗，本專案使用新一代極速套件管理工具 `uv`，不需要手動設定虛擬環境。

**這份文件只講怎麼用（安裝/設定/執行/看輸出）。想知道分數/燃燒方案背後是怎麼算出來的（物理模型、Lambert 攔截設計、最佳化演算法、GMAT 驗證流程…），看 [METHODOLOGY.md](METHODOLOGY.md)。**

---

## ⚠️ 系統環境需求

本專案需要 **Python 3.12 或以上版本**（`pyproject.toml` 寫死 `requires-python = ">=3.12"`）。不用自己先裝好——下面的 `uv` 工具會自動抓一份對的版本回來，不會跟你電腦上其他專案用的 Python 打架。

---

## 步驟一：安裝 `uv` 工具

請打開終端機 (Mac) 或 命令提示字元/PowerShell (Windows)，輸入以下指令：

```bash
pip install uv
```

### 每次 `git pull` 之後：跑一次 `uv sync`

```bash
uv sync
```

`uv run` 平常會自動補齊缺少的套件，但**不會清掉已經不需要的舊套件**。如果別人改過
`pyproject.toml`/`uv.lock`（例如移除某個依賴），你的環境會留著殘骸，而殘骸會掩蓋
問題——這個專案至少踩過兩次：一次是 `tqdm` 從來沒被列進依賴、靠殘留的舊環境活著，
換到全新機器就 `ModuleNotFoundError`；一次是清掉 `torch` 之後本機還留著整套 CUDA
套件，1GB 的東西白佔空間。

`uv sync` 會讓環境**精確等於** lockfile，多的砍掉、缺的補上。養成 pull 完跑一次的
習慣，就不會遇到「在我這台好好的」這種問題。

---

## 步驟二：設定 `configs/config.json`

程式第一次執行時，如果找不到設定檔會自動生成一份預設範例，但**正式提交前務必手動確認以下欄位是主辦方公布的正式數字**，不是範例值：

config 分四大塊 + 一塊選填，各自對應「誰決定這個數字」：`orbit_A`/`orbit_B`（軌道六根數）、`rules`（主辦方規定/公告的數字，我們不能改）、`strategy`（我們自己的任務設計選項，不是規則要求）、`optimization`（純演算法搜尋設定，只影響找不找得到好解/要跑多久，不影響規則本身）、`local`（選填，跟任務/規則完全無關的「這台機器」設定，見下）。

| 欄位 | 說明 |
|---|---|
| `orbit_A` / `orbit_B` | 太空船 A / B 的軌道六根數 (SMA, ECC, INC, RAAN, AOP, TA) |
| `rules.MAX_DV_MPS` / `MIN_MANEUVER_INTERVAL_SEC` / `T_MAX_PERIOD_MULTIPLE` | 規則規定的數字（規則第 2、3 節）：單次機動 Δv 上限 (m/s)、兩次機動間隔下限 (秒)、`T_max` 是 A 軌道週期的幾倍。預設值就是目前初賽規則的 1500 / 100 / 4，晉級賽如果規則數字不一樣，改這裡就好 |
| `rules.k_t` / `C_t` / `k_v` / `C_v` | 主辦方公告的計分參數（規則第 5 節），跟軌道分布狀況有關，每次比賽前會公告 |
| `strategy.GRAVITY_DEGREE` | 重力場要算到第幾階 zonal harmonic：`0`=純點質量、`2`=J2、`3`=J2+J3、`4`=J2+J3+J4。Python 端跟產生的 GMAT script 會同步套用，不用改程式碼。**建議用 `4`**——實測最準；設 `0` 雖然讓兩邊模型一致，但等於兩邊都在算不真實的物理，比賽當天主辦方環境若有開擾動就會對不上 |
| `strategy.MISS_TOLERANCE_KM` | 規則只要求 Δr ≤ 這個值 (預設對齊規則的 5km)，可以彈性調小 (甚至設 0 退回精準瞄準)，讓最後一棒 Lambert 在容許範圍內找最省油的落點，而不是死盯著 A 的精確位置 |
| `optimization.MAX_BURNS` | 要嘗試的燃燒次數列表，例如 `[1, 2, 3]` 會三種都跑，選分數最高的 |
| `optimization.MAXITER` / `POPSIZE` | 搜尋精細度。`POPSIZE` 是「每個決策變數維度分配幾個個體」(族群大小 = 維度數 × POPSIZE)，不是總數，越大越準但越久 |
| `local.gmat_console_path`（選填） | 這台機器上 `GmatConsole` 的路徑。不填就用 `--gmat-console` 參數，或 `main.py` 裡寫死的最後備援值（那是我這台機器的路徑，換一台機器大概率對不上）。優先順序：`--gmat-console` > 這個欄位 > 寫死的備援值。config.json 本來就被 `.gitignore` 排除，填在這裡不會跟著 git 到處跑，換電腦/換人開發各自維護自己的這一項就好，不用每次執行都手動打 `--gmat-console` |
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

## 拿到一個新情境時的建議順序

```
新測資 → feasibility.py → (範圍很寬才需要 sweep_burns.py) → main.py → 檢查 run_history
```

**前面兩步都可以跳過**——`main.py` 已經內建了最關鍵的檢查（見下），直接跑不會出事。

### 1. `feasibility.py`：先問「這題有沒有解」

```bash
uv run feasibility.py --config configs/x.json           # 快，只做前兩層
uv run feasibility.py --config configs/x.json --burns 3 # 加做 3 棒可行性 (較慢)
```

回答三件事：**能量下限（至少要幾棒）**、**合法單棒解存不存在**、**有多稀有**。

存在的理由很實際：搜尋跑完沒找到合法解時，**分不清是「工具不夠力」還是「這題本來
就無解」**——沒有這個答案，結果完全沒辦法解讀。

輸出怎麼看：

| 情況 | 建議 |
|---|---|
| 能量下限 = 0、合法解常見（>1%） | 直接 `main.py`，`MAX_BURNS` 用 `[1]` 或 `[1,2]` |
| 能量下限 > 每棒上限 | `MAX_BURNS` 從下限起跳，別放更小的（注定違規） |
| 合法解極稀有（<0.05%） | 窄窗地形，用正式預算別省，靠種子機制找 |

### 2. `sweep_burns.py`：燃燒次數範圍很寬時才划算

```bash
uv run sweep_burns.py --config configs/x.json --burns 2-8
```

先用調低的 `MAXITER` 粗掃一個寬範圍，找出分數大概從哪裡開始不再明顯進步，再針對
那附近用 config 原本的 `MAXITER` 重跑一次「公平」的精細驗證。常用參數：`--burns 1-8`、
`--coarse-iters 300`、`--output-config x.json`（把建議寫成新的 config 檔）。

**範圍在 3~4 個以內就跳過這步**——`main.py` 本來就會平行跑所有燃燒次數並自動挑
贏家，再多一層 sweep 只是浪費時間。它真正划算的場合是 `MAX_BURNS` 有十幾個值的時候。

**這是效率工具，不是最終判定**：工具的結論是「分數打平」，但規則的平手判定看的是
`Δr_min`/`ΔV_team`/`T_team` 這些原始數字，正式方案還是要回頭核對細節。

### `main.py` 已經內建的檢查（所以前面兩步可以跳過）

* **開跑前**：如果 `MAX_BURNS` 裡有「能量上不可能合法」的燃燒次數，會直接警告並建議
  拿掉（能量下限是封閉解，算一次不到微秒，所以無條件做，不影響速度）。
* **印任務規劃時**：如果贏家其實是「中間棒 Δv≈0 的空燒」，會明講「這是 N 棒的方案但
  實際只用到 M 棒」——多棒解退化成單棒很常見，光看棒數會誤以為用了多棒策略。

### 現成的測試情境

`configs/` 被 `.gitignore` 排除，所以情境不會跟著 git 走。**所有測試情境的完整參數
（六根數 + 規則參數 + 實測難度）記錄在 [SCENARIOS.md](SCENARIOS.md)**，照著貼就能重建。
換機器、或不小心刪掉時去那裡找。

---

## 📂 資料夾讀寫說明

* **輸入資料：** 軌道參數與計分參數放在 `configs/config.json`（找不到會自動生成範例）。
* **GMAT 任務腳本（兩份）：**
  * `outputs/output.txt`：一般版本，最後一棒靠 GMAT 自己的 `DifferentialCorrector`（`Target/Vary/Achieve`）收斂命中瞄準點，用來找出正確答案。
  * `outputs/output_submit.txt`：**建議拿去正式繳交的版本**。一般版本驗證通過後會自動產生，把 GMAT 剛剛收斂出來的燃燒值直接寫死，整份腳本不含任何求解器——單純傳播＋施加燃燒，換一台電腦（例如比賽當天主辦單位準備的電腦）執行，不用擔心求解器的收斂行為跟我們這邊不一樣，因為根本沒有求解器在跑。想跳過這一步（省幾秒）可以加 `--no-fixed-script`。
  * 兩份都會各自備份一份帶時間戳記的版本到 `outputs/history/`，避免之後的測試跑動不小心把先前的好結果蓋掉。
* **GMAT 攔截報表：** 預設會被 `main.py` 自動讀取並印出對照，不用手動找。原始檔案在 GMAT 安裝資料夾下的 `output/GMAT_InterceptReport.txt`（如果想自己手動在 GMAT 裡開 `output.txt`/`output_submit.txt` 執行也完全可以，看 `InterceptSuccess` 欄位：1 = 成功、0 = 失敗）。3D 視角 `View_Intercept` 會自動用紅/綠/灰區分 ShipA/ShipB/地球。
* **執行紀錄：** 每次執行都會把這次用的設定跟結果（時間戳、分數、ΔV、T_team、違規次數、兩份腳本各自的 GMAT 實際驗證結果…）附加一行 JSON 到 `outputs/run_history.jsonl`，方便之後比較不同設定/軌道跑出來的分數，以及 Python 預測跟 GMAT 實測差多少。

---

## 🖥️ 部署到一台全新電腦

分兩種情況，需要的東西差很多：

### A. 要在新電腦上跑整套設計工具（例如隊友的筆電）

1. **裝 `uv`**：`pip install uv`（Windows 用命令提示字元/PowerShell，Mac/Linux 用終端機）。
2. **拿到程式碼**：`git clone https://github.com/happpycorn/ODC_GMAT_Planner.git`，或直接把整個資料夾複製過去。
3. **`configs/` 資料夾要另外處理**：這個資料夾整個被 `.gitignore` 排除（避免測試用的軌道數字不小心被當成正式資料 commit 上去），`git clone` 下來 `configs/` 會是空的。兩個選項：
   - 直接跑 `uv run main.py`，找不到設定檔會自動生成一份範例（`orbit_A`/`orbit_B` 都是佔位數字，記得換成真的資料）。
   - 或者手動把原本電腦上 `configs/*.json` 複製過去（USB / 雲端硬碟 / email 都行，就是幾個文字檔）。
4. **第一次執行會比較慢**：`uv run main.py` 第一次跑，`uv` 會自動下載對應版本的 Python（3.12+）跟所有套件（`numpy`/`numba`/`scipy`/`astropy`/`poliastro`/`mealpy` 等，現在裝起來大約 1GB 左右——早期版本不小心留了 `torch`/`optuna`/`pymoo` 這些完全沒用到的重量級依賴，已經清掉了，不然會大好幾倍），**這一步需要網路**。之後每次執行都是用裝好的環境，不會重新下載。
5. **GMAT 是完全獨立的一套軟體，`uv` 不會幫你裝**：這台新電腦要另外安裝 GMAT，然後用 `--gmat-console` 指到正確路徑：
   ```bash
   uv run main.py --gmat-console "C:\Program Files\GMAT\bin\GmatConsole.exe"   # Windows 範例路徑
   uv run main.py --gmat-console "/path/to/GMAT/bin/GmatConsole"               # Mac/Linux 範例路徑
   ```
   （`main.py` 裡寫死的預設路徑是我這台機器的路徑，新電腦上一定對不上，一定要用這個參數蓋掉，不然只會印警告然後跳過 GMAT 驗證。）
6. **建議先拿一個小情境（例如 `configs/practice_scenario.json`）跑一次 `--no-gmat` 版本，確認 Python 端能跑，再測 GMAT 那段**，不要直接拿正式資料在新電腦上測試新環境。

### B. 比賽當天，主辦單位準備的電腦

**不需要部署上面這整套東西。** 規則寫明「太空船的指令下達與模擬，需使用主辦/承辦單位所準備的電腦」，但正式要拿去執行的 `outputs/output_submit.txt` 本身就是一份**純文字的 GMAT script**，不含任何求解器（見上面「固定燃燒版本」的說明）——只要那台電腦上有裝 GMAT（官方應該會確保這件事，畢竟整場比賽都靠 GMAT 跑），直接把這個檔案帶過去（USB/email 都行），在 GMAT 裡開檔執行就好，完全不需要 Python、`uv`、或這個 repo 的任何程式碼。

真正需要在自己電腦上（賽前「先期模擬與運算」）跑的是這整套工具，用來**找出**這份 script；比賽現場要交出去的只是**結果**。兩件事分開想，能大幅降低「主辦單位電腦環境跟我們不一樣」的風險——順便也是這個 session 加「固定燃燒版本」的動機。

---

## ✅ 正式提交前

規則附則：「所有結果以主辦單位驗證程式為準；若結果無法重現，主辦單位得取消其成績。」`main.py` 現在每次執行都會自動跑 GMAT 驗證，**正式提交前還是建議再手動確認一次**：`run_history.jsonl` 最新那筆記錄裡：

1. `gmat_verified.intercept_success`、`targeter_converged` 都是 `true`，且沒有任何一次燃燒超過 1500 m/s（一般版本，`outputs/output.txt`，用來確認算出來的方案本身沒問題）。
2. `fixed_script_verified.intercept_success`、`final_burn_legal` 都是 `true`（固定燃燒版本，`outputs/output_submit.txt`，**這份才是建議繳交的檔案**，不含任何求解器，換電腦跑結果會更穩定）。

如果沒有 `fixed_script_verified` 這個欄位，代表一般版本沒有通過驗證（或是有加 `--no-fixed-script`），先確認一般版本乾淨過了，再重跑一次讓固定版本產生出來。

（補充：這份規則 PDF 裡沒有明確寫「繳交格式」是腳本還是別的，「所有結果以主辦單位驗證程式為準」比較像是主辦方會自己重新執行驗證，建議另外跟主辦方確認實際的繳交方式。）
