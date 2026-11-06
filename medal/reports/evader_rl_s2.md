# Tournament evader_rl_s2

- **rules**: configs/rulesets/ranking_like.json
- **scenario**: mixed
- **games per pairing**: 24
- **seed**: 2
- **note**: STRONG = 強化版 rollout 追者（copilot STRONG_ROLLOUT_PURSUER，E16）；部分局由 scratch subset runner 補跑，與 evaluate.py 同 seed/games 逐局相同

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | py:agents.evader_lab:LazyEvader2 | py:agents.evader_lab:LazyEvader3 | rollout_evader | 平均 |
|---|---|---|---|---|
| lambert_pursuer | 0% [0–14] | 0% [0–14] | 29% [15–49] | 10% |
| rollout_pursuer | 0% [0–14] | 0% [0–14] | 25% [12–45] | 8% |
| STRONG | 0% [0–14] | 0% [0–24] | 42% [24–61] | 14% |
| rollout_pursuer(opponents=['py:agents.evader_lab:LazyEvader2']) | 4% [1–20] | nan% [nan–nan] | nan% [nan–nan] | nan% |
| rollout_pursuer(opponents=['py:agents.evader_lab:LazyEvader3']) | nan% [nan–nan] | 0% [0–24] | nan% [nan–nan] | nan% |
| **躲者平均存活** | nan% | nan% | nan% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | py:agents.evader_lab:LazyEvader2 | 24 | crash_pursuer:1, timeout:23 | 25.1 | 2726 / 802 | 4.1 / 3.7 |
| lambert_pursuer | py:agents.evader_lab:LazyEvader3 | 24 | crash_pursuer:1, timeout:23 | 29.5 | 2734 / 817 | 2.9 / 2.9 |
| lambert_pursuer | rollout_evader | 24 | capture:7, timeout:17 | 343.0 | 2721 / 2240 | 3.5 / 245.3 |
| rollout_pursuer | py:agents.evader_lab:LazyEvader2 | 24 | crash_pursuer:1, timeout:23 | 40.5 | 1048 / 552 | 204.1 / 3.0 |
| rollout_pursuer | py:agents.evader_lab:LazyEvader3 | 24 | crash_pursuer:1, timeout:23 | 40.5 | 1048 / 552 | 147.7 / 2.2 |
| rollout_pursuer | rollout_evader | 24 | capture:6, timeout:18 | 284.8 | 1453 / 2338 | 171.5 / 285.1 |
| STRONG | py:agents.evader_lab:LazyEvader2 | 24 | timeout:24 | 28.2 | 836 / 442 | 4296.1 / 2.7 |
| STRONG | py:agents.evader_lab:LazyEvader3 | 12 | timeout:12 | 38.0 | 884 / 375 | 2882.0 / 1.7 |
| STRONG | rollout_evader | 24 | capture:10, timeout:14 | 139.0 | 1390 / 2348 | 3967.0 / 357.7 |
| rollout_pursuer(opponents=['py:agents.evader_lab:LazyEvader2']) | py:agents.evader_lab:LazyEvader2 | 24 | crash_evader:1, timeout:23 | 14.3 | 1359 / 688 | 285.6 / 3.6 |
| rollout_pursuer(opponents=['py:agents.evader_lab:LazyEvader2']) | py:agents.evader_lab:LazyEvader3 | 0 |  | nan | nan / nan | nan / nan |
| rollout_pursuer(opponents=['py:agents.evader_lab:LazyEvader2']) | rollout_evader | 0 |  | nan | nan / nan | nan / nan |
| rollout_pursuer(opponents=['py:agents.evader_lab:LazyEvader3']) | py:agents.evader_lab:LazyEvader2 | 0 |  | nan | nan / nan | nan / nan |
| rollout_pursuer(opponents=['py:agents.evader_lab:LazyEvader3']) | py:agents.evader_lab:LazyEvader3 | 12 | timeout:12 | 9.8 | 1225 / 571 | 190.2 / 2.3 |
| rollout_pursuer(opponents=['py:agents.evader_lab:LazyEvader3']) | rollout_evader | 0 |  | nan | nan / nan | nan / nan |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 49 | 0% |
| near_coplanar | 118 | 20% |
| wild | 73 | 0% |
