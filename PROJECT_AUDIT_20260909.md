# 專案盤點與整理（2026-09-09）

初賽結束後的一次全專案盤點:分清**現役 / 初賽專用 / 棄用**,挑出**潛在問題**,並對到 Linear 卡務。
Claude 讀過全部現役程式(`main.py` + 6 個 `src/` 模組)、掃過 `scratch_overnight/` 66 個檔與根目錄腳本後整理。

> **一句話結論**:核心程式品質高、現役路徑乾淨;混亂主要在**外圍**(大量初賽一次性實驗混在 `scratch_overnight/`、`core_math.py` 有 ~430 行棄用傳播器、文件/runbook 有初賽專用的沒標記)。**最重要的潛在問題只有一個**:Earth-collision 只在搜尋 fitness 裡擋,不在繳交路徑上擋——而初賽已證實這是**官方失格線**(撞地球的兩隊被判 F)。

---

## 1. 現役核心(實際會跑的東西)

`main.py` 流程:
```
load_or_create_config + validate_config
      → run_study_over_revs(config)          # REVS=0 / REVS=LAMBERT_MAX_REVS 各跑一次取較好(REVS_ENSEMBLE)
          → MissionOptimizer (L-SHADE + 種子 + NLP 微調, fast_fitness_evaluator 內含 Earth-safe 判定)
      → print_score_breakdown                # 分數三塊 + 交換率
      → script_generator → outputs/output.txt # 含 GMAT DC 打靶
      → run_gmat_verification                 # 無頭 GmatConsole
      → (固定燃燒版) script_generator → output_submit.txt → 再驗一次  # 建議繳交這份
      → append_run_history
```

現役模組(全部讀過):

| 檔案 | 行數 | 角色 | 狀態 |
|---|---|---|---|
| `src/optimizer.py` | 2201 | L-SHADE 搜尋、種子、Lambert、拆分、REVS 集成、計分重播 | 現役,巨大 |
| `src/core_math.py` | 740 | 物理引擎:DOP853 傳播、J2/J3/J4、Earth-safe 判定 | 現役(但含棄用,見 §3) |
| `main.py` | 538 | 進入點/流程/GMAT 驗證/繳交腳本 | 現役 |
| `src/script_generator.py` | 516 | 產 GMAT script(DC 版 + 固定燃燒版,含雙曲線相機) | 現役 |
| `src/config_validator.py` | 381 | config 欄位/值域驗證(已支援雙曲線 A) | 現役,品質高 |
| `src/scorer.py` | 64 | 官方計分公式(距離50 + 時間25 + 燃料25 − 罰分) | 現役 |
| `src/propagator.py` | 87 | `get_r0_v0`(poliastro)+ DOP853 包裝 | 現役 |

根目錄支援腳本(都還 wired 到 `src`):`feasibility.py`(合法解存不存在)、`check_problem.py`(檢視題目)、`sweep_burns.py`(棒數兩階段掃描)、`run_regression.py`(子行程回歸)。

---

## 2. 現役設定的注意點(非 bug,但要知道)

- `main.py` 的 `DEFAULT_CONFIG`:`GRAVITY_DEGREE=2`(J2)、`k_t/C_t/k_v/C_v` 是**佔位值**(0.0001/11000/0.005/1200),不是任何一場真實比賽的數字。初賽用的是 `configs/contest.json`(**Degree=0 點質量**、真實計分參數)。→ **跑之前務必確認在哪個 config**;決賽力模未知(見 §5)。
- `configs/` 整個被 gitignore,換機器不會帶過來。

---

## 3. 棄用 / 參考碼(用不到)

- **`core_math.py` 裡的 `propagate_rk45` + `propagate_encke`(含 `rk45_step`/`encke_*`,約 430 行)**:8/14 探索期產物,驗證正確但比 DOP853 慢,**現役、scratch 都沒有任何地方 import**。純參考殘留。→ 建議:抽到 `src/_reference_propagators.py` 或直接刪(git 有歷史)。留著只是讓 740 行的檔更難讀。
- **`scratch_overnight/` ~66 檔**,絕大多數是**初賽期一次性實驗 + 結果 dump**:
  - 一次性實驗(可封存):`design_*.py`×6、`mb_*.py`×8、`split_test1~4.py`、`verify_*.py`、`inc_sweep*.py`、`inc_aop_adversarial.py`、`decode_*.py`、`bonus_resonance_test.py`、`reverify_weird_test.py`、`proxy_gap.py`、`gtoc9_*`×5(+csv)、`full_budget_ab_*`
  - 結果 dump(可 gitignore/封存):`*_results.json`、`*.npy`、`porkchop.png`
  - **值得保留的可重用工具**(finals 用得到):`porkchop_oracle_sweep.py`、`porkchop_verify*.py`、`monotonicity_harness.py`、`penalty_wall_probe.py`、`sample_pareto_frontier.py`、`degradation_audit.py`、`runtime_ceiling.py`、`probe_hyperbolic_A.py`、`sweep_hyperbolic_limits.py`、`known_answer_suite.py`、`xcheck_lambert_pykep.py`、`gmat/`(DC_ALGORITHMS、perigee_xcheck、yukon)
  - → 建議:`scratch_overnight/` 分成 `tools/`(可重用)與 `archive_prelim/`(一次性),結果 dump 加進 gitignore。

---

## 4. 初賽專用 vs 決賽(文件層)

初賽已結束(2026-09-05,實質第一——撞地球兩隊 F 失格、Team15 為主辦內部炸魚隊)。以下是**初賽專用、現在是歷史**:
- `CONTEST_DAY.md`(504 行,初賽當天手冊)、`runbooks/情境A/B/C`(初賽當天站別卡)、`SCENARIOS.md`(619 行)
- `STATUS.md`(2104 行**累積式 log**)——歷史價值高但已臃腫,決賽開始前值得**封頂**(標一條「初賽線」,決賽另起新段或新檔)。
- → 建議:開 `docs/prelim/` 收 CONTEST_DAY / runbooks;`STATUS.md` 加初賽封頂線。

---

## 5. 潛在問題(依嚴重度)

| # | 嚴重度 | 問題 | 現況 / 建議 |
|---|---|---|---|
| **P1** | 🔴 **決勝級** | **Earth-collision 只在搜尋 fitness(`fast_fitness_evaluator`)擋,不在 `_replay_mission`/`mission_metrics`/GMAT/繳交路徑擋**。初賽已證實這是**官方失格線**(撞地球兩隊被判 F);我們自己的 99.996 也是靠 `fast_fitness_evaluator` 才擋下(replay/GMAT 都放行)。手工解或固定燃燒繳交路徑目前**沒有硬性 Earth-safe 閘門**。 | = HAP-48。**升級**:繳交前對最終解強制跑一次碰撞閘門,不過就擋下不准繳。 |
| **P2** | 🟠 高(決賽) | **Earth-safe 判定是點質量解析式**(`reaches_perigee`/`check_constraints`,"J2 在 100s 尺度改不動")。決賽若開攝動,長弧近地點會漂,解析判定不再精確——而它現在是失格線。 | = HAP-46 §5 / HAP-20。攝動開時要切數值密集取樣判定。 |
| **P3** | 🟠 高(決賽) | **雙曲線 A 路徑從未端到端跑過**。防禦大多已就位(T_max guard、validator、GMAT 相機、radius-range),但沒有一個雙曲線測資實跑過 `main.py`+GMAT。 | = HAP-46 / HAP-36。建雙曲線測資實跑。 |
| P4 | 🟡 中 | `config_validator` 對雙曲線 A **沒檢查 TA 是否落在漸近線內**(\|TA\|<arccos(−1/e))。給錯會在 poliastro `get_r0_v0` 才炸,不是早攔。 | 小補丁:加一條雙曲線 TA 範圍檢查。 |
| P5 | 🟡 中 | **拆分/路線只達到 Earth-safe 家族**,但初賽真正贏我們的(炸魚隊)是同一條解精修更緊。2nd→1st 的槓桿是精度,不是新解。 | = HAP-47(取代貪婪 relay)。 |
| P6 | 🟢 低 | ~430 行棄用傳播器 + 66 個 scratch 混雜,降低可讀性/新人上手。 | = §3 清理。 |

---

## 6. Linear 卡務對照(提案,待確認再執行)

**保留 + 升級優先級:**
- **HAP-48**(collision gate bug)→ 🔴 從「Med bug」升成**繳交阻塞閘門**,附初賽證據(官方 F 失格 + 我們的 99.996)。**這是決賽第一優先。**
- **HAP-50**(向主辦確認決賽規則)→ 記錄已知事實「**官方會判地表碰撞失格**(初賽 F)」,決賽再確認細節。High 維持。
- **HAP-46**(route-first + 自動拆分,雙曲線)、**HAP-47**(更優拆分取代貪婪 relay)→ 現在有明確動機(2nd→1st 是精度),維持 High/Med。
- **HAP-36 / 49 / 56 / 51-54**(決賽雙曲線 + RL 追逃 env)→ 決賽主線,保留。

**可能已完成、建議關閉(待你確認):**
- **HAP-42**(REVS=4 預設讓某些幾何變差)→ commit `03a0b3b` 的 **REVS_ENSEMBLE**(REVS=0/4 各跑取較好)看起來就是這張的解。→ 若同意,**關閉**。
- **HAP-35**(當天多 seed 集成)→ 是否被 REVS_ENSEMBLE 部分覆蓋?待確認。

**建議新開:**
- **[cleanup]** 移除/封存棄用傳播器(RK45+Encke, ~430 行)+ scratch 分 `tools/` 與 `archive_prelim/` + 結果 dump gitignore。(§3)
- **[docs]** 初賽材料封存到 `docs/prelim/`,`STATUS.md` 加初賽封頂線。(§4)
- **[validation]** 雙曲線 A 的 TA 漸近線範圍檢查。(P4)

**已標 Done(確認是否已 closed):** HAP-25/26/30/31/32/34/37/38/39/41。

---

## 7. 建議動手順序(決賽導向)

1. **P1 / HAP-48**:繳交前硬性 Earth-safe 閘門——這是唯一「決勝級」的洞,先補。
2. **P3 / HAP-46**:建雙曲線測資實跑,讓 P2(攝動下碰撞判定)現形。
3. **清理(P6 §3、§4)**:降噪,讓 1/2 做起來不被雜訊干擾。
4. **P5 / HAP-47**:精度層(2nd→1st),賽前有餘力再做。
