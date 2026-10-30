# 專案狀態

最後更新：2026-10-30

TASA／淡江大學「第一屆軌道設計競賽」的太空船攔截任務規劃工具；初賽第二名。下一場是 **2026-11-09 決賽的排位賽（10:45–11:45，60 分鐘）**，
目標前二進金牌賽（[策略](docs/final/FINAL_STRATEGY.md)）。當天照 [CONTEST_DAY](docs/ranking/CONTEST_DAY.md) 做。

## 目前狀態

- **比賽設定**是 [ranking_round.json](configs/shared/ranking_round.json)：單棒 250 m/s、總 Δv 3,000 m/s、機動間隔 100 s；J2–J4、命中容差 5 km，
  開 `SPLIT_LEADING` 與 `ORACLE_TWOBURN`；搜尋 `MAX_BURNS=[1,2]`、`MAXITER=1000`、`POPSIZE=20`、`SEED=null`。
  A/B 軌道、`T_MAX_SEC`、`k_t/C_t/k_v/C_v` 是佔位值，開賽時換成官方題目。
- **當天流程**（10-30 重寫）：單一行程用滿核心求解 → 全攝動 B 平面重瞄準 → GMAT 重驗 → 失格清單 → 11:20 前存保底、11:25 開始繳交。
  Mac 實測三題求解 2.5–5 分鐘、重瞄準加驗證 < 20 秒（[附錄 A](docs/ranking/CONTEST_DAY.md#附錄-a實測紀錄)）。以前的 3 顆固定種子並行已不用：oracle 開了之後各種子同分，並行只會互搶核心。
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
| 盡快 | **寄出主辦提問**（[草稿](docs/ranking/QUESTIONS_FOR_ORGANIZER.md)，寄出紀錄仍是空的） |
| 10/31–11/02 | 盲測題計時（含人工步驟）；Mac 量保底設定 |
| 11/03–11/07 | 照 CONTEST_DAY 三人彩排兩次，含主辦機繳交；實測時間填回附錄 A |
| 11/08 | 凍結程式碼，重看 TASA 頁的規則修訂 |

## 已知問題

- **繳交（步驟 8）沒有計時過**，主辦機能不能交整份自製 Script 也不知道（[問題 12–14](docs/ranking/QUESTIONS_FOR_ORGANIZER.md)）。
- 太空船質量、Cd/Cr、面積、SPADFile、曆元還是佔位值；重瞄準時 A 用跟 B 同一個力學模型（規則說 A 只受重力，研究量到差 ≤ 0.6 km）。
- primer 加棒重搜（`PRIMER_GUIDED_RESEARCH`）沒有時間上限，觸發時多一整輪搜尋；當天靠手冊的保底設定處理。fast 模式有 300 s 上限，但救分案例少 0.51 分（[primer 對照](docs/research/PRIMER_FAST_V1_20261028.md)）。
- [階段 2 未驗證項目](docs/research/ORACLE_PHASE2_20261029.md#5-沒驗證到的地方)：oracle 逾時清理只經單元測試；`SPLIT_LEADING=false` 時 primer 重搜的搜尋／重播不同尺。
- [全域對照](docs/research/GLOBAL_ORACLE_20261028.md#hyper_far-的拆棒盲點)的長滑行終端路線、[E1](docs/research/E1_FREQUENCY_20261029.md#限制) 的 e1_r7 拆棒失敗原因仍未查明。
- 求解時「最大單棒超標 N 倍」的警告文字還寫「見 feasibility.py」，應為 `odc.py feasibility`；改它會讓既有 `mission.json` 的版本雜湊失效，留到賽後。

## 環境（本機、不進 git）

- 開發機是 Mac；GMAT R2026a 在 `/Users/corn/Documents/GMAT R2026a/bin/GmatConsole`，用 `odc.py new-config <名稱> --gmat-console <路徑>` 寫進本機設定。
- `configs/local/` 與 `outputs/` 被 gitignore。共用情境在 `configs/shared/`；本機設定遺失時照 [SCENARIOS.md](docs/SCENARIOS.md) 重建。
- 另一台開發機 Corn（Ryzen 7 5800X、WSL2）負責長批次；兩邊透過 `Master` 同步，在 Mac 動手前先 `git pull`。WSL 上的 GMAT 修補記在 DEVLOG_prelim 末段。

## 文件入口

- [README](README.md)：安裝、設定、指令與輸出。
- [docs/README](docs/README.md)：比賽當天、現行參考、研究與封存導覽。
