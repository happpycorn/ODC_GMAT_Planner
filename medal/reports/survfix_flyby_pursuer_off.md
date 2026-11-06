# Tournament survfix_flyby_pursuer_off

- **rules**: configs/rulesets/flyby_ranking_like.json
- **scenario**: flyby_pursuer
- **games per pairing**: 24
- **seed**: 1

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | coast | dv_evader | rollout_evader | escape_evader | sb3:models/evader.zip | 平均 |
|---|---|---|---|---|---|---|
| lambert_pursuer | 92% [74–98] | 0% [0–14] | 0% [0–14] | 8% [2–26] | 29% [15–49] | 26% |
| rollout_pursuer | 88% [69–96] | 0% [0–14] | 0% [0–14] | 0% [0–14] | 42% [24–61] | 26% |
| sb3:models/pursuer.zip | 92% [74–98] | 0% [0–14] | 0% [0–14] | 4% [1–20] | 46% [28–65] | 28% |
| **躲者平均存活** | 10% | 100% | 100% | 96% | 61% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | coast | 24 | capture:22, timeout:2 | 0.0 | 273 / 0 | 7.3 / 0.2 |
| lambert_pursuer | dv_evader | 24 | timeout:24 | 1156.3 | 2828 / 2698 | 4.4 / 31.1 |
| lambert_pursuer | rollout_evader | 24 | timeout:24 | 68.1 | 2547 / 575 | 4.3 / 224.3 |
| lambert_pursuer | escape_evader | 24 | crash_evader:2, timeout:22 | 1172.1 | 2899 / 2760 | 4.3 / 4.0 |
| lambert_pursuer | sb3:models/evader.zip | 24 | crash_evader:7, timeout:17 | 132.9 | 2918 / 2864 | 2.0 / 2.8 |
| rollout_pursuer | coast | 24 | capture:21, timeout:3 | 0.0 | 115 / 0 | 137.4 / 0.2 |
| rollout_pursuer | dv_evader | 24 | timeout:24 | 932.3 | 850 / 2712 | 101.5 / 30.5 |
| rollout_pursuer | rollout_evader | 24 | timeout:24 | 53.8 | 539 / 529 | 99.8 / 228.8 |
| rollout_pursuer | escape_evader | 24 | timeout:24 | 1171.9 | 966 / 2740 | 98.4 / 3.7 |
| rollout_pursuer | sb3:models/evader.zip | 24 | crash_evader:10, timeout:14 | 145.6 | 902 / 2846 | 101.8 / 3.1 |
| sb3:models/pursuer.zip | coast | 24 | capture:22, timeout:2 | 0.0 | 182 / 0 | 5.6 / 0.2 |
| sb3:models/pursuer.zip | dv_evader | 24 | timeout:24 | 1423.8 | 1696 / 2719 | 5.1 / 30.9 |
| sb3:models/pursuer.zip | rollout_evader | 24 | timeout:24 | 111.6 | 1285 / 575 | 5.1 / 225.6 |
| sb3:models/pursuer.zip | escape_evader | 24 | crash_evader:1, timeout:23 | 1400.6 | 2283 / 2760 | 4.7 / 3.8 |
| sb3:models/pursuer.zip | sb3:models/evader.zip | 24 | capture:1, crash_evader:10, timeout:13 | 234.2 | 2012 / 2785 | 4.8 / 2.8 |
