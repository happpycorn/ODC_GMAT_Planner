# 軌道攔截設計賽：任務規劃工具

TASA／淡江大學「第一屆軌道設計競賽」用的任務規劃工具。我方太空船 B 以多次瞬時脈衝機動，在 T_max 內攔截只受重力的太空船 A；
工具用 L-SHADE 搜尋路線、把超標的棒拆成合法多棒解，再產生 GMAT 腳本並用 GMAT 驗證。初賽第二名，下一場是 2026-11-09 決賽的排位賽。

| 想做什麼 | 看哪裡 |
|---|---|
| **比賽當天照著做** | [docs/ranking/CONTEST_DAY.md](docs/ranking/CONTEST_DAY.md) |
| 目前狀態、未完成的事 | [STATUS.md](STATUS.md) |
| 每個子命令的選項與範例 | [docs/CLI.md](docs/CLI.md) |
| 程式在哪個檔案、呼叫順序 | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| 物理模型、搜尋、計分的原理 | [docs/METHODOLOGY.md](docs/METHODOLOGY.md) |
| 所有文件的導覽 | [docs/README.md](docs/README.md) |

---

## 安裝

需要 Python 3.12 以上，由 `uv` 自動下載，不用自己裝。

```bash
pip install uv
```

```bash
uv sync
```

**每次 `git pull` 之後都跑一次 `uv sync`**。`uv run` 會補缺的套件，但不會刪多的；殘留套件曾經掩蓋過漏列的依賴（`tqdm`），換新機器才爆。

GMAT 要另外裝（本機是 GMAT R2026a）。工具只用無頭的 `GmatConsole`，路徑的優先順序是：
`--gmat-console` 參數 > 設定檔的 `local.gmat_console_path` > [odc/config/defaults.py](odc/config/defaults.py) 寫死的備援值（作者 Mac 的路徑）。

所有指令都要在專案根目錄執行，入口只有一個：

```bash
uv run python odc.py --help
```

---

## 快速試跑

```bash
uv run python odc.py new-config trial --from hyperbolic_smoke
```

```bash
uv run python odc.py solve configs/local/trial.json --no-gmat
```

`new-config` 從 `configs/shared/` 複製一份到 `configs/local/`（不覆蓋已存在的檔，加 `--gmat-console <路徑>` 會一起寫進 `local`）。
`--no-gmat` 跳過 GMAT，只看 Python 端結果。有裝 GMAT 就拿掉它，會自動做無頭驗證。

不給設定檔時用 `configs/local/config.json`；那個檔不存在會自動產生**初賽格式的範例**（單棒 1500 m/s、沒有總 Δv 上限），排位賽不要用它，改用 `new-config`。

---

## 設定檔

`configs/shared/` 跟著 Git，是可以重現的共用情境；`configs/local/` 被 gitignore，放自己的設定與當天題目。
共用情境的用途與參數見 [SCENARIOS.md](docs/SCENARIOS.md)。排位賽範本是 [configs/shared/ranking_round.json](configs/shared/ranking_round.json)。

設定檔分五塊，依「誰決定這個數字」區分：

| 區塊 | 內容 | 誰決定 |
|---|---|---|
| `orbit_A`、`orbit_B` | 六根數 `SMA, ECC, INC, RAAN, AOP, TA`（km、度）。雙曲線的 SMA 是負的、ECC > 1 | 題目 |
| `rules` | 規則數字與計分參數 | 主辦單位，不能改 |
| `strategy` | 力學模型、命中容差、拆棒與 oracle 等任務設計選項 | 我們 |
| `optimization` | 搜尋預算與種子，只影響找不找得到好解、要跑多久 | 我們 |
| `local`（選填） | 這台機器的 `gmat_console_path` | 各機器自己 |

### rules

