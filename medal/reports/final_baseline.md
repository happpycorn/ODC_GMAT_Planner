# Tournament final_baseline

- **rules**: configs/rulesets/final_official.json
- **scenario**: final
- **games per pairing**: 40
- **seed**: 0

## 追者勝率（捕獲 + 躲者撞地；同時出手賽制另含 sma_out），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | coast | random | dv_evader | lazy_evader | rollout_evader | 平均 |
|---|---|---|---|---|---|---|
| lambert_pursuer | 100% [91–100] | 95% [83–99] | 100% [91–100] | 100% [91–100] | 100% [91–100] | 99% |
| rollout_pursuer | 72% [57–84] | 90% [77–96] | 75% [60–86] | 75% [60–86] | 75% [60–86] | 78% |
| **躲者平均存活** | 14% | 7% | 12% | 12% | 12% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | coast | 40 | capture:40 | 3.3 | 50 / 0 | 6.0 / 0.0 |
| lambert_pursuer | random | 40 | capture:20, crash_evader:2, escape:2, sma_out:16 | 10.0 | 362 / 271 | 5.2 / 0.0 |
| lambert_pursuer | dv_evader | 40 | capture:38, sma_out:2 | 3.4 | 50 / 38 | 4.3 / 40.7 |
| lambert_pursuer | lazy_evader | 40 | capture:38, sma_out:2 | 3.4 | 50 / 38 | 6.1 / 95.7 |
| lambert_pursuer | rollout_evader | 40 | capture:40 | 3.3 | 50 / 0 | 4.3 / 137.8 |
| rollout_pursuer | coast | 40 | escape:11, sma_out:29 | 120.9 | 212 / 0 | 89.1 / 0.0 |
| rollout_pursuer | random | 40 | crash_evader:2, escape:4, sma_out:34 | 175.2 | 156 / 293 | 60.3 / 0.1 |
| rollout_pursuer | dv_evader | 40 | capture:1, escape:10, sma_out:29 | 120.9 | 206 / 2 | 60.8 / 34.9 |
| rollout_pursuer | lazy_evader | 40 | capture:1, escape:10, sma_out:29 | 120.9 | 206 / 2 | 56.7 / 21.1 |
| rollout_pursuer | rollout_evader | 40 | capture:1, escape:10, sma_out:29 | 120.9 | 206 / 6 | 56.7 / 52.5 |
