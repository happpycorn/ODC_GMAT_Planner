# Tournament baseline_final_t3600

- **rules**: configs/rulesets/final_t3600.json
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
| lambert_pursuer | coast | 20 | capture:20 | 3.6 | 31 / 0 | 298.7 / 0.0 |
| lambert_pursuer | dv_evader | 20 | capture:20 | 3.6 | 31 / 5 | 299.9 / 82.5 |
| lambert_pursuer | lazy_evader | 20 | capture:20 | 3.6 | 31 / 5 | 17.8 / 272.4 |
| rollout_pursuer | coast | 20 | escape:6, sma_out:14 | 175.2 | 38 / 0 | 104.4 / 0.0 |
| rollout_pursuer | dv_evader | 20 | capture:3, escape:5, sma_out:12 | 163.2 | 38 / 30 | 162.5 / 73.0 |
| rollout_pursuer | lazy_evader | 20 | capture:3, escape:5, sma_out:12 | 163.2 | 38 / 30 | 163.6 / 133.8 |
