# 11/09 決賽全天總覽

印出來帶去。每一場的細節照各自的手冊做，這頁只講哪一場用哪個資料夾、哪份手冊，以及兩場之間要做什麼。
前一晚的事看 [TONIGHT_20261109](TONIGHT_20261109.md)，出門前的電腦清理看 [CLEANUP_20261109](CLEANUP_20261109.md)。

## 時程（主辦 11-06、11-08 行前通知）

| 時間 | 項目 | 用什麼 |
|---|---|---|
| 08:30–09:00 | **報到**：台南會展中心，一進大門右轉、行李寄放處旁 | 證件正本、初賽識別證＋掛繩 |
| 09:00–10:15 | 開幕式 | |
| 10:15–10:45 | 就位（我們的安排，時間以現場為準）：拷題目檔、筆電開飛航模式給工作人員確認 | 見下方「排位賽電腦規定」 |
| 10:45–11:45 | **排位賽**（60 分鐘，九組） | 專案根目錄 |
| 11:45–12:50 | 休息 | |
| 12:50–13:00 | 公布四強 | |
| 13:00–14:30 | 銅牌賽（排位 3、4 名） | `medal/` |
| 14:30–16:00 | 金牌賽（排位 1、2 名） | `medal/` |
| 16:00–17:00 | 閉幕、頒獎 | |

**報到要帶**：每位隊員**附照片的身分證件正本**（身分證、健保卡、駕照或護照；沒帶不能入場）、初賽識別證和掛繩（掛繩不補發）。

## 排位賽電腦規定（11-08 行前通知之三＋同日「禁止生成式 AI」信）

- 可以自備筆電，或用主辦的桌電。桌電只裝 GMAT R2026a 和題目檔，**沒有 Python、沒有網路**，所以我們一定用自己的 Mac 求解。
- **題目檔只放在桌電上**，要自己用 USB 從桌電拷到 Mac。隨身碟一定要帶。
- 事先準備的程式可以用 USB 帶入（我們的程式已在 Mac 上）。
- **全程禁止網路與生成式 AI，含離線模型**。自備筆電開賽前要開飛航模式，工作人員確認後才開始；全程巡查，違規取消成績。
  Mac 上的 AI 程式（Claude、ChatGPT／Codex、Cursor、Gemini、Ollama、VS Code 的 Continue／Copilot）出門前就要全部關掉，做法在 [CLEANUP](CLEANUP_20261109.md)。
- 主辦信裡提到「排位賽規則（場地版）」，我們沒收到這份檔；最新的電子版是 [排位賽規則_20261104](../../rules/排位賽規則_20261104.pdf)。現場有紙本就以紙本為準。
- 金／銅牌賽本來就禁止網路與生成式 AI（[四強賽規則](../../rules/四強賽規則_20261029.pdf)），一樣用 Mac、一樣保持飛航模式。

## 兩場對照

| | 排位賽 | 金／銅牌賽 |
|---|---|---|
| 資料夾 | `~/Documents/Program/ODC_Program` | `~/Documents/Program/ODC_Program/medal` |
| 指令開頭 | `uv run python odc.py ...` | `.venv/bin/python copilot.py final ...` |
| 當天手冊 | [CONTEST_DAY](../ranking/CONTEST_DAY.md) | [CONTEST_DAY_FINAL](../../medal/CONTEST_DAY_FINAL.md) |
| 規則 PDF | [排位賽規則_20261104](../../rules/排位賽規則_20261104.pdf) | [四強賽規則_20261029](../../rules/四強賽規則_20261029.pdf) |
| 當天寫入 | `configs/local/ranking.json`、`outputs/runs/rank-*` | `medal/day/` |
| 交什麼 | GMAT Script＋Report（USB 帶去主辦桌電） | 每回合手寫一行 `角色, 回合, ΔvX, ΔvY, ΔvZ` |
| 力學 | 全攝動（GMAT 重驗） | 純二體 |

兩場的指令只在各自的資料夾裡跑：排位賽在專案根目錄，金／銅牌賽在 `medal/`（各有自己的 `.venv`，套件版本不同，不能混用）。
開兩個終端機視窗，分別命名「排位賽」和「金牌賽」（後者先 `cd medal`），**不要在同一個視窗裡 `cd` 來回切換**。

**GUI**：雙擊 `gui/start.command`（Windows：`gui\start.bat`）開決賽控制台（[說明](../../gui/README.md)），兩場都可以在裡面照步驟做，資料夾 GUI 會自己切換。
它跑的就是手冊上的指令，每個輸出框上方都印著完整指令；GUI 出問題就改照手冊在終端機跑。

## 開賽前確認

- 前一晚照 [TONIGHT_20261109](TONIGHT_20261109.md) 做完，最後一項是 [CLEANUP_20261109](CLEANUP_20261109.md) 清場。
- 確認三個地方是空的：`outputs/runs/`、`configs/local/` 裡只剩 `config.json`、`medal/day/` 不存在。
  彩排留下的 `rank-1` 會讓當天步驟 5 直接報錯（`--run-dir` 不能已存在）。CLEANUP 第四節的檢查指令一次看完。
- 10:15 就位後：Mac 插電、開飛航模式（Wi‑Fi、藍牙都關）、給工作人員看；桌電員拿 USB 去桌電拷題目檔。

## USB

兩支 USB 都照這個結構放，路徑全用英文（GMAT 讀不了非 ASCII 路徑）：

```
ODC_Final/
  problem/   排位賽題目檔：開賽時從主辦桌電拷來，再拷到 Mac 的 ~/ODC_problem/
  ranking/   排位賽：帶分數檔名的繳交件，例如 rank1_86.78_output_submit.txt、對應的 Report
  medal/     金／銅牌賽：主辦給的狀態檔、day/session.json 的備份、每回合手寫提交行的照片或抄本
  backup/    repo 的 git bundle（備機 git clone 它再跑 setup.sh；venv 要有網路才建得起來，必須賽前先建好）
```

`backup/` 的 bundle 在專案根目錄做：`git bundle create ODC_Program.bundle --all`（`medal/` 已經在同一個 repo 裡，一個 bundle 就夠）。
備機用法：`git clone ODC_Program.bundle ODC_Program`，再照 [SETUP](../SETUP.md) 跑 `setup.sh`。

## 午休（11:45–13:00）

1. 確認排位賽上傳成功，USB `ODC_Final/ranking/` 裡有最後交的那份。
2. 關掉「排位賽」視窗。把 `outputs/runs/` 整個複製到 USB `ODC_Final/ranking/`，賽後要用。
3. 打開「金牌賽」視窗，跑一次 `.venv/bin/python -m pytest -q` 確認環境正常。
4. 12:50 公布四強後，看是銅牌賽（13:00）還是金牌賽（14:30），照 CONTEST_DAY_FINAL 第二節準備。

## 封存

舊產物在 `~/Documents/Program/ODC_archive_pre1109/`（不進 git，說明在該資料夾的 README）。當天產生的東西賽後再整理，比賽中不要動。
