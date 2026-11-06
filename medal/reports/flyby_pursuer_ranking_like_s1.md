# Tournament flyby_pursuer_ranking_like_s1

- **rules**: configs/rulesets/flyby_ranking_like.json
- **scenario**: flyby_pursuer
- **games per pairing**: 12
- **seed**: 1

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | coast | dv_evader | rollout_evader | escape_evader | sb3:models/evader.zip | 平均 |
|---|---|---|---|---|---|---|
| lambert_pursuer | 100% [76–100] | 0% [0–24] | 0% [0–24] | 8% [1–35] | 42% [19–68] | 30% |
| rollout_pursuer | 100% [76–100] | 0% [0–24] | 0% [0–24] | 0% [0–24] | 50% [25–75] | 30% |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | 100% [76–100] | 0% [0–24] | 0% [0–24] | 0% [0–24] | 58% [32–81] | 32% |
| sb3:models/pursuer.zip | 100% [76–100] | 0% [0–24] | 0% [0–24] | 8% [1–35] | 42% [19–68] | 30% |
| **躲者平均存活** | 0% | 100% | 100% | 96% | 52% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | coast | 12 | capture:12 | 0.0 | 65 / 0 | 8.3 / 0.1 |
| lambert_pursuer | dv_evader | 12 | timeout:12 | 1375.6 | 2885 / 2804 | 4.4 / 17.9 |
| lambert_pursuer | rollout_evader | 12 | timeout:12 | 77.4 | 2563 / 558 | 4.4 / 130.9 |
| lambert_pursuer | escape_evader | 12 | crash_evader:1, timeout:11 | 1226.7 | 2908 / 2812 | 4.5 / 2.2 |
| lambert_pursuer | sb3:models/evader.zip | 12 | crash_evader:5, timeout:7 | 295.4 | 2931 / 2897 | 5.1 / 1.8 |
| rollout_pursuer | coast | 12 | capture:12 | 0.0 | 70 / 0 | 83.7 / 0.1 |
| rollout_pursuer | dv_evader | 12 | timeout:12 | 1322.4 | 904 / 2804 | 59.9 / 17.5 |
| rollout_pursuer | rollout_evader | 12 | timeout:12 | 125.8 | 688 / 608 | 58.8 / 131.8 |
| rollout_pursuer | escape_evader | 12 | timeout:12 | 1226.7 | 1088 / 2812 | 56.2 / 2.1 |
| rollout_pursuer | sb3:models/evader.zip | 12 | crash_evader:6, timeout:6 | 295.4 | 1025 / 2829 | 58.7 / 2.0 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | coast | 12 | capture:12 | 0.0 | 69 / 0 | 938.5 / 0.1 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | dv_evader | 12 | timeout:12 | 1322.4 | 908 / 2804 | 535.1 / 17.2 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | rollout_evader | 12 | timeout:12 | 125.8 | 699 / 608 | 501.7 / 130.7 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | escape_evader | 12 | timeout:12 | 1226.7 | 1075 / 2812 | 520.8 / 2.1 |
| rollout_pursuer(opponents=['coast', 'dv_evader_fast', {'name': 'rollout_evader', 'candidates': ['dv_evader_fast'], 'opponents': ['lambert_pursuer_fast']}]) | sb3:models/evader.zip | 12 | crash_evader:7, timeout:5 | 295.4 | 1029 / 2825 | 549.5 / 2.0 |
| sb3:models/pursuer.zip | coast | 12 | capture:12 | 0.0 | 105 / 0 | 3.1 / 0.1 |
| sb3:models/pursuer.zip | dv_evader | 12 | timeout:12 | 1672.1 | 1924 / 2800 | 3.0 / 17.3 |
| sb3:models/pursuer.zip | rollout_evader | 12 | timeout:12 | 397.0 | 1441 / 608 | 3.2 / 128.8 |
| sb3:models/pursuer.zip | escape_evader | 12 | crash_evader:1, timeout:11 | 1481.7 | 2308 / 2771 | 2.8 / 2.2 |
| sb3:models/pursuer.zip | sb3:models/evader.zip | 12 | crash_evader:5, timeout:7 | 613.3 | 2207 / 2890 | 2.8 / 1.7 |
