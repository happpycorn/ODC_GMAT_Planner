# 多發規則下放寬「中間軌道」存活檢查（清單第 1 項，2026-10-21）

## 1. 問題
`burns_per_turn > 1` 時，同窗口兩發之間的中間軌道其實只要撐過 `min_burn_gap_sec`（下一發能救）。
`LambertPursuer` 一律要求「推完這發純滑行撐到比賽結束」，部分解不過就減半（最多 8 次）或改救命推力，
所以不會用初賽官方範例解那招（兩發同向、中間近地點在地表下）。放寬後追者會不會變強？（E17「另一個限制」）

## 2. 改了什麼
- `agents/analytic.py`（**預設關，行為不變**）：
  - `next_burn_gap(game, side)`：這發之後本窗口還會不會再被問一發（照 `plan_turn` 的問法：每隔間隔問一次、
    最多 `burns_per_turn` 問、推零也用掉一問；取「已過秒數/間隔」與「已下發數」大者保守估計）。
  - `gap_burn_survives(...)`：放寬條件 = (a) 間隔這段弧最低點 ≥ 撞地高度 + 50 km（二體精確），引擎滑行也沒撞地；
    (b) 間隔後不推就安全或 `rescue_burn` 找得到一發。每一發都要確認 (b)，窗口最後一發一律嚴格。
    level 2 再加 (c)：間隔後一發（≤ 單發上限）補得完到同一個攔截目標，且補完的軌道過嚴格檢查（或在本窗口內抓到）。
  - `LambertPursuer(gap_survival=None|0|1|2)`，None = 環境變數 `ODC_GAP_SURVIVAL`（0/1/2，evaluate.py 子行程會繼承），
    預設 `GAP_SURVIVAL_DEFAULT = 0`。放寬只影響最後的「減半 → 救命」那段；掃描時排除不安全轉移軌道（TOF > 窗口）維持嚴格。
    放寬開著且目前在不安全的中間軌道上時，「滑行就會抓到 → 不推」要先確認滑完窗口真的先抓到。
- 新規則集 `configs/rulesets/symmetric_2burn.json`、`symmetric_3burn.json`（1500/3000 + 2/3 發、間隔 100 s）。
- 測試 `tests/test_gap_survival.py`（9 項）；報表 `reports/gap_survival_ab.md`（全部表格 + 診斷腳本）。

## 3. 設定
mixed 幾何；seed 1（24 局/配對）、seed 2 確認（24 局）、3 發（12 局）；追者 lambert / rollout × 躲者 dv / rollout；
5 worker、`nice 10`。勝負可重跑：
`ODC_GAP_SURVIVAL={0,1,2} uv run python evaluate.py --rules configs/rulesets/<規則>.json --scenario mixed --games 24 --seed 1 --workers 5 --pursuers "lambert_pursuer;rollout_pursuer" --evaders "dv_evader;rollout_evader"`
（決策層計數用 `reports/gap_survival_ab.md` 裡的診斷腳本，同一個 `tournament.play`，局面相同）。

## 4. 結果
**存活檢查多常咬到**（真實決策：Lambert 追者本身、rollout 追者的候選；窗口第 1 發；on1 下「嚴格不過、放寬通過」次數）：

| 規則 | Lambert 追者 | rollout 候選 |
|---|---|---|
| ranking_like_2burn（250/3000） | 6/1690（0.4%） | 4/6140（0.1%） |
| ranking_like_3burn | 1/817 | 4/2712 |
| symmetric_2burn（1500/3000） | 167/1997（8%） | 2231/7064（32%） |

放寬後的那發，下一發多半只能救命：250 m/s 規則 6 次放寬有 5 次接救命推力；1500 m/s 規則 Lambert 追者第 2 發救命 137 → 230 次（48 局）。

**追者勝率 off → on1**（[Wilson 95%]，配對 = 只有 off 抓到/只有 on1 抓到，雙尾符號檢定）：

