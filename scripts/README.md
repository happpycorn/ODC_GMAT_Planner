# 實驗腳本

這些腳本以專案根目錄為基準尋找 `main.py`、`sweep_params.py` 和 sweep 規格。
在專案環境中以 `uv run python` 執行 Python 腳本。

| 工作 | 預覽 | 執行或彙整 |
| --- | --- | --- |
| C4 設定 | — | `uv run python scripts/generate_c4_configs.py` |
| C4 排程 | `uv run python scripts/c4_runner.py --dry-run --slots 4` | `uv run python scripts/c4_runner.py --slots 4 --gmat-console /path/to/GmatConsole` |
| C4 彙整 | — | `uv run python scripts/c4_summary.py --out outputs/c4 --md` |
| ablation_v1 | `scripts/run_ablation_v1.sh --dry-run` | `scripts/run_ablation_v1.sh` |
| budget_v1 與 slow | `scripts/run_budget_v1.sh --dry-run` | `scripts/run_budget_v1.sh` |
| 本機成果索引 | — | `uv run python scripts/output_inventory.py index` |
| 研究與交叉驗證 | [工具導覽](research/README.md) | 依導覽選用 `scripts/research/` 中的腳本 |

`sweeps/c4_v1.json` 與 `configs/shared/` 可重建 33 份 C4 設定。乾淨 clone 下，
`c4_runner.py --dry-run` 在記憶體中預覽這些設定；正式執行前才寫入 `configs/c4/`。
已有的本機 C4 設定不會被覆蓋；`uv run python scripts/generate_c4_configs.py --check`
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
`uv run python sweep_params.py sweeps/budget_v1.json --gmat --gmat-console /path/to/GmatConsole`。
重跑失敗工作時，舊 run 目錄、當時產生的設定及主控台日誌會一起移到
`outputs/sweeps/<實驗>/runs/_stale/`，方便回查。
`configs/c4/` 是被 Git 忽略的本機設定目錄；產生器只補缺少的檔案，遇到參數不同會先報錯。

`output_inventory.py` 也能驗證、壓縮封存與還原舊 sweep 的主控台日誌；指令見
[README 的成果管理段落](../README.md#查找與封存本機結果)。
Sweep 執行與日誌封存共用 Unix 檔案鎖，這兩項指令在 Linux／macOS 使用。
