# 雙曲線／飛掠幾何（清單第 4 項，2026-10-21）

## 1. 問題
排位賽的外星船 A 是雙曲線飛掠，T_max =「A 過近地點後地心距離第一次增加到任務邊界的時刻」（開賽公布）。四強賽可能沿用：
一方（多半是躲者）雙曲線飛掠、另一方從 LEO 攔截。引擎、agent、copilot、GMAT 重播都只在橢圓 LEO 測過。
要回答：(1) 各元件在雙曲線下會不會當機、出 nan/inf、判錯；(2) 飛掠幾何上大腦怎麼排、勝率多少。

## 2. 改了什麼（預設規則逐位元不變，見 §8）
- `game/rules.py`：新欄位 `t_max_boundary_km`（預設 0 = 舊定義）。> 0 且 `t_max_sec` <= 0 時用排位賽定義。
- `game/core.py`：
  - `kepler_exit_time`（二體解析，雙曲線／橢圓，同 Planner `src/tmax.py`）、`boundary_exit_time`（先解析確認穿越存在，
    再用引擎同一套重力分段傳播 + 二分到 0.1 ms）、`flyby_side`（初始比能量較高的一方）、`specific_energy`。
  - `Game.__init__` 的 T_max：`t_max_sec` > 0 → 直接用；`t_max_boundary_km` > 0 → 飛掠方飛出邊界的時刻；否則週期倍數。
    **修 bug**：追者初始軌道是雙曲線時舊版 T_max = inf，比賽永遠不會超時（雙方都不抓不撞就是無窮迴圈）→ 改用躲者週期；
    兩方都是雙曲線丟 ValueError。新屬性 `Game.t_max_basis`（`t_max_sec` / `boundary(evader)` / `periods(pursuer)` …）。
- `game/scenarios.py`：新家族 `flyby`、`flyby_pursuer`（設計見 §3）；`FAMILIES` 末尾加兩個。`mixed` 不變
  （跟改前模組比 1200 筆抽樣與共用亂數流消耗完全相同；`tests/test_flyby.py` 有回歸值）。
- `copilot.py`：`_perigee_alt` 改用 h²/(μ(1+e))（舊版 sma <= 0 回傳 nan，雙曲線方戰況印 `nan`）；戰況多 `orbit_type`，
  有雙曲線方時印「飛掠：evader hyperbolic (v_inf …)」。沒動 DEFAULT_BRAINS／DEFAULT_OPP_MODELS。
- `game/state_io.py`：GMAT 六根數報表接受雙曲線（ECC > 1、SMA < 0、近地點在地表上、TA 在漸近線內），舊版一律丟
  「六根數不合理」；SMA 正負號寫反、TA 超出漸近線、SMA 像公尺都會擋。
- `tools/gmat_verify.py`：`gmat_truth` 只在**捕獲**結束時把最後窗口補滿；撞地結束時不補（舊版會讓 GMAT 在大氣層裡積分，
  `tests/test_flyby.py` 那局 3000 s 的飛掠實測 147 s、密集報表 15 萬列；改後 13 s）。
- 新規則集 `configs/rulesets/flyby_ranking_like.json`（250/3000 + 邊界 40,000 km）、`flyby_symmetric.json`（1500/3000 + 邊界）。
- 新測試 `tests/test_flyby.py`（49 項）；報表 `reports/flyby_ranking_like_s1.md`、`flyby_symmetric_s1.md`、`flyby_pursuer_ranking_like_s1.md`。
- 沒改：`game/obs.py`（飛掠下觀測全部有限，不需要防呆；但飛掠方在三、四萬 km 時高度特徵 `alt_*` 到 30 以上，遠超 RL 訓練分布）、
  `physics/frames.py`（`rv2coe` 雙曲線來回已驗證；只剩拋物線 e≈1 會給 sma=inf，現在沒有呼叫端）。

