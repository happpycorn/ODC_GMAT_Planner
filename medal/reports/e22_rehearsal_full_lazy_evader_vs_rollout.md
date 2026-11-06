# 當天流程彩排 e22_rehearsal_full_lazy_evader_vs_rollout

- 我方 evader、對手 `rollout_pursuer`、規則 `configs/rulesets/ranking_like.json`、幾何 `near_coplanar`、seed 0、推演 開
- 結局：**timeout**（我方勝），78 回合，t = 23323 s，最近距離 8.87 km
- 最終距離：引擎 55.9488 km / GMAT 55.9488 km
- GMAT 力學模型 `ranking_full`、每回合重設引擎狀態 開
- **GMAT 真實軌跡判定**：最近距離 8.876 km @ t=13191 s；全程沒進捕獲球（躲者勝）；引擎判定 timeout（evader 勝）
- 匯入狀態 vs 引擎最大差：17.50 m
- 我方決策耗時：平均 13.2 s、最長 30.6 s；GMAT 重播每回合平均 0.7 s
- 總耗時 634 s

| 回合 | 方 | 決策者 | |Δv| m/s | GMAT s | 決策 s | 匯入差 m | 距離 km | 事件 |
|---|---|---|---|---|---|---|---|---|
| 0 | pursuer | 對手 rollout_pursuer | 0.0 | 0.0 | 6.1 | 0.00 | 110.77 |  |
| 1 | evader | 我方 lazy_evader | 0.0 | 0.6 | 30.6 | 2.68 | 176.22 |  |
| 2 | pursuer | 對手 rollout_pursuer | 107.3 | 0.6 | 0.3 | 5.19 | 218.11 |  |
| 3 | evader | 我方 lazy_evader | 0.0 | 0.6 | 26.6 | 8.05 | 243.28 |  |
| 4 | pursuer | 對手 rollout_pursuer | 0.0 | 0.6 | 0.2 | 6.42 | 246.62 |  |
| 5 | evader | 我方 lazy_evader | 0.0 | 0.6 | 25.5 | 10.28 | 227.64 |  |
| 6 | pursuer | 對手 rollout_pursuer | 0.0 | 0.6 | 0.2 | 17.50 | 188.73 |  |
| 7 | evader | 我方 lazy_evader | 250.0 | 0.6 | 24.0 | 12.74 | 143.80 |  |
| 8 | pursuer | 對手 rollout_pursuer | 0.0 | 0.6 | 0.2 | 8.00 | 172.32 |  |
| 9 | evader | 我方 lazy_evader | 0.0 | 0.6 | 23.9 | 9.20 | 277.09 |  |
| 10 | pursuer | 對手 rollout_pursuer | 0.0 | 0.6 | 0.3 | 4.40 | 423.72 |  |
| 11 | evader | 我方 lazy_evader | 0.0 | 0.6 | 23.3 | 2.59 | 592.71 |  |
| 12 | pursuer | 對手 rollout_pursuer | 165.3 | 0.6 | 0.3 | 4.73 | 757.18 |  |
| 13 | evader | 我方 lazy_evader | 0.0 | 0.7 | 27.8 | 7.81 | 910.23 |  |
| 14 | pursuer | 對手 rollout_pursuer | 131.2 | 0.7 | 0.2 | 9.29 | 1015.37 |  |
| 15 | evader | 我方 lazy_evader | 0.0 | 0.7 | 22.2 | 6.78 | 1075.30 |  |
| 16 | pursuer | 對手 rollout_pursuer | 26.5 | 0.7 | 0.2 | 3.11 | 1081.43 |  |
| 17 | evader | 我方 lazy_evader | 0.0 | 0.7 | 22.7 | 1.29 | 1034.62 |  |
| 18 | pursuer | 對手 rollout_pursuer | 0.0 | 0.7 | 0.2 | 2.54 | 940.52 |  |
| 19 | evader | 我方 lazy_evader | 0.0 | 0.6 | 23.0 | 2.93 | 809.72 |  |
| 20 | pursuer | 對手 rollout_pursuer | 13.7 | 0.6 | 0.2 | 4.96 | 655.32 |  |
| 21 | evader | 我方 lazy_evader | 0.0 | 0.7 | 21.9 | 2.99 | 493.47 |  |
| 22 | pursuer | 對手 rollout_pursuer | 6.3 | 0.7 | 0.2 | 4.15 | 335.61 |  |
| 23 | evader | 我方 lazy_evader | 250.0 | 0.7 | 19.7 | 4.98 | 157.40 |  |
| 24 | pursuer | 對手 rollout_pursuer | 250.0 | 0.6 | 0.2 | 5.04 | 120.04 |  |
| 25 | evader | 我方 lazy_evader | 0.0 | 0.7 | 17.9 | 6.68 | 293.73 |  |
| 26 | pursuer | 對手 rollout_pursuer | 50.8 | 0.7 | 0.1 | 10.85 | 491.75 |  |
| 27 | evader | 我方 lazy_evader | 0.0 | 0.7 | 17.6 | 8.96 | 704.41 |  |
| 28 | pursuer | 對手 rollout_pursuer | 0.0 | 0.7 | 0.3 | 10.23 | 922.82 |  |
| 29 | evader | 我方 lazy_evader | 0.0 | 0.7 | 16.0 | 10.16 | 1133.85 |  |
| 30 | pursuer | 對手 rollout_pursuer | 0.0 | 0.7 | 0.2 | 4.87 | 1321.78 |  |
| 31 | evader | 我方 lazy_evader | 0.0 | 0.7 | 16.9 | 2.92 | 1471.25 |  |
| 32 | pursuer | 對手 rollout_pursuer | 0.0 | 0.7 | 0.1 | 3.67 | 1569.68 |  |
| 33 | evader | 我方 lazy_evader | 0.0 | 0.8 | 16.0 | 5.70 | 1609.06 |  |
| 34 | pursuer | 對手 rollout_pursuer | 96.1 | 0.8 | 0.1 | 5.22 | 1587.56 |  |
| 35 | evader | 我方 lazy_evader | 0.0 | 0.7 | 14.6 | 4.70 | 1510.13 |  |
| 36 | pursuer | 對手 rollout_pursuer | 0.0 | 0.7 | 0.2 | 1.78 | 1383.66 |  |
| 37 | evader | 我方 lazy_evader | 0.0 | 0.7 | 13.8 | 2.27 | 1218.26 |  |
| 38 | pursuer | 對手 rollout_pursuer | 0.0 | 0.8 | 0.2 | 2.87 | 1025.96 |  |
| 39 | evader | 我方 lazy_evader | 0.0 | 0.7 | 12.9 | 2.91 | 819.17 |  |
| 40 | pursuer | 對手 rollout_pursuer | 2.5 | 0.8 | 0.1 | 4.42 | 608.35 |  |
| 41 | evader | 我方 lazy_evader | 0.0 | 0.7 | 12.2 | 3.87 | 402.13 |  |
| 42 | pursuer | 對手 rollout_pursuer | 34.1 | 0.7 | 0.2 | 3.02 | 194.97 |  |
| 43 | evader | 我方 lazy_evader | 0.0 | 0.7 | 12.7 | 3.11 | 11.00 |  |
| 44 | pursuer | 對手 rollout_pursuer | 0.0 | 0.7 | 0.1 | 4.57 | 207.89 |  |
| 45 | evader | 我方 lazy_evader | 0.0 | 0.7 | 10.7 | 3.03 | 415.30 |  |
| 46 | pursuer | 對手 rollout_pursuer | 0.0 | 0.8 | 0.1 | 4.80 | 631.95 |  |
| 47 | evader | 我方 lazy_evader | 0.0 | 0.8 | 10.4 | 7.21 | 854.70 |  |
| 48 | pursuer | 對手 rollout_pursuer | 0.0 | 0.8 | 0.1 | 10.08 | 1074.46 |  |
| 49 | evader | 我方 lazy_evader | 0.0 | 0.7 | 9.5 | 9.27 | 1278.00 |  |
| 50 | pursuer | 對手 rollout_pursuer | 14.8 | 0.8 | 0.1 | 6.00 | 1448.17 |  |
| 51 | evader | 我方 lazy_evader | 0.0 | 0.7 | 8.3 | 3.83 | 1573.81 |  |
| 52 | pursuer | 對手 rollout_pursuer | 23.0 | 0.7 | 0.1 | 5.00 | 1643.27 |  |
| 53 | evader | 我方 lazy_evader | 0.0 | 0.7 | 7.4 | 4.01 | 1653.14 |  |
| 54 | pursuer | 對手 rollout_pursuer | 0.0 | 0.7 | 0.1 | 3.68 | 1603.23 |  |
| 55 | evader | 我方 lazy_evader | 0.0 | 0.7 | 6.5 | 3.85 | 1498.26 |  |
| 56 | pursuer | 對手 rollout_pursuer | 19.1 | 0.7 | 0.1 | 3.13 | 1343.89 |  |
| 57 | evader | 我方 lazy_evader | 0.0 | 0.7 | 5.5 | 3.12 | 1153.79 |  |
| 58 | pursuer | 對手 rollout_pursuer | 61.3 | 0.8 | 0.1 | 2.99 | 927.26 |  |
| 59 | evader | 我方 lazy_evader | 0.0 | 0.7 | 4.3 | 3.02 | 690.37 |  |
| 60 | pursuer | 對手 rollout_pursuer | 0.0 | 0.7 | 0.0 | 3.82 | 456.39 |  |
| 61 | evader | 我方 lazy_evader | 250.0 | 0.7 | 3.2 | 4.10 | 197.83 |  |
| 62 | pursuer | 對手 rollout_pursuer | 0.0 | 0.7 | 0.0 | 3.23 | 157.60 |  |
| 63 | evader | 我方 lazy_evader | 0.0 | 0.7 | 2.6 | 1.93 | 428.55 |  |
| 64 | pursuer | 對手 rollout_pursuer | 250.0 | 0.7 | 0.0 | 1.75 | 696.25 |  |
| 65 | evader | 我方 lazy_evader | 0.0 | 0.7 | 2.0 | 5.35 | 996.55 |  |
| 66 | pursuer | 對手 rollout_pursuer | 250.0 | 0.7 | 0.0 | 5.39 | 1259.24 |  |
| 67 | evader | 我方 lazy_evader | 0.0 | 0.7 | 1.7 | 7.57 | 1498.20 |  |
| 68 | pursuer | 對手 rollout_pursuer | 0.0 | 0.7 | 0.0 | 9.65 | 1686.22 |  |
| 69 | evader | 我方 lazy_evader | 0.0 | 0.7 | 1.1 | 10.07 | 1803.71 |  |
| 70 | pursuer | 對手 rollout_pursuer | 250.0 | 0.7 | 0.0 | 7.35 | 1802.73 |  |
| 71 | evader | 我方 lazy_evader | 0.0 | 0.7 | 0.8 | 4.60 | 1703.12 |  |
| 72 | pursuer | 對手 rollout_pursuer | 250.0 | 0.7 | 0.0 | 5.56 | 1474.80 |  |
| 73 | evader | 我方 lazy_evader | 0.0 | 0.7 | 0.4 | 6.48 | 1179.82 |  |
| 74 | pursuer | 對手 rollout_pursuer | 84.2 | 0.6 | 0.0 | 5.89 | 842.29 |  |
| 75 | evader | 我方 lazy_evader | 0.0 | 0.7 | 0.2 | 8.53 | 512.22 |  |
| 76 | pursuer | 對手 rollout_pursuer | 0.0 | 0.7 | 0.0 | 7.02 | 209.96 |  |
| 77 | evader | 我方 lazy_evader | 250.0 | 0.7 | 0.0 | 3.90 | 55.95 | timeout |
