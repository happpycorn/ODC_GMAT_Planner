# Tournament hap105_pursuer

- **rules**: configs/rulesets/symmetric.json
- **scenario**: mixed
- **games per pairing**: 24
- **seed**: 0

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | dv_evader | rollout_evader | sb3:models/evader.zip | 平均 |
|---|---|---|---|---|
| rollout_pursuer | 54% [35–72] | 54% [35–72] | 62% [43–79] | 57% |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', 'sb3:models/evader.zip']) | 50% [31–69] | 46% [28–65] | 71% [51–85] | 56% |
| rollout_pursuer(candidates=[{'name': 'lambert_pursuer', 'time_weight_mps': 0.0}, {'name': 'lambert_pursuer', 'time_weight_mps': 10.0}, {'name': 'lambert_pursuer', 'time_weight_mps': 60.0}, {'name': 'lambert_pursuer', 'time_weight_mps': 300.0}, 'sb3:models/pursuer.zip']) | 58% [39–76] | 50% [31–69] | 67% [47–82] | 58% |
| sb3:models/pursuer.zip | 8% [2–26] | 0% [0–14] | 12% [4–31] | 7% |
| **躲者平均存活** | 57% | 62% | 47% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| rollout_pursuer | dv_evader | 24 | capture:13, timeout:11 | 0.0 | 1956 / 3000 | 136.9 / 3.7 |
| rollout_pursuer | rollout_evader | 24 | capture:13, timeout:11 | 1.1 | 2554 / 2775 | 134.2 / 130.8 |
| rollout_pursuer | sb3:models/evader.zip | 24 | capture:15, timeout:9 | 0.0 | 2287 / 3000 | 140.2 / 4.3 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', 'sb3:models/evader.zip']) | dv_evader | 24 | capture:12, timeout:12 | 235.8 | 1937 / 3000 | 316.7 / 3.7 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', 'sb3:models/evader.zip']) | rollout_evader | 24 | capture:11, timeout:13 | 242.4 | 2475 / 2838 | 312.5 / 132.3 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', 'sb3:models/evader.zip']) | sb3:models/evader.zip | 24 | capture:17, timeout:7 | 0.0 | 2153 / 3000 | 337.9 / 3.9 |
| rollout_pursuer(candidates=[{'name': 'lambert_pursuer', 'time_weight_mps': 0.0}, {'name': 'lambert_pursuer', 'time_weight_mps': 10.0}, {'name': 'lambert_pursuer', 'time_weight_mps': 60.0}, {'name': 'lambert_pursuer', 'time_weight_mps': 300.0}, 'sb3:models/pursuer.zip']) | dv_evader | 24 | capture:14, timeout:10 | 0.0 | 1900 / 3000 | 160.2 / 3.3 |
| rollout_pursuer(candidates=[{'name': 'lambert_pursuer', 'time_weight_mps': 0.0}, {'name': 'lambert_pursuer', 'time_weight_mps': 10.0}, {'name': 'lambert_pursuer', 'time_weight_mps': 60.0}, {'name': 'lambert_pursuer', 'time_weight_mps': 300.0}, 'sb3:models/pursuer.zip']) | rollout_evader | 24 | capture:12, timeout:12 | 12.8 | 2609 / 2725 | 167.9 / 130.1 |
| rollout_pursuer(candidates=[{'name': 'lambert_pursuer', 'time_weight_mps': 0.0}, {'name': 'lambert_pursuer', 'time_weight_mps': 10.0}, {'name': 'lambert_pursuer', 'time_weight_mps': 60.0}, {'name': 'lambert_pursuer', 'time_weight_mps': 300.0}, 'sb3:models/pursuer.zip']) | sb3:models/evader.zip | 24 | capture:16, timeout:8 | 0.0 | 2437 / 3000 | 173.8 / 4.4 |
| sb3:models/pursuer.zip | dv_evader | 24 | capture:2, timeout:22 | 1198.5 | 2923 / 3000 | 18.5 / 2.6 |
| sb3:models/pursuer.zip | rollout_evader | 24 | timeout:24 | 1020.9 | 3000 / 2875 | 19.1 / 114.1 |
| sb3:models/pursuer.zip | sb3:models/evader.zip | 24 | capture:3, timeout:21 | 1439.9 | 2887 / 3000 | 18.4 / 3.7 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 120 | 42% |
| near_coplanar | 120 | 56% |
| wild | 48 | 23% |
