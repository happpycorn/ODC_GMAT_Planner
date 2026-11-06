# Tournament survfix_flyby_pursuer_on

- **rules**: configs/rulesets/flyby_ranking_like.json
- **scenario**: flyby_pursuer
- **games per pairing**: 24
- **seed**: 1

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | coast | dv_evader | rollout_evader | escape_evader | sb3:models/evader.zip | 平均 |
|---|---|---|---|---|---|---|
| lambert_pursuer | 92% [74–98] | 0% [0–14] | 0% [0–14] | 0% [0–14] | 0% [0–14] | 18% |
| rollout_pursuer | 88% [69–96] | 0% [0–14] | 0% [0–14] | 0% [0–14] | 0% [0–14] | 18% |
| sb3:models/pursuer.zip | 92% [74–98] | 0% [0–14] | 0% [0–14] | 0% [0–14] | 4% [1–20] | 19% |
| **躲者平均存活** | 10% | 100% | 100% | 100% | 99% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | coast | 24 | capture:22, timeout:2 | 0.0 | 273 / 0 | 7.3 / 0.2 |
| lambert_pursuer | dv_evader | 24 | timeout:24 | 1156.3 | 2828 / 2698 | 4.3 / 29.1 |
| lambert_pursuer | rollout_evader | 24 | timeout:24 | 61.9 | 2497 / 460 | 4.3 / 212.2 |
| lambert_pursuer | escape_evader | 24 | timeout:24 | 1172.1 | 2899 / 2760 | 4.1 / 3.6 |
| lambert_pursuer | sb3:models/evader.zip | 24 | timeout:24 | 132.9 | 2918 / 2719 | 1.9 / 2.7 |
| rollout_pursuer | coast | 24 | capture:21, timeout:3 | 0.0 | 114 / 0 | 127.0 / 0.2 |
| rollout_pursuer | dv_evader | 24 | timeout:24 | 932.3 | 863 / 2712 | 95.4 / 28.2 |
| rollout_pursuer | rollout_evader | 24 | timeout:24 | 53.8 | 515 / 519 | 93.1 / 216.5 |
| rollout_pursuer | escape_evader | 24 | timeout:24 | 1171.9 | 966 / 2740 | 92.9 / 3.5 |
| rollout_pursuer | sb3:models/evader.zip | 24 | timeout:24 | 143.4 | 904 / 2662 | 95.2 / 2.9 |
| sb3:models/pursuer.zip | coast | 24 | capture:22, timeout:2 | 0.0 | 182 / 0 | 5.3 / 0.2 |
| sb3:models/pursuer.zip | dv_evader | 24 | timeout:24 | 1423.8 | 1695 / 2712 | 5.0 / 29.4 |
| sb3:models/pursuer.zip | rollout_evader | 24 | timeout:24 | 86.1 | 1315 / 523 | 4.8 / 212.3 |
| sb3:models/pursuer.zip | escape_evader | 24 | timeout:24 | 1400.6 | 2281 / 2760 | 4.4 / 3.6 |
| sb3:models/pursuer.zip | sb3:models/evader.zip | 24 | capture:1, timeout:23 | 234.2 | 2003 / 2544 | 4.5 / 2.6 |
