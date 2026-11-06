# Tournament evader_screen1_s1

- **rules**: configs/rulesets/ranking_like.json
- **scenario**: mixed
- **games per pairing**: 12
- **seed**: 1

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | py:agents.evader_lab:LazyEvader | py:agents.evader_lab:ReserveRolloutEvader | 平均 |
|---|---|---|---|
| rollout_pursuer | 0% [0–24] | 0% [0–24] | 0% |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | 0% [0–24] | 8% [1–35] | 4% |
| **躲者平均存活** | 100% | 96% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| rollout_pursuer | py:agents.evader_lab:LazyEvader | 12 | timeout:12 | 37.4 | 928 / 625 | 291.9 / 2.7 |
| rollout_pursuer | py:agents.evader_lab:ReserveRolloutEvader | 12 | timeout:12 | 109.7 | 1544 / 2151 | 239.1 / 1159.6 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | py:agents.evader_lab:LazyEvader | 12 | timeout:12 | 20.3 | 1057 / 592 | 4396.1 / 2.6 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | py:agents.evader_lab:ReserveRolloutEvader | 12 | capture:1, timeout:11 | 72.8 | 1398 / 1875 | 3863.9 / 1163.2 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 16 | 0% |
| near_coplanar | 32 | 3% |
