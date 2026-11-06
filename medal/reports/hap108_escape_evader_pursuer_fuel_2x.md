# Tournament hap108_escape_evader_pursuer_fuel_2x

- **rules**: configs/rulesets/pursuer_fuel_2x.json
- **scenario**: mixed
- **games per pairing**: 16
- **seed**: 777

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | rollout_evader | escape_evader | rollout_evader(candidates=['dv_evader', 'dv_evader_fast', 'escape_evader']) | 平均 |
|---|---|---|---|---|
| lambert_pursuer | 50% [28–72] | 81% [57–93] | 50% [28–72] | 60% |
| rollout_pursuer | 88% [64–97] | 94% [72–99] | 88% [64–97] | 90% |
| **躲者平均存活** | 31% | 12% | 31% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | rollout_evader | 16 | capture:8, timeout:8 | 21.5 | 4810 / 3000 | 37.6 / 101.9 |
| lambert_pursuer | escape_evader | 16 | capture:13, timeout:3 | 0.0 | 4596 / 3000 | 43.7 / 0.8 |
| lambert_pursuer | rollout_evader(candidates=['dv_evader', 'dv_evader_fast', 'escape_evader']) | 16 | capture:8, timeout:8 | 21.5 | 4810 / 3000 | 37.7 / 103.3 |
| rollout_pursuer | rollout_evader | 16 | capture:14, timeout:2 | 0.0 | 3844 / 2906 | 197.3 / 136.6 |
| rollout_pursuer | escape_evader | 16 | capture:15, timeout:1 | 0.0 | 4377 / 3000 | 233.6 / 0.7 |
| rollout_pursuer | rollout_evader(candidates=['dv_evader', 'dv_evader_fast', 'escape_evader']) | 16 | capture:14, timeout:2 | 0.0 | 3996 / 2906 | 242.4 / 137.6 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 24 | 79% |
| near_coplanar | 60 | 85% |
| wild | 12 | 17% |
