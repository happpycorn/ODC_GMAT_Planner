# 專案狀態筆記（交接用）

給下一個 session（不管是我自己回來還是你自己看）快速抓回上下文用的，這份主要是「現在做到哪、還缺什麼、為什麼」的整理。**怎麼用這個工具看 [README.md](README.md)；演算法/物理模型原理看 [METHODOLOGY.md](METHODOLOGY.md)**；更細節的技術決策看 commit log 跟程式碼註解。

最後更新：2026-08-13 晚間。`improve-optimizer-and-gmat-integration` 分支已經 fast-forward
merge 回 `Master` 並 push，分支本身已刪除——**現在直接在 `Master` 上開發**。分支合併後
又陸續追加了 tqdm 進度條修復、console 輸出簡化、把 3 個規則數字搬進 config、config 分組
整理、`sweep_burns.py`、固定燃燒繳交腳本、清依賴、`local.gmat_console_path`、`outputs/`
資料夾建立修復、izzo 例外處理、**一個發現後又撤銷的危險改動 (RK4 自適應步長，見下)**
這幾項，全部已 commit 且已 push（見最新的 commit log，最新一筆是 `62f8d6c`）。working
tree 乾淨，跟 `origin/Master` 同步。

**⚠️ 本次更新最重要的一件事**：發現這個工具在「極端軌道」(SMA ~80,000km、ECC ~0.87
這個量級) 上完全沒有驗證過，Python 預測跟 GMAT 實測會差到四五個數量級，連 GMAT 自己
的求解器都收斂不了。細節見下面「極端軌道測試」那一節。**這不是今天的改動造成的，是
一直都存在、今天才第一次被測出來的深層限制。**

## 這是什麼

TASA/淡江大學辦的「第一屆軌道設計競賽」初賽用的任務規劃工具。太空船 B（我方）要在時間/燃料限制下攔截太空船 A（被動、只受重力）。`rules/` 資料夾裡有三份官方文件（正式規則 PDF ×2、0510 線上說明會簡報）。

規則重點：Δv ≤ 1500 m/s/次、機動間隔 ≥100s、T_max=4×A的軌道週期、**Δr ≤ 5km 即算成功且以內都是同分**（這點很關鍵，見下）、繳交格式是「Script + 至少模擬一次產生的 Report」上傳。初賽 A 是圓軌道；後面的排位賽/四強賽是完全不同玩法（A 變雙曲線／即時追逐戰），還沒開始準備。

**時程**（2026-08-13 查證，來源：官方簡報 + 淡江航太系官網 + 報名表單本身）：線上報名 5/11~**8/21 週五下午5點截止**（查證當下還沒截止，剩沒幾天，記得確認團隊真的報名了）；GMAT 實體訓練 6/27（已過）；**初賽 8/29，淡江大學淡水校園**；決賽 11/09，大臺南會展中心。官方目前完全沒公布任何測試用的軌道數字或範例——`k_t/C_t/k_v/C_v` 跟 A/B 六根數都要等「題目 Script」發布才知道，詳細計分/繳交規則也還沒完整公告，要持續關注 TASA 官網。

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

### 新增「固定燃燒版本」的繳交腳本 (`outputs/output_submit.txt`)
起因：使用者擔心一般版本最後一棒靠 GMAT 的 `Target/Vary/Achieve`（DifferentialCorrector）即時求解，換到比賽當天主辦單位的電腦上執行時，求解器的收斂行為可能跟我們自己測的不一樣。討論後確認方向：**不是拿掉求解器，而是把求解器已經找到的答案變成常數**——先用一般版本 + GMAT 的 DC 把正確答案找出來，驗證乾淨通過後，把 GMAT 自己收斂出的最後一棒 VNB 分量（不是 Python 的估計值）直接寫死，產生一份完全不含任何求解器的新腳本，單純傳播 + 施加燃燒。

