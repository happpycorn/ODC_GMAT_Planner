# Tournament hap105_evader

- **rules**: configs/rulesets/symmetric.json
- **scenario**: mixed
- **games per pairing**: 24
- **seed**: 0

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | rollout_evader | rollout_evader(candidates=['dv_evader', 'dv_evader_fast', 'sb3:models/evader.zip']) | rollout_evader(opponents=['lambert_pursuer_fast', {'name': 'lambert_pursuer_fast', 'time_weight_mps': 60.0}, 'sb3:models/pursuer.zip']) | sb3:models/evader.zip | 平均 |
|---|---|---|---|---|---|
| lambert_pursuer | 4% [1–20] | 4% [1–20] | 17% [7–36] | 17% [7–36] | 10% |
| rollout_pursuer | 54% [35–72] | 54% [35–72] | 50% [31–69] | 62% [43–79] | 55% |
| sb3:models/pursuer.zip | 0% [0–14] | 8% [2–26] | 4% [1–20] | 12% [4–31] | 6% |
| **躲者平均存活** | 81% | 78% | 76% | 69% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | rollout_evader | 24 | capture:1, timeout:23 | 992.9 | 2943 / 2750 | 15.1 / 115.7 |
| lambert_pursuer | rollout_evader(candidates=['dv_evader', 'dv_evader_fast', 'sb3:models/evader.zip']) | 24 | capture:1, timeout:23 | 992.9 | 2943 / 2750 | 16.2 / 146.0 |
| lambert_pursuer | rollout_evader(opponents=['lambert_pursuer_fast', {'name': 'lambert_pursuer_fast', 'time_weight_mps': 60.0}, 'sb3:models/pursuer.zip']) | 24 | capture:4, timeout:20 | 1029.5 | 2917 / 2875 | 16.1 / 264.3 |
| lambert_pursuer | sb3:models/evader.zip | 24 | capture:4, timeout:20 | 1669.2 | 2844 / 3000 | 15.6 / 3.9 |
| rollout_pursuer | rollout_evader | 24 | capture:13, timeout:11 | 1.1 | 2554 / 2775 | 132.3 / 129.0 |
| rollout_pursuer | rollout_evader(candidates=['dv_evader', 'dv_evader_fast', 'sb3:models/evader.zip']) | 24 | capture:13, timeout:11 | 1.1 | 2483 / 2775 | 133.8 / 159.1 |
| rollout_pursuer | rollout_evader(opponents=['lambert_pursuer_fast', {'name': 'lambert_pursuer_fast', 'time_weight_mps': 60.0}, 'sb3:models/pursuer.zip']) | 24 | capture:12, timeout:12 | 235.2 | 2053 / 2900 | 133.2 / 302.3 |
| rollout_pursuer | sb3:models/evader.zip | 24 | capture:15, timeout:9 | 0.0 | 2287 / 3000 | 138.5 / 4.2 |
| sb3:models/pursuer.zip | rollout_evader | 24 | timeout:24 | 1020.9 | 3000 / 2875 | 18.9 / 113.8 |
| sb3:models/pursuer.zip | rollout_evader(candidates=['dv_evader', 'dv_evader_fast', 'sb3:models/evader.zip']) | 24 | capture:2, timeout:22 | 1239.6 | 2927 / 2875 | 30.8 / 143.7 |
| sb3:models/pursuer.zip | rollout_evader(opponents=['lambert_pursuer_fast', {'name': 'lambert_pursuer_fast', 'time_weight_mps': 60.0}, 'sb3:models/pursuer.zip']) | 24 | capture:1, timeout:23 | 1239.6 | 2999 / 2875 | 18.6 / 267.0 |
| sb3:models/pursuer.zip | sb3:models/evader.zip | 24 | capture:3, timeout:21 | 1439.9 | 2887 / 3000 | 18.6 / 3.6 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 120 | 20% |
| near_coplanar | 120 | 33% |
| wild | 48 | 10% |
