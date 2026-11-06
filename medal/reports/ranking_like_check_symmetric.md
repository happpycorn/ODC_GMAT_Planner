# Tournament ranking_like_check_symmetric

- **rules**: configs/rulesets/symmetric.json
- **scenario**: mixed
- **games per pairing**: 20
- **seed**: 0

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | dv_evader | rollout_evader | escape_evader | 平均 |
|---|---|---|---|---|
| lambert_pursuer | 25% [11–47] | 5% [1–24] | 5% [1–24] | 12% |
| rollout_pursuer | 55% [34–74] | 45% [26–66] | 50% [30–70] | 50% |
| **躲者平均存活** | 60% | 75% | 72% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | dv_evader | 20 | capture:5, timeout:15 | 992.9 | 2920 / 3000 | 14.6 / 2.6 |
| lambert_pursuer | rollout_evader | 20 | capture:1, timeout:19 | 1029.5 | 2932 / 2700 | 14.5 / 106.8 |
| lambert_pursuer | escape_evader | 20 | capture:1, timeout:19 | 2802.2 | 2997 / 3000 | 13.4 / 0.6 |
| rollout_pursuer | dv_evader | 20 | capture:11, timeout:9 | 0.0 | 1978 / 3000 | 127.1 / 3.5 |
| rollout_pursuer | rollout_evader | 20 | capture:9, timeout:11 | 656.6 | 2519 / 2730 | 106.4 / 114.9 |
| rollout_pursuer | escape_evader | 20 | capture:10, timeout:10 | 420.9 | 2179 / 3000 | 81.7 / 0.6 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 48 | 29% |
| near_coplanar | 48 | 38% |
| wild | 24 | 21% |
