# copilot ★ 整體策略評測＋現場決策時間預算（清單第 5 項）

## 1. 問題
當天每回合照 `copilot.py advise` 的「★ 推薦」下（各大腦建議 × 對手模型推演到終局，先比最壞再比平均，`rank_advice`）。
這個**整體策略**從沒大批對打過（E16 限制），只驗過單一大腦。要確認：(a) ★ 不輸最好的單一大腦（躲者 `lazy_evader`、
追者 `rollout_pursuer`）；(b) 每回合 advise 要多久、現場用幾個 worker、時間不夠時用哪些選項。

## 2. 改了什麼（預設行為與輸出不變）
- **`agents/copilot_agent.py`**（`py:agents.copilot_agent:CopilotAgent`）：每次 act 走 `state_from_game` → `advise` →
  ★ 大腦的這一發（原始 Δv，不經 1e-4 m/s 四捨五入）。多發規則：窗口開始跑一次 advise、記住 ★ 的整個窗口計畫，
  `take_turn` 窗口中途再問時照計畫回傳（= 當天每回合跑一次 copilot、照 ★ 多發計畫輸入）。`COPILOT_AGENT_LOG=<目錄>`
  時每次決策寫一行 JSON（★、各大腦推演表狀態、用時）。評測時設 `COPILOT_WORKERS=1`（每局單行程）。
- **`copilot.py` 只加可選功能**（`advise` 不帶新參數時走原本的程式碼）：
  - `--prune`／`advise(prune=True)`：大腦依序「決策 → 推演表」，推演中途就能確定「不可能是 ★」時停掉
    （燃料、時間只增不減 → 分數上界 `_value_upper_bound`；低於目前最佳大腦的最壞分數就停）。對手模型順序與有狀態大腦
    （EscapeEvader）的連續推演都跟預設相同，**★ 與完整推演相同**。另外：續行是 RolloutPlanner、第一發逐位元相同、
    續行規格相同的推演直接沿用（強化版 rollout 追者的推演表續行就是 rollout 追者）。
  - `--budget-sec S`：超過 S 秒就停；還沒開始的大腦跳過、推到一半的推演表作廢，★ 只在推演表完整的大腦裡選，
    一個都沒有就用第一個大腦（躲者 lazy_evader、追者 rollout_pursuer）。印出剪枝／超時／跳過的大腦。
  - `--rank wins`：★ 改成先比「贏幾個對手模型」再比最壞、平均（§4.3 的候選修正；**沒有大批評測**）。
  - `advise(workers=, with_situation=)`、`rollout(stop=)`、`default_brains()`：給 agent 用的參數。
- `tests/test_copilot_agent.py`（11 項；全套 166 項全綠）：剪枝 ★ = 完整 ★（追者／躲者、兩種排序）、上界永不低於最後分數、推演沿用、
  時間預算 0 退回第一大腦、單一大腦的 copilot 整局 = 那個大腦（單發與 2 發逐位元相同）、預設輸出欄位不變。

## 3. 設定
`ranking_like.json`、mixed、seed 1、12 局、`nice 10`、`NUMBA_NUM_THREADS=1`、`COPILOT_WORKERS=1`、兩組各 `--workers 2`
（當時另外兩個任務在跑，load 10–15）。
```bash
STRONG='{"name":"rollout_pursuer","opponents":["coast","dv_evader_fast",{"name":"rollout_evader","candidates":["dv_evader_fast"],"opponents":["lambert_pursuer_fast"]}]}'
CP=py:agents.copilot_agent:CopilotAgent
COPILOT_WORKERS=1 COPILOT_AGENT_LOG=logs/ev_rp uv run python evaluate.py --rules configs/rulesets/ranking_like.json \
    --scenario mixed --games 12 --seed 1 --workers 2 --pursuers rollout_pursuer --evaders "$CP;lazy_evader" \
    --name copilot_evader_vs_rollout_ranking_like            # 強化版：--pursuers "$STRONG;" --name copilot_evader_vs_strong_ranking_like
uv run python tools/paired_compare.py --a reports/copilot_evader_vs_rollout_ranking_like.jsonl --ae $CP --be lazy_evader --win evader
```
決策時間：`copilot.py advise state.json [--prune] [--budget-sec 10] [--no-rollout]`（子行程，含程式啟動），局勢檔 =
ranking_like／ranking_like_2burn、seed 1 第 0 局（inclined）用 rollout 追者 vs lazy_evader（躲者角色）／rollout_evader
（追者角色）下到 t ≈ 0 與 ≈ 0.4 T_max。量的時候機器空（load < 0.5，量測中只有自己的行程，load 1–4）。

