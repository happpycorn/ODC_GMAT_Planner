# Tournament survfix_flyby_off

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
| lambert_pursuer | coast | 24 | capture:22, crash_pursuer:1, timeout:1 | 0.0 | 294 / 0 | 6.7 / 0.2 |
| lambert_pursuer | dv_evader | 24 | crash_pursuer:8, timeout:16 | 606.4 | 2509 / 2802 | 3.7 / 30.2 |
| lambert_pursuer | rollout_evader | 24 | crash_pursuer:13, timeout:11 | 46.2 | 1924 / 260 | 3.9 / 207.4 |
| lambert_pursuer | escape_evader | 24 | crash_pursuer:5, timeout:19 | 145.1 | 2806 / 2875 | 3.6 / 3.7 |
| lambert_pursuer | sb3:models/evader.zip | 24 | crash_pursuer:4, timeout:20 | 148.1 | 2498 / 2976 | 1.8 / 2.7 |
| rollout_pursuer | coast | 24 | capture:22, timeout:2 | 0.0 | 118 / 0 | 131.6 / 0.2 |
| rollout_pursuer | dv_evader | 24 | timeout:24 | 401.5 | 1125 / 2827 | 84.7 / 29.5 |
| rollout_pursuer | rollout_evader | 24 | timeout:24 | 46.2 | 284 / 260 | 87.2 / 199.0 |
| rollout_pursuer | escape_evader | 24 | timeout:24 | 145.1 | 1206 / 2844 | 85.1 / 3.6 |
| rollout_pursuer | sb3:models/evader.zip | 24 | timeout:24 | 148.2 | 922 / 2972 | 86.3 / 2.9 |
| sb3:models/pursuer.zip | coast | 24 | capture:12, crash_pursuer:6, timeout:6 | 16.0 | 1560 / 0 | 4.1 / 0.2 |
| sb3:models/pursuer.zip | dv_evader | 24 | crash_pursuer:8, timeout:16 | 902.2 | 2583 / 2838 | 3.9 / 29.8 |
| sb3:models/pursuer.zip | rollout_evader | 24 | crash_pursuer:9, timeout:15 | 80.5 | 2433 / 125 | 4.0 / 212.2 |
| sb3:models/pursuer.zip | escape_evader | 24 | crash_pursuer:5, timeout:19 | 528.4 | 2639 / 2844 | 3.7 / 3.5 |
| sb3:models/pursuer.zip | sb3:models/evader.zip | 24 | capture:2, crash_pursuer:5, timeout:17 | 158.3 | 2462 / 2776 | 3.7 / 2.7 |
