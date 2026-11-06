# Tournament hap108_escape_evader_symmetric

- **rules**: configs/rulesets/symmetric.json
- **scenario**: mixed
- **games per pairing**: 16
- **seed**: 777

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | rollout_evader | escape_evader | rollout_evader(candidates=['dv_evader', 'dv_evader_fast', 'escape_evader']) | 平均 |
|---|---|---|---|---|
| lambert_pursuer | 0% [0–19] | 6% [1–28] | 0% [0–19] | 2% |
| rollout_pursuer | 56% [33–77] | 19% [7–43] | 56% [33–77] | 44% |
| **躲者平均存活** | 72% | 88% | 72% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | rollout_evader | 16 | timeout:16 | 1106.0 | 3000 / 2812 | 36.1 / 103.4 |
| lambert_pursuer | escape_evader | 16 | capture:1, timeout:15 | 1106.0 | 2994 / 3000 | 36.5 / 0.8 |
| lambert_pursuer | rollout_evader(candidates=['dv_evader', 'dv_evader_fast', 'escape_evader']) | 16 | timeout:16 | 1106.0 | 3000 / 2812 | 36.8 / 105.3 |
| rollout_pursuer | rollout_evader | 16 | capture:9, timeout:7 | 0.0 | 2199 / 3000 | 169.8 / 119.5 |
| rollout_pursuer | escape_evader | 16 | capture:3, timeout:13 | 922.0 | 1273 / 3000 | 127.6 / 0.6 |
| rollout_pursuer | rollout_evader(candidates=['dv_evader', 'dv_evader_fast', 'escape_evader']) | 16 | capture:9, timeout:7 | 0.0 | 2199 / 3000 | 168.3 / 120.9 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 24 | 8% |
| near_coplanar | 60 | 30% |
| wild | 12 | 17% |
