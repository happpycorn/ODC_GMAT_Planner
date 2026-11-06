# Tournament copilot_evader_vs_rollout_ranking_like

- **rules**: configs/rulesets/ranking_like.json
- **scenario**: mixed
- **games per pairing**: 12
- **seed**: 1

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | py:agents.copilot_agent:CopilotAgent | lazy_evader | 平均 |
|---|---|---|---|
| rollout_pursuer | 0% [0–24] | 0% [0–24] | 0% |
| **躲者平均存活** | 100% | 100% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| rollout_pursuer | py:agents.copilot_agent:CopilotAgent | 12 | timeout:12 | 37.4 | 986 / 625 | 200.7 / 5808.1 |
| rollout_pursuer | lazy_evader | 12 | timeout:12 | 37.4 | 986 / 625 | 201.3 / 2.9 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 8 | 0% |
| near_coplanar | 16 | 0% |
