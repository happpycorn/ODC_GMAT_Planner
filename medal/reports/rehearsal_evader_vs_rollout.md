# 當天流程彩排 rehearsal_evader_vs_rollout

- 我方 evader、對手 `rollout_pursuer`、規則 `default`、幾何 `near_coplanar`、seed 0、推演 開
- 結局：**timeout**（我方勝），78 回合，t = 23323 s，最近距離 26.56 km
- 最終距離：引擎 18390.0746 km / GMAT 18390.1278 km
- 匯入狀態 vs 引擎最大差：83.94 m
- 我方決策耗時：平均 3.9 s、最長 14.0 s；GMAT 重播每回合平均 0.6 s
- 總耗時 208 s

| 回合 | 方 | 決策者 | |Δv| m/s | GMAT s | 決策 s | 匯入差 m | 距離 km | 事件 |
|---|---|---|---|---|---|---|---|---|
| 0 | pursuer | 對手 rollout_pursuer | 303.2 | 0.0 | 6.2 | 0.00 | 26.56 |  |
| 1 | evader | 我方 escape_evader | 1500.0 | 0.2 | 14.0 | 0.04 | 457.48 |  |
| 2 | pursuer | 對手 rollout_pursuer | 0.0 | 0.2 | 0.2 | 0.15 | 987.34 |  |
| 3 | evader | 我方 sb3:/home/corn/ODC_GMAT_DRL/models/evader.zip | 1500.0 | 0.2 | 9.5 | 0.29 | 1906.34 |  |
| 4 | pursuer | 對手 rollout_pursuer | 0.0 | 0.2 | 0.1 | 0.46 | 3123.81 |  |
| 5 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.2 | 11.4 | 0.66 | 4674.30 |  |
| 6 | pursuer | 對手 rollout_pursuer | 0.0 | 0.2 | 0.1 | 0.94 | 6552.33 |  |
| 7 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.2 | 10.9 | 1.32 | 8717.39 |  |
| 8 | pursuer | 對手 rollout_pursuer | 0.0 | 0.3 | 0.1 | 1.79 | 11111.56 |  |
| 9 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.3 | 8.2 | 2.34 | 13670.25 |  |
| 10 | pursuer | 對手 rollout_pursuer | 0.0 | 0.3 | 0.1 | 2.92 | 16327.03 |  |
| 11 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.3 | 7.7 | 3.52 | 19015.21 |  |
| 12 | pursuer | 對手 rollout_pursuer | 93.8 | 0.3 | 0.1 | 4.11 | 21651.78 |  |
| 13 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.3 | 7.1 | 4.66 | 24183.26 |  |
| 14 | pursuer | 對手 rollout_pursuer | 46.9 | 0.3 | 0.1 | 5.17 | 26537.75 |  |
| 15 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.3 | 6.7 | 5.62 | 28651.92 |  |
| 16 | pursuer | 對手 rollout_pursuer | 0.0 | 0.3 | 0.1 | 6.03 | 30456.27 |  |
| 17 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.3 | 6.4 | 6.37 | 31879.95 |  |
| 18 | pursuer | 對手 rollout_pursuer | 11.7 | 0.3 | 0.1 | 6.66 | 32855.06 |  |
| 19 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.4 | 5.9 | 6.88 | 33325.05 |  |
| 20 | pursuer | 對手 rollout_pursuer | 0.0 | 0.4 | 0.1 | 7.03 | 33258.68 |  |
| 21 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.4 | 5.5 | 7.13 | 32666.85 |  |
| 22 | pursuer | 對手 rollout_pursuer | 1500.0 | 0.4 | 0.1 | 7.21 | 31379.08 |  |
| 23 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.4 | 5.1 | 7.32 | 29865.48 |  |
| 24 | pursuer | 對手 rollout_pursuer | 1044.5 | 0.4 | 0.1 | 7.52 | 28141.57 |  |
| 25 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.4 | 4.5 | 7.88 | 26530.67 |  |
| 26 | pursuer | 對手 rollout_pursuer | 0.0 | 0.4 | 0.0 | 8.41 | 25074.10 |  |
| 27 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.4 | 4.3 | 9.12 | 23772.99 |  |
| 28 | pursuer | 對手 rollout_pursuer | 0.0 | 0.4 | 0.0 | 9.96 | 22614.76 |  |
| 29 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.5 | 4.1 | 10.91 | 21583.94 |  |
| 30 | pursuer | 對手 rollout_pursuer | 0.0 | 0.5 | 0.0 | 11.95 | 20665.92 |  |
| 31 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.5 | 3.9 | 13.04 | 19847.97 |  |
| 32 | pursuer | 對手 rollout_pursuer | 0.0 | 0.5 | 0.0 | 14.18 | 19119.28 |  |
| 33 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.5 | 3.7 | 15.36 | 18470.75 |  |
| 34 | pursuer | 對手 rollout_pursuer | 0.0 | 0.5 | 0.0 | 16.57 | 17894.64 |  |
| 35 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.5 | 3.4 | 17.81 | 17384.35 |  |
| 36 | pursuer | 對手 rollout_pursuer | 0.0 | 0.5 | 0.0 | 19.07 | 16934.16 |  |
| 37 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.5 | 3.2 | 20.34 | 16539.07 |  |
| 38 | pursuer | 對手 rollout_pursuer | 0.0 | 0.6 | 0.0 | 21.64 | 16194.64 |  |
| 39 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.6 | 2.9 | 22.95 | 15896.86 |  |
| 40 | pursuer | 對手 rollout_pursuer | 0.0 | 0.6 | 0.0 | 24.27 | 15642.11 |  |
| 41 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.6 | 2.7 | 25.61 | 15427.04 |  |
| 42 | pursuer | 對手 rollout_pursuer | 0.0 | 0.6 | 0.0 | 26.96 | 15248.57 |  |
| 43 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.6 | 2.6 | 28.33 | 15103.83 |  |
| 44 | pursuer | 對手 rollout_pursuer | 0.0 | 0.6 | 0.0 | 29.70 | 14990.13 |  |
| 45 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.6 | 2.3 | 31.09 | 14904.97 |  |
| 46 | pursuer | 對手 rollout_pursuer | 0.0 | 0.6 | 0.0 | 32.49 | 14845.96 |  |
| 47 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.6 | 2.2 | 33.90 | 14810.92 |  |
| 48 | pursuer | 對手 rollout_pursuer | 0.0 | 0.7 | 0.0 | 35.33 | 14797.75 |  |
| 49 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.7 | 2.0 | 36.76 | 14804.53 |  |
| 50 | pursuer | 對手 rollout_pursuer | 0.0 | 0.7 | 0.0 | 38.21 | 14829.43 |  |
| 51 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.7 | 1.8 | 39.68 | 14870.78 |  |
| 52 | pursuer | 對手 rollout_pursuer | 0.0 | 0.7 | 0.0 | 41.15 | 14927.00 |  |
| 53 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.7 | 1.5 | 42.64 | 14996.65 |  |
| 54 | pursuer | 對手 rollout_pursuer | 0.0 | 0.7 | 0.0 | 44.15 | 15078.39 |  |
| 55 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.7 | 1.4 | 45.67 | 15170.97 |  |
| 56 | pursuer | 對手 rollout_pursuer | 0.0 | 0.7 | 0.0 | 47.20 | 15273.27 |  |
| 57 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.8 | 1.3 | 48.75 | 15384.23 |  |
| 58 | pursuer | 對手 rollout_pursuer | 0.0 | 0.7 | 0.0 | 50.32 | 15502.92 |  |
| 59 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.8 | 1.1 | 51.90 | 15628.45 |  |
| 60 | pursuer | 對手 rollout_pursuer | 0.0 | 0.8 | 0.0 | 53.50 | 15760.04 |  |
| 61 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.8 | 0.9 | 55.11 | 15896.97 |  |
| 62 | pursuer | 對手 rollout_pursuer | 0.0 | 0.8 | 0.0 | 56.75 | 16038.57 |  |
| 63 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.8 | 0.8 | 58.40 | 16184.26 |  |
| 64 | pursuer | 對手 rollout_pursuer | 0.0 | 0.8 | 0.0 | 60.07 | 16333.50 |  |
| 65 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.8 | 0.7 | 61.77 | 16485.81 |  |
| 66 | pursuer | 對手 rollout_pursuer | 0.0 | 0.8 | 0.0 | 63.48 | 16640.76 |  |
| 67 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.8 | 0.5 | 65.22 | 16797.94 |  |
| 68 | pursuer | 對手 rollout_pursuer | 0.0 | 0.8 | 0.0 | 66.97 | 16957.02 |  |
| 69 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.9 | 0.4 | 68.75 | 17117.67 |  |
| 70 | pursuer | 對手 rollout_pursuer | 0.0 | 0.9 | 0.0 | 70.56 | 17279.62 |  |
| 71 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.9 | 0.3 | 72.39 | 17442.63 |  |
| 72 | pursuer | 對手 rollout_pursuer | 0.0 | 0.9 | 0.0 | 74.24 | 17606.47 |  |
| 73 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.9 | 0.2 | 76.13 | 17770.95 |  |
| 74 | pursuer | 對手 rollout_pursuer | 0.0 | 0.9 | 0.0 | 78.03 | 17935.91 |  |
| 75 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.9 | 0.1 | 79.97 | 18101.21 |  |
| 76 | pursuer | 對手 rollout_pursuer | 0.0 | 1.0 | 0.0 | 81.94 | 18266.72 |  |
| 77 | evader | 我方 {'name': 'rollout_evader', 'workers': 8} | 0.0 | 0.9 | 0.0 | 83.94 | 18390.07 | timeout |
