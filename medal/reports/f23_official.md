# Tournament f23_official

- **rules**: configs/rulesets/final_official.json
- **scenario**: final
- **games per pairing**: 40
- **seed**: 0

## 追者勝率（捕獲 + 躲者撞地；同時出手賽制另含 sma_out），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | safe_evader | dv_evader | heuristic_evader | 平均 |
|---|---|---|---|---|
| capture_pursuer | 0% [-0–9] | 98% [87–100] | 40% [26–55] | 46% |
| lambert_pursuer | 0% [-0–9] | 100% [91–100] | 28% [16–43] | 42% |
| **躲者平均存活** | 100% | 1% | 66% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| capture_pursuer | safe_evader | 40 | escape:40 | 185.2 | 1329 / 1141 | 150.5 / 305.2 |
| capture_pursuer | dv_evader | 40 | capture:37, escape:1, sma_out:2 | 0.0 | 680 / 30 | 167.3 / 47.1 |
| capture_pursuer | heuristic_evader | 40 | capture:6, escape:24, sma_out:10 | 150.6 | 1227 / 1078 | 150.3 / 0.2 |
| lambert_pursuer | safe_evader | 40 | escape:40 | 274.0 | 1125 / 1147 | 95.5 / 307.4 |
| lambert_pursuer | dv_evader | 40 | capture:38, sma_out:2 | 3.4 | 50 / 38 | 5.0 / 35.2 |
| lambert_pursuer | heuristic_evader | 40 | capture:2, escape:29, sma_out:9 | 285.5 | 940 / 1188 | 27.4 / 0.2 |
