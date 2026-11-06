# 已部署模型（2026-09-16 01:02）

## pursuer: `runs/sp3/pursuer_it04.zip`（it4，訓練平均勝率 57%）

訓練中評測：coast=83%, dv_evader_fast=42%, dv_evader=46%

### 確認評測 pursuer

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | coast | dv_evader_fast | dv_evader | 平均 |
|---|---|---|---|---|
| sb3:runs/sp3/pursuer_it04.zip | 78% [62–88] | 40% [26–55] | 42% [29–58] | 53% |
| lambert_pursuer | 82% [68–91] | 40% [26–55] | 40% [26–55] | 54% |
| **躲者平均存活** | 20% | 60% | 59% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| sb3:runs/sp3/pursuer_it04.zip | coast | 40 | capture:31, crash_pursuer:1, timeout:8 | 0.0 | 503 / 0 | 125.8 / 0.0 |
| sb3:runs/sp3/pursuer_it04.zip | dv_evader_fast | 40 | capture:16, timeout:24 | 182.1 | 1799 / 1681 | 31.8 / 5.9 |
| sb3:runs/sp3/pursuer_it04.zip | dv_evader | 40 | capture:16, crash_evader:1, timeout:23 | 297.8 | 1916 / 1682 | 33.1 / 16.6 |
| lambert_pursuer | coast | 40 | capture:33, timeout:7 | 0.0 | 492 / 0 | 88.0 / 0.0 |
| lambert_pursuer | dv_evader_fast | 40 | capture:16, timeout:24 | 113.9 | 1893 / 1689 | 31.6 / 19.3 |
| lambert_pursuer | dv_evader | 40 | capture:15, crash_evader:1, crash_pursuer:1, timeout:23 | 449.7 | 1934 / 1661 | 19.1 / 23.0 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 72 | 47% |
| near_coplanar | 126 | 70% |
| wild | 42 | 17% |

## evader: `runs/sp3/evader_it08.zip`（it8，訓練平均勝率 54%）

訓練中評測：lambert_pursuer=54%, lambert_pursuer(time_weight_mps=60.0)=54%

### 確認評測 evader

## 追者勝率（捕獲 + 躲者撞地），列 = 追者、欄 = 躲者

| 追者 \ 躲者 | sb3:runs/sp3/evader_it08.zip | dv_evader | 平均 |
|---|---|---|---|
| lambert_pursuer | 42% [29–58] | 40% [26–55] | 41% |
| lambert_pursuer(time_weight_mps=60.0) | 38% [24–53] | 35% [22–50] | 36% |
| **躲者平均存活** | 60% | 62% | |

## 細節

| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |
|---|---|---|---|---|---|---|
| lambert_pursuer | sb3:runs/sp3/evader_it08.zip | 40 | capture:12, crash_evader:5, timeout:23 | 468.1 | 1858 / 1597 | 60.1 / 4.5 |
| lambert_pursuer | dv_evader | 40 | capture:15, crash_evader:1, crash_pursuer:1, timeout:23 | 449.7 | 1934 / 1661 | 44.7 / 17.7 |
| lambert_pursuer(time_weight_mps=60.0) | sb3:runs/sp3/evader_it08.zip | 40 | capture:8, crash_evader:7, timeout:25 | 611.6 | 1953 / 1652 | 41.0 / 4.1 |
| lambert_pursuer(time_weight_mps=60.0) | dv_evader | 40 | capture:13, crash_evader:1, crash_pursuer:1, timeout:25 | 449.7 | 1990 / 1678 | 49.0 / 19.0 |

## 依幾何家族的追者勝率（所有配對平均）

| 家族 | n | 追者勝率 |
|---|---|---|
| inclined | 48 | 33% |
| near_coplanar | 84 | 52% |
| wild | 28 | 7% |

