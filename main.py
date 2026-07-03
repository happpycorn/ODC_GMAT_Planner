import os
import time
import json
import warnings
import multiprocessing
import cProfile
import pstats

# 引入重構後的新模組
from src.optimizer import MissionOptimizer
from src.script_generator import script_generator

# 是否開啟效能分析 (True: 顯示 Top 20 耗時函式)
ENABLE_PROFILING = True

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
        "MAX_BURNS": [1, 2, 3], # 範例：讓它依序嘗試不同的推進次數
        "MAXITER": 200,
        "POPSIZE": 10,
        "NUM_THREADS": -1, # 如果用 Numba，可以考慮設為 1 (單執行緒可能就極快)
        "MAX_EARLY_STOP": 30,
        "TOL": 10e-4,
    },
    # 新增：主辦方公告的環境計分參數
    "k_t": 0.0001,
    "C_t": 11000.0,
    "k_v": 0.005,
    "C_v": 1200.0
}

def load_or_create_config(filename=os.path.join("configs", "config.json")):
    """讀取設定檔；如果不存在，則建立一個預設的設定檔"""
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    if not os.path.exists(filename):
        print(f"⚠️ 找不到 {filename}，正在自動生成預設設定檔...")
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        return DEFAULT_CONFIG
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)

def main():
    # 效能分析器設定
    if ENABLE_PROFILING:
        profiler = cProfile.Profile()
        profiler.enable()

    multiprocessing.freeze_support()
    warnings.filterwarnings("ignore")

    config = load_or_create_config()

    start_time = time.perf_counter() 

    # 1. 啟動最佳化器 (內部已經包含 L-SHADE 與 NLP 微調)
    optimizer = MissionOptimizer(config)
    burns, times, _ = optimizer.run_study()
    
    if burns is None or times is None: 
        print("任務終止。")
        return

    # 2. 產出 GMAT 腳本
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

    # 輸出效能報告
    if ENABLE_PROFILING:
        profiler.disable()
        stats = pstats.Stats(profiler).sort_stats('tottime')
        print("\n--- 效能分析報告 (Top 20 最耗時函式) ---")
        stats.print_stats(20)

if __name__ == '__main__':
    main()