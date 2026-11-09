# 排位賽賽前準備

當天流程在 [CONTEST_DAY](CONTEST_DAY.md)。11-09 前一晚按 [TONIGHT_20261109](../final/TONIGHT_20261109.md) 的順序做，清場改照 [CLEANUP_20261109](../final/CLEANUP_20261109.md)（下面的清場指令仍可用，CLEANUP 多了金牌賽與 AI 程式的部分）。

## 盡快

- [ ] 寄出 [QUESTIONS_FOR_ORGANIZER](QUESTIONS_FOR_ORGANIZER.md)，回覆記在該檔最後一節。

## 賽前一晚

- [ ] `git pull`、`uv sync`，`git status` 乾淨、在 `Master`。
- [ ] `uv run python odc.py test --quick -q`
- [ ] **拔網路**，用名稱 `rehearsal` 照 CONTEST_DAY 從步驟 1 跑到步驟 7（順便讓 numba 快取變熱）：
  ```bash
  uv run python odc.py new-config rehearsal --gmat-console "/Users/corn/Documents/GMAT R2026a/bin/GmatConsole"
  ```
- [ ] 對答案：佔位題應該跟 [已知答案](../solutions/ranking_placeholder_86.78/README.md) 同分（求解 86.7847、重瞄準 86.7843；11-08 前的版本瞄正中心，重瞄準是 86.7807）。
- [ ] **清場**（彩排完才做）：彩排的 `rank-1` 留著，當天步驟 5 會報錯；`ranking.json` 留著，`new-config` 不會覆蓋。整批搬去封存：
  ```bash
  A=~/Documents/Program/ODC_archive_pre1109/rehearsal_$(date +%m%d_%H%M)/ODC_Program; mkdir -p "$A/outputs" "$A/configs_local"
  find outputs -mindepth 1 -maxdepth 1 ! -name .DS_Store -exec mv {} "$A/outputs/" \;
  find configs/local -mindepth 1 -maxdepth 1 ! -name config.json -exec mv {} "$A/configs_local/" \;
  ls outputs configs/local
  ```
  `outputs` 是空的、`configs/local` 只剩 `config.json` 才算完成。
- [ ] GMAT 有 `data/gravity/earth/EGM96.cof` 與 CSSI 太空天氣檔。
- [ ] 看 TASA 頁有沒有規則修訂；主辦有回覆就把太空船參數、曆元填進範本。
- [ ] 主辦沒回覆的題目抄在紙上，開賽時由桌電員問工作人員。
- [ ] 筆電充飽、充電器、延長線、兩支 USB、證件。
- [ ] Mac 關自動睡眠、自動更新。

## 實測紀錄

M4 MacBook Air、插電、快取已熱、排位賽範本設定（2026-10-30；含步驟 5 的 GMAT 驗證）：

| 題目 | 求解 | 重瞄準 | 驗證 | 結果 |
|---|---|---|---|---|
| 佔位題 | 149 s | 7 s | 3 s | 86.781 |
| hyper_far | 293 s | 13 s | 4 s | 82.638 |
| e1_r8（觸發 primer 重搜） | 220 s | — | — | 76.534 |
| hyper_far＋保底設定 | 270 s | — | — | 82.645 |

11-03 只計求解（`--stop-after solve`）：佔位題 136–158 s、3 次同分，見 [MAC_TIMING_20261103](../research/MAC_TIMING_20261103.md)。

人工步驟（抄題、核對、繳交）還沒計時，彩排後填這裡。
