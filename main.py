import os
import time
import json
import warnings
import argparse
import datetime
import subprocess
import multiprocessing
import cProfile
import pstats

# 引入重構後的新模組
from src.optimizer import MissionOptimizer
from src.script_generator import script_generator

# GmatConsole 預設路徑 (你的機器上的 GMAT 安裝位置)。不同機器/重灌過可以用
# --gmat-console 覆蓋，或用 --no-gmat 直接跳過這一步。
GMAT_CONSOLE_DEFAULT = "/Users/corn/Documents/GMAT R2026a/bin/GmatConsole"

# 是否開啟效能分析 (True: 顯示 Top 20 耗時函式)。預設關閉：這份報告主要反映的是主行程
# 「等待」子行程/執行緒的時間，不太能看出真正的運算熱點在哪，平常跑正式結果會被這一大
# 串洗版；真的要抓效能瓶頸時再手動打開。
ENABLE_PROFILING = False

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
        "POPSIZE": 10,  # 每個決策變數維度分配幾個個體 (族群大小 = 維度數 * POPSIZE)
        "NUM_THREADS": -1, # <=0 自動用「可用核心數 / 燃燒次數案例數」估合理的執行緒數
        "MAX_EARLY_STOP": 30,
        "TOL": 0.02,  # Score 是 0~100 分量表，這個值要跟這個量表相稱，太小早停形同虛設
        "SEED": None,  # 設一個整數可以讓同一組設定每次重現一樣的結果，方便比較改動
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


def parse_args():
    parser = argparse.ArgumentParser(description="軌道攔截設計賽 - 任務規劃與計分工具")
    parser.add_argument(
        "--config", default=os.path.join("configs", "config.json"),
        help="設定檔路徑 (預設 configs/config.json)，方便在測試資料/正式測資之間切換而不用互相覆蓋"
    )
    parser.add_argument(
        "--gmat-console", default=GMAT_CONSOLE_DEFAULT,
        help="GmatConsole 執行檔路徑，用來自動跑無頭驗證 (預設抓你機器上的安裝路徑)"
    )
    parser.add_argument(
        "--no-gmat", action="store_true",
        help="跳過自動 GMAT 驗證這一步，只產生 script"
    )
    return parser.parse_args()


def run_gmat_verification(console_path: str, script_path: str, timeout_sec: float = 120.0):
    """
    呼叫 GmatConsole 用無頭批次模式 (--exit --run) 跑我們產生的 script，
    跑完直接讀回 GMAT 自己寫的 GMAT_InterceptReport.txt，回傳一個 dict。
    這一步失敗 (GMAT 沒裝/路徑不對/腳本有誤) 都不該讓整個程式當掉，只印警告後回傳 None，
    Python 端算出來的結果照樣有效、照樣會寫進 outputs/output.txt。
    """
    console_path = os.path.expanduser(console_path)
    if not os.path.exists(console_path):
        print(f"⚠️ 找不到 GmatConsole ({console_path})，略過自動 GMAT 驗證 "
              f"(用 --gmat-console 指到正確路徑，或用 --no-gmat 關掉這個提示)。")
        return None

    bin_dir = os.path.dirname(console_path)
    report_path = os.path.normpath(os.path.join(bin_dir, "..", "output", "GMAT_InterceptReport.txt"))

    print("\n🛰️  正在呼叫 GmatConsole 做無頭驗證...")
    try:
        result = subprocess.run(
            [console_path, "--exit", "--run", os.path.abspath(script_path)],
            cwd=bin_dir, capture_output=True, text=True, timeout=timeout_sec
        )
    except subprocess.TimeoutExpired:
        print(f"⚠️ GmatConsole 超過 {timeout_sec} 秒沒結束，放棄這次驗證。")
        return None
    except Exception as exc:
        print(f"⚠️ 呼叫 GmatConsole 失敗: {exc}")
        return None

    stdout = result.stdout or ""
    targeter_converged = "The Targeter converged!" in stdout

    if not os.path.exists(report_path):
        print(f"⚠️ GMAT 執行完但找不到報表檔 ({report_path})，可能腳本執行有誤，GMAT 輸出末段：")
        print("\n".join(stdout.strip().splitlines()[-15:]))
        return None

    with open(report_path, "r", encoding="utf-8") as f:
        lines = [ln for ln in f.read().strip().splitlines() if ln.strip()]
    if len(lines) < 2:
        print(f"⚠️ 報表檔 ({report_path}) 內容看起來不完整: {lines}")
        return None

    try:
        t_team, miss_km, success_flag = lines[-1].split()
        return {
            "t_team_sec": float(t_team),
            "miss_km": float(miss_km),
            "intercept_success": bool(int(float(success_flag))),
            "targeter_converged": targeter_converged,
            "report_path": report_path,
        }
    except ValueError:
        print(f"⚠️ 報表檔格式解析失敗: {lines[-1]!r}")
        return None


