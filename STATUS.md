# 專案狀態筆記（交接用）

給下一個 session（不管是我自己回來還是你自己看）快速抓回上下文用的，這份主要是「現在做到哪、還缺什麼、為什麼」的整理。**怎麼用這個工具看 [README.md](README.md)；演算法/物理模型原理看 [METHODOLOGY.md](METHODOLOGY.md)**；更細節的技術決策看 commit log 跟程式碼註解。

最後更新：2026-08-15（白天，在**另一台機器**上——見下面「換機器」那段）。
`improve-optimizer-and-gmat-integration` 跟 `overnight-generalization` 兩個分支
都已經 merge 回 `Master` 並刪除——**現在直接在 `Master` 上開發**。

8/14 那一整天以及 8/15 凌晨夜間開發的所有改動都已經 commit 且 push 完畢
（`cf8c316` 為止）。8/15 白天新增 `829afac`（GMAT R2026a 顏色欄位棄用修正）、
`7216d47`（多棒種子正式預算驗證 + 兩組新極限測資設計），也已經 commit。

### ⚠️ 換機器了：現在是 WSL / Ryzen 5800X，不是 MacBook Air

8/15 白天起改在 **WSL2 (Ubuntu 24.04) + Ryzen 5800X (16 threads)** 上開發，
不是先前那台會熱降頻的 MacBook Air。這份文件前面幾節提到「MacBook Air 熱降頻」
的效能討論（`sweep_burns.py` 那節、「還沒做」清單第 11/12 項）**要用這個前提
重讀**——那些「先不做，因為在會降頻的機器上不保證是淨賺」的判斷，在這台有塔扇
散熱的桌機上結論可能不一樣，值得重新評估。

這台機器的環境設定（都是機器本地、不進 git）：
- GMAT R2026a 裝在 `/home/corn/software/GMAT/GMAT/R2026a`，路徑寫在各個
  `configs/*.json` 的 `local.gmat_console_path`，不用每次帶 `--gmat-console`。
- **GMAT GUI 可以在 WSLg 上跑**，但需要兩個修補，包成
  `~/software/gmat-gui.sh` 啟動器：(a) `libtiff.so.5` 在 Ubuntu 24.04 已經沒有了，
  從 jammy 抓一份放在 `~/software/gmat-compat-libs/`，只用 `LD_LIBRARY_PATH`
  掛給 GMAT，不動系統的 libtiff6；(b) OSG 的格式外掛 (`osgdb_jpeg.so` 等) 是
  `dlopen` 進來的，而 `RUNPATH` 不會傳遞給 dlopen 的模組，所以 GMAT 的 `lib/`
  也必須進 `LD_LIBRARY_PATH`，否則貼圖/模型/字型全部載入失敗。另外 `arial.ttf`
  這類微軟字型 Linux 沒有，用 `~/software/gmat-compat-fonts/` 裡指向 DejaVu 的
  符號連結 + `OSG_FILE_PATH` 補上。`libsm6`/`libpcre2-32-0` 等系統套件要 apt 裝。
- `configs/` 整個被 gitignore，換機器不會自動帶過來，要自己重建。

**⚠️ `practice_scenario.json` 在這台機器上不存在**。這份文件底下有十幾處寫「用
`practice_scenario.json` 跑一次回歸測試確認沒壞」——那是 8/13~8/14 在 Mac 上的
標準做法，但這個檔案沒有進 git，**WSL 這台沒有**，照著做會直接失敗。這台目前有的
configs：`config.json`、`weird_test.json`、`smoke_test.json`（快速煙霧測試，同平面
圓軌道、單棒、30 代，約 15 秒含 GMAT 驗證）、`apoapsis_planechange_test.json`、
`perigee_kick_test.json`。**要做「一般規模」的回歸測試，用 `smoke_test.json` 代替**，
或是重建一份 practice_scenario（原始參數沒有完整記錄下來，這也是下面第 16 項那個
教訓的另一個實例）。

**最新一輪 (2026-08-15 白天) 做的事**，細節見「2026-08-15 白天」那一節：
- 正式預算重跑夜間的多棒 A/B 表 → 種子機制確認有效且證據更強，但「棒數越多分數
  越好」被推翻（多棒解全是 Δv=0 的退化單棒）
- 設計兩組新極限測資：`apoapsis_planechange_test.json`（否定結果，而且否定了設計
  前提本身）、`perigee_kick_test.json`（**單棒數學上不可能**，多棒在這組確實找出
  真實的兩棒合法解，結論反轉）
- **統一結論：多棒退化成單棒是正確行為，不是缺陷**——單棒夠用時退化，單棒不可能
  時就會找出真多棒解
- 修 GMAT R2026a 顏色欄位棄用警告（會影響繳交檔案）`829afac`
- 換機器到 WSL / 5800X，含 GMAT GUI 在 WSLg 上跑起來的一整套修補

**傍晚到晚上追加**，細節見「傳播器容忍度太鬆」那一節：
- 🔴 **傳播器容忍度太鬆，高離心率軌道會安靜地算錯**（使用者實測 Python 3.5km /
  GMAT 88km）→ 收緊到 `rtol=1e-12, atol=1e-9`，落差降到 0.154m
