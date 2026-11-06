# 當天流程彩排 rehearsal_full_evader_vs_rollout

- 我方 evader、對手 `rollout_pursuer`、規則 `configs/rulesets/ranking_like.json`、幾何 `near_coplanar`、seed 0、推演 開
- 結局：**timeout**（我方勝），78 回合，t = 23323 s，最近距離 60.52 km
- 最終距離：引擎 15107.2847 km / GMAT 15107.2821 km
- GMAT 力學模型 `ranking_full`、每回合重設引擎狀態 開
- **GMAT 真實軌跡判定**：最近距離 60.523 km @ t=0 s；全程沒進捕獲球（躲者勝）；引擎判定 timeout（evader 勝）
- 匯入狀態 vs 引擎最大差：27.31 m
- 我方決策耗時：平均 15.9 s、最長 58.7 s；GMAT 重播每回合平均 1.0 s
- 總耗時 828 s

| 回合 | 方 | 決策者 | |Δv| m/s | GMAT s | 決策 s | 匯入差 m | 距離 km | 事件 |
|---|---|---|---|---|---|---|---|---|
| 0 | pursuer | 對手 rollout_pursuer | 0.0 | 0.0 | 10.5 | 0.00 | 110.77 |  |
| 1 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 0.0 | 1.2 | 58.7 | 2.68 | 176.22 |  |
| 2 | pursuer | 對手 rollout_pursuer | 107.3 | 1.2 | 0.6 | 5.19 | 218.11 |  |
| 3 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 0.0 | 1.2 | 49.8 | 8.05 | 243.28 |  |
| 4 | pursuer | 對手 rollout_pursuer | 0.0 | 1.2 | 0.4 | 6.42 | 246.62 |  |
| 5 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 250.0 | 1.2 | 44.2 | 10.28 | 264.00 |  |
| 6 | pursuer | 對手 rollout_pursuer | 250.0 | 1.2 | 0.3 | 17.50 | 287.49 |  |
| 7 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 0.0 | 1.2 | 45.7 | 12.59 | 324.11 |  |
| 8 | pursuer | 對手 rollout_pursuer | 0.0 | 1.2 | 0.6 | 7.59 | 385.60 |  |
| 9 | evader | 我方 dv_evader | 250.0 | 1.2 | 43.7 | 8.05 | 528.78 |  |
| 10 | pursuer | 對手 rollout_pursuer | 191.9 | 1.2 | 0.4 | 3.33 | 722.14 |  |
| 11 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 0.0 | 1.2 | 40.0 | 1.67 | 917.26 |  |
| 12 | pursuer | 對手 rollout_pursuer | 65.0 | 1.3 | 0.6 | 2.02 | 1088.15 |  |
| 13 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 250.0 | 1.2 | 37.8 | 2.98 | 1277.37 |  |
| 14 | pursuer | 對手 rollout_pursuer | 0.0 | 1.2 | 0.5 | 4.02 | 1462.29 |  |
| 15 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 250.0 | 1.2 | 35.6 | 4.08 | 1619.62 |  |
| 16 | pursuer | 對手 rollout_pursuer | 0.0 | 1.1 | 0.3 | 3.02 | 1796.84 |  |
| 17 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 250.0 | 1.1 | 27.2 | 2.02 | 1984.26 |  |
| 18 | pursuer | 對手 rollout_pursuer | 250.0 | 1.1 | 0.2 | 1.00 | 2300.78 |  |
| 19 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 250.0 | 1.0 | 24.0 | 1.14 | 2710.62 |  |
| 20 | pursuer | 對手 rollout_pursuer | 0.0 | 0.9 | 0.3 | 1.55 | 3177.69 |  |
| 21 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 0.0 | 1.0 | 22.2 | 1.73 | 3679.38 |  |
| 22 | pursuer | 對手 rollout_pursuer | 162.3 | 0.9 | 0.3 | 2.28 | 4238.43 |  |
| 23 | evader | 我方 sb3:/home/corn/ODC_GMAT_DRL_hap107/models/evader.zip | 151.2 | 0.9 | 21.0 | 2.14 | 4759.19 |  |
| 24 | pursuer | 對手 rollout_pursuer | 122.5 | 0.9 | 0.3 | 2.88 | 5277.94 |  |
| 25 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 0.0 | 0.9 | 17.8 | 3.31 | 5732.64 |  |
| 26 | pursuer | 對手 rollout_pursuer | 0.0 | 0.9 | 0.2 | 2.87 | 6099.27 |  |
| 27 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 0.0 | 1.0 | 16.6 | 3.10 | 6360.94 |  |
| 28 | pursuer | 對手 rollout_pursuer | 0.0 | 0.9 | 0.2 | 3.95 | 6507.70 |  |
| 29 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 250.0 | 0.9 | 14.4 | 4.00 | 6474.01 |  |
| 30 | pursuer | 對手 rollout_pursuer | 0.0 | 0.9 | 0.2 | 3.29 | 6345.75 |  |
| 31 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 250.0 | 0.9 | 12.6 | 2.74 | 6074.60 |  |
| 32 | pursuer | 對手 rollout_pursuer | 0.0 | 1.0 | 0.2 | 3.23 | 5766.72 |  |
| 33 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 250.0 | 1.1 | 12.0 | 3.11 | 5430.97 |  |
| 34 | pursuer | 對手 rollout_pursuer | 250.0 | 1.2 | 0.2 | 2.71 | 5235.01 |  |
| 35 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 250.0 | 0.9 | 10.2 | 2.41 | 5119.89 |  |
| 36 | pursuer | 對手 rollout_pursuer | 0.0 | 0.9 | 0.1 | 1.74 | 5169.66 |  |
| 37 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 0.0 | 0.9 | 9.6 | 0.91 | 5398.28 |  |
| 38 | pursuer | 對手 rollout_pursuer | 0.0 | 0.9 | 0.1 | 0.45 | 5803.28 |  |
| 39 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 0.0 | 1.0 | 9.4 | 0.63 | 6370.25 |  |
| 40 | pursuer | 對手 rollout_pursuer | 0.0 | 0.9 | 0.1 | 0.80 | 7079.29 |  |
| 41 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 0.0 | 1.0 | 8.7 | 0.89 | 7909.76 |  |
| 42 | pursuer | 對手 rollout_pursuer | 0.0 | 0.9 | 0.1 | 0.90 | 8842.32 |  |
| 43 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 0.0 | 0.9 | 8.2 | 0.83 | 9859.19 |  |
| 44 | pursuer | 對手 rollout_pursuer | 0.0 | 0.9 | 0.1 | 0.69 | 10943.43 |  |
| 45 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 0.0 | 0.9 | 7.5 | 0.57 | 12078.13 |  |
| 46 | pursuer | 對手 rollout_pursuer | 0.0 | 0.9 | 0.1 | 0.63 | 13245.69 |  |
| 47 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 0.0 | 0.9 | 6.7 | 0.82 | 14427.25 |  |
| 48 | pursuer | 對手 rollout_pursuer | 0.0 | 0.9 | 0.1 | 0.99 | 15602.45 |  |
| 49 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 0.0 | 0.9 | 6.2 | 1.12 | 16749.49 |  |
| 50 | pursuer | 對手 rollout_pursuer | 0.0 | 0.9 | 0.1 | 1.10 | 17845.58 |  |
| 51 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 0.0 | 0.9 | 5.4 | 1.01 | 18867.78 |  |
| 52 | pursuer | 對手 rollout_pursuer | 0.0 | 0.9 | 0.1 | 1.06 | 19794.21 |  |
| 53 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 0.0 | 0.9 | 4.8 | 1.23 | 20605.54 |  |
| 54 | pursuer | 對手 rollout_pursuer | 250.0 | 1.0 | 0.1 | 1.23 | 21321.78 |  |
| 55 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 0.0 | 0.9 | 4.2 | 1.23 | 21884.56 |  |
| 56 | pursuer | 對手 rollout_pursuer | 250.0 | 0.9 | 0.1 | 1.19 | 22333.19 |  |
| 57 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 0.0 | 0.9 | 3.6 | 1.09 | 22618.73 |  |
| 58 | pursuer | 對手 rollout_pursuer | 250.0 | 0.9 | 0.1 | 1.19 | 22793.83 |  |
| 59 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 0.0 | 0.9 | 3.0 | 1.30 | 22813.56 |  |
| 60 | pursuer | 對手 rollout_pursuer | 250.0 | 0.9 | 0.1 | 1.36 | 22735.15 |  |
| 61 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 0.0 | 0.8 | 2.5 | 1.39 | 22513.52 |  |
| 62 | pursuer | 對手 rollout_pursuer | 0.0 | 0.9 | 0.1 | 1.36 | 22161.79 |  |
| 63 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 0.0 | 1.0 | 2.0 | 1.33 | 21692.78 |  |
| 64 | pursuer | 對手 rollout_pursuer | 0.0 | 0.9 | 0.1 | 1.31 | 21119.93 |  |
| 65 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 0.0 | 0.9 | 1.7 | 1.24 | 20458.32 |  |
| 66 | pursuer | 對手 rollout_pursuer | 62.5 | 0.9 | 0.1 | 1.09 | 19734.02 |  |
| 67 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 0.0 | 1.0 | 1.2 | 0.84 | 18955.02 |  |
| 68 | pursuer | 對手 rollout_pursuer | 7.8 | 0.9 | 0.0 | 0.66 | 18148.96 |  |
| 69 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 0.0 | 0.8 | 0.9 | 0.78 | 17347.96 |  |
| 70 | pursuer | 對手 rollout_pursuer | 3.9 | 0.9 | 0.0 | 1.54 | 16592.77 |  |
| 71 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 0.0 | 0.9 | 0.6 | 2.69 | 15928.08 |  |
| 72 | pursuer | 對手 rollout_pursuer | 0.0 | 0.9 | 0.0 | 3.78 | 15397.88 |  |
| 73 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 0.0 | 0.9 | 0.3 | 5.97 | 15034.96 |  |
| 74 | pursuer | 對手 rollout_pursuer | 0.0 | 0.9 | 0.0 | 8.34 | 14851.16 |  |
| 75 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 0.0 | 1.0 | 0.2 | 8.76 | 14834.31 |  |
| 76 | pursuer | 對手 rollout_pursuer | 0.0 | 0.9 | 0.0 | 27.31 | 14953.63 |  |
| 77 | evader | 我方 {'name': 'rollout_evader', 'workers': 3} | 0.0 | 0.8 | 0.0 | 2.63 | 15107.28 | timeout |
