# Tournament plazy_final_check_rl_s5

- **rules**: configs/rulesets/ranking_like.json
- **scenario**: mixed
- **games per pairing**: 12
- **seed**: 5

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | py:agents.evader_lab:LazyEvader3 | 平均 |
|---|---|---|
| py:agents.pursuer_lab:LazyHunter | 0% [0–24] | 0% |
| **躲者平均存活** | 100% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| py:agents.pursuer_lab:LazyHunter | py:agents.evader_lab:LazyEvader3 | 12 | timeout:12 | 76.7 | 2332 / 1004 | 746.5 / 3.5 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 6 | 0% |
| near_coplanar | 4 | 0% |
| wild | 2 | 0% |