改動：
- `script_generator()` 加 `final_burn_fixed_vnb`/`output_filename` 兩個參數，`None`（預設）走原本的 DC 路徑；給值就走固定路徑（最後一棒跟其他棒一樣直接套用，不進 `Target/Vary/Achieve`）。共用同一份函式，只有 Burns 區塊跟 Mission Sequence 的最後一段分支，其餘（Spacecraft/ForceModel/Propagator/OrbitView/ReportFile）完全共用，避免兩份重複的樣板。
- `Report_Intercept` 多加三欄（最後一棒的 `Element1/2/3`），讓 `main.py` 讀回 GMAT 實際收斂後的燃燒向量。
- `main.py`：一般版本驗證乾淨通過（成功+收斂+合規）後，自動用讀回來的向量產生 `outputs/output_submit.txt`，**再送一次 GMAT 驗證**確認這份「重新單純傳播」出來的結果站得住腳，兩者印出來對照。新增 `--no-fixed-script` 可以跳過這一步（省幾秒，開發迭代時用）。`append_run_history` 多記一個 `fixed_script_verified` 欄位。
- 實測：`configs/practice_scenario.json` 跑一次完整流程，一般版本 MissDistance 3984.786m，固定版本重新驗證出來是 3985.204m——只差 0.4m，證實「寫死 GMAT 收斂後的值再重跑」確實能重現幾乎一樣的結果；另外確認固定版本產生的 script 裡完全沒有任何 `Target`/`Vary`/`Achieve`/`DifferentialCorrector` 實際指令（只有註解提到），也確認 0 個非 ASCII 字元（沒有重踩 `887e64e` 那個雷）。

### 清掉沒用到的重量級依賴 + 加「部署到新電腦」的說明
起因：使用者問「這個要部署到一台全新電腦要怎麼做」——查 `pyproject.toml` 發現 `torch`/`optuna`/`pymoo`/`line-profiler` 四個依賴，整個 repo (`src/`、`main.py`、`sweep_burns.py`) 完全沒有 import 過，應該是早期實驗階段（`GPU_Trial` 分支、舊版 `optuna_optimizer.py`）留下的殘留，這兩個都已經在前面的 session 清掉了，但 `pyproject.toml` 沒有跟著清。`torch` 又特別重，`uv lock` 重新解析後移除了一整串 NVIDIA CUDA 函式庫（`nvidia-cublas`/`nvidia-cudnn`/`nvidia-cusolver`...）、`sqlalchemy`、`sympy`、`networkx` 等一堆間接依賴——這台完全沒有 GPU 的機器上根本用不到。
- 改動：`pyproject.toml` 的 `dependencies` 從 7 個砍到 3 個（`astropy`/`mealpy`/`poliastro`，`numpy`/`numba`/`scipy`/`tqdm` 是這幾個的間接依賴，不用列）；重新 `uv lock`；README 補了「Python 3.8+」跟 `pyproject.toml` 實際要求的 3.12+ 對不上的錯誤，順手修正。
- 實測：清完後跑 `configs/practice_scenario.json --no-gmat` 完整流程一次，確認 tqdm（雖然被移除出直接依賴，但透過 mealpy 間接帶進來）跟其他套件都還在，沒有 ImportError，結果正常。目前 `.venv` 大小 1.1GB（清之前含 torch+CUDA 套件應該大好幾倍，沒留清之前的數字對照，但移除的套件清單看得出差很多）。
- README 新增「🖥️ 部署到一台全新電腦」章節，分兩種情況講清楚：(A) 要在新電腦跑整套設計工具（`configs/` 被 gitignore 排除、GMAT 要另外裝、`--gmat-console` 一定要蓋掉寫死的預設路徑）；(B) 比賽當天主辦單位的電腦——**其實不需要部署這整套東西**，`outputs/output_submit.txt` 本身就是一份純文字 GMAT script，直接帶去在對方的 GMAT 裡開檔執行就好，不需要 Python/uv/這個 repo 的任何程式碼。這個區分本身也是「固定燃燒版本」那個功能存在的意義。

**⚠️ 這次清理留了一個真的會炸的回歸，之後補上了（見下一節）**：上面「實測」那句寫的「tqdm 透過 mealpy 間接帶進來」是錯的——當時本機的 `.venv` 是清理前就裝好的舊環境，`uv run` 沒有重新驗證每個 import 是不是真的能被目前的 lockfile 滿足，所以在自己機器上測不出問題。隊友在全新電腦上 `uv run main.py` 直接 `ModuleNotFoundError: No module named 'tqdm'`。教訓：**改完依賴之後，光靠既有 `.venv` 測不出「全新環境裝不裝得起來」這種問題，得真的刪掉 `.venv` 重來一次**，或者請別人在全新環境上實測。

