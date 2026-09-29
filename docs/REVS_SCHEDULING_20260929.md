# REVS 集成案例統一排程（2026-09-29）

`run_study_over_revs()` 原本先跑完 REVS=0 的各棒數，再跑 REVS=4；第一趟尾端只剩少數案例時，
其餘核心閒置。現在把 `(REVS, burn_count)` 全部送進同一個 `ProcessPoolExecutor`，完成搜尋後
仍依 REVS 順序各自挑贏家、精修，再照原 §6 規則選兩趟較好者。單跑 REVS 時繼續使用原本的
`MissionOptimizer.run_study()` 路徑。

未設定 SEED 時，mealpy 仍可使用 thread 模式；共用池會依同時執行的行程數重新計算每案例
thread 上限，並限制明確指定的 `NUM_THREADS`，避免六個案例各自照三案例的配額超訂。
設定 SEED 時維持各案例單執行緒與 BLAS 單執行緒，供逐位元比較。

| 固定 SEED 基準（MAXITER=40、POPSIZE=10、MAX_BURNS=[1,2,3]） | 舊串行牆鐘 | 共用池牆鐘 | 結果 |
|---|---:|---:|---|
| official_sample | 37.7s | 26.0s | burns、times、mission_info、勝出 REVS 完全相同 |
| hyper_far | 78.0s | 49.7s | 同上 |

兩組在同一台機器上依序測量，約省 31%／36% 牆鐘。這是搜尋與每趟收尾的直接計時，不含拆棒；
不同幾何、棒數與 CPU 配額的收益會不同。`tests/test_revs_schedule.py` 使用 repo 內建小案例，
比較 REVS=0/4 共用池與逐趟搜尋的完整回傳值，並捕捉背景進度執行緒錯誤；測試已通過。
無 SEED、`NUM_THREADS=12` 的短案例也成功跑完。相同小案例以 multiprocessing `spawn`
啟動模式執行，成功得到有效解；修改後完整回歸 14/14 通過（422.2s）。

另用 [revs_unified_v1.json](../sweeps/revs_unified_v1.json) 跑 contest、SEED=0、600×20，
包含完整拆棒管線。新舊拆棒前與拆棒後的結果欄位完全相同（拆後 score
`98.31907221535428`、零違規），新 run 沒有冷編譯記錄。新 run 牆鐘 233s；舊對照資料
`early_stop_v1` 的同種子 off 為 422s，但當時同時跑 5 個 job，兩筆負載不同，不能用這組數字
估算排程加速。原始結果存於 `outputs/sweeps/revs_unified_v1/` 與
`outputs/sweeps/early_stop_v1/`（輸出目錄被 gitignore）。
