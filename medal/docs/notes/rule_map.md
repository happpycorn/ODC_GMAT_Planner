# 規則敏感度地圖：250 m/s 級規則、rollout 大腦（清單第 3 項）

## 1. 問題
規則公布當天要在幾分鐘內知道「這組規則誰有利、哪個大腦最好」。E8 的平衡地圖是解析大腦在 1500 m/s 級規則量的；
E14–E17 顯示 250 m/s 級規則下結論會翻。這裡在 `ranking_like.json`（雙方 250/3000、窗口 300 s、半徑 5 km、
T_max 4 週期、追者先手、1 發/回合、continuous、J2）附近逐軸改一個欄位（加兩組兩軸交叉），量 rollout 大腦的追者勝率、
跟基底格逐局配對，做成當天查表工具；再在 `symmetric.json`（1500/3000）上確認趨勢方向。

## 2. 改了什麼（沒有改任何既有程式）
- `tools/rule_map.py`（新）：格子 = 相對基底的改動；每局一結束就 append 到 `reports/<name>.jsonl`（中斷後同指令重跑會續跑，
  規則不同會拒絕混檔）；`report` 寫 `reports/<name>.md`（勝率、vs 基底配對、大腦選擇、一句話建議）；`export` 合併成 `configs/rule_map.json`。
- `tools/rule_lookup.py`（新）：`uv run python tools/rule_lookup.py configs/rules_final.json [--top 3]` → 最接近的格子（列出差在哪些欄位）、
  各配對勝率與 vs 基底 p、抽到追者／躲者的建議、你的規則跟基底不同的每個軸的單軸效果、**超出地圖範圍的欄位**
  （數值超出測過的最小～最大、類別值沒測過如 J4、燃料發數／燃料比超出）。沒跑的配對顯示「未跑」。
- `game/rule_presets.py`（新）：`RankingRuleRanges`（`RuleRanges` 子類別：單發 150–400、躲者 ×0.8–1.25、燃料 8–16 發、窗口 120–900、
  半徑 1–20、T_max 2–6、1–3 發/回合，窗口放不下的發數照實截掉）。`game/rules.py` 沒動。
- `configs/rule_map.json`（新，37 格）、`reports/rmap_ranking.md`、`reports/rmap_symmetric.md`。
- `tests/test_rule_map.py`（新，12 項）。

## 3. 設定
- 每格 24 局、mixed 幾何、seed 1（**跟 E15–E17 同一批幾何**；基底格 rr 7/24、Lambert 11/24 都跟 E17 完全一樣）、5 worker、nice 10。
- 配對（同一批幾何、同 agent seed）：**rr** = `rollout_pursuer` vs `rollout_evader`；**escape** = `rollout_pursuer` vs `escape_evader`；
  **lambert** = `lambert_pursuer` vs `rollout_evader`（對照，只跑基底／燃料／窗口格）；**strong**（強化版追者）**未跑**。
- 「vs 基底」：同一局在本格與基底格的結果配對，+只有本格追者贏 / −只有基底追者贏，p = 雙尾精確符號檢定。
  這裡有 ~70 個檢定，約 5% 會是偽陽性；+0/−7 的格子 p 最小也只有 0.016。
- 跑的 commit：`aa7d605`（多發／燃料／窗口軸）、`4882cb3`（其餘）。**都早於另一個任務對多發存活檢查（agents/analytic.py）的修改，合併後多發格要重跑。**
```bash
uv run python tools/rule_map.py run --base configs/rulesets/ranking_like.json --name rmap_ranking --pairs fast \
    --group burns --group fuel --group window --games 24 --seed 1 --workers 5          # 約 35 分鐘
uv run python tools/rule_map.py run --base configs/rulesets/ranking_like.json --name rmap_ranking --pairs fast \
    --group burns_x_window --group burns_x_fuel --group maxdv --group tmax --group radius --group first --group capmode
uv run python tools/rule_map.py run --base configs/rulesets/ranking_like.json --name rmap_ranking --pairs lambert --group window --group fuel
uv run python tools/rule_map.py run --base configs/rulesets/symmetric.json --name rmap_symmetric --pairs fast \
    --group burns --group fuel --group window
uv run python tools/rule_map.py export --name rmap_ranking --name rmap_symmetric --out configs/rule_map.json
```

