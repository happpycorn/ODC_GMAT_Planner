# Tournament baseline_final_corner_short

- **rules**: configs/rulesets/final_corner_short.json
- **scenario**: final
- **games per pairing**: 20
- **seed**: 0

## 追者勝率（捕獲 + 躲者撞地；同時出手賽制另含 sma_out），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | coast | dv_evader | lazy_evader | 平均 |
|---|---|---|---|---|
| lambert_pursuer | 100% [84–100] | 100% [84–100] | 100% [84–100] | 100% |
| rollout_pursuer | 70% [48–85] | 75% [53–89] | 75% [53–89] | 73% |
| **躲者平均存活** | 15% | 12% | 12% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | coast | 20 | capture:20 | 15.5 | 164 / 0 | 7.7 / 0.0 |
| lambert_pursuer | dv_evader | 20 | capture:11, sma_out:9 | 19.5 | 167 / 84 | 8.0 / 23.0 |
| lambert_pursuer | lazy_evader | 20 | capture:11, sma_out:9 | 19.7 | 167 / 79 | 10.0 / 15.9 |
| rollout_pursuer | coast | 20 | escape:6, sma_out:14 | 41.3 | 275 / 0 | 165.0 / 0.0 |
| rollout_pursuer | dv_evader | 20 | capture:2, escape:5, sma_out:13 | 41.3 | 270 / 7 | 114.8 / 21.9 |
| rollout_pursuer | lazy_evader | 20 | capture:1, escape:5, sma_out:14 | 41.3 | 275 / 2 | 69.8 / 3.7 |
