# 文件導覽

[專案 README](../README.md) 說明安裝、設定、執行與輸出；[STATUS](../STATUS.md) 記錄目前狀態。日期性報告保留當時的結論，最新設定以 STATUS 與程式為準。

## 比賽當天

| 文件 | 用途 |
|---|---|
| [ranking/CONTEST_DAY](ranking/CONTEST_DAY.md) | 排位賽 60 分鐘作業手冊：時間盒、三人分工、逐步指令、保底與失格檢查清單 |
| [ranking/RANKING_ROUND_RULES_20261006](ranking/RANKING_ROUND_RULES_20261006.md) | 排位賽規則跟初賽的差異，以及工具怎麼對應 |
| [ranking/QUESTIONS_FOR_ORGANIZER](ranking/QUESTIONS_FOR_ORGANIZER.md) | 給主辦單位的問題草稿（尚未寄出）：太空船參數、曆元、驗證設定、T_max、繳交格式 |
| [final/FINAL_STRATEGY](final/FINAL_STRATEGY.md) | 主攻排位賽前二的策略、賽前待辦與時程 |
| [final/AIAA_CTS_RESEARCH](final/AIAA_CTS_RESEARCH.md) | AIAA Capture the Satellite Challenge 考古，及對金／銅牌賽的啟示 |

## 現行參考

| 文件 | 用途 |
|---|---|
| [ARCHITECTURE](ARCHITECTURE.md) | 套件配置、solve 呼叫順序與存檔版本規則 |
| [CLI](CLI.md) | 單一入口的子命令、使用範例與舊指令對照 |
| [METHODOLOGY](METHODOLOGY.md) | 物理模型、搜尋、計分與 GMAT 驗證的設計原理 |
| [SCENARIOS](SCENARIOS.md) | 情境參數與測試目的；版控中的共用情境見 [configs/shared/](../configs/shared/) |
| [solutions/README](solutions/README.md) | 初賽解、正式繳交資料與可重播的拆棒前存檔 |
| [scripts/README](../scripts/README.md) | T_max 計算、計分參數驗算與本機成果索引工具 |
| [研究驗證工具](../scripts/research/README.md) | Porkchop、GMAT 對照及其他可重跑的診斷腳本，並列出封存的 C4／批次 sweep 工具 |
| [官方規則](../rules/) | 原始 PDF；具體數值仍以對應輪次的公告為準 |

## 研究報告

[research/](research/) 收錄已完成的實驗與設計研究；資料目錄隨報告保存在同層。

