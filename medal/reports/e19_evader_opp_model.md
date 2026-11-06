# Tournament e19_evader_opp_model

- **rules**: configs/rulesets/ranking_like.json
- **scenario**: mixed
- **games per pairing**: 24
- **seed**: 1

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | rollout_evader | rollout_evader(opponents=['lambert_pursuer_fast', {'name': 'lambert_pursuer_fast', 'time_weight_mps': 60.0}, {'name': 'rollout_pursuer', 'candidates': [{'name': 'lambert_pursuer_fast', 'time_weight_mps': 10.0}, {'name': 'lambert_pursuer_fast', 'time_weight_mps': 300.0}], 'opponents': ['dv_evader_fast']}]) | 平均 |
|---|---|---|---|
| lambert_pursuer | 46% [28–65] | 46% [28–65] | 46% |
| rollout_pursuer | 29% [15–49] | 62% [43–79] | 46% |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | 71% [51–85] | 67% [47–82] | 69% |
| **躲者平均存活** | 51% | 42% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | rollout_evader | 24 | capture:11, timeout:13 | 54.6 | 2629 / 2698 | 37.5 / 259.6 |
| lambert_pursuer | rollout_evader(opponents=['lambert_pursuer_fast', {'name': 'lambert_pursuer_fast', 'time_weight_mps': 60.0}, {'name': 'rollout_pursuer', 'candidates': [{'name': 'lambert_pursuer_fast', 'time_weight_mps': 10.0}, {'name': 'lambert_pursuer_fast', 'time_weight_mps': 300.0}], 'opponents': ['dv_evader_fast']}]) | 24 | capture:11, timeout:13 | 48.2 | 2680 / 2867 | 36.2 / 2130.3 |
| rollout_pursuer | rollout_evader | 24 | capture:7, timeout:17 | 928.3 | 1347 / 2446 | 208.3 / 322.4 |
| rollout_pursuer | rollout_evader(opponents=['lambert_pursuer_fast', {'name': 'lambert_pursuer_fast', 'time_weight_mps': 60.0}, {'name': 'rollout_pursuer', 'candidates': [{'name': 'lambert_pursuer_fast', 'time_weight_mps': 10.0}, {'name': 'lambert_pursuer_fast', 'time_weight_mps': 300.0}], 'opponents': ['dv_evader_fast']}]) | 24 | capture:15, timeout:9 | 0.0 | 2131 / 2973 | 187.5 / 2290.5 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | rollout_evader | 24 | capture:17, timeout:7 | 0.0 | 1721 / 2771 | 2745.7 / 279.4 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | rollout_evader(opponents=['lambert_pursuer_fast', {'name': 'lambert_pursuer_fast', 'time_weight_mps': 60.0}, {'name': 'rollout_pursuer', 'candidates': [{'name': 'lambert_pursuer_fast', 'time_weight_mps': 10.0}, {'name': 'lambert_pursuer_fast', 'time_weight_mps': 300.0}], 'opponents': ['dv_evader_fast']}]) | 24 | capture:16, timeout:8 | 0.0 | 2010 / 2983 | 2427.9 / 2345.9 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 54 | 35% |
| near_coplanar | 72 | 78% |
| wild | 18 | 11% |
