# 初賽解存檔（從 `outputs/` 封存進版控）

初賽期間 `outputs/best_*/` 累積的解與教訓。`outputs/` 本身是 gitignore 的活動暫存區、
會被每次跑覆寫，所以把**值得長期保留的部分**（各解的 SUMMARY、冠軍實際繳交件、
重力模型 bug 記錄）搬進這裡版控，其餘可重生的跑檔已清掉。封存日期 2026-09-11。

## 冠軍（實際繳交）

- [`98.32_champion_team19.md`](98.32_champion_team19.md) — Score 98.32、零違規、Earth-safe、GMAT 驗證過的五棒解
- `98.32_champion_team19_report.txt` — 對應的 GMAT Report（2.1MB，實際上傳的繳交件）

## 分數演進（各解的設計理由與取捨）

| 檔案 | Score | 重點 |
|---|---|---|
| [`84.90_single_burn_unconstrained.md`](84.90_single_burn_unconstrained.md) | 84.90 | 不設約束的單棒基準 |
| [`86.28_clean_legal.md`](86.28_clean_legal.md) | 86.28 | 全網格普查找到的零違規窄峰（L-SHADE 找不到）|
| [`88.30_penalty_2burn.md`](88.30_penalty_2burn.md) | 88.30 | 收尾一棒超標 3 倍、吃 −10 罰分的兩棒解 |
| [`88.32_pointmass.md`](88.32_pointmass.md) | 88.32 | 88.30 在正確點質量模型（`GRAVITY_DEGREE=0`）下的重驗 |
| [`98.21_split5.md`](98.21_split5.md) | 98.21 | 把 88 家族的超標收尾拆成 4 段合法燒 → 罰分歸零 |
| [`98.31_split5_rebalanced.md`](98.31_split5_rebalanced.md) | 98.31 | 五棒再平衡 |
| [`98.319_route4_split6.md`](98.319_route4_split6.md) | **98.3190** | 2026-09-23 事後：4 棒路線家族（拆前 88.30 反而拆後最高）+ A1 拆棒，GMAT 驗證、含繳交腳本 |

## 教訓（負面/警示）

- [`gravity_model_bug.md`](gravity_model_bug.md) — 官方 script 用點質量（`Degree=0`），
  早期 86.28/88.30 用 J2+J3+J4 算的已作廢；換模型的完整故事
- [`INVALID_99.996_hits_earth.md`](INVALID_99.996_hits_earth.md) — Score 99.996 的兩棒解
  **會撞地球**：`_replay_mission` 與 GMAT `InterceptSuccess` 都抓不到，只有
  `fast_fitness_evaluator` 抓得到——手搓解務必用它再驗一次
