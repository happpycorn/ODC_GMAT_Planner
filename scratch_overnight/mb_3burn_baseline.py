import sys, time, json
sys.path.insert(0, "/Users/corn/Documents/Program/ODC_Program")
import numpy as np
from src.optimizer import MissionOptimizer, fast_fitness_evaluator
from mealpy.evolutionary_based.SHADE import L_SHADE
from mealpy import FloatVar

config = json.load(open("/Users/corn/Documents/Program/ODC_Program/configs/weird_test.json"))
cfg = dict(config); cfg["optimization"] = dict(config["optimization"])
cfg["optimization"]["MAX_BURNS"] = [3]
opt = MissionOptimizer(cfg)
scalar_params = np.array([
    opt.MIN_COAST_TIME, opt.T_max, opt.MU, opt.J2_VAL, opt.J3_VAL, opt.J4_VAL,
    opt.RE_VAL, opt.MIN_PERIAPSIS, opt.MAX_DV_SOFT, opt.k_t, opt.C_t, opt.k_v, opt.C_v
], dtype=np.float64)
vector_params = np.vstack([opt.A_r0, opt.A_v0, opt.B_r0, opt.B_v0])

def fitness_wrapper(solution):
    return fast_fitness_evaluator(np.asarray(solution, dtype=np.float64), 3, scalar_params, vector_params)

lb, ub = opt._generate_bounds(3)
pop_size = max(30, len(lb) * 10)
problem = {"obj_func": fitness_wrapper, "bounds": [FloatVar(lb=l, ub=u) for l, u in zip(lb, ub)],
           "minmax": "min", "log_to": None}
model = L_SHADE(epoch=300, pop_size=pop_size, termination={"max_early_stop": 300, "epsilon": 0.0001})
t0 = time.time()
g_best = model.solve(problem, mode="thread", n_workers=6)
print(f"[3棒-無種子baseline] 分數={g_best.target.fitness:.4f} 耗時={time.time()-t0:.1f}s pop_size={pop_size}")
