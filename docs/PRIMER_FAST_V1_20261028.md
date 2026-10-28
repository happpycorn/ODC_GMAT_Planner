# primer 快速重搜對照（primer_fast_v1，2026-10-28）

**問題：** `PRIMER_RESEARCH_MODE=fast`（[C1_PRIMER_VECTOR_STUDY](C1_PRIMER_VECTOR_STUDY.md) 的「fast 模式」一節）
能不能保住 full 重搜在 `hyperbolic_smoke` 賺到的分數，同時省下 `hyper_far` 的重搜時間。

**規格：** [`sweeps/primer_fast_v1.json`](../sweeps/primer_fast_v1.json)，`1bf8045`。`hyperbolic_smoke` 種子 1–3、`hyper_far` 種子 0、2，
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

## 還沒回答的

- **fast 能不能救回「第一輪落在差路線、要靠 primer 跳盆地」的情況**：要找一個在現行程式上仍會觸發 primer、而且 full 重搜大幅勝出的案例。
  候選做法是掃 `hyperbolic_smoke` 更多種子（4–15，每顆約 2–4 分鐘）挑出 primer 重搜勝出的，再對那幾顆跑 full／fast。
- 種子數少（每情境 2–3 顆），只能說「沒看到退步」，不能估退步機率。

## 量測條件

- 機器：Corn，AMD Ryzen 7 5800X（8 實體核心／16 執行緒），WSL2。`--slots 1` 依序跑，期間沒有其他重運算；
  開跑前 1 分鐘負載 0.10。sweep 從 12:11 到 13:30，全程 78 分鐘（含 48 s numba 暖身）。
- SEED 有設定時 `run_study_over_revs` 會把 BLAS 鎖成單執行緒，啟動時也加了 `OMP/OPENBLAS/MKL/NUMEXPR_NUM_THREADS=1`。
- 原始資料在本機 `outputs/sweeps/primer_fast_v1/`（`results.jsonl`、各 run 的 `run.log`、`mission.json`、拆前贏家存檔），不進 git。