## 4. 結果

### 4.1 單軸（ranking_like 基底，`reports/rmap_ranking.md`）
追者勝率 [95% 區間]，n = 24/格；**粗體** = 跟基底逐局配對 p < 0.05。

| 軸 | 值 | rr | rr vs 基底 | lambert | 逃逸躲者被抓 |
|---|---|---|---|---|---|
| 基底 | 250/3000、300 s、1 發 | 29% [15–49] | — | 46% [28–65] | 100% [86–100] |
| 一回合發數 | 2 | 83% [64–93] | **+14/−1 p=0.001** | 未跑 | 100% |
| | 3 | 75% [55–88] | **+12/−1 p=0.003** | 未跑 | 96% |
| 燃料 追/躲 | 3000/1500 | 100% [86–100] | **+17/−0 p<0.001** | 83% | 100% |
| | 1500/3000 | 0% [0–14] | **+0/−7 p=0.016** | 0% | 75% |
| | 4500/3000 | 46% [28–65] | +9/−5 p=0.42 | 71% | 100% |
| | 3000/4500 | 0% [0–14] | **+0/−7 p=0.016** | 0% | 17% |
| 窗口 | 120 s | 83% [64–93] | **+13/−0 p<0.001** | 46% | 88% |
| | 600 s | 0% [0–14] | **+0/−7 p=0.016** | 0% | 75% |
| | 900 s | 0% [0–14] | **+0/−7 p=0.016** | 0% | **0%** |
| T_max | 2 週期 | 0% [0–14] | **+0/−7 p=0.016** | 未跑 | 33% |
| | 6 週期 | 71% [51–85] | **+12/−2 p=0.013** | 未跑 | 88% |
| 單發 追/躲 | 250/150 | 33% [18–53] | +6/−5 p=1 | 未跑 | 92% |
| | 150/250 | 42% [24–61] | +6/−3 p=0.51 | 未跑 | 92% |
| 捕獲半徑 | 1 km | 21% [9–40] | +0/−2 p=0.5 | 未跑 | 100% |
| | 20 km | 25% [12–45] | +0/−1 p=1 | 未跑 | 100% |
| 先手 | 躲者 | 42% [24–61] | +6/−3 p=0.51 | 未跑 | 100% |
| 捕獲判定 | endpoint | 21% [9–40] | +2/−4 p=0.69 | 未跑 | 92% |

- **顯著的軸**：多發、燃料（躲者油多或追者油少）、窗口、T_max。**看不出差異**：追者燃料 ×1.5、單發不對稱 150/250、半徑 1–20 km、先手、endpoint（都在 ±13 個百分點內、p ≥ 0.42）。
- **窗口跟 E8 不一樣**：E8（1500 m/s 解析大腦）窗口幾乎是平的；rollout 大腦在 250 m/s 下 120 s → 83%、600/900 s → 0%。
  長窗口時 rollout 追者只用了 405–470 m/s（共 3000），像 E12 的「推演判斷全輸就不追」；但每回合都追的 Lambert 追者也是 0/24，所以**不只是大腦放棄**。
- **追者大腦**（同格配對，lambert vs rr）：基底 +10/−6 p=0.45、燃料 4500/3000 71% vs 46% +10/−4 p=0.18（都看不出差異）；
  **窗口 120 s 時 rollout 顯著較好**（83% vs 46%，+0/−9 p=0.004）。強化版追者（E16）**未跑**。
- **躲者大腦**（同格配對，對 rollout 追者的存活）：逃逸**沒有任何一格顯著較好**；窗口 900 s 兩者都 24/24 存活、燃料 3000/1500 兩者都 0/24；
  其餘大多是逃逸顯著較差（基底 +0/−17 p<0.001）。→ 躲者一律 rollout 躲者。

### 4.2 交叉（ranking_like 基底；「vs 1 發格」= 跟同窗口／同燃料的 1 發格逐局配對）

