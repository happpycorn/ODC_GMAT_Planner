# medal/（原 ODC_GMAT_DRL）—— 軌道設計競賽「決賽」追逃戰

第一屆軌道設計競賽（TASA / 淡江）**決賽（四強賽）** 的物理、解析/推演策略、DRL 訓練與當天作戰工具。初賽 9/5 已晉級（57 隊取前 8）；決賽 **2026-11-09 @ 大臺南會展中心**。

- **怎麼用** → 這份
- **問題本質、理論、為什麼這樣做、實測教訓** → [METHODOLOGY.md](METHODOLOGY.md)
- **每個實驗量到什麼（E1–E12）** → [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md)
- **全天總覽（排位賽＋金／銅牌賽）** → [docs/final/DAY_OVERVIEW.md](../docs/final/DAY_OVERVIEW.md)
- **新電腦安裝（兩個工具＋GUI 一次裝好）** → [docs/SETUP.md](../docs/SETUP.md)
- **當天流程** → [CONTEST_DAY_FINAL.md](CONTEST_DAY_FINAL.md)；賽前檢查 → [PRE_CONTEST_FINAL.md](PRE_CONTEST_FINAL.md)
- **做到哪、接下來做什麼** → [ROADMAP.md](ROADMAP.md)（進度同步在 Linear 專案 `ODC_GMAT_DRL`）

---

## 決賽賽制（一段話，2026-11-01 正式規則）

兩艘太空船在**純二體**下追逐 vs 躲避，**6 回合、雙方同時出手、互相看不到**，每回合起點一發（超過 ΔV_lim 等比例縮放），**總 Δv 無上限**。追方在回合內進到 R_cap 就贏；逃方撐完 6 回合**且半長軸 a 落在安全空域**才贏，穿越地球的一方判輸。ΔV_lim、R_cap、T_round、安全空域當場公告，公告後 10 分鐘分析，排位較優者選角色。比賽中禁網路與生成式 AI。規則與引擎差異見 [docs/FINAL_RULES_PLAN_20261101.md](docs/FINAL_RULES_PLAN_20261101.md)。

## 目前結論（一段話）

**躲方結構性佔優**：`safe_evader` 每回合算安全證書（追方怎麼推都碰不到的推力）並把 a 帶進安全空域，規則分布與六類對抗題共 1200 局全部 escape（E28、E29）。追方的機會只來自對手不算證書（直覺閃法被 `capture_pursuer` 抓 30–62%）或安全空域到不了。當天流程：`role_select.py` 選角色（Mac 126 s，`--fast` 39 s）→ 每回合 `copilot.py final advise`（Mac 1.3–4.9 s）。11-04 起軟凍結。下面「舊引擎」各節（rollout、RL、燃料比查表）是 11-01 前回合交替賽制的成果，保留作背景。

---

## 安裝

2026-11-06 起這個工具是 ODC_Program 的子資料夾 `medal/`（git subtree，保留原歷史），但仍是**獨立的 uv 專案**：
自己的 `pyproject.toml`、`uv.lock`、`.venv`，套件版本跟根目錄的排位賽工具不同（numpy 2.5 對 1.26）。
新電腦用根目錄的 `setup.sh` 一次裝好；只裝這邊就在 `medal/` 裡：

```bash
pip install uv
uv sync            # 每次 git pull 後跑一次
uv run pytest      # 58 項；有裝 GMAT 的機器會多跑 GMAT 重播一致性測試
```

GMAT（只用於驗證/彩排，不在訓練迴圈裡）預設路徑 `~/software/GMAT/GMAT/R2026a/bin/GmatConsole`，可用環境變數 `GMAT_CONSOLE` 覆寫。

---

## 常用指令

```bash
# 當天 copilot：局勢檔 → 戰況 + 各大腦建議（ECI/VNB/RSW）+ 推演 + ★ 推薦 + GMAT 驗證腳本
uv run python copilot.py init state.json
uv run python copilot.py import state.json GMAT_report.txt --pursuer-ship ShipP --evader-ship ShipE --mover pursuer
uv run python copilot.py advise state.json --gmat burn.script --verify
uv run python copilot.py drill --role evader --opponent rollout_pursuer            # 整場演練（無 GMAT）

# 當天流程彩排：GMAT 當真實世界，每回合 GMAT 重播 → import → advise → 下指令
uv run python tools/dress_rehearsal.py --role pursuer --opponent dv_evader
# 同上，但 GMAT 用排位賽官方全攝動模型、每回合把引擎重設成 GMAT 狀態、賽後 GMAT 判勝負（E18）
uv run python tools/dress_rehearsal.py --role evader --opponent rollout_pursuer \
    --rules configs/rulesets/ranking_like.json --force-model ranking_full

# 對打評測：追者 × 躲者 × 同一批隨機（規則, 幾何），輸出 reports/<name>.md
uv run python evaluate.py --pursuers "lambert_pursuer;rollout_pursuer" \
    --evaders "dv_evader;rollout_evader;escape_evader" --games 40 --rules ranges --scenario mixed
uv run python evaluate.py --rules configs/rulesets/symmetric.json ...      # 指定規則集

# 規則平衡地圖 / exploitability
uv run python tools/balance_sweep.py --axis max_dv_evader_mps=150,375,750,1500 --axis fuel_evader_mps=750,1500,3000
uv run python tools/exploitability.py --target rollout_pursuer --role pursuer --games 16

# GMAT 一致性：整局機動丟進 GMAT 重播、逐回合比位置
uv run python tools/gmat_verify.py --pursuer lambert_pursuer --evader dv_evader

# Self-play 訓練（BC → curriculum → league）與部署
uv run python train_selfplay.py --name sp4 --envs 12 --iters 12
uv run python tools/promote_model.py --run sp4 --games 60
```

