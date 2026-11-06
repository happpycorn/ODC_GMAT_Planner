# Tournament baseline_final_corner_long

- **rules**: configs/rulesets/final_corner_long.json
- **scenario**: final
- **games per pairing**: 20
- **seed**: 0

## 追者勝率（捕獲 + 躲者撞地；同時出手賽制另含 sma_out），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | coast | dv_evader | lazy_evader | 平均 |
|---|---|---|---|---|
| lambert_pursuer | 100% [84–100] | 100% [84–100] | 100% [84–100] | 100% |
| rollout_pursuer | 70% [48–85] | 70% [48–85] | 70% [48–85] | 70% |
| **躲者平均存活** | 15% | 15% | 15% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | coast | 20 | capture:20 | 0.0 | 31 / 0 | 297.3 / 0.0 |
| lambert_pursuer | dv_evader | 20 | capture:20 | 0.0 | 31 / 0 | 300.3 / 79.2 |
| lambert_pursuer | lazy_evader | 20 | capture:20 | 0.0 | 31 / 0 | 16.6 / 263.5 |
| rollout_pursuer | coast | 20 | escape:6, sma_out:14 | 223.3 | 25 / 0 | 105.2 / 0.0 |
| rollout_pursuer | dv_evader | 20 | escape:6, sma_out:14 | 223.3 | 25 / 0 | 106.9 / 66.5 |
| rollout_pursuer | lazy_evader | 20 | escape:6, sma_out:14 | 223.3 | 25 / 0 | 105.7 / 132.2 |
