# Tournament plazy_screen1_e1500_s1

- **rules**: /tmp/claude-1000/-home-corn-ODC-GMAT-DRL/efe6e979-35f3-446d-a651-9f3d3c9ef88b/scratchpad/rules/ranking_evader1500.json
- **scenario**: mixed
- **games per pairing**: 12
- **seed**: 1

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | py:agents.evader_lab:LazyEvader3 | 平均 |
|---|---|---|
| rollout_pursuer | 0% [0–24] | 0% |
| py:agents.pursuer_lab:HarassPursuer | 17% [5–45] | 17% |
| **躲者平均存活** | 92% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| rollout_pursuer | py:agents.evader_lab:LazyEvader3 | 12 | timeout:12 | 41.6 | 1056 / 717 | 152.6 / 2.8 |
| py:agents.pursuer_lab:HarassPursuer | py:agents.evader_lab:LazyEvader3 | 12 | capture:2, timeout:10 | 23.7 | 2227 / 1292 | 899.8 / 4.8 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 8 | 0% |
| near_coplanar | 16 | 12% |
