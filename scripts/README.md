# 現行工具

從專案根目錄執行；Python 腳本使用 `uv run python`。

| 工具 | 用途與指令 |
|---|---|
| [check_scoring_params.py](../odc/tools/check_scoring_params.py) | 排位賽計分參數驗算：`uv run python odc.py scoring --demo-prelim`；正式參數與單位見[當天手冊](../docs/ranking/CONTEST_DAY.md) |
| [tmax_from_boundary.py](../odc/tools/tmax_from_boundary.py) | A 軌道根數與任務邊界計算 T_max：`uv run python odc.py tmax --config <檔> --boundary-km <km>`（`--write` 寫回） |
| [output_inventory.py](../odc/tools/output_inventory.py) | 重建本機成果索引：`uv run python odc.py outputs index`；也可驗證、壓縮封存與還原舊 sweep 日誌 |

成果管理指令見 [README](../README.md#查找與封存本機結果)。Sweep 執行與日誌封存共用 Unix 檔案鎖，這兩項指令在 Linux／macOS 使用。

可重跑的診斷與交叉驗證見[研究工具導覽](research/README.md)；C4、ablation_v1、budget_v1 的指令見其[封存一節](research/README.md#封存)。
