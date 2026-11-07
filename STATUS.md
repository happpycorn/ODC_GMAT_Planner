# 專案狀態

最後更新：2026-11-08

## 11-08 重瞄準改瞄 3.5 km 圈（軟凍結破例，使用者同意）

距離 ≤ 5 km 就拿滿 50 分，舊版重瞄準卻一律修到正中心，把求解刻意偏移瞄準省下的油吐回去。改成只修到
`strategy.RETARGET_AIM_KM`（預設 = 求解的 `MISS_TOLERANCE_SOFT` = 3.5 km）的圈上，原方案已在圈內就不改棒；設 0 回到舊版。
GMAT 實測：佔位題重瞄準 86.780719 → **86.784288**（+0.0036）、test_1107 74.876282 → 74.879110（+0.0028）。
取捨：模型跟官方對不上 1.5–5 km 時（曆元／太空船參數填錯，[MARGIN_SENSITIVITY](docs/research/MARGIN_SENSITIVITY_20261030.md) §3），
舊版還能攔到、新版不一定；所以 CONTEST_DAY 步驟 1 照題目填曆元與太空船參數更重要。
同時試了單棒餘裕 2 → 1 m/s：只多 0.00002–0.0005 分，預設不改。GUI 排位賽頁分數改顯示 6 位小數。
佔位題已知答案已更新（[ranking_placeholder_86.78](docs/solutions/ranking_placeholder_86.78/README.md)）。

注意：`odc/pipeline/stages.py`、`odc/config/validator.py` 在 mission.json 的版本檢查清單裡，**11-08 以前存的 mission.json 不能再拿去重瞄準**，要重新求解。

TASA／淡江大學「第一屆軌道設計競賽」的太空船攔截任務規劃工具；初賽第二名。下一場是 **2026-11-09 決賽的排位賽（10:45–11:45，60 分鐘）**，
目標前二進金牌賽（[策略](docs/final/FINAL_STRATEGY.md)）。全天流程看 [DAY_OVERVIEW](docs/final/DAY_OVERVIEW.md)，排位賽當天照 [CONTEST_DAY](docs/ranking/CONTEST_DAY.md) 做，賽前照 [PRE_CONTEST](docs/ranking/PRE_CONTEST.md)。

## 11-06 合併成單一 repo（11-07 已合回 Master）

11-07 用 fast-forward 合回 Master（b866951）並 push，`monorepo` 分支已刪。舊的 `~/Documents/Program/ODC_GMAT_DRL` 沒動、沒封存。
要回到合併前：兩個 repo 的本機 tag `pre-monorepo-20261106`（沒 push；ODC_Program 是 52723c4）。
同時清掉 GitHub 上已合併的舊 `codex/*`、`claude/*` 分支；有未合併 commit 的兩個留成 tag `archive/codex-e1-frequency`、`archive/codex-global-oracle`。

做了什麼：
- ODC_GMAT_DRL（main 6fe29bc）用 `git subtree add` 併進 `medal/`，保留歷史；仍是**獨立的 uv 專案**（自己的 `pyproject.toml`、`uv.lock`、`.venv`），不是 uv workspace。
  版本基準在 [ENV_BASELINE_20261106](docs/final/ENV_BASELINE_20261106.md)；合併後、以及 /tmp 新 clone 跑 `setup.sh` 後，兩邊 `uv pip freeze` 都跟基準逐行相同。
- GUI：金牌賽目錄改成 `ROOT/medal`（`ODC_DRL_DIR` 仍可覆寫）；GMAT 路徑改由 [gui/gmat_path.py](gui/gmat_path.py) 找
  （`configs/local/config.json` 的 `local.gmat_console_path` → `GMAT_CONSOLE` → 常見位置）；停止工作、隨身碟清單、顯示檔案加了 Windows／Linux 分支。
- 一鍵安裝 [setup.sh](setup.sh)（Mac／Linux）、[setup.ps1](setup.ps1)（Windows）、`gui/start.bat`；新電腦步驟在 [SETUP](docs/SETUP.md)。
- 手冊：DAY_OVERVIEW、gui/README、medal 的 CONTEST_DAY_FINAL／PRE_CONTEST_FINAL／README、QUESTIONS_FOR_ORGANIZER、FINAL_STRATEGY 改成 `medal/` 路徑；USB 備份改成一個 bundle。
- 求解程式、參數一行都沒改（`odc/`、`medal/` 的程式碼只動了一個 docstring）。

