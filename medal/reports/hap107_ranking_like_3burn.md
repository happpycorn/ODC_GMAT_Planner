# Tournament hap107_ranking_like_3burn

- **rules**: configs/rulesets/ranking_like_3burn.json
- **scenario**: mixed
- **games per pairing**: 24
- **seed**: 1

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | dv_evader | rollout_evader | escape_evader | 平均 |
|---|---|---|---|---|
| lambert_pursuer | 46% [28–65] | 33% [18–53] | 50% [31–69] | 43% |
| rollout_pursuer | 96% [80–99] | 75% [55–88] | 96% [80–99] | 89% |
| **躲者平均存活** | 29% | 46% | 27% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | dv_evader | 24 | capture:11, timeout:13 | 46.6 | 2803 / 3000 | 20.3 / 17.1 |
| lambert_pursuer | rollout_evader | 24 | capture:8, timeout:16 | 426.3 | 2702 / 2906 | 19.2 / 1070.5 |
| lambert_pursuer | escape_evader | 24 | capture:12, timeout:12 | 28.8 | 2602 / 3000 | 20.3 / 3.9 |
| rollout_pursuer | dv_evader | 24 | capture:23, timeout:1 | 0.0 | 2085 / 3000 | 993.7 / 18.0 |
| rollout_pursuer | rollout_evader | 24 | capture:18, timeout:6 | 0.0 | 2111 / 2854 | 1031.9 / 1176.4 |
| rollout_pursuer | escape_evader | 24 | capture:23, timeout:1 | 0.0 | 2106 / 3000 | 1081.0 / 4.1 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 54 | 46% |
| near_coplanar | 72 | 90% |
| wild | 18 | 28% |
