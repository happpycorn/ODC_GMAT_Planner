# Tournament rollout_eval_default

- **rules**: default
- **scenario**: mixed
- **games per pairing**: 30
- **seed**: 0

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | coast | dv_evader | rollout_evader | 平均 |
|---|---|---|---|---|
| lambert_pursuer | 93% [79–98] | 17% [7–34] | 7% [2–21] | 39% |
| rollout_pursuer | 97% [83–99] | 50% [33–67] | 57% [39–73] | 68% |
| **躲者平均存活** | 5% | 67% | 68% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | coast | 30 | capture:28, timeout:2 | 0.0 | 1007 / 0 | 23.7 / 0.0 |
| lambert_pursuer | dv_evader | 30 | capture:5, timeout:25 | 992.9 | 2947 / 3000 | 12.1 / 2.8 |
| lambert_pursuer | rollout_evader | 30 | capture:2, timeout:28 | 992.9 | 2955 / 2800 | 13.1 / 131.3 |
| rollout_pursuer | coast | 30 | capture:29, timeout:1 | 0.0 | 1107 / 0 | 249.7 / 0.0 |
| rollout_pursuer | dv_evader | 30 | capture:15, timeout:15 | 10.3 | 1839 / 3000 | 141.8 / 4.0 |
| rollout_pursuer | rollout_evader | 30 | capture:17, timeout:13 | 1.1 | 2545 / 2820 | 136.1 / 143.2 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 66 | 52% |
| near_coplanar | 78 | 60% |
| wild | 36 | 42% |