| 規則 / seed | 追者 vs 躲者 | n | off | on1 | 配對 | p |
|---|---|---|---|---|---|---|
| ranking_like_2burn / 1 | lambert vs dv / rollout | 24 | 50% / 50% | 50% / 50% | 0/0、0/0 | 1 |
| | rollout vs dv | 24 | 83% [64–93] | 83% | 0/0 | 1 |
| | rollout vs rollout | 24 | 83% [64–93] | 79% [60–91] | 2/1 | 1 |
| ranking_like_3burn / 1 | rollout vs rollout | 12 | 100% | 92% | 1/0 | 1 |
| | 其他 3 個配對 | 12 | — | 相同 | 0/0 | 1 |
| symmetric_2burn / 1 | lambert vs dv / rollout | 24 | 8% / 12% | 8% / 12% | 0/0、0/0 | 1 |
| | rollout vs dv | 24 | 50% [31–69] | 50% | 1/1 | 1 |
| | rollout vs rollout | 24 | 71% [51–85] | 62% [43–79] | 3/1 | 0.62 |
| symmetric_2burn / **2** | lambert vs dv / rollout | 24 | 8% / 4% | 8% / 8% | 0/0、0/1 | 1 |
| | rollout vs dv | 24 | 33% [18–53] | 33% | 0/0 | 1 |
| | rollout vs rollout | 24 | 42% [24–61] | 46% [28–65] | 1/2 | 1 |

合計（全部規則/seed/配對）：只有 off 抓到 8 局、只有 on1 抓到 6 局，**p = 0.79**；rollout vs rollout 合計 7 對 4，p = 0.55。
level 2（要補得完）幾乎不觸發（symmetric_2burn seed 1：Lambert 0/1997、rollout 候選 8/7216），seed 1 兩組規則 8 個配對都與 off 0/0 不一致局。

**撞地**：on1 在 symmetric_2burn seed 1 出現 1 局追者撞地（rollout vs dv_evader 第 21 局，wild 幾何、最近 11,335 km 的必輸局）。
重播：rollout 選了放寬的 1500 m/s 候選，之後第 2 問與往後每回合都選零候選——所有候選推演都輸時分數平手
（−歷史最近距離/10），`RolloutPlanner` 取第一個候選＝零向量，所以從不救命。off 時同局是超時輸。

## 5. 另一組規則上的確認
大推力（symmetric_2burn）是放寬真的會觸發的地方，seed 1 與沒調參的 seed 2 都看不出差異（見上表）；250 m/s 規則幾乎不觸發。

## 6. 結論
- **看不出差異**：放寬在 250 m/s 多發下幾乎不觸發（≤ 0.4% 的決策）；在 1500 m/s 多發下常觸發（Lambert 8%、rollout 候選 32%），
  但勝率沒有變（合計 8 對 6，p = 0.79）。原因：LambertPursuer 的目標是「單發最省 Δv 的轉移」，不會規劃兩發機動，
  放寬只讓第 1 發推更大，第 2 發多半得救命；要求第 2 發補得完（level 2）則幾乎沒有符合的情況。
- **預設關**（`GAP_SURVIVAL_DEFAULT = 0`）：沒有增益，而且 level 1 的安全保證（下一問救得回來）只在下一發由
  LambertPursuer 決定時成立；rollout 追者在必輸局會停在撞地軌道上（1 局）。開關保留給之後的兩發規劃實驗。

## 7. 限制、沒做的事、建議下一步
- 沒跑：escape_evader、強化版 rollout 追者（E16）、躲者側放寬（DvEvader/EscapeEvader）、symmetric_3burn、ranking_like_3burn 只有 12 局。
- 24 局/配對的區間約 ±20 個百分點；只能說沒有大效果。
- 若要用官方範例那招，需要的是**兩發規劃**（候選直接列舉 (第 1 發, 第 2 發) 或 Lambert 目標選「兩發內補得完、TOF 短」的解），
  不是只放寬檢查；那才是下一步。
- 若之後開放寬：`agents/rollout.py` 應在平手時偏好安全候選（或排除讓窗口結束軌道不安全的候選），
  copilot 的「推完安全」顯示（`orbit_survives`）對多發計畫的第 1 發會顯示 False，應改成看窗口結束時的軌道。

## 8. 逐位元檢查
同一個 worktree、同一份 numba 快取，改前 vs 最終程式，逐局比 outcome、t_end、min_dist_km、used_pursuer_mps、used_evader_mps：
- 開關未設定（= 關）：default 48/48、ranking_like 48/48、ranking_like_2burn 36/36、ranking_like_3burn 24/24 局完全相同。
- 開關開（單發規則）：default（level 2）48/48、ranking_like（level 1）48/48 完全相同。
- 指令：`evaluate.py --rules {default,ranking_like.json} --games 8 --seed 0`、`{2burn,3burn} --games 6 --seed 0`，
  追者 lambert/rollout × 躲者 dv/rollout/escape（3burn 不含 escape）。pytest 85 passed（原 76 + 新 9）。
