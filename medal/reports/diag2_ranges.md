# Tournament diag2_ranges

- **rules**: ranges
- **scenario**: mixed
- **games per pairing**: 60
- **seed**: 0

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | coast | random | dv_evader | minimax_evader_fast | 平均 |
|---|---|---|---|---|---|
| lambert_pursuer | 73% [61–83] | 67% [54–77] | 42% [30–54] | 35% [24–48] | 54% |
| minimax_pursuer | 58% [46–70] | 65% [52–76] | 32% [21–44] | 37% [26–49] | 48% |
| **躲者平均存活** | 34% | 34% | 63% | 64% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | coast | 60 | capture:44, timeout:16 | 0.3 | 893 / 0 | 28.8 / 0.0 |
| lambert_pursuer | random | 60 | capture:26, crash_evader:14, timeout:20 | 15.2 | 1082 / 730 | 42.0 / 0.0 |
| lambert_pursuer | dv_evader | 60 | capture:25, timeout:35 | 218.5 | 1496 / 1471 | 31.9 / 16.1 |
| lambert_pursuer | minimax_evader_fast | 60 | capture:21, crash_pursuer:1, timeout:38 | 218.5 | 1498 / 1471 | 19.8 / 21.3 |
| minimax_pursuer | coast | 60 | capture:35, crash_pursuer:1, timeout:24 | 5.1 | 1055 / 0 | 38.5 / 0.0 |
| minimax_pursuer | random | 60 | capture:24, crash_evader:15, timeout:21 | 51.0 | 1018 / 834 | 40.6 / 0.0 |
| minimax_pursuer | dv_evader | 60 | capture:19, timeout:41 | 365.6 | 1689 / 1463 | 27.9 / 15.9 |
| minimax_pursuer | minimax_evader_fast | 60 | capture:22, timeout:38 | 401.9 | 1523 / 1471 | 26.2 / 24.4 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 160 | 38% |
| near_coplanar | 232 | 74% |
| wild | 88 | 15% |
