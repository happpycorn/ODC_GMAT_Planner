# 更強的躲者打法（清單第 2 項）

## 1. 問題
照排位賽數字的規則（`ranking_like.json`，雙方單發 250 m/s、燃料 3000）下，最強的躲者 `rollout_evader` 被強化版
rollout 追者（STRONG，E16）抓到 71%，一回合可多發時連一般 rollout 追者都抓到 75–83%（E17）。11/9 抽到躲者時
要有一個顯著更難抓的大腦。

**診斷**（seed 1、24 局，`reports/evader_base_rl_s1.md`，與 E16/E19 逐數字相同）：STRONG 抓到 rollout_evader 的
17 局，躲者**全部**把 3000 m/s 用光，被抓都在後段（t ≈ 20,000–27,000 s）。逐回合重播（第 1 局）：躲者每個回合推滿
250 m/s，t = 8,100 s 就沒油；追者那時還有 940 m/s，之後幾乎只滑行，t = 22,600 s 抓到。原因：推演勝局的
tie-break 偏好「終局距離遠」，續行 `dv_evader_fast` 也幾乎每回合推，所以推演看不出留油的價值。

## 2. 改了什麼（只新增，既有程式與預設值都沒動）
- `agents/evader_lab.py`（規格 `py:agents.evader_lab:<類別>`）
  - **`LazyEvader3`（建議採用）**：平常不推，**只有受威脅才閃**，閃法沿用 DvEvader（26 方向 × {1.0, 0.4}）。
    威脅 = 下列任一：不推的話會撞地；我這個窗口內就會被抓；我滑完窗口後，追者下一回合在窗口內（+60 s 寬限）一發攔截
    所需 Δv ≤ 追者可用推力 + 40 m/s（多發規則用整個窗口加總）；雙方純滑行時，追者窗口（+60 s）內的最近接近 ≤ 捕獲半徑
    + (追者推力 + 40 m/s) × 時間。閃避時，推完仍會被最後一條威脅到的候選重罰；存活檢查用 `strict_survives`。
    參數（40 m/s、60 s）是事先定的，沒有調過。
  - 演進：`LazyEvader`（v1）→ `LazyEvader2`（補「純滑行最近接近」那條威脅，見 §4 反制追者）→ `LazyEvader3`
    （存活檢查改嚴，見 §4 撞地）。`ReserveRolloutEvader`：RolloutPlanner 子類別，續行改 LazyEvader、勝局分數改成
    燃料戰餘裕；跟 Lazy 一樣強但每步 ~1.1 s、用油 3 倍，不建議用。
- `tests/test_evader_lab.py`（6 項，含窗口邊界盲點與「近地點在地底下」撞地的重現）；`uv run pytest -q` 82 項全綠。

## 3. 設定（可重跑）
mixed 幾何、24 局/配對、5 worker、`nice 10`、`NUMBA_NUM_THREADS=1`。seed 1 用來開發（v2、v3 的修正都是看 seed 1 /
對稱規則的輸局做的），**seed 2 是沒調過參的確認**。下面的指令與實際跑的逐局相同（部分局是用同 seed/games 的子集補跑，
game_id 一一對應）。
```bash
STRONG='{"name":"rollout_pursuer","opponents":["coast","dv_evader_fast",{"name":"rollout_evader","candidates":["dv_evader_fast"],"opponents":["lambert_pursuer_fast"]}]}'
L3=py:agents.evader_lab:LazyEvader3
uv run python evaluate.py --rules configs/rulesets/ranking_like.json --scenario mixed --games 24 --seed 2 --workers 5 \
    --pursuers "lambert_pursuer;rollout_pursuer;$STRONG" --evaders "rollout_evader;$L3" --name evader_rl_s2   # seed 1 → evader_rl_s1
uv run python evaluate.py --rules configs/rulesets/ranking_like_2burn.json ... --pursuers "lambert_pursuer;rollout_pursuer"  # evader_2burn_s1
uv run python evaluate.py --rules configs/rulesets/symmetric.json ... --pursuers "lambert_pursuer;rollout_pursuer"          # evader_sym_s1
# 反制追者（exploitability）：rollout 追者、對手模型 = 我方躲者
uv run python evaluate.py ... --pursuers '{"name":"rollout_pursuer","opponents":["py:agents.evader_lab:LazyEvader3"]};' --evaders "$L3;"
uv run python tools/paired_compare.py --a reports/evader_rl_s2.jsonl --ap rollout_pursuer --ae $L3 --be rollout_evader --win evader
```
報表：`reports/evader_{base_rl_s1,screen1_s1,rl_s1,rl_s2,2burn_s1,sym_s1}.md`（STRONG = 強化版 rollout 追者；nan = 沒跑的配對）。