### 修 tqdm 遺漏（上面那個回歸的修復）
`src/optimizer.py` 直接 `from tqdm import tqdm`，但 `tqdm` 從來沒被列進 `pyproject.toml` 的 `dependencies`，一直是「賭它會被間接帶進來」。這次清理把 `torch`/`optuna`/`pymoo`/`line-profiler` 拿掉之後，間接依賴的解析結果變了，`tqdm` 完全沒被解析進 lockfile——不是只有回報的那位隊友的環境特殊，是**這次清理之後所有全新安裝都會炸**。
- 修法：把 `tqdm` 明確加進 `pyproject.toml` 的 `dependencies`（本來就該這樣，直接 import 的東西不該賭它靠間接依賴活著）。
- 實測：這次真的刪掉本機 `.venv` 重來，`uv lock` 印出 `Added tqdm v4.70.0`、`Added colorama v0.4.6`（tqdm 在 Windows 上的顏色套件依賴）——證實清理前 `tqdm` 真的完全沒被解析進來，不是我看錯。重新從乾淨環境跑一次完整流程確認正常。
- 因為是會擋住別人立刻沒辦法動的回歸，這次直接 commit + push，沒有照平常「累積幾個 commit 再問要不要推」的節奏。

### 新增 `local.gmat_console_path`（選填的 config 欄位）
起因：使用者發現 `GMAT_CONSOLE_DEFAULT` 寫死在 `main.py`（被 git 追蹤），換一台電腦/換一個人開發，這個值一定要改，但改了又變成本地修改污染 git、容易在 pull/merge 卡住。既然 `configs/config.json` 本來就被 gitignore 排除，機器相關的設定放在那裡才是一致的做法，不該混進 `main.py`。
- 新增 config 第五塊（選填，不在 `top_required` 裡）：`local`，目前只有 `gmat_console_path` 一個欄位。`config_validator.py` 加 `_validate_local`（型別檢查：必須是字串，不強制要有這個區塊）。
- `main.py` 的 `--gmat-console` 解析優先順序：CLI 參數 > `config["local"]["gmat_console_path"]` > `GMAT_CONSOLE_DEFAULT`（最後備援，就是我這台機器的路徑）。
- 實測：故意在 config 裡塞一個錯的路徑（不帶 `--gmat-console`），確認真的印出「找不到 GmatConsole (那個錯路徑)」的警告，不是悄悄退回寫死的正確路徑；換回正確路徑、完全不帶 `--gmat-console`，確認 GMAT 驗證正常跑完；最後確認 `--gmat-console` 給錯路徑時還是蓋得過 config 的正確值——三層優先順序都驗證過。

### 順手驗證：USE_J2 關掉，Python 端跟 GMAT script 是不是真的同步
使用者問的，追蹤程式碼確認 `strategy.USE_J2` → `optimizer.USE_J2`/`J2_VAL`（Python 端傳播）→ `main.py` 兩處 `script_generator()` 呼叫（一般版本+固定版本）都帶 `use_j2=optimizer.USE_J2` → GMAT script 的 `GravityField.Earth.Degree/Order` 跟著變 0/0。重力場開關那段是共用模板，不在 DC/固定版本的分支邏輯裡，兩種腳本都會同步。實測：`USE_J2=false` 跑一次，`outputs/output.txt` 裡 `Degree`/`Order` 確認都是 0，GMAT 驗證照樣成功。結論：**兩邊確實同步，沒有問題**。

### 修 `outputs/` 資料夾不存在的崩潰（隊友回報）
跟 tqdm 那個回歸同一個病因：`outputs/*` 整個被 `.gitignore` 排除，全新 `git clone` 下來這個資料夾根本不存在 (git 不會建空資料夾)，`script_generator.py` 寫 `outputs/<file>` 之前沒有 `os.makedirs("outputs", exist_ok=True)`（只有 `outputs/history/` 那層有建，但建的時機已經在第一次寫檔失敗之後）。這台機器測不出來是因為 `outputs/` 資料夾在這個 session 開始前就已經存在（裡面還有更早、跟這個專案無關的舊檔案）。
- 修法：`script_generator()` 開頭補上 `os.makedirs("outputs", exist_ok=True)`。
- 實測：這次真的把本機的 `outputs/` 整個資料夾搬到別的地方（模擬「完全沒有」的狀態），確認能正常建立資料夾並寫檔，測完把原本累積的 session 紀錄搬回來。
- commit `713523b`，因為會擋住隊友下一步，直接 push。

### 找不到 GmatConsole 的警告訊息，補上 `local.gmat_console_path` 的提示
`DEFAULT_CONFIG` 刻意不生成 `local` 區塊（沒有通用預設路徑），所以隊友全新安裝跑出來的警告只提了 `--gmat-console`/`--no-gmat`，沒提到這個新選項——得自己去翻 README 才知道。改成警告訊息裡直接印出要加的 JSON 片段。commit `cf94da7`。

### 🔴 極端軌道測試：一個危險改動的完整故事 (加了又撤銷)
使用者故意想測極限情境（`orbit_A`: SMA=80000km, ECC=0.87, INC=90°——遠地點快 15 萬公里，接近月球距離）。過程分四階段，**第三階段那個改動已經被撤銷，只留第四階段的修復**：

