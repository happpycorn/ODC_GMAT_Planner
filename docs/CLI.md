# 命令列用法

從專案根目錄執行 `uv run python odc.py <子命令>`；每個子命令的完整選項見 `--help`。
未指定設定檔時使用 `configs/local/config.json`，共用情境放在 `configs/shared/`。輸入位置參數與對應旗標不能同時指定。
各工具的結束碼原樣傳回；求解找不到合法路線時為 3，工作目錄錯誤或參數衝突時為 2。

## solve

搜尋任務，依停止階段保存方案、產腳本或驗證。

舊指令對照：`main.py --config <設定檔>`。

```bash
uv run python odc.py solve configs/shared/contest.json --no-gmat
uv run python odc.py solve configs/shared/ranking_round.json --stop-after solve --run-dir outputs/runs/solve-a
```

## resume

讀取拆棒前贏家，重跑合法化與後續階段。

舊指令對照：`main.py --from-winner <winner.json>`。

```bash
uv run python odc.py resume docs/solutions/checkpoints/contest_route4_seed7_presplit.json --no-gmat
uv run python odc.py resume outputs/runs/solve-a/winner_presplit_seed0.json --stop-after solve --run-dir outputs/runs/resume-a
```

## export

重用已保存的 mission，產生腳本。存檔版本規則見 [架構文件](ARCHITECTURE.md#版本驗證)。

舊指令對照：`main.py --from-mission <mission.json>`。

```bash
uv run python odc.py export outputs/runs/solve-a/mission.json --no-gmat --run-dir outputs/runs/export-a
uv run python odc.py export outputs/runs/solve-a/mission.json --stop-after export --model-scale 0.8 --run-dir outputs/runs/export-large
```

## retarget

以官方全攝動模型執行 B 平面重瞄準，檢查後產生固定燃燒繳交版。

舊指令對照：`main.py --from-mission <mission.json> --retarget-full-perturbation`。

```bash
uv run python odc.py retarget outputs/runs/solve-a/mission.json --run-dir outputs/runs/retarget-a
uv run python odc.py retarget outputs/runs/solve-a/mission.json --retarget-burn 0 --gmat-console "C:/GMAT/bin/GmatConsole.exe" --run-dir outputs/runs/retarget-b
```

## verify

用 GMAT 驗證既有腳本，保存獨立報表與驗證紀錄。

舊指令對照：`main.py --verify-script <script>`。

```bash
uv run python odc.py verify outputs/runs/retarget-a/output_submit.txt --run-dir outputs/runs/recheck-a
uv run python odc.py verify outputs/runs/export-a/output.txt --gmat-console "C:/GMAT/bin/GmatConsole.exe" --run-dir outputs/runs/recheck-b
```

## check

回顯軌道、時間與規則，檢查情境是否合理。

舊指令對照：`check_problem.py --config <設定檔>`。

```bash
uv run python odc.py check configs/shared/official_sample.json
uv run python odc.py check configs/shared/ranking_round.json
```

## feasibility

估算能量下限，網格探測單棒或多棒可行性。

舊指令對照：`feasibility.py --config <設定檔>`。

```bash
uv run python odc.py feasibility configs/shared/official_sample.json --grid 3
uv run python odc.py feasibility configs/shared/contest.json --burns 3
```

## sweep-burns

以粗掃與精查選擇適合投入預算的燃燒次數範圍。

舊指令對照：`sweep_burns.py --config <設定檔>`。

```bash
uv run python odc.py sweep-burns configs/shared/contest.json --burns 2-6
uv run python odc.py sweep-burns configs/shared/contest.json --burns 2-8 --coarse-iters 20 --coarse-popsize 5
```

## sweep

依規格執行情境、種子與參數組的批次實驗。

舊指令對照：`sweep_params.py <spec>`。

```bash
uv run python odc.py sweep sweeps/ranking_mc_v1.json --dry-run
uv run python odc.py sweep sweeps/ranking_mc_v1.json --slots 2 --out outputs/sweeps/ranking-local
```

## test

執行 tests 下的獨立回歸腳本。

舊指令對照：`run_regression.py`。

```bash
uv run python odc.py test --quick -q
uv run python odc.py test test_pipeline_stages test_odc_cli
```

## tmax

由 A 軌道與任務邊界計算 T_max。

舊指令對照：`scripts/tmax_from_boundary.py`。

```bash
uv run python odc.py tmax --config configs/shared/ranking_round.json --boundary-km 100000
uv run python odc.py tmax --config configs/local/ranking.json --boundary-alt-km 93621.863 --write
```

## scoring

將官方計分參數換成工具單位，檢查參考解與飽和情形。

舊指令對照：`scripts/check_scoring_params.py`。

```bash
uv run python odc.py scoring --demo-prelim
uv run python odc.py scoring --kt 0.003982 --kt-unit 1/s --Ct 6505.65 --Ct-unit s --kv 0.0011862 --kv-unit "1/(m/s)" --Cv 9064.3 --Cv-unit m/s
```

## outputs

索引執行結果，或驗證及還原已封存的 sweep 日誌。

舊指令對照：`scripts/output_inventory.py <子命令>`。

```bash
uv run python odc.py outputs index
uv run python odc.py outputs verify-archive outputs/archive/sweep-console-logs.tar.gz
uv run python odc.py outputs restore-archive outputs/archive/sweep-console-logs.tar.gz
```

## new-config

從共用情境複製本機設定；目標已存在時保留原檔，驗證失敗會清掉本次新檔。

舊指令對照：無，重構時新增。

```bash
uv run python odc.py new-config ranking
uv run python odc.py new-config prelim --from contest
uv run python odc.py new-config ranking-win --from ranking_round --gmat-console "C:/GMAT/bin/GmatConsole.exe"
```
