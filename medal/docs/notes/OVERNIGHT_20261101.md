# 夜間工作（2026-11-01）：把排位賽工具的優化搬進追逃工具

分支 `codex/port-ranking-opts`（從 master `70d8e5d` 開），三個 commit，沒有 push、沒有合併。實作由 Codex 做，Claude 出規格與驗收。
週額度到 70% 時收工。

## 先講結論

1. **排位賽那邊的大項優化幾乎都不能直接搬。** 拆棒、兩棒 oracle、星曆快取、primer 的前提都是「目標軌道固定、整條路線一次規劃」，
   追逃是雙方每回合都在動，沒有可以快取或預先拆的固定路線。盤點表（16 項）在本 session 的 Codex 研究輸出，重點摘在下面「盤點」一節。
2. **copilot 在 Mac（M4 MacBook Air）上已經夠快，沒有因為這次修改變得更快。** 暖機後 `advise --prune`：追者單發約 19 s、躲者單發約 12 s、
   追者 2 發約 25 s（4 workers），跟 E26 桌機數字同一個等級。決策內重用完全相同的掃描（`ODC_SCAN_REUSE`）結果逐位元相同，但端到端時間只差 −1%～+9%，在雜訊範圍內。
   詳見 [mac_advise_timing_20261101.md](mac_advise_timing_20261101.md)。
3. **太空船參數與曆元猜錯，在追逃賽局裡影響很小。** 這跟排位賽相反（排位賽偏 0.5–161 km）。原因是追逃每回合都重讀官方狀態，
   一個窗口只有 300 s；排位賽是一條十幾小時的開迴路。結果見下表。
4. GMAT 驗證補了撞地閘門：copilot `--verify` 與彩排報告現在會檢查雙方在 GMAT 軌跡上的最低地心半徑，判定「捕獲前撞地」，跟引擎同一個門檻。

## 敏感度實測（GMAT 全攝動 ranking_full，78 回合 × 15 變體，1,185 次 GMAT）

紀錄是 E22 同設定（ranking_like、lazy_evader 躲者對 rollout 追者）以純引擎重跑的新對局，不是原彩排的數值重現。

| 變體 | 單窗口末位置誤差 中位／最大 | 單窗口最近距離誤差最大 | 整場開迴路最近距離 |
|---|---:|---:|---:|
| 基準（850 kg、Cd 2.2、Cr 1.8、6／8 m²） | 4.8 m／17.5 m | 3.9 m | 21.53 km |
| 質量 ×0.5／×2 | 4.8 m／17.5 m | 3.9 m | 21.55／21.52 km |
| Cd 1.5／3.0 | 4.8 m／17.5 m | 3.9 m | 21.52／21.54 km |
| Cr 1.0／2.0 | 4.8 m／17.5 m | 3.9 m | 21.53／21.53 km |
| 阻力面積 ×0.5／×2 | 4.8 m／17.5 m | 3.9 m | 21.52／21.55 km |
| 輻射壓面積 ×0.5／×2 | 4.8 m／17.5 m | 3.9 m | 21.53／21.53 km |
| 曆元 +0.5／+30／+180 天 | 6.4／5.0／6.4 m（最大 16.3／13.4／16.4 m） | 4.8／6.6／4.8 m | 22.17／21.55／22.25 km |
| 全部取最壞方向 | 6.4 m／36.1 m | 4.9 m | 22.54 km |

- 單窗口誤差（現場每回合重讀狀態的情境）最大 36 m，跟捕獲半徑（公里級）比可以忽略；15 組全部 78/78 窗口成功、沒有撞地。
- 整場開迴路（不重讀狀態、誤差一路累積，上界情境）最近距離最多只變 1 km，曆元影響最大（日月位置），太空船參數幾乎沒影響。
- 這場的躲者最低高度約 176 km、追者約 445 km。

