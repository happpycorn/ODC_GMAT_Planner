# 勢均力敵版對答案（全部跑完再看）

11-07 Claude 在 Mac 上找的題目。產生方法：躲方從 520 km 近圓軌道出發，安全空域高到躲方每回合都得沿速度推滿（約 5 發）；
再把追方放在「不推力也會在 t = 2,250 s（第 3 回合中段）跟名義躲方相遇」的軌道上，相遇時相對速度 150 m/s、法向。
躲方被迫走的路線正好經過追方，閃避和爬升衝突。

## 該填的值

規則檔 `day/announced.json`：`max_dv_pursuer_mps` 200、`max_dv_evader_mps` 200、`capture_radius_km` 8、`window_sec` 900、
`safe_sma_km` **[9648.137, 9678.137]**。船名 `pursuer=SC_Alpha,evader=SC_Beta`。

## 角色選擇器（完整版、4 worker、150 s 預算；實跑 80 s、200 局）

| 項目 | 值 |
|---|---|
| 初始距離 | 686.1 km |
| 追方高度／近地點 | 1,145.4 / 829.4 km |
| 躲方高度／近地點 | 512.1 / 509.7 km |
| 安全空域 | [9648.1, 9678.1] km；題目特徵：很遠（約 5.1 發）、很窄（0.083 發）、要穿過追方的 a |
| 我方追方 vs safe_evader | **47.5%** [32.9, 62.5]（capture 19、escape 21） |
| 我方躲方 vs capture_pursuer | **55.0%** [39.8, 69.3]（capture 18、escape 22） |
| 追方 vs heuristic／dv_evader | 100%／100%（heuristic 被抓或 sma_out，dv_evader 全 sma_out） |
| 躲方 vs lambert_pursuer | 100% |
| 安全證書 | 第 1 回合 100%、**第 2 回合 50%**、第 3–6 回合 100% |
| 建議 | 追方（見下面說明） |

**建議為什麼是追方**：兩個主要數字差 7.5 個百分點，不到 10 的門檻，選擇器改比「三個追方配對平均 vs 兩個躲方配對平均」；
追方那邊含 heuristic、dv_evader 兩個弱對手的 100%，所以平均較高。主要那兩格的信賴區間幾乎完全重疊，**實際上是平手**，
這題選哪邊都合理——要練的是看懂這個情況，而不是照最後一行選。

## 對打（organizer 預設對手種子 1）

我們用自己的 agent 扮選手走 organizer 測過：

| 你們 | 對手 | 結果 |
|---|---|---|
| 躲方 safe_evader 種子 0／1／2 | capture_pursuer | 被抓（R2）／**escape**／被抓（R2） |
| 追方 capture_pursuer 種子 0／1／2 | safe_evader 種子 1（預設） | 3 局都 escape（對手逃掉） |
| 追方 capture_pursuer | safe_evader 種子 0 或 2 | 都在 R2 抓到 |

- **勝負在第 2 回合定**：被抓的局都在第 2 回合開始後約 75 s，最近距離 6.1–6.4 km；逃掉的局同一時間最近 **8.626 km**，只比 R_cap 多 0.63 km。
  之後距離拉開到 64–506 km，第 6 回合推完 a 進安全空域。
- capture_pursuer 是確定性的（換種子招式不變），勝負取決於躲方在第 2 回合抽到哪個近似最優方向。
  所以你選躲方時 advise 給的數字跟上表不一樣是正常的，第 2 回合看「證書成立／margin」——不成立就代表這回合真的有被抓的風險。
- 第 1 回合 advise（躲方）會印「還差約 7.07 發……保守餘裕 -649.741 km」：保守容量用遠地點估、偏悲觀，實際在不同位置推的效率比較高，
  上面逃掉的局第 6 回合都推進了安全空域。這裡的負數不代表一定到不了；第 5、6 回合再看 `提交值推完 a = ...`。
- 你選追方時，預設的對手（種子 1）我們的工具抓不到，要贏得自己找機會；換 `--opp-seed 0` 是工具抓得到的對手。

## 這題暴露的事（給賽前參考，沒有改程式）

這是第一個 safe_evader **被抓**的題目（E28／E29 一共 1,200 局都是 escape 或 sma_out）。原因是第 2 回合在這個幾何下
「追方怎麼推都碰不到」的推力不一定存在（證書 50%），躲方只能挑命中率最低的方向賭。
條件是三個一起出現：安全空域遠到躲方得每回合推滿、追方在躲方必經路線上、相遇落在前 2–3 回合。
當天角色選擇器若出現「安全空域很遠＋要穿過追方的 a」兩個旗標、且第 2 或第 3 回合證書比例明顯低於 100%，就要當成真的五五波。

## 範例對局（11-09 Claude 照 CLI 流程打的一場）

[sample_game/](sample_game/)：選躲方、對手種子 1，**escape**。每回合 `advise` → 抄提交行 → organizer → `announce --state`，完整輸出在 `game.log`。
第 2 回合證書不成立、最近 8.612 km；第 4 回合證書又不成立、最近 11.72 km；結束 a = 9,651.025 km（下界 +2.9 km）。
路徑：`trajectory.csv`（2 s 取樣、雙方 ECI r/v、距離、a）、`trajectory.png`。自己的對局也能畫：
`.venv/bin/python ../docs/final/mock_drill_close_20261107/plot_game.py <你的 organizer_log.json> <輸出資料夾>`（在 `medal/` 跑）。
GMAT 看：`sample_game/close_game.script`（用 `gmat_replay.py` 從 organizer_log.json 產生，純二體、每 5 s 一步），GMAT GUI 打開按 Run，
有 3D 軌道、以躲方為原點的 RSW 相對運動、距離、半長軸四個視窗；報表 `close_game_report.txt` 跟引擎的追方位置最多差 0.08 m。
自己的對局：`.venv/bin/python ../docs/final/mock_drill_close_20261107/gmat_replay.py <organizer_log.json> <輸出.script>`（在 `medal/` 跑）。
