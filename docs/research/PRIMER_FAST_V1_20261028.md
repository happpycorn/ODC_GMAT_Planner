# primer 快速重搜對照（primer_fast_v1，2026-10-28）

**問題：** `PRIMER_RESEARCH_MODE=fast`（[C1_PRIMER_VECTOR_STUDY](C1_PRIMER_VECTOR_STUDY.md) 的「fast 模式」一節）
能不能保住 full 重搜在 `hyperbolic_smoke` 賺到的分數，同時省下 `hyper_far` 的重搜時間。

**規格：** [`sweeps/primer_fast_v1.json`](../../sweeps/primer_fast_v1.json)，`1bf8045`。`hyperbolic_smoke` 種子 1–3、`hyper_far` 種子 0、2，
各跑 full／fast，共 10 次。排位賽限制（250 m/s、總 3,000 m/s）、MAXITER 600 × POPSIZE 20、
拆棒用 [SPLITTER_SPEED](SPLITTER_SPEED_20261020.md) 的建議設定（600 s 預算）。只求解、不跑 GMAT。

## 結論

1. **fast 沒有比 full 差：10 組裡 fast 對 full 的最大落後是 0，沒有任何一組差超過 0.01 分。**
   primer 沒觸發或原解勝出的 4 組分數逐位元相同；兩組 `hyper_far` 分數差 +1.4×10⁻⁴ 與 +2×10⁻⁸（fast 略高，屬拆棒雜訊）。
2. **`hyper_far` 牆鐘省 19–24%**：總牆鐘 1,102 → 840 s（−262 s）、1,010 → 821 s（−189 s）。
   primer 重搜這一段從 412 → 138 s、296 → 96 s，約省 2/3。
