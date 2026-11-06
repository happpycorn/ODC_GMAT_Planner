# Tournament rollout_eval_official_geom

- **rules**: ranges
- **scenario**: official_sample
- **games per pairing**: 30
- **seed**: 0

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | coast | dv_evader | rollout_evader | 平均 |
|---|---|---|---|---|
| lambert_pursuer | 27% [14–44] | 7% [2–21] | 7% [2–21] | 13% |
| rollout_pursuer | 50% [33–67] | 23% [12–41] | 17% [7–34] | 30% |
| **躲者平均存活** | 62% | 85% | 88% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | coast | 30 | capture:8, timeout:22 | 263.9 | 1736 / 0 | 6.2 / 0.0 |
| lambert_pursuer | dv_evader | 30 | capture:2, timeout:28 | 4961.5 | 2071 / 1797 | 4.9 / 8.6 |
| lambert_pursuer | rollout_evader | 30 | capture:2, crash_pursuer:2, timeout:26 | 1870.4 | 2055 / 1088 | 5.3 / 163.2 |
| rollout_pursuer | coast | 30 | capture:15, timeout:15 | 4.8 | 972 / 0 | 127.5 / 0.0 |
| rollout_pursuer | dv_evader | 30 | capture:7, timeout:23 | 2683.9 | 1002 / 1797 | 77.0 / 8.0 |
| rollout_pursuer | rollout_evader | 30 | capture:5, timeout:25 | 900.6 | 1305 / 1078 | 84.3 / 152.9 |
