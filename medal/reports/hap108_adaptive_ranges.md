# Tournament hap108_adaptive_ranges

- **rules**: ranges
- **scenario**: mixed
- **games per pairing**: 40
- **seed**: 2026

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | rollout_evader | escape_evader | adaptive_evader(threshold=0.5) | adaptive_evader | adaptive_evader(threshold=1.0) | 平均 |
|---|---|---|---|---|---|---|
| lambert_pursuer | 30% [18–45] | 52% [37–67] | 45% [31–60] | 40% [26–55] | 38% [24–53] | 41% |
| rollout_pursuer | 50% [35–65] | 72% [57–84] | 68% [52–80] | 68% [52–80] | 65% [50–78] | 64% |
| **躲者平均存活** | 60% | 38% | 44% | 46% | 49% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | rollout_evader | 40 | capture:12, crash_pursuer:4, timeout:24 | 181.3 | 1507 / 1128 | 24.0 / 151.3 |
| lambert_pursuer | escape_evader | 40 | capture:21, timeout:19 | 14.5 | 1209 / 1231 | 28.7 / 1.7 |
| lambert_pursuer | adaptive_evader(threshold=0.5) | 40 | capture:18, crash_pursuer:2, timeout:20 | 50.8 | 1325 / 1229 | 8.3 / 42.8 |
| lambert_pursuer | adaptive_evader | 40 | capture:16, crash_pursuer:3, timeout:21 | 86.8 | 1360 / 1223 | 8.1 / 84.6 |
| lambert_pursuer | adaptive_evader(threshold=1.0) | 40 | capture:15, crash_pursuer:4, timeout:21 | 149.6 | 1498 / 1170 | 8.2 / 122.9 |
| rollout_pursuer | rollout_evader | 40 | capture:20, timeout:20 | 16.8 | 877 / 1032 | 147.0 / 161.0 |
| rollout_pursuer | escape_evader | 40 | capture:29, timeout:11 | 0.0 | 1169 / 1231 | 117.0 / 1.6 |
| rollout_pursuer | adaptive_evader(threshold=0.5) | 40 | capture:27, timeout:13 | 0.0 | 1004 / 1229 | 120.0 / 41.6 |
| rollout_pursuer | adaptive_evader | 40 | capture:27, timeout:13 | 0.0 | 923 / 1229 | 134.4 / 84.7 |
| rollout_pursuer | adaptive_evader(threshold=1.0) | 40 | capture:26, timeout:14 | 0.0 | 924 / 1058 | 147.2 / 130.0 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 120 | 48% |
| near_coplanar | 250 | 60% |
| wild | 30 | 10% |
