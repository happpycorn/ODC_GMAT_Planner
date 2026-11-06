# Tournament hap108_robust_pursuer

- **rules**: configs/rulesets/symmetric.json
- **scenario**: mixed
- **games per pairing**: 16
- **seed**: 777

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | rollout_evader | escape_evader | rollout_evader(opponents=[{'name': 'rollout_pursuer', 'candidates': [{'name': 'lambert_pursuer_fast', 'time_weight_mps': 10.0}, {'name': 'lambert_pursuer_fast', 'time_weight_mps': 300.0}], 'opponents': ['dv_evader_fast']}]) | 平均 |
|---|---|---|---|---|
| rollout_pursuer | 56% [33–77] | 19% [7–43] | 12% [3–36] | 29% |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', 'escape_evader']) | 56% [33–77] | 19% [7–43] | 19% [7–43] | 31% |
| **躲者平均存活** | 44% | 81% | 84% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| rollout_pursuer | rollout_evader | 16 | capture:9, timeout:7 | 0.0 | 2199 / 3000 | 170.8 / 123.6 |
| rollout_pursuer | escape_evader | 16 | capture:3, timeout:13 | 922.0 | 1273 / 3000 | 126.6 / 0.6 |
| rollout_pursuer | rollout_evader(opponents=[{'name': 'rollout_pursuer', 'candidates': [{'name': 'lambert_pursuer_fast', 'time_weight_mps': 10.0}, {'name': 'lambert_pursuer_fast', 'time_weight_mps': 300.0}], 'opponents': ['dv_evader_fast']}]) | 16 | capture:2, timeout:14 | 556.1 | 1419 / 3000 | 142.7 / 938.2 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', 'escape_evader']) | rollout_evader | 16 | capture:9, timeout:7 | 1.5 | 1961 / 3000 | 247.2 / 131.4 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', 'escape_evader']) | escape_evader | 16 | capture:3, timeout:13 | 773.1 | 1544 / 3000 | 173.3 / 0.6 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', 'escape_evader']) | rollout_evader(opponents=[{'name': 'rollout_pursuer', 'candidates': [{'name': 'lambert_pursuer_fast', 'time_weight_mps': 10.0}, {'name': 'lambert_pursuer_fast', 'time_weight_mps': 300.0}], 'opponents': ['dv_evader_fast']}]) | 16 | capture:3, timeout:13 | 632.9 | 1193 / 3000 | 195.6 / 963.5 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 24 | 25% |
| near_coplanar | 60 | 37% |
| wild | 12 | 8% |
