# 專案狀態筆記（交接用）

給下一個 session（不管是我自己回來還是你自己看）快速抓回上下文用的：「現在做到哪、還缺什麼、為什麼」。
**怎麼用這個工具看 [README.md](README.md)；演算法/物理模型原理看 [METHODOLOGY.md](docs/METHODOLOGY.md)**；
初賽的逐日開發日誌封存在 [docs/log/DEVLOG_prelim.md](docs/log/DEVLOG_prelim.md)；更細的技術決策看 commit log 跟程式碼註解。

**最後更新：2026-09-11——初賽已結束；HAP-67 拆棒管線上線（違規解自動合法化，見下）。**

## 這是什麼

TASA／淡江大學辦的「第一屆軌道設計競賽」的任務規劃工具。太空船 B（我方，機動）要在時間／燃料限制下攔截
太空船 A。`rules/` 有官方文件（正式規則 PDF ×2、0510 說明會簡報、參賽選手注意事項）。

- **初賽**：A 是圓軌道、被動（只受重力），單純攔截。**已結束。**
- **下一輪（排位賽起）**：官方簡報說是**完全不同玩法**——A 變雙曲線、即時追逐戰。工具的雙曲線輸入端
  防禦大多已就位，但**從未端到端實跑過**（見下面風險 P3）。玩法／計分細節要等官方發題才知道。

規則要點（初賽）：Δv ≤ 1500 m/s/次、機動間隔 ≥100s、T_max=4×A 週期、**Δr ≤ 5km 即算成功且以內同分**
（這點很關鍵，計分對命中位置是平的，決定策略）、繳交「Script + 至少模擬一次的 Report」。

## 🏁 初賽結果（2026-09-05）

**第二名。** 我們官方繳交 `docs/solutions/98.32_champion_team19.md` 那份（GMAT DC 驗證 98.31、零違規、
Earth-safe 的五棒解）。第一名 Team15 以 98.3162 奪冠；兩隊因撞地球失格。

事後補記（不影響已定結果）：2026-09-09 用 HAP-47 的 joint NLP 拆分器對同一組解重新聯合優化、GMAT 驗證後
得 98.3177，理論上會以 0.0015 分之差贏過 Team15——但初賽已結束、無法追溯提交，價值在下一輪。
細節見 [HAP47_SPLIT_ALGORITHM_RESEARCH.md](docs/HAP47_SPLIT_ALGORITHM_RESEARCH.md) §7.1。

初賽的解與教訓都封存在 [docs/solutions/](docs/solutions/)（各解 SUMMARY、冠軍繳交件、重力模型 bug 與
撞地球教訓）。初賽當天手冊／站別卡在 [docs/prelim/](docs/prelim/)。

## 下一輪準備：現況與待辦

**已就位、可跨輪沿用：**
- 力學引擎：DOP853 積分器（`rtol=1e-12, atol=1e-9`）、可設定重力場 `GRAVITY_DEGREE`(0/2/3/4)。
- GMAT 整合：`GmatConsole --exit --run` 無頭驗證、自動讀報表對照、雙曲線相機／radius-range 已加。
- Config 驗證：`config_validator` 已放寬 SMA/ECC、支援雙曲線輸入。
- 種子機制四家族：relay／ladder／pcsplit／joint NLP 精修（HAP-47）。
- **拆棒管線（HAP-67，2026-09-11 上線，預設開）**：`src/burn_splitter.py` + `main.py` 的
  `legalize_violating_winner()`。DE 挑完贏家後，若有「超標但 Earth-safe」的違規棒，自動拆成
  合法多棒版（**段數動態算出、不再被 MAX_BURNS 綁死** → joint NLP 用真實 `calculate_score`
  壓低總 Δv），後面產腳本/GMAT/紀錄全用合法版。旗標 `strategy.AUTO_SPLIT_LEGALIZE`（設 false
  退回舊行為）。實證：contest.json **88.32（含 −10 違規）→ 98.31（零違規、GMAT 定燒命中、可交）**，
  +9.99 分。設計/驗證全記在 [HAP67_SPLIT_PIPELINE_PLAN.md](docs/HAP67_SPLIT_PIPELINE_PLAN.md)。
  注意：種子端的 pcsplit/split_even-as-seed 現在是死重（拆棒改由後處理），待收尾移除。
- 回歸：`uv run python run_regression.py`（5 支、~27s，動任何東西前先跑）。拆棒管線目前只有
  scratchpad 手動驗證，還沒收斂成正式回歸測試。

**開始下一輪前要處理的風險**（出自 [PROJECT_AUDIT_20260909.md](docs/PROJECT_AUDIT_20260909.md)）：
- 🟠 **P2 Earth-safe 判定是點質量解析式**（`reaches_perigee`/`check_constraints`）。下一輪若開攝動，
  長弧近地點會漂、解析判定不再精確——而它是失格線。→ HAP-20（攝動開時切數值密集取樣）。
- 🟠 **P3 雙曲線 A 從未端到端跑過**。防禦就位但沒有一組雙曲線測資實跑過 `main.py`+GMAT。→ HAP-46/HAP-36。
- 🟡 **P4 雙曲線 A 的 TA 未檢查是否落在漸近線內**（`|TA|<arccos(−1/e)`）。給錯會晚到 poliastro 才炸。
- ⚠️ **計分參數與 A/B 六根數要等官方發題**（`k_t/C_t/k_v/C_v`）。

## 環境（本機、不進 git）

- **目前開發機：Mac（Darwin）。** GMAT R2026a 在 `/Users/corn/Documents/GMAT R2026a/bin/GmatConsole`
  （已存在，寫進各 `configs/*.json` 的 `local.gmat_console_path`，或帶 `--gmat-console`）。
- `configs/` 整個被 gitignore、換機器不會帶過來。**設定檔的完整重建參數記在 [SCENARIOS.md](docs/SCENARIOS.md)**
  （configs/ 遺失就靠這份重建）。
- 2026-08-15 曾在 WSL2+Ryzen 上開發，那套 GMAT-on-WSL 修補若日後回 WSL 用得上，記在 DEVLOG_prelim.md 末段。
