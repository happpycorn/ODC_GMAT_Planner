# Tournament e15_ranking_like_wide

- **rules**: configs/rulesets/ranking_like.json
- **scenario**: mixed
- **games per pairing**: 48
- **seed**: 1

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | dv_evader | rollout_evader | escape_evader | adaptive_evader | sb3:models/evader.zip | 平均 |
|---|---|---|---|---|---|---|
| lambert_pursuer | 52% [38–66] | 35% [23–50] | 62% [48–75] | 62% [48–75] | 44% [31–58] | 51% |
| rollout_pursuer | 81% [68–90] | 40% [27–54] | 94% [83–98] | 94% [83–98] | 75% [61–85] | 77% |
| sb3:models/pursuer.zip | 60% [46–73] | 48% [34–62] | 67% [53–78] | 67% [53–78] | 48% [34–62] | 58% |
| **躲者平均存活** | 35% | 59% | 26% | 26% | 44% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | dv_evader | 48 | capture:25, timeout:23 | 1.6 | 2705 / 3000 | 20.3 / 19.0 |
| lambert_pursuer | rollout_evader | 48 | capture:17, timeout:31 | 363.2 | 2713 / 2591 | 18.2 / 374.8 |
| lambert_pursuer | escape_evader | 48 | capture:30, timeout:18 | 0.0 | 2403 / 3000 | 18.9 / 2.7 |
| lambert_pursuer | adaptive_evader | 48 | capture:30, timeout:18 | 0.0 | 2403 / 3000 | 21.8 / 2.8 |
| lambert_pursuer | sb3:models/evader.zip | 48 | capture:21, timeout:27 | 189.1 | 2957 / 3000 | 20.4 / 5.3 |
| rollout_pursuer | dv_evader | 48 | capture:39, timeout:9 | 0.0 | 2045 / 3000 | 230.1 / 19.1 |
| rollout_pursuer | rollout_evader | 48 | capture:19, timeout:29 | 646.9 | 1651 / 2577 | 283.0 / 439.6 |
| rollout_pursuer | escape_evader | 48 | capture:45, timeout:3 | 0.0 | 2122 / 3000 | 256.4 / 2.9 |
| rollout_pursuer | adaptive_evader | 48 | capture:45, timeout:3 | 0.0 | 2122 / 3000 | 250.6 / 2.9 |
| rollout_pursuer | sb3:models/evader.zip | 48 | capture:36, timeout:12 | 0.0 | 2027 / 2992 | 244.7 / 5.7 |
| sb3:models/pursuer.zip | dv_evader | 48 | capture:29, crash_pursuer:1, timeout:18 | 0.0 | 2465 / 3000 | 25.1 / 20.0 |
| sb3:models/pursuer.zip | rollout_evader | 48 | capture:23, timeout:25 | 47.6 | 2579 / 2808 | 26.4 / 367.0 |
| sb3:models/pursuer.zip | escape_evader | 48 | capture:32, timeout:16 | 0.0 | 2367 / 3000 | 9.9 / 2.9 |
| sb3:models/pursuer.zip | adaptive_evader | 48 | capture:32, timeout:16 | 0.0 | 2367 / 3000 | 9.3 / 2.7 |
| sb3:models/pursuer.zip | sb3:models/evader.zip | 48 | capture:23, timeout:25 | 25.7 | 2692 / 3000 | 9.6 / 5.0 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 270 | 42% |
| near_coplanar | 330 | 90% |
| wild | 120 | 30% |
