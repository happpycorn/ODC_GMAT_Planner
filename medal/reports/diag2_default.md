# Tournament diag2_default

- **rules**: default
- **scenario**: mixed
- **games per pairing**: 60
- **seed**: 0

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | coast | random | dv_evader | minimax_evader_fast | 平均 |
|---|---|---|---|---|---|
| lambert_pursuer | 92% [82–96] | 93% [84–97] | 22% [13–34] | 28% [19–41] | 59% |
| minimax_pursuer | 27% [17–39] | 80% [68–88] | 8% [4–18] | 10% [5–20] | 31% |
| **躲者平均存活** | 41% | 13% | 85% | 81% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | coast | 60 | capture:55, timeout:5 | 0.0 | 901 / 0 | 22.2 / 0.0 |
| lambert_pursuer | random | 60 | capture:19, crash_evader:37, timeout:4 | 559.8 | 1999 / 2123 | 50.9 / 0.0 |
| lambert_pursuer | dv_evader | 60 | capture:13, timeout:47 | 786.5 | 2909 / 3000 | 13.6 / 2.9 |
| lambert_pursuer | minimax_evader_fast | 60 | capture:17, timeout:43 | 730.4 | 2793 / 3000 | 15.6 / 7.2 |
| minimax_pursuer | coast | 60 | capture:16, timeout:44 | 801.5 | 2413 / 0 | 35.6 / 0.0 |
| minimax_pursuer | random | 60 | capture:9, crash_evader:39, timeout:12 | 1131.1 | 2174 / 2277 | 56.7 / 0.0 |
| minimax_pursuer | dv_evader | 60 | capture:5, timeout:55 | 1605.6 | 2941 / 3000 | 22.2 / 3.5 |
| minimax_pursuer | minimax_evader_fast | 60 | capture:6, timeout:54 | 1320.3 | 2838 / 2900 | 20.6 / 8.1 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 192 | 44% |
| near_coplanar | 208 | 50% |
| wild | 80 | 34% |