| 欄位 | 排位賽 | 說明 |
|---|---|---|
| `MAX_DV_MPS` | 250 | 單棒上限，超過 250 + 10⁻⁵ m/s 失格（初賽是 1500、超標扣分） |
| `MAX_TOTAL_DV_MPS` | 3000 | 總 Δv 上限，超過失格；不填等於沒有上限（初賽） |
| `MIN_MANEUVER_INTERVAL_SEC` | 100 | 兩棒最小間隔，違規每次扣 10 分 |
| `T_MAX_SEC` | 開賽算 | 任務時間上限（秒，從 epoch 起算）。A 是雙曲線時必填，用 `odc.py tmax` 由任務邊界算 |
| `T_MAX_PERIOD_MULTIPLE` | 不用 | 初賽用：沒給 `T_MAX_SEC` 時 T_max = 倍數 × A 週期 |
| `k_t`、`C_t`、`k_v`、`C_v` | 開賽公布 | 計分參數，工具用秒與 m/s；用 `odc.py scoring` 換單位並驗算 |

計分：`50·exp(−(Δr_min−5)/100) + 25/(1+e^{k_t(T−C_t)}) + 25/(1+e^{k_v(ΔV−C_v)}) − 罰分`，Δr ≤ 5 km 距離項拿滿。
規則全文與初賽差異見 [RANKING_ROUND_RULES](docs/ranking/RANKING_ROUND_RULES_20261006.md)。

### optimization

| 欄位 | 排位賽範本 | 說明 |
|---|---|---|
| `MAX_BURNS` | `[1, 2]` | 拆棒**前**的路線棒數。DE 先找少棒路線，拆棒器再拆成合法多棒，不要照能量下限放大 |
| `MAXITER`、`POPSIZE` | 1000、20 | 搜尋代數與每維族群倍數（族群 = 維度 × POPSIZE）。要省時先降代數，不要加大 POPSIZE |
| `NUM_THREADS` | -1 | 每個燃燒案例的執行緒數；≤ 0 自動用「核心數 ÷ 案例數」 |
| `SEED` | `null` | 設整數可重現，但**搜尋會退回單執行緒**；`null` 用多執行緒換速度 |
| `EARLY_STOP_ENABLED` | 不填（關） | 開了才用 `MAX_EARLY_STOP`、`TOL`；消融顯示會掉分（[報告](docs/research/EARLY_STOP_ABLATION_20260929.md)） |

### strategy

全部選填，下表是程式預設值；排位賽範本另開 `SPLIT_LEADING`、`ORACLE_TWOBURN`。

| 欄位 | 預設 | 說明 |
|---|---|---|
| `GRAVITY_DEGREE` | 2（範本 4） | Python 與 GMAT 同步套用的 zonal 階數：0 點質量、2–4 為 J2–J4。排位賽設計用 4，官方驗證的全攝動靠重瞄準補 |
| `MISS_TOLERANCE_KM` | 5 | 末棒 Lambert 可瞄在 A 周圍多遠內的最省油點。實際瞄約 3.5 km，留 1.5 km 給攝動 |
| `AUTO_SPLIT_LEGALIZE` | `true` | 贏家有棒超標時自動拆成合法多棒 |
| `MAX_DV_MARGIN_MPS` | 2.0 | 拆棒時每棒上限往內縮多少（250 → 248 m/s） |
| `SPLIT_LEADING` | `false` | 拆棒階段也拆超標的前導棒；可拆上限 = `SPLIT_AWARE_MAX_FACTOR`（預設 3）× 單棒上限 |
| `ORACLE_TWOBURN` | `false` | 背景跑兩棒網格 oracle，前 `ORACLE_TWOBURN_K`（10）名跟 DE 贏家一起拆棒比較；需要 `SPLIT_LEADING`。網格加拆棒的牆鐘上限 `ORACLE_TWOBURN_WALL_SEC`（600 s） |
| `SPLIT_AWARE_TERMINAL` | `true` | 終端棒超標但拆得掉（≤ 5 倍）時，搜尋改用拆後估分；拆不掉會自動用 `false` 重搜一輪 |
| `SPLIT_JACOBIAN` | `"stm"` | 拆棒 NLP 的 Jacobian；`"fd"` 退回有限差分 |
| `SPLIT_WORKERS` | 3 | 拆棒行程數 |
| `SPLIT_MULTISTART` | `[0, 0.75, 1]` | 拆棒多起點；`null` 退回單起點 |
| `SPLIT_PRUNE_REOPT_MPS` | 1.0 | 剔除小於此值的空棒後重最佳化 |
| `SPLIT_WALL_BUDGET_SEC` | 600 | 拆棒牆鐘軟上限，到期交目前最好的合法解（觸發時不可逐位元重現） |
| `REVS_ENSEMBLE` | `true` | REVS=0 與 REVS=`LAMBERT_MAX_REVS`（4）各跑一趟搜尋取好的；關掉約省 37% CPU，但有情境掉 1.7 分（[排程驗證](docs/research/REVS_SCHEDULING_20260929.md)） |
| `SEARCH_COAST_RTOL` | `1e-12` | 搜尋時滑行傳播容差；`1e-9` 較快，贏家仍以 `1e-12` 重算 |
| `TIEBREAK_POLISH` | `true` | 不掉分的前提下把 d_min 壓小（同分先比 d_min） |
| `TIEBREAK_SCORE_EPS` | `1e-9` | 分差多少內算同分；設 0.005 等於賭官方四捨五入到小數兩位 |
| `FORCE_MODEL` | `"contest_prelim"` | 一般流程 GMAT 腳本的力學模型（與 Python 對齊）。全攝動交給 `odc.py retarget`，不建議改成 `"ranking_full"` |
| `GMAT_SPACECRAFT`、`GMAT_SPACECRAFT_A`、`GMAT_EPOCH`、`GMAT_EPOCH_FORMAT` | 850 kg、Cd 2.2、Cr 1.8、阻力 6 m²、SRP 8 m²；`"21545"` TAIModJulian | 只影響 GMAT 端。官方公布後填進當天設定；重瞄準時 `--config` 給的這幾項會蓋過存檔 |

