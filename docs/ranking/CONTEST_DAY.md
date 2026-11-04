# 排位賽當天作業手冊（2026-11-09，10:45–11:45）

從上到下照做。現場以工作人員說的為準。

**三條原則**

1. **先交得出東西。** 第一份通過步驟 7 的解立刻存 USB，之後只有更好的解才換。
2. **到點就收。** 截止時間到了就交手上最好的合法解。
3. **失格的解不交。** 沒攔到還有分數，失格是 0 分。

---

## 一、時間盒

| 時刻 | 主控（Mac） | 隊友 A（核對） | 隊友 B（主辦機） |
|---|---|---|---|
| 10:45 | 步驟 1 建設定檔 | 獨立抄一份根數與參數 | 弄清楚主辦機怎麼開 Script、跑、上傳 |
| 10:52 | 步驟 2–3 | 逐字元核對設定檔 | 同上 |
| 10:55 | 步驟 4 | 對 `check` 的數字 | |
| **10:57** | **步驟 5 開跑求解**（約 3–5 分） | 準備步驟 7 清單 | 先看懂題目 Script 要改哪裡 |
| 求解完 | 步驟 6（約 1 分） | | |
| ＋3 分 | 步驟 7 | 唸清單打勾 | |
| **11:20 前** | 保底解存 USB | 記下 d_min、ΔV、T、分數 | 主辦機上先跑一次 |
| 有空檔 | 步驟 9（11:08 前有保底才做） | | |
| **11:25** | **停止改善** | | 步驟 8 繳交 |
| 11:35 | 確認上傳成功 | 確認上傳成功 | |

**硬性截止**：11:15 求解還沒完 → [三](#三出狀況怎麼辦)「求解太慢」；11:20 USB 上一定要有保底；11:25 開始繳交，不再換解。

**分工**：只有主控操作工具、決定交哪份。三個人都要會步驟 8；主控卡住時，隊友直接交 USB 上最新那份。

---

## 二、逐步流程

指令都在專案根目錄執行。重跑時目錄名 `-1` 改 `-2`（`--run-dir` 不能已存在）。

### 步驟 1：建設定檔（5 分鐘）

```bash
uv run python odc.py new-config ranking --gmat-console "/Users/corn/Documents/GMAT R2026a/bin/GmatConsole"
```

在 `configs/local/ranking.json` 填 `orbit_A`、`orbit_B` 六根數（SMA、ECC、INC、RAAN、AOP、TA；km、度）。其他欄位不要動。

- 雙曲線 **SMA 是負的**、ECC > 1。
- **TA 正負號**別抄錯（決定 A 飛向還是飛離近地點）。
- 題目給狀態向量時，用 GMAT 開題目 Script 讀出根數。
- 主控與隊友 A **各抄一次，逐字元對**。

題目有給**曆元與太空船參數**就一定要抄，在 `strategy` 加（只填官方有給的欄位；A 不同時另填 `GMAT_SPACECRAFT_A`）：

```json
"GMAT_EPOCH": "<題目 Script 的 Epoch>",
"GMAT_EPOCH_FORMAT": "<照 Script 的 DateFormat，如 UTCGregorian、TAIModJulian>",
"GMAT_SPACECRAFT": {"DRY_MASS_KG": 850, "CD": 2.2, "CR": 1.8, "DRAG_AREA_M2": 6, "SRP_AREA_M2": 8}
```

### 步驟 2：T_max（1 分鐘）

官方直接給秒數 → 填 `rules.T_MAX_SEC`，跳過。否則：

```bash
uv run python odc.py tmax --config configs/local/ranking.json --boundary-km <邊界>
```

邊界是高度時改 `--boundary-alt-km`。確認三件事後加 `--write` 再跑一次：

1. 點質量數值解與解析解差 < 1 ms（不是就是根數抄錯）。
2. J2–J4 與解析解差幾秒內。
3. 「註」說的 A 位置跟題目描述一致。

工具擋下時看[附錄](#附錄t_max-工具擋下的情況)。

### 步驟 3：計分參數（2 分鐘）

照官方單位填（`1/(km/s)` 或 `1/(m/s)`、`km/s` 或 `m/s`）：

```bash
uv run python odc.py scoring --config configs/local/ranking.json --kt <k_t> --kt-unit 1/s --Ct <C_t> --Ct-unit s --kv <k_v> --kv-unit "<單位>" --Cv <C_v> --Cv-unit <單位>
```

- 有參考解：加 `--ref-dv <總Δv> --ref-dv-unit <單位> --ref-t <攔截時刻>`，選總分落在整數的那種單位。
- 沒參考解：m/s 制的 `C_v` 應是幾百到幾千；`C_v < 50` 多半還是 km/s。
- 沒警告就加 `--write` 再跑一次。

### 步驟 4：體檢（1 分鐘）

```bash
uv run python odc.py check configs/local/ranking.json
```

```bash
uv run python odc.py feasibility configs/local/ranking.json
```

- `check`：近地點、平面夾角、T_max、`C_t/T_max` 合理即可；「參考解 90 分」忽略。
- `feasibility`：能量下限接近 3,000 m/s 時可能無合法解。
- 求解時印「MAX_BURNS 裡的 [1, 2] … 必然違規」是正常的。

### 步驟 5：求解（約 3–5 分鐘）

```bash
uv run python odc.py solve configs/local/ranking.json --run-dir outputs/runs/rank-1 -q
```

只跑**一個**行程（會用滿核心）。進度看 `tail -f outputs/runs/rank-1/run.log`。跑完 `echo $?`（0 正常、3 找不到合法路線），再看結果：

```bash
python3 -c "import json;d=json.load(open('outputs/runs/rank-1/mission.json'))['mission_info'];print('分數',round(d['score'],4),'失格',d['disqualified'],d['dq_reasons'],'棒數',d['num_burns'],'總Δv',round(d['total_dv_mps'],1),'T',round(d['T_team']))"
```

`失格 False` → 步驟 6；結束碼 3 或 `失格 True` → [三](#三出狀況怎麼辦)。

這步的 `rank-1/output_submit.txt` 在全攝動下會偏，**只在步驟 6 失敗時才交**。

### 步驟 6：全攝動重瞄準＋GMAT 重驗（1 分鐘）

```bash
uv run python odc.py retarget outputs/runs/rank-1/mission.json --config configs/local/ranking.json --run-dir outputs/runs/rank-1-rt
```

看到 `✅ 全攝動重瞄準通過` 就重驗：

```bash
uv run python odc.py verify outputs/runs/rank-1-rt/output_submit.txt --config configs/local/ranking.json --run-dir outputs/runs/rank-1-verify
```

印 `✅ GMAT 獨立驗證通過` 就往下；不通過看[三](#三出狀況怎麼辦)。

### 步驟 7：失格檢查清單（3 分鐘）

```bash
R=outputs/runs/rank-1-rt C=configs/local/ranking.json python3 -c "
import json,os;r=json.load(open(os.environ['R']+'/retarget.json'));c=json.load(open(os.environ['C']))['rules'];x=r['result'];g=x['retargeted']['legality'];v=x['fixed_script_verification'];b=g['burn_dv_mps'];T=x['retargeted']['t_team_sec']
print('狀態',r['status'],'| 失格',g['disqualified'],g['dq_reasons'],'| 間隔違規',g['penalty_count']);print('棒數',len(b),'| 最大單棒 %.3f m/s（上限 %g）'%(max(b),c['MAX_DV_MPS']),'| 總Δv %.2f m/s（上限 %g）'%(g['total_dv_mps'],c.get('MAX_TOTAL_DV_MPS',0)))
print('全攝動 d_min %.3f km | GMAT 固定版 Δr %.3f km 命中 %s'%(x['retargeted']['d_min_km'],v['miss_km'],v['intercept_success']));print('T_team %.1f s，離 T_max 還有 %.0f s | 攔截前最低高度 %.0f km'%(T,c['T_MAX_SEC']-T,v['min_radius_before_intercept_km']-6378.137));print('官方分數估計 %.4f'%g['official_score'])"
```

隊友 A 唸、主控對，**全部打勾才存 USB**：

- [ ] `狀態 accepted`、`失格 False`、`間隔違規 0`
- [ ] 最大單棒 ≤ 249 m/s
- [ ] 總 Δv ≤ 3,000 m/s
- [ ] d_min 與 GMAT Δr 都 < 4 km，`命中 True`
- [ ] 離 T_max ≥ 300 s
- [ ] 攔截前最低高度 > 100 km
- [ ] `T_MAX_SEC`、`k_t/C_t/k_v/C_v` 是今天的官方值，不是範本的 40000／0.0001／25000／0.002／1500
- [ ] 步驟 6 的 `verify` 印了 `✅`

存成帶分數的檔名，例如 `rank1_86.78_output_submit.txt`。

### 步驟 8：繳交（11:25 開始）

**能交整份自製 Script**：

1. 主辦機 GMAT 開 USB 上的 `output_submit.txt`，跑一次。
2. Report 的命中距離要跟步驟 7 的 GMAT Δr 一致；不一致就問工作人員的力學設定。
3. Script＋Report 照官方檔名上傳，確認成功。

**只能改題目 Script**：把 `output_submit.txt` 裡 `SC_Human` 的初始狀態、每棒 `ImpulsiveBurn`（`BurnB0`、`BurnB1`…）的 VNB 分量與滑行時間抄進題目 Script。

腳本必須全 ASCII，手改時不要加中文。

### 步驟 9：有空檔才做

只在 **11:08 前**已有保底時做，**11:25 一到就停**。多半只會同分，當保險：

```bash
cp configs/local/ranking.json configs/local/ranking-s1.json
```

把 `optimization.SEED` 改成 `1`，照步驟 5–7 跑，目錄用 `rank-2`、`rank-2-rt`、`rank-2-verify`。分數高 > 0.01 且清單全過才換。

---

## 三、出狀況怎麼辦

| 狀況 | 怎麼做 |
|---|---|
| **求解太慢**（11:15 還沒完） | 看 `run.log` 最後幾行。在「拆棒」就等（最多 10 分鐘）。在「primer 診斷 … 以 N 棒重搜」：另開終端跑[保底設定](#保底設定)，誰先完成用誰 |
| **結束碼 3** | 看 `rank-1/no_legal_route.json` 與能量下限。下限 > 3,000 m/s 就問工作人員；否則 `MAXITER` 改 2000 重跑（時間加倍） |
| **`失格 True`** | 看 `dq_reasons`；Δv 超標同結束碼 3 |
| **重瞄準不通過** | 加 `--retarget-burn N`（0 起算）換一棒餘裕大的，`--run-dir` 改 `rank-1-rt2`。還是不過就交 `rank-1/output_submit.txt` |
| **GMAT 打不開** | 確認路徑（必須 ASCII），重跑 `verify`；不行就到主辦機上跑 |
| **Mac 當掉或沒電** | 有備機就從步驟 5 重跑；沒有就交 USB 上最新那份 |
| **主辦機結果跟我們不同** | 問他們的力學模型與太空船參數，改 `GMAT_SPACECRAFT`／`GMAT_EPOCH`，從步驟 6 重跑 |

### 保底設定

```bash
cp configs/local/ranking.json configs/local/ranking-fast.json
```

`optimization.MAXITER` 改 `300`，`strategy` 加 `"PRIMER_GUIDED_RESEARCH": false`，照步驟 5–7 跑，目錄用 `rank-fast`、`rank-fast-rt`、`rank-fast-verify`。分數可能稍低。

---

## 四、已知地雷

1. `k_v`、`C_v` 的單位（初賽照抄 km/s 制，分數全錯）。
2. 邊界是地心距離還是高度（差 6,378 km）。
3. TA 正負號。
4. `T_MAX_SEC` 從 epoch 起算，不是從近地點。
5. `run.json` 的 `completed` 不代表能交，只看步驟 7。
6. `--run-dir` 不能已存在；`new-config` 不覆蓋。

---

## 附錄：T_max 工具擋下的情況

| 訊息 | 怎麼辦 |
|---|---|
| 「A 的距離永遠不會小於近地點」 | 多半把高度當地心距離，改 `--boundary-alt-km` |
| 「雙曲線不會再回來」 | 檢查 TA 正負號 |
| 「\|TA\| 必須 < …」 | TA 或 ECC 抄錯 |
| 「A 永遠在邊界內」、圓軌道、拋物線 | 問工作人員 |

A 已過近地點但還在邊界內時工具照算並附註，要跟工作人員確認定義。
