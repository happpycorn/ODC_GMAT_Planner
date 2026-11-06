# ROADMAP —— 到 2026-11-09 決賽

> **2026-11-04 註**：11-01 正式規則公布後，主線改成 [FINAL_RULES_PLAN](docs/FINAL_RULES_PLAN_20261101.md) 的 F1–F6；下面的「策略主軸」與階段 0–4 是舊賽制的紀錄。11-04 起軟凍結，只換參數、修彩排 bug、改手冊。

進度同步在 Linear 專案 `ODC_GMAT_DRL`（team Happpycorn）。實驗數字見 [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md)。

## 策略主軸
1. 規則未公告 → 兩條腿走路：**解析/推演規劃器**（不用訓練、公告即可用，保底）+ **rule-conditioned RL**（訓練時抽規則、規則放進觀測）。
2. 核心物理量是**追擊所需 Δv**；但勝負取決於很久以後的燃料消耗 → 最強大腦是**推演到終局**的 rollout 規劃器。
3. 當天真正的交付物是 **copilot**（建議脈衝 + 推演 + GMAT 驗證腳本），RL 只是其中一個大腦。

## 階段

| 階段 | 內容 | 狀態 | Linear |
|---|---|---|---|
| 0 | env 正確性修復 + 遊戲核心重構 | ✅ 09-15 | HAP-101 |
| 1 | 物理工具箱：numba Lambert、追擊所需 Δv、座標系 | ✅ 09-15 | HAP-102 |
| 2 | 解析 agent + 對打評測 + rollout 規劃器 | ✅ 09-15 | HAP-103 |
| 2.5 | GMAT 重播一致性（< 10 m） | ✅ 待官方 ForceModel | HAP-56 |
| 3 | self-play 訓練（BC → curriculum → league） | ✅ sp3 完成：持平專家、未超越（E9） | HAP-54 |
| 4 | RL × rollout 整合、決定 RL 當天角色 | ✅ 無增益 → 主腦純 rollout（E11） | HAP-105 |
| 4.1 | 規則平衡地圖 → 當天查表 | ✅ 6 張地圖 + rollout 確認（E8、E10） | HAP-106 |
| 4.2 | Exploitability 測試 | ✅ rollout 追者對稱規則 +44（賽局結構）；逃逸躲者不採用當預設（E12） | HAP-108 |
| 5 | copilot CLI + 當天手冊 | ✅ 初版 | HAP-104 / HAP-55 |
| 5.1 | copilot 狀態匯入（GMAT 報表）、推演排序 ★ 推薦、rollout 平行化 | ✅ | HAP-109 / HAP-104 |
| 5.2 | 當天流程彩排（GMAT 當真實世界跑完整 SOP） | ✅ 兩場皆勝、決策最長 ~14 s（E13） | HAP-55 |
| 6 | 規則公告 → 鎖定參數 → 演練 → 凍結 | ☐ 阻塞於 HAP-50 | HAP-50 / HAP-55 |
| — | 規則變體：一回合多發 | ✅ 引擎/copilot/GMAT 支援；多發大幅利於追者（E17） | HAP-107 |
| — | 全攝動彩排（GMAT 排位賽官方模型當真實世界） | ✅ 工具完成（E18） | HAP-55 |

## 近期待辦
- [x] sp3 → `tools/promote_model.py` → RL 當 rollout 候選/對手模型的評測（HAP-105：無增益）
- [ ] 對手風格辨識：從對手前幾回合行為挑對手模型（E11 顯示猜中對手 +9 個百分點）
- [x] 平衡地圖六張 + rollout 確認（HAP-106）
- [x] copilot `import` 讀 GMAT 報表、rollout 平行化（HAP-109）
- [x] Exploitability：rollout 大腦被針對時多弱（HAP-108）
- [x] 排位賽版規則集（250/3000 對稱）小批評測：開局逃逸翻盤成最弱、rollout 躲者最強（E14）
- [x] 排位賽版規則下用 `copilot.py drill` 確認 ★ 推薦不會選逃逸大腦（E14b：0/39 回合；但會分批往逃逸方向推）
- [x] 排位賽版規則大批評測 + exploitability（E15：rollout 躲者在這組規則下可被針對 +29）
- [x] 一回合多發（HAP-107，E17）
- [x] 全攝動 GMAT 彩排工具（E18）
- [x] 多發規則下放寬中間軌道存活檢查（E20，HAP-118）：看不出增益，預設關
- [x] 250 m/s 級規則敏感度地圖 + `tools/rule_lookup.py` 當天查表（E21，HAP-120）：窗口、T_max、多發、燃料比都能翻盤
- [x] 躲者改進：受威脅才閃的 `lazy_evader`（E22，HAP-119）→ copilot 躲者第一大腦
- [x] 雙曲線／飛掠幾何（E23，HAP-121）：引擎、copilot、匯入、GMAT 支援雙曲線；飛掠場景躲者壓倒性有利
- [x] 追者反制「受威脅才閃」的躲者（E24，HAP-122）：排位版數字下抓不到（結構性）；HarassPursuer 逼它多耗一倍油
- [x] `orbit_survives` 漏判修正（E25）：開關 `ODC_STRICT_SURVIVAL`，預設關
- [x] `ODC_STRICT_SURVIVAL` 改成預設開（2026-10-22 使用者決定；設 0 回舊行為）
- [x] copilot ★ 整體評測與決策時間預算（E26）：躲者 ★ = lazy_evader；`--prune`、`--budget-sec`、`--rank wins`；現場 `COPILOT_WORKERS=4`
- [ ] 追者 ★ 排序：`--rank wins` 大批驗證（E26 發現「全輸給某模型」時排序不可靠）
- [x] GMAT 獨立撞地閘門、太空船參數／曆元敏感度工具與整場 dry-run（[操作與紀錄](docs/notes/gmat_sensitivity.md)）
- [ ] 全攝動彩排擴大：太空船參數（Cd·A/m）／曆元掃描實跑、多幾何（工具已完成；E22 設定的 78 回合 × 15 變體 dry-run 已產生，GMAT 實測待沙盒外執行）
- [ ] 排位版規則重訓 RL（sp4，HAP-123；夜間因額度上限未開始）
- [ ] 真正的兩發規劃：rollout 候選列舉 (第一發, 第二發) 組合（E17/E20 的限制）
- [ ] 規則地圖補跑：強化版 rollout 追者各格、`RankingRuleRanges` 分布平均（E21 未跑）
- [ ] 規則公告後：在正式規則上重跑 E7/E11/E12 的關鍵對打（大腦選擇可能隨規則翻轉，例如逃逸躲者）
- [ ] 規則公告（HAP-50）→ `configs/rules_final.json` → 重跑評測/平衡 → 微調 RL → 凍結 `models/`
