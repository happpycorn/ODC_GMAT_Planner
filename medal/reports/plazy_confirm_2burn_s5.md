# Tournament plazy_confirm_2burn_s5

- **rules**: configs/rulesets/ranking_like_2burn.json
- **scenario**: mixed
- **games per pairing**: 24
- **seed**: 5

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | py:agents.evader_lab:LazyEvader3 | 平均 |
|---|---|---|
| rollout_pursuer | 0% [0–14] | 0% |
| py:agents.pursuer_lab:LazyHunter | 0% [0–14] | 0% |
| **躲者平均存活** | 100% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| rollout_pursuer | py:agents.evader_lab:LazyEvader3 | 24 | crash_pursuer:2, timeout:22 | 51.4 | 1432 / 785 | 764.0 / 6.2 |
| py:agents.pursuer_lab:LazyHunter | py:agents.evader_lab:LazyEvader3 | 24 | crash_pursuer:2, timeout:22 | 51.4 | 1432 / 785 | 752.0 / 6.3 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 20 | 0% |
| near_coplanar | 22 | 0% |
| wild | 6 | 0% |
