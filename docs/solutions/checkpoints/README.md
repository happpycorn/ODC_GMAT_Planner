# 拆棒前贏家存檔（contest 幾何）

`main.py --from-winner <檔>` 跳過搜尋、直接重跑拆棒 + 產腳本 + GMAT（~4 分鐘）。改拆棒器時用它做前後對照。
存檔內的 config 已移除本機 `local` 區塊；重播時用 `--config <你的 config>` 提供 `local.gmat_console_path`。

| 檔案 | 拆前 | 路線 | 拆後（2026-09-23，`_slot_after_capped` 後） |
|---|---|---|---|
| `contest_route88.32_seed0_presplit.json` | 88.3219 | 預設管線 SEED 0：1498 m/s @0 s + 空燒 @1270.8 s + 終端 4691 m/s @2370.9 s | 98.3191 |
| `contest_route4_seed7_presplit.json` | 88.3009 | 強制 4 棒 SEED 7：1498 m/s @0 s + 空燒 @100.4 s / @867.6 s + 終端 4756 m/s @2386.5 s | 98.3189 |

重播前記得 pin BLAS（見 memory odc-blas-nondeterminism）：
`OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1`。