| 交叉 | rr | vs 1 發格 |
|---|---|---|
| 燃料 1500/3000 × 2 發 | 33% [18–53] | 0% → **+8/−0 p=0.008** |
| 燃料 1500/3000 × 3 發 | 54% [35–72] | 0% → **+13/−0 p<0.001** |
| 燃料 3000/4500 × 2 發 | 46% [28–65] | 0% → **+11/−0 p=0.001** |
| 燃料 3000/4500 × 3 發 | 54% [35–72] | 0% → **+13/−0 p<0.001** |
| 窗口 120 s × 2 發 | 62% [43–79] | 83% → +0/−5 p=0.06（看不出；vs 300 s × 2 發 83%：+1/−6 p=0.12） |
| 窗口 600 s × 2 發 | 8% [2–26] | 0% → +2/−0 p=0.5 |
| 窗口 600 s × 3 發 | 67% [47–82] | 0% → **+16/−0 p<0.001**（vs 300 s × 3 發 75%：+3/−5 p=0.73） |
| 窗口 900 s × 2 發 | 25% [12–45] | 0% → **+6/−0 p=0.031** |
| 窗口 900 s × 3 發 | 33% [18–53] | 0% → **+8/−0 p=0.008** |

- 多發能把「躲者燃料優勢」和「長窗口」的劣勢拉回一半左右（0% → 33–67%）。600 s × 2 發（8%）跟 × 3 發（67%）差很多，
  只有一批幾何，不要過度解讀單一格。逃逸躲者在交叉格也沒有比 rollout 躲者好（報表「大腦選擇」表）。

### 4.3 當天查表（ranking_like 附近；「預期」= 我方最強追者 vs rollout 躲者，n = 24）

| 規則特徵 | 誰有利 | 抽到追者 | 抽到躲者 |
|---|---|---|---|
| 照排位賽（250/3000、300 s、1 發） | 躲者（29% [15–49]） | rollout 或 Lambert（46%，看不出差異），照 ★ | rollout 躲者，存活 ~70%；不要逃逸 |
| 一回合 2–3 發 | 追者（75–83%） | rollout 追者 | rollout 躲者，存活只有 ~20%：拖時間、逼對方耗油 |
| 窗口 ≤ 120 s | 追者（83%） | **rollout 追者（顯著優於 Lambert）** | rollout 躲者，存活 ~17% |
| 窗口 ≥ 600 s、1 發 | 躲者（0%，兩種追者都是） | 目標改成縮短最近距離 | rollout 躲者（逃逸在 900 s 也 24/24，但沒有更好） |
| 窗口 ≥ 600 s、3 發 | 不確定（600 s 67%、900 s 33%） | rollout 追者 | rollout 躲者 |
| 躲者燃料 ×1.5 或追者燃料 ×0.5 | 躲者（0%）；多發時拉回 33–54% | 1 發時目標改成縮短距離 | rollout 躲者 |
| 追者燃料 ×1.5 | 看不出（rr 46%、Lambert 71%） | 照 ★（Lambert 點估計較高，不顯著） | rollout 躲者 |
| 躲者燃料 ×0.5 | 追者（100%） | rollout 追者 | rollout 躲者，存活幾乎 0 |
| T_max 2 週期 / 6 週期 | 躲者 0% / 追者 71% | rollout 追者 | rollout 躲者 |
| 半徑 1–20 km、先手、endpoint、單發 150/250 不對稱 | 跟基底看不出差異 | 同基底 | 同基底 |

### 4.4 規則不確定時的平均（`RankingRuleRanges`）：**未跑**（分布與工具都備好，見 7）。

## 5. 第二組規則確認（symmetric.json 1500/3000，`reports/rmap_symmetric.md`，rr + escape，24 局）

| 軸 | 值 | rr | rr vs 基底 | 逃逸被抓 | ranking 同格 rr |
|---|---|---|---|---|---|
| 基底 | 1500/3000、300 s | 58% [39–76] | — | 21% [9–40] | 29% |
| 發數 | 2 / 3 | 71% / 58% | +7/−4 p=0.55 / +4/−4 p=1 | 42% / 42% | 83% / 75% |
| 燃料 追/躲 | 3000/1500 | 100% [86–100] | **+10/−0 p=0.002** | 96% | 100% |
| | 1500/3000 | 33% [18–53] | +3/−9 p=0.15 | 0% | 0% |
| | 4500/3000 | 88% [69–96] | **+7/−0 p=0.016** | 75% | 46% |
| | 3000/4500 | 21% [9–40] | **+3/−12 p=0.035** | 0% | 0% |
| 窗口 | 120 s | 46% [28–65] | +1/−4 p=0.38 | 38% | 83% |
| | 600 s | 21% [9–40] | **+2/−11 p=0.022** | 4% | 0% |
| | 900 s | 8% [2–26] | **+1/−13 p=0.002** | 21% | 0% |