- 階梯種子在 `num_burns=2` 時產生 0 個 → 修好後該情境 67.86 → 77.76 分、違規歸零
- **正式預算 A/B 表整組重跑**：種子優勢維持 +14.45 分，但舊表裡「棒數之間差 2 分」
  被證實**整個是積分誤差**——三個有種子案例現在收斂到同一個數字
- GMAT 3D 視角兩個相機距離都改成依情境縮放 `27597dd`
- `METHODOLOGY.md` 補上 DOP853 / zonal harmonics / 種子機制的設計理由 `1feaa2b`

---

**8/13~8/14 那個 session 做的事，由前到後**（各自的細節都在下面對應章節，這裡只列
索引方便快速定位）：
1. 排位賽雙曲線軌道輸入端準備 (`config_validator.py` 放寬 SMA/ECC、`rules.T_MAX_SEC`
   覆寫) → 見「排位賽輸入端準備」
2. `strategy.USE_J2` 換成 `strategy.GRAVITY_DEGREE` (0/2/3/4)，Python 力學引擎補上
   J3/J4 → 見「重力場模型可設定」
3. 傳播器三部曲：固定 RK4 → RK45 自適應 → **DOP853 (目前主線)**，中途評估過 Encke's
   method (驗證正確但比較慢，沒有換上) → 見「傳播器：RK45...」「DOP853」兩節
4. GMAT script 新增太空船 B 追蹤視角，過程中意外抓到一個 `run_gmat_verification()`
   會誤讀殘留舊報表檔的真 bug，已修 → 見「太空船 B 追蹤視角」
5. 系統性掃描 SMA/ECC/雙曲線找出工具的可信邊界：**SMA 不是問題，ECC>0.95 才是**
   → 見「系統性測試軌道參數極限」
6. 追加：進度條的粒度問題 (使用者發現，同一天稍晚已修，見下面「還沒做」清單第 9 項)
7. 追加：`sweep_burns.py` 粗掃階段依維度公平分配世代預算 + 加時間上限，過程中
   發現 MacBook Air 熱降頻讓「順便修 n_workers」這個念頭不再是穩賺 → 見
   「sweep_burns.py 粗掃階段依維度公平分配世代預算」一節
8. 追加：`weird_test.json` 深度診斷——單棒死局分析、拆分燃燒陷阱、多棒長程解重演
   模型分岔問題、k_t/C_t 實驗、最後找到一個藏在 0.0086% 窄窗口裡的合法單棒解
   (1189.73 m/s，L-SHADE 2000 代都找不到) → 見「weird_test.json 深度診斷」一節；
   順便修了 `View_ShipBChase` 鏡頭跑進地球裡面的 bug → 同一節提到

**上一次 (8/13) 最重要的發現，這次 session 已經拆解出根因，見下面「拆解 GMAT 對不上的
真正原因」那一節**：「極端軌道」(SMA ~80,000km、ECC ~0.87) 上 Python 預測跟 GMAT 實測
差到四五個數量級、GMAT 求解器收斂不了——原本猜的三層原因中，第三層 (長時間傳播下的
模型落差) 這次 session 後段又有新進展 (J3/J4 補上去 + 意外發現固定步長比原本以為的
影響更大)，細節見下面新增的兩節，「還沒做」清單第 1/3 項已經照最新理解更新。

## 這是什麼

TASA/淡江大學辦的「第一屆軌道設計競賽」初賽用的任務規劃工具。太空船 B（我方）要在時間/燃料限制下攔截太空船 A（被動、只受重力）。`rules/` 資料夾裡有三份官方文件（正式規則 PDF ×2、0510 線上說明會簡報）。

規則重點：Δv ≤ 1500 m/s/次、機動間隔 ≥100s、T_max=4×A的軌道週期、**Δr ≤ 5km 即算成功且以內都是同分**（這點很關鍵，見下）、繳交格式是「Script + 至少模擬一次產生的 Report」上傳。初賽 A 是圓軌道；後面的排位賽/四強賽是完全不同玩法（A 變雙曲線／即時追逐戰），還沒開始準備。

**時程**（2026-08-13 查證，來源：官方簡報 + 淡江航太系官網 + 報名表單本身）：線上報名 5/11~**8/21 週五下午5點截止**（查證當下還沒截止，剩沒幾天，記得確認團隊真的報名了）；GMAT 實體訓練 6/27（已過）；**初賽原訂 8/29，因沙德爾颱風官方於 2026-08-25 來信延後一週，改為 9/5（六）**，淡江大學淡水校園（時間地點官方說近日另行寄發，要再確認）；決賽 11/09，大臺南會展中心。官方目前完全沒公布任何測試用的軌道數字或範例——`k_t/C_t/k_v/C_v` 跟 A/B 六根數都要等「題目 Script」發布才知道，詳細計分/繳交規則也還沒完整公告，要持續關注 TASA 官網。

## 開發日誌（已封存）

8/13～8/15 那幾個 session 的逐日技術記錄（原本佔了這份 2000+ 行的絕大部分）
已搬到 [docs/log/DEVLOG_prelim.md](docs/log/DEVLOG_prelim.md)，讓這份回到「當前
狀態／交接」的本份。完整逐版歷史仍在 git log。
