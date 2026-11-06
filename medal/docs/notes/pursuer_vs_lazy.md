# 怎麼抓「受威脅才閃」的躲者（清單第 10 項）

## 1. 問題
`LazyEvader3`（`py:agents.evader_lab:LazyEvader3`）平常不推，只有「追者下一窗口（+60 s）一發攔得到」或「雙方滑行會在追者窗口內
接近到推得到」時才用 DvEvader 閃。排位版規則（`ranking_like.json`，250/3000）下我們所有追者對它 ~0%。四強賽對手若這樣打，
抽到追者有沒有辦法？沒有的話最好能做到什麼、當天怎麼打？

## 2. 改了什麼（只新增，既有程式與預設值都沒動）
- `agents/pursuer_lab.py`：
  - **`HarassPursuer`**（燃料消耗戰）：①窗口內一發抓得到就抓；②「逼角」：用躲者模型（預設 LazyEvader3，決定性、每步毫秒級）
    模擬它的閃避，閃完後我方窗口內抓得到就推那發；③否則選「Δv + λ×等待的躲者決策數」最小、讓模型在之後 10 個決策內判定受威脅的一發
    （零推力也是候選：閃避後的相對運動常會自己繞回來）；④都做不到才接近（一圈內最省的攔截）；⑤躲者沒油 → Lambert 追者收尾。
    逼閃不能用掉最後 1 發單發上限的油（留給收尾）；自己的推力用 `strict_survives` 檢查存活。參數（λ = 15 m/s、10 個決策）是事先定的。
  - **`LazyHunter`**（自動大腦）：一開始照 `rollout_pursuer` 打；躲者已有 ≥ 2 個決策「跟 LazyEvader3 的威脅測試吻合」（受威脅才推）、
    沒有不吻合、也沒有「寬鬆測試（150 m/s、300 s）都說沒受威脅卻推了」→ 換 HarassPursuer；之後只要它沒受威脅卻推，永遠換回 rollout。
  - 工具：`window_capture`、`first_threat`、`cornered`、`evader_decisions`（從 history 重建躲者每個決策當下的局面）。
- `tests/test_pursuer_lab.py`（6 項）；報表 `reports/plazy_*.md`。

## 3. 設定（可重跑）
mixed、5 worker、`nice 10`、`NUMBA_NUM_THREADS=1`。seed 1 開發（12 局篩選），**seed 5 未調參確認（24 局）**。
「躲者半油」= ranking_like 但 `fuel_evader_mps=1500`（臨時規則檔，沒有進 configs/）。
```bash
L3=py:agents.evader_lab:LazyEvader3; H=py:agents.pursuer_lab:LazyHunter
uv run python evaluate.py --rules configs/rulesets/ranking_like.json --scenario mixed --games 24 --seed 5 --workers 5 \
    --pursuers "rollout_pursuer;$H" --evaders "$L3;rollout_evader;dv_evader" --name plazy_confirm_rl_s5
# 同上換 --rules <躲者半油>.json / ranking_like_2burn.json --evaders "$L3"；seed 1 12 局 → plazy_main_*_s1
uv run python tools/paired_compare.py --a reports/plazy_confirm_rl_s5.jsonl --ap $H --bp rollout_pursuer --ae rollout_evader
```
連續量（躲者耗油、最近距離）：jsonl 的 `used_evader_mps`／`min_dist_km` 依 game_id 配對，數「哪邊較好」的局數做
`evaluation.stats.sign_test`（平手不計）。

## 4. 結果
### 4.1 為什麼抓不到（結構）
- **槓桿**：回合交替時躲者永遠在追者窗口前最後出手。單發上限相同時，躲者一發在追者窗口第 t 秒的位移 ≈ 250×(300+t)、追者修正只有
  250×t，「一個窗口內收掉」的可達集合永遠被它避開；只有它剩油不夠推滿時才逼得到角。
- **壓力測試**（隨機近距離局面：追者 5–150 km、相對速度 ≤ 300 m/s，n = 103 個受威脅局面）：LazyEvader3 **一律推滿單發上限**，閃完後
  追者窗口內一發抓得到的比例：躲者剩油 ≥ 150 m/s → **0/103**；剩 100 → 11/103；剩 50 → 47/103。→ 要先把它耗到 ≲ 100 m/s。
