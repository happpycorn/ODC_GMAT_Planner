# 決賽評測分桶報表

來源：reports/f29v3_adv_close.jsonl、reports/f29v3_adv_cover.jsonl、reports/f29v3_adv_cross.jsonl、reports/f29v3_adv_far.jsonl、reports/f29v3_adv_narrow.jsonl、reports/f29v3_adv_taiwan.jsonl、reports/f29v3s1_adv_close.jsonl、reports/f29v3s1_adv_cover.jsonl、reports/f29v3s1_adv_cross.jsonl、reports/f29v3s1_adv_far.jsonl、reports/f29v3s1_adv_narrow.jsonl、reports/f29v3s1_adv_taiwan.jsonl

共 1440 局、4 個配對。

## 配對總覽

| 追方 | 躲方 | 局數 | 躲方勝率 | Wilson 95% 區間 | 結局分布 |
|---|---|---:|---:|---:|---|
| capture_pursuer | heuristic_evader | 240 | 54% (129/240) | 47.4–59.9% | capture: 53、escape: 129、sma_out: 58 |
| capture_pursuer | safe_evader | 480 | 100% (480/480) | 99.2–100.0% | escape: 480 |
| lambert_pursuer | heuristic_evader | 240 | 65% (156/240) | 58.8–70.8% | capture: 14、escape: 156、sma_out: 70 |
| lambert_pursuer | safe_evader | 480 | 100% (480/480) | 99.2–100.0% | escape: 480 |

## 躲方勝率分桶

τ* = 1000 × R_cap（km）/ ΔV_lim（m/s）；初始距離比例 = 1000 × 初始距離（km） / [ΔV_lim（m/s）× T_round（秒）]。每桶顯示勝率（勝局數/局數）。

### ΔV_lim（m/s）

| 追方 | 躲方 | 100–200 | 200–350 | 350–500 |
|---|---|---|---|---|
| capture_pursuer | heuristic_evader | 53% (54/102) | 54% (52/96) | 55% (23/42) |
| capture_pursuer | safe_evader | 100% (192/192) | 100% (204/204) | 100% (84/84) |
| lambert_pursuer | heuristic_evader | 63% (64/102) | 69% (66/96) | 62% (26/42) |
| lambert_pursuer | safe_evader | 100% (192/192) | 100% (204/204) | 100% (84/84) |

### R_cap（km）

| 追方 | 躲方 | 1–3 | 3–8 | 8–20 |
|---|---|---|---|---|
| capture_pursuer | heuristic_evader | 55% (59/108) | 54% (39/72) | 52% (31/60) |
| capture_pursuer | safe_evader | 100% (174/174) | 100% (180/180) | 100% (126/126) |
| lambert_pursuer | heuristic_evader | 72% (78/108) | 57% (41/72) | 62% (37/60) |
| lambert_pursuer | safe_evader | 100% (174/174) | 100% (180/180) | 100% (126/126) |

### T_round（秒）

| 追方 | 躲方 | 600–1200 | 1200–2400 | 2400–3600 |
|---|---|---|---|---|
| capture_pursuer | heuristic_evader | 55% (56/102) | 53% (51/96) | 52% (22/42) |
| capture_pursuer | safe_evader | 100% (186/186) | 100% (210/210) | 100% (84/84) |
| lambert_pursuer | heuristic_evader | 62% (63/102) | 65% (62/96) | 74% (31/42) |
| lambert_pursuer | safe_evader | 100% (186/186) | 100% (210/210) | 100% (84/84) |

### τ* = R_cap/ΔV_lim（秒）

| 追方 | 躲方 | 0–10 | 10–30 | 30 以上 |
|---|---|---|---|---|
| capture_pursuer | heuristic_evader | 52% (44/84) | 54% (42/78) | 55% (43/78) |
| capture_pursuer | safe_evader | 100% (138/138) | 100% (168/168) | 100% (174/174) |
| lambert_pursuer | heuristic_evader | 70% (59/84) | 63% (49/78) | 62% (48/78) |
| lambert_pursuer | safe_evader | 100% (138/138) | 100% (168/168) | 100% (174/174) |

### 初始距離比例：初始距離 / (ΔV_lim·T_round)

| 追方 | 躲方 | 0–0.5 | 0.5–2 | 2 以上 |
|---|---|---|---|---|
| capture_pursuer | heuristic_evader | 32% (13/41) | 56% (23/41) | 59% (93/158) |
| capture_pursuer | safe_evader | 100% (82/82) | 100% (100/100) | 100% (298/298) |
| lambert_pursuer | heuristic_evader | 63% (26/41) | 66% (27/41) | 65% (103/158) |
| lambert_pursuer | safe_evader | 100% (82/82) | 100% (100/100) | 100% (298/298) |

