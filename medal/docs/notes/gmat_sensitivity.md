# GMAT 撞地閘門與參數敏感度掃描

`tools/gmat_verify.py` 的 `analyze_dense` 以引擎的 `physics.RE_VAL + rules.crash_altitude_km` 為撞地半徑，沒有額外半徑容差。相對位置與雙方地心位置共用每段 64 等分的三次 Hermite 內插，再精修最低點與第一次觸界時間。判定使用 `≤`，與 `physics.coast.coast_pair` 相同；同時觸界時撞地優先，雙方同時撞地時追者優先。事件時間精修的同時判定精度為 10 ns。

最低半徑與最近距離涵蓋完整 GMAT 輸出，因此可能出現在終局事件之後。`radii[side]` 保存 `min_radius_km`、`t_min_sec`、`t_crossing_sec`、`crossed_crash_radius`；`t_enter_capture_sec` 是幾何觸球時間，`t_capture_candidate_sec` 依 `capture_mode` 判定，`t_capture_sec` 只有捕獲先發生才有值。`earth_safe`／`crash_before_capture` 用來判斷捕獲前撞地，`first_event`、`t_event_sec`、`event_order` 保存順序。捕獲後觸地仍回報半徑，但不判撞地。端點模式只在真正窗口末判捕獲，機動中途的報表列不算窗口末。

`verify_game`、`gmat_truth` 都取得密集軌跡；`gmat_step(..., with_analysis=True)` 回傳 `(state, analysis)`，時間為整場絕對秒數。copilot `advise --gmat ... --verify` 與彩排終端／Markdown 都印出雙方最低半徑及閘門判定；彩排遇到 GMAT 終局事件後停止決策。報表缺少起末時刻、時間倒退或密集間隔超過 60 秒時拒絕判安全。

`game_to_script` 新增關鍵字參數 `spacecraft`（雙方共用的部分欄位覆寫）及 `epoch_tai_mjd`；既有預設腳本文字不變。密集驗證的執行副本用 `instrument_dense_script` 補上初末、窗口末、脈衝前後取樣，避免跨速度跳變內插。預設腳本文字的 8 組 SHA-256 來自修改前程式，測試涵蓋 zonal／ranking_full、有無密集報表、零／非零任務時間偏移。

## 紀錄來源

E22／E26 只有 `reports/e22_rehearsal_full_lazy_evader_vs_rollout.md`、`reports/e26_rehearsal_full_lazy_evader_2burn.md` 的摘要，沒有 ECI 脈衝向量與窗口起始狀態，不能直接重播。新的 `dress_rehearsal.py --record-out PATH` 保存 `odc_gmat_replay_v1` JSON，內容包括規則、初始雙船 `(r, v)`、T_max、Game.history 全欄位與每回合 `state_before`；後者保留彩排當下 GMAT resync 後的實際起點。

2026-11-01 在沙盒內以 `gmat_sensitivity.py --generate-record ... --preset e22` 產生純引擎新對局：`ranking_like`、`near_coplanar`、seed 0、`rollout_pursuer` 對 `lazy_evader`；E22 的 copilot ★ 每回合都選 lazy_evader，所以直接使用同一策略。E22 發生在 E25 生存判定修正前，產生器暫設 `ODC_STRICT_SURVIVAL=0`，完成後還原環境；E26 預設則使用修正後的 1 與兩發規則。

這次新對局為 78 回合、23323.464699 秒、timeout、引擎最近 21.670090 km。它沒有逐回合 GMAT resync，**不是 E22 原彩排最近 8.876 km 的數值重現**。這個紀錄用來驗證掃描工具；針對原彩排餘裕的結論，應先在沙盒外用 `--record-out` 保存新的全攝動彩排再掃描。

產物放在已有忽略規則的 `runs/gmat_sensitivity_e22_20261101/`：

- `replay.json`：完整可重播新對局。
- `scripts/<variant>/window_*.script`、`open_loop.script`：共 1185 份 GMAT 腳本。
- `plan.json`：有效參數、引擎預測、腳本 SHA-256、每次 GMAT 完整命令與工作目錄。
- `results.md`、`results.json`：目前為 dry-run，數值欄位待測，GMAT 執行次數為 0。

## 量測與變體

單窗口量測對每回合從該紀錄的 `state_before` 重起，施加原 ECI 向量，以相同窗口長度比較引擎與 GMAT `ranking_full`。它記錄雙方窗口末位置誤差、窗口內最近距離的有號誤差及絕對誤差，避免混入之前回合的累積偏差。引擎預測固定重播已記錄機動，不重新決策、裁切燃料或因事件提早停止。