## 3. 設定
**flyby 家族（先選交會點與時刻再倒推）**：躲者雙曲線近地點高度 U(300, 2000) km、v∞ U(1, 4) km/s、軌道面隨機；
交會點取躲者軌道上近地點附近、高度 ≤ 2000 km 的一點，開賽後 U(900, 5400) s 經過；追者圓軌道過交會點附近：
軌道面繞交會點徑向轉 ±60°、到達時間差 ±60 s、高度差 ±30 km、側傾 ±0.3°，再二體倒推回 t=0；躲者開賽時要在邊界 95% 內。
seed 1 的 24 局：T_max 1.9–3.35 h（中位 2.55）、純滑行最近距離 17–432 km（中位 152）、追者一發攔截不動躲者所需 11–416 m/s（中位 46）。
J2 下的 T_max 跟二體解析差 ≤ 2 s。`flyby_pursuer` 是同一組軌道角色對調（同 seed 同幾何）。邊界 40,000 km 是佔位（`FLYBY_BOUNDARY_KM`）。

評測（5 worker、nice 10、約 9 分鐘）：
```bash
STRONG='{"name":"rollout_pursuer","opponents":["coast","dv_evader_fast",{"name":"rollout_evader","candidates":["dv_evader_fast"],"opponents":["lambert_pursuer_fast"]}]}'
uv run python evaluate.py --rules configs/rulesets/flyby_ranking_like.json --scenario flyby --games 24 --seed 1 --workers 5 \
  --pursuers "lambert_pursuer;rollout_pursuer;$STRONG;sb3:models/pursuer.zip" \
  --evaders "coast;dv_evader;rollout_evader;escape_evader;sb3:models/evader.zip" --name flyby_ranking_like_s1
# 第二組規則：--rules configs/rulesets/flyby_symmetric.json --name flyby_symmetric_s1
# 角色對調：--scenario flyby_pursuer --games 12 --name flyby_pursuer_ranking_like_s1
```

## 4. 結果
**追者勝率**（flyby、250/3000 + 邊界、seed 1、每格 n=24，[Wilson 95%]）：

| 追者 \ 躲者 | coast | dv_evader | rollout_evader | escape_evader | sb3 躲者 |
|---|---|---|---|---|---|
| lambert_pursuer | 92% [74–98] | 0% [0–14] | 0% [0–14] | 0% [0–14] | 0% [0–14] |
| rollout_pursuer | 92% [74–98] | 0% | 0% | 0% | 0% |
| 強化版 rollout | 92% [74–98] | 0% | 0% | 0% | 0% |
| sb3 追者 | 50% [31–69] | 0% | 0% | 0% | 8% [2–26] |

- 會動的躲者**全部活下來**（4 種躲者 × 3 個解析/rollout 追者 = 288 局 0 局被抓）。rollout_evader 最省：平均只花 260 m/s
  （多半一發），最近距離中位 46 km；dv_evader／escape_evader／sb3 躲者都把 3000 m/s 幾乎燒光。
- 不動的躲者：22/24 被抓；抓不到的 2 局（#16、#23）是開賽約 1000 s 就交會、一發要 400 m/s 以上（> 單發 250），兩發來不及。
- **強化版 rollout 追者沒有任何好處**：跟預設 rollout 追者 120/120 局結局與結束時刻完全相同，決策 ~0.5–1 s/步（預設 ~0.05–0.08 s）。
- 為什麼追者贏不了：交會時相對速度 3–10 km/s，捕獲只能在追者那一窗口（≤ 300 s）內完成；躲者在前一窗口一發就能把交會點移
  ≥ 250 m/s × 300 s = 75 km，追者最後一窗口最多修 250 m/s × 300 s = 75 km。把交會提早到 600–1500 s 也一樣
  （臨時把 `FLYBY_T_ENC_SEC` 改成 (600, 1500)；lambert/rollout × dv/rollout/escape，12 局 × 6 配對 = 0/72）。
- 角色對調（flyby_pursuer，n=12）：追者對 coast 100%、對 dv/rollout 躲者 0%；對 escape 0–8%、sb3 躲者 42–58% **全部是躲者自己撞地**
  （見 §7 的 orbit_survives 漏洞）。

**GMAT 重播**（flyby 第 0 局、rollout 追者，`tools/gmat_verify.py`）：J2（引擎同款）39 回合、3.2 h，雙方位置差 ≤ 2.2 m；
排位賽全攝動模型下 LEO 追者 ≤ 0.83 km、雙曲線躲者 ≤ 56 m。vs coast 那局全攝動下同一時刻抓到（d_min 0.41 km）。
rollout_evader 的勝局邊緣不少（最近距離 < 6 km 有 5/72、< 10 km 有 15/72）；把 < 7 km 的 7 局用 GMAT 全攝動重判（`gmat_truth`），
**全部仍沒進捕獲球**（d_min 5.98–6.87 km，比引擎大 −0.01～+0.37 km）。

