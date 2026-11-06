# Tournament plazy_main_sym2burn_s1

- **rules**: configs/rulesets/symmetric_2burn.json
- **scenario**: mixed
- **games per pairing**: 12
- **seed**: 1

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | py:agents.evader_lab:LazyEvader3 | 平均 |
|---|---|---|
| rollout_pursuer | 25% [9–53] | 25% |
| py:agents.pursuer_lab:HarassPursuer | 8% [1–35] | 8% |
| **躲者平均存活** | 83% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| rollout_pursuer | py:agents.evader_lab:LazyEvader3 | 12 | capture:3, timeout:9 | 152.5 | 2317 / 3000 | 314.2 / 2.6 |
| py:agents.pursuer_lab:HarassPursuer | py:agents.evader_lab:LazyEvader3 | 12 | capture:1, timeout:11 | 332.3 | 2829 / 2750 | 416.7 / 2.1 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 8 | 0% |
| near_coplanar | 16 | 25% |
