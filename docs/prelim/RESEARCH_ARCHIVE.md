# 初賽一次性研究封存索引

`scratch_overnight/` 曾收集初賽期的試算與驗證腳本。主要結論已整理進正式文件或程式；
可重跑的診斷工具移至 [`scripts/research/`](../../scripts/research/README.md)。
一次性腳本自工作樹移除，原始碼仍在 Git commit `0369919` 的
`research/archive_prelim/`。需要查算法或數值時可用：

```bash
git show 0369919:research/archive_prelim/design_hard_mode_case.py
```

| 主題 | 現在查看 | 舊腳本（位於上述 commit） |
|---|---|---|
| 單棒網格、多圈解與重播差距 | [Porkchop 報告](PORKCHOP.md)；建網格、畫圖及重播工具仍在 `scripts/research/` | `porkchop_grid.py`、`porkchop_plot.py`（已移至工具區） |
| `hard_mode`、遠地點轉面、反向高離心率等情境設計 | [情境目錄](../SCENARIOS.md)、`configs/shared/` | `design_*.py`、`verify_hardmode_*.py` |
| 雙曲線與側向燃燒可行性 | [情境目錄](../SCENARIOS.md) | `split_burn_feasibility.py`、`design_lateral_burn_case*.py` |
| 多棒基準與拆棒試算 | [初賽日誌](../log/DEVLOG_prelim.md)、[拆棒研究](../HAP47_SPLIT_ALGORITHM_RESEARCH.md) | `mb_*.py`、`split_test*.py`、`decode_*.py` |
| GTOC-9 軌道壓力測試與多圈 A/B | [初賽日誌](../log/DEVLOG_prelim.md) | `gtoc9_*.py` |

本機一次性 JSON、圖片與網格不在版控中；保留的 `porkchop_h20.npz` 已移至
`outputs/research/`。封存腳本可能依賴當時的本機設定或暫存檔，Git 歷史保留的是原始研究程式，
不能保證在目前環境直接執行。