## 4. 結果：躲者存活率（[95% Wilson 區間]）與逐局配對

| 規則 | 追者 | rollout_evader | LazyEvader2 | **LazyEvader3** | 配對：只 Lazy 存活 / 只 rollout_evader 存活，p |
|---|---|---|---|---|---|
| 排位版 seed 1（開發用） | Lambert | 13/24 = 54% [35–72] | 24/24 = 100% [86–100] | （未跑，見下） | v2：11 / 0，p = 0.001 |
| | rollout | 17/24 = 71% [51–85] | 24/24 | | v2：7 / 0，p = 0.016 |
| | STRONG | 7/24 = 29% [15–49] | 24/24 | | v2：17 / 0，p = 1.5e-5 |
| | 反制追者 | — | 24/24（模型 = v2） | | — |
| **排位版 seed 2（未調參）** | Lambert | 17/24 = 71% [51–85] | 24/24 | **24/24 = 100%** [86–100] | v3：7 / 0，p = 0.016 |
| | rollout | 18/24 = 75% [55–88] | 24/24 | **24/24** | v3：6 / 0，p = 0.031 |
| | STRONG | 14/24 = 58% [39–76] | 24/24 | **12/12**（只跑 0–11 局） | v2：10 / 0，p = 0.002；v3（n=12）：4 / 0，p = 0.12 |
| | 反制追者 | — | 23/24（模型 = v2，1 局撞地） | **12/12**（模型 = v3） | — |
| 排位版 2 發 seed 1 | Lambert | 12/24 = 50% [31–69] | 24/24 | （未跑） | v2：12 / 0，p = 0.0005 |
| | rollout | 4/24 = 17% [7–36] | 24/24 | | v2：20 / 0，p = 1.9e-6 |
| 對稱 1500/3000 seed 1 | Lambert | 24/24 = 100% [86–100] | 22/24 | **23/24 = 96%** [80–99] | v3：0 / 1，p = 1（看不出差異） |
| | rollout | 10/24 = 42% [24–61] | 21/24 | **21/24 = 88%** [69–96] | v3：13 / 2，p = 0.007 |

- **v3 與 v2 的差別只在「有候選近地點低於撞地高度 + 50 km」時**：seed 2 三種追者 60 局配對完全相同（0 / 0）；對稱規則 2 / 1。
  seed 1 與 2 發規則下 v2 沒有任何撞地局，v3 沒重跑（預期相同，未驗證）。
- **用油**（排位版，每局平均）：Lazy 375–830 m/s（2 發規則 910–1180），rollout_evader 2240–2900；追者對 Lazy 用 840–2950
  （Lambert 幾乎燒光，rollout 系 840–1650）。Lazy 打的是燃料戰：讓追者先出手，只在它真的威脅到時才閃。
- **決策時間**（單行程、評測報表）：Lazy2/3 **1–6 ms/步**；rollout_evader ~100–770 ms；ReserveRolloutEvader ~1.1 s。
- **開發中抓到的兩個洞**：
  1. *窗口邊界盲點*（v1 → v2）：反制追者（模型 = v1）在 seed 1 抓到 v1 3/24，其中一局躲者一滴油都沒用——雙方純滑行、
     相對速度 ~6.5 km/s，交會落在追者窗口開始後 6 s；窗口內 Lambert 掃描從 TOF 10 s 起、DvEvader 評分從 60 s 起，都看不到。
  2. *「近地點在地底下」漏判*（v2 → v3）：v2 的 3 局輸局是**躲者撞地**（對稱規則 2 局、seed 2 反制追者 1 局），都在比賽
     尾聲：剩 ~1,350 s 時大推力往下 + 往後閃，近地點在地表下 2,000 km，`agents.analytic.orbit_survives` 只看「二體近地點
     時刻在不在比賽結束後」就判安全，實際 783 s 後撞地。v3 的 `strict_survives` 對近地點低於門檻的候選實際推進到比賽結束
     + 300 s 檢查；三局都修好，其餘輸局都是燃料用完後被抓。