**限制**：只有一個幾何、一場對局；開迴路最近距離 21.5 km，離捕獲球還遠，沒測到「誤差剛好讓捕獲翻盤」的邊緣局。
E22 原彩排 lazy_evader 被逼到 8.9 km，邊際只剩幾公里，但單窗口誤差是公尺級，結論不變。
重跑：`.venv/bin/python tools/gmat_sensitivity.py --record <紀錄> --output-dir <目錄> --gmat-console <GmatConsole> --resume`（[操作說明](gmat_sensitivity.md)）。

## 盤點（Codex 唯讀研究，Claude 抽查過引用）

| 排位賽優化 | 追逃工具 | 判斷 |
|---|---|---|
| 星曆快取 | 雙方都會機動，整場快取不成立 | 只剩「同一狀態完全相同計算重用」，已做，沒加速 |
| 拆棒器 STM | 只有 `shoot_j2` 用到 3×3 差分，快速追者已關 shooting | 不值得 |
| 搜尋滑行 rtol 放寬 | 窗口 300 s、substep 60 s 與初始步長同級，放寬多半不減步數 | 不做 |
| `_osc_perigee` 雙曲線 bug | 追逃用通用近地點公式，沒有同型 bug；E25 已修 `orbit_survives` | 不用搬；`reaches_perigee` 新版不能單獨換（會破壞 `_radius_after_coast` 的前提） |
| Earth-safe 獨立閘門 | GMAT 驗證原本只判相對距離 | **已搬**（`tools/gmat_verify.py`） |
| BLAS 單執行緒 | 父行程與 worker 都沒限制 | **已做**（`runtime_threads.py`），只有重現性收益 |
| 多圈 Lambert | 已有 | 不用搬 |
| 全攝動 B 平面重瞄準 | 有逐回合 GMAT 真值，沒有 DC | 單窗口誤差只有公尺級，現在看不出需要 |
| 250 m/s 拆棒、兩棒 oracle、primer | 對應 ROADMAP「真正的兩發規劃」 | 不是速度問題，是新功能；規則公布前不做 |

## 這個分支改了什麼

- `24d707a`：`agents/scan_reuse.py`（`ODC_SCAN_REUSE`，預設開，設 0 退回）、`runtime_threads.py`、`tools/bench_advise.py`、`tools/audit_advise.py`、
  Mac 計時報告與三個計時局勢。
- `59927e8`：`tools/gmat_verify.py` 撞地閘門與參數／曆元注入（預設 script 逐字不變）、`tools/gmat_sensitivity.py`、copilot／彩排輸出。
- 測試：接上 GMAT 時 246 passed、0 skipped、1 failed。失敗的是 `test_rule_map.py::test_rule_ranges_sample_unchanged[seed0]`，
  改動前就失敗（期望值 …402、實得 …6929501406），應該是 Python 3.12 環境的 numpy 版本不同造成的末位差。

## Mac 環境

- 原本 `.python-version` 3.10 搭配的 scipy 1.15.3，在 macOS 27 載入時失敗（`_spropack` 的 `__thread_bss` dyld 錯誤）。
  `.venv` 改用 `UV_PYTHON=3.12 uv sync` 重建（lockfile 裡本來就有 3.12 用的 scipy 1.18.1），repo 檔案沒動。
- 這台 Mac 上的 Codex 沙盒跑不了 `uv run`（`~/.cache/uv` 權限問題），要直接用 `.venv/bin/python`。

## 待決定

- 要不要把這個分支合進 master、推到 GitHub，再讓 Corn 那邊 pull（Corn 上的 repo 是主要副本）。
- `ODC_SCAN_REUSE` 沒有帶來加速，又多一層快取。可以留著預設開（結果逐位元相同），也可以改成預設關或拿掉。我傾向拿掉，少一個當天會出事的地方。
- 手冊第二節第 11 列要不要加 Mac 門檻：標準 `--prune` 單發 T ≥ 30 s、2 發 T ≥ 40 s（報告的建議，還沒改進手冊）。