| 文件 | 結論／用途 |
|---|---|
| [C1_PRIMER_VECTOR_STUDY](research/C1_PRIMER_VECTOR_STUDY.md) | Primer 引導與加棒搜尋的理論及實作脈絡 |
| [C3_CONVEX_SPLITTER_PLAN](research/C3_CONVEX_SPLITTER_PLAN.md) | 拆棒收斂問題、修正與後續選項 |
| [C4_TERMINAL_SPLIT_AWARE_PLAN](research/C4_TERMINAL_SPLIT_AWARE_PLAN.md) | 終端棒拆後估分的設計與實測；已實作部分見文內結果 |
| [EARLY_STOP_ABLATION_20260929](research/EARLY_STOP_ABLATION_20260929.md) | 提早停止消融；目前預設關閉 |
| [EPHEM_CACHE_20261028](research/EPHEM_CACHE_20261028.md) | A 全程、B 第一棒前的檢查點快取已實作，查詢用原傳播器補積分、不插值；保留當時回歸未通過項目 |
| [HAP47_SPLIT_ALGORITHM_RESEARCH](research/HAP47_SPLIT_ALGORITHM_RESEARCH.md) | 早期拆棒演算法研究與 PoC |
| [HAP67_SPLIT_AWARE_INVESTIGATION](research/HAP67_SPLIT_AWARE_INVESTIGATION.md) | 中間棒拆分需求的調查與適用邊界 |
| [HAP67_SPLIT_PIPELINE_PLAN](research/HAP67_SPLIT_PIPELINE_PLAN.md) | 搜尋到合法化的拆棒管線 |
| [GLOBAL_ORACLE_20261028](research/GLOBAL_ORACLE_20261028.md) | 全域對照找到 hyper_far 的中段大前導棒家族，當時比管線多約 0.215 分 |
| [E1_FREQUENCY_20261029](research/E1_FREQUENCY_20261029.md) | 8 題隨機題中 oracle 贏 3 題，支持進行完整四臂比較 |
| [ORACLE_INTEGRATION_PLAN_20261029](research/ORACLE_INTEGRATION_PLAN_20261029.md) | 中段大燒路線的問題、量測與實作規劃 |
| [ORACLE_PHASE2_20261029](research/ORACLE_PHASE2_20261029.md) | 四臂比較建議開 SPLIT_LEADING 與 ORACLE_TWOBURN；4 題排位賽題高 0.10–0.22 分，smoke／contest 平手 |
| [PERTURBATION_GAP_20261019](research/PERTURBATION_GAP_20261019.md) | 我們的解放進排位賽官方攝動模型還打不打得中；比賽當天要加「全攝動 B 平面重瞄準」 |
| [PRIMER_FAST_V1_20261028](research/PRIMER_FAST_V1_20261028.md) | fast 在首批對照省時，但後續救分案例比 full 少 0.51 分 |
| [RANKING_MC_20261019](research/RANKING_MC_20261019.md) | 排位賽條件（250 m/s、總 Δv 3 km/s）多種子實測：時間、8–15 棒拆棒穩定度、失格案例 |
| [RANKING_PENALTY_V2_20261019](research/RANKING_PENALTY_V2_20261019.md) | 排位賽搜尋懲罰改成「失格層」：任何合法候選都排在總 Δv 超標／拆不掉的候選前面 |
| [REVS_SCHEDULING_20260929](research/REVS_SCHEDULING_20260929.md) | REVS 案例共用行程池的驗證 |
| [SPLITTER_SPEED_20261020](research/SPLITTER_SPEED_20261020.md) | 拆棒器加速與穩定化：3 顆種子並行 22 分鐘、疊合差分（逐位元不變）、多起點拆棒；現場設定已寫進 ranking_round.json |
| [SPLIT_AWARE_SEARCH_FIX_20261029](research/SPLIT_AWARE_SEARCH_FIX_20261029.md) | SEARCH 與 LEADING 同開時修正搜尋／重播不同尺；LEADING 關時保留原行為與已知問題 |

## 封存

| 文件 | 用途 |
|---|---|
| [archive/refactor_20261030/REFACTOR_REPORT](archive/refactor_20261030/REFACTOR_REPORT.md) | 10 月 30 日全面重構的分階段驗收證據；patch 對照在同目錄 REFACTOR_PATCH_TARGETS |
| [archive/PROJECT_AUDIT_20260909](archive/PROJECT_AUDIT_20260909.md) | 9 月 9 日盤點快照；其中部分清理已完成 |
| [archive/HANDOFF_20260928](archive/HANDOFF_20260928.md) | 9 月 28 日交接快照；任務 1–3 已在 9 月 29 日完成 |
| [archive/FLOW_EFFICIENCY_AUDIT_20260923](archive/FLOW_EFFICIENCY_AUDIT_20260923.md) | 流程成本審計；其中部分提案已完成 |
| [archive/NEXT_ROUND_BACKLOG](archive/NEXT_ROUND_BACKLOG.md) | 下一輪題型、依賴與待官方發題後的檢查項目 |
| [archive/prelim/CONTEST_DAY](archive/prelim/CONTEST_DAY.md) | 初賽當天的作業手冊與站別卡入口 |
| [archive/prelim/RESEARCH_ARCHIVE](archive/prelim/RESEARCH_ARCHIVE.md) | 初賽一次性腳本的結論位置與 Git 歷史取回方式 |
| [archive/prelim/PORKCHOP](archive/prelim/PORKCHOP.md) | 單棒窮舉與真傳播器重播的結果 |
| [log/DEVLOG_prelim](log/DEVLOG_prelim.md) | 初賽逐日開發日誌 |
| [log/DEVLOG_ranking](log/DEVLOG_ranking.md) | 2026-10-30 從 STATUS 移出的排位賽準備期紀錄 |

[archive/](archive/) 保存過期快照與已結束的初賽資料；[log/](log/) 保存開發紀錄。本機實驗產物在 `outputs/research/`。