- ReserveRolloutEvader（seed 1）：Lambert / rollout / STRONG 存活 24/24、24/24、23/24，與 Lazy2 配對 1 / 0（看不出差異），慢 300 倍。

## 5. 另一組規則上的確認
- **一回合 2 發**（E17 讓追者大幅變強的規則）：Lazy2 對 Lambert / rollout 都 24/24，rollout_evader 只有 50% / 17%。
- **對稱 1500/3000**（逃逸本來就強的規則）：Lazy3 對 rollout 追者 88% vs 42%（p = 0.007）、對 Lambert 96% vs 100%
  （p = 1）；合計 13 / 3（p = 0.021）——**不比 rollout_evader 差**，大推力規則下也能用。

## 6. 結論
1. **排位版規則下，躲者的關鍵是「留油、受威脅才閃」**。rollout_evader 輸在前段把油燒光；Lazy 在兩批幾何、三種追者
   （含 STRONG）、單發與 2 發規則下全部存活，逐局配對沒有任何一局反向（seed 2 v3：17 / 0，p = 1.5e-5；v2：23 / 0，p = 2.4e-7）。
2. 對知道我們打法的反制追者也撐得住（v3：0/12；v2：1/24，那局是撞地漏判，v3 已修）。
3. 規則相依性低：對稱 1500/3000 也不輸 rollout_evader。

**建議 copilot**：躲者大腦清單把 `py:agents.evader_lab:LazyEvader3` 放**第一順位（預設採用）**，`rollout_evader`、
`dv_evader`、`escape_evader` 降為參考。注意 ★ 推演排序若在某些回合改選 rollout_evader 會又開始燒油——當天建議預設照
Lazy3 下，只有它的推演對某個對手模型輸、別的大腦贏時才改。（是否改 copilot 由主 session 決定，本任務沒有改。）

## 7. 限制、沒做的事、下一步
- **追者都是我們自己的大腦**（Lambert、rollout、STRONG、反制）。它們的推演都假設躲者會積極閃（對手模型 coast /
  dv_evader_fast / rollout 躲者），遇到「不推的躲者」就判斷追不到而很少出手——這是 Lazy 贏的一部分原因。換一種風格的
  追者（例如慢慢貼近、逼躲者連續閃的）可能較難；Lazy 的最近距離中位數 12–48 km，比 rollout_evader 薄。
- **反過來對我方追者是警訊**：對手的躲者如果也這樣打，我們所有追者大腦對它的捕獲率是 0–4%。追者那邊值得研究「怎麼抓懶躲者」。
- **既有程式的同一個漏判**：`agents.analytic.orbit_survives` 對「近地點在地底下」的軌跡會誤判安全，DvEvader、LambertPursuer
  （部分推力的存活檢查）、EscapeEvader、rescue_burn 都用它。這次沒有改既有檔（任務範圍）；建議主 session 評估把
  `strict_survives` 的做法搬進 `orbit_survives`（要做逐位元檢查：只有近地點低於門檻的候選會變）。
- 沒跑：v3 在 seed 1 與 2 發規則的重跑、v3 對 STRONG 的後 12 局、對稱與 2 發規則下對 STRONG、3 發規則、copilot ★ 整體
  策略的 drill / GMAT 彩排。
- 任務清單上的其他候選（細方向搜尋、改軌道面、拖時間的距離維持）沒有實作：診斷顯示瓶頸是燃料用法而不是閃避方向，留油版已經
  把被抓率壓到 0–4%，後續若要再強化，先找更強的追者來測 Lazy3。
- 逐位元檢查：不適用（沒有改 `game/`、`agents/` 既有檔、`physics/`）。
