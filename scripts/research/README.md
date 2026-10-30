# 可重跑的研究工具

正式求解入口是根目錄的 `odc.py`。這裡保留獨立驗證與診斷腳本，從專案根目錄執行。
輸出寫入 Git 忽略的 `outputs/research/`；正式成果與結論仍以 `docs/`、`configs/shared/`
及 `odc/` 為準。

| 目的 | 入口 | 主要紀錄 |
|---|---|---|
| 檢查極端幾何 | `degradation_audit.py --list` | [情境目錄](../../docs/SCENARIOS.md) |
| 單棒全域網格 | `porkchop_grid.py 20` → `porkchop_verify.py 20` | [Porkchop 報告](../../docs/archive/prelim/PORKCHOP.md) |
| HAP-47 拆棒 PoC | `hap47_poc_nlp_split.py` | [拆棒研究](../../docs/research/HAP47_SPLIT_ALGORITHM_RESEARCH.md) |
| GMAT 對照 | `gmat/` | [GMAT 工具說明](gmat/README.md) |
| 排位賽全攝動落差與重瞄準 | `perturbation_gap.py ladder` → `mc` → `retarget --mode bplane` | [全攝動落差報告](../../docs/research/PERTURBATION_GAP_20261019.md) |

例如：

```bash
uv run python scripts/research/degradation_audit.py --list
uv run python scripts/research/porkchop_verify.py 20
```

第二個指令需要先建立 `outputs/research/porkchop_h20.npz`，或在本機保留原有網格。
需要 GMAT 的腳本可用 `GMAT_CONSOLE` 指定執行檔。部分診斷依賴本機設定或額外套件；
各腳本開頭列出用法。初賽期的一次性腳本已從工作樹移除，見
[封存索引](../../docs/archive/prelim/RESEARCH_ARCHIVE.md)。

## 封存

舊實驗腳本在 [archive/](archive/)，保留重跑與彙整用途，從專案根目錄執行。

| 工作 | 預覽 | 執行或彙整 |
|---|---|---|
| [C4 設定](archive/generate_c4_configs.py) | `uv run python scripts/research/archive/generate_c4_configs.py --check` | `uv run python scripts/research/archive/generate_c4_configs.py` |
| [C4 排程](archive/c4_runner.py) | `uv run python scripts/research/archive/c4_runner.py --dry-run --slots 4` | `uv run python scripts/research/archive/c4_runner.py --slots 4 --gmat-console /path/to/GmatConsole` |
| [C4 彙整](archive/c4_summary.py) | — | `uv run python scripts/research/archive/c4_summary.py --out outputs/c4 --md` |
| [ablation_v1](archive/run_ablation_v1.sh) | `bash scripts/research/archive/run_ablation_v1.sh --dry-run` | `bash scripts/research/archive/run_ablation_v1.sh` |
| [budget_v1 與 slow](archive/run_budget_v1.sh) | `bash scripts/research/archive/run_budget_v1.sh --dry-run` | `bash scripts/research/archive/run_budget_v1.sh` |

`sweeps/c4_v1.json` 與 `configs/shared/` 可重建 33 份 C4 設定。乾淨 clone 下，
`c4_runner.py --dry-run` 在記憶體中預覽這些設定；正式執行前才寫入 `configs/c4/`。
已有的本機 C4 設定不會被覆蓋；`uv run python scripts/research/archive/generate_c4_configs.py --check`
可檢查其物理與搜尋參數，不會建立新檔。
`c4_runner.py` 預設讀取 `configs/c4/`，寫入 `outputs/c4/`；可用 `--config-dir`、
`--out`、`--python` 和 `--gmat-console` 指定其他位置。它會跳過 `run.json` 標記為完成的工作，
並將未完成的既有工作目錄改名為 `.stale<時間戳>` 後重跑。舊的同名
`*.console.log` 會移到該 stale 目錄的 `console.log`；若工作目錄不存在，
會以 `.stale<時間戳>` 檔名保存在輸出目錄。
`c4_runner.py` 使用 Linux `/proc` 監看行程與記憶體，目前只支援 Linux。
`c4_summary.py` 讀取 `--out` 指定的工作目錄，不修改結果。

兩個 sweep 腳本預設使用 5 個槽位、將結果寫入 `outputs/sweeps/`。
可用 `--slots N` 和 `--out-root PATH` 調整；相對輸出路徑以呼叫腳本時的工作目錄為基準。
要對 sweep 的每筆結果執行 GMAT 驗證，可直接跑
`uv run python odc.py sweep sweeps/budget_v1.json --gmat --gmat-console /path/to/GmatConsole`。
重跑失敗工作時，舊 run 目錄、當時產生的設定及主控台日誌會一起移到
`outputs/sweeps/<實驗>/runs/_stale/`，方便回查。
`configs/c4/` 是被 Git 忽略的本機設定目錄；產生器只補缺少的檔案，遇到參數不同會先報錯。
