import sys, time, json
sys.path.insert(0, "/Users/corn/Documents/Program/ODC_Program")
import numpy as np
from src.optimizer import MissionOptimizer

config = json.load(open("/Users/corn/Documents/Program/ODC_Program/configs/weird_test.json"))
config["optimization"]["MAX_BURNS"] = [2]
config["optimization"]["MAXITER"] = 300
config["optimization"]["POPSIZE"] = 10
config["optimization"]["MAX_EARLY_STOP"] = 300
opt = MissionOptimizer(config)
print(f"T_max={opt.T_max:.0f}s ({opt.T_max/86400:.2f}天)")

scalar_params = np.array([
    opt.MIN_COAST_TIME, opt.T_max, opt.MU, opt.J2_VAL, opt.J3_VAL, opt.J4_VAL,
    opt.RE_VAL, opt.MIN_PERIAPSIS, opt.MAX_DV_SOFT, opt.k_t, opt.C_t, opt.k_v, opt.C_v
], dtype=np.float64)
vector_params = np.vstack([opt.A_r0, opt.A_v0, opt.B_r0, opt.B_v0])

t0 = time.time()
result = opt._optimize_burn_case(2, scalar_params, vector_params, progress_queue=None)
elapsed = time.time() - t0
_, best_x, best_score, epochs_run, note = result
print(f"[weird_test 2棒 baseline(無種子)] 分數={best_score:.4f}  代數={epochs_run}  耗時={elapsed:.1f}s  note={note}")
print(f"解: {best_x}")
np.save("/Users/corn/Documents/Program/ODC_Program/scratch_overnight/mb_baseline_weird_x.npy", best_x)
