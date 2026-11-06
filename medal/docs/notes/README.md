# 研究筆記（docs/notes/）

每個研究子任務把結果寫在這裡一個檔案（`docs/notes/<主題>.md`），由主 session 驗收後整合進
`docs/EXPERIMENTS.md`（E20 之後的編號）、`ROADMAP.md`、`CONTEST_DAY_FINAL.md`。子任務不要直接改那三份文件。

每份筆記的格式：

1. **問題**：要回答什麼、為什麼對 11/9 當天有用。
2. **改了什麼**：程式（檔案、預設值有沒有變）、新規則集、新工具。
3. **設定**：規則集、幾何家族、seed、局數、worker 數、指令（可重跑）。
4. **結果**：表格附局數 n 與 95% 區間（`evaluation.tournament.wilson`）；同一批幾何的比較附逐局配對與符號檢定
   （`tools/paired_compare.py`、`evaluation.stats`）。
5. **另一組規則上的確認**：結論在另一組假設規則（對稱 1500/3000、多發 2–3 發等）上是否仍成立。
6. **結論**：不顯著就照實寫「看不出差異」，不要硬下結論。
7. **限制、沒做的事、建議下一步**。
8. **逐位元檢查**（改到 `game/`、`agents/`、`physics/` 時）：預設規則（burns_per_turn=1）下同一個 worktree、
   同一份 numba 快取的 before/after 比對結果。

報表（`reports/*.md`）照舊進 git；`reports/*.jsonl`、`*.log` 不進 git（.gitignore），筆記裡要引用的數字直接寫進筆記。
