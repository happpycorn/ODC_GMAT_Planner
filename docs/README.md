# 文件導覽

從 [專案 README](../README.md) 看安裝、設定、執行與輸出；從 [STATUS](../STATUS.md) 看目前進度與待辦。本頁按用途整理其餘文件。日期標在檔名上的研究與交接紀錄保留當時的結論，最新狀態以 STATUS 為準。

## 操作與重現

| 文件 | 用途 |
|---|---|
| [METHODOLOGY](METHODOLOGY.md) | 物理模型、搜尋、計分與 GMAT 驗證的設計原理 |
| [SCENARIOS](SCENARIOS.md) | 情境參數與測試目的；版控中的共用情境見 `../configs/shared/` |
| [solutions/README](solutions/README.md) | 初賽解、正式繳交資料與可重播的拆棒前存檔 |
| [output_inventory.py](../scripts/output_inventory.py) | 重建本機 `outputs/INDEX.md`，並驗證、封存或還原舊 sweep 日誌；用法見[專案 README](../README.md#查找與封存本機結果) |
| [scripts/README](../scripts/README.md) | C4 排程、彙整與批次 sweep 的可重用指令；C4 runner 使用 Linux `/proc` |
| [C4 實驗規格](../sweeps/c4_v1.json) | 搭配 `configs/shared/` 重建 33 份 C4 本機設定 |
| [官方規則](../rules/) | 原始 PDF；具體數值仍以對應輪次的公告為準 |

## 目前決策與未完成工作

| 文件 | 用途 |
|---|---|
| [NEXT_ROUND_BACKLOG](NEXT_ROUND_BACKLOG.md) | 下一輪題型、依賴與待官方發題後的檢查項目 |
| [C4_TERMINAL_SPLIT_AWARE_PLAN](C4_TERMINAL_SPLIT_AWARE_PLAN.md) | 終端棒拆後估分的設計與實測；已實作部分見文內結果 |
| [C1_PRIMER_VECTOR_STUDY](C1_PRIMER_VECTOR_STUDY.md) | Primer 引導與加棒搜尋的理論及實作脈絡 |
| [C3_CONVEX_SPLITTER_PLAN](C3_CONVEX_SPLITTER_PLAN.md) | 拆棒收斂問題、修正與後續選項 |
| [HAP67_SPLIT_PIPELINE_PLAN](HAP67_SPLIT_PIPELINE_PLAN.md) | 搜尋到合法化的拆棒管線 |
| [HAP67_SPLIT_AWARE_INVESTIGATION](HAP67_SPLIT_AWARE_INVESTIGATION.md) | 中間棒拆分需求的調查與適用邊界 |

## 實驗與歷史紀錄

| 文件 | 內容 |
|---|---|
| [EARLY_STOP_ABLATION_20260929](EARLY_STOP_ABLATION_20260929.md) | 提早停止消融；目前預設關閉 |
| [REVS_SCHEDULING_20260929](REVS_SCHEDULING_20260929.md) | REVS 案例共用行程池的驗證 |
| [FLOW_EFFICIENCY_AUDIT_20260923](FLOW_EFFICIENCY_AUDIT_20260923.md) | 流程成本審計；其中部分提案已完成 |
| [HAP47_SPLIT_ALGORITHM_RESEARCH](HAP47_SPLIT_ALGORITHM_RESEARCH.md) | 早期拆棒演算法研究與 PoC |
| [PROJECT_AUDIT_20260909](PROJECT_AUDIT_20260909.md) | 9 月 9 日盤點快照；其中部分清理已完成 |
| [HANDOFF_20260928](HANDOFF_20260928.md) | 9 月 28 日交接快照；任務 1–3 已在 9 月 29 日完成 |

初賽當天的 [作業手冊與站別卡](prelim/CONTEST_DAY.md)、[逐日開發日誌](log/DEVLOG_prelim.md) 都是歷史資料。`scratch_overnight/` 的研究腳本另有 `tools/` 與 `archive_prelim/`，不是正式執行入口。
