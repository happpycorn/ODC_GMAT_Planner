# Tournament rollout_rules_pursuer_fuel_2x

- **rules**: configs/rulesets/pursuer_fuel_2x.json
- **scenario**: mixed
- **games per pairing**: 24
- **seed**: 0

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | dv_evader | rollout_evader | 平均 |
|---|---|---|---|
| lambert_pursuer | 88% [69–96] | 58% [39–76] | 73% |
| rollout_pursuer | 88% [69–96] | 83% [64–93] | 85% |
| **躲者平均存活** | 12% | 29% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | dv_evader | 24 | capture:21, timeout:3 | 0.0 | 4218 / 3000 | 27.5 / 2.9 |
| lambert_pursuer | rollout_evader | 24 | capture:14, timeout:10 | 0.0 | 5146 / 2900 | 24.6 / 101.8 |
| rollout_pursuer | dv_evader | 24 | capture:21, timeout:3 | 0.0 | 3705 / 3000 | 150.6 / 4.2 |
| rollout_pursuer | rollout_evader | 24 | capture:20, timeout:4 | 0.0 | 3445 / 3000 | 149.9 / 108.2 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 40 | 82% |
| near_coplanar | 40 | 95% |
| wild | 16 | 31% |
