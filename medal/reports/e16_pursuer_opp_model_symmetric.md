# Tournament e16_pursuer_opp_model_symmetric

- **rules**: configs/rulesets/symmetric.json
- **scenario**: mixed
- **games per pairing**: 24
- **seed**: 1

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | dv_evader | rollout_evader | escape_evader | sb3:models/evader.zip | 平均 |
|---|---|---|---|---|---|
| rollout_pursuer | 33% [18–53] | 58% [39–76] | 21% [9–40] | 50% [31–69] | 41% |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | 29% [15–49] | 46% [28–65] | 12% [4–31] | 50% [31–69] | 34% |
| **躲者平均存活** | 69% | 48% | 83% | 50% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| rollout_pursuer | dv_evader | 24 | capture:8, timeout:16 | 520.3 | 1551 / 3000 | 124.7 / 2.3 |
| rollout_pursuer | rollout_evader | 24 | capture:14, timeout:10 | 0.0 | 1887 / 2875 | 149.3 / 119.9 |
| rollout_pursuer | escape_evader | 24 | capture:5, timeout:19 | 1258.1 | 1322 / 3000 | 118.6 / 0.8 |
| rollout_pursuer | sb3:models/evader.zip | 24 | capture:12, timeout:12 | 182.0 | 1796 / 3000 | 131.7 / 4.4 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | dv_evader | 24 | capture:7, timeout:17 | 596.5 | 1354 / 3000 | 976.1 / 2.3 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | rollout_evader | 24 | capture:11, timeout:13 | 114.6 | 1725 / 2938 | 1287.0 / 105.7 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | escape_evader | 24 | capture:3, timeout:21 | 1258.1 | 1116 / 3000 | 909.7 / 0.7 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | sb3:models/evader.zip | 24 | capture:12, timeout:12 | 182.0 | 1847 / 3000 | 1058.4 / 4.3 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 72 | 18% |
| near_coplanar | 96 | 59% |
| wild | 24 | 8% |
