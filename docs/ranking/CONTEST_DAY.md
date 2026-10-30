# 排位賽當天作業手冊（2026-11-09，10:45–11:45）

比賽當天從上到下照做。規則摘要見 [RANKING_ROUND_RULES](RANKING_ROUND_RULES_20261006.md)，給主辦的問題見
[QUESTIONS_FOR_ORGANIZER](QUESTIONS_FOR_ORGANIZER.md)，工具說明見[專案 README](../../README.md)。
沒標「官方」的判斷都是我們的推論，現場以工作人員說的為準。

**三條原則**

1. **先交得出東西，再求更好。** 第一份通過檢查的解立刻存 USB，之後只有更好的解才換掉它。
2. **到點就收。** 時間盒的截止時刻一到，就交手上最好的合法解，不等跑到一半的東西。
3. **失格的解一律不交。** 沒攔到也有分數（差 50 km 仍約 32 分），失格是 0 分。

---

## 一、時間盒

60 分鐘只夠跑一輪主力求解，加上保留時間給檢查與繳交。下表的機器時間是 2026-10-30 在 M4 MacBook Air
（插電）上用排位賽範本設定實測的，見[附錄 A](#附錄-a實測紀錄)。

| 時刻 | 主控（Mac） | 隊友 A（核對） | 隊友 B（主辦機與後勤） |
|---|---|---|---|
| 10:45 | 步驟 1：建設定檔、抄 A／B 根數 | 獨立抄一份根數、邊界與計分參數 | 確認主辦機的 GMAT 能開、題目 Script 在哪、怎麼上傳 |
| 10:52 | 步驟 2–3：T_max、計分參數寫回 | 逐字元核對主控的設定檔 | 同上；不清楚的當場問工作人員 |
| 10:55 | 步驟 4：`check`、`feasibility` | 唸出 `check` 的近地點、T_max、`C_t/T_max` 跟題目對 | |
| **10:57** | **步驟 5：開跑求解**（實測 2.5–5 分，預留 15 分） | 準備步驟 7 清單 | 在主辦機開題目 Script，先熟悉要改哪裡 |
| 求解完 | 步驟 6：重瞄準（< 1 分）、GMAT 重驗（< 10 s） | | |
| ＋3 分 | 步驟 7：失格檢查清單 | 唸清單、逐項打勾 | |
| **最晚 11:20** | 存 USB：**保底解** | 記下 d_min、ΔV、T、分數 | 接 USB，主辦機上跑一次 |
| 有空檔 | [步驟 9](#步驟-9有空檔才做) 改善（只在 11:08 前拿到保底時） | | |
| **11:25** | **停止一切改善**，交手上最好的那份 | | 步驟 8：主辦機跑、產 Report、上傳 |
| 11:35 | 確認上傳成功 | 確認上傳成功 | 上傳完成 |
| 11:45 | 結束 | | |

**硬性截止**

- **11:15 求解還沒結束** → 照[五、出狀況](#五出狀況怎麼辦)的「求解太慢」處理。
- **11:20** 一定要有一份通過步驟 7 的檔案在 USB 上。
- **11:25** 開始繳交，之後不再換解。繳交（步驟 8）從沒在主辦機上計時過，先留 20 分鐘。

### 分工

主控是唯一操作工具、決定交哪份解的人。隊友只做不需要懂程式、但能獨立驗證的事：

- **隊友 A（核對）**：獨立抄題、逐字元核對設定檔；看時鐘，到截止時刻提醒主控；唸步驟 7 的清單。
- **隊友 B（主辦機）**：開賽就去弄清楚主辦機怎麼開 Script、跑模擬、產 Report、上傳；保底解一到就先在主辦機跑一次。

三個人都要會步驟 8。主控卡住時，隊友直接把 USB 上最新那份交出去。

---

## 二、賽前一晚

- [ ] `git pull`、`uv sync`，`git status` 乾淨、在 `Master`。
- [ ] 回歸測試（約 1.5 分鐘）：
  ```bash
  uv run python odc.py test --quick -q
  ```
- [ ] **拔掉網路**，從[步驟 1](#步驟-1建設定檔5-分鐘) 到步驟 7 用範本完整跑一次並計時，名稱改用 `rehearsal`：
  ```bash
  uv run python odc.py new-config rehearsal --gmat-console "/Users/corn/Documents/GMAT R2026a/bin/GmatConsole"
  ```
  第一次跑會編譯 numba，比較慢；跑完之後快取就熱了，當天會跟實測一樣快。
- [ ] 確認當天要用的名稱 `configs/local/ranking.json` **還不存在**（`new-config` 不會覆蓋，存在就換名字）。
- [ ] GMAT 安裝裡有 `data/gravity/earth/EGM96.cof` 和 CSSI 太空天氣檔（全攝動要用）。
- [ ] 看一次 TASA 競賽頁有沒有規則修訂；主辦有回覆就把太空船參數、曆元填進範本（[問題 1–6](QUESTIONS_FOR_ORGANIZER.md)）。
- [ ] 筆電充飽、充電器、延長線、兩支 USB、證件；全員到場。
- [ ] Mac 關掉自動睡眠與自動更新；比賽中全程插電。

---

## 三、開賽時先問工作人員

隊友 B 問，答案寫在紙上給主控。主辦還沒回信的話，這些都是當天才知道（完整問題見 [QUESTIONS_FOR_ORGANIZER](QUESTIONS_FOR_ORGANIZER.md)）：

1. 任務邊界是**地心距離還是高度**？有沒有直接給 T_max 秒數？
2. 計分參數 `k_v`、`C_v` 的**單位**？有沒有參考解？
3. 繳交格式：Script＋Report？要從題目 Script 改，還是可以交整份自製 Script？
4. 可以用自己的筆電先算嗎？太空船質量、Cd、Cr、面積、曆元？

---

## 四、逐步流程

以下指令都在專案根目錄執行。路徑照抄就好；多跑一次時把目錄名稱的 `-1` 改成 `-2`（`--run-dir` 不能是已存在的目錄）。

### 步驟 1：建設定檔（5 分鐘）

```bash
uv run python odc.py new-config ranking --gmat-console "/Users/corn/Documents/GMAT R2026a/bin/GmatConsole"
```

打開 `configs/local/ranking.json`，改 `orbit_A`、`orbit_B` 的六根數（SMA、ECC、INC、RAAN、AOP、TA；km 與度）。
`rules` 的 `MAX_DV_MPS`、`MAX_TOTAL_DV_MPS`、`MIN_MANEUVER_INTERVAL_SEC` 已是官方值，**不要動**；
`T_MAX_SEC` 與計分參數由步驟 2、3 寫入。`strategy` 與 `optimization` 不要動。`_comment_*` 欄位可以留著。

抄根數要注意：

- 雙曲線的 **SMA 是負的**、ECC > 1。
- **TA 的正負號**決定 A 是飛向近地點還是已經飛過，抄錯 T_max 完全不同。[0, 360) 或 (−180, 180] 都可以。
- 題目給的若是狀態向量不是根數，用 GMAT 開題目 Script 讀出 Keplerian 根數再抄。
- 主控與隊友 A **各抄一次，逐字元對**。

### 步驟 2：T_max（1 分鐘）

**官方直接公布 T_max 秒數**：把它填進 `rules.T_MAX_SEC`，跳過這步。

否則依任務邊界算。邊界是**地心距離**：

```bash
uv run python odc.py tmax --config configs/local/ranking.json --boundary-km <邊界>
```

邊界是**高度**時改用 `--boundary-alt-km <邊界>`（兩者差 6,378 km）。輸出要看三件事：

1. 點質量數值解跟解析解差 < 1 ms；不是的話根數抄錯，先不要寫。
2. J2–J4 與解析解差幾秒以內（實測 +0.15～+0.29 s）。
3. 「註」說 A 是否已過近地點、一開始在邊界內外，跟題目描述對得上。

都對就在同一行指令後面加 `--write` 再跑一次（寫入解析與 J2–J4 取早者，捨去到整秒）。工具擋下的情況見[附錄 B](#附錄-bt_max-工具擋下的情況)。

### 步驟 3：計分參數（2 分鐘）

`--kv-unit`、`--Cv-unit` 沒有預設值，照官方寫的單位填（`1/(km/s)` 或 `1/(m/s)`、`km/s` 或 `m/s`）：

```bash
uv run python odc.py scoring --config configs/local/ranking.json --kt <k_t> --kt-unit 1/s --Ct <C_t> --Ct-unit s --kv <k_v> --kv-unit "<單位>" --Cv <C_v> --Cv-unit <單位>
```

有官方參考解就加 `--ref-dv <總Δv> --ref-dv-unit <單位> --ref-t <攔截時刻>`。

- **有參考解**：初賽主辦照參考解校準參數，換對單位的總分剛好是整數（初賽 90.00；照抄 km/s 制只有 72.50）。工具會把四種單位解讀都算一遍，標出落在整數的那種。
- **沒有參考解**：看「數量級檢查」。m/s 制的 `C_v` 應該是幾百到幾千，`C_v < 50` 幾乎一定還是 km/s。
- 沒有警告就加 `--write` 再跑一次。

格式範例（初賽參數）：`uv run python odc.py scoring --demo-prelim`。

### 步驟 4：體檢（1 分鐘）

```bash
uv run python odc.py check configs/local/ranking.json
```

```bash
uv run python odc.py feasibility configs/local/ranking.json
```

- `check`：近地點、平面夾角、T_max、`C_t/T_max` 有沒有離譜。最後的「參考解 90 分」對照只對初賽有意義，忽略。
- `feasibility`：**能量下限**。拆棒後至少 ⌈下限 ÷ 250⌉ 棒。下限接近或超過 3,000 m/s 時可能無合法解，先有心理準備（見[五](#五出狀況怎麼辦)「結束碼 3」）。
- 求解時會印「能量下限 … MAX_BURNS 裡的 [1, 2] 在搜尋輸出當下必然違規」：**正常**，`MAX_BURNS` 不要改。

### 步驟 5：求解（實測 2.5–5 分鐘）

```bash
uv run python odc.py solve configs/local/ranking.json --run-dir outputs/runs/rank-1 -q
```

一次跑完搜尋、oracle、拆棒、J2–J4 版 GMAT 驗證。`-q` 只印警告，完整進度寫在 `outputs/runs/rank-1/run.log`
（另開終端 `tail -f outputs/runs/rank-1/run.log` 可看）。只跑**一個**行程：範本設定 `SEED: null` 會用滿所有核心，
oracle 也在背景佔核心，同時跑兩個會互搶、兩個都變慢。

跑完先 `echo $?` 看結束碼（0 正常、3 找不到合法路線），再看結果：

```bash
python3 -c "import json;d=json.load(open('outputs/runs/rank-1/mission.json'))['mission_info'];print('分數',round(d['score'],4),'失格',d['disqualified'],d['dq_reasons'],'棒數',d['num_burns'],'總Δv',round(d['total_dv_mps'],1),'T',round(d['T_team']))"
```

- `失格 False` → 步驟 6。
- 結束碼 3（終端機說找不到合法路線）、或 `失格 True` → [五、出狀況](#五出狀況怎麼辦)。

這一步產生的 `outputs/runs/rank-1/output_submit.txt` 是 J2–J4 版，全攝動下會偏離，**只在步驟 6 失敗時當最後手段**：
佔位題（5.5 h 到攔截）偏 3.8 km 還算命中，hyper_far（22.6 h）偏 103 km、分數從 82.6 掉到 51.4。

### 步驟 6：全攝動重瞄準＋GMAT 重驗（1 分鐘）

官方驗證開全攝動，我們用 J2–J4 設計，瞄準點只留 1.5 km 餘裕；這步在 GMAT 全攝動下修一棒、重新判定合法性，
通過才產繳交腳本（原理見 [README](../../README.md#全攝動重瞄準排位賽)）。

```bash
uv run python odc.py retarget outputs/runs/rank-1/mission.json --config configs/local/ranking.json --run-dir outputs/runs/rank-1-rt
```

看到 `✅ 全攝動重瞄準通過` 和 `👉 繳交腳本：…/rank-1-rt/output_submit.txt` 就成功。再用 GMAT 獨立重驗一次那份腳本：

```bash
uv run python odc.py verify outputs/runs/rank-1-rt/output_submit.txt --config configs/local/ranking.json --run-dir outputs/runs/rank-1-verify
```

印 `✅ GMAT 獨立驗證通過` 就往下。重瞄準不通過時，終端機會列原因與每棒餘裕，照[五](#五出狀況怎麼辦)處理。

### 步驟 7：失格檢查清單（3 分鐘）

印出檢查用的數字：

```bash
R=outputs/runs/rank-1-rt C=configs/local/ranking.json python3 -c "
import json,os;r=json.load(open(os.environ['R']+'/retarget.json'));c=json.load(open(os.environ['C']))['rules'];x=r['result'];g=x['retargeted']['legality'];v=x['fixed_script_verification'];b=g['burn_dv_mps'];T=x['retargeted']['t_team_sec']
print('狀態',r['status'],'| 失格',g['disqualified'],g['dq_reasons'],'| 間隔違規',g['penalty_count']);print('棒數',len(b),'| 最大單棒 %.3f m/s（上限 %g）'%(max(b),c['MAX_DV_MPS']),'| 總Δv %.2f m/s（上限 %g）'%(g['total_dv_mps'],c.get('MAX_TOTAL_DV_MPS',0)))
print('全攝動 d_min %.3f km | GMAT 固定版 Δr %.3f km 命中 %s'%(x['retargeted']['d_min_km'],v['miss_km'],v['intercept_success']));print('T_team %.1f s，離 T_max 還有 %.0f s | 攔截前最低高度 %.0f km'%(T,c['T_MAX_SEC']-T,v['min_radius_before_intercept_km']-6378.137));print('官方分數估計 %.4f'%g['official_score'])"
```

隊友 A 唸、主控對，**每一項都打勾才能存 USB**：

- [ ] `狀態 accepted`、`失格 False`、`間隔違規 0`。
- [ ] 最大單棒 ≤ 249 m/s（上限 250，超過 250 + 10⁻⁵ 失格）。
- [ ] 總 Δv ≤ 3,000 m/s。
- [ ] 全攝動 d_min 與 GMAT 固定版 Δr 都 < 4 km，`命中 True`。
- [ ] 離 T_max 還有 ≥ 300 s（官方算 T_max 的模型可能跟我們差到分鐘等級）。
- [ ] 攔截前最低高度 > 100 km。
- [ ] `configs/local/ranking.json` 的 `T_MAX_SEC`、`k_t/C_t/k_v/C_v` 是今天的官方值，不是範本的 40000／0.0001／25000／0.002／1500。
- [ ] 步驟 6 的 `verify` 印了 `✅`。

全部打勾就複製到 USB，檔名帶分數，例如 `rank1_86.78_output_submit.txt`。同時記下 d_min、ΔV、T、分數（同分依序比這三個）。

### 步驟 8：繳交（11:25 開始，留 20 分鐘）

繳交格式官方還沒公布。初賽是在主辦機的 GMAT 開題目 Script、改 B 的設定與機動、至少模擬一次產 Report、把 Script＋Report 上傳。
`output_submit.txt` 是完整的固定燃燒 GMAT 腳本（不含求解器），如果允許交整份自製 Script：

1. 在主辦機的 GMAT 開 USB 上那份 `output_submit.txt`，跑一次。
2. 看 Report 的命中距離跟步驟 7 的 GMAT 固定版 Δr 一致（差幾公尺以內）。不一致就停下來問工作人員他們的力學設定。
3. Report 檔名照官方要求，Script＋Report 上傳，確認上傳成功。

如果**只能改題目 Script**：把 `output_submit.txt` 裡 B 的初始狀態、每一棒 `ImpulsiveBurn` 的 VNB 分量與滑行時間，照抄進題目 Script 對應的地方。
這種情況比較花時間，所以隊友 B 開賽就要先看懂題目 Script。

腳本必須全 ASCII（中文註解會讓 GMAT 解析失敗，初賽踩過三次）；工具產的腳本已經是 ASCII，手改時不要加中文。

### 步驟 9：有空檔才做

只在 **11:08 前**已經存好保底解時才做，**11:25 一到就停**，沒跑完就算了。

用不同種子再跑一次，取較好的那份。範本開了 oracle 之後，5 顆種子在 6 題測試題裡的分數都一樣
（[階段 2](../research/ORACLE_PHASE2_20261029.md)），所以這步多半只會拿到同分，主要是保險：

```bash
cp configs/local/ranking.json configs/local/ranking-s1.json
```

把 `ranking-s1.json` 的 `optimization.SEED` 從 `null` 改成 `1`，然後照步驟 5–7 跑，設定檔換成 `ranking-s1.json`、
目錄名稱換成 `rank-2`、`rank-2-rt`、`rank-2-verify`。設了 SEED 搜尋會變單執行緒，比主力慢。
新解的官方分數估計**明顯更高**（> 0.01）且清單全過，才換掉 USB 上的那份。

---

## 五、出狀況怎麼辦

| 狀況 | 怎麼判斷 | 怎麼做 |
|---|---|---|
| **求解太慢**（11:15 還沒完） | `run.log` 最後幾行。出現 `🧭 primer 診斷 … 以 N 棒重搜` 表示多跑一整輪搜尋；`多起點拆棒`、`拆棒` 表示在拆棒（有 600 s 上限） | 拆棒中就等，最多 10 分鐘會交出結果。primer 重搜中、且已過 11:15：另開終端用[保底設定](#保底設定)跑一份，兩邊誰先完成用誰 |
| **結束碼 3**：找不到合法路線 | 終端機訊息；`outputs/runs/rank-1/no_legal_route.json` | 看最接近的候選超標多少、步驟 4 的能量下限。下限 > 3,000 m/s 代表題目本身可能無合法解，問工作人員。否則 `ranking.json` 的 `MAXITER` 加到 2000 重跑（多一倍時間，來不及就放棄這題的改善） |
| **`失格 True`** | 步驟 5 的結果 | 看 `dq_reasons`。單棒或總 Δv 超標時同「結束碼 3」 |
| **重瞄準不通過** | 終端機紅字列出原因與每棒餘裕（`retarget.json` 的 `result.reasons`） | 改的那棒超標：加 `--retarget-burn N`（0 起算）改一棒餘裕大的，`--run-dir` 換 `rank-1-rt2` 重跑。d_min 壓不下來或 Earth-safe 不過：換一棒試一次；還是不過就交 `rank-1/output_submit.txt`（J2–J4 版），並在清單上記下這是退路 |
| **GMAT 打不開或驗證失敗** | `verify` 沒印 `✅`、或 GMAT 錯誤 | 確認 `--gmat-console` 路徑；路徑字串必須是 ASCII。重跑一次 `verify`。還是不行就直接到主辦機上跑那份腳本確認 |
| **Mac 當掉或沒電** | | 有另一台裝好工具的筆電就從步驟 5 在那台跑；沒有就交 USB 上最新那份 |
| **主辦機跑出來跟我們不一樣** | 步驟 8 第 2 點 | 問工作人員他們的力學模型與太空船參數；拿到參數後改 `ranking.json` 的 `strategy.GMAT_SPACECRAFT`／`GMAT_EPOCH`，從步驟 6 重跑（不用重新求解） |

### 保底設定

只在主力求解來不及時用：

```bash
cp configs/local/ranking.json configs/local/ranking-fast.json
```

把 `ranking-fast.json` 的 `optimization.MAXITER` 改成 `300`，`strategy` 加一行 `"PRIMER_GUIDED_RESEARCH": false`（關掉加棒重搜），
照步驟 5–7 跑，目錄名稱換成 `rank-fast`、`rank-fast-rt`、`rank-fast-verify`。搜尋代數約剩三分之一，
代價是分數可能低一點：降預算在測試題最差掉 1.7 分（[準備期紀錄](../log/DEVLOG_ranking.md) budget_v1）。
hyper_far 實測 270 s（主力 293 s，同分）：時間主要花在背景 oracle，所以它只在 primer 重搜或搜尋特別久時才有用。

---

## 六、已知地雷

1. **`k_v`、`C_v` 的單位。** 初賽官方給 km/s 制，照抄燃料項全錯（72.50 vs 90.00）。
2. **邊界是地心距離還是高度**，差 6,378 km。工具只在「邊界 < 近地點」時提醒。
3. **TA 正負號**決定 A 往近地點飛還是飛離。
4. **`T_MAX_SEC` 從 epoch 起算**，不是從近地點。
5. **重瞄準只能用 B 平面**（`odc.py retarget` 已是），定時位置對齊在長任務會多花上百 m/s 而失格。
6. **拆出來的棒都貼著 248 m/s**，重瞄準改棒時看每一棒的餘裕，不是只看最後一棒。
7. **共用情境的 `T_MAX_SEC` 是編的**（用 2 × 到近地點時間），不要拿來當排位賽參考。
8. **`run.json` 的 `completed` 不代表能交**，能不能交只看步驟 7。
9. `--run-dir` 不能指到已存在的目錄；`new-config` 不覆蓋已存在的設定檔。

---

## 附錄 A：實測紀錄

2026-10-30，M4 MacBook Air（4 效能核＋6 節能核、32 GB），插電，numba 快取已熱。設定是 `ranking_round.json` 的
`strategy`／`optimization`（oracle 開、`SEED: null`、`MAXITER` 1000），只換軌道與計分參數。

| 題目 | 步驟 5 求解 | 步驟 6 重瞄準 | 驗證 | 結果 |
|---|---|---|---|---|
| `ranking_round` 佔位題（T_max 11.1 h、能量下限 637 m/s） | 149 s | 7 s | 3 s | 4 棒、86.785 → 重瞄準後 86.781，d_min 4 m |
| `hyper_far` 軌道（T_max 45 h、能量下限 1,885 m/s） | 293 s | 13 s | 4 s | 8 棒、82.645 → 82.638，d_min 321 m；未重瞄準的 J2–J4 版在全攝動下偏 103 km（51.4 分） |
| `e1_r8` 軌道（T_max 21.5 h、能量下限 1,352 m/s），**有觸發 primer 重搜** | 220 s | — | — | 8 棒、76.534（重搜約 2 分鐘） |
| `hyper_far`＋[保底設定](#保底設定) | 270 s | — | — | 8 棒、82.645，跟主力同分 |

人工步驟（抄題、核對、繳交）還沒計時，彩排時補進來。

舊紀錄（3 顆固定種子並行、oracle 未開）：2026-10-20 Corn 佔位題 12.6 分；2026-10-28 Mac hyper_far 最快一顆 33 分、
有一顆觸發 primer 重搜跑到 48 分鐘被手動停掉。改成單行程多執行緒＋oracle 之後才降到上表的時間。

## 附錄 B：T_max 工具擋下的情況

都會印原因，結束碼不是 0。

| 情況 | 訊息 | 怎麼辦 |
|---|---|---|
| 邊界 ≤ 近地點距離 | 「A 的距離永遠不會小於近地點」 | 多半是把高度當地心距離，改用 `--boundary-alt-km` |
| A 已過近地點且已在邊界外 | 「雙曲線不會再回來」 | 檢查 TA 正負號 |
| TA 在漸近線外 | 「\|TA\| 必須 < …」 | TA 或 ECC 抄錯 |
| 橢圓 A、邊界 > 遠地點 | 「A 永遠在邊界內」 | 規則定義不適用，問工作人員 |
| 圓軌道、拋物線 | 沒有定義 | 問工作人員 |

A 一開始就過了近地點、但還在邊界內時，工具照算（T_max = 往外飛出邊界的時刻）並附註提醒，要跟工作人員確認他們也這樣定義。
