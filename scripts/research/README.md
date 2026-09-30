# 可重跑的研究工具

正式求解入口是根目錄的 `main.py`。這裡保留獨立驗證與診斷腳本，從專案根目錄執行。
輸出寫入 Git 忽略的 `outputs/research/`；正式成果與結論仍以 `docs/`、`configs/shared/`
及 `src/` 為準。

| 目的 | 入口 | 主要紀錄 |
|---|---|---|
| 檢查極端幾何 | `degradation_audit.py --list` | [情境目錄](../../docs/SCENARIOS.md) |
| 單棒全域網格 | `porkchop_grid.py 20` → `porkchop_verify.py 20` | [Porkchop 報告](../../docs/prelim/PORKCHOP.md) |
| HAP-47 拆棒 PoC | `hap47_poc_nlp_split.py` | [拆棒研究](../../docs/HAP47_SPLIT_ALGORITHM_RESEARCH.md) |
| GMAT 對照 | `gmat/` | [GMAT 工具說明](gmat/README.md) |

例如：

```bash
uv run python scripts/research/degradation_audit.py --list
uv run python scripts/research/porkchop_verify.py 20
```

第二個指令需要先建立 `outputs/research/porkchop_h20.npz`，或在本機保留原有網格。
需要 GMAT 的腳本可用 `GMAT_CONSOLE` 指定執行檔。部分診斷依賴本機設定或額外套件；
各腳本開頭列出用法。初賽期的一次性腳本已從工作樹移除，見
[封存索引](../../docs/prelim/RESEARCH_ARCHIVE.md)。
