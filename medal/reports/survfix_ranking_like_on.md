# Tournament survfix_ranking_like_on

- **rules**: configs/rulesets/ranking_like.json
- **scenario**: mixed
- **games per pairing**: 24
- **seed**: 1

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | dv_evader | rollout_evader | escape_evader | 平均 |
|---|---|---|---|---|
| lambert_pursuer | 58% [39–76] | 46% [28–65] | 67% [47–82] | 57% |
| rollout_pursuer | 79% [60–91] | 29% [15–49] | 100% [86–100] | 69% |
| **躲者平均存活** | 31% | 62% | 17% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | dv_evader | 24 | capture:14, timeout:10 | 0.0 | 2628 / 3000 | 12.6 / 11.9 |
| lambert_pursuer | rollout_evader | 24 | capture:11, timeout:13 | 54.6 | 2629 / 2698 | 12.8 / 231.7 |
| lambert_pursuer | escape_evader | 24 | capture:16, timeout:8 | 0.0 | 2366 / 3000 | 12.8 / 1.9 |
| rollout_pursuer | dv_evader | 24 | capture:19, timeout:5 | 0.0 | 2107 / 3000 | 143.4 / 11.7 |
| rollout_pursuer | rollout_evader | 24 | capture:7, timeout:17 | 790.2 | 1330 / 2373 | 166.8 / 290.1 |
| rollout_pursuer | escape_evader | 24 | capture:24 | 0.0 | 2069 / 3000 | 149.8 / 1.9 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 54 | 48% |
| near_coplanar | 72 | 82% |
| wild | 18 | 33% |
