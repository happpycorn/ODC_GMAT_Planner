# Tournament flyby_ranking_like_s1

- **rules**: configs/rulesets/flyby_ranking_like.json
- **scenario**: flyby
- **games per pairing**: 24
- **seed**: 1

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | coast | dv_evader | rollout_evader | escape_evader | sb3:models/evader.zip | 平均 |
|---|---|---|---|---|---|---|
| lambert_pursuer | 92% [74–98] | 0% [0–14] | 0% [0–14] | 0% [0–14] | 0% [0–14] | 18% |
| rollout_pursuer | 92% [74–98] | 0% [0–14] | 0% [0–14] | 0% [0–14] | 0% [0–14] | 18% |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | 92% [74–98] | 0% [0–14] | 0% [0–14] | 0% [0–14] | 0% [0–14] | 18% |
| sb3:models/pursuer.zip | 50% [31–69] | 0% [0–14] | 0% [0–14] | 0% [0–14] | 8% [2–26] | 12% |
| **躲者平均存活** | 19% | 100% | 100% | 100% | 98% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | coast | 24 | capture:22, crash_pursuer:1, timeout:1 | 0.0 | 294 / 0 | 4.5 / 0.1 |
| lambert_pursuer | dv_evader | 24 | crash_pursuer:8, timeout:16 | 606.4 | 2509 / 2802 | 2.5 / 18.8 |
| lambert_pursuer | rollout_evader | 24 | crash_pursuer:13, timeout:11 | 46.2 | 1924 / 260 | 2.6 / 127.9 |
| lambert_pursuer | escape_evader | 24 | crash_pursuer:5, timeout:19 | 145.1 | 2806 / 2875 | 2.4 / 2.3 |
| lambert_pursuer | sb3:models/evader.zip | 24 | crash_pursuer:4, timeout:20 | 148.1 | 2498 / 2976 | 2.3 / 1.9 |
| rollout_pursuer | coast | 24 | capture:22, timeout:2 | 0.0 | 118 / 0 | 80.9 / 0.1 |
| rollout_pursuer | dv_evader | 24 | timeout:24 | 401.5 | 1125 / 2827 | 51.7 / 18.0 |
| rollout_pursuer | rollout_evader | 24 | timeout:24 | 46.2 | 284 / 260 | 53.5 / 121.8 |
| rollout_pursuer | escape_evader | 24 | timeout:24 | 145.1 | 1206 / 2844 | 52.1 / 2.2 |
| rollout_pursuer | sb3:models/evader.zip | 24 | timeout:24 | 148.2 | 922 / 2972 | 53.0 / 1.9 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | coast | 24 | capture:22, timeout:2 | 0.0 | 118 / 0 | 961.4 / 0.1 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | dv_evader | 24 | timeout:24 | 401.5 | 1125 / 2827 | 523.0 / 18.6 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | rollout_evader | 24 | timeout:24 | 46.2 | 284 / 260 | 494.2 / 123.6 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | escape_evader | 24 | timeout:24 | 145.1 | 1206 / 2844 | 528.8 / 2.3 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | sb3:models/evader.zip | 24 | timeout:24 | 148.2 | 922 / 2972 | 525.2 / 2.0 |
| sb3:models/pursuer.zip | coast | 24 | capture:12, crash_pursuer:6, timeout:6 | 16.0 | 1560 / 0 | 2.6 / 0.1 |
| sb3:models/pursuer.zip | dv_evader | 24 | crash_pursuer:8, timeout:16 | 902.2 | 2583 / 2838 | 2.5 / 18.8 |
| sb3:models/pursuer.zip | rollout_evader | 24 | crash_pursuer:9, timeout:15 | 80.5 | 2433 / 125 | 2.7 / 132.1 |
| sb3:models/pursuer.zip | escape_evader | 24 | crash_pursuer:5, timeout:19 | 528.4 | 2639 / 2844 | 2.3 / 2.2 |
| sb3:models/pursuer.zip | sb3:models/evader.zip | 24 | capture:2, crash_pursuer:5, timeout:17 | 158.3 | 2462 / 2776 | 2.3 / 1.6 |
