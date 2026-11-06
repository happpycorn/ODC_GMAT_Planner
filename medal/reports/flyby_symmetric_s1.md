# Tournament flyby_symmetric_s1

- **rules**: configs/rulesets/flyby_symmetric.json
- **scenario**: flyby
- **games per pairing**: 24
- **seed**: 1

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | coast | dv_evader | rollout_evader | escape_evader | sb3:models/evader.zip | 平均 |
|---|---|---|---|---|---|---|
| lambert_pursuer | 100% [86–100] | 0% [0–14] | 0% [0–14] | 33% [18–53] | 38% [21–57] | 34% |
| rollout_pursuer | 96% [80–99] | 4% [1–20] | 0% [0–14] | 54% [35–72] | 54% [35–72] | 42% |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | 96% [80–99] | 4% [1–20] | 0% [0–14] | 54% [35–72] | 54% [35–72] | 42% |
| sb3:models/pursuer.zip | 38% [21–57] | 0% [0–14] | 0% [0–14] | 0% [0–14] | 0% [0–14] | 8% |
| **躲者平均存活** | 18% | 98% | 100% | 65% | 64% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | coast | 24 | capture:24 | 0.0 | 133 / 0 | 5.3 / 0.1 |
| lambert_pursuer | dv_evader | 24 | timeout:24 | 1344.5 | 3000 / 3000 | 2.1 / 4.1 |
| lambert_pursuer | rollout_evader | 24 | timeout:24 | 77.0 | 2970 / 1500 | 2.4 / 63.8 |
| lambert_pursuer | escape_evader | 24 | capture:8, timeout:16 | 573.9 | 2909 / 3000 | 2.3 / 0.6 |
| lambert_pursuer | sb3:models/evader.zip | 24 | capture:9, timeout:15 | 631.9 | 2801 / 3000 | 2.1 / 2.0 |
| rollout_pursuer | coast | 24 | capture:23, timeout:1 | 0.0 | 182 / 0 | 41.2 / 0.1 |
| rollout_pursuer | dv_evader | 24 | capture:1, timeout:23 | 1105.7 | 2570 / 3000 | 16.5 / 4.2 |
| rollout_pursuer | rollout_evader | 24 | timeout:24 | 92.2 | 619 / 1438 | 29.9 / 64.6 |
| rollout_pursuer | escape_evader | 24 | capture:13, timeout:11 | 0.0 | 2585 / 3000 | 21.3 / 0.5 |
| rollout_pursuer | sb3:models/evader.zip | 24 | capture:13, timeout:11 | 4.0 | 2314 / 3000 | 23.4 / 2.2 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | coast | 24 | capture:23, timeout:1 | 0.0 | 179 / 0 | 461.6 / 0.1 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | dv_evader | 24 | capture:1, timeout:23 | 1105.7 | 2570 / 3000 | 120.2 / 4.1 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | rollout_evader | 24 | timeout:24 | 92.2 | 617 / 1438 | 256.7 / 64.6 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | escape_evader | 24 | capture:13, timeout:11 | 0.7 | 2584 / 3000 | 152.4 / 0.5 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | sb3:models/evader.zip | 24 | capture:13, timeout:11 | 2.1 | 2301 / 3000 | 167.9 / 2.2 |
| sb3:models/pursuer.zip | coast | 24 | capture:9, timeout:15 | 144.1 | 2185 / 0 | 2.3 / 0.1 |
| sb3:models/pursuer.zip | dv_evader | 24 | timeout:24 | 3403.0 | 3000 / 3000 | 1.9 / 4.0 |
| sb3:models/pursuer.zip | rollout_evader | 24 | timeout:24 | 309.6 | 2987 / 562 | 2.3 / 65.3 |
| sb3:models/pursuer.zip | escape_evader | 24 | timeout:24 | 2179.2 | 3000 / 3000 | 1.9 / 0.5 |
| sb3:models/pursuer.zip | sb3:models/evader.zip | 24 | timeout:24 | 1416.8 | 2957 / 3000 | 1.9 / 1.8 |