### 安全空域偏移：|區間中心 − 初始 a| / 一發容量

| 追方 | 躲方 | 0（在區間內） | 0–2 | 2–4 | 4 以上 |
|---|---|---|---|---|---|
| capture_pursuer | heuristic_evader | 37% (16/43) | 65% (55/85) | 52% (29/56) | 52% (29/56) |
| capture_pursuer | safe_evader | 100% (90/90) | 100% (183/183) | 100% (102/102) | 100% (105/105) |
| lambert_pursuer | heuristic_evader | 58% (25/43) | 71% (60/85) | 71% (40/56) | 55% (31/56) |
| lambert_pursuer | safe_evader | 100% (90/90) | 100% (183/183) | 100% (102/102) | 100% (105/105) |

## 安全證書成立比例

有 5760 個躲方決策回合含 certificate 紀錄。

### 依回合

| 追方 | 躲方 | 第 1 回合 | 第 2 回合 | 第 3 回合 | 第 4 回合 | 第 5 回合 | 第 6 回合 |
|---|---|---|---|---|---|---|---|
| capture_pursuer | heuristic_evader | — | — | — | — | — | — |
| capture_pursuer | safe_evader | 99% (475/480) | 100% (480/480) | 100% (479/480) | 100% (479/480) | 100% (480/480) | 100% (479/480) |
| lambert_pursuer | heuristic_evader | — | — | — | — | — | — |
| lambert_pursuer | safe_evader | 99% (475/480) | 100% (480/480) | 100% (480/480) | 100% (480/480) | 100% (478/480) | 99% (476/480) |

### 依規則與題目分桶

#### ΔV_lim（m/s）

| 追方 | 躲方 | 100–200 | 200–350 | 350–500 |
|---|---|---|---|---|
| capture_pursuer | heuristic_evader | — | — | — |
| capture_pursuer | safe_evader | 100% (1148/1152) | 100% (1221/1224) | 100% (503/504) |
| lambert_pursuer | heuristic_evader | — | — | — |
| lambert_pursuer | safe_evader | 99% (1146/1152) | 100% (1219/1224) | 100% (504/504) |

#### R_cap（km）

| 追方 | 躲方 | 1–3 | 3–8 | 8–20 |
|---|---|---|---|---|
| capture_pursuer | heuristic_evader | — | — | — |
| capture_pursuer | safe_evader | 100% (1044/1044) | 100% (1078/1080) | 99% (750/756) |
| lambert_pursuer | heuristic_evader | — | — | — |
| lambert_pursuer | safe_evader | 100% (1043/1044) | 100% (1076/1080) | 99% (750/756) |

#### T_round（秒）

| 追方 | 躲方 | 600–1200 | 1200–2400 | 2400–3600 |
|---|---|---|---|---|
| capture_pursuer | heuristic_evader | — | — | — |
| capture_pursuer | safe_evader | 100% (1115/1116) | 100% (1257/1260) | 99% (500/504) |
| lambert_pursuer | heuristic_evader | — | — | — |
| lambert_pursuer | safe_evader | 100% (1115/1116) | 99% (1253/1260) | 99% (501/504) |

#### τ* = R_cap/ΔV_lim（秒）

| 追方 | 躲方 | 0–10 | 10–30 | 30 以上 |
|---|---|---|---|---|
| capture_pursuer | heuristic_evader | — | — | — |
| capture_pursuer | safe_evader | 100% (828/828) | 100% (1007/1008) | 99% (1037/1044) |
| lambert_pursuer | heuristic_evader | — | — | — |
| lambert_pursuer | safe_evader | 100% (828/828) | 100% (1006/1008) | 99% (1035/1044) |

#### 初始距離比例：初始距離 / (ΔV_lim·T_round)

| 追方 | 躲方 | 0–0.5 | 0.5–2 | 2 以上 |
|---|---|---|---|---|
| capture_pursuer | heuristic_evader | — | — | — |
| capture_pursuer | safe_evader | 99% (485/492) | 100% (600/600) | 100% (1787/1788) |
| lambert_pursuer | heuristic_evader | — | — | — |
| lambert_pursuer | safe_evader | 99% (486/492) | 100% (600/600) | 100% (1783/1788) |

#### 安全空域偏移：|區間中心 − 初始 a| / 一發容量

