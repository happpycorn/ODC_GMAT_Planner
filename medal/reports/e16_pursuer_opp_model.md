# Tournament e16_pursuer_opp_model

- **rules**: configs/rulesets/ranking_like.json
- **scenario**: mixed
- **games per pairing**: 24
- **seed**: 1

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | dv_evader | rollout_evader | escape_evader | sb3:models/evader.zip | 平均 |
|---|---|---|---|---|---|
| rollout_pursuer | 79% [60–91] | 29% [15–49] | 100% [86–100] | 83% [64–93] | 73% |
| rollout_pursuer(opponents=[{'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | 88% [69–96] | 71% [51–85] | 92% [74–98] | 83% [64–93] | 83% |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | 83% [64–93] | 71% [51–85] | 100% [86–100] | 88% [69–96] | 85% |
| **躲者平均存活** | 17% | 43% | 3% | 15% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| rollout_pursuer | dv_evader | 24 | capture:19, timeout:5 | 0.0 | 2107 / 3000 | 159.6 / 13.1 |
| rollout_pursuer | rollout_evader | 24 | capture:7, timeout:17 | 928.3 | 1347 / 2446 | 197.1 / 316.3 |
| rollout_pursuer | escape_evader | 24 | capture:24 | 0.0 | 2068 / 3000 | 179.1 / 2.2 |
| rollout_pursuer | sb3:models/evader.zip | 24 | capture:20, timeout:4 | 0.0 | 2087 / 3000 | 159.2 / 4.1 |
| rollout_pursuer(opponents=[{'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | dv_evader | 24 | capture:21, timeout:3 | 0.0 | 2187 / 3000 | 1963.7 / 12.7 |
| rollout_pursuer(opponents=[{'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | rollout_evader | 24 | capture:17, timeout:7 | 0.0 | 2149 / 2723 | 2565.0 / 274.9 |
| rollout_pursuer(opponents=[{'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | escape_evader | 24 | capture:22, timeout:2 | 0.0 | 2207 / 3000 | 2254.1 / 2.1 |
| rollout_pursuer(opponents=[{'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | sb3:models/evader.zip | 24 | capture:20, timeout:4 | 0.0 | 2445 / 3000 | 2048.9 / 4.0 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | dv_evader | 24 | capture:20, timeout:4 | 0.0 | 2088 / 3000 | 2044.0 / 12.5 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | rollout_evader | 24 | capture:17, timeout:7 | 0.0 | 1721 / 2771 | 2723.1 / 279.8 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | escape_evader | 24 | capture:24 | 0.0 | 1891 / 3000 | 2315.8 / 2.0 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | sb3:models/evader.zip | 24 | capture:21, timeout:3 | 0.0 | 2216 / 3000 | 2194.7 / 4.2 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 108 | 73% |
| near_coplanar | 144 | 90% |
| wild | 36 | 67% |
