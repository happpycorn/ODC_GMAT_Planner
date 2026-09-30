# 研究區

這裡存放實驗與交叉驗證腳本。正式求解入口仍是根目錄的 `main.py`；研究腳本從專案根目錄執行。

| 目錄 | 內容 | 用途 |
|---|---|---|
| [`tools/`](tools/) | 可重跑的診斷、對照與 HAP-47 PoC | 需要時個別執行；部分腳本需要本機 config 或 GMAT |
| [`tools/gmat/`](tools/gmat/) | GMAT 對照腳本、固定輸入與研究報告 | 手寫 `.script`、兩份對照 `.npy` 仍在版控中 |
| [`archive_prelim/`](archive_prelim/) | 初賽期一次性實驗與 [Porkchop 報告](archive_prelim/PORKCHOP.md) | 保留研究紀錄；部分腳本依賴舊本機檔案或輸出，不能保證直接重跑 |
| `generated/` | 網格、JSON、圖片等可重建產物 | 整個目錄內容不進版控（只有 `.gitkeep`） |

常用入口：

```bash
uv run python research/tools/degradation_audit.py --list
uv run python research/tools/known_answer_suite.py
uv run python research/tools/porkchop_verify.py 20
```

最後一項需要先用 `uv run python research/archive_prelim/porkchop_grid.py 20` 建立
`research/generated/porkchop_h20.npz`；詳細前提與結果見 [Porkchop 報告](archive_prelim/PORKCHOP.md)。
HAP-47 PoC 的背景與依賴見 [研究紀錄](../docs/HAP47_SPLIT_ALGORITHM_RESEARCH.md)。
執行其中的 GMAT 驗證腳本時，可用 `GMAT_CONSOLE` 指定本機執行檔路徑。

2026-09-30 前此目錄名為 `scratch_overnight/`。歷史日誌與盤點保留當時的路徑文字；
舊頂層腳本現在依用途位於 `tools/` 或 `archive_prelim/`，一次性產物移至 `generated/`。