驗收（Mac，A/B 前 pin `OMP/OPENBLAS/MKL_NUM_THREADS=1`）：
- 排位賽：`odc.py test --quick -q` 24/24；pytest 89 passed、1 skipped（`test_split_stm.py` 直接執行也通過）。
- 佔位題 CLI：求解 **86.7847**（4 棒、639.35 m/s、T 19,972.99 s）、重瞄準 **86.7807** accepted、verify 通過，跟已知答案完全相同。求解 5 分 08 秒，比 11-03 的 136–158 s 慢。
- **速度沒有退步**（11-07 A/B，同一份佔位題、`--stop-after solve`、機器沒別的工作）：不 pin 153 s、pin BLAS 執行緒 195 s，兩次都是 86.7847。上面的 5 分 08 秒是 pin 加上完整流程（含 GMAT）的結果；SEED=null 時 pin 會慢約 27%，所以比賽當天不要設這三個變數（已寫進 CONTEST_DAY 步驟 5）。合併前的 Master 在 11-06 19:39 解同一題也花了 279 s（`outputs/runs/test-1`，沒 pin），當時多半有別的程式在搶 CPU，沒查證。
- 金牌賽：pytest 318 passed、17 skipped、1 failed（已知的 `test_rule_map::test_rule_ranges_sample_unchanged` 浮點假失敗）；`final_rehearsal --role evader --opponent capture_pursuer --fast` 6 回合、GMAT 結局 escape，advise 最長 3.3 s。
- GUI（`ODC_DAY_DIR` 指到暫存）：排位賽從建設定檔點到步驟 7（求解 86.7847、重瞄準 86.7807、清單全過、存檔到本機 `outputs/ODC_Final`）；
  金牌賽填規則→放狀態檔→解析→角色選擇器 `--fast`（34.7 s，建議躲方）→建 session→6 回合 advise／announce，每回合提交行跟 CLI 彩排逐字相同；停止按鈕實測 2 秒內停下、沒留子行程。
- /tmp 新 clone `monorepo` 跑 `./setup.sh --yes`：7 項全 ✓，4 分 54 秒（uv 快取是熱的；真正的新電腦要多下載約 2 GB）。

沒做或沒驗到：
- **Windows 完全沒實機跑過**：`setup.ps1`、`start.bat` 沒執行過（Mac 上沒有 PowerShell）；GUI 的 Windows 分支只用假環境測過 venv 路徑、Ctrl+Break 停止、可移除磁碟、`explorer /select`。Linux 隨身碟與 `xdg-open` 也只用假環境測。
- `setup.sh` 的「找不到 GMAT 就問一次」互動分支沒實際輸入過（測了 `--yes` 與不存在的 `--gmat`）。
- 隨身碟存檔只測了「存在本機」，沒有寫進真的隨身碟；「打開所在資料夾」沒按（Mac 分支跟原本一樣是 `open -R`）。
- `odc/config/defaults.py` 的 GMAT 最後備援值仍是這台 Mac 的路徑（凍結期不動程式）；別台電腦靠 setup 寫進 `config.json`、`new-config --gmat-console` 解決。
- 舊的 `docs/research`、`medal/docs/notes`、`medal/reports` 等歷史紀錄裡的舊路徑沒改。
- `configs/local/test_1.json` 和 `outputs/runs/test-1*`（11-06 19:44，比這次合併早）不是這次產生的，沒有刪；當天開賽前要照 DAY_OVERVIEW 清掉。
- Mac 的 `medal/.venv` 已建好；比賽前照 PRE_CONTEST／PRE_CONTEST_FINAL 在新的 Master 上再彩排一次（numba 快取會重新編譯）。
- WSL（Corn）11-07 從新 clone 跑 `setup.sh` 7 項全 ✓、金牌賽完整 pytest 336 過；`setup.sh` 改成指定 Python 3.12.12 後，舊的 3.12.3 venv 會就地重建。

## 目前狀態

- **11-04 起軟凍結**：不加功能、不改演算法；只換官方參數、修彩排抓到的 bug、更新手冊。Mac 上 pytest 90 項全過，`tests/test_split_stm.py` 要直接執行（`uv run python tests/test_split_stm.py`，用 pytest 跑會報 fixture error）。
- **比賽設定**是 [ranking_round.json](configs/shared/ranking_round.json)：單棒 250 m/s、總 Δv 3,000 m/s、機動間隔 100 s；J2–J4、命中容差 5 km，
  開 `SPLIT_LEADING` 與 `ORACLE_TWOBURN`；搜尋 `MAX_BURNS=[1,2]`、`MAXITER=1000`、`POPSIZE=20`、`SEED=null`。
  A/B 軌道、`T_MAX_SEC`、`k_t/C_t/k_v/C_v` 是佔位值，開賽時換成官方題目。
