# 11/09 決賽全天總覽

印出來帶去。每一場的細節照各自的手冊做，這頁只講哪一場用哪個資料夾、哪份手冊，以及兩場之間要做什麼。

## 時程

| 時間 | 項目 | 用什麼 |
|---|---|---|
| 10:45–11:45 | **排位賽**（60 分鐘） | ODC_Program |
| 12:50 | 公布四強 | |
| 13:00–14:30 | 銅牌賽（排位 3、4 名） | ODC_GMAT_DRL |
| 14:30–16:00 | 金牌賽（排位 1、2 名） | ODC_GMAT_DRL |

## 兩場對照

| | 排位賽 | 金／銅牌賽 |
|---|---|---|
| 資料夾 | `~/Documents/Program/ODC_Program` | `~/Documents/Program/ODC_GMAT_DRL` |
| 指令開頭 | `uv run python odc.py ...` | `.venv/bin/python copilot.py final ...` |
| 當天手冊 | [CONTEST_DAY](../ranking/CONTEST_DAY.md) | [CONTEST_DAY_FINAL](../../../ODC_GMAT_DRL/CONTEST_DAY_FINAL.md) |
| 規則 PDF | [排位賽規則_20261101](../../rules/排位賽規則_20261101.pdf) | [四強賽規則_20261029](../../rules/四強賽規則_20261029.pdf) |
| 當天寫入 | `configs/local/ranking.json`、`outputs/runs/rank-*` | `day/` |
| 交什麼 | GMAT Script＋Report（USB 帶去主辦機） | 每回合手寫一行 `角色, 回合, ΔvX, ΔvY, ΔvZ` |
| 力學 | 全攝動（GMAT 重驗） | 純二體 |

兩場的指令只在各自的資料夾裡跑。開兩個終端機視窗，分別命名「排位賽」和「金牌賽」，**不要在同一個視窗裡 `cd` 來回切換**。

## 開賽前確認

- 前一晚照 [PRE_CONTEST](../ranking/PRE_CONTEST.md) 與 [PRE_CONTEST_FINAL](../../../ODC_GMAT_DRL/PRE_CONTEST_FINAL.md) 做完，最後一項是清場。
- 確認三個地方是空的：`ODC_Program/outputs/runs/`、`ODC_Program/configs/local/` 裡只剩 `config.json`、`ODC_GMAT_DRL/day/` 不存在。
  彩排留下的 `rank-1` 會讓當天步驟 5 直接報錯（`--run-dir` 不能已存在）。

## USB

兩支 USB 都照這個結構放，路徑全用英文（GMAT 讀不了非 ASCII 路徑）：

```
ODC_Final/
  ranking/   排位賽：帶分數檔名的繳交件，例如 rank1_86.78_output_submit.txt、對應的 Report
  medal/     金／銅牌賽：主辦給的狀態檔、day/session.json 的備份、每回合手寫提交行的照片或抄本
  backup/    兩個 repo 的 git bundle（備機要用時 git clone 它；venv 必須在賽前先建好）
```

## 午休（11:45–13:00）

1. 確認排位賽上傳成功，USB `ODC_Final/ranking/` 裡有最後交的那份。
2. 關掉「排位賽」視窗。把 `ODC_Program/outputs/runs/` 整個複製到 USB `ODC_Final/ranking/`，賽後要用。
3. 打開「金牌賽」視窗，跑一次 `.venv/bin/python -m pytest -q` 確認環境正常。
4. 12:50 公布四強後，看是銅牌賽（13:00）還是金牌賽（14:30），照 CONTEST_DAY_FINAL 第二節準備。

## 封存

舊產物在 `~/Documents/Program/ODC_archive_pre1109/`（不進 git，說明在該資料夾的 README）。當天產生的東西賽後再整理，比賽中不要動。
