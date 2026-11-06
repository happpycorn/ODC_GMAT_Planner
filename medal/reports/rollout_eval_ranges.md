# Tournament rollout_eval_ranges

- **rules**: ranges
- **scenario**: mixed
- **games per pairing**: 40
- **seed**: 0

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | coast | dv_evader | rollout_evader | 平均 |
|---|---|---|---|---|
| lambert_pursuer | 72% [57–84] | 38% [24–53] | 25% [14–40] | 45% |
| rollout_pursuer | 82% [68–91] | 57% [42–71] | 35% [22–50] | 58% |
| **躲者平均存活** | 23% | 52% | 70% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | coast | 40 | capture:29, timeout:11 | 1.3 | 966 / 0 | 5.6 / 0.0 |
| lambert_pursuer | dv_evader | 40 | capture:15, timeout:25 | 233.7 | 1580 / 1525 | 4.5 / 11.2 |
| lambert_pursuer | rollout_evader | 40 | capture:10, timeout:30 | 271.6 | 1737 / 1083 | 4.3 / 132.9 |
| rollout_pursuer | coast | 40 | capture:33, timeout:7 | 0.0 | 623 / 0 | 205.1 / 0.0 |
| rollout_pursuer | dv_evader | 40 | capture:23, timeout:17 | 2.5 | 1126 / 1525 | 99.3 / 10.9 |
| rollout_pursuer | rollout_evader | 40 | capture:14, timeout:26 | 133.0 | 1263 / 1074 | 121.8 / 154.6 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 72 | 44% |
| near_coplanar | 120 | 70% |
| wild | 48 | 17% |
