"""
2026-08-15 補測：夜間 seeded-init 開發 (見 STATUS.md「夜間自主開發」一節) 的
A/B 對照表原本只在縮減預算 (MAXITER=300, POPSIZE=10) 下測過，這支腳本用
configs/weird_test.json 裡真正的正式預算 (MAXITER=1000, POPSIZE=20,
MAX_EARLY_STOP=40, TOL=0.02) 重新跑一次同一組對照 (1/2/3 棒，有種子 vs
無種子 baseline)，確認結論在完整搜尋預算下依然成立。

跟原本 scratch_overnight/mb_*.py 系列腳本方法論一致：
- 「有種子」= 直接呼叫 MissionOptimizer._optimize_burn_case()（正式路徑，
  種子生成是內建行為）。
- 「無種子 baseline」= 手動重現 _optimize_burn_case 內部的 L_SHADE 呼叫，
  但 starting_solutions=None，跳過 _generate_seed_candidates。

跟原始腳本的差異：這裡改用相對路徑 (repo root)，不是寫死的 Mac 路徑，
因為這次是在另一台機器 (WSL, 5800X) 上跑的。
"""
import sys, os, time, json
import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from src.optimizer import MissionOptimizer, fast_fitness_evaluator
from mealpy.evolutionary_based.SHADE import L_SHADE
from mealpy import FloatVar

CONFIG_PATH = os.path.join(REPO_ROOT, "configs", "weird_test.json")
base_config = json.load(open(CONFIG_PATH))


def make_opt(num_burns):
    cfg = dict(base_config)
    cfg["optimization"] = dict(base_config["optimization"])
    cfg["optimization"]["MAX_BURNS"] = [num_burns]
    return MissionOptimizer(cfg)


def _params(opt):
    scalar_params = np.array([
        opt.MIN_COAST_TIME, opt.T_max, opt.MU, opt.J2_VAL, opt.J3_VAL, opt.J4_VAL,
        opt.RE_VAL, opt.MIN_PERIAPSIS, opt.MAX_DV_SOFT, opt.k_t, opt.C_t, opt.k_v, opt.C_v
    ], dtype=np.float64)
    vector_params = np.vstack([opt.A_r0, opt.A_v0, opt.B_r0, opt.B_v0])
    return scalar_params, vector_params


def run_seeded(num_burns):
    opt = make_opt(num_burns)
    scalar_params, vector_params = _params(opt)
    t0 = time.time()
    result = opt._optimize_burn_case(num_burns, scalar_params, vector_params, progress_queue=None)
    elapsed = time.time() - t0
    _, best_x, best_score, epochs_run, note = result
    print(f"[{num_burns}棒-有種子-正式預算] 分數={best_score:.4f} 代數={epochs_run} "
          f"耗時={elapsed:.1f}s note={note}", flush=True)
    return {"score": best_score, "x": best_x, "elapsed": elapsed, "epochs": epochs_run}


def run_baseline(num_burns):
    """複製 _optimize_burn_case 的邏輯，但不生成/注入種子 (starting_solutions=None)。"""
    opt = make_opt(num_burns)
    scalar_params, vector_params = _params(opt)
    lb, ub = opt._generate_bounds(num_burns)
    n_dims = len(lb)
    pop_size = max(30, n_dims * opt.popsize)

    def fitness_wrapper(solution):
        return fast_fitness_evaluator(
            np.asarray(solution, dtype=np.float64), num_burns, scalar_params, vector_params
        )

    problem = {
        "obj_func": fitness_wrapper,
        "bounds": [FloatVar(lb=l, ub=u) for l, u in zip(lb, ub)],
        "minmax": "min",
        "log_to": None,
    }
    case_maxiter = opt._maxiter_for(num_burns)
    term_dict = {"max_early_stop": opt.mes, "epsilon": opt.tol}
    model = L_SHADE(epoch=case_maxiter, pop_size=pop_size, termination=term_dict)
    n_workers = max(2, os.cpu_count() or 4)
    t0 = time.time()
    g_best = model.solve(problem, mode="thread", n_workers=n_workers, seed=opt.seed,
                          starting_solutions=None)
    elapsed = time.time() - t0
    epochs_run = len(model.history.list_epoch_time)
    score = float(g_best.target.fitness)
    print(f"[{num_burns}棒-無種子baseline-正式預算] 分數={score:.4f} 代數={epochs_run} "
          f"耗時={elapsed:.1f}s", flush=True)
    return {"score": score, "x": g_best.solution, "elapsed": elapsed, "epochs": epochs_run}


if __name__ == "__main__":
    print(f"=== 正式預算 (MAXITER={base_config['optimization']['MAXITER']}, "
          f"POPSIZE={base_config['optimization']['POPSIZE']}) A/B 驗證，"
          f"configs/weird_test.json (5800X, {os.cpu_count()} threads) ===", flush=True)

    t_start = time.time()
    results = {}
    results["1_seed"] = run_seeded(1)
    results["2_base"] = run_baseline(2)
    results["2_seed"] = run_seeded(2)
    results["3_base"] = run_baseline(3)
    results["3_seed"] = run_seeded(3)
    total_elapsed = time.time() - t_start

    print("\n=== 總表 (跟夜間縮減預算表對照) ===")
    print(f"{'案例':<20}{'分數':>12}{'代數':>8}{'耗時(s)':>10}")
    print(f"{'1棒(有種子)':<20}{results['1_seed']['score']:>12.4f}"
          f"{results['1_seed']['epochs']:>8}{results['1_seed']['elapsed']:>10.1f}")
    print(f"{'2棒(無種子baseline)':<20}{results['2_base']['score']:>12.4f}"
          f"{results['2_base']['epochs']:>8}{results['2_base']['elapsed']:>10.1f}")
    print(f"{'2棒(有種子)':<20}{results['2_seed']['score']:>12.4f}"
          f"{results['2_seed']['epochs']:>8}{results['2_seed']['elapsed']:>10.1f}")
    print(f"{'3棒(無種子baseline)':<20}{results['3_base']['score']:>12.4f}"
          f"{results['3_base']['epochs']:>8}{results['3_base']['elapsed']:>10.1f}")
    print(f"{'3棒(有種子)':<20}{results['3_seed']['score']:>12.4f}"
          f"{results['3_seed']['epochs']:>8}{results['3_seed']['elapsed']:>10.1f}")
    print(f"\n總耗時: {total_elapsed:.1f}s ({total_elapsed/60:.1f} 分鐘)")

    out_path = os.path.join(REPO_ROOT, "scratch_overnight", "full_budget_ab_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({k: {"score": v["score"], "elapsed": v["elapsed"], "epochs": v["epochs"],
                        "x": np.asarray(v["x"]).tolist()} for k, v in results.items()},
                   f, indent=2, ensure_ascii=False)
    print(f"結果已存到 {out_path}")