- **當天流程**（10-30 重寫）：單一行程用滿核心求解 → 全攝動 B 平面重瞄準 → GMAT 重驗 → 失格清單 → 11:20 前存保底、11:25 開始繳交。
  Mac 實測求解：排位賽設定 136–158 s（3 次同分 86.7847）、其他情境 82–215 s（[11-03 夜跑](docs/research/MAC_TIMING_20261103.md)，`--stop-after solve`）；不含 GMAT 驗證，跟 10-30 含驗證的 2.5–5 分鐘不能直接比、重瞄準加驗證 < 20 秒（[實測紀錄](docs/ranking/PRE_CONTEST.md#實測紀錄)）。以前的 3 顆固定種子並行已不用：oracle 開了之後各種子同分，並行只會互搶核心。
- **程式結構**（10-30 全面重構，commit `209953c`，重構前 tag `pre-refactor`）：入口只剩 `odc.py`，程式在 `odc/`，
  設定分 `configs/shared/`（版控）與 `configs/local/`（本機）。重構前後 11 個案例逐位元相同、回歸 31/31（[驗收報告](docs/archive/refactor_20261030/REFACTOR_REPORT.md)）。
- **文件**（10-30 重寫）：README、CONTEST_DAY、規則摘要的工具對應、METHODOLOGY 與其他現行文件的舊路徑已改成重構後的指令。

主要功能與依據：排位賽失格層與結束碼 3（[懲罰 v2](docs/research/RANKING_PENALTY_V2_20261019.md)）；拆棒 STM、多起點、剔空棒、600 s 預算
（[拆棒加速](docs/research/SPLITTER_SPEED_20261020.md)）；全攝動重瞄準（[攝動落差](docs/research/PERTURBATION_GAP_20261019.md)）；
星曆快取（[報告](docs/research/EPHEM_CACHE_20261028.md)）；前導棒拆分＋兩棒 oracle（[階段 2](docs/research/ORACLE_PHASE2_20261029.md)）。
完整紀錄在 [DEVLOG_ranking](docs/log/DEVLOG_ranking.md)。

## 接下來

依 [FINAL_STRATEGY 時程](docs/final/FINAL_STRATEGY.md#時程)：

| 日期 | 內容 |
|---|---|
| 盡快 | **寄出主辦提問**（[草稿](docs/ranking/QUESTIONS_FOR_ORGANIZER.md)；寄出後記在該檔最後一節） |
| 11/04–11/05 | 量 GMAT 段（export／retarget／verify）時間，補齊 60 分鐘預算；P4 彩排 #1 |
| 11/06–11/07 | P4 彩排 #2（拔網路、電池各一次），實測時間填回 [PRE_CONTEST](docs/ranking/PRE_CONTEST.md#實測紀錄) |
| 11/08 | 硬凍結，重看 TASA 頁的規則修訂 |

## 已知問題

- **曆元與太空船參數要照官方填**：填錯時重瞄準後的解在 GMAT 偏 0.5–161 km（[敏感度實測](docs/research/MARGIN_SENSITIVITY_20261030.md)）；官方驗證會不會沿用我們腳本裡的參數也還不知道。
- **繳交（步驟 8）沒有計時過**，主辦機能不能交整份自製 Script 也不知道（[問題 12–14](docs/ranking/QUESTIONS_FOR_ORGANIZER.md)）。
- 太空船質量、Cd/Cr、面積、SPADFile、曆元還是佔位值；重瞄準時 A 用跟 B 同一個力學模型（規則說 A 只受重力，研究量到差 ≤ 0.6 km）。
- primer 加棒重搜（`PRIMER_GUIDED_RESEARCH`）沒有時間上限，觸發時多一整輪搜尋；當天靠手冊的保底設定處理。fast 模式有 300 s 上限，但救分案例少 0.51 分（[primer 對照](docs/research/PRIMER_FAST_V1_20261028.md)）。
- [階段 2 未驗證項目](docs/research/ORACLE_PHASE2_20261029.md#5-沒驗證到的地方)：oracle 逾時清理只經單元測試；`SPLIT_LEADING=false` 時 primer 重搜的搜尋／重播不同尺。
- [全域對照](docs/research/GLOBAL_ORACLE_20261028.md#hyper_far-的拆棒盲點)的長滑行終端路線、[E1](docs/research/E1_FREQUENCY_20261029.md#限制) 的 e1_r7 拆棒失敗原因仍未查明。
- 求解時「最大單棒超標 N 倍」的警告文字還寫「見 feasibility.py」，應為 `odc.py feasibility`；改它會讓既有 `mission.json` 的版本雜湊失效，留到賽後。

## 環境（本機、不進 git）

- 開發機是 Mac；GMAT R2026a 在 `/Users/corn/Documents/GMAT R2026a/bin/GmatConsole`，用 `odc.py new-config <名稱> --gmat-console <路徑>` 寫進本機設定。
- `configs/local/` 與 `outputs/` 被 gitignore。共用情境在 `configs/shared/`；本機設定遺失時照 [SCENARIOS.md](docs/SCENARIOS.md) 重建。
  11-04 清場：兩個 repo 的舊產物與舊本機設定搬到 `~/Documents/Program/ODC_archive_pre1109/`（只搬不刪，說明在該資料夾 README）。
- 另一台開發機 Corn（Ryzen 7 5800X、WSL2）負責長批次；兩邊透過 `Master` 同步，在 Mac 動手前先 `git pull`。WSL 上的 GMAT 修補記在 DEVLOG_prelim 末段。

## 文件入口

- [README](README.md)：安裝、設定、指令與輸出。
- [docs/README](docs/README.md)：比賽當天、現行參考、研究與封存導覽。
