# Tournament plazy_main_2burn_s1

- **rules**: configs/rulesets/ranking_like_2burn.json
- **scenario**: mixed
- **games per pairing**: 12
- **seed**: 1

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | py:agents.evader_lab:LazyEvader3 | 平均 |
|---|---|---|
| rollout_pursuer | 0% [0–24] | 0% |
| py:agents.pursuer_lab:HarassPursuer | 0% [0–24] | 0% |
| **躲者平均存活** | 100% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| rollout_pursuer | py:agents.evader_lab:LazyEvader3 | 12 | timeout:12 | 45.5 | 1580 / 1100 | 526.1 / 5.3 |
| py:agents.pursuer_lab:HarassPursuer | py:agents.evader_lab:LazyEvader3 | 12 | timeout:12 | 100.6 | 2682 / 1750 | 1692.6 / 7.3 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 8 | 0% |
| near_coplanar | 16 | 0% |
