# Tournament evader_rl_s1

- **rules**: configs/rulesets/ranking_like.json
- **scenario**: mixed
- **games per pairing**: 24
- **seed**: 1
- **note**: STRONG = 強化版 rollout 追者（copilot STRONG_ROLLOUT_PURSUER，E16）；部分局由 scratch subset runner 補跑，與 evaluate.py 同 seed/games 逐局相同

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | py:agents.evader_lab:LazyEvader | py:agents.evader_lab:LazyEvader2 | py:agents.evader_lab:ReserveRolloutEvader | rollout_evader | 平均 |
|---|---|---|---|---|---|
| lambert_pursuer | 0% [0–14] | 0% [0–14] | 0% [0–14] | 46% [28–65] | 11% |
| rollout_pursuer | 0% [0–14] | 0% [0–14] | 0% [0–14] | 29% [15–49] | 7% |
| STRONG | 0% [0–14] | 0% [0–14] | 4% [1–20] | 71% [51–85] | 19% |
| rollout_pursuer(opponents=['py:agents.evader_lab:LazyEvader']) | 12% [4–31] | nan% [nan–nan] | nan% [nan–nan] | 42% [24–61] | nan% |
| rollout_pursuer(opponents=['py:agents.evader_lab:LazyEvader2']) | nan% [nan–nan] | 0% [0–14] | nan% [nan–nan] | nan% [nan–nan] | nan% |
| **躲者平均存活** | nan% | nan% | nan% | nan% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | py:agents.evader_lab:LazyEvader | 24 | timeout:24 | 31.3 | 2555 / 810 | 5.0 / 3.8 |
| lambert_pursuer | py:agents.evader_lab:LazyEvader2 | 24 | timeout:24 | 36.9 | 2571 / 831 | 3.5 / 4.0 |
| lambert_pursuer | py:agents.evader_lab:ReserveRolloutEvader | 24 | timeout:24 | 64.2 | 2998 / 1495 | 4.6 / 1152.8 |
| lambert_pursuer | rollout_evader | 24 | capture:11, timeout:13 | 54.6 | 2629 / 2698 | 16.1 / 188.6 |
| rollout_pursuer | py:agents.evader_lab:LazyEvader | 24 | timeout:24 | 37.4 | 807 / 525 | 287.5 / 2.5 |
| rollout_pursuer | py:agents.evader_lab:LazyEvader2 | 24 | timeout:24 | 37.5 | 844 / 529 | 209.5 / 2.9 |
| rollout_pursuer | py:agents.evader_lab:ReserveRolloutEvader | 24 | timeout:24 | 155.0 | 1506 / 2021 | 239.9 / 1133.1 |
| rollout_pursuer | rollout_evader | 24 | capture:7, timeout:17 | 928.3 | 1347 / 2446 | 143.7 / 235.3 |
| STRONG | py:agents.evader_lab:LazyEvader | 24 | timeout:24 | 27.4 | 910 / 508 | 4226.0 / 2.3 |
| STRONG | py:agents.evader_lab:LazyEvader2 | 24 | timeout:24 | 31.6 | 920 / 504 | 4764.2 / 3.8 |
| STRONG | py:agents.evader_lab:ReserveRolloutEvader | 24 | capture:1, timeout:23 | 78.3 | 1241 / 1817 | 4022.7 / 1126.1 |
| STRONG | rollout_evader | 24 | capture:17, timeout:7 | 0.0 | 1721 / 2771 | 2047.5 / 210.7 |
| rollout_pursuer(opponents=['py:agents.evader_lab:LazyEvader']) | py:agents.evader_lab:LazyEvader | 24 | capture:3, timeout:21 | 11.3 | 1363 / 683 | 311.1 / 3.4 |
| rollout_pursuer(opponents=['py:agents.evader_lab:LazyEvader']) | py:agents.evader_lab:LazyEvader2 | 0 |  | nan | nan / nan | nan / nan |
| rollout_pursuer(opponents=['py:agents.evader_lab:LazyEvader']) | py:agents.evader_lab:ReserveRolloutEvader | 0 |  | nan | nan / nan | nan / nan |
| rollout_pursuer(opponents=['py:agents.evader_lab:LazyEvader']) | rollout_evader | 24 | capture:10, timeout:14 | 20.8 | 2274 / 2448 | 201.2 / 353.0 |
| rollout_pursuer(opponents=['py:agents.evader_lab:LazyEvader2']) | py:agents.evader_lab:LazyEvader | 0 |  | nan | nan / nan | nan / nan |
| rollout_pursuer(opponents=['py:agents.evader_lab:LazyEvader2']) | py:agents.evader_lab:LazyEvader2 | 24 | timeout:24 | 12.3 | 1354 / 660 | 296.0 / 3.3 |
| rollout_pursuer(opponents=['py:agents.evader_lab:LazyEvader2']) | py:agents.evader_lab:ReserveRolloutEvader | 0 |  | nan | nan / nan | nan / nan |
| rollout_pursuer(opponents=['py:agents.evader_lab:LazyEvader2']) | rollout_evader | 0 |  | nan | nan / nan | nan / nan |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 135 | 9% |
| near_coplanar | 180 | 19% |
| wild | 45 | 4% |