**Agent 規格字串**：`coast`、`random`、`lambert_pursuer`、`lambert_pursuer_fast`、`dv_evader`、`dv_evader_fast`、`escape_evader`、`adaptive_evader`、`minimax_pursuer`、`minimax_evader(_fast)`、`rollout_pursuer`、`rollout_evader`、`sb3:<模型.zip>`，或 JSON（例 `{"name":"rollout_pursuer","workers":8}`、`{"name":"pool","specs":[...]}`）。多個規格用 `;` 分隔。

---

## Repo 佈局

```
physics/           軌道物理
  propagator.py      get_r0_v0、propagate（DOP853）         ← vendored 自 Planner（PROVENANCE.md）
  core_math.py       動力學、J2/J3/J4、VNB、近地點檢查       ← vendored
  scorer.py          初賽官方計分公式                         ← vendored
  lambert.py         numba Izzo Lambert（多圈），與 poliastro 比對到機器精度
  intercept.py       追擊所需 Δv 掃描（TOF × 圈數 × 分支 + J2 打靶）
  coast.py           雙船滑行 + 窗口內連續偵測捕獲/撞地/最近接近
  frames.py          RSW(LVLH)、VNB、rv2coe
game/              純遊戲核心（與 gym 解耦；搜尋、評測、copilot 共用）
  rules.py           Rules（佔位規則，含 capture_mode）+ RuleRanges（規則分布）
  scenarios.py       初始幾何家族（near_coplanar / inclined / wild / official_sample / default）
  core.py            Game：回合推進、Δv 裁切、燃料帳、勝負、歷程、中途快照
  obs.py / actions.py  RL 觀測、action↔Δv（direct / guided）
  state_io.py        GMAT 報表 → 局勢檔（含單位防呆）
agents/            策略
  base.py            Agent 介面、coast、random、PoolAgent
  analytic.py        LambertPursuer、DvEvader、EscapeEvader、存活檢查/救命推力、追擊所需 Δv
  rollout.py         RolloutPlanner（★ 當天主腦，可平行）
  adaptive.py        AdaptiveEvader（依規則切逃逸；實測不當預設）
  search.py          2-ply 極小極大（實驗性，較弱）
  rl.py              SB3Agent（含撞地防呆）
envs/final_env.py  gym 包裝：單 agent + 可插拔對手、role 可隨機、勢能型塑形
evaluation/        對打評測系統
tools/             gmat_verify、dress_rehearsal、balance_sweep、exploitability、promote_model、compare_lambert_poliastro
configs/           rules_template.json、rulesets/（symmetric / pursuer_fuel_2x / evader_small_burn_big_fuel）
models/            已部署 RL 模型（sp3）+ PROMOTED.md
reports/           評測/彩排報表（.md 進 git）
docs/EXPERIMENTS.md 實驗紀錄
evaluate.py  copilot.py  train_selfplay.py
tests/             pytest
```

---

## 現況（2026-10-20）

- ✅ 物理：自寫 Lambert / 攔截掃描 / 連續事件偵測；**GMAT 重播位置差 < 10 m**（degree 0/2/4）
- ✅ 遊戲核心、解析 agent、**rollout 規劃器**、對打評測、規則平衡地圖（HAP-101/102/103/106）
- ✅ self-play 管線與 sp3 訓練（持平專家）、RL × rollout 整合評測（無增益）（HAP-54/105）
- ✅ exploitability 測試（HAP-108）、copilot（匯入、推演排序、GMAT 腳本）、當天手冊、GMAT 彩排工具（HAP-104/109/55）
- ✅ 排位賽版規則（250/3000）評測：逃逸翻盤成最弱、rollout 躲者最強、強化版 rollout 追者（E14–E16）
- ✅ 一回合多發（`Rules.burns_per_turn`，HAP-107）：多發大幅利於追者（E17）
- ✅ 全攝動 GMAT 彩排（`--force-model ranking_full`）：每回合匯入官方狀態時，引擎單窗口誤差公尺級、勝負與 GMAT 一致（E18）
- ⏳ 決賽規則待官方公告（HAP-50）→ 公告後在正式規則上重跑關鍵評測並鎖定大腦