| 追方 | 躲方 | 0（在區間內） | 0–2 | 2–4 | 4 以上 |
|---|---|---|---|---|---|
| capture_pursuer | heuristic_evader | — | — | — | — |
| capture_pursuer | safe_evader | 99% (534/540) | 100% (1096/1098) | 100% (612/612) | 100% (630/630) |
| lambert_pursuer | heuristic_evader | — | — | — | — |
| lambert_pursuer | safe_evader | 99% (535/540) | 100% (1094/1098) | 100% (610/612) | 100% (630/630) |

證書成立的回合被捕獲：0 次。

## 追方命中機率校準

平均 hit_prob 與實際捕獲率均以有 hit_prob 的決策回合為分母；實際捕獲指該回合結束時 outcome 為 capture。

| 追方 | 躲方 | 決策回合 | 平均 hit_prob | 實際捕獲率 |
|---|---|---:|---:|---:|
| capture_pursuer | heuristic_evader | 1278 | 3.5% | 4% (53/1278) |
| capture_pursuer | safe_evader | 2880 | 2.6% | 0% (0/2880) |

## 對抗題目分桶

有 1440 局含 scenario_meta。每格依序顯示躲方勝率 / 安全證書成立比例；勝率以局數、證書以有紀錄的躲方決策回合數為分母。

### family（題目家族）

| 追方 | 躲方 | final_adv_close | final_adv_cover | final_adv_cross | final_adv_far | final_adv_narrow | final_adv_taiwan |
|---|---|---|---|---|---|---|---|
| capture_pursuer | heuristic_evader | 38% (15/40) / — | 62% (25/40) / — | 60% (24/40) / — | 45% (18/40) / — | 48% (19/40) / — | 70% (28/40) / — |
| capture_pursuer | safe_evader | 100% (80/80) / 99% (473/480) | 100% (80/80) / 100% (479/480) | 100% (80/80) / 100% (480/480) | 100% (80/80) / 100% (480/480) | 100% (80/80) / 100% (480/480) | 100% (80/80) / 100% (480/480) |
| lambert_pursuer | heuristic_evader | 62% (25/40) / — | 68% (27/40) / — | 78% (31/40) / — | 50% (20/40) / — | 68% (27/40) / — | 65% (26/40) / — |
| lambert_pursuer | safe_evader | 100% (80/80) / 99% (474/480) | 100% (80/80) / 100% (480/480) | 100% (80/80) / 100% (479/480) | 100% (80/80) / 100% (480/480) | 100% (80/80) / 99% (476/480) | 100% (80/80) / 100% (480/480) |

### sub（題目子類）

| 追方 | 躲方 | close_frac | close_km | cover | cross | far | narrow | w002 | w05_10 | 缺資料 |
|---|---|---|---|---|---|---|---|---|---|---|
| capture_pursuer | heuristic_evader | 27% (6/22) / — | 50% (9/18) / — | 20% (1/5) / — | 90% (9/10) / — | 69% (11/16) / — | 78% (7/9) / — | 47% (8/17) / — | 48% (11/23) / — | 56% (67/120) / — |
| capture_pursuer | safe_evader | 100% (45/45) / 99% (267/270) | 100% (35/35) / 98% (206/210) | 100% (17/17) / 100% (102/102) | 100% (25/25) / 100% (150/150) | 100% (25/25) / 100% (150/150) | 100% (13/13) / 100% (78/78) | 100% (34/34) / 100% (204/204) | 100% (46/46) / 100% (276/276) | 100% (240/240) / 100% (1439/1440) |
| lambert_pursuer | heuristic_evader | 82% (18/22) / — | 39% (7/18) / — | 20% (1/5) / — | 70% (7/10) / — | 69% (11/16) / — | 78% (7/9) / — | 59% (10/17) / — | 74% (17/23) / — | 65% (78/120) / — |
| lambert_pursuer | safe_evader | 100% (45/45) / 99% (268/270) | 100% (35/35) / 98% (206/210) | 100% (17/17) / 100% (102/102) | 100% (25/25) / 100% (150/150) | 100% (25/25) / 100% (150/150) | 100% (13/13) / 100% (78/78) | 100% (34/34) / 100% (203/204) | 100% (46/46) / 99% (273/276) | 100% (240/240) / 100% (1439/1440) |

### zone_width_da（安全空域寬 / 一發容量）

