# 排位賽佔位題的已知答案（86.78）

10-30 彩排（commit `209953c`）用 [ranking_round.json](../../../configs/shared/ranking_round.json) 原封不動跑完 CONTEST_DAY 步驟 5–6 的結果，
從 `outputs/runs/rehearsal-rr*` 收進版控。賽前彩排拿來對答案：同一份設定跑出來應該落在同一個解。

| 項目 | 求解（步驟 5） | 全攝動重瞄準（步驟 6） |
|---|---|---|
| 分數 | 86.7847 | 86.7807（`accepted`） |
| 棒數 | 4 | 4 |
| 最大單棒 | — | 247.98 m/s |
| 總 Δv | 639.35 m/s | 639.93 m/s |
| T_team | 19,972.99 s | 19,973.46 s |
| 命中距離 | GMAT 3.49 km | 全攝動 d_min 0.0042 km、GMAT 固定版 0.0042 km |

求解約 147 s（Mac、快取已熱）。11-03 夜跑同設定 3 次都是 86.7847（[MAC_TIMING_20261103](../../research/MAC_TIMING_20261103.md)）。

## 檔案

- `mission.json`：步驟 5 的解。
- `retarget.json`：步驟 6 的重瞄準結果，CONTEST_DAY 步驟 7 的清單就是讀這個檔。
- `output_submit_retargeted.txt`：步驟 6 產的繳交腳本（全 ASCII），可以拿來練習步驟 8 在主辦機上開檔、跑、對 Report。

A/B 軌道與計分參數是佔位值，**不能拿去比賽當天交**。
