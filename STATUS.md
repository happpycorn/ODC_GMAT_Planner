# 專案狀態

最後更新：2026-10-30

TASA／淡江大學「第一屆軌道設計競賽」的太空船攔截任務規劃工具；初賽已獲第二名（[準備期紀錄](docs/log/DEVLOG_ranking.md)）。

## 目前狀態

- **比賽設定**以 [ranking_round.json](configs/shared/ranking_round.json) 為準：單棒上限 250 m/s、總 Δv 上限 3,000 m/s、機動間隔 100 s；重力階數 4、命中容差 5 km，開啟 `SPLIT_LEADING` 與 `ORACLE_TWOBURN`。
- 該範本的 A/B 軌道、`T_MAX_SEC`、`k_t/C_t/k_v/C_v` 仍是佔位值，須在開賽時整組換成官方題目；搜尋設定為 `MAX_BURNS=[1,2]`、`MAXITER=1000`、`POPSIZE=20`、`NUM_THREADS=-1`、`SEED=null`。並行種子須各設不同 SEED（同上設定檔註解）。
- **共用拆棒預設**見 [split_defaults.py](odc/config/split_defaults.py)：STM Jacobian、三起點 `[0,0.75,1]`、1 m/s 剔空棒重最佳化、600 s 牆鐘預算、3 行程。

2026-09-29 之後完成的主要功能（依 Git 紀錄與報告）：

- REVS 案例已共用行程池；提早停止已接通，但消融顯示掉分，預設維持關閉（[REVS 排程](docs/research/REVS_SCHEDULING_20260929.md)、[提早停止消融](docs/research/EARLY_STOP_ABLATION_20260929.md)）。
- 排位賽硬性限制與搜尋「失格層」已接通；找不到合法路線時保存 `no_legal_route.json` 並以結束碼 3 結束（[搜尋懲罰 v2](docs/research/RANKING_PENALTY_V2_20261019.md)）。
- T_max 計算、計分單位驗算工具及當天手冊已就緒；全攝動 B 平面重瞄準已接進正式管線（[決賽策略](docs/final/FINAL_STRATEGY.md#判斷)、[攝動落差](docs/research/PERTURBATION_GAP_20261019.md)）。
- 拆棒加速、多起點、剔空棒重最佳化與牆鐘預算已實作；後續加入 STM Jacobian 與固定軌道星曆快取（[拆棒加速](docs/research/SPLITTER_SPEED_20261020.md)、[星曆快取](docs/research/EPHEM_CACHE_20261028.md)；Git `dfc2b0a`、`1277cf0`）。
- 撞地球判定已補驗證腳本半徑關卡、雙曲線真近地點與第一棒前等待弧（Git `d97ca92`）；primer 快速重搜與搜尋滑行容差旋鈕已加入，預設仍維持 full／`1e-12`（[primer 對照](docs/research/PRIMER_FAST_V1_20261028.md)；Git `72e63a6`）。
- 前導棒拆分、兩棒 oracle 附加候選與 SEARCH／LEADING 同開時計分修正已整合；排位賽範本已採四臂比較建議的 C 臂，並納入 e1_r4/r5/r8 共用情境（[階段 2](docs/research/ORACLE_PHASE2_20261029.md)、[計分修正](docs/research/SPLIT_AWARE_SEARCH_FIX_20261029.md)；Git `402faff`）。

## 比賽前時程

依 [FINAL_STRATEGY 時程表](docs/final/FINAL_STRATEGY.md#時程)：10/29–10/30 寫入 60 分鐘時間盒並開始 Mac 實測；10/31–11/02 完成機器實測與盲測題計時；11/03–11/07 彩排兩次並修手冊；11/08 凍結程式碼、重看官方規則；11/09 比賽，排位賽 10:45–11:45。

## 已知問題與還沒做的事

- [FINAL_STRATEGY 待辦](docs/final/FINAL_STRATEGY.md#待辦依優先序)：主辦提問、60 分鐘流程與保底設定、當天機器及低預算實測、盲測與三人彩排；官方參數回覆後須替換預設並重驗。金／銅牌賽細則公布前不再投入。
- [階段 2 未驗證項目](docs/research/ORACLE_PHASE2_20261029.md#5-沒驗證到的地方)：Mac C 臂只量過 hyper_far 一個 run；其餘題牆鐘與現場核心分配未量。oracle 逾時清理只經單元測試，重瞄準＋GMAT 只驗每題每臂最佳 run。
- 同報告記錄：`SPLIT_LEADING=false` 時 primer 重搜的搜尋／重播仍不同尺；smoke 的終端／前導拆棒預付估分會排反，其他題未驗證、未調參；B 臂跨機器非確定性尚未在修正後重測。
- [primer 快速模式](docs/research/PRIMER_FAST_V1_20261028.md) 在已找到的救分案例比 full 少 0.51 分；[全域對照](docs/research/GLOBAL_ORACLE_20261028.md#hyper_far-的拆棒盲點) 的長滑行終端路線、[E1](docs/research/E1_FREQUENCY_20261029.md#限制) 的 e1_r7 拆棒失敗原因仍未查明。

## 環境（本機、不進 git）

- **目前開發機：Mac（Darwin）。** GMAT R2026a 在 `/Users/corn/Documents/GMAT R2026a/bin/GmatConsole`
  （已存在，寫進各 `configs/local/*.json` 的 `local.gmat_console_path`，或帶 `--gmat-console`）。
- `configs/` 整個被 gitignore、換機器不會帶過來。**設定檔的完整重建參數記在 [SCENARIOS.md](docs/SCENARIOS.md)**
  （configs/ 遺失就靠這份重建）。
- 2026-08-15 曾在 WSL2+Ryzen 上開發，那套 GMAT-on-WSL 修補若日後回 WSL 用得上，記在 DEVLOG_prelim.md 末段。

## 文件入口

- [README](README.md)：安裝、設定、執行與輸出。
- [docs/README](docs/README.md)：比賽當天、現行參考、研究與封存導覽。
- [docs/log/](docs/log/)：初賽與排位賽準備期的完整開發紀錄。
