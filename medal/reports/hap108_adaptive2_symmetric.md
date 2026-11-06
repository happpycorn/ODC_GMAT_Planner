# Tournament hap108_adaptive2_symmetric

- **rules**: configs/rulesets/symmetric.json
- **scenario**: mixed
- **games per pairing**: 16
- **seed**: 777

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | rollout_evader | adaptive_evader | 平均 |
|---|---|---|---|
| lambert_pursuer | 0% [0–19] | 6% [1–28] | 3% |
| rollout_pursuer | 56% [33–77] | 19% [7–43] | 38% |
| **躲者平均存活** | 72% | 88% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | rollout_evader | 16 | timeout:16 | 1106.0 | 3000 / 2812 | 53.7 / 102.1 |
| lambert_pursuer | adaptive_evader | 16 | capture:1, timeout:15 | 1106.0 | 2994 / 3000 | 53.3 / 0.7 |
| rollout_pursuer | rollout_evader | 16 | capture:9, timeout:7 | 0.0 | 2199 / 3000 | 192.2 / 114.1 |
| rollout_pursuer | adaptive_evader | 16 | capture:3, timeout:13 | 922.0 | 1273 / 3000 | 144.3 / 0.6 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 16 | 6% |
| near_coplanar | 40 | 28% |
| wild | 8 | 12% |
