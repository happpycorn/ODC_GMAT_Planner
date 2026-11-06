# 決賽評測分桶報表

來源：reports/f24_ranges.jsonl

共 720 局、6 個配對。

## 配對總覽

| 追方 | 躲方 | 局數 | 躲方勝率 | Wilson 95% 區間 | 結局分布 |
|---|---|---:|---:|---:|---|
| capture_pursuer | dv_evader | 120 | 2% (2/120) | 0.5–5.9% | capture: 103、escape: 2、sma_out: 15 |
| capture_pursuer | heuristic_evader | 120 | 56% (67/120) | 46.9–64.4% | capture: 34、escape: 67、sma_out: 19 |
| capture_pursuer | safe_evader | 120 | 100% (120/120) | 96.9–100.0% | escape: 120 |
| lambert_pursuer | dv_evader | 120 | 0% (0/120) | -0.0–3.1% | capture: 97、sma_out: 23 |
| lambert_pursuer | heuristic_evader | 120 | 70% (84/120) | 61.3–77.5% | capture: 4、escape: 84、sma_out: 32 |
| lambert_pursuer | safe_evader | 120 | 100% (120/120) | 96.9–100.0% | escape: 120 |

## 躲方勝率分桶

τ* = 1000 × R_cap（km）/ ΔV_lim（m/s）；初始距離比例 = 1000 × 初始距離（km） / [ΔV_lim（m/s）× T_round（秒）]。每桶顯示勝率（勝局數/局數）。

### ΔV_lim（m/s）

| 追方 | 躲方 | 100–200 | 200–350 | 350–500 |
|---|---|---|---|---|
| capture_pursuer | dv_evader | 0% (0/52) | 2% (1/43) | 4% (1/25) |
| capture_pursuer | heuristic_evader | 54% (28/52) | 63% (27/43) | 48% (12/25) |
| capture_pursuer | safe_evader | 100% (52/52) | 100% (43/43) | 100% (25/25) |
| lambert_pursuer | dv_evader | 0% (0/52) | 0% (0/43) | 0% (0/25) |
| lambert_pursuer | heuristic_evader | 69% (36/52) | 72% (31/43) | 68% (17/25) |
| lambert_pursuer | safe_evader | 100% (52/52) | 100% (43/43) | 100% (25/25) |

### R_cap（km）

| 追方 | 躲方 | 1–3 | 3–8 | 8–20 |
|---|---|---|---|---|
| capture_pursuer | dv_evader | 0% (0/51) | 6% (2/31) | 0% (0/38) |
| capture_pursuer | heuristic_evader | 67% (34/51) | 45% (14/31) | 50% (19/38) |
| capture_pursuer | safe_evader | 100% (51/51) | 100% (31/31) | 100% (38/38) |
| lambert_pursuer | dv_evader | 0% (0/51) | 0% (0/31) | 0% (0/38) |
| lambert_pursuer | heuristic_evader | 78% (40/51) | 68% (21/31) | 61% (23/38) |
| lambert_pursuer | safe_evader | 100% (51/51) | 100% (31/31) | 100% (38/38) |

### T_round（秒）

| 追方 | 躲方 | 600–1200 | 1200–2400 | 2400–3600 |
|---|---|---|---|---|
| capture_pursuer | dv_evader | 5% (2/44) | 0% (0/49) | 0% (0/27) |
| capture_pursuer | heuristic_evader | 48% (21/44) | 63% (31/49) | 56% (15/27) |
| capture_pursuer | safe_evader | 100% (44/44) | 100% (49/49) | 100% (27/27) |
| lambert_pursuer | dv_evader | 0% (0/44) | 0% (0/49) | 0% (0/27) |
| lambert_pursuer | heuristic_evader | 66% (29/44) | 73% (36/49) | 70% (19/27) |
| lambert_pursuer | safe_evader | 100% (44/44) | 100% (49/49) | 100% (27/27) |

### τ* = R_cap/ΔV_lim（秒）

