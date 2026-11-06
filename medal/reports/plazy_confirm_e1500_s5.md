# Tournament plazy_confirm_e1500_s5

- **rules**: /tmp/claude-1000/-home-corn-ODC-GMAT-DRL/efe6e979-35f3-446d-a651-9f3d3c9ef88b/scratchpad/rules/ranking_evader1500.json
- **scenario**: mixed
- **games per pairing**: 24
- **seed**: 5

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | py:agents.evader_lab:LazyEvader3 | 平均 |
|---|---|---|
| rollout_pursuer | 0% [0–14] | 0% |
| py:agents.pursuer_lab:LazyHunter | 8% [2–26] | 8% |
| **躲者平均存活** | 96% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| rollout_pursuer | py:agents.evader_lab:LazyEvader3 | 24 | timeout:24 | 30.5 | 1186 / 725 | 196.8 / 4.4 |
| py:agents.pursuer_lab:LazyHunter | py:agents.evader_lab:LazyEvader3 | 24 | capture:2, timeout:22 | 47.1 | 2378 / 1006 | 1112.5 / 5.8 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 20 | 5% |
| near_coplanar | 22 | 5% |
| wild | 6 | 0% |