---

## 執行

常用子命令（完整選項見 [docs/CLI.md](docs/CLI.md) 或 `--help`）：

| 子命令 | 做什麼 |
|---|---|
| `new-config <名稱> [--from <共用情境>]` | 建本機設定（預設從 `ranking_round` 複製） |
| `solve [設定檔]` | 搜尋 → 拆棒 → 存 `mission.json` → 產腳本 → GMAT 驗證 |
| `retarget <mission.json>` | GMAT 全攝動 B 平面重瞄準，通過才產全攝動繳交腳本（排位賽必做） |
| `verify <腳本>` | 用 GMAT 獨立重驗一份腳本 |
| `resume <winner_presplit_seed*.json>` | 從拆棒前存檔重跑拆棒與後續（改拆棒器時用） |
| `export <mission.json>` | 從已存方案重產腳本、重跑 GMAT，不重新求解 |
| `tmax`、`scoring` | 比賽當天算 T_max、換計分參數單位 |
| `check`、`feasibility`、`sweep-burns` | 檢查情境、估能量下限、掃燃燒次數 |
| `test [--quick]` | 跑回歸測試 |
| `sweep`、`outputs` | 批次實驗、本機成果索引 |

### 分段執行

`solve` 預設一次跑完。加 `--stop-after solve|export|verify` 可停在某一階段，之後用存檔接著跑，不必重新搜尋：

```bash
uv run python odc.py solve configs/local/x.json --stop-after solve --run-dir outputs/runs/x
uv run python odc.py export outputs/runs/x/mission.json --run-dir outputs/runs/x-export
uv run python odc.py retarget outputs/runs/x/mission.json --config configs/local/x.json --run-dir outputs/runs/x-rt
uv run python odc.py verify outputs/runs/x-rt/output_submit.txt --config configs/local/x.json --run-dir outputs/runs/x-verify
```

