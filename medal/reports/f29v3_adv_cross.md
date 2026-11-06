# Tournament f29v3_adv_cross

- **rules**: final_ranges
- **scenario**: final_adv_cross
- **games per pairing**: 40
- **seed**: 0

## 追者勝率（捕獲 + 躲者撞地；同時出手賽制另含 sma_out），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | safe_evader | heuristic_evader | 平均 |
|---|---|---|---|
| capture_pursuer | 0% [-0–9] | 40% [26–55] | 20% |
| lambert_pursuer | 0% [-0–9] | 22% [12–38] | 11% |
| **躲者平均存活** | 100% | 69% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| capture_pursuer | safe_evader | 40 | escape:40 | 211.3 | 1340 / 1096 | 295.6 / 678.7 |
| capture_pursuer | heuristic_evader | 40 | capture:6, escape:24, sma_out:10 | 233.4 | 1277 / 1145 | 294.5 / 0.3 |
| lambert_pursuer | safe_evader | 40 | escape:40 | 333.4 | 1210 / 1100 | 112.7 / 685.0 |
| lambert_pursuer | heuristic_evader | 40 | escape:31, sma_out:9 | 414.4 | 1101 / 1196 | 226.5 / 0.5 |