1. **一開始「跑不出結果」**：其實不是壞掉，是真的在算，只是慢——`T_max=4×週期` 隨 SMA 三次方成長，這組軌道的 `T_max` 高達 90 萬秒 (10.4 天)，而 RK4 固定 60 秒步長代表單次傳播要走 1.5 萬步，比一般測過的情境 (`T_max` 幾萬秒等級) 貴 10~35 倍。
2. **危險的「修復」(已撤銷)**：把 `dt` 改成跟 `T_max` 成比例放大 (`max(60.0, T_max/1600.0)`)，讓極端情境的步數回到跟一般情境差不多——**這個改動上了 commit `ebaf728`、也 push 了**，速度確實從 150+ 秒壓到 14 秒，一般情境 (`practice_scenario.json`) 的回歸測試也過了。
3. **但這個改動是錯的**：因為步長是跟 `T_max`（整個任務的時間尺度）綁定，沒考慮到中途一次機動可能製造出一個近地點很低、局部速度很快的軌道——那一段用「整體平均」算出來的粗步長積分，RK4 會發散。實測抓到：某組候選解的 `r_curr` 在傳播中飆到 `9.88×10^10 km`（比太陽系還大 600 多倍），完全是數值爆炸，餵進 Lambert 求解器後不是崩潰就是算出一個「看起來合法但其實是垃圾」的解。**用 `git revert` 撤銷了 (`91bd68f`)，已 push。極端軌道重新變回慢，但至少不會再算出假答案。**
4. **順便修的另一個問題**：`izzo` (Lambert 求解器) 內部的 Householder 疊代對退化幾何會丟 `RuntimeError("Failed to converge")`，`fast_fitness_evaluator` 原本沒接住，一個候選解踩到就讓整個 `model.solve()` 當掉，白白浪費掉那個燃燒次數案例已經算完的搜尋結果 (實測：3 個案例裡 2 個因此報廢)。這個問題不是新引入的，是本來就有、只是沒有情境慢到能撞見過。用 numba 的 `try/except` 接住 (驗證過 numba 能正確 catch 巢狀 njit 函式丟出的例外，不會退回 object mode)，兩個方向都失敗就當作這組候選解是 0 分，讓 L-SHADE 自然淘汰它，不要拖垮整次搜尋。commit `62f8d6c`，已 push。**這個修復是對的、有留著。**

**修復後重新完整測過兩組極端情境（含 GMAT 驗證），結果**：

| | orbit_A 極端 (B 正常 LEO) | orbit_A + orbit_B 都極端 |
|---|---|---|
| 崩潰？ | ✅ 沒有 (3 案例都跑完) | ✅ 沒有 (3 案例都跑完) |
| 耗時 | 29.1 分鐘 | 26.8 分鐘 |
| Python 預測 Δr_min | 3488m（判定成功） | 3496m（判定成功） |
| **GMAT 實際 Δr_min** | **50,229,818 m** | **25,401,794 m** |
| GMAT Targeter | ❌ 未收斂 | ❌ 未收斂 |

**結論（很重要）**：崩潰/數值爆炸的問題確實修好了，但底下曝露出一個更深、跟這次改動完全無關、原本就存在的限制——**這個工具目前只在「一般規模」軌道（大概到中高軌道 MEO 等級）驗證過**。SMA 大到 80,000km、ECC 高到 0.87 這種近月距離、高離心率的極端軌道，Python 端的簡化模型 (二體+J2、`refine_lambert_burn` 的牛頓修正) 算出來的答案跟 GMAT 真實模擬差了四五個數量級，連 GMAT 自己的 DC 都收斂不了——不是安全邊界不夠寬 (那是差幾百公尺等級的問題)，是模型本身的假設在這個尺度下完全站不住腳。**還沒找出精確的「能信任」跟「不能信任」的軌道規模分界線在哪，也還沒修——這是下面「還沒做」清單的新增第一優先項。**

用到的兩組測試 config 沒留在 repo 裡（純粹一次性診斷，存在對話紀錄裡，不是 repo 裡的檔案）：
```
情境一 orbit_A: SMA=80000, ECC=0.87, INC=90, RAAN=5, AOP=5, TA=5 / orbit_B: SMA=7500, ECC=0, INC=0, RAAN=0, AOP=0, TA=0
情境二 orbit_A 同上 / orbit_B: SMA=80000, ECC=0.87, INC=0, RAAN=5, AOP=5, TA=5
```

## 還沒做 / 值得考慮的

優先順序由高到低：