- **再逼一次的代價**（59 個閃避後局面）：一發＋滑行在 6 個躲者決策（3,600 s）內再造成威脅只有 8/59 做得到、中位數 ~250 m/s
  （= 它閃一次的油）；不推的話 12 個決策內 0/59 會自己繞回來。CW 估算：徑向外推的閃避 ~5,000 s 才繞回；它常選的「徑向外＋順行」
  會改半長軸、一路漂走。→ **燃料戰約 1:1、每半圈～一圈才逼得出一次**；T_max ≈ 4 圈只逼得出 4–7 次（1,000–1,750 m/s），
  3,000 m/s 的躲者耗不完。

### 4.2 評測（追者勝率 [95% Wilson]；躲者耗油、最近距離中位數；逐局配對符號檢定）

| 規則 / seed / n | 追者 | 抓到 | 躲者耗油 m/s | 最近距離 km |
|---|---|---|---|---|
| 排位版 / s1 / 12 | rollout | 0/12 [0–24] | 625 | 37.4 |
| | LazyHunter | 0/12 [0–24] | 1300（12/0，p = 0.0005） | 59.1（4/8，p = 0.39） |
| | rollout + LazyEvader3 對手模型 | 0/12 | 562 | **22.6**（8/2，p = 0.11） |
| **排位版 / s5 / 24** | rollout | 0/24 [0–14] | 546 | 37.3 |
| | LazyHunter | 0/24 [0–14]（1 局自己撞地，已修，見下） | **1090（21/3，p = 0.0003）** | 47.5（**較遠**：6/17，p = 0.035） |
| 躲者半油 / s1 / 12 | rollout | 0/12 [0–24] | 717 | 41.6 |
| | LazyHunter | **3/12 = 25%** [9–53]（3/0，p = 0.25） | 1175 | 47.7 |
| **躲者半油 / s5 / 24** | rollout | 0/24 [0–14] | 725 | 30.5 |
| | LazyHunter | **2/24 = 8%** [2–26]（2/0，p = 0.5） | 1006（16/4，p = 0.012） | 47.1 |

- 躲者半油兩個 seed 合計：只有 Hunter 抓到 5 局、反向 0 局（p = 0.06）——**方向一致但不顯著**。抓到的局都是先把它耗光再收尾；
  沒抓到的局多半是耗光得太晚（第一版沒有收尾邏輯時 6/12 局把它耗光但只抓到 2 局）。
- 篩選過、沒採用：自適應 λ（油多就花錢換快）＋保留 400 m/s：躲者耗油反而少（排位版 1162 vs 1358），抓到數相同。
- **撞地**：seed 5 第 8 局 Hunter 自己撞地（低軌、一發逆行＋側推，`orbit_survives` 的「近地點在地底下」漏判）。已改用
  `strict_survives`，同局重跑 → 撞地消失（timeout）。表中數字是修正前跑的；修正只影響「近地點低於撞地高度 + 50 km」的候選。
  修正後版本 seed 5 前 12 局：見 §4.4。

### 4.3 對主動躲者沒有變差（seed 5、24 局、逐局配對 Hunter vs rollout）
- rollout_evader：7/24 vs 7/24，只有 Hunter 1、只有 rollout 1（p = 1）；dv_evader：20/24 vs 20/24，逐局相同。
- 機制：rollout_evader／dv_evader 第一、二個決策就會在沒受威脅時推（各 11/12），偵測器不會切換，跟 rollout 逐步相同。例外：
  seed 1 第 6 局 rollout_evader 前 5 個決策表現得跟懶躲者一樣，Hunter 切過去 2 回合，那局 rollout 抓到、Hunter 沒抓到（12 局 0/1）。

### 4.4 修正後版本（strict_survives）確認
seed 5 前 12 局（`reports/plazy_final_check_rl_s5.md`）：0/12、沒有撞地；躲者耗油 1004 vs rollout 488（同 12 局 10/1，p = 0.012）；
跟修正前的 Hunter 比 10 局逐數字相同、2 局不同（含撞地那局）。

## 5. 另一組規則上的確認
- **一回合 2 發**（`ranking_like_2burn`）：HarassPursuer（s1，12 局）0/12、rollout 0/12；躲者耗油 1750 vs 1100（10/0，p = 0.002）。
  **LazyHunter 在多發規則不會切換**（s5，24 局與 rollout 逐局相同，0/24、各 2 局追者撞地——rollout 本身的問題）：躲者窗口內第二發
  的時刻偵測器沒有重建，被判成「沒受威脅卻推」。多發規則要直接選 HarassPursuer。
