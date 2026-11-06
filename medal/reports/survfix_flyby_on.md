# Tournament survfix_flyby_on

- **rules**: configs/rulesets/flyby_ranking_like.json
- **scenario**: flyby
- **games per pairing**: 24
- **seed**: 1

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | coast | dv_evader | rollout_evader | escape_evader | sb3:models/evader.zip | 平均 |
|---|---|---|---|---|---|---|
| lambert_pursuer | 92% [74–98] | 0% [0–14] | 0% [0–14] | 0% [0–14] | 0% [0–14] | 18% |
| rollout_pursuer | 92% [74–98] | 0% [0–14] | 0% [0–14] | 0% [0–14] | 0% [0–14] | 18% |
| sb3:models/pursuer.zip | 50% [31–69] | 0% [0–14] | 0% [0–14] | 0% [0–14] | 8% [2–26] | 12% |
| **躲者平均存活** | 22% | 100% | 100% | 100% | 97% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | coast | 24 | capture:22, timeout:2 | 0.0 | 248 / 0 | 7.2 / 0.2 |
| lambert_pursuer | dv_evader | 24 | timeout:24 | 606.4 | 2339 / 2812 | 3.9 / 28.9 |
| lambert_pursuer | rollout_evader | 24 | timeout:24 | 46.2 | 1597 / 260 | 4.1 / 205.9 |
| lambert_pursuer | escape_evader | 24 | timeout:24 | 145.1 | 2670 / 2875 | 3.8 / 3.5 |
| lambert_pursuer | sb3:models/evader.zip | 24 | timeout:24 | 148.1 | 2350 / 2976 | 1.8 / 2.7 |
| rollout_pursuer | coast | 24 | capture:22, timeout:2 | 0.0 | 118 / 0 | 133.5 / 0.2 |
| rollout_pursuer | dv_evader | 24 | timeout:24 | 401.5 | 1125 / 2827 | 85.9 / 29.3 |
| rollout_pursuer | rollout_evader | 24 | timeout:24 | 46.2 | 284 / 260 | 89.6 / 202.7 |
| rollout_pursuer | escape_evader | 24 | timeout:24 | 145.1 | 1206 / 2844 | 85.4 / 3.6 |
| rollout_pursuer | sb3:models/evader.zip | 24 | timeout:24 | 148.2 | 922 / 2972 | 86.9 / 2.9 |
| sb3:models/pursuer.zip | coast | 24 | capture:12, timeout:12 | 16.0 | 1438 / 0 | 4.1 / 0.2 |
| sb3:models/pursuer.zip | dv_evader | 24 | timeout:24 | 902.2 | 2413 / 2838 | 3.8 / 28.5 |
| sb3:models/pursuer.zip | rollout_evader | 24 | timeout:24 | 80.5 | 2233 / 125 | 4.0 / 207.6 |
| sb3:models/pursuer.zip | escape_evader | 24 | timeout:24 | 528.4 | 2523 / 2844 | 3.5 / 3.4 |
| sb3:models/pursuer.zip | sb3:models/evader.zip | 24 | capture:2, timeout:22 | 158.3 | 2302 / 2786 | 3.5 / 2.6 |
