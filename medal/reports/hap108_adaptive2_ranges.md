# Tournament hap108_adaptive2_ranges

- **rules**: ranges
- **scenario**: mixed
- **games per pairing**: 40
- **seed**: 2026

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | rollout_evader | adaptive_evader | 平均 |
|---|---|---|---|
| lambert_pursuer | 30% [18–45] | 38% [24–53] | 34% |
| rollout_pursuer | 50% [35–65] | 62% [47–76] | 56% |
| **躲者平均存活** | 60% | 50% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | rollout_evader | 40 | capture:12, crash_pursuer:4, timeout:24 | 181.3 | 1507 / 1128 | 26.4 / 151.2 |
| lambert_pursuer | adaptive_evader | 40 | capture:15, crash_pursuer:4, timeout:21 | 169.9 | 1498 / 1167 | 31.5 / 130.8 |
| rollout_pursuer | rollout_evader | 40 | capture:20, timeout:20 | 16.8 | 877 / 1032 | 165.1 / 159.5 |
| rollout_pursuer | adaptive_evader | 40 | capture:25, timeout:15 | 0.0 | 936 / 1066 | 165.0 / 133.4 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 48 | 46% |
| near_coplanar | 100 | 49% |
| wild | 12 | 8% |