| 追方 | 躲方 | 0–10 | 10–30 | 30 以上 |
|---|---|---|---|---|
| capture_pursuer | dv_evader | 2% (1/43) | 3% (1/36) | 0% (0/41) |
| capture_pursuer | heuristic_evader | 65% (28/43) | 56% (20/36) | 46% (19/41) |
| capture_pursuer | safe_evader | 100% (43/43) | 100% (36/36) | 100% (41/41) |
| lambert_pursuer | dv_evader | 0% (0/43) | 0% (0/36) | 0% (0/41) |
| lambert_pursuer | heuristic_evader | 77% (33/43) | 72% (26/36) | 61% (25/41) |
| lambert_pursuer | safe_evader | 100% (43/43) | 100% (36/36) | 100% (41/41) |

### 初始距離比例：初始距離 / (ΔV_lim·T_round)

| 追方 | 躲方 | 0–0.5 | 0.5–2 | 2 以上 |
|---|---|---|---|---|
| capture_pursuer | dv_evader | 0% (0/19) | 3% (2/69) | 0% (0/32) |
| capture_pursuer | heuristic_evader | 58% (11/19) | 54% (37/69) | 59% (19/32) |
| capture_pursuer | safe_evader | 100% (19/19) | 100% (69/69) | 100% (32/32) |
| lambert_pursuer | dv_evader | 0% (0/19) | 0% (0/69) | 0% (0/32) |
| lambert_pursuer | heuristic_evader | 68% (13/19) | 72% (50/69) | 66% (21/32) |
| lambert_pursuer | safe_evader | 100% (19/19) | 100% (69/69) | 100% (32/32) |

### 安全空域偏移：|區間中心 − 初始 a| / 一發容量

| 追方 | 躲方 | 0（在區間內） | 0–2 | 2–4 |
|---|---|---|---|---|
| capture_pursuer | dv_evader | 13% (2/15) | 0% (0/30) | 0% (0/75) |
| capture_pursuer | heuristic_evader | 47% (7/15) | 67% (20/30) | 53% (40/75) |
| capture_pursuer | safe_evader | 100% (15/15) | 100% (30/30) | 100% (75/75) |
| lambert_pursuer | dv_evader | 0% (0/15) | 0% (0/30) | 0% (0/75) |
| lambert_pursuer | heuristic_evader | 53% (8/15) | 87% (26/30) | 67% (50/75) |
| lambert_pursuer | safe_evader | 100% (15/15) | 100% (30/30) | 100% (75/75) |

## 安全證書成立比例

有 1440 個躲方決策回合含 certificate 紀錄。

### 依回合

| 追方 | 躲方 | 第 1 回合 | 第 2 回合 | 第 3 回合 | 第 4 回合 | 第 5 回合 | 第 6 回合 |
|---|---|---|---|---|---|---|---|
| capture_pursuer | dv_evader | — | — | — | — | — | — |
| capture_pursuer | heuristic_evader | — | — | — | — | — | — |
| capture_pursuer | safe_evader | 99% (119/120) | 100% (120/120) | 100% (120/120) | 100% (120/120) | 100% (120/120) | 99% (119/120) |
| lambert_pursuer | dv_evader | — | — | — | — | — | — |
| lambert_pursuer | heuristic_evader | — | — | — | — | — | — |
| lambert_pursuer | safe_evader | 99% (119/120) | 100% (120/120) | 100% (120/120) | 100% (120/120) | 100% (120/120) | 100% (120/120) |

### 依規則與題目分桶

#### ΔV_lim（m/s）

| 追方 | 躲方 | 100–200 | 200–350 | 350–500 |
|---|---|---|---|---|
| capture_pursuer | dv_evader | — | — | — |
| capture_pursuer | heuristic_evader | — | — | — |
| capture_pursuer | safe_evader | 100% (311/312) | 100% (257/258) | 100% (150/150) |
| lambert_pursuer | dv_evader | — | — | — |
| lambert_pursuer | heuristic_evader | — | — | — |
| lambert_pursuer | safe_evader | 100% (311/312) | 100% (258/258) | 100% (150/150) |

