# hyperbolic_smoke 種子 4：A 拿到 3 棒 86.7864，C 只到 4 棒 86.7847

**結論：兩個因素都有，但主因是種子運氣。** 3 棒 86.7864 在臂 A 的 10 顆種子裡只出現 1 次（種子 4），本身就是少見的盆地。就在種子 4 這一顆上，C 拿不到它是 SPLIT_LEADING 造成的，oracle 沒有影響（只開 SPLIT_LEADING 的 SL 結果跟 C 完全相同）。SPLIT_LEADING 改變了 primer 重搜裡 DE 的目標函數，3 棒解從頭到尾沒被產生出來，所以不存在「在比較中輸給誰」的情況。

## 1. 讀 log（四臂比較已有的 run，未另外跑）

資料來源：`outputs/sweeps/phase2_arm{A,C}/runs/hyperbolic_smoke__base__s4/` 和 `smoke10_SL/runs/hyperbolic_smoke__base__s4/`（run.log、winner_presplit、mission.json）。A 用 14b7849，C 和 SL 用 ef87f65；A 的 SPLIT_LEADING 是關的，所以兩個 commit 對 A 逐位元相同。

**A 的 86.7864（3 棒）來自 primer 重搜。**
- 第一輪搜尋：2 棒贏家（REVS=4）搜尋分數 76.2713，拆後估計 86.2713。
- primer 診斷要插一棒（max|p|=1.744），於是開 SPLIT_AWARE、加插棒種子，以 3 棒重搜。
- 重搜贏家（REVS=0）：76.4464，拆後估計 86.4464。拆前 3 棒為 181.5／226.6／281.5 m/s，只有終端棒超標。
- 「primer 重搜勝出 76.2713 → 76.4464」後拆棒：多起點提前 100 s，拆後是合法 86.7864（3 棒、639 m/s）。
- 沒有走 C4 退路。

**C 在 primer 重搜裡才開始跟 A 分岔。**
- 第一輪搜尋跟 A 逐位元相同：1 棒 −85.2485；2 棒 REVS=4 −86.2942、REVS=0 −86.0901；贏家都是 REVS=4、76.2713。
- primer 有觸發，診斷也相同（max|p|=1.744，以 3 棒重搜）。
- 3 棒重搜的 DE 目標值不同：

  | 臂 | REVS=0 | REVS=4 |
  |---|---|---|
  | A | −86.2806 | −86.0950 |
  | C | −86.3512 | −86.1916 |

- C 的重搜贏家是 REVS=0：搜尋分數 66.6719（2 棒超標），拆後估計 86.6377，「前導棒 1 發、終端棒可拆」。
- 前導棒等分成 2 段後拆棒，拆後是 86.7847（4 棒、639 m/s）。
- 「primer 重搜勝出 76.2713 → 66.6719」，比較用的是 `_primer_post_rank_key`，即拆後分數 86.2767 對 86.7847。
- SL 種子 4 的 log 跟 C 完全一樣（同樣的 −86.1916／−86.3512、66.6719、86.7847），所以分岔和 oracle 無關。

**C 的 primer 重搜走的是 ef87f65 的新算法。**
- primer 在 `main.primer_guided_research`（main.py:603）把 `SPLIT_AWARE_SEARCH` 設成 True。
- C 本來就開 `SPLIT_LEADING`，所以 `fast_fitness_evaluator` 走 `split_leading_abi` 分支（src/optimizer.py:144、:192）。這個分支讓 ≤ LEADING_SPLIT_LIMIT 的超標前導棒只預付燃料，不推時鐘、不判失格層。
- A 沒開 SPLIT_LEADING，走舊的 `elif split_aware` 分支：超標前導棒歸入失格層，DE 等於被禁止用大前導棒。
- 挑 REVS 贏家的拆後估計也不同：`split_est_score`（src/optimizer.py:2395）在 SPLIT_LEADING 開時，會把可拆的前導棒加回 −10 分，只扣 SPLIT_AWARE_DV_OVERHEAD（src/optimizer.py:2417）。
- 舊版 C（14b7849，修正前）的種子 4 也是 86.7847（見 `../sweeps/phase2_armC_results_replaced_14b7849.jsonl`），所以這和 ef87f65 的修正無關，是 SPLIT_LEADING 本身造成的。