**copilot drill**（flyby_ranking_like、`--scenario flyby --seed 1`，預設大腦與對手模型，各一場、約 1.5–2 分鐘）：
我方追者 vs rollout_evader → 超時輸（最近 6.09 km，我方只花 60 m/s；推演表 17 次選 rollout、3 次選 Lambert，最多贏 1/4 個對手模型）；
我方躲者 vs rollout_pursuer → 超時贏（最近 5.95 km，花 250 m/s；19 回合都選 rollout_evader、4/4 對手模型都贏）。
戰況顯示「飛掠：evader hyperbolic (v_inf 3.85 km/s)」，近地點 1547／1170 km，全程沒有 nan、沒有例外。
`tools/dress_rehearsal.py --scenario flyby --rules configs/rulesets/flyby_ranking_like.json --max-turns 6` 也跑通（GMAT 匯入雙曲線狀態跟引擎差 0.26 m）。

**撞地（agent 自己的安全檢查漏洞，見 §7）**：250/3000 下 Lambert 追者 31/120 局、sb3 追者 33/120 局在已經追不到之後撞地
（勝負不變：本來就是超時輸）；flyby_pursuer 下 sb3 躲者 23/48、escape 躲者 2/48 撞地（**因此輸掉**）。1500/3000 下 0 局。

## 5. 另一組規則上的確認（flyby、1500/3000 + 邊界、同 24 局幾何）
| 追者 \ 躲者 | coast | dv_evader | rollout_evader | escape_evader | sb3 躲者 |
|---|---|---|---|---|---|
| lambert_pursuer | 100% [86–100] | 0% [0–14] | 0% [0–14] | 33% [18–53] | 38% [21–57] |
| rollout_pursuer | 96% [80–99] | 4% [1–20] | 0% [0–14] | 54% [35–72] | 54% [35–72] |
| 強化版 rollout | 96% | 4% | 0% | 54% | 54% |
| sb3 追者 | 38% [21–57] | 0% | 0% | 0% | 0% |

- rollout_evader 仍 72/72 存活（平均 1458 m/s）；dv_evader 70/72。
- **escape_evader 在大單發下會輸**：開局兩發 1500 m/s 就把燃料燒光，之後是不動的靶。同一批幾何 vs rollout 追者：
  250/3000 存活 100% → 1500/3000 46%（只有 250 規則活 13 局、反向 0，p = 0.0002）；1500/3000 下 rollout_evader 100% vs escape 46%（13:0，p = 0.0002）。
- 追者：rollout vs lambert 對 escape 54% vs 33%（5:0，p = 0.06，看不出顯著差異）；強化版跟 rollout 114/120 局結局與時刻相同、
  5 個躲者逐局勝負 0 局不一致。

## 6. 結論
- **元件**：引擎、Lambert／攔截掃描、所有 agent（coast、lambert(_fast)、dv_evader(_fast)、escape、rollout 追/躲、強化版、sb3 兩個）、
  觀測、copilot advise／drill、GMAT 匯入、當天流程彩排、GMAT 重播（J2 ≤ 2.2 m／39 回合／3.2 h）在雙曲線下都不當機、
  不出 nan/inf。
  修掉的：雙曲線追者 T_max = inf（無窮迴圈）、copilot 近地點 nan、GMAT 六根數匯入拒收雙曲線、gmat_truth 撞地後補窗口。
- **大腦排序（飛掠、躲者在雙曲線上）**：躲者用 **rollout_evader**（兩組規則都 100% 存活、最省油；但常只閃開 6–10 km，
  官方模型重判沒翻盤，當天若想要裕度可改看 dv_evader 的建議：最近 ≥ 64 km、代價是燒光燃料）；escape_evader 在大單發規則下會輸，
  不要用。追者用預設 rollout 或 Lambert 都一樣（對會動的躲者都是 0%，對不動的躲者 92–100%）；強化版 rollout 沒有增益、慢 10 倍。
