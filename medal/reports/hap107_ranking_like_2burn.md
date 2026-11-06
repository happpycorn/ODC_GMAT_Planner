# Tournament hap107_ranking_like_2burn

- **rules**: configs/rulesets/ranking_like_2burn.json
- **scenario**: mixed
- **games per pairing**: 24
- **seed**: 1

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | dv_evader | rollout_evader | escape_evader | 平均 |
|---|---|---|---|---|
| lambert_pursuer | 50% [31–69] | 50% [31–69] | 71% [51–85] | 57% |
| rollout_pursuer | 83% [64–93] | 83% [64–93] | 100% [86–100] | 89% |
| **躲者平均存活** | 33% | 33% | 15% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | dv_evader | 24 | capture:12, timeout:12 | 8.9 | 2627 / 3000 | 12.8 / 12.4 |
| lambert_pursuer | rollout_evader | 24 | capture:12, timeout:12 | 4.9 | 2462 / 2804 | 14.0 / 564.0 |
| lambert_pursuer | escape_evader | 24 | capture:17, timeout:7 | 0.0 | 2462 / 3000 | 15.6 / 2.5 |
| rollout_pursuer | dv_evader | 24 | capture:20, timeout:4 | 0.0 | 1983 / 3000 | 432.6 / 13.9 |
| rollout_pursuer | rollout_evader | 24 | capture:20, timeout:4 | 0.0 | 2104 / 2906 | 476.2 / 582.0 |
| rollout_pursuer | escape_evader | 24 | capture:24 | 0.0 | 1754 / 3000 | 450.8 / 2.7 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 54 | 54% |
| near_coplanar | 72 | 97% |
| wild | 18 | 33% |
