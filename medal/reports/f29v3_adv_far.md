# Tournament f29v3_adv_far

- **rules**: final_ranges
- **scenario**: final_adv_far
- **games per pairing**: 40
- **seed**: 0

## 追者勝率（捕獲 + 躲者撞地；同時出手賽制另含 sma_out），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | safe_evader | heuristic_evader | 平均 |
|---|---|---|---|
| capture_pursuer | 0% [-0–9] | 55% [40–69] | 28% |
| lambert_pursuer | 0% [-0–9] | 50% [35–65] | 25% |
| **躲者平均存活** | 100% | 48% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| capture_pursuer | safe_evader | 40 | escape:40 | 359.0 | 1277 / 1252 | 282.5 / 650.5 |
| capture_pursuer | heuristic_evader | 40 | capture:8, escape:18, sma_out:14 | 182.5 | 1202 / 1154 | 262.2 / 0.3 |
| lambert_pursuer | safe_evader | 40 | escape:40 | 718.7 | 1352 / 1238 | 34.9 / 658.6 |
| lambert_pursuer | heuristic_evader | 40 | capture:1, escape:20, sma_out:19 | 575.7 | 1180 / 1235 | 212.5 / 0.4 |