- **策略含意**：雙曲線飛掠 + 對稱單發上限下，躲者只要在交會前一窗口推一發就安全——抽到躲者照 rollout_evader 打；抽到追者
  基本只能等對手失誤（不動、或把燃料一次燒光），重點是**別撞地**（Lambert 建議在追不到之後會把近地點壓到地表下，見 §7）。

## 7. 限制、沒做的事、建議下一步
- **agent 漏洞（沒修，`agents/` 不在範圍）**：`agents/analytic.py::orbit_survives` 在「剩餘時間內到不了近地點」時直接判安全，
  沒檢查弧的**終點**半徑（`reaches_perigee` 說明裡寫的「弧內不經過近地點 → 最低點在兩端」只做了一半）。剩餘時間比週期短時
  （飛掠局 T_max ≈ 1.3–2 個 LEO 週期；LEO 局理論上最後不到一個週期時也會，沒量）推完的軌道會在比賽結束前往下穿過撞地高度、
  但還沒到（地表下的）近地點。
  Lambert 追者（部分推力朝不可能的攔截解）、sb3 兩個、dv_evader_fast（escape 的後段）都會因此撞地。建議修法：
  `reaches_perigee` 為 False 時再看 horizon 結束時的半徑（二體 Kepler 或一次 `propagate`）≥ 撞地高度 + 裕度。重現：
  `uv run python evaluate.py --rules configs/rulesets/flyby_ranking_like.json --scenario flyby_pursuer --games 12 --seed 1 --pursuers rollout_pursuer --evaders "sb3:models/evader.zip" --workers 5`
  （game_id 1：t=3900 s 起 sb3 躲者每一發 orbit_survives=True，但推完純滑行 4100 s 就撞地、比賽還剩 4145 s；12 局裡 6 局 crash_evader）。
- **引擎回報小問題（沒修，`physics/coast.py` 不在範圍）**：撞地結束的那個 substep，`coast_pair` 先把整段 substep 的最近距離併進
  `min_dist` 才判撞地，所以 `window_min_dist_km`／`min_dist_km` 可能含撞地之後的幾十秒（實例：撞地 2452.7 s、最近距離記在 2460 s、
  差 90 km）。只影響回報與 rollout 輸局分數，不影響勝負判定。
- `physics/core_math.py::reaches_perigee` 的雙曲線分支（往內飛一律當成會過近地點）是保守的：只會多擋、不會漏擋
  （往外飛的雙曲線半徑單調增加，最低點就是起點；Lambert 弧的終點是目標本身，所以 `_arc_safe` 不受上面終點漏洞影響）。沒改。
- `Game.period()` 雙曲線回傳 6000 s：只在追者是雙曲線（flyby_pursuer）時用到（TOF 網格密度、need_horizon、copilot 推演長度），
  實測無害——flyby 上預設網格（24 點/週期）跟 10 倍密網格找到的最小攔截 Δv 中位比 1.001、最大 1.14（20 局）；flyby_pursuer
  追者對 coast 12/12 抓到。沒改。
- `tools/rule_lookup.py` 的 `tmax_periods()` 不認得邊界定義（會回報 t_max_periods）；不在範圍，沒改。
- 沒跑：`py:agents.evader_lab:LazyEvader3`（master 上沒有 `agents/evader_lab.py`）、multi-burn（2–3 發）飛掠、
  flyby_pursuer 的 1500/3000、不同邊界（官方邊界未公布；40,000 km 只是讓 T_max 落在 1–4 h）。
- 建議：若四強賽確定是飛掠，抽到追者時 copilot 推演表要把「撞地」標成最壞（現在 Lambert 系大腦撞地也只是「輸」），
  並先修 orbit_survives。

## 8. 逐位元檢查
同一個 worktree、同一份 numba 快取（沒動 physics/），改前（b4384b5）vs 最終程式：`evaluate.py --rules {default, ranges,
configs/rulesets/ranking_like.json} --games 6 --seed 0`（mixed），追者 lambert/rollout × 躲者 dv/rollout/escape/`sb3:models/evader.zip`，
逐局比 outcome、t_end、min_dist_km、used_pursuer_mps、used_evader_mps：**default 48/48、ranges 48/48、ranking_like 48/48 完全相同**。
（jsonl 的 rules 欄位多一個 `t_max_boundary_km: 0.0`。）`uv run pytest -q`：146 passed（原 97 + 新 49，含 GMAT 重播）。