| 追方 | 躲方 | <0.05 | 0.05–0.1 | 0.1–0.3 | ≥0.3 |
|---|---|---|---|---|---|
| capture_pursuer | heuristic_evader | 47% (8/17) / — | 56% (18/32) / — | — | 54% (103/191) / — |
| capture_pursuer | safe_evader | 100% (34/34) / 100% (204/204) | 100% (59/59) / 100% (354/354) | — | 100% (387/387) / 100% (2314/2322) |
| lambert_pursuer | heuristic_evader | 59% (10/17) / — | 75% (24/32) / — | — | 64% (122/191) / — |
| lambert_pursuer | safe_evader | 100% (34/34) / 100% (203/204) | 100% (59/59) / 99% (351/354) | — | 100% (387/387) / 100% (2315/2322) |

### |zone_offset_da|（中心相對躲方初始 a / 一發容量）

| 追方 | 躲方 | 0–1 | 1–2 | 2–4 | ≥4 |
|---|---|---|---|---|---|
| capture_pursuer | heuristic_evader | 45% (25/56) / — | 64% (46/72) / — | 52% (29/56) / — | 52% (29/56) / — |
| capture_pursuer | safe_evader | 100% (120/120) / 99% (713/720) | 100% (153/153) / 100% (917/918) | 100% (102/102) / 100% (612/612) | 100% (105/105) / 100% (630/630) |
| lambert_pursuer | heuristic_evader | 59% (33/56) / — | 72% (52/72) / — | 71% (40/56) / — | 55% (31/56) / — |
| lambert_pursuer | safe_evader | 100% (120/120) / 99% (714/720) | 100% (153/153) / 100% (915/918) | 100% (102/102) / 100% (610/612) | 100% (105/105) / 100% (630/630) |

### ap_in_zone（追方初始 a 在安全空域內）

| 追方 | 躲方 | 否 | 是 |
|---|---|---|---|
| capture_pursuer | heuristic_evader | 57% (88/155) / — | 48% (41/85) / — |
| capture_pursuer | safe_evader | 100% (303/303) / 100% (1818/1818) | 100% (177/177) / 99% (1054/1062) |
| lambert_pursuer | heuristic_evader | 66% (103/155) / — | 62% (53/85) / — |
| lambert_pursuer | safe_evader | 100% (303/303) / 100% (1813/1818) | 100% (177/177) / 99% (1056/1062) |

### cross（躲方初始 a 與區間中心位於追方兩側）

| 追方 | 躲方 | 否 | 是 |
|---|---|---|---|
| capture_pursuer | heuristic_evader | 58% (30/52) / — | 53% (99/188) / — |
| capture_pursuer | safe_evader | 100% (93/93) / 100% (557/558) | 100% (387/387) / 100% (2315/2322) |
| lambert_pursuer | heuristic_evader | 60% (31/52) / — | 66% (125/188) / — |
| lambert_pursuer | safe_evader | 100% (93/93) / 100% (556/558) | 100% (387/387) / 100% (2313/2322) |

### dist0_over_DT（初始距離 / ΔV_lim·T_round）

| 追方 | 躲方 | <0.2 | 0.2–1 | ≥1 |
|---|---|---|---|---|
| capture_pursuer | heuristic_evader | 29% (9/31) / — | 47% (8/17) / — | 58% (112/192) / — |
| capture_pursuer | safe_evader | 100% (62/62) / 98% (365/372) | 100% (39/39) / 100% (234/234) | 100% (379/379) / 100% (2273/2274) |
| lambert_pursuer | heuristic_evader | 68% (21/31) / — | 53% (9/17) / — | 66% (126/192) / — |
| lambert_pursuer | safe_evader | 100% (62/62) / 98% (366/372) | 100% (39/39) / 100% (234/234) | 100% (379/379) / 100% (2269/2274) |

### epoch_gap_h（兩艘入軌時間差，時）

| 追方 | 躲方 | 0–6 | 6–12 | 12–24 | 缺資料 |
|---|---|---|---|---|---|
| capture_pursuer | heuristic_evader | 86% (6/7) / — | 73% (8/11) / — | 64% (14/22) / — | 50% (101/200) / — |
| capture_pursuer | safe_evader | 100% (13/13) / 100% (78/78) | 100% (24/24) / 100% (144/144) | 100% (43/43) / 100% (258/258) | 100% (400/400) / 100% (2392/2400) |
| lambert_pursuer | heuristic_evader | 86% (6/7) / — | 55% (6/11) / — | 64% (14/22) / — | 65% (130/200) / — |
| lambert_pursuer | safe_evader | 100% (13/13) / 100% (78/78) | 100% (24/24) / 100% (144/144) | 100% (43/43) / 100% (258/258) | 100% (400/400) / 100% (2389/2400) |

## safe_evader 輸掉的局

共 0 局。
