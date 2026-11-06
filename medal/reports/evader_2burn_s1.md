# Tournament evader_2burn_s1

- **rules**: configs/rulesets/ranking_like_2burn.json
- **scenario**: mixed
- **games per pairing**: 24
- **seed**: 1
- **note**: STRONG = 強化版 rollout 追者（copilot STRONG_ROLLOUT_PURSUER，E16）；部分局由 scratch subset runner 補跑，與 evaluate.py 同 seed/games 逐局相同

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | py:agents.evader_lab:LazyEvader2 | rollout_evader | 平均 |
|---|---|---|---|
| lambert_pursuer | 0% [0–14] | 50% [31–69] | 25% |
| rollout_pursuer | 0% [0–14] | 83% [64–93] | 42% |
| **躲者平均存活** | 100% | 33% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | py:agents.evader_lab:LazyEvader2 | 24 | timeout:24 | 41.2 | 2949 / 1177 | 6.5 / 5.8 |
| lambert_pursuer | rollout_evader | 24 | capture:12, timeout:12 | 4.9 | 2462 / 2804 | 6.0 / 575.9 |
| rollout_pursuer | py:agents.evader_lab:LazyEvader2 | 24 | crash_pursuer:1, timeout:23 | 48.5 | 1651 / 908 | 566.4 / 5.1 |
| rollout_pursuer | rollout_evader | 24 | capture:20, timeout:4 | 0.0 | 2104 / 2906 | 623.8 / 768.1 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 36 | 22% |
| near_coplanar | 48 | 46% |
| wild | 12 | 17% |
