# Tournament evader_base_rl_s1

- **rules**: configs/rulesets/ranking_like.json
- **scenario**: mixed
- **games per pairing**: 24
- **seed**: 1

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | rollout_evader | 平均 |
|---|---|---|
| lambert_pursuer | 46% [28–65] | 46% |
| rollout_pursuer | 29% [15–49] | 29% |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | 71% [51–85] | 71% |
| **躲者平均存活** | 51% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | rollout_evader | 24 | capture:11, timeout:13 | 54.6 | 2629 / 2698 | 16.1 / 188.6 |
| rollout_pursuer | rollout_evader | 24 | capture:7, timeout:17 | 928.3 | 1347 / 2446 | 143.7 / 235.3 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | rollout_evader | 24 | capture:17, timeout:7 | 0.0 | 1721 / 2771 | 2047.5 / 210.7 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 27 | 37% |
| near_coplanar | 36 | 67% |
| wild | 9 | 11% |
