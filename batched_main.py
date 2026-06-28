import json
import os
from batched_core import MissionOptimizer
from script_generator import script_generator

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
        "POPSIZE": 10,
        "NUM_PARAMS": 200,
    }
}

def load_or_create_config(filename="config.json"):
    """讀取設定檔；如果不存在，則建立一個預設的設定檔"""
    if not os.path.exists(filename):
        print(f"⚠️ 找不到 {filename}，正在自動生成預設設定檔...")
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        return DEFAULT_CONFIG
    
    # print(f"📂 成功讀取 {filename} 設定檔！")
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)

def main():
    config = load_or_create_config()
    
    optimizer = MissionOptimizer(
        orbit_a_params=config["orbit_A"],
        orbit_b_params=config["orbit_B"],
        max_burns=config["optimization"]["MAX_BURNS"],
        popsize=config["optimization"]["POPSIZE"],
        num_params=config["optimization"]["NUM_PARAMS"],
    )

        # 2. 定義優化循環
    num_iterations = 500  # 迭代次數

    for i in range(num_iterations):
        # 調用 PSO 更新一步
        # 隨著迭代增加，調整 w 可以幫助收斂 (初期廣泛搜索，後期精確拋光)
        w = 0.9 - (0.5 * (i / num_iterations)) 
        optimizer.optimize_step(w=w, c1=1.5, c2=1.5)
        
        # 3. 監控進度 (每 10 次顯示一次最佳結果)
        if i % 10 == 0:
            print(f"Iteration {i:03d} | Best Score: {-optimizer.gbest_score:.4f}")

    # 4. 取得最終結果
    best_strategy = optimizer.gbest_pos
    print("優化完成！最佳策略參數為:", best_strategy)
    

    # if best_score_polished <= 0.0:
    #         print("❌ 最佳化失敗：所有的嘗試都撞毀或超時了，沒有有效的軌道可以回放。")
    #         return
    
    # burns, times = optimizer.replay_mission(best_params)
    
    # script_generator(
    #     **config["orbit_A"], **config["orbit_B"],
    #     burns=burns, times=times
    # )

if __name__ == "__main__":
    main()