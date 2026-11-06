# Tournament f24_ranges

- **rules**: final_ranges
- **scenario**: final
- **games per pairing**: 120
- **seed**: 0

## 追者勝率（捕獲 + 躲者撞地；同時出手賽制另含 sma_out），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | safe_evader | dv_evader | heuristic_evader | 平均 |
|---|---|---|---|---|
| capture_pursuer | 0% [-0–3] | 98% [94–100] | 44% [36–53] | 47% |
| lambert_pursuer | 0% [-0–3] | 100% [97–100] | 30% [23–39] | 43% |
| **躲者平均存活** | 100% | 1% | 63% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| capture_pursuer | safe_evader | 120 | escape:120 | 194.4 | 1340 / 1188 | 247.9 / 615.4 |
| capture_pursuer | dv_evader | 120 | capture:103, escape:2, sma_out:15 | 0.1 | 526 / 11 | 263.4 / 81.4 |
| capture_pursuer | heuristic_evader | 120 | capture:34, escape:67, sma_out:19 | 99.0 | 1081 / 968 | 248.1 / 0.3 |
| lambert_pursuer | safe_evader | 120 | escape:120 | 278.4 | 1118 / 1180 | 56.2 / 618.6 |
| lambert_pursuer | dv_evader | 120 | capture:97, sma_out:23 | 5.1 | 46 / 78 | 72.8 / 63.7 |
| lambert_pursuer | heuristic_evader | 120 | capture:4, escape:84, sma_out:32 | 177.2 | 907 / 1168 | 57.6 / 0.3 |