1. **🔴 新發現，最優先：極端軌道 (SMA~80,000km/ECC~0.87 這個量級) 的 Python 預測完全不能信，GMAT 自己的求解器也收斂不了**（詳見上面「極端軌道測試」那一節）。目前完全不知道「一般規模」跟「極端規模」的分界線在哪——初賽 A 是圓軌道、SMA 大概不會離譜，這個問題**大概率不影響初賽**，但排位賽/四強賽的軌道規模未知，值得先弄清楚這個工具的有效範圍到哪裡，或至少加一個「軌道規模超出已驗證範圍」的警告，不要讓使用者誤信一個其實是垃圾的預測。**這不是一天能解掉的，可能需要重新檢視 Python 端的精度假設，或考慮換一種做法（例如乾脆放棄 Python 預測，搜尋階段就直接呼叫 GMAT）。**
2. **正式測資公布後，`configs/config.json` 整組要換成官方數字**（軌道六根數 + `k_t/C_t/k_v/C_v`）。現在的數字除了 `orbit_A.ECC=0` 是照簡報修正過的，其他都是我們自己編的，不能直接拿去用。
3. **固定 60 秒 RK4 步長**：原本的評估（查證過對 LEO 型軌道有 ~108m 的積分誤差，安全邊界 1.5km 夠用）只適用於「一般規模」軌道，上面第 1 項的極端軌道測試已經證明這個假設在夠極端的情況下完全不成立——但兩者的根因可能不一樣（第 1 項看起來是模型假設本身的問題，不只是步長粗細），還沒有定論，先把這兩項的關係搞清楚再決定要不要做自適應步長。
4. **物理直覺的初始種子** 沒做（讓 L-SHADE 從一個粗略 Hohmann-like 猜測開始，而不是純隨機初始化）——早期評估過投入產出比不確定，沒有動手。
5. 排位賽（A 變雙曲線軌道）、四強賽（即時追逐戰）**完全還沒碰**，等晉級再說。

## 跑法提醒

```bash
uv run main.py                          # 用 configs/config.json
uv run main.py --config configs/x.json  # 換設定檔
uv run main.py --no-gmat                # 跳過自動 GMAT 驗證
```

正式提交前：確認 `run_history.jsonl` 最新那筆 `gmat_verified.intercept_success` 和 `final_burn_legal` 都是 `true`。README.md 有更完整的欄位說明。

## 這個 session 的工作方式（給下次的自己參考）

- 使用者很重視「實測驗證，不要用猜的」——這個 session 好幾次理論上「應該沒問題」的東西實測後發現是錯的（seed 沒生效、GMAT 打靶蓋掉省油設計、安全邊界不夠寬、`local` dt 自適應改動），都是靠寫小驗證腳本、跑 `main.py`、對照 GMAT 實際輸出抓出來的，不是光看程式碼推理出來的。改動後最好都找方法實測，不要只憑理論保證。
- 傾向小步快跑：改一項、驗證一項、確認沒問題再繼續，不要一次改一大包才測。
- **新教訓（RK4 自適應步長那次）**：只在「一般規模」情境上跑過回歸測試就以為沒事是不夠的——那次改動在 `practice_scenario.json` 上完全正常，卻在極端規模的情境上讓數值直接爆炸。**改動核心物理引擎/演算法時，光靠一種規模的情境驗證不夠，至少要用差異夠大的多種規模交叉測過，才能真的說「沒問題」。**
- **新教訓（依賴清理那次）**：改完 `pyproject.toml`/依賴之後，只在本機既有的 `.venv` 測不出「全新環境裝不裝得起來」這種問題（本機的 venv 可能還留著清理前的殘留套件，掩蓋掉問題）。**改完依賴後，要嘛自己刪掉 `.venv` 重來一次真的模擬全新環境，要嘛請別人在真正全新的機器上測。** 這個 session 至少踩到兩次同一類的坑（`tqdm` 遺漏、`outputs/` 資料夾不存在）。
- 這個 session 後半段有隊友在幫忙用全新 Windows 環境實測，抓到好幾個只有在「完全乾淨的環境」才會現形的問題（tqdm 依賴、`outputs/` 資料夾、GMAT 路徑寫死）——**這種交叉環境測試很有價值，比自己一個人在同一台開發機上測更容易抓到部署層級的問題**，值得繼續維持這個習慣。
- 背景執行長時間指令（例如極端情境的完整流程，可能要跑 20~30 分鐘）時，**不要同時開兩個一起跑**——這個 session 曾經讓兩組極端情境的測試同時搶 10 個核心，互相拖慢，比序列執行還慢。一次一組，或至少留意資源競爭。
