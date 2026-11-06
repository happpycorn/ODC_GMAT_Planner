# 規則平衡掃描 balance_evader_dv_fuel

- 追者 `lambert_pursuer` vs 躲者 `dv_evader`，每格 24 局（同一批 `mixed` 幾何）
- 基底規則：`{"window_sec": 300.0, "max_dv_pursuer_mps": 1500.0, "max_dv_evader_mps": 1500.0, "fuel_pursuer_mps": 3000.0, "fuel_evader_mps": 3000.0, "capture_radius_km": 5.0, "t_max_sec": 0.0, "t_max_periods": 4.0, "gravity_degree": 2, "first_mover": "pursuer", "crash_altitude_km": 100.0, "substep_sec": 60.0}`

格內：追者勝率 [95% 區間]（最近距離中位數 km）

| max_dv_evader_mps \ fuel_evader_mps | 750.0 | 1500.0 | 3000.0 |
|---|---|---|---|
| 150.0 | 67% [47–82] (0) | 46% [28–65] (303) | 8% [2–26] (785) |
| 375.0 | 75% [55–88] (0) | 79% [60–91] (0) | 38% [21–57] (1478) |
| 750.0 | 83% [64–93] (0) | 67% [47–82] (0) | 38% [21–57] (760) |
| 1500.0 | 83% [64–93] (0) | 62% [43–79] (0) | 21% [9–40] (933) |
