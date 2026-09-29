# 提早停止消融（2026-09-29）

## 結論

`optimization.EARLY_STOP_ENABLED` 已接到 mealpy `solve(termination=...)`，預設 `false`。
啟用後確實提前停止並省 CPU，但在多個情境顯著掉分。**保留開關，競賽預設維持關閉。**
現有 `MAX_EARLY_STOP`、`TOL` 只有開關為 `true` 時生效；`TOL` 是分數單位。

## 方法

- 四個快情境 × 5 顆 SEED × off/on，固定 MAXITER=600、POPSIZE=20，共 40 次。
  規格：[early_stop_v1.json](../sweeps/early_stop_v1.json)。每次走 `main.py --stop-after solve`，
  包含搜尋與拆棒合法化，不含 GMAT。
- `weird_test` 使用相同預算與 3 顆 SEED，on 跑 3 次，off 採既有
  `budget_v1_slow` 的 `B1_pop20` 暖快取結果。規格：[early_stop_weird_v1.json](../sweeps/early_stop_weird_v1.json)。
- `sweep_params.py` 在快情境開跑前暖 numba 快取，逐筆記錄快取變動、最終分數、實際代數和 CPU 秒。
  40 次快情境與 3 次窄窗測試均為 `ok`、零違規、無冷編譯記錄。
- 快情境的 20 筆 off 最終結果與先前 `budget_v1` 同情境、同 SEED 的結果 **20/20 完全相同**。
  這驗證了新開關預設關閉時維持歷史行為。執行時工作目錄尚有未 commit 改動，重現請使用本文件對應的程式版本。

| 情境 | off 分數中位 | on 分數中位 | on 相對 off 最差差距 | on/off CPU 中位比例 |
|---|---:|---:|---:|---:|
| contest | 98.3191 | 98.3191 | −0.00006 | 0.59 |
| contest_fastT | 76.7256 | 76.6481 | **−1.7269** | 0.43 |
| official_sample | 90.4412 | 90.2082 | **−0.2329** | 0.58 |
| hyper_far | 82.5912 | 82.0421 | **−0.5561** | 0.29 |
| weird_test（歷史 off 基準） | 78.8532 | 76.8984 | **−1.9547** | 0.064 |

表中 CPU 比例是相同 SEED 的 on/off CPU 秒比例之中位數；較小代表較省。快情境全部為同批配對。
`weird_test` 的 off 來自先前暖快取批次，時間比值可能受批次環境影響；分數差距在三顆 SEED
都約 −1.9547。`hyper_far` 五顆種子全掉約 0.55；`official_sample` 五顆全掉約 0.233。
`contest_fastT` seed 3、4 掉約 1.727，顯示早停可能錯過較晚找到的解。

一個 8 代、`MAX_EARLY_STOP=2`、`TOL=1000` 的功能探針也確認 off 跑滿 8/8，on 在 2/8 停止。
探針刻意使用極寬容忍值，僅用來驗證開關接線，不用來決定競賽預設。
把同一個 on 探針改成 `SEED=null`、`NUM_THREADS=2` 後，thread 模式也在 2/8 代停止，
並成功儲存求解結果。修改後完整回歸 13/13 通過（389.9s），包含開關型別驗證。

原始資料在 `outputs/sweeps/early_stop_v1/`、`outputs/sweeps/early_stop_weird_v1/`、
`outputs/sweeps/early_stop_probe/`（輸出目錄被 gitignore）。可用
`uv run python sweep_params.py sweeps/early_stop_v1.json --summary` 重看彙整。
