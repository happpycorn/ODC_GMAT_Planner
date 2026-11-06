# Tournament verify_lazy3_s3

- **rules**: configs/rulesets/ranking_like.json
- **scenario**: mixed
- **games per pairing**: 12
- **seed**: 3

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | rollout_evader | py:agents.evader_lab:LazyEvader3 | 平均 |
|---|---|---|---|
| lambert_pursuer | 33% [14–61] | 0% [0–24] | 17% |
| rollout_pursuer | 42% [19–68] | 0% [0–24] | 21% |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | 75% [47–91] | 0% [0–24] | 38% |
| **躲者平均存活** | 50% | 100% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | rollout_evader | 12 | capture:4, timeout:8 | 352.5 | 2657 / 2488 | 19.2 / 235.3 |
| lambert_pursuer | py:agents.evader_lab:LazyEvader3 | 12 | timeout:12 | 35.5 | 2450 / 875 | 15.4 / 4.1 |
| rollout_pursuer | rollout_evader | 12 | capture:5, timeout:7 | 177.3 | 1630 / 2688 | 162.3 / 245.8 |
| rollout_pursuer | py:agents.evader_lab:LazyEvader3 | 12 | timeout:12 | 41.0 | 1211 / 688 | 213.0 / 3.5 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | rollout_evader | 12 | capture:9, timeout:3 | 0.0 | 1812 / 2875 | 2518.5 / 231.9 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | py:agents.evader_lab:LazyEvader3 | 12 | timeout:12 | 61.8 | 827 / 458 | 3695.5 / 2.7 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 18 | 17% |
| near_coplanar | 42 | 33% |
| wild | 12 | 8% |
