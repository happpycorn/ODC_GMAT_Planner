# Tournament plazy_confirm_rl_s5

- **rules**: configs/rulesets/ranking_like.json
- **scenario**: mixed
- **games per pairing**: 24
- **seed**: 5

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | py:agents.evader_lab:LazyEvader3 | rollout_evader | dv_evader | 平均 |
|---|---|---|---|---|
| rollout_pursuer | 0% [0–14] | 29% [15–49] | 83% [64–93] | 38% |
| py:agents.pursuer_lab:LazyHunter | 0% [0–14] | 29% [15–49] | 83% [64–93] | 38% |
| **躲者平均存活** | 100% | 71% | 17% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| rollout_pursuer | py:agents.evader_lab:LazyEvader3 | 24 | timeout:24 | 37.3 | 1125 / 546 | 207.1 / 3.0 |
| rollout_pursuer | rollout_evader | 24 | capture:7, timeout:17 | 744.0 | 1587 / 2504 | 167.5 / 257.3 |
| rollout_pursuer | dv_evader | 24 | capture:20, timeout:4 | 0.0 | 1983 / 3000 | 145.1 / 11.6 |
| py:agents.pursuer_lab:LazyHunter | py:agents.evader_lab:LazyEvader3 | 24 | crash_pursuer:1, timeout:23 | 47.5 | 2460 / 1090 | 971.8 / 5.2 |
| py:agents.pursuer_lab:LazyHunter | rollout_evader | 24 | capture:7, timeout:17 | 771.1 | 1693 / 2588 | 179.5 / 253.8 |
| py:agents.pursuer_lab:LazyHunter | dv_evader | 24 | capture:20, timeout:4 | 0.0 | 1983 / 3000 | 138.2 / 11.6 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 60 | 38% |
| near_coplanar | 66 | 44% |
| wild | 18 | 11% |
