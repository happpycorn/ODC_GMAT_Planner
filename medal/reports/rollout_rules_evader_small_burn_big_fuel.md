# Tournament rollout_rules_evader_small_burn_big_fuel

- **rules**: configs/rulesets/evader_small_burn_big_fuel.json
- **scenario**: mixed
- **games per pairing**: 24
- **seed**: 0

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | dv_evader | rollout_evader | 平均 |
|---|---|---|---|
| lambert_pursuer | 8% [2–26] | 8% [2–26] | 8% |
| rollout_pursuer | 42% [24–61] | 33% [18–53] | 38% |
| **躲者平均存活** | 75% | 79% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | dv_evader | 24 | capture:2, timeout:22 | 784.9 | 2927 / 2894 | 12.7 / 17.3 |
| lambert_pursuer | rollout_evader | 24 | capture:2, timeout:22 | 25.3 | 2924 / 1959 | 23.8 / 346.5 |
| rollout_pursuer | dv_evader | 24 | capture:10, timeout:14 | 128.3 | 2528 / 2431 | 249.5 / 20.9 |
| rollout_pursuer | rollout_evader | 24 | capture:8, timeout:16 | 15.3 | 2147 / 1305 | 275.0 / 366.9 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 40 | 12% |
| near_coplanar | 40 | 42% |
| wild | 16 | 0% |
