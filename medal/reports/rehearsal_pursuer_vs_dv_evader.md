# 當天流程彩排 rehearsal_pursuer_vs_dv_evader

- 我方 pursuer、對手 `dv_evader`、規則 `default`、幾何 `near_coplanar`、seed 0、推演 開
- 結局：**capture**（我方勝），62 回合，t = 18551 s，最近距離 0.03 km
- 最終距離：引擎 5.0000 km / GMAT 5.0057 km
- 匯入狀態 vs 引擎最大差：47.37 m
- 我方決策耗時：平均 1.5 s、最長 11.6 s；GMAT 重播每回合平均 0.5 s
- 總耗時 79 s

| 回合 | 方 | 決策者 | |Δv| m/s | GMAT s | 決策 s | 匯入差 m | 距離 km | 事件 |
|---|---|---|---|---|---|---|---|---|
| 0 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 8} | 303.2 | 0.0 | 11.6 | 0.00 | 26.56 |  |
| 1 | evader | 對手 dv_evader | 1500.0 | 0.2 | 0.0 | 0.04 | 457.48 |  |
| 2 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 8} | 0.0 | 0.2 | 4.0 | 0.15 | 987.34 |  |
| 3 | evader | 對手 dv_evader | 1500.0 | 0.2 | 0.0 | 0.29 | 2037.32 |  |
| 4 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 8} | 0.0 | 0.2 | 3.4 | 0.46 | 3380.69 |  |
| 5 | evader | 對手 dv_evader | 0.0 | 0.2 | 0.0 | 0.67 | 5054.95 |  |
| 6 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 8} | 0.0 | 0.2 | 3.1 | 0.95 | 7044.50 |  |
| 7 | evader | 對手 dv_evader | 0.0 | 0.3 | 0.0 | 1.33 | 9300.39 |  |
| 8 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 8} | 0.0 | 0.3 | 2.8 | 1.81 | 11759.34 |  |
| 9 | evader | 對手 dv_evader | 0.0 | 0.3 | 0.0 | 2.35 | 14353.70 |  |
| 10 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 8} | 0.0 | 0.3 | 2.5 | 2.94 | 17015.52 |  |
| 11 | evader | 對手 dv_evader | 0.0 | 0.3 | 0.0 | 3.54 | 19677.66 |  |
| 12 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 8} | 0.0 | 0.3 | 2.3 | 4.12 | 22273.56 |  |
| 13 | evader | 對手 dv_evader | 0.0 | 0.3 | 0.0 | 4.67 | 24736.70 |  |
| 14 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 8} | 0.0 | 0.3 | 2.1 | 5.18 | 27000.19 |  |
| 15 | evader | 對手 dv_evader | 0.0 | 0.4 | 0.0 | 5.62 | 28997.12 |  |
| 16 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 8} | 0.0 | 0.3 | 2.0 | 6.00 | 30662.05 |  |
| 17 | evader | 對手 dv_evader | 0.0 | 0.3 | 0.0 | 6.31 | 31934.09 |  |
| 18 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 8} | 0.0 | 0.4 | 1.8 | 6.54 | 32761.82 |  |
| 19 | evader | 對手 dv_evader | 0.0 | 0.4 | 0.0 | 6.68 | 33110.25 |  |
| 20 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 8} | 0.0 | 0.4 | 1.7 | 6.74 | 32969.19 |  |
| 21 | evader | 對手 dv_evader | 0.0 | 0.4 | 0.0 | 6.73 | 32362.18 |  |
| 22 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 8} | 1500.0 | 0.4 | 1.5 | 6.70 | 31137.47 |  |
| 23 | evader | 對手 dv_evader | 0.0 | 0.4 | 0.0 | 6.68 | 29715.32 |  |
| 24 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 8} | 1160.9 | 0.4 | 1.4 | 6.78 | 28028.52 |  |
| 25 | evader | 對手 dv_evader | 0.0 | 0.4 | 0.0 | 7.04 | 26418.91 |  |
| 26 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 8} | 0.8 | 0.4 | 1.2 | 7.49 | 24922.88 |  |
| 27 | evader | 對手 dv_evader | 0.0 | 0.4 | 0.0 | 8.10 | 23543.88 |  |
| 28 | pursuer | 我方 sb3:/home/corn/ODC_GMAT_DRL/models/pursuer.zip | 35.1 | 0.5 | 1.1 | 8.84 | 22263.35 |  |
| 29 | evader | 對手 dv_evader | 0.0 | 0.5 | 0.0 | 9.69 | 21077.85 |  |
| 30 | pursuer | 我方 sb3:/home/corn/ODC_GMAT_DRL/models/pursuer.zip | 0.0 | 0.5 | 0.7 | 10.61 | 19975.07 |  |
| 31 | evader | 對手 dv_evader | 0.0 | 0.5 | 0.0 | 11.59 | 18944.00 |  |
| 32 | pursuer | 我方 sb3:/home/corn/ODC_GMAT_DRL/models/pursuer.zip | 0.0 | 0.5 | 0.7 | 12.61 | 17975.13 |  |
| 33 | evader | 對手 dv_evader | 0.0 | 0.5 | 0.0 | 13.66 | 17060.38 |  |
| 34 | pursuer | 我方 lambert_pursuer | 0.0 | 0.5 | 0.6 | 14.74 | 16192.93 |  |
| 35 | evader | 對手 dv_evader | 0.0 | 0.5 | 0.0 | 15.83 | 15366.95 |  |
| 36 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 8} | 0.0 | 0.5 | 0.6 | 16.95 | 14577.50 |  |
| 37 | evader | 對手 dv_evader | 0.0 | 0.6 | 0.0 | 18.08 | 13820.34 |  |
| 38 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 8} | 0.0 | 0.5 | 0.5 | 19.22 | 13091.80 |  |
| 39 | evader | 對手 dv_evader | 0.0 | 0.6 | 0.0 | 20.36 | 12388.70 |  |
| 40 | pursuer | 我方 lambert_pursuer | 0.0 | 0.6 | 0.4 | 21.52 | 11708.28 |  |
| 41 | evader | 對手 dv_evader | 0.0 | 0.6 | 0.0 | 22.69 | 11048.08 |  |
| 42 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 8} | 0.0 | 0.6 | 0.4 | 23.86 | 10405.97 |  |
| 43 | evader | 對手 dv_evader | 0.0 | 0.6 | 0.0 | 25.05 | 9780.03 |  |
| 44 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 8} | 0.0 | 0.6 | 0.3 | 26.23 | 9168.54 |  |
| 45 | evader | 對手 dv_evader | 0.0 | 0.6 | 0.0 | 27.43 | 8570.00 |  |
| 46 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 8} | 0.0 | 0.7 | 0.3 | 28.63 | 7983.00 |  |
| 47 | evader | 對手 dv_evader | 0.0 | 0.6 | 0.0 | 29.84 | 7406.32 |  |
| 48 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 8} | 0.0 | 0.6 | 0.2 | 31.05 | 6838.81 |  |
| 49 | evader | 對手 dv_evader | 0.0 | 0.7 | 0.0 | 32.27 | 6279.45 |  |
| 50 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 8} | 0.0 | 0.7 | 0.2 | 33.49 | 5727.29 |  |
| 51 | evader | 對手 dv_evader | 0.0 | 0.7 | 0.0 | 34.72 | 5181.46 |  |
| 52 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 8} | 0.0 | 0.7 | 0.1 | 35.96 | 4641.15 |  |
| 53 | evader | 對手 dv_evader | 0.0 | 0.7 | 0.0 | 37.20 | 4105.63 |  |
| 54 | pursuer | 我方 lambert_pursuer | 0.0 | 0.7 | 0.1 | 38.45 | 3574.22 |  |
| 55 | evader | 對手 dv_evader | 0.0 | 0.7 | 0.0 | 39.71 | 3046.26 |  |
| 56 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 8} | 0.0 | 0.7 | 0.1 | 40.97 | 2521.16 |  |
| 57 | evader | 對手 dv_evader | 0.0 | 0.7 | 0.0 | 42.24 | 1998.35 |  |
| 58 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 8} | 0.0 | 0.7 | 0.0 | 43.51 | 1477.33 |  |
| 59 | evader | 對手 dv_evader | 0.0 | 0.8 | 0.0 | 44.79 | 957.57 |  |
| 60 | pursuer | 我方 {'name': 'rollout_pursuer', 'workers': 8} | 0.0 | 0.8 | 0.0 | 46.07 | 438.63 |  |
| 61 | evader | 對手 dv_evader | 0.0 | 0.8 | 0.0 | 47.37 | 5.00 | capture |
