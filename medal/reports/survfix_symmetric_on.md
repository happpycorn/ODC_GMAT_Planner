# Tournament survfix_symmetric_on

- **rules**: configs/rulesets/symmetric.json
- **scenario**: mixed
- **games per pairing**: 24
- **seed**: 1

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | dv_evader | rollout_evader | escape_evader | 平均 |
|---|---|---|---|---|
| lambert_pursuer | 12% [4–31] | 0% [0–14] | 0% [0–14] | 4% |
| rollout_pursuer | 33% [18–53] | 58% [39–76] | 21% [9–40] | 38% |
| **躲者平均存活** | 77% | 71% | 90% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | dv_evader | 24 | capture:3, timeout:21 | 1051.5 | 2917 / 3000 | 10.8 / 1.9 |
| lambert_pursuer | rollout_evader | 24 | timeout:24 | 743.9 | 3000 / 2875 | 11.1 / 96.1 |
| lambert_pursuer | escape_evader | 24 | timeout:24 | 1468.0 | 3000 / 3000 | 10.3 / 0.7 |
| rollout_pursuer | dv_evader | 24 | capture:8, timeout:16 | 520.3 | 1551 / 3000 | 96.6 / 1.9 |
| rollout_pursuer | rollout_evader | 24 | capture:14, timeout:10 | 0.0 | 1887 / 2875 | 109.7 / 107.1 |
| rollout_pursuer | escape_evader | 24 | capture:5, timeout:19 | 1258.1 | 1298 / 3000 | 83.1 / 0.7 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 54 | 15% |
| near_coplanar | 72 | 31% |
| wild | 18 | 0% |