- `--run-dir` 必須是不存在的目錄；省略時自動建 `outputs/runs/<唯一識別碼>/`。
- 重播用存檔裡的軌道、規則與設定；另給 `--config` 時只讀 `local.gmat_console_path`（重瞄準另外讀太空船參數與曆元）。
- 存檔記錄格式版本與 21 個物理相關來源檔的雜湊；那些檔改過後，`mission.json` 會被拒絕重用，要重新求解或從 `resume` 接（[版本驗證](docs/ARCHITECTURE.md#版本驗證)）。
- `-q` 終端機只印警告，完整日誌照樣寫進執行目錄的 `run.log`；`-v` 印全部細節。

### 全攝動重瞄準（排位賽）

Python 只算 J2–J4，官方驗證開 EGM96 20×20、潮汐、阻力、日月、SRP、相對論。同一組脈衝放進全攝動，短任務偏 0.5–1.3 km，
22.6 h 的 hyper_far 偏上百 km（[攝動落差](docs/research/PERTURBATION_GAP_20261019.md)）。`odc.py retarget` 的做法：

1. 在 GMAT 全攝動下用 DifferentialCorrector 改一棒（預設最後一棒；`--retarget-burn N` 指定，0 起算，同腳本 `BurnB<N>`），
   **只消掉垂直於相對速度的兩個 B 平面分量**。不用定時位置對齊：那在 hyper_far 會多花 272 m/s、末棒 361 m/s 直接失格。
2. 重新判定 d_min ≤ 5 km、攔截前 Earth-safe、最近點 ≤ T_max、單棒與總 Δv、機動間隔。
3. 全部通過才寫全攝動、全固定燃燒的 `output_submit.txt`，再用 GMAT 跑一次確認；`retarget.json` 的 `status` 是 `accepted`。
4. 任一步不過就保留原方案、不產繳交腳本，終端機列出原因與每棒餘裕，可改用餘裕大的棒重試。

---

## 輸出

每次執行一個目錄（`outputs/runs/<id>/` 或 `--run-dir`），不覆寫舊結果。`outputs/` 不進版控，值得留的解複製到 [docs/solutions/](docs/solutions/README.md)。

| 檔案 | 用途 |
|---|---|
| `mission.json` | 最終 Python 方案；`mission_info` 有 `score`、`disqualified`、`num_burns`、`total_dv_mps`、`miss_km`、`T_team` |
| `winner_presplit_seed*.json` | 拆棒前贏家，給 `resume` 用 |
| `mission_seed*.json`、`oracle_candidates_seed*.json` | 各種子拆後方案、oracle 候選 |
| `no_legal_route.json` | 找不到合法路線時（結束碼 3）最接近的候選與超標量 |
| `output.txt` | 一般 GMAT 腳本，末棒由 DC 修正 |
| `output_submit.txt` | 固定燃燒版（不含求解器）。重瞄準目錄裡的才是排位賽繳交版 |
| `gmat_dc/`、`gmat_fixed/`、`gmat/`、`gmat_retarget/` | 各次 GMAT 執行的腳本副本、報表、stdout/stderr、`verification.json` |
| `retarget.json` | 重瞄準結果：`accepted`／`rejected` 與原因、前後的棒、全攝動 d_min、合法性、官方分數估計、太空船參數 |
| `run.json` | 來源鏈、程式版本、執行狀態、`elapsed_sec` |
| `run.log`、`run_history.jsonl` | 完整日誌；產腳本與驗證階段的成績 |

`run.json` 的 `status=completed` 只表示要求的階段跑完，不代表可以交。能不能交看 `mission.json` 的 `disqualified` 與 `retarget.json` 的 `status`。
重瞄準不通過時沒有 `output_submit.txt`（固定版驗證沒過時改名 `output_submit_REJECTED.txt`）。

```bash
uv run python odc.py outputs index
```

重建 `outputs/INDEX.md`，列出本機所有 run 與驗證狀態。

---

## 測試

```bash
uv run python odc.py test --quick -q
```

不需要 pytest；`--quick` 跳過慢測試，不加就全跑（含 GMAT 端到端）。也可以只跑檔名含某字串的測試，例如 `odc.py test tiebreak`。

---

## 部署到新電腦

1. 裝 `uv`、`git clone https://github.com/happpycorn/ODC_GMAT_Planner.git`、`uv sync`（第一次要網路，約 1 GB）。
2. 另裝 GMAT，用 `new-config ... --gmat-console <路徑>` 或 `--gmat-console` 參數指過去。
3. `configs/local/` 不會跟著 clone，需要的設定另外複製，或照 [SCENARIOS.md](docs/SCENARIOS.md) 重建。
4. 先跑 `odc.py test --quick -q` 和上面的快速試跑，再試 GMAT。

主辦單位的電腦不需要這套工具：繳交的 `output_submit.txt` 是純文字 GMAT 腳本，不含求解器，只要那台有 GMAT 就能直接開來跑。
規則附則寫「所有結果以主辦單位驗證程式為準」，所以交之前要在那台機器上跑一次確認結果一致。
