# 規則平衡掃描 balance_pursuer_dv_fuel

- 追者 `lambert_pursuer` vs 躲者 `dv_evader`，每格 24 局（同一批 `mixed` 幾何）
- 基底規則：`{"window_sec": 300.0, "max_dv_pursuer_mps": 1500.0, "max_dv_evader_mps": 1500.0, "fuel_pursuer_mps": 3000.0, "fuel_evader_mps": 3000.0, "capture_radius_km": 5.0, "t_max_sec": 0.0, "t_max_periods": 4.0, "gravity_degree": 2, "first_mover": "pursuer", "crash_altitude_km": 100.0, "substep_sec": 60.0, "capture_mode": "continuous"}`

格內：追者勝率 [95% 區間]（最近距離中位數 km）

| max_dv_pursuer_mps \ fuel_pursuer_mps | 1500.0 | 3000.0 | 6000.0 |
|---|---|---|---|
| 300.0 | 8% [2–26] (1116) | 29% [15–49] (933) | 33% [18–53] (845) |
| 750.0 | 0% [0–14] (1460) | 12% [4–31] (933) | 62% [43–79] (0) |
| 1500.0 | 0% [0–14] (1736) | 21% [9–40] (933) | 88% [69–96] (0) |