## 4. 結果

### 4.1 躲者：copilot★ vs lazy_evader（逐局配對）
| 追者 | copilot★ 存活 | lazy_evader 存活 | 只 copilot／只 lazy | p | 用油（m/s，平均） | 最近距離中位數 |
|---|---|---|---|---|---|---|
| rollout_pursuer | 12/12 = 100% [76–100] | 12/12 = 100% [76–100] | 0／0 | 1 | 625 ／ 625 | 38.0 ／ 38.0 km |
| 強化版 rollout 追者 | 12/12 = 100% [76–100] | 12/12 = 100% [76–100] | 0／0 | 1 | 583 ／ 583 | 33.2 ／ 33.2 km |

- **★ 在 1008/1008 次決策都選 lazy_evader**，所以兩邊逐局完全一樣（燃料、最近距離都相同）。推演表 5040 個裡 3943 個
  被剪枝（其他大腦都燒油，推演到一半就確定輸給 lazy 的「省油勝」）。
- 每次 advise（剪枝、單行程、load 10–15）：中位 4.7／3.9 s、p90 12.7／11.5 s、最長 28.8 s。

### 4.2 剪枝不改 ★
16 個局勢（兩組規則 × 2 幾何 × 兩個角色 × 開局／中盤）完整 vs `--prune`：**★ 16/16 相同**；單行程 CPU 躲者省 2.1–4.6 倍
（2 發開局 238 → 51 s），追者 1.0–1.6 倍（時間花在 rollout 大腦的決策與續行）。worker 數 1/2/4/8、`--prune` 下 ★ 也都相同。

### 4.3 追者：沒有大批對打（額度），只找到排序規則的風險
- 追者的 copilot★ 每回合 30–60 s（單行程、高負載），12 局 × 3 種躲者約 13 CPU 小時，收斂前沒跑。
- **機制**：所有大腦都輸給某個對手模型（常見：dv_evader）時，「先比最壞」變成比**輸局裡最接近的距離**，不看贏幾個模型。
  例：ranking_like 第 0 局開局 ★ = RL 追者（4 個模型抓到 2 個，最壞 −1289 km），rollout_pursuer 抓到 3 個（最壞 −1593 km）；
  同局實際對打前 5 回合有 3 回合 ★ 選 RL 追者（贏 1–2 個）而 rollout_pursuer 贏 3 個，t = 600 s 兩者最壞只差 20 km（−1218 vs −1238）。
  抽樣 8 個追者局勢中 7 個 ★ 是贏最多的大腦。躲者不受影響（lazy 幾乎總是 4/4 全贏，兩種排序結果一樣）。
- 候選修正 `--rank wins` 已實作（預設不變、剪枝仍精確），**沒有評測**；要驗證用：
  `--pursuers "$CP;{\"name\":\"$CP\",\"rank\":\"wins\"};rollout_pursuer" --evaders "rollout_evader;"`（dv_evader、lazy_evader 同理）。

## 5. 另一組規則
對稱 1500/3000 **沒跑**（收斂）。決策時間另量了 2 發規則（§6）。

## 6. 決策時間（16 執行緒桌機、機器空、牆鐘秒、含程式啟動）

