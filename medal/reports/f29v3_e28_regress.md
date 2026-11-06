# Tournament f29v3_e28_regress

- **rules**: final_ranges
- **scenario**: final
- **games per pairing**: 120
- **seed**: 0

## 追者勝率（捕獲 + 躲者撞地；同時出手賽制另含 sma_out），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | safe_evader | dv_evader | heuristic_evader | 平均 |
|---|---|---|---|---|
| capture_pursuer | 0% [-0–3] | 98% [94–100] | 42% [34–51] | 47% |
| lambert_pursuer | 0% [-0–3] | 100% [97–100] | 30% [23–39] | 43% |
| **躲者平均存活** | 100% | 1% | 64% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| capture_pursuer | safe_evader | 120 | escape:120 | 194.8 | 1328 / 1123 | 312.5 / 792.8 |
| capture_pursuer | dv_evader | 120 | capture:102, escape:2, sma_out:16 | 0.1 | 530 / 12 | 313.9 / 94.5 |
| capture_pursuer | heuristic_evader | 120 | capture:32, escape:69, sma_out:19 | 94.4 | 1087 / 974 | 302.3 / 0.3 |
| lambert_pursuer | safe_evader | 120 | escape:120 | 231.6 | 1105 / 1123 | 53.8 / 795.7 |
| lambert_pursuer | dv_evader | 120 | capture:97, sma_out:23 | 5.1 | 46 / 78 | 84.7 / 76.8 |
| lambert_pursuer | heuristic_evader | 120 | capture:4, escape:84, sma_out:32 | 177.2 | 907 / 1168 | 113.0 / 0.3 |
