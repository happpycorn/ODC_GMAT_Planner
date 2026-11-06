# Tournament ranking_like_check_ranking_like

- **rules**: configs/rulesets/ranking_like.json
- **scenario**: mixed
- **games per pairing**: 20
- **seed**: 0

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | dv_evader | rollout_evader | escape_evader | 平均 |
|---|---|---|---|---|
| lambert_pursuer | 40% [22–61] | 20% [8–42] | 45% [26–66] | 35% |
| rollout_pursuer | 80% [58–92] | 20% [8–42] | 100% [84–100] | 67% |
| **躲者平均存活** | 40% | 80% | 28% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | dv_evader | 20 | capture:8, timeout:12 | 742.0 | 2689 / 3000 | 15.5 / 10.2 |
| lambert_pursuer | rollout_evader | 20 | capture:4, timeout:16 | 653.2 | 2828 / 2320 | 15.4 / 210.1 |
| lambert_pursuer | escape_evader | 20 | capture:9, timeout:11 | 108.9 | 2548 / 3000 | 15.3 / 1.4 |
| rollout_pursuer | dv_evader | 20 | capture:16, timeout:4 | 0.0 | 1982 / 3000 | 134.1 / 10.4 |
| rollout_pursuer | rollout_evader | 20 | capture:4, timeout:16 | 1524.4 | 1668 / 2528 | 143.0 / 233.8 |
| rollout_pursuer | escape_evader | 20 | capture:20 | 0.0 | 2215 / 3000 | 122.5 / 1.5 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 48 | 42% |
| near_coplanar | 48 | 73% |
| wild | 24 | 25% |
