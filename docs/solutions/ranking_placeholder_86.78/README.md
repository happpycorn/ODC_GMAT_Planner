# 排位賽佔位題的已知答案（86.78）

用 [ranking_round.json](../../../configs/shared/ranking_round.json) 原封不動跑完 CONTEST_DAY 步驟 5–6 的結果。賽前彩排拿來對答案：
同一份設定跑出來應該落在同一個解。2026-11-08 重瞄準改成瞄 3.5 km 圈（`strategy.RETARGET_AIM_KM`，見
[retarget.py](../../../odc/gmat/retarget.py) 模組說明第 2 點）後，從 `outputs/runs/final-placeholder-*` 重新收進版控；
舊版瞄正中心的答案是重瞄準 86.7807（最後一棒多花 0.58 m/s，d_min 0.004 km）。

| 項目 | 求解（步驟 5） | 全攝動重瞄準（步驟 6） |
|---|---|---|
| 分數 | 86.784742 | 86.784288（`accepted`） |
| 棒數 | 4 | 4 |
| 最大單棒 | — | 247.98 m/s |
| 總 Δv | 639.35 m/s | 639.39 m/s |
| T_team | 19,972.99 s | 19,973.30 s |
| 命中距離 | Python 3.49 km（全攝動重播 3.78 km） | 全攝動 d_min 3.500 km、GMAT 固定版 3.500 km |

求解約 147 s（Mac、快取已熱）。11-03 夜跑同設定 3 次都是 86.7847（[MAC_TIMING_20261103](../../research/MAC_TIMING_20261103.md)）。

## 檔案

- `mission.json`：步驟 5 的解。
- `retarget.json`：步驟 6 的重瞄準結果，CONTEST_DAY 步驟 7 的清單就是讀這個檔。
- `output_submit_retargeted.txt`：步驟 6 產的繳交腳本（全 ASCII），可以拿來練習步驟 8 在主辦機上開檔、跑、對 Report。

A/B 軌道與計分參數是佔位值，**不能拿去比賽當天交**。