| 狀態 | 預設 w=1 | w=2 | w=4 | w=8 | `--prune` w=8 | `--no-rollout` w=8 | `--prune --budget-sec 10` w=8 |
|---|---|---|---|---|---|---|---|
| 躲者 開局（1 發） | 46 | 36 | 34 | 32 | 14 | 4 | 11（★ 相同） |
| 躲者 中盤（1 發） | 51\*（CPU 30） | 22 | 25 | 24 | 27 | 8 | 11（★ 相同） |
| 追者 開局（1 發） | 36 | 32 | 28 | 28 | 18 | 12 | 11（沒排序 → 第一大腦） |
| 追者 中盤（1 發） | 13 | 12 | 13 | 13 | 11 | 10 | 10（★ 相同） |
| 躲者 開局（2 發） | 111 | – | – | 71 | 22 | 4 | 11（沒排序 → lazy） |
| 躲者 中盤（2 發） | 56 | – | – | 37 | 14 | 4 | 11（沒排序 → lazy） |
| 追者 開局（2 發） | 96 | – | – | 78 | 33 | 18 | 11（沒排序 → 第一大腦） |
| 追者 中盤（2 發） | 43 | – | – | 32 | 21 | 14 | 11（沒排序 → 第一大腦） |

\* 開機後第一次跑（載入快取），多約 20 s：**開賽前先跑一次 advise 暖機**。
- worker 到 4 就飽和：只有 rollout 大腦的候選評估是平行的，推演表本身（例：躲者對 rollout 追者模型的推演）是序列的。
- 追者 `--no-rollout` 也要 10–18 s：兩個 rollout 大腦光決策各 ~5 s（含行程池啟動）。
- `--opponents` 減少：躲者的推演時間幾乎都花在 rollout_pursuer 這個對手模型（單行程開局約 6.6 s／7.2 s），但它是最重要的模型
  （HAP-108），拿掉不如用 `--prune`；追者時間花在大腦本身，減少對手模型效果有限。

**現場 worker／時間預算建議表**（`COPILOT_WORKERS=4`；T = 每回合留給 copilot 的秒數）

| T（單發規則／2 發規則） | 指令 | 說明 |
|---|---|---|
| ≥ 60 ／ ≥ 120 | `advise state.json` | 完整推演表；實測最長 36／96 s（w=1）、32／78 s（w=4–8） |
| 25–60 ／ 40–120 | `advise state.json --prune` | ★ 與完整表相同；實測最長 27／33 s。**建議當作標準指令** |
| 15–25 ／ 15–40 | `--prune --budget-sec $((T-5))` | 截到時 ★ 只在做完的大腦裡選；都沒做完 → 第一大腦 |
| < 15 | 躲者 `--no-rollout`（4–8 s），採第一大腦 lazy_evader；追者 `--no-rollout --brains rollout_pursuer`（估 7–9 s） | 躲者 ★ 在 1008/1008 次都是 lazy_evader |

## 7. 結論
- **躲者：copilot★ 不輸 lazy_evader**——排位版規則下 ★ 每回合都選它，結果逐局相同（24/24 vs 24/24，p = 1）。
- **剪枝（`--prune`）★ 不變、躲者快 2–4 倍**，建議手冊的標準指令加上它；worker 用 4（8 沒有更快）。
- **追者：看不出結論（沒跑）**。排序規則在「所有大腦都會輸給某個模型」時會用輸局距離挑大腦，可能選到贏得少的
  RL／Lambert 追者。copilot 預設先不改；現場當追者時，若 ★ 不是 rollout 系大腦、且「贏 x/n」比 rollout_pursuer 少，
  改用贏最多的那個（或 `--rank wins`）。要不要改預設，等 §4.3 的配對評測。

## 8. 限制、下一步
- 躲者只跑排位版單發規則 12 局×2 種追者；追者側、對稱規則、2 發規則的大批對打都沒跑。
- ★ 選 lazy 100% 是因為推演表的勝局分數只看燃料；如果有局勢讓 lazy 推演輸、別的大腦贏，★ 會換大腦——這批 1008 次沒遇到。
- 決策時間只量一個幾何（inclined）、這台機器；比賽電腦不同要先用 `time` 量一次。
- 下一步：§4.3 的追者配對（copilot★、`--rank wins`、rollout_pursuer × rollout_evader／dv_evader／lazy_evader）。

## 9. 逐位元檢查
`copilot.py` 預設路徑：同一個局勢、改前（7c6f7c4）與改後的 `advise` JSON 與 `print_advice` 文字完全相同（去掉決策秒數；
預設大腦的 ranking_like 躲者中盤、2 發追者局勢各一）。`game/`、`physics/`、既有 `agents/` 沒有改動。
