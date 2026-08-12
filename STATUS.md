# 專案狀態筆記（交接用）

給下一個 session（不管是我自己回來還是你自己看）快速抓回上下文用的。技術細節看 commit log 跟程式碼註解，這份主要是「現在做到哪、還缺什麼、為什麼」的整理。

最後更新：2026-08-12，分支 `improve-optimizer-and-gmat-integration`（還沒 merge 回 `Master`，也還沒 push）。

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

## 還沒做 / 值得考慮的

優先順序由高到低：

1. **正式測資公布後，`configs/config.json` 整組要換成官方數字**（軌道六根數 + `k_t/C_t/k_v/C_v`）。現在的數字除了 `orbit_A.ECC=0` 是照簡報修正過的，其他都是我們自己編的，不能直接拿去用。
2. **多圈 Lambert (M>0) 沒探索**，只有 `M=0`。大 SMA 落差的情境可能有機會受益，但還沒驗證過投報比。
3. **固定 60 秒 RK4 步長**：查證過對 LEO 型軌道有 ~108m 的積分誤差（慢軌道幾乎沒差），但因為安全邊界（1.5km）遠大於目前觀察到的最大落差（~900m），評估後決定先不動——如果拿到正式測資後發現落差逼近安全邊界，再回頭考慮自適應步長。
4. **`configs/config.json` 沒有欄位驗證**，打錯字/填不合理值不會有清楚錯誤訊息，會一路跑到某個奇怪的地方才炸。
5. **物理直覺的初始種子** 沒做（讓 L-SHADE 從一個粗略 Hohmann-like 猜測開始，而不是純隨機初始化）——早期評估過投入產出比不確定，沒有動手。
6. **GMAT script 裡 `Isp`/`DryMass` 等還是裝飾用的寫死數字**（因為 `DecrementMass=false` 完全不影響結果），純粹美觀，不影響正確性。
7. 排位賽（A 變雙曲線軌道）、四強賽（即時追逐戰）**完全還沒碰**，等晉級再說。

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
