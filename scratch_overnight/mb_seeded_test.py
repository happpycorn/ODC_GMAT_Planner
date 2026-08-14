import sys, time, json
sys.path.insert(0, "/Users/corn/Documents/Program/ODC_Program")
import numpy as np
from src.optimizer import MissionOptimizer

config = json.load(open("/Users/corn/Documents/Program/ODC_Program/configs/weird_test.json"))

# 先確認單棒(有種子)迴歸沒壞
config1 = dict(config); config1["optimization"] = dict(config["optimization"])
config1["optimization"]["MAX_BURNS"] = [1]
config1["optimization"]["MAXITER"] = 300
config1["optimization"]["POPSIZE"] = 10
config1["optimization"]["MAX_EARLY_STOP"] = 300
opt1 = MissionOptimizer(config1)
scalar_params1 = np.array([
    opt1.MIN_COAST_TIME, opt1.T_max, opt1.MU, opt1.J2_VAL, opt1.J3_VAL, opt1.J4_VAL,
    opt1.RE_VAL, opt1.MIN_PERIAPSIS, opt1.MAX_DV_SOFT, opt1.k_t, opt1.C_t, opt1.k_v, opt1.C_v
], dtype=np.float64)
vector_params1 = np.vstack([opt1.A_r0, opt1.A_v0, opt1.B_r0, opt1.B_v0])
t0 = time.time()
r1 = opt1._optimize_burn_case(1, scalar_params1, vector_params1, progress_queue=None)
print(f"[迴歸-單棒] 分數={r1[2]:.4f} 代數={r1[3]} 耗時={time.time()-t0:.1f}s note={r1[4]}")

# 多棒 (2棒) 有種子版本
config2 = dict(config); config2["optimization"] = dict(config["optimization"])
config2["optimization"]["MAX_BURNS"] = [2]
config2["optimization"]["MAXITER"] = 300
config2["optimization"]["POPSIZE"] = 10
config2["optimization"]["MAX_EARLY_STOP"] = 300
opt2 = MissionOptimizer(config2)

seeds = opt2._generate_seed_candidates(2, 5)
print(f"\n2棒種子數: {len(seeds)}")
for s in seeds:
    print(f"  {s}")

scalar_params2 = np.array([
    opt2.MIN_COAST_TIME, opt2.T_max, opt2.MU, opt2.J2_VAL, opt2.J3_VAL, opt2.J4_VAL,
    opt2.RE_VAL, opt2.MIN_PERIAPSIS, opt2.MAX_DV_SOFT, opt2.k_t, opt2.C_t, opt2.k_v, opt2.C_v
], dtype=np.float64)
vector_params2 = np.vstack([opt2.A_r0, opt2.A_v0, opt2.B_r0, opt2.B_v0])
t0 = time.time()
r2 = opt2._optimize_burn_case(2, scalar_params2, vector_params2, progress_queue=None)
print(f"\n[2棒-有種子] 分數={r2[2]:.4f} 代數={r2[3]} 耗時={time.time()-t0:.1f}s note={r2[4]}")
print(f"解: {r2[1]}")
print(f"\n=== 對照 ===")
print(f"1棒(有種子): {r1[2]:.4f}")
print(f"2棒(無種子,先前baseline): -64.3348")
print(f"2棒(有種子): {r2[2]:.4f}")
