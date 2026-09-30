import sys, time, json
sys.path.insert(0, "/Users/corn/Documents/Program/ODC_Program")
import numpy as np
from src.optimizer import MissionOptimizer

# 用今晚較快算的 INC=90 案例 (單棒 legal, Dv~326m/s, 窗寬220s) 當多棒開發用的快速測試案例
config = {
    "orbit_A": {"SMA": 9375.0, "ECC": 0.2, "INC": 90.0, "RAAN": 0.0, "AOP": 0.0, "TA": 0.0},
    "orbit_B": {"SMA": 6800.0, "ECC": 0.001, "INC": 0.0, "RAAN": 0.0, "AOP": 0.0, "TA": 200.0},
    "rules": {"MAX_DV_MPS": 1500.0, "MIN_MANEUVER_INTERVAL_SEC": 100.0, "T_MAX_PERIOD_MULTIPLE": 4.0,
              "k_t": 0.000002, "C_t": 1800000.0, "k_v": 0.05, "C_v": 1200.0},
    "strategy": {"GRAVITY_DEGREE": 4, "MISS_TOLERANCE_KM": 5.0},
    "optimization": {"MAX_BURNS": [2], "MAXITER": 300, "POPSIZE": 15, "NUM_THREADS": -1,
                      "MAX_EARLY_STOP": 300, "TOL": 0.0001, "SEED": None}
}
opt = MissionOptimizer(config)
print(f"T_max={opt.T_max:.0f}s")

scalar_params = np.array([
    opt.MIN_COAST_TIME, opt.T_max, opt.MU, opt.J2_VAL, opt.J3_VAL, opt.J4_VAL,
    opt.RE_VAL, opt.MIN_PERIAPSIS, opt.MAX_DV_SOFT, opt.k_t, opt.C_t, opt.k_v, opt.C_v
], dtype=np.float64)
vector_params = np.vstack([opt.A_r0, opt.A_v0, opt.B_r0, opt.B_v0])

t0 = time.time()
result = opt._optimize_burn_case(2, scalar_params, vector_params, progress_queue=None)
elapsed = time.time() - t0
_, best_x, best_score, epochs_run, note = result
print(f"[Baseline 2棒, 無種子] 分數={best_score:.4f}  代數={epochs_run}  耗時={elapsed:.1f}s  note={note}")
print(f"解: {best_x}")
