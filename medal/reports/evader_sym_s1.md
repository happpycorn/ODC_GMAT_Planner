# Tournament evader_sym_s1

- **rules**: configs/rulesets/symmetric.json
- **scenario**: mixed
- **games per pairing**: 24
- **seed**: 1
- **note**: STRONG = 強化版 rollout 追者（copilot STRONG_ROLLOUT_PURSUER，E16）；部分局由 scratch subset runner 補跑，與 evaluate.py 同 seed/games 逐局相同

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | py:agents.evader_lab:LazyEvader2 | py:agents.evader_lab:LazyEvader3 | rollout_evader | 平均 |
|---|---|---|---|---|
| lambert_pursuer | 8% [2–26] | 4% [1–20] | 0% [0–14] | 4% |
| rollout_pursuer | 12% [4–31] | 12% [4–31] | 58% [39–76] | 28% |
| STRONG | nan% [nan–nan] | nan% [nan–nan] | 50% [24–76] | nan% |
| **躲者平均存活** | nan% | nan% | 64% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | py:agents.evader_lab:LazyEvader2 | 24 | capture:1, crash_evader:1, timeout:22 | 289.2 | 3000 / 2562 | 3.3 / 1.7 |
| lambert_pursuer | py:agents.evader_lab:LazyEvader3 | 24 | capture:1, timeout:23 | 282.0 | 3000 / 2562 | 2.4 / 1.5 |
| lambert_pursuer | rollout_evader | 24 | timeout:24 | 743.9 | 3000 / 2938 | 2.4 / 95.0 |
| rollout_pursuer | py:agents.evader_lab:LazyEvader2 | 24 | capture:2, crash_evader:1, timeout:21 | 259.8 | 1745 / 2500 | 106.4 / 1.7 |
| rollout_pursuer | py:agents.evader_lab:LazyEvader3 | 24 | capture:3, timeout:21 | 259.8 | 1898 / 2500 | 75.9 / 1.5 |
| rollout_pursuer | rollout_evader | 24 | capture:14, timeout:10 | 0.0 | 1887 / 2875 | 106.7 / 104.0 |
| STRONG | py:agents.evader_lab:LazyEvader2 | 0 |  | nan | nan / nan | nan / nan |
| STRONG | py:agents.evader_lab:LazyEvader3 | 0 |  | nan | nan / nan | nan / nan |
| STRONG | rollout_evader | 10 | capture:5, timeout:5 | 245.0 | 1587 / 3000 | 1654.1 / 132.6 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 57 | 11% |
| near_coplanar | 79 | 27% |
| wild | 18 | 6% |
