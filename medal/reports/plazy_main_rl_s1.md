# Tournament plazy_main_rl_s1

- **rules**: configs/rulesets/ranking_like.json
- **scenario**: mixed
- **games per pairing**: 12
- **seed**: 1

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | py:agents.evader_lab:LazyEvader3 | rollout_evader | dv_evader | 平均 |
|---|---|---|---|---|
| rollout_pursuer | 0% [0–24] | 42% [19–68] | 75% [47–91] | 39% |
| py:agents.pursuer_lab:LazyHunter | 0% [0–24] | 33% [14–61] | 75% [47–91] | 36% |
| **躲者平均存活** | 100% | 62% | 25% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| rollout_pursuer | py:agents.evader_lab:LazyEvader3 | 12 | timeout:12 | 37.4 | 986 / 625 | 170.7 / 2.5 |
| rollout_pursuer | rollout_evader | 12 | capture:5, timeout:7 | 488.5 | 1358 / 2625 | 135.8 / 195.3 |
| rollout_pursuer | dv_evader | 12 | capture:9, timeout:3 | 0.0 | 1960 / 3000 | 112.5 / 8.5 |
| py:agents.pursuer_lab:LazyHunter | py:agents.evader_lab:LazyEvader3 | 12 | timeout:12 | 59.1 | 2388 / 1300 | 777.8 / 4.3 |
| py:agents.pursuer_lab:LazyHunter | rollout_evader | 12 | capture:4, timeout:8 | 488.5 | 1353 / 2625 | 142.7 / 194.2 |
| py:agents.pursuer_lab:LazyHunter | dv_evader | 12 | capture:9, timeout:3 | 0.0 | 1960 / 3000 | 98.5 / 8.4 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 24 | 33% |
| near_coplanar | 48 | 40% |
