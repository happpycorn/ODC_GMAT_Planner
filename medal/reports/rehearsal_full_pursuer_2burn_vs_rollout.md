# 當天流程彩排 rehearsal_full_pursuer_2burn_vs_rollout

- 我方 pursuer、對手 `rollout_evader`、規則 `configs/rulesets/ranking_like_2burn.json`、幾何 `near_coplanar`、seed 0、推演 開
- 結局：**capture**（我方勝），51 回合，t = 15130 s，最近距離 0.03 km
- 最終距離：引擎 5.0000 km / GMAT 5.0000 km
- GMAT 力學模型 `ranking_full`、每回合重設引擎狀態 開
- **GMAT 真實軌跡判定**：最近距離 0.512 km @ t=15134 s；t=15131 s 進捕獲球（追者勝）；引擎判定 capture（pursuer 勝）
- 匯入狀態 vs 引擎最大差：14.10 m
- 我方決策耗時：平均 3.9 s、最長 20.1 s；GMAT 重播每回合平均 0.6 s
- 總耗時 179 s

| 回合 | 方 | 決策者 | |Δv| m/s | GMAT s | 決策 s | 匯入差 m | 距離 km | 事件 |
|---|---|---|---|---|---|---|---|---|
| 0 | pursuer | 我方 sb3:/home/corn/ODC_GMAT_DRL_hap107/models/pursuer.zip | 316.0 | 0.0 | 20.1 | 0.00 | 46.11 |  |
| 1 | evader | 對手 rollout_evader | 500.0 | 0.8 | 1.2 | 2.68 | 121.42 |  |
| 2 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 4} | 109.9 | 0.8 | 9.6 | 5.09 | 284.82 |  |
| 3 | evader | 對手 rollout_evader | 500.0 | 1.7 | 1.1 | 8.00 | 558.75 |  |
| 4 | pursuer | 我方 lambert_pursuer | 264.7 | 0.8 | 10.4 | 6.30 | 925.34 |  |
| 5 | evader | 對手 rollout_evader | 500.0 | 0.8 | 0.9 | 9.87 | 1369.85 |  |
| 6 | pursuer | 我方 sb3:/home/corn/ODC_GMAT_DRL_hap107/models/pursuer.zip | 273.2 | 0.8 | 7.9 | 14.10 | 1904.08 |  |
| 7 | evader | 對手 rollout_evader | 500.0 | 0.8 | 0.9 | 8.82 | 2537.65 |  |
| 8 | pursuer | 我方 {'name': 'lambert_pursuer', 'time_weight_mps': 60.0} | 121.0 | 0.8 | 7.0 | 5.38 | 3232.94 |  |
| 9 | evader | 對手 rollout_evader | 0.0 | 0.8 | 0.7 | 4.03 | 3914.12 |  |
| 10 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 4} | 18.6 | 0.5 | 6.5 | 1.72 | 4558.73 |  |
| 11 | evader | 對手 rollout_evader | 250.0 | 0.8 | 0.5 | 1.07 | 5142.98 |  |
| 12 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 4} | 193.0 | 0.5 | 5.7 | 0.60 | 5741.68 |  |
| 13 | evader | 對手 rollout_evader | 250.0 | 0.5 | 0.4 | 0.50 | 6275.22 |  |
| 14 | pursuer | 我方 sb3:/home/corn/ODC_GMAT_DRL_hap107/models/pursuer.zip | 232.5 | 0.5 | 5.2 | 0.61 | 6835.10 |  |
| 15 | evader | 對手 rollout_evader | 500.0 | 0.8 | 0.5 | 0.71 | 7319.35 |  |
| 16 | pursuer | 我方 sb3:/home/corn/ODC_GMAT_DRL_hap107/models/pursuer.zip | 406.9 | 0.8 | 4.4 | 0.73 | 7881.55 |  |
| 17 | evader | 對手 rollout_evader | 0.0 | 0.8 | 0.2 | 0.69 | 8430.56 |  |
| 18 | pursuer | 我方 sb3:/home/corn/ODC_GMAT_DRL_hap107/models/pursuer.zip | 0.7 | 0.5 | 4.0 | 0.60 | 8943.21 |  |
| 19 | evader | 對手 rollout_evader | 0.0 | 0.8 | 0.1 | 0.49 | 9413.93 |  |
| 20 | pursuer | 我方 sb3:/home/corn/ODC_GMAT_DRL_hap107/models/pursuer.zip | 0.2 | 0.5 | 3.5 | 0.39 | 9838.55 |  |
| 21 | evader | 對手 rollout_evader | 0.0 | 0.8 | 0.1 | 0.31 | 10213.93 |  |
| 22 | pursuer | 我方 sb3:/home/corn/ODC_GMAT_DRL_hap107/models/pursuer.zip | 0.4 | 0.5 | 3.1 | 0.25 | 10537.71 |  |
| 23 | evader | 對手 rollout_evader | 0.0 | 0.8 | 0.1 | 0.22 | 10808.04 |  |
| 24 | pursuer | 我方 sb3:/home/corn/ODC_GMAT_DRL_hap107/models/pursuer.zip | 0.4 | 0.5 | 2.8 | 0.22 | 11023.44 |  |
| 25 | evader | 對手 rollout_evader | 0.0 | 0.8 | 0.1 | 0.21 | 11182.70 |  |
| 26 | pursuer | 我方 sb3:/home/corn/ODC_GMAT_DRL_hap107/models/pursuer.zip | 14.0 | 0.5 | 2.4 | 0.20 | 11285.31 |  |
| 27 | evader | 對手 rollout_evader | 0.0 | 0.8 | 0.1 | 0.19 | 11330.49 |  |
| 28 | pursuer | 我方 lambert_pursuer | 8.5 | 0.5 | 2.0 | 0.19 | 11316.80 |  |
| 29 | evader | 對手 rollout_evader | 0.0 | 0.8 | 0.1 | 0.19 | 11243.35 |  |
| 30 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 4} | 0.0 | 0.5 | 1.7 | 0.19 | 11109.32 |  |
| 31 | evader | 對手 rollout_evader | 0.0 | 0.5 | 0.1 | 0.18 | 10913.94 |  |
| 32 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 4} | 0.0 | 0.5 | 1.4 | 0.17 | 10656.48 |  |
| 33 | evader | 對手 rollout_evader | 0.0 | 0.5 | 0.1 | 0.18 | 10336.32 |  |
| 34 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 4} | 0.0 | 0.5 | 1.2 | 0.20 | 9953.05 |  |
| 35 | evader | 對手 rollout_evader | 0.0 | 0.5 | 0.1 | 0.23 | 9506.56 |  |
| 36 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 4} | 0.6 | 0.5 | 1.0 | 0.27 | 8997.20 |  |
| 37 | evader | 對手 rollout_evader | 0.0 | 0.5 | 0.1 | 0.30 | 8426.19 |  |
| 38 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 4} | 0.7 | 0.5 | 0.7 | 0.34 | 7795.84 |  |
| 39 | evader | 對手 rollout_evader | 0.0 | 0.5 | 0.0 | 0.36 | 7110.37 |  |
| 40 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 4} | 0.0 | 0.5 | 0.6 | 0.37 | 6376.42 |  |
| 41 | evader | 對手 rollout_evader | 0.0 | 0.5 | 0.0 | 0.42 | 5604.00 |  |
| 42 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 4} | 0.0 | 0.5 | 0.4 | 0.54 | 4807.32 |  |
| 43 | evader | 對手 rollout_evader | 0.0 | 0.5 | 0.0 | 0.76 | 4005.32 |  |
| 44 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 4} | 0.0 | 0.5 | 0.3 | 0.98 | 3221.15 |  |
| 45 | evader | 對手 rollout_evader | 0.0 | 0.5 | 0.0 | 1.12 | 2479.80 |  |
| 46 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 4} | 0.0 | 0.5 | 0.1 | 1.21 | 1803.33 |  |
| 47 | evader | 對手 rollout_evader | 0.0 | 0.5 | 0.0 | 1.15 | 1204.14 |  |
| 48 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 4} | 0.0 | 0.5 | 0.1 | 1.20 | 678.39 |  |
| 49 | evader | 對手 rollout_evader | 0.0 | 0.5 | 0.0 | 1.38 | 203.91 |  |
| 50 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 4} | 0.0 | 0.5 | 0.0 | 1.47 | 5.00 | capture |