整場開迴路從初始狀態重播相同機動序列，不重設狀態，記錄最近距離、幾何進球、有效捕獲與撞地。若引擎最後一回合因捕獲截斷，就像 `gmat_truth` 一樣補到原窗口末或 T_max；撞地窗口不補。它是誤差累積的情境，不能當成現場每回合重新讀狀態的誤差。

預設 15 組：基準 850 kg／Cd 2.2／Cr 1.8／DragArea 6 m²／SRPArea 8 m²／TAIModJulian 21545；質量 ×0.5、×2；Cd 1.5、3.0；Cr 1.0、2.0；兩種面積各自 ×0.5、×2；曆元 +0.5、+30、+180 天；一組最壞方向組合。曆元偏移與窗口起始秒數相加，雙方都使用相同有效參數。

最壞方向組合在單因子實測後，各參數選取「單窗口最大末位置誤差」最大的方向，同分再比較最近距離絕對誤差。它不是非線性參數組合的全域最壞搜尋。dry-run 尚無實測，只產生小質量／大係數與面積／+180 天的明確標示預覽；實跑完成單因子後重寫這組腳本與計畫，JSON 保存 `selected` 所選方向。若某單因子的窗口失敗，不能宣稱已選出實測最壞方向；不使用不完整掃描補猜。

`--spacecraft-json PATH` 可部分覆寫基準，`--epoch-tai-mjd VALUE` 可指定基準曆元，`--variants PATH` 可替換單因子清單，例如：

```json
[
  {"name": "mass_600", "spacecraft": {"DryMass": 600}},
  {"name": "epoch_plus_2d", "epoch_offset_days": 2}
]
```

工具會補上基準與自動組合。若在清單提供名為 `combined_worst` 的明確參數物件，就照該物件執行，不自動選方向。`spacecraft` 只接受 `DryMass`、`Cd`、`Cr`、`DragArea`、`SRPArea` 的有限正數。路徑與變體名稱須能寫成 GMAT 的 ASCII 腳本。

## 沙盒外執行

以下從已保存紀錄執行，不重新產生機動，也不需要在 shell 先切換工作目錄：

```sh
/Users/corn/Documents/Program/ODC_GMAT_DRL/.venv/bin/python /Users/corn/Documents/Program/ODC_GMAT_DRL/tools/gmat_sensitivity.py \
  --record /Users/corn/Documents/Program/ODC_GMAT_DRL/runs/gmat_sensitivity_e22_20261101/replay.json \
  --output-dir /Users/corn/Documents/Program/ODC_GMAT_DRL/runs/gmat_sensitivity_e22_20261101 \
  --gmat-console '/Users/corn/Documents/GMAT R2026a/bin/GmatConsole' \
  --resume
```

加 `--dry-run` 可重新產生計畫而不啟動 GMAT。78 回合 × 15 變體需要 1170 次單窗口與 15 次整場呼叫，共 **1185 次**。按 E18/E22 每窗口約 0.7 秒估計，單窗口約 13.7 分鐘，加整場重播後約 **14–28 分鐘**；這不是時間上限，Python 分析、啟動、阻力造成的步長縮小與每次預設 600 秒逾時都會影響時間。

每次 GMAT 在傳入的 console 所在 `bin` 目錄啟動，保留 Mac symlink 路徑，避免工作目錄跟著解析到 `.app/Contents/MacOS`。腳本、stdout、stderr、密集報表及 `.run.json` 保存於各變體目錄。`--resume` 只採用 SHA-256 相同且報表完整的成功呼叫；一般重跑會先清除該次舊報表。每完成一個變體更新 Markdown／JSON，失敗保留原因並以非零退出碼回報。

如果要重新取得全攝動彩排紀錄，在 repo 工作目錄執行：

```sh
.venv/bin/python tools/dress_rehearsal.py --role evader --opponent rollout_pursuer \
  --rules configs/rulesets/ranking_like.json --scenario near_coplanar --seed 0 \
  --force-model ranking_full --gmat-console '/Users/corn/Documents/GMAT R2026a/bin/GmatConsole' \
  --record-out runs/e22_new_full_replay.json --name e22_new_full
```

接著把掃描命令的 `--record` 換成新紀錄、`--output-dir` 換成新資料夾。此處尚未執行 GMAT，沒有參數敏感度的實測結論。

本次沙盒驗證：新增 34 個純 Python 測試全數通過；`.venv/bin/python -m pytest -q` 為 234 通過、12 略過，唯一失敗是已知的 `tests/test_rule_map.py::test_rule_ranges_sample_unchanged[seed0-None-want0]`（436.3546929501406 與預期 436.3546929501402 的浮點差異）。整批 1185 份腳本的參數、曆元、SHA-256 皆已檢查；其中基準 79 份與修改前產生器套相同取樣插樁後逐字相同，結果存於產物目錄的 `audit.json`。
