# Tournament f24_harsh_zone

- **rules**: final_ranges
- **scenario**: final（安全空域偏移 4.5–5.5 發、初始不在區間）
- **games per pairing**: 40
- **seed**: 0

## 追者勝率（捕獲 + 躲者撞地；同時出手賽制另含 sma_out），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | safe_evader | heuristic_evader | 平均 |
|---|---|---|---|
| capture_pursuer | 0% [-0–9] | 57% [42–71] | 29% |
| lambert_pursuer | 0% [-0–9] | 45% [31–60] | 22% |
| **躲者平均存活** | 100% | 49% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| capture_pursuer | safe_evader | 40 | escape:40 | 189.1 | 1295 / 1313 | 234.6 / 542.8 |
| capture_pursuer | heuristic_evader | 40 | capture:13, escape:17, sma_out:10 | 141.3 | 1085 / 1048 | 228.3 / 0.2 |
| lambert_pursuer | safe_evader | 40 | escape:40 | 409.9 | 1259 / 1306 | 59.4 / 543.5 |
| lambert_pursuer | heuristic_evader | 40 | escape:22, sma_out:18 | 342.9 | 1129 / 1281 | 110.2 / 0.4 |