- **方向相同**：燃料（躲者油多 → 躲者、追者油多 → 追者）、長窗口 → 躲者。**E8「窗口沒影響」對 rollout 大腦不成立**：兩組規則下 600/900 s 都顯著利於躲者。
- **不同**：多發在 1500/3000 下看不出效果（燃料只有 2 整發，用不到多發）；短窗口 120 s 只在 250 m/s 下顯著利於追者；
  追者燃料 ×1.5 在 1500 m/s 下顯著（88%）、250 m/s 下看不出（46%）；逃逸在 1500 m/s 下是強打法（基底只被抓 21%），250 m/s 下最弱。

## 6. 結論
1. 250 m/s 級規則下最重要的四個軸：**一回合發數、窗口、雙方燃料（尤其躲者的）、T_max**。半徑、先手、捕獲判定、單發 150/250 不對稱看不出影響。
2. 規則一公布先看：多發或短窗口 → 抽到追者大優勢；長窗口 1 發或躲者油多 → 抽到躲者大優勢（追者 0%，換大腦也沒用）。
3. 躲者大腦：所有測過的格子都用 rollout 躲者（逃逸從沒顯著較好）。追者大腦：rollout 與 Lambert 只在 120 s 窗口分得出（rollout 較好）；強化版沒量。
4. 查表：`uv run python tools/rule_lookup.py configs/rules_final.json`。

## 7. 限制、沒做的事、建議下一步
- **未跑**：強化版 rollout 追者（所有格子）；規則分布平均（`--ranges ranking`）；lambert 只跑基底／燃料／窗口格；symmetric 只跑 rr + escape。
  ```bash
  uv run python tools/rule_map.py run --base configs/rulesets/ranking_like.json --name rmap_ranking --pairs strong \
      --group burns --group fuel --group window      # 估 ~2 小時（5 worker；多發與 120 s 窗口最貴）
  uv run python tools/rule_map.py run --base configs/rulesets/ranking_like.json --name rmap_ranges --ranges ranking --no-base \
      --games 48 --pairs fast                         # 估 20–30 分鐘；跑完 export 加 --name rmap_ranges
  ```
- 每格 24 局、一批幾何（seed 1）、只有 J2；~70 個檢定的多重比較；格子之間的差 < ~25 個百分點通常分不出來。
- 多發格在 `aa7d605`／`4882cb3` 跑，早於 agents/analytic.py 的多發存活檢查修改，合併後要重跑多發與交叉格（同指令換 `--name`）。
- 長窗口的 0% 是「我們的兩種追者大腦」都追不到，不等於理論上追不到；更強的追者（例如強化版）可能不同。
- 查表的「最接近格子」用加權距離排序（權重見 `tools/rule_lookup.py` 開頭），多個軸同時偏離基底時，請同時看「各軸單獨的效果」。

## 8. 逐位元檢查
沒有改 `game/`、`agents/`、`physics/` 的既有程式（只新增 `game/rule_presets.py`）。
- `tests/test_rule_map.py::test_rule_ranges_sample_unchanged`：`RuleRanges().sample` 的 4 組抽樣值與下一個亂數，跟改前（master 80dc622）逐位元相同；
  `make_games(..., "ranges")` 的規則也不變。
- 同一個 worktree、同一份 numba 快取，改前（80dc622 的程式，新檔還沒被任何程式 import）與改後（全部新檔 commit 後）各跑 `evaluate.py --rules {default,ranges,ranking_like.json}`
  6 局 × {lambert, rollout} 追者 × {dv, rollout} 躲者，逐局比 outcome、t_end、min_dist_km、used_*、turns、rules：**72/72 局完全相同**。
