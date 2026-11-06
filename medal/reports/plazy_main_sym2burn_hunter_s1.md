# Tournament plazy_main_sym2burn_hunter_s1

- **rules**: configs/rulesets/symmetric_2burn.json
- **scenario**: mixed
- **games per pairing**: 12
- **seed**: 1

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | py:agents.evader_lab:LazyEvader3 | 平均 |
|---|---|---|
| py:agents.pursuer_lab:LazyHunter | 25% [9–53] | 25% |
| **躲者平均存活** | 75% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| py:agents.pursuer_lab:LazyHunter | py:agents.evader_lab:LazyEvader3 | 12 | capture:3, timeout:9 | 152.5 | 2317 / 3000 | 440.8 / 3.4 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 4 | 0% |
| near_coplanar | 8 | 38% |