3. **這次量不到「1.58 分」那件事。** 在 `1bf8045` 上，`hyperbolic_smoke` 種子 1–3 的第一輪搜尋就直接落在
   86.78 的路線（拆前 2 棒、拆後 4 棒、639 m/s）：種子 1、3 的 primer 根本沒觸發，種子 2 觸發了但 full 和 fast 都是原解勝出。
   1.58 分出自 [RANKING_MC](RANKING_MC_20261019.md)（`d5afcff`），當時種子 1–3 是靠 primer 重搜才從 851 m/s 的路線跳到
   654 m/s；之後的搜尋懲罰 v2（[RANKING_PENALTY_V2](RANKING_PENALTY_V2_20261019.md)）讓第一輪搜尋自己就找得到，
   種子 0 也從 85.20 升到 86.78。所以 fast 在「primer 真的救分」的情境下表現如何，**這組種子回答不了**。
   後續掃描找到一個救分案例，**fast 沒救到，比 full 少 0.51 分**，見「[救分案例](#救分案例primer_rescue_scan_v1--primer_fast_v2)」。
4. Mac 上量到 full 重搜在 `hyper_far` 多花 14–40 分鐘；在 Corn 上 full 的重搜段只要 5–7 分鐘（見下表「重搜段」）。

## 結果

牆鐘是 `sweep_params` 量的整個 run；「重搜段」是 `run.log` 裡「primer 診斷」到重搜結果那一行的時間差。
分數、棒數、總 Δv 是拆棒後的最終方案，10 組都合法、Earth-safe、miss 3.495–3.496 km。

| 情境 | 種子 | 模式 | 牆鐘 (s) | 重搜段 (s) | primer 觸發 | fast 勝出階段（local／global 秒） | 拆後分數 | 棒數 | 總 Δv (m/s) |
|---|---|---|---|---|---|---|---|---|---|
| hyperbolic_smoke | 1 | full | 127 | — | 否（max\|p\|=1.002） | — | 86.783465 | 4 | 639.55 |
| hyperbolic_smoke | 1 | fast | 129 | — | 否（max\|p\|=1.002） | — | 86.783465 | 4 | 639.55 |
| hyperbolic_smoke | 2 | full | 244 | 110 | 是（2.382，3 棒重搜） | —（重搜 76.6740 < 原 76.6867，沿用原解） | 86.784691 | 4 | 639.36 |
| hyperbolic_smoke | 2 | fast | 170 | 40 | 是（2.382，3 棒重搜） | original（5.39／33.64） | 86.784691 | 4 | 639.36 |
| hyperbolic_smoke | 3 | full | 119 | — | 否（max\|p\|=1.002） | — | 86.784291 | 4 | 639.42 |
| hyperbolic_smoke | 3 | fast | 116 | — | 否（max\|p\|=1.002） | — | 86.784291 | 4 | 639.42 |
| hyper_far | 0 | full | 1,102 | 412 | 是（1.971，4 棒重搜） | —（重搜勝出 72.5893 → 72.5957） | 82.432435 | 9 | 1,920.34 |
| hyper_far | 0 | fast | 840 | 138 | 是（1.971，4 棒重搜） | global（3.23／130.57） | 82.432575 | 9 | 1,920.33 |
| hyper_far | 2 | full | 1,010 | 296 | 是（3.951，3 棒重搜） | —（重搜勝出 72.4833 → 72.4834） | 82.292454 | 8 | 1,938.04 |
| hyper_far | 2 | fast | 821 | 96 | 是（3.951，3 棒重搜） | local（1.08／90.95） | 82.292454 | 8 | 1,938.04 |

觀察：

- fast 選出的拆前解跟 full 一樣（`hyper_far` 0：72.5957、4 棒；`hyper_far` 2：72.4834、3 棒），拆後差別只來自拆棒。
- `hyper_far` 2 的 local 階段 1 秒就找到跟 full 重搜一樣的解，global 那 91 秒沒有再進步；`hyper_far` 0 則是 local 停在跟 global 同分
  （72.5957），按同尺取優規則判給 global。短全域都在 300 s 上限內結束，沒有觸發牆鐘到期。
- `hyperbolic_smoke` 2 的 local／global 候選都只有 72.03（拆後估 82.03），遠比原解差，full 重搜也沒勝過原解；兩種模式都正確地沿用原解。
- 拆棒段（`split_sec`）full／fast 都是 `hyper_far` 327–341 s、`hyperbolic_smoke` 28–47 s，跟 primer 模式無關。

## 救分案例（primer_rescue_scan_v1 → primer_fast_v2）

**結論：`hyperbolic_smoke` 種子 4–15 裡只有種子 5 是救分案例，fast 在這顆沒救到：拆後 86.2748 vs full 86.7847（−0.51 分），
牆鐘 174 vs 225 s。** fast 的 local 與短全域候選都比原解差，同尺取優後退回原解。所以 fast 目前的實作在「需要 primer 跳盆地」時
會丟掉 full 能賺到的分數；省下的時間在 `hyperbolic_smoke` 是約 70 s（重搜段 107 → 36 s）。
找到救分案例後就沒有再掃 `ranking_round`。

### 掃描（[`sweeps/primer_rescue_scan_v1.json`](../../sweeps/primer_rescue_scan_v1.json)）

`hyperbolic_smoke` 種子 4–15，只跑 full，設定同 v1；`--slots 3` 並行（只看分數；固定 SEED 時 slot 數不影響結果，牆鐘會互相干擾），19 分鐘。

判定條件是「primer 觸發、重搜勝出、拆後比原解高 > 0.01 分」。full 模式只拆勝出的那個解，原解的拆後分數沒有算，
所以用 log 裡的**拆前分數差**代替（排位賽下拆前分數 + 10 就是拆後估計分，`split_est`）。

| 種子 | primer | full 重搜結果（拆前分數） | 拆後分數 |
|---|---|---|---|
| 4、7、12、14 | 沒觸發（max\|p\| 1.000–1.007） | — | 86.7841、86.7620、86.7846、86.7841 |
| **5** | **觸發（1.701）** | **勝出：76.2803 → 76.6535（2 → 3 棒，714 → 659 m/s）** | **86.7847** |
| 6 | 觸發（1.641） | 平手 76.4298，沿用原解 | 86.4292 |
| 8 | 觸發（1.747） | 重搜 −11.8173，沿用原解 76.2795 | 86.2745 |
| 9、10、11、13、15 | 觸發（1.098–9.125） | 都沒勝過原解（差 0.06–0.73） | 86.7834–86.7847 |

12 顆裡 8 顆觸發 primer，只有種子 5 重搜勝出（拆前 +0.373）。種子 6、8 是另一種情況：觸發了、原解偏低（86.43、86.27），
但 full 也沒救到；一起放進 v2 當補充。

### full vs fast（[`sweeps/primer_fast_v2.json`](../../sweeps/primer_fast_v2.json)）

`--slots 1` 依序跑，21 分鐘。重搜段的算法同上表。

| 種子 | 模式 | 牆鐘 (s) | 重搜段 (s) | 勝出（local／global 秒；各候選拆前分數） | 拆後分數 | 棒數 | 總 Δv (m/s) |
|---|---|---|---|---|---|---|---|
| **5** | full | 225 | 107 | 重搜勝出 76.2803 → 76.6535 | **86.784736** | 4 | 639.35 |
| **5** | fast | 174 | 36 | original（3.35／31.37；local 75.2156、global 75.4843） | **86.274758** | 4 | 714.60 |
| 6 | full | 280 | 110 | 沿用原解 | 86.429162 | 4 | 692.61 |
| 6 | fast | 204 | 37 | original（2.78／31.77；local 75.2156、global 75.7880） | 86.429162 | 4 | 692.61 |
| 8 | full | 238 | 110 | 沿用原解 | 86.274465 | 4 | 714.64 |
| 8 | fast | 166 | 36 | original（2.76／32.25；local 75.2156、global 75.2285） | 86.274465 | 4 | 714.64 |

觀察：

- 種子 5 full 的分數跟掃描那次（3 slot 並行）逐位元相同，重現性正常。
- 三顆種子的 local 階段都收斂到同一個 75.2156 的解，比原解差 1 分以上：插棒種子局部精修後落在同一個較差的盆地，跟原贏家無關。
- 短全域都在 31–32 s 跑完，沒有碰到 300 s 牆鐘上限。所以限制它的是代數（MAXITER × 0.33），不是牆鐘；
  full 的完整重搜約 110 s 就能從 76.28 跳到 76.65，fast 的 1/3 代數跳不過去。
- 種子 6、8 兩種模式都退回原解，分數逐位元相同，fast 省約 75 s。

**對 fast 的含意**：在 v1 的 `hyper_far` 上 fast 每顆省 3–5 分鐘、分數不變；在 `hyperbolic_smoke` 種子 5 上 fast 省 51 s、丟 0.51 分。
要讓 fast 兩邊都顧到，可能的方向是提高短全域的代數比例（例如 0.66，`hyperbolic_smoke` 的 full 重搜本來就只要 ~110 s），
或依原贏家的搜尋耗時決定 full／fast；這些都要改程式，這次沒做。

## 還沒回答的

- 救分案例只有 1 顆（`hyperbolic_smoke` 種子 5）。其他幾何（`ranking_round`、`hyper_far` 更多種子）上 primer 救分的頻率和 fast 的表現沒量。
- 種子數少，只能看方向，不能估退步機率。

## 量測條件

- 機器：Corn，AMD Ryzen 7 5800X（8 實體核心／16 執行緒），WSL2。`--slots 1` 依序跑，期間沒有其他重運算；
  開跑前 1 分鐘負載 0.10。sweep 從 12:11 到 13:30，全程 78 分鐘（含 48 s numba 暖身）。
- SEED 有設定時 `run_study_over_revs` 會把 BLAS 鎖成單執行緒，啟動時也加了 `OMP/OPENBLAS/MKL/NUMEXPR_NUM_THREADS=1`。
- 救分案例那兩批（掃描約 13:32–13:53、對照約 13:54–14:17）同一台機器；對照期間只有另一個 repo 的 git 操作與讀檔，沒有其他重運算。
- 原始資料在本機 `outputs/sweeps/primer_fast_v1/`、`primer_rescue_scan_v1/`、`primer_fast_v2/`（`results.jsonl`、各 run 的 `run.log`、`mission.json`、拆前贏家存檔），不進 git。
