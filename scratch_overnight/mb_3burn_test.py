import sys, time, json
sys.path.insert(0, "/Users/corn/Documents/Program/ODC_Program")
import numpy as np
from src.optimizer import MissionOptimizer

config = json.load(open("/Users/corn/Documents/Program/ODC_Program/configs/weird_test.json"))

def run(num_burns, use_seed_label):
    cfg = dict(config); cfg["optimization"] = dict(config["optimization"])
    cfg["optimization"]["MAX_BURNS"] = [num_burns]
    cfg["optimization"]["MAXITER"] = 300
    cfg["optimization"]["POPSIZE"] = 10
    cfg["optimization"]["MAX_EARLY_STOP"] = 300
    opt = MissionOptimizer(cfg)
    scalar_params = np.array([
        opt.MIN_COAST_TIME, opt.T_max, opt.MU, opt.J2_VAL, opt.J3_VAL, opt.J4_VAL,
        opt.RE_VAL, opt.MIN_PERIAPSIS, opt.MAX_DV_SOFT, opt.k_t, opt.C_t, opt.k_v, opt.C_v
    ], dtype=np.float64)
    vector_params = np.vstack([opt.A_r0, opt.A_v0, opt.B_r0, opt.B_v0])
    t0 = time.time()
    r = opt._optimize_burn_case(num_burns, scalar_params, vector_params, progress_queue=None)
    elapsed = time.time() - t0
    print(f"[{num_burns}棒-{use_seed_label}] 分數={r[2]:.4f} 代數={r[3]} 耗時={elapsed:.1f}s note={r[4]}")
    return r[2]

s3 = run(3, "有種子(現行程式碼)")
