# Tournament f29v3_adv_taiwan

- **rules**: final_ranges
- **scenario**: final_adv_taiwan
- **games per pairing**: 40
- **seed**: 0

## 追者勝率（捕獲 + 躲者撞地；同時出手賽制另含 sma_out），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | safe_evader | heuristic_evader | 平均 |
|---|---|---|---|
| capture_pursuer | 0% [-0–9] | 30% [18–45] | 15% |
| lambert_pursuer | 0% [-0–9] | 35% [22–50] | 18% |
| **躲者平均存活** | 100% | 68% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| capture_pursuer | safe_evader | 40 | escape:40 | 2991.5 | 1348 / 1093 | 254.4 / 673.5 |
| capture_pursuer | heuristic_evader | 40 | capture:1, escape:28, sma_out:11 | 3268.1 | 1304 / 1155 | 245.0 / 0.3 |
| lambert_pursuer | safe_evader | 40 | escape:40 | 6276.2 | 902 / 1100 | 98.1 / 668.4 |
| lambert_pursuer | heuristic_evader | 40 | capture:2, escape:26, sma_out:12 | 6536.1 | 895 / 1168 | 75.4 / 0.5 |
