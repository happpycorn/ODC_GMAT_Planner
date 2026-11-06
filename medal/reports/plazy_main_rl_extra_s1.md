# Tournament plazy_main_rl_extra_s1

- **rules**: configs/rulesets/ranking_like.json
- **scenario**: mixed
- **games per pairing**: 12
- **seed**: 1

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | py:agents.evader_lab:LazyEvader3 | 平均 |
|---|---|---|
| py:agents.pursuer_lab:HarassPursuer | 0% [0–24] | 0% |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', 'py:agents.evader_lab:LazyEvader3']) | 0% [0–24] | 0% |
| **躲者平均存活** | 100% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| py:agents.pursuer_lab:HarassPursuer | py:agents.evader_lab:LazyEvader3 | 12 | timeout:12 | 40.1 | 2490 / 1254 | 986.6 / 5.1 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', 'py:agents.evader_lab:LazyEvader3']) | py:agents.evader_lab:LazyEvader3 | 12 | timeout:12 | 22.6 | 855 / 562 | 422.7 / 2.5 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 8 | 0% |
| near_coplanar | 16 | 0% |
