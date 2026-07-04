from src.optimizer import fast_fitness_evaluator
import numpy as np

# 1. 給一些不會破壞物理定律的標量參數
scalar_params = np.ones(11)
scalar_params[0] = 100.0        # min_coast_time (至少滑行 100 秒)
scalar_params[1] = 10000.0      # T_max (任務總時間 10000 秒)
scalar_params[2] = 398600.4418  # mu (地球引力常數，絕對不能為 0)
scalar_params[4] = 6378.137     # re_val (地球半徑)

# 2. 給一些不會完全重疊的座標與速度向量 (大約 7000km 的軌道)
vector_params = np.zeros((4, 3))
vector_params[0] = [7000.0, 0.0, 0.0]  # A_r0
vector_params[1] = [0.0, 7.5, 0.0]     # A_v0
vector_params[2] = [0.0, 7000.0, 0.0]  # B_r0 (跟 A 錯開，不然距離為 0 會報錯)
vector_params[3] = [-7.5, 0.0, 0.0]    # B_v0

# 3. 給一組非零的決策變數 (時間比例和推力都給一點點)
x_array = np.ones(10) * 0.5

fast_fitness_evaluator(x_array, 1, scalar_params, vector_params)

llvm_dict = fast_fitness_evaluator.inspect_llvm()

for signature, llvm_code in llvm_dict.items():
    lines = len(llvm_code.split('\n'))
    print(f"[{signature}] 編譯後的底層代碼共有: {lines} 行")
    
    # 如果你想看它長怎樣，可以寫入檔案慢慢看（不建議直接 print，終端機會被洗版）
    with open("evaluate_dump.ll", "w") as f:
        f.write(llvm_code)