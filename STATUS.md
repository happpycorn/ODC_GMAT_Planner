# 專案狀態筆記（交接用）

給下一個 session（不管是我自己回來還是你自己看）快速抓回上下文用的，這份主要是「現在做到哪、還缺什麼、為什麼」的整理。**怎麼用這個工具看 [README.md](README.md)；演算法/物理模型原理看 [METHODOLOGY.md](METHODOLOGY.md)**；更細節的技術決策看 commit log 跟程式碼註解。

最後更新：2026-08-12。`improve-optimizer-and-gmat-integration` 分支已經 fast-forward
merge 回 `Master` 並 push，分支本身已刪除——**現在直接在 `Master` 上開發**。同一天內
又追加了 tqdm 進度條修復、console 輸出簡化、把 3 個規則數字搬進 config 這幾項，都已
commit 到 `Master`（尚未 push，見最新的 commit log）。

## 這是什麼

TASA/淡江大學辦的「第一屆軌道設計競賽」初賽用的任務規劃工具。太空船 B（我方）要在時間/燃料限制下攔截太空船 A（被動、只受重力）。`rules/` 資料夾裡有三份官方文件（正式規則 PDF ×2、0510 線上說明會簡報）。

規則重點：Δv ≤ 1500 m/s/次、機動間隔 ≥100s、T_max=4×A的軌道週期、**Δr ≤ 5km 即算成功且以內都是同分**（這點很關鍵，見下）、繳交格式是「Script + 至少模擬一次產生的 Report」一起上傳。初賽 A 是圓軌道；後面的排位賽/四強賽是完全不同玩法（A 變雙曲線／即時追逐戰），還沒開始準備。

## 這個 session 做了什麼

### 正確性
- Python 端加了含 J2 的差分修正 (`refine_lambert_burn`)，讓 Lambert 的理想解貼近 GMAT 實測，不用開 GMAT 就能高精度預覽分數
- Lambert 同時算順向/逆向，取較小 Δv（大傾角差情境影響很大，實測過省一半以上）
- 燃燒方向改球座標參數化，天生保證合規，不用事後懲罰排除
- NLP 微調加安全回退（比較微調前後 fitness，沒變好就退回，且區分「沒改善」vs「scipy 沒收斂」兩種訊息）
- **「命中容許範圍」利用**：規則只要求 Δr≤5km 就是滿分，所以最後一棒改成瞄準 A 附近容許球內最省油的點，不用死盯著精確位置（`MISS_TOLERANCE_KM`，預設 5.0，可調）
- 修了一個實測抓到的真 bug：GMAT script 的打靶原本還是瞄準 ShipA 精確位置，會把 Python 算好的「刻意打偏省油」設計悄悄蓋掉——現在改成瞄準絕對座標的瞄準點
- 安全邊界：Δv 內部軟上限 1490 m/s（真實 1500）、命中容許範圍軟上限比設定值少 1.5km（原本只留 0.1km，壓力測試發現某些軌道幾何落差可到 900m 才加大）
- **GMAT 實際收斂後的 Δv 現在會被記錄並檢查**（`FinalBurnDvMps`/`FinalBurnLegal`）——之前 `InterceptSuccess` 只看距離不看 Δv，GMAT 自己的打靶器完全可能悄悄修出一把超過 1500 m/s 的火而沒人發現，現在補上了

### 速度
- `fast_fitness_evaluator` 加 `nogil=True` + mealpy 改 `mode='thread'`，原本 `n_workers=1` 其實完全沒生效（預設 `mode='single'` 會忽略它）
- 族群大小改成跟真實決策變數維度掛鉤，舊公式在低燃燒次數時嚴重超編（180倍維度）
- 全流程實測從 373 秒壓到 40~60 秒量級（同樣的軌道規模）

### GMAT 整合
- `GmatConsole --exit --run` 自動無頭執行，`main.py` 跑完自動呼叫、自動讀報表對照，不用手動開 GUI（`--gmat-console` 換路徑，`--no-gmat` 跳過）
- GMAT script 內部：`Ship1/2`→`ShipA/B`、`OpenFramesInterface`（外掛依賴，官方電腦可能沒裝）→`OrbitView`（標準內建）、加 `ReportFile` 自動輸出 `InterceptSuccess`、修掉中文/非 ASCII 字元會讓 GMAT 解析器直接報錯的問題

### 其他
- `USE_J2` 開關（Python/GMAT 兩邊同步），`SEED` 可重現（但會自動退回單執行緒，多執行緒下亂數搶用有 race condition 沒法兩者兼得）
- `--config` 切換設定檔、`outputs/history/` 版本化、`outputs/run_history.jsonl` 執行紀錄
- `configs/config.json` 的 `orbit_A.ECC` 改成 0（照簡報說初賽 A 是圓軌道）——但 SMA/INC/其他軌道參數仍然是隨便編的測試值，等正式測資公布要整組換掉

## 這次追加的工作（同一天，config 驗證 + 多圈 Lambert 評估）

### Config 欄位驗證（`src/config_validator.py`，新檔案）
- `main.py` 的 `load_or_create_config()` 讀完 JSON 後會呼叫 `validate_config()`，把型別錯/缺欄位/物理上不合理的值 (SMA≤0、ECC 落在 [0,1) 之外、近地點在地球表面以下、`MAX_BURNS`/`MAXITER`/`POPSIZE` 等不是正整數……) 一次全部收集起來，印一份清楚列點的錯誤訊息後 `sys.exit(1)`，不會再讓打錯字的設定一路跑到 poliastro/mealpy 深處才炸出看不懂的 traceback。
- 另外對「型別合法但可疑」的值印警告但不擋執行：`MISS_TOLERANCE_KM > 5`（optimizer 會悄悄夾回 5，設的值不會真的生效）、`k_t`/`k_v` 是負的（會讓分數方向跟規則意圖相反）。
- 實測：合法設定照常跑完全流程；故意做壞的設定 (缺欄位/型別錯/ECC≥1/穿地球軌道/`MAX_BURNS` 含 0 或負數) 都各自觸發預期的清楚錯誤，`main.py --config <壞檔>` 乾淨結束、exit code 1，沒有 traceback。

### 多圈 Lambert (M>0)：評估後決定暫不實作
STATUS.md 原本寫「大 SMA 落差的情境可能受益，但還沒驗證投報比」，這次用兩個刻意刁難的合成情境(不是真的官方測資) 實測驗證：

1. **極端傾角差** (照目前 config，A/B 傾角差到 100°)：單純比較 Lambert 轉移本身，M=1 確實常常比 M=0 省 10~20% Δv；但套用近地點合規檢查後發現，這個情境不管 M 多少，單棒直飛的 Δv 都遠遠超過 1500 m/s 上限——M>0 省下的那 10~20% 完全不夠填平缺口，救不了。
2. **純 SMA 落差、同平面** (B: SMA 7500 圓軌道，A: SMA 18000 圓軌道，INC/RAAN/AOP 全部對齊，排除掉傾角差這個干擾變因，直接對應原本的假設)：`M=0/1/2` 在整個 `[0, T_max]` 的飛行時間網格裡完全找不到合規解，`M=3` 只在一個窄窗 (~56000s 附近) 找到剛好壓線合規的解 (~1475 m/s)。單看這個結果，會覺得 M>0「解鎖」了原本 M=0 打不到的解。
   但是——這個小實驗只固定了「等待時間=0、瞄準 A 的精確位置」，沒開放真正 optimizer 擁有的兩個自由度：**t_wait 可以自由選擇出發時機**、以及**命中容許範圍可以讓 Lambert 瞄準偏移點省油**。把這個純 SMA 落差情境丟進真正的 `MissionOptimizer` 跑一次 (`MAX_BURNS=[1]`，M 依然固定 0)，最佳化器自己找到 t_wait=373.3s、單棒 Δv=1492.6 m/s、**完全合規**、Score 100/100。也就是說：M=0 配合現有的時機選擇 + 命中容許範圍利用，已經能解掉這個「特意設計來為難 M=0」的情境，不需要 M>0。

**結論**：M>0 的 Lambert 解單獨拿出來看確實常常比較省油，但把它接進真正的 optimizer 需要 (a) 處理每個 M 是否可行的邊界情況 (`izzo` 對太大的 M 會丟例外)、(b) 每次 fitness evaluation 的 Lambert 呼叫數再乘上好幾倍 (直接推翻這個 session 前半段把全流程從 373 秒壓到 40~60 秒的工作)。而目前測過的兩個「刻意刁難」情境，既有的自由度 (t_wait 時機選擇、多棒自由方向噴射、命中容許範圍瞄準偏移) 都已經足夠達到 100 分，看不出 M>0 會多解鎖什麼。**決定跟下面清單裡的「固定 60 秒 RK4 步長」「物理直覺初始種子」一樣先不做**，等正式測資公布後，如果真的出現這兩個合成情境沒設想到的幾何 (才知道是什麼樣子)，再回頭考慮。
實驗腳本沒留在 repo 裡 (純粹一次性驗證，不是可重用工具)，這裡的數字是實際跑出來的記錄。

### GMAT script 裝飾用參數潤飾
- `DragArea`/`SRPArea` 原本是 15/1 (SRP 受光面積比阻力面積還小，物理上不太合理)，改成自洽的 6/8。`ForceModel` 的 `Drag=None`、`SRP=Off`，這些欄位本來就是裝飾用不影響結果，純粹是改得更像樣。
- 在 script 裡加了英文註解，講清楚 `DryMass`/`Cd`/`Cr`/`DragArea`/`SRPArea`/`Isp`/`GravitationalAccel` 為什麼是裝飾用 (Drag/SRP 關閉、`DecrementMass=false`)，不用下次再重新想一遍。
- **過程中抓到自己的一個回歸**：第一版註解寫成中文，直接會重踩這個分支前面已經修過的雷 (`887e64e`：非 ASCII 字元讓 GMAT 解析器直接報錯)。改成跟其他註解一致的純英文，並且實際掃過產生出來的 `outputs/output.txt` 確認 0 個非 ASCII 字元，再整套跑一次含 GMAT 驗證確認腳本還是能正常解析/收斂 (`InterceptSuccess`/`FinalBurnLegal` 都是 true) 才收工。

### tqdm 進度條修復 + console 輸出簡化
- **根因**：`_optimize_burn_case`（跑在 `ProcessPoolExecutor` 的子行程裡）直接呼叫 `print`/`tqdm.write`，但外層進度條活在主行程——子行程不知道進度條的游標位置，好幾個子行程各自時間點搶著寫同一個終端機，跟主行程的 `\r` 覆寫互相打架，導致進度條沒辦法原地更新，越印越往下（使用者回報的症狀）。
- **修法**：子行程改成只回傳資訊 (`epochs_run` + 一個簡短備註字串)，所有 print 都收斂到主行程做，讓 tqdm 全程只在單一行程裡運作。用 `cat -vet` 看過原始字元確認整段進度條重繪現在是完整不被打斷的 `\r` 序列。
- 順便把使用者覺得「印太多」的搜尋階段雜訊砍掉：3 條「核心啟動」併成 1 條、每個推進次數完成從 2 行併成 1 行、拿掉每次分數進步就喊一次的「發現新最佳解」（改成搜尋結束後只報一次最終選了哪個方案）、兩段計算時間分隔線併成 1 行、拿掉跟 GMAT 驗證結果重複的提醒。任務清單/最終分數/GMAT 驗證這些真正要看的輸出完全沒動。
- 實測：全流程含 GMAT 驗證重跑一次，分數/Δv/T_team 跟改之前完全一致 (100/100, InterceptSuccess ✅)，確認只是砍雜訊沒動到邏輯。

### 把規則規定的 3 個數字搬進 config
翻 `Regulations_PrelimRound-20260605.pdf` 對照程式碼，發現 `ΔV_lim`（1500 m/s）、機動間隔下限（100s）、`T_max` 的週期倍數（4 倍）這三個規則數字是寫死在 `optimizer.py` 裡，沒有跟旁邊的 `k_t/C_t/k_v/C_v`（同樣是規則數字）放在一起。新增三個 config 欄位：`MAX_DV_MPS`、`MIN_MANEUVER_INTERVAL_SEC`、`T_MAX_PERIOD_MULTIPLE`，預設值等於現在初賽規則的數字，`config_validator.py` 也加了必填 + 值域檢查（必須是正數）。
- 動機：規則第 7 節說晉級賽「會有更具挑戰性的情境與動態環境條件」，但這份 PDF 只涵蓋初賽，沒寫這三個數字會不會變——不確定，但不管會不會變，這樣改都是合理的架構收斂：晉級賽如果規則數字真的不一樣，改 config 就好，不用再回來翻 `optimizer.py`。
- 實測：`validate_config` 對三個新欄位的必填/值域檢查都如預期觸發；直接 instantiate `MissionOptimizer` 塞不同的數字進去，確認 `self.MAX_DV`/`self.MIN_COAST_TIME`/`self.T_max` 三個屬性都正確反映 config 的值（不是巧合等於預設）；用預設值跑一次完整流程 (含 GMAT)，分數/Δv 跟改之前完全一致，確認沒有把初賽這一輪跑壞。

### config.json 分組整理（使用者反映參數變多、有點亂）
上面幾輪陸續加欄位後，config 頂層累積了 12 個欄位（`orbit_A`/`orbit_B`/`optimization` 三個巢狀物件 + 9 個攤平的純量欄位），改成 4 個頂層區塊，依「誰決定這個數字」分組：
- `orbit_A` / `orbit_B`：軌道六根數，不變
- `rules`：主辦方規定/公告、我們不能改的數字 —— `MAX_DV_MPS`/`MIN_MANEUVER_INTERVAL_SEC`/`T_MAX_PERIOD_MULTIPLE`/`k_t`/`C_t`/`k_v`/`C_v` 全部搬進來
- `strategy`：我們自己的任務設計選項，不是規則要求 —— `USE_J2`/`MISS_TOLERANCE_KM` 搬進來
- `optimization`：純演算法搜尋設定，不變

改動範圍：`configs/config.json`、`main.py`（`DEFAULT_CONFIG` + `append_run_history` 記錄的欄位）、`src/optimizer.py`（`MissionOptimizer.__init__` 改讀 `config["rules"]`/`config.get("strategy", {})`）、`src/config_validator.py`（拆成 `_validate_rules`/`_validate_strategy` 兩個新函式）、`README.md` 欄位表。
- 實測：新結構的 config 通過驗證；故意拿掉整個 `rules`/`strategy` 區塊、`strategy.USE_J2` 型別錯、`rules.k_t` 是負的（軟性警告）都如預期觸發；設定檔不存在時自動生成的預設範例也是新結構，且能自己通過驗證；用不變的正式 config 跑一次全流程 (含 GMAT)，分數/Δv/T_team 跟改之前完全一致 (100/100, InterceptSuccess ✅)；順便確認 `run_history.jsonl` 記錄的是完整的 `rules`/`strategy` 物件，不是拆散的欄位。

### 新增 METHODOLOGY.md（拆分文件：怎麼用 vs 怎麼算的）
使用者反映應該把「怎麼用」跟「怎麼算的」拆成兩份文件。`README.md` 本來就幾乎全是「怎麼用」的內容（安裝/config/執行/輸出/提交前檢查），不用大改；新寫了 [METHODOLOGY.md](METHODOLOGY.md)，把散落在程式碼註解跟這份 STATUS.md 裡的技術知識整理成一份對外可讀的說明：問題設定、整體流程、物理模型 (RK4+J2)、決策變數編碼 (球座標參數化)、Lambert 攔截 + 命中容許範圍利用、安全邊界設計、L-SHADE/L-BFGS-B 最佳化、計分公式、GMAT 驗證流程 (含 aim-point sync 那個 bug 的故事)、已知限制。兩份文件互相加了連結。
- 寫的時候把引用的具體數字都回頭對照過原始碼/STATUS.md 抓錯了一個：族群大小超編寫成「快 200 倍」，實際是「180 倍」(360 個體 / 2 維)，已修正；其他引用數字 (108m 積分誤差、863m 命中容許壓力測試落差、17m 理論最差 Achieve 誤差) 都對照過原文確認無誤才留著。
- 副作用：這份文件剛好也對得上規則第 6 節「設計理論」平手加賽的要求（同分要上台講 5 分鐘軌道設計方法論），晉級賽如果真的平手用得到。

### 新增 sweep_burns.py：掃描一個情境需要燒幾次
起因：用 `configs/practice_scenario.json`（自己編的中等難度練習情境，不是官方測資，用來模擬跑一次比賽的感覺）實測發現「燃燒次數越多、搜尋時間越長」——族群大小是決策變數維度 × POPSIZE，維度隨燃燒次數線性長，但 `MAXITER`（世代數）不會跟著長，導致高燃燒次數案例在同樣代數預算下天生吃虧。實測驗證過這個效應是真的：`MAX_BURNS=[1..6]` 時 6 次燒 (`MAXITER=1000`) 目標值 -99.9863，明顯輸 2 次燒的 -99.9941；把 `MAXITER` 拉到 3000 (3倍)，6 次燒追到 -99.9952，反而小幅超過——證實純粹是預算不夠冤枉了它，不是本質上比較差。

新增 [`sweep_burns.py`](sweep_burns.py)，把這個結論實作成兩階段流程：
1. **粗掃**：`MAX_BURNS` 開一個寬範圍（預設 1-6），`MAXITER` 刻意調低（預設 300），快速找出分數大概從哪個燃燒次數開始不再明顯進步（`find_elbow`）。這階段的數字不能直接當結論，只能抓候選範圍。
2. **精細驗證**：只針對候選範圍附近（`--window` 控制往上延伸幾格），用 config 原本的 `MAXITER`（使用者已經調過、信任的預算）重新跑一次「公平」比較，這一步的數字才拿來下結論。

`MissionOptimizer` 加了 `self.burn_case_results` 屬性（`run_study()` 完成迴圈裡順手記錄每個燃燒次數的 fitness/代數/備註），純增量、不影響 `run_study()` 原本的回傳值，`main.py` 的正常流程不受影響。

值得注意的細節：工具判斷「已經打平」用的容忍度（`--plateau-tol`，預設 0.05 分）是主觀取捨——在 Δv/時間預算寬鬆的情境下（像 practice_scenario 這種），連 1 次燒都能拿到 99.98 分，容忍度一寬就會建議「用最少的那個就好」，但**分數打平不代表 Δr_min/ΔV_team/T_team 這些平手判定用的原始數字也打平**（規則第 6 節：先比 Δr_min，再比 ΔV_team，再比 T_team），這點在工具的結論輸出裡有特別提醒，正式方案還是要回頭看 Mission Plan 的細節數字，不能只看建議就定案。
- 實測：對 `practice_scenario.json` 跑過完整兩階段（`--burns 1-6`）跟縮小範圍的快速版（`--burns 1-3 --coarse-iters 150`），兩次都正確跑完、印出趨勢表跟建議，`--output-config` 能正確把建議寫成新的 config 檔。

## 還沒做 / 值得考慮的

優先順序由高到低：

1. **正式測資公布後，`configs/config.json` 整組要換成官方數字**（軌道六根數 + `k_t/C_t/k_v/C_v`）。現在的數字除了 `orbit_A.ECC=0` 是照簡報修正過的，其他都是我們自己編的，不能直接拿去用。
2. **固定 60 秒 RK4 步長**：查證過對 LEO 型軌道有 ~108m 的積分誤差（慢軌道幾乎沒差），但因為安全邊界（1.5km）遠大於目前觀察到的最大落差（~900m），評估後決定先不動——如果拿到正式測資後發現落差逼近安全邊界，再回頭考慮自適應步長。
3. **物理直覺的初始種子** 沒做（讓 L-SHADE 從一個粗略 Hohmann-like 猜測開始，而不是純隨機初始化）——早期評估過投入產出比不確定，沒有動手。
4. 排位賽（A 變雙曲線軌道）、四強賽（即時追逐戰）**完全還沒碰**，等晉級再說。

## 跑法提醒

```bash
uv run main.py                          # 用 configs/config.json
uv run main.py --config configs/x.json  # 換設定檔
uv run main.py --no-gmat                # 跳過自動 GMAT 驗證
```

正式提交前：確認 `run_history.jsonl` 最新那筆 `gmat_verified.intercept_success` 和 `final_burn_legal` 都是 `true`。README.md 有更完整的欄位說明。

## 這個 session 的工作方式（給下次的自己參考）

- 使用者很重視「實測驗證，不要用猜的」——這個 session 好幾次理論上「應該沒問題」的東西實測後發現是錯的（seed 沒生效、GMAT 打靶蓋掉省油設計、安全邊界不夠寬），都是靠寫小驗證腳本、跑 `main.py`、對照 GMAT 實際輸出抓出來的，不是光看程式碼推理出來的。改動後最好都找方法實測，不要只憑理論保證。
- 傾向小步快跑：改一項、驗證一項、確認沒問題再繼續，不要一次改一大包才測。