- **對稱 1500/3000、2 發**（題目第 5 點：rollout 怎麼抓到的）：LazyEvader3 每次受威脅都推滿 1500 m/s，**兩次就沒油**（12 局全部用光
  3000）；rollout 的 3/12 都是它沒油之後、在比賽尾聲（t = 21,365 / 26,615 / 26,023 s，T_max 24,764–26,616）用剩下的油收掉。
  LazyHunter 3/12、逐局與 rollout 相同；保留油固定 250 m/s 的舊版 Harass 只有 1/12（把油燒光收不了尾 → 改成保留 1 發上限）。

## 6. 結論
1. **排位版規則（雙方單發、燃料相同、T_max ~4 週期）下找不到抓得到 LazyEvader3 的打法**：結構上一個窗口逼不到角，燃料戰約 1:1 且
   每半圈～一圈才逼得出一次，4 圈耗不完它的 3,000 m/s。兩個 seed 36 局、含用精確躲者模型逼角的追者，全部 0。
2. **最好能做到**：逼它多耗一倍油（Hunter 1,090 vs 546 m/s，p = 0.0003），或把最近距離壓低（rollout 本身較近；加 LazyEvader3 對手
   模型的 rollout 在 s1 中位數 22.6 km，n.s.）。兩者互斥：Hunter 最近距離較遠（p = 0.035）。
3. **規則給追者燃料優勢時才有機會**：躲者燃料只剩一半時 Hunter 抓到 5/36、rollout 0/36（p = 0.06）。對稱 1500 級規則下它被逼兩次就沒油，
   rollout／Hunter 都抓到 1/4。
4. LazyHunter 對主動躲者不會變差（36 局配對 1/1，其餘逐局相同），但多發規則下偵測不觸發。

**當天抽到追者、對手躲者是 lazy 型（前兩個決策沒推、只在 copilot 顯示「追者攔截所需 Δv ≤ 單發上限」時才推）**：
- 先看規則：雙方單發與燃料相同、T_max ~4 週期 → **不要期待抓到**，照計分選次目標——計分看對手耗油（或不明）→ HarassPursuer
  （對手多耗一倍、我們 ~2,400 m/s 也燒得完）；計分看最近距離 → 維持 rollout 追者（必要時加 LazyEvader3 對手模型）。
- 我方燃料 ≥ 對手 2 倍（或對手燃料少）→ 用 HarassPursuer，留至少 1 發上限的油給收尾。
- 單發上限大（1500 級）→ rollout 追者即可（它被逼兩次就沒油），重點是自己別把油用光。

**建議 copilot 改法**（本任務沒改，由主 session 決定）：
1. `DEFAULT_BRAINS["pursuer"]` 加 `"py:agents.pursuer_lab:HarassPursuer"`（不放第一）。copilot 每次 advise 都從局勢檔重建、沒有
   history，所以 **LazyHunter 的自動偵測在 copilot 裡無效**，要由操作者看到 lazy 行為後手動採用 Harass 的建議。
2. `DEFAULT_OPP_MODELS["pursuer"]` 加 `"py:agents.evader_lab:LazyEvader3"`，推演表才看得到「對手只閃不推」的情況（排位版規則下所有
   大腦都會 LOSE，★ 排序就變成看最近距離）。
3. 戰況區可加一行「躲者至今只在受威脅時推過 N/N 次」（需要從官方歷史填 history，局勢檔目前沒有這個欄位）。

## 7. 限制、沒做的事、下一步
- 對手模型就是被測的 LazyEvader3（逼角、威脅判定都用它）：**換門檻的變體沒測**（margin 0/slack 0 那批因 spec 解析失敗沒跑出來）。
  Harass 的「逼閃」靠模型判定威脅，對手門檻比模型緊時會白花油。
- 躲者半油、追者兩倍燃料等「規則給追者優勢」只測了躲者半油；追者 6000 沒跑。強化版 rollout（STRONG）沒加進比較。
- 再逼一次只考慮「一發＋滑行」與一圈內的單發接近；兩發組合規劃（窗口間連推）沒做，可能把燃料戰比例從 ~1:1 往下壓。
- 多發規則下的偵測器（窗口內第二發）沒做。逐位元檢查：不適用（沒改 `game/`、`agents/` 既有檔、`physics/`）。