def append_run_history(config, mission_info, execution_time, gmat_result=None,
                        path=os.path.join("outputs", "run_history.jsonl")):
    """把這次執行的結果 (連同用的 config) 附加成一行 JSON，累積成可回頭比較的執行紀錄。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    record = {
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "num_burns": mission_info["num_burns"],
        "score": round(float(mission_info["score"]), 4),
        "delta_v_mps": round(float(mission_info["total_dv_mps"]), 2),
        "t_team_sec": round(float(mission_info["T_team"]), 2),
        "miss_km": round(float(mission_info["miss_km"]), 6),
        "penalty_count": int(mission_info["penalty_count"]),
        "dc_converged": bool(mission_info["dc_converged"]),
        "execution_time_sec": round(execution_time, 2),
        "orbit_A": config["orbit_A"],
        "orbit_B": config["orbit_B"],
        "k_t": config["k_t"], "C_t": config["C_t"], "k_v": config["k_v"], "C_v": config["C_v"],
        "optimization": config["optimization"],
    }
    if gmat_result is not None:
        record["gmat_verified"] = {
            "intercept_success": gmat_result["intercept_success"],
            "targeter_converged": gmat_result["targeter_converged"],
            "miss_km": round(gmat_result["miss_km"], 6),
            "t_team_sec": round(gmat_result["t_team_sec"], 2),
        }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"📒 執行紀錄已附加到 {path}")


def main():
    # 效能分析器設定
    if ENABLE_PROFILING:
        profiler = cProfile.Profile()
        profiler.enable()

    multiprocessing.freeze_support()
    warnings.filterwarnings("ignore")

    args = parse_args()
    config = load_or_create_config(args.config)

    start_time = time.perf_counter()

    # 1. 啟動最佳化器 (內部已經包含 L-SHADE 與 NLP 微調)
    optimizer = MissionOptimizer(config)
    burns, times, mission_info = optimizer.run_study()

    if burns is None or times is None:
        print("任務終止。")
        return

    # 2. 產出 GMAT 腳本 (打靶邊界跟著規則的 ΔV_lim 走，避免 GMAT 端偷偷超標)
    script_generator(
        config["orbit_A"]["SMA"], config["orbit_A"]["ECC"], config["orbit_A"]["INC"],
        config["orbit_A"]["RAAN"], config["orbit_A"]["AOP"], config["orbit_A"]["TA"],
        config["orbit_B"]["SMA"], config["orbit_B"]["ECC"], config["orbit_B"]["INC"],
        config["orbit_B"]["RAAN"], config["orbit_B"]["AOP"], config["orbit_B"]["TA"],
        burns, times, max_dv=optimizer.MAX_DV
    )

    end_time = time.perf_counter()
    execution_time = end_time - start_time

    print("\n" + "="*40)
    print(f"⏳ 總計算時間: {execution_time:.2f} 秒")
    if execution_time > 60:
        print(f"   (大約 {execution_time / 60:.2f} 分鐘)")
    print("="*40)

    # 3. 自動呼叫 GMAT 做無頭驗證，不用再手動開 GUI 點來點去
    gmat_result = None
    if not args.no_gmat:
        gmat_result = run_gmat_verification(args.gmat_console, os.path.join("outputs", "output.txt"))
        if gmat_result:
            match = "✅" if gmat_result["intercept_success"] else "❌"
            print("\n--- 🛰️  GMAT 獨立驗證結果 (真實高階模型，非 Python 預測) ---")
            print(f"  InterceptSuccess : {match} {'成功' if gmat_result['intercept_success'] else '失敗'} "
                  f"(Targeter {'收斂' if gmat_result['targeter_converged'] else '⚠️ 未收斂'})")
            print(f"  MissDistance     : GMAT {gmat_result['miss_km']*1000:.3f} m   "
                  f"(Python 預測 {mission_info['miss_km']*1000:.3f} m)")
            print(f"  T_team           : GMAT {gmat_result['t_team_sec']:.2f} s   "
                  f"(Python 預測 {mission_info['T_team']:.2f} s)")
            print(f"  報表原始檔案     : {gmat_result['report_path']}")

    # 4. 附加寫入執行紀錄，方便之後比較不同設定/軌道跑出來的分數
    append_run_history(config, mission_info, execution_time, gmat_result=gmat_result)

    # 輸出效能報告
    if ENABLE_PROFILING:
        profiler.disable()
        stats = pstats.Stats(profiler).sort_stats('tottime')
        print("\n--- 效能分析報告 (Top 20 最耗時函式) ---")
        stats.print_stats(20)

if __name__ == '__main__':
    main()