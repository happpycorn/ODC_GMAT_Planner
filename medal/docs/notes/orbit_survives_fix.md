# orbit_survives 漏判修正：弧終點半徑檢查（開關 ODC_STRICT_SURVIVAL，2026-10-22）

> **2026-10-22 更新**：使用者決定改成**預設開**（`STRICT_SURVIVAL_DEFAULT = 1`）；`ODC_STRICT_SURVIVAL=0` 回到舊行為（與改前逐位元相同）。下文寫的「預設關」是當時的狀態。

## 1. 問題
`agents/analytic.py::orbit_survives` 在密切近地點低於「撞地高度 + 50 km」時只問「剩餘時間內會不會飛過近地點」，
不會就判安全。近地點在地底下時，太空船**還沒到近地點就先穿過撞地高度**——`physics/core_math.py::reaches_perigee`
說明裡「弧內不經過近地點 → 最低點是兩端取小」只做了一半。E22（對稱規則尾聲大推力閃避撞地，`agents/evader_lab.py`
另寫了 `strict_survives` 繞過）、E23（`docs/notes/flyby_geometry.md` §7：飛掠局 Lambert／sb3 追者撞地、
flyby_pursuer 下 sb3 躲者撞地而輸）都踩到。用它的地方：LambertPursuer、DvEvader、EscapeEvader、`rescue_burn`、
SB3Agent 的安全過濾、`gap_burn_survives`、minimax 候選、copilot 的「不推安全／推完安全」顯示。

## 2. 改了什麼（預設關，舊行為逐位元不變，見 §8）
- `agents/analytic.py`：
  - `orbit_survives(..., strict=None)`：近地點低於門檻、horizon 內不經過近地點時，開關開 → 再要求 **horizon 結束時的
    二體半徑 ≥ 撞地高度 + 裕度**（同一個 50 km）；關 → 舊行為（直接安全）。起點不檢查（推力改不了它、此刻沒撞地）。
    這一支的雙曲線只可能是往外飛（往內飛 `reaches_perigee` 一律回 True），半徑單調增加 → 安全，同舊。
  - `_radius_after_coast(r, v, mu, dt)`：二體 Kepler（Newton + [0, 2π] 夾擠、跳出就二分），純 float，**8 µs/次**，只在那一支呼叫。
  - 開關：環境變數 `ODC_STRICT_SURVIVAL`（1/0，也認 on/off/true/false/yes/no；evaluate.py 子行程與 rollout／copilot 行程池會繼承）
    ＋ 模組常數 `STRICT_SURVIVAL_DEFAULT = 0`；`strict=True/False` 直接覆寫。環境變數只在那一支才讀。
- **為什麼用二體末端、不照 `strict_survives` 實際推進**：(a) 二體下「不經過近地點 → 最低點在兩端」是精確的，正好補完
  `reaches_perigee` 的設計；(b) O(1)：`orbit_survives` 一次決策會被叫幾十到兩百多次（`rescue_burn` 最多 208 次），
  J2 逐 60 s 推進到比賽結束要上百次積分；(c) 驗證（隨機 LEO 近圓 + 0–1.5 km/s 任意方向推力 + horizon 60–12,000 s，
  20,000 筆裡 1,544 筆落在漏判那一支、其中 618 筆引擎（J2、coast_pair 連續偵測）真的撞地）：
  舊行為 618 筆全放行；二體末端 **0 筆放行撞地**、2 筆放行但途中低於 150 km（沒撞）、2 筆多擋；
  一次 J2 propagate 到末端 0/0/0。二體 vs J2 末端半徑差中位 3.9 km、95% 16.6 km、最大 44.8 km（< 50 km 裕度）。
  二體 Kepler 跟 `propagate(gravity_degree=0)` 差 ≤ 1.2e-5 km。
- 新測試 `tests/test_orbit_survives_fix.py`（14 項）：開關解析與預設；E22 型態（對稱 1500/3000、剩 1350 s 往下+往後推 1500 m/s，
  開=不安全、關=安全、引擎真的撞地；DvEvader 53 個候選開了放行的都不撞、舊行為放行的有會撞的）；E23 兩個實際對局快照
  （flyby_pursuer 第 1 局 sb3 躲者 t=3900 s、flyby 第 1 局 Lambert 追者 t=6000 s：舊放行、開=不安全、推完滑行真的撞地）；
  6 個幾何家族開賽狀態 × 104 種推力兩邊一致（開了只會更嚴，LEO 開賽完全一致）；150 筆隨機漏判區對引擎：開了 0 筆放行撞地；
  Kepler 半徑對數值二體；往外飛雙曲線兩邊都安全。
- 報表：`reports/survfix_paired.md`（逐局配對表＋結局改變清單）、`reports/survfix_<組>_{off,on}.md`。

## 3. 設定
seed 1、每配對 24 局、4 worker、`nice 10`、`NUMBA_NUM_THREADS=1`；關／開各跑一次同一批幾何：
```bash
ODC_STRICT_SURVIVAL={0,1} uv run python evaluate.py --rules configs/rulesets/{ranking_like,symmetric}.json --games 24 --seed 1 --workers 4 \
  --pursuers "lambert_pursuer,rollout_pursuer" --evaders "dv_evader,rollout_evader,escape_evader" --name survfix_<組>_{off,on}
ODC_STRICT_SURVIVAL={0,1} uv run python evaluate.py --rules configs/rulesets/flyby_ranking_like.json --scenario {flyby,flyby_pursuer} \
  --games 24 --seed 1 --workers 4 --pursuers "lambert_pursuer;rollout_pursuer;sb3:models/pursuer.zip" \
  --evaders "coast;dv_evader;rollout_evader;escape_evader;sb3:models/evader.zip" --name survfix_<組>_{off,on}
```

## 4. 結果（關 → 開，逐局配對；p = 勝負翻轉局的雙尾符號檢定）

| 組 | 局數 | 撞地 關 → 開 | 有變的局 | 勝負翻轉（只關追者勝 / 只開追者勝） | 追者勝率 關 → 開 |
|---|---|---|---|---|---|
| ranking_like（250/3000、mixed） | 144 | 0 → 0 | 2 | 0 / 0（p = 1） | 63% [55–71] → 63% [55–71] |
| symmetric（1500/3000、mixed） | 144 | 0 → 0 | 3 | 0 / 0（p = 1） | 21% [15–28] → 21% [15–28] |
| flyby（LEO 追者 vs 雙曲線躲者） | 360 | 追者 **64 → 0** | 66 | 0 / 0（p = 1） | 16% [13–20] → 16% [13–20] |
| flyby_pursuer（雙曲線追者 vs LEO 躲者） | 360 | 躲者 **30 → 0** | 74 | **30 / 0** | 27% [22–31] → 18% [15–23] |

- **flyby**：Lambert 追者撞地 31 → 0（coast 1、dv 8、rollout 13、escape 5、sb3 4）、sb3 追者 33 → 0（6、8、9、5、5）、rollout 追者 0 → 0。
  64 局全部 crash_pursuer → timeout、最近距離不變——撞地都發生在已經追不到之後，**勝負不變**。
- **flyby_pursuer**：躲者撞地全部消失，30 局翻成躲者勝、反向 0 局。逐配對：sb3 躲者 vs Lambert 29% → 0%（7/0，p = 0.016）、
  vs rollout 42% → 0%（10/0，p = 0.002）、vs sb3 追者 46% → 4%（10/0，p = 0.002）；escape 躲者 vs Lambert 8% → 0%（2/0，p = 0.5）、
  vs sb3 追者 4% → 0%（1/0，p = 1）。合併 30/0（p = 2e-9，局間共用幾何不獨立，僅供參考）。
  另外 44 局只有時間／燃料／最近距離變（躲者閃法改了），勝負沒變。
- **四組合計 1,008 局：撞地 94 → 0，開了之後沒有任何一局變差**（沒有新撞地、沒有反向翻轉）。
- 決策時間看不出差異：symmetric／flyby／flyby_pursuer 關開差 ±7% 內；ranking_like 開 +35%，但同一批只有 2 局有任何改變，
  應是機器負載（另兩個任務同時在跑），不是修正本身（那一支 8 µs/次）。

## 5. 另一組規則上的確認
對稱 1500/3000（mixed）也是 0 撞地、0 翻轉，跟 250/3000 一樣：LEO 局裡漏判那一支只在剩餘時間 < 一個週期時出現，評測裡幾乎碰不到。
飛掠 1500/3000（flyby_symmetric）沒跑：flyby_geometry §4 記錄那組規則下本來就 0 局撞地。

## 6. 結論與預設建議
- 修正把漏判那一支補成二體精確，飛掠兩個家族的自己撞地 94 → 0；會因此**改變勝負**的是 LEO 躲者（sb3 躲者三個配對 p ≤ 0.016），
  追者端只是把「超時輸」前的撞地拿掉。LEO 規則（mixed）幾乎不受影響。沒有測到任何副作用。
- **建議預設開**（`STRICT_SURVIVAL_DEFAULT = 1`）：這是 bug 修正、零成本，而且當天 copilot 的「推完安全」顯示也會變正確；
  只靠環境變數容易在比賽當天忘記設。這是**有意的行為改變**，翻預設時要一起做：
  1. 改兩個依賴舊漏判的既有測試（`ODC_STRICT_SURVIVAL=1` 全套 pytest：167 passed、2 failed，正好這兩個）：
     `tests/test_evader_lab.py::test_strict_survives_catches_crash_before_perigee`（`assert orbit_survives(...)` 寫的是「舊檢查的漏判」
     → 改成 `strict=False`）、`tests/test_flyby.py::test_gmat_full_perturbation_flyby_pursuer_runs`（GMAT 測試，靠 dv_evader_fast
     漏判撞地來測「撞地後不補窗口」→ 改成 `strict=False` 的情境或用環境變數 0）；以及本檔 `test_switch_default_is_old_behavior` 的預設值。
  2. 在 EXPERIMENTS 記錄：E23 飛掠表格裡的撞地數（Lambert 31、sb3 追者 33、sb3 躲者撞地）是舊行為下的數字。
  3. sb3 策略本身不變：這個檢查只在部署時的安全過濾（`SB3Agent.act`：推完撐不到就減半／救命）套用，翻預設不用重訓。
- 不翻預設的話：比賽當天跑 copilot／彩排前 `export ODC_STRICT_SURVIVAL=1`。

## 7. 限制、沒做的事、建議下一步
- 二體末端：J2 讓末端半徑差到 ~45 km（< 50 km 裕度），隨機樣本 2/1,544 筆途中低於 150 km 但沒撞；要更緊可改成一次 J2 propagate（同樣 O(1) 次積分，
  但時間隨 horizon 增加）。起點半徑不檢查。往內飛的雙曲線仍一律判不安全（保守，同舊）。
- 沒跑：多發規則（`gap_burn_survives` 間隔後的檢查也會變嚴）、flyby_symmetric、seed 2 以上、LazyEvader3（它有自己的 `strict_survives`，
  更保守：J2 逐 60 s、底線 10 km、多推 300 s；開關開後兩者重疊）、copilot drill／GMAT 彩排。
- E22 原始對局（對稱 seed 1 第 3 局、LazyEvader2）沒重跑；測試用同型態的構造局面，symmetric 這次 24 局 × 6 配對 0 撞地。

## 8. 逐位元檢查
同一個 worktree、同一份 numba 快取，改前（7c6f7c4）vs 最終程式（開關未設定），`evaluate.py --rules {default, ranges,
configs/rulesets/ranking_like.json} --games 6 --seed 0`（mixed），追者 lambert/rollout × 躲者 dv/rollout/escape，逐局比 outcome、winner、
t_end、t_max、turns、min_dist_km、final_dist_km、used_pursuer_mps、used_evader_mps（浮點逐位元）：**default 36/36、ranges 36/36、
ranking_like 36/36 完全相同**。`uv run pytest -q`：169 passed（原 155 + 新 14）。
