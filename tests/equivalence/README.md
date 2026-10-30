# 重構等價驗證

從專案根目錄執行，工具只使用標準函式庫，所有計算均由獨立子行程執行。
`legacy` 用於階段 0、1；階段 2 移除舊入口後，執行時請使用 `--entry odc`。

```bash
uv run python tests/equivalence/run_equivalence.py --entry legacy --repeat 2 --out outputs/equivalence/baseline
uv run python tests/equivalence/run_equivalence.py --entry legacy --out outputs/equivalence/baseline --compare outputs/equivalence/baseline
uv run python tests/equivalence/run_equivalence.py --entry odc --compare outputs/equivalence/baseline
```

`--cases smoke_full from_mission` 可只選部分案例；`from_mission` 自動先執行自己的 `smoke_full`，避免引用重構前的版本雜湊。
輸出目錄已存在時拒絕覆寫；唯一例外是 `--out` 與 `--compare` 指向同一基準，此時只重讀已存結果進行自我比對。

案例涵蓋完整管線、初賽拆棒、排位賽 oracle spawn 與拆棒 fork、雙曲線、winner 與 mission 重播、四支文字工具及 sweep dry-run。
所有子行程固定 `OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMBA_NUM_THREADS=1 PYTHONHASHSEED=0`，並使用全新的暫存 Numba 快取。
較重案例以輸出目錄中的設定副本降低搜尋預算；不改原始情境、fixture 或 checkpoint。
排位賽保留兩個拆棒起點及兩個工作行程，牆鐘預算為 3600 秒，避免把機器速度當成演算法輸入。

`equivalence_results.json` 保存指令、結束碼、牆鐘秒數、產物清單、正規化快照及腳本原始位元組。
每次執行另外保存 stdout、stderr、設定副本及完整管線產物；報告列出實際排除的 JSON 鍵。
比對保留所有燃燒、滑行、mission_info 數值；GMAT 腳本逐位元比較。工具 stdout 只移除含路徑或執行時間的整行。
牆鐘差異超過 30% 僅標記，數值、腳本、退出碼或必要路徑覆蓋不同則失敗。
重複執行不一致會標為「基準本身不穩定」並列第一個差異，不自動放寬容忍度。

GMAT 端到端測試另由使用者在外部執行；一般回歸紀錄保存於基準目錄的 `regression.txt`。