#### R_cap（km）

| 追方 | 躲方 | 1–3 | 3–8 | 8–20 |
|---|---|---|---|---|
| capture_pursuer | dv_evader | — | — | — |
| capture_pursuer | heuristic_evader | — | — | — |
| capture_pursuer | safe_evader | 100% (306/306) | 99% (185/186) | 100% (227/228) |
| lambert_pursuer | dv_evader | — | — | — |
| lambert_pursuer | heuristic_evader | — | — | — |
| lambert_pursuer | safe_evader | 100% (306/306) | 100% (186/186) | 100% (227/228) |

#### T_round（秒）

| 追方 | 躲方 | 600–1200 | 1200–2400 | 2400–3600 |
|---|---|---|---|---|
| capture_pursuer | dv_evader | — | — | — |
| capture_pursuer | heuristic_evader | — | — | — |
| capture_pursuer | safe_evader | 100% (263/264) | 100% (294/294) | 99% (161/162) |
| lambert_pursuer | dv_evader | — | — | — |
| lambert_pursuer | heuristic_evader | — | — | — |
| lambert_pursuer | safe_evader | 100% (263/264) | 100% (294/294) | 100% (162/162) |

#### τ* = R_cap/ΔV_lim（秒）

| 追方 | 躲方 | 0–10 | 10–30 | 30 以上 |
|---|---|---|---|---|
| capture_pursuer | dv_evader | — | — | — |
| capture_pursuer | heuristic_evader | — | — | — |
| capture_pursuer | safe_evader | 100% (258/258) | 100% (215/216) | 100% (245/246) |
| lambert_pursuer | dv_evader | — | — | — |
| lambert_pursuer | heuristic_evader | — | — | — |
| lambert_pursuer | safe_evader | 100% (258/258) | 100% (216/216) | 100% (245/246) |

#### 初始距離比例：初始距離 / (ΔV_lim·T_round)

| 追方 | 躲方 | 0–0.5 | 0.5–2 | 2 以上 |
|---|---|---|---|---|
| capture_pursuer | dv_evader | — | — | — |
| capture_pursuer | heuristic_evader | — | — | — |
| capture_pursuer | safe_evader | 99% (113/114) | 100% (413/414) | 100% (192/192) |
| lambert_pursuer | dv_evader | — | — | — |
| lambert_pursuer | heuristic_evader | — | — | — |
| lambert_pursuer | safe_evader | 99% (113/114) | 100% (414/414) | 100% (192/192) |

#### 安全空域偏移：|區間中心 − 初始 a| / 一發容量

| 追方 | 躲方 | 0（在區間內） | 0–2 | 2–4 |
|---|---|---|---|---|
| capture_pursuer | dv_evader | — | — | — |
| capture_pursuer | heuristic_evader | — | — | — |
| capture_pursuer | safe_evader | 99% (89/90) | 99% (179/180) | 100% (450/450) |
| lambert_pursuer | dv_evader | — | — | — |
| lambert_pursuer | heuristic_evader | — | — | — |
| lambert_pursuer | safe_evader | 100% (90/90) | 99% (179/180) | 100% (450/450) |

證書成立的回合被捕獲：0 次。

## 追方命中機率校準

平均 hit_prob 與實際捕獲率均以有 hit_prob 的決策回合為分母；實際捕獲指該回合結束時 outcome 為 capture。

| 追方 | 躲方 | 決策回合 | 平均 hit_prob | 實際捕獲率 |
|---|---|---:|---:|---:|
| capture_pursuer | dv_evader | 316 | 17.4% | 33% (103/316) |
| capture_pursuer | heuristic_evader | 603 | 4.6% | 6% (34/603) |
| capture_pursuer | safe_evader | 720 | 3.1% | 0% (0/720) |
