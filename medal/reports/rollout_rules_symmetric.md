# Tournament rollout_rules_symmetric

- **rules**: configs/rulesets/symmetric.json
- **scenario**: mixed
- **games per pairing**: 24
- **seed**: 0

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | dv_evader | rollout_evader | 平均 |
|---|---|---|---|
| lambert_pursuer | 21% [9–40] | 4% [1–20] | 12% |
| rollout_pursuer | 54% [35–72] | 54% [35–72] | 54% |
| **躲者平均存活** | 62% | 71% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | dv_evader | 24 | capture:5, timeout:19 | 933.2 | 2934 / 3000 | 15.3 / 2.7 |
| lambert_pursuer | rollout_evader | 24 | capture:1, timeout:23 | 992.9 | 2943 / 2750 | 15.3 / 110.5 |
| rollout_pursuer | dv_evader | 24 | capture:13, timeout:11 | 0.0 | 1956 / 3000 | 132.4 / 3.5 |
| rollout_pursuer | rollout_evader | 24 | capture:13, timeout:11 | 1.1 | 2554 / 2775 | 124.6 / 121.7 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 40 | 30% |
| near_coplanar | 40 | 40% |
| wild | 16 | 25% |
