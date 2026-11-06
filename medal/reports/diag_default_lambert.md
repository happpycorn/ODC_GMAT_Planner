# Tournament diag_default_lambert

- **rules**: default
- **scenario**: mixed
- **games per pairing**: 60
- **seed**: 0

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | coast | random | dv_evader | 平均 |
|---|---|---|---|---|
| lambert_pursuer | 83% [72–91] | 93% [84–97] | 25% [16–37] | 67% |
| **躲者平均存活** | 17% | 7% | 75% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | coast | 60 | capture:50, crash_pursuer:1, timeout:9 | 0.0 | 904 / 0 | 42.2 / 0.0 |
| lambert_pursuer | random | 60 | capture:19, crash_evader:37, timeout:4 | 559.8 | 1990 / 2123 | 74.4 / 0.0 |
| lambert_pursuer | dv_evader | 60 | capture:15, crash_pursuer:25, timeout:20 | 724.3 | 2358 / 3000 | 27.8 / 4.3 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 72 | 75% |
| near_coplanar | 78 | 72% |
| wild | 30 | 37% |