**3 棒解沒有出現在 C 的任何候選比較裡。**
- primer 比較只有兩個候選：原本的 2 棒（拆後 86.2767）和重搜贏家（86.7847）。REVS 集成的另一個候選（REVS=4，3 棒，拆後估計 86.1641）也不是 A 那條路線。
- Oracle comparison 表裡的 3 棒候選是 rank 6／9 的 86.7620 和 rank 7 的 86.6855，都不是 86.7864。
- C 最後交的是 oracle rank 1：86.784742，前導 304.8 m/s，4 棒。它以 1e-6 的平手勝過 DE 的 86.784741。

**為什麼 SL／C 的 DE 不選 A 那條路線：拆後估計把兩條路線的順序排反了。**

| 路線 | 拆後估計 | 實際拆後分數 |
|---|---|---|
| A 路線（終端超標） | 86.4464 | 86.7864 |
| C 路線（前導 + 終端超標） | 86.6377 | 86.7847 |

A 路線的前導棒都 ≤ 250 m/s，`split_est_score` 不會對它套用前導棒的加回規則，所以在 SL/C 下，挑 REVS 贏家時它的估計仍是 86.4464。DE 適應度的 `split_leading_abi` 分支把單棒上限改成真實上限，不再用 SOFT，所以 DE 目標值可能有極小的差異。這條路線在 SL/C 下仍然合法、可以被搜到，但它的估計比 C 路線低 0.19，因此 DE 和 REVS 挑選都偏向「大前導棒」那個盆地。實際拆後卻是 A 路線高 0.0017。估計低估了 A 路線 0.34，只低估 C 路線 0.15：終端棒拆棒的預付（SPLIT_AWARE_TERMINAL_DV_OVERHEAD）相對偏重，前導棒等分的預付（SPLIT_AWARE_DV_OVERHEAD = 1.02）相對偏輕。

## 2. 用跑的區分：種子 0–9

設定：smoke 排位賽 base，環境變數同四臂比較，`--slots 2`，HEAD 9808cbc（程式碼 = ef87f65）。A 和 C 的種子 0–4 沿用四臂比較的結果，種子 5–9 是新跑的；SL 的 10 顆全部新跑。規格檔是 `smoke10_{A,SL,C}.json`，逐 run 結果在 `smoke_seeds0-9.csv` 與 `sweeps/`。

| 組 | 設定 | 拿到 86.7864（3 棒）的種子 | 其餘 |
|---|---|---|---|
| A | 現行預設 | **1/10**（種子 4） | 9 顆都是 86.7847（4 棒） |
| SL | 只開 SPLIT_LEADING | **0/10** | 9 顆 86.7847；種子 5 是 86.7834（4 棒） |
| C | SPLIT_LEADING＋ORACLE_TWOBURN | **0/10** | 10 顆都是 86.7847（4 棒，oracle 都以平手勝出） |

SL 拿不到 86.7864 的種子：0–9 全部。C 拿不到的種子：0–9 全部。

解讀：
- A 也只有 10% 的種子拿得到 86.7864，1/10 對 0/10 在統計上分不出「SPLIT_LEADING 會系統性擋掉這個解」。
- 能確定的只有種子 4：同一顆種子下，SPLIT_LEADING 改了 primer 重搜的目標函數，必然走到另一個盆地。
- A 的其他種子，primer 重搜要嘛沒勝出，要嘛勝出後拆出 4 棒（例如 A 種子 5：76.2728 → 76.6302，拆後 86.7847）。
- 差距只有 0.0017 分。

## 檔案

- `smoke10_{A,SL,C}.json`：規格檔。
- `smoke_seeds0-9.csv`：三組各 10 顆種子的分數、棒數、總 Δv、拆前棒數、拆後估計、牆鐘、commit、資料來源。
- `sweeps/smoke10_{A,SL,C}_results.jsonl`：新跑的那 20 個 run 的 sweep 原始記錄。
