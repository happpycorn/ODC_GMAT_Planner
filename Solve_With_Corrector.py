import os
import time
import json
import warnings
import multiprocessing
from scipy.optimize import minimize

from src.DE_Mealpy import MissionOptimizer
from src.script_generator import script_generator
from src.propagator import OrbitPropagator

import cProfile
import pstats

DEFAULT_CONFIG = {
    "orbit_A": {
        "SMA": 9000.0, "ECC": 0.0, "INC": 0.0, 
        "RAAN": 0.0, "AOP": 0.0, "TA": 0.0
    },
    "orbit_B": {
        "SMA": 7500.0, "ECC": 0.0, "INC": 0.0, 
        "RAAN": 0.0, "AOP": 0.0, "TA": 0.0
    },
    "optimization": {
        "MAX_BURNS": 8,
        "MAXITER": 200,
        "POPSIZE": 10,
        "NUM_THREADS": -1,
        "TOL":10e-4,
    }
}

def load_or_create_config(filename=os.path.join("configs", "config.json")):
    """讀取設定檔；如果不存在，則建立一個預設的設定檔"""
    if not os.path.exists(filename):
        print(f"⚠️ 找不到 {filename}，正在自動生成預設設定檔...")
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        return DEFAULT_CONFIG
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)

def refine_trajectory(initial_guess_x, num_burns, bounds, accurate_optimizer):
    print("\n🔬 啟動高精度 NLP 微調 (含 J2 攝動)...")
    
    narrow_bounds = []
    for i, (lb, ub) in enumerate(bounds):
        x_val = initial_guess_x[i]
        span = ub - lb
        
        # 💡 動態緊箍咒：利用下界是否小於 0，來區分推力與時間參數
        # 在你的設定中，只有推力參數 (dv) 的下界是 -MAX_DV (-1.5)
        # 時間或比例參數的下界都是 0.0
        if lb < 0:
            # 這是推力向量！給予 15% 的寬容度，讓它有足夠的燃料去對抗 J2
            tolerance = span * 0.15 
        else:
            # 這是時間或比例！給予 2% 的嚴格限制，防止它亂縮短時間
            tolerance = span * 0.02 
            
        new_lb = max(lb, x_val - tolerance)
        new_ub = min(ub, x_val + tolerance)
        narrow_bounds.append((new_lb, new_ub))

    nlp_result = minimize(
        fun=accurate_optimizer.objective, 
        x0=initial_guess_x,                     
        args=(num_burns,), 
        method='L-BFGS-B',                      
        bounds=narrow_bounds,                   
        options={'disp': True, 'maxiter': 50} 
    )
    
    if nlp_result.success:
        print(f"✅ NLP 微調成功！最終高精度分數: {-nlp_result.fun:.4f}")
        return nlp_result.x
    else:
        print("⚠️ NLP 微調遇到困難，可能落入局部死胡同。")
        return initial_guess_x

def main():
    profiler = cProfile.Profile()
    profiler.enable()

    multiprocessing.freeze_support()
    warnings.filterwarnings("ignore")

    config = load_or_create_config()

    start_time = time.perf_counter() 

    optimizer = MissionOptimizer(config)
    burns, times, res = optimizer.run_study()
    if burns is None or times is None or res is None: return

    acc_opt = MissionOptimizer(config, propagator=OrbitPropagator.propagate)
    acc_opt.MIN_PERIAPSIS -= 50

    res_x = refine_trajectory(res[0], res[1], zip(*acc_opt._generate_bounds(res[1])), acc_opt)
    params = acc_opt.decode_params(res_x, res[1])

    burns, times = acc_opt.replay_mission(params, res[1])

    script_generator(
        config["orbit_A"]["SMA"], config["orbit_A"]["ECC"], config["orbit_A"]["INC"],
        config["orbit_A"]["RAAN"], config["orbit_A"]["AOP"], config["orbit_A"]["TA"],
        config["orbit_B"]["SMA"], config["orbit_B"]["ECC"], config["orbit_B"]["INC"],
        config["orbit_B"]["RAAN"], config["orbit_B"]["AOP"], config["orbit_B"]["TA"],
        burns, times
    )

    end_time = time.perf_counter() 
    execution_time = end_time - start_time

    print("\n" + "="*40)
    print(f"⏳ 總計算時間: {execution_time:.2f} 秒")
    if execution_time > 60:
        print(f"   (大約 {execution_time / 60:.2f} 分鐘)")
    print("="*40)

    profiler.disable()

    stats = pstats.Stats(profiler).sort_stats('tottime')
    print("\n--- 效能分析報告 (Top 20 最耗時函式) ---")
    stats.print_stats(20)

if __name__ == '__main__':
    main()