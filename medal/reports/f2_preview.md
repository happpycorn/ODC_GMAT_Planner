# Tournament f2_preview

- **rules**: configs/rulesets/final_official.json
- **scenario**: final
- **games per pairing**: 40
- **seed**: 0

## 追者勝率（捕獲 + 躲者撞地；同時出手賽制另含 sma_out），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | safe_evader | heuristic_evader | 平均 |
|---|---|---|---|
| lambert_pursuer | 0% [-0–9] | 28% [16–43] | 14% |
| rollout_pursuer | 0% [-0–9] | 32% [20–48] | 16% |
| **躲者平均存活** | 100% | 70% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | safe_evader | 40 | escape:40 | 274.0 | 1125 / 1147 | 47.0 / 292.0 |
| lambert_pursuer | heuristic_evader | 40 | capture:2, escape:29, sma_out:9 | 285.5 | 940 / 1188 | 4.2 / 0.2 |
| rollout_pursuer | safe_evader | 40 | escape:40 | 444.2 | 100 / 1131 | 45.0 / 290.3 |
| rollout_pursuer | heuristic_evader | 40 | escape:27, sma_out:13 | 401.8 | 84 / 1219 | 45.5 / 0.2 |
