# 當天流程彩排 e26_rehearsal_full_lazy_evader_2burn

- 我方 evader、對手 `rollout_pursuer`、規則 `configs/rulesets/ranking_like_2burn.json`、幾何 `near_coplanar`、seed 0、推演 開
- 結局：**timeout**（我方勝），78 回合，t = 23323 s，最近距離 13.11 km
- 最終距離：引擎 2920.0372 km / GMAT 2920.0104 km
- GMAT 力學模型 `ranking_full`、每回合重設引擎狀態 開
- **GMAT 真實軌跡判定**：最近距離 13.111 km @ t=20911 s；全程沒進捕獲球（躲者勝）；引擎判定 timeout（evader 勝）
- 匯入狀態 vs 引擎最大差：16.71 m
- 我方決策耗時：平均 21.4 s、最長 56.4 s；GMAT 重播每回合平均 0.6 s
- 總耗時 983 s

| 回合 | 方 | 決策者 | |Δv| m/s | GMAT s | 決策 s | 匯入差 m | 距離 km | 事件 |
|---|---|---|---|---|---|---|---|---|
| 0 | pursuer | 對手 rollout_pursuer | 250.0 | 0.0 | 6.3 | 0.00 | 58.37 |  |
| 1 | evader | 我方 lazy_evader | 500.0 | 0.6 | 56.4 | 2.68 | 149.51 |  |
| 2 | pursuer | 對手 rollout_pursuer | 0.0 | 0.9 | 0.5 | 5.10 | 307.79 |  |
| 3 | evader | 我方 lazy_evader | 0.0 | 0.6 | 47.0 | 7.99 | 529.10 |  |
| 4 | pursuer | 對手 rollout_pursuer | 324.3 | 0.5 | 0.5 | 6.45 | 865.64 |  |
| 5 | evader | 我方 lazy_evader | 0.0 | 0.8 | 54.5 | 10.21 | 1290.18 |  |
| 6 | pursuer | 對手 rollout_pursuer | 0.0 | 0.6 | 0.8 | 16.26 | 1755.69 |  |
| 7 | evader | 我方 lazy_evader | 0.0 | 0.5 | 46.0 | 10.41 | 2221.77 |  |
| 8 | pursuer | 對手 rollout_pursuer | 0.0 | 0.6 | 1.0 | 6.63 | 2655.98 |  |
| 9 | evader | 我方 lazy_evader | 0.0 | 0.6 | 39.3 | 5.62 | 3034.17 |  |
| 10 | pursuer | 對手 rollout_pursuer | 0.0 | 0.6 | 0.5 | 2.97 | 3339.23 |  |
| 11 | evader | 我方 lazy_evader | 0.0 | 0.6 | 43.5 | 1.83 | 3559.53 |  |
| 12 | pursuer | 對手 rollout_pursuer | 0.0 | 0.5 | 0.6 | 1.01 | 3687.57 |  |
| 13 | evader | 我方 lazy_evader | 0.0 | 0.6 | 43.4 | 1.34 | 3718.96 |  |
| 14 | pursuer | 對手 rollout_pursuer | 0.0 | 0.6 | 0.5 | 2.01 | 3652.03 |  |
| 15 | evader | 我方 lazy_evader | 0.0 | 0.6 | 38.8 | 2.48 | 3487.81 |  |
| 16 | pursuer | 對手 rollout_pursuer | 0.0 | 0.6 | 0.3 | 2.55 | 3230.53 |  |
| 17 | evader | 我方 lazy_evader | 0.0 | 0.6 | 37.6 | 3.35 | 2888.70 |  |
| 18 | pursuer | 對手 rollout_pursuer | 4.0 | 0.6 | 0.4 | 4.00 | 2477.13 |  |
| 19 | evader | 我方 lazy_evader | 0.0 | 0.8 | 39.2 | 3.24 | 2017.11 |  |
| 20 | pursuer | 對手 rollout_pursuer | 1.4 | 1.6 | 0.6 | 1.15 | 1538.21 |  |
| 21 | evader | 我方 lazy_evader | 0.0 | 0.6 | 36.9 | 1.24 | 1075.14 |  |
| 22 | pursuer | 對手 rollout_pursuer | 5.6 | 0.6 | 0.5 | 2.59 | 659.61 |  |
| 23 | evader | 我方 lazy_evader | 500.0 | 0.8 | 32.1 | 3.72 | 314.74 |  |
| 24 | pursuer | 對手 rollout_pursuer | 0.0 | 0.9 | 0.4 | 4.63 | 268.38 |  |
| 25 | evader | 我方 lazy_evader | 0.0 | 0.6 | 29.0 | 2.82 | 547.52 |  |
| 26 | pursuer | 對手 rollout_pursuer | 0.0 | 0.6 | 0.4 | 4.54 | 889.39 |  |
| 27 | evader | 我方 lazy_evader | 0.0 | 0.6 | 25.5 | 4.63 | 1233.83 |  |
| 28 | pursuer | 對手 rollout_pursuer | 0.0 | 0.5 | 0.3 | 5.89 | 1540.81 |  |
| 29 | evader | 我方 lazy_evader | 0.0 | 0.5 | 25.2 | 8.30 | 1772.89 |  |
| 30 | pursuer | 對手 rollout_pursuer | 0.0 | 0.5 | 0.3 | 7.51 | 1901.83 |  |
| 31 | evader | 我方 lazy_evader | 0.0 | 0.5 | 26.2 | 5.93 | 1914.24 |  |
| 32 | pursuer | 對手 rollout_pursuer | 250.0 | 0.5 | 0.4 | 5.96 | 1775.25 |  |
| 33 | evader | 我方 lazy_evader | 0.0 | 0.8 | 25.2 | 7.21 | 1547.22 |  |
| 34 | pursuer | 對手 rollout_pursuer | 0.0 | 0.6 | 0.4 | 5.51 | 1331.54 |  |
| 35 | evader | 我方 lazy_evader | 0.0 | 0.6 | 23.2 | 2.44 | 1270.79 |  |
| 36 | pursuer | 對手 rollout_pursuer | 500.0 | 0.6 | 0.3 | 2.42 | 1354.98 |  |
| 37 | evader | 我方 lazy_evader | 0.0 | 0.8 | 20.9 | 3.53 | 1620.59 |  |
| 38 | pursuer | 對手 rollout_pursuer | 0.0 | 0.5 | 0.3 | 5.51 | 1953.21 |  |
| 39 | evader | 我方 lazy_evader | 0.0 | 0.5 | 19.2 | 6.14 | 2251.01 |  |
| 40 | pursuer | 對手 rollout_pursuer | 0.0 | 0.5 | 0.3 | 3.64 | 2457.28 |  |
| 41 | evader | 我方 lazy_evader | 0.0 | 0.5 | 18.1 | 3.95 | 2546.73 |  |
| 42 | pursuer | 對手 rollout_pursuer | 242.3 | 0.5 | 0.3 | 2.77 | 2570.09 |  |
| 43 | evader | 我方 lazy_evader | 0.0 | 0.5 | 14.7 | 4.11 | 2457.45 |  |
| 44 | pursuer | 對手 rollout_pursuer | 17.7 | 0.5 | 0.2 | 5.34 | 2220.65 |  |
| 45 | evader | 我方 lazy_evader | 0.0 | 0.5 | 13.9 | 7.15 | 1892.30 |  |
| 46 | pursuer | 對手 rollout_pursuer | 26.9 | 0.5 | 0.3 | 4.72 | 1508.50 |  |
| 47 | evader | 我方 lazy_evader | 0.0 | 0.8 | 14.1 | 2.90 | 1112.60 |  |
| 48 | pursuer | 對手 rollout_pursuer | 0.0 | 0.5 | 0.2 | 5.74 | 743.37 |  |
| 49 | evader | 我方 lazy_evader | 250.0 | 0.5 | 11.2 | 4.32 | 465.31 |  |
| 50 | pursuer | 對手 rollout_pursuer | 247.3 | 0.5 | 0.2 | 3.08 | 259.95 |  |
| 51 | evader | 我方 lazy_evader | 250.0 | 0.5 | 10.5 | 4.58 | 75.52 |  |
| 52 | pursuer | 對手 rollout_pursuer | 250.0 | 0.5 | 0.2 | 5.13 | 175.26 |  |
| 53 | evader | 我方 lazy_evader | 0.0 | 0.5 | 9.4 | 5.93 | 362.56 |  |
| 54 | pursuer | 對手 rollout_pursuer | 0.0 | 0.5 | 0.2 | 6.20 | 604.55 |  |
| 55 | evader | 我方 lazy_evader | 0.0 | 0.5 | 7.7 | 4.17 | 895.67 |  |
| 56 | pursuer | 對手 rollout_pursuer | 0.0 | 0.5 | 0.3 | 3.12 | 1217.85 |  |
| 57 | evader | 我方 lazy_evader | 0.0 | 0.5 | 6.3 | 6.40 | 1541.94 |  |
| 58 | pursuer | 對手 rollout_pursuer | 177.5 | 0.5 | 0.2 | 3.66 | 1800.95 |  |
| 59 | evader | 我方 lazy_evader | 0.0 | 0.8 | 4.9 | 9.09 | 1968.60 |  |
| 60 | pursuer | 對手 rollout_pursuer | 250.0 | 0.5 | 0.1 | 16.71 | 2023.00 |  |
| 61 | evader | 我方 lazy_evader | 0.0 | 0.8 | 3.7 | 6.51 | 1956.18 |  |
| 62 | pursuer | 對手 rollout_pursuer | 0.0 | 0.6 | 0.1 | 4.96 | 1782.09 |  |
| 63 | evader | 我方 lazy_evader | 0.0 | 0.5 | 2.6 | 6.46 | 1528.44 |  |
| 64 | pursuer | 對手 rollout_pursuer | 0.0 | 0.5 | 0.1 | 4.22 | 1230.61 |  |
| 65 | evader | 我方 lazy_evader | 0.0 | 0.5 | 2.0 | 7.79 | 923.75 |  |
| 66 | pursuer | 對手 rollout_pursuer | 0.0 | 0.5 | 0.1 | 4.45 | 636.29 |  |
| 67 | evader | 我方 lazy_evader | 250.0 | 0.5 | 1.8 | 2.14 | 380.10 |  |
| 68 | pursuer | 對手 rollout_pursuer | 438.3 | 0.5 | 0.1 | 2.03 | 177.87 |  |
| 69 | evader | 我方 lazy_evader | 250.0 | 0.8 | 1.5 | 3.18 | 74.72 |  |
| 70 | pursuer | 對手 rollout_pursuer | 0.0 | 0.5 | 0.0 | 3.16 | 335.66 |  |
| 71 | evader | 我方 lazy_evader | 0.0 | 0.5 | 0.6 | 3.49 | 639.51 |  |
| 72 | pursuer | 對手 rollout_pursuer | 0.0 | 0.5 | 0.0 | 4.76 | 999.88 |  |
| 73 | evader | 我方 lazy_evader | 0.0 | 0.5 | 0.4 | 5.66 | 1412.22 |  |
| 74 | pursuer | 對手 rollout_pursuer | 0.0 | 0.5 | 0.0 | 7.49 | 1855.48 |  |
| 75 | evader | 我方 lazy_evader | 0.0 | 0.5 | 0.2 | 8.04 | 2295.12 |  |
| 76 | pursuer | 對手 rollout_pursuer | 0.0 | 0.5 | 0.0 | 6.01 | 2687.11 |  |
| 77 | evader | 我方 lazy_evader | 0.0 | 0.5 | 0.0 | 13.76 | 2920.04 | timeout |
