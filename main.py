import os
import sys
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
from src.config_validator import validate_config, ConfigValidationError

# GmatConsole 預設路徑 (你的機器上的 GMAT 安裝位置)。不同機器/重灌過可以用
# --gmat-console 覆蓋，或用 --no-gmat 直接跳過這一步。
GMAT_CONSOLE_DEFAULT = "/Users/corn/Documents/GMAT R2026a/bin/GmatConsole"

# 是否開啟效能分析 (True: 顯示 Top 20 耗時函式)。預設關閉：這份報告主要反映的是主行程
# 「等待」子行程/執行緒的時間，不太能看出真正的運算熱點在哪，平常跑正式結果會被這一大
# 串洗版；真的要抓效能瓶頸時再手動打開。
ENABLE_PROFILING = False

# config 分四大塊，各自對應「誰決定這個數字」：
# - orbit_A / orbit_B：軌道六根數
# - rules：主辦方規定/公告的數字，我們不能改，只能照填 (ΔV_lim、機動間隔、T_max
#   倍數是規則白紙黑字寫的常數；k_t/C_t/k_v/C_v 是每次比賽前才公告的計分參數)
# - strategy：我們自己的任務設計選項，不是規則要求，但會影響算出來的任務規劃
# - optimization：純演算法搜尋設定，只影響「找不找得到好解、要跑多久」，不影響
#   規則本身怎麼定義
DEFAULT_CONFIG = {
    "orbit_A": {
        "SMA": 9000.0, "ECC": 0.0, "INC": 0.0,
        "RAAN": 0.0, "AOP": 0.0, "TA": 0.0
    },
    "orbit_B": {
        "SMA": 7500.0, "ECC": 0.0, "INC": 0.0,
        "RAAN": 0.0, "AOP": 0.0, "TA": 0.0
    },
    "rules": {
        # 這三個是規則規定的數字 (初賽規則第 2、3 節)，不是我們自己編的。預設值等於
        # 目前初賽規則的數字；晉級賽如果規則數字不一樣，改這裡就好，不用動程式碼。
        "MAX_DV_MPS": 1500.0,                # 單次機動 Δv 上限 (ΔV_lim)
        "MIN_MANEUVER_INTERVAL_SEC": 100.0,  # 兩次機動間至少要間隔多久
        "T_MAX_PERIOD_MULTIPLE": 4.0,        # T_max = 這個值 × A 的軌道週期
        # 主辦方公告的環境計分參數 (依軌道分布狀況，每次比賽前會公告)
        "k_t": 0.0001,
        "C_t": 11000.0,
        "k_v": 0.005,
        "C_v": 1200.0,
    },
    "strategy": {
        "USE_J2": True,  # 不確定某一輪/場景有沒有 J2 擾動時用這個切換，Python 端跟
                         # 產生的 GMAT script 會同步套用，不用改程式碼
        "MISS_TOLERANCE_KM": 5.0,  # 規則只要求 Δr <= 這個值 (預設對齊規則的 5km)，可以
                                    # 彈性調小 (甚至設 0 退回精準瞄準)，讓最後一棒 Lambert
                                    # 在容許範圍內找最省油的落點，而不是死盯著 A 的精確位置
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
}

def load_or_create_config(filename=os.path.join("configs", "config.json")):
    """
    讀取設定檔；如果不存在，則建立一個預設的設定檔。
    不管是新建的還是讀進來的，都會跑一次 validate_config()——打錯字/型別錯/
    不合理的值 (負的 SMA、ECC 超出 [0,1) 之類) 會在這裡直接攔下來噴清楚的錯誤
    訊息，而不是讓程式一路跑到 poliastro/mealpy 深處才炸出一段看不懂的 traceback。
    驗證失敗時印出訊息並用 sys.exit(1) 結束 (而不是往上丟例外)，讓失敗訊息乾淨、
    不夾帶一堆跟問題無關的內部呼叫堆疊。
    """
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    if not os.path.exists(filename):
        print(f"⚠️ 找不到 {filename}，正在自動生成預設設定檔...")
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        config = DEFAULT_CONFIG
    else:
        with open(filename, "r", encoding="utf-8") as f:
            try:
                config = json.load(f)
            except json.JSONDecodeError as exc:
                print(f"❌ {filename} 不是合法的 JSON: {exc}")
                sys.exit(1)

    try:
        validate_config(config)
    except ConfigValidationError as exc:
        print(f"❌ {filename} 驗證失敗:\n{exc}")
        sys.exit(1)

    return config


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
    parser.add_argument(
        "--no-fixed-script", action="store_true",
        help="跳過『固定燃燒版本』的產生+驗證。預設：一般版本 (outputs/output.txt，"
             "最後一棒靠 GMAT 的 DC 求解器收斂) 通過驗證後，會自動把 GMAT 收斂後的"
             "燃燒值寫死、產生一份不含任何求解器的版本 (outputs/output_submit.txt)，"
             "適合正式繳交——換一台電腦跑也不用擔心求解器行為不一致，因為根本沒有"
             "求解器在跑。開發/迭代時想省這幾秒可以加這個旗標跳過。"
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
        t_team, miss_km, success_flag, final_dv_mps, final_dv_legal, e1, e2, e3 = lines[-1].split()
        return {
            "t_team_sec": float(t_team),
            "miss_km": float(miss_km),
            "intercept_success": bool(int(float(success_flag))),
            # GMAT 自己的 DC 可以自由調整這棒去命中瞄準點，這是它實際收斂後的真實
            # 大小，不是 Python 預測的那個值——InterceptSuccess 只看距離，不看這個，
            # 兩者要分開檢查。
            "final_burn_dv_mps": float(final_dv_mps),
            "final_burn_legal": bool(int(float(final_dv_legal))),
            "targeter_converged": targeter_converged,
            "report_path": report_path,
            # 最後一棒收斂後的 VNB 分量 (DC 版本才有意義；固定版本這三個值本來就是
            # 我們自己填的，讀回來只是拿來確認腳本真的照著寫死的值跑)。main.py 用
            # 這三個值產生「固定燃燒版本」的繳交腳本，見 script_generator() 的說明。
            "final_burn_vnb": (float(e1), float(e2), float(e3)),
        }
    except ValueError:
        print(f"⚠️ 報表檔格式解析失敗: {lines[-1]!r}")
        return None


def append_run_history(config, mission_info, execution_time, gmat_result=None,
                        fixed_script_result=None,
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
        "rules": config["rules"],
        "strategy": config.get("strategy", {}),
        "optimization": config["optimization"],
    }
    if gmat_result is not None:
        record["gmat_verified"] = {
            "intercept_success": gmat_result["intercept_success"],
            "targeter_converged": gmat_result["targeter_converged"],
            "miss_km": round(gmat_result["miss_km"], 6),
            "t_team_sec": round(gmat_result["t_team_sec"], 2),
            "final_burn_dv_mps": round(gmat_result["final_burn_dv_mps"], 2),
            "final_burn_legal": gmat_result["final_burn_legal"],
        }
    # 固定燃燒版本 (outputs/output_submit.txt，沒有求解器) 的驗證結果——正式提交前
    # 檢查這個欄位是不是 intercept_success/final_burn_legal 都 true，比 gmat_verified
    # 那個 (DC 版本) 更接近實際要繳交的東西。
    if fixed_script_result is not None:
        record["fixed_script_verified"] = {
            "intercept_success": fixed_script_result["intercept_success"],
            "miss_km": round(fixed_script_result["miss_km"], 6),
            "t_team_sec": round(fixed_script_result["t_team_sec"], 2),
            "final_burn_dv_mps": round(fixed_script_result["final_burn_dv_mps"], 2),
            "final_burn_legal": fixed_script_result["final_burn_legal"],
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
        burns, times, aim_point=mission_info["aim_point"],
        max_dv=optimizer.MAX_DV, use_j2=optimizer.USE_J2
    )

    end_time = time.perf_counter()
    execution_time = end_time - start_time

    minute_note = f" (約 {execution_time / 60:.2f} 分鐘)" if execution_time > 60 else ""
    print(f"\n⏳ 總計算時間: {execution_time:.2f} 秒{minute_note}")

    # 3. 自動呼叫 GMAT 做無頭驗證，不用再手動開 GUI 點來點去
    gmat_result = None
    if args.no_gmat:
        print("（跳過了 GMAT 驗證，記得手動開 GMAT 跑一次 outputs/output.txt 確認 InterceptSuccess）")
    else:
        gmat_result = run_gmat_verification(args.gmat_console, os.path.join("outputs", "output.txt"))
        if gmat_result:
            match = "✅" if gmat_result["intercept_success"] else "❌"
            dv_match = "✅" if gmat_result["final_burn_legal"] else "❌"
            print("\n--- 🛰️  GMAT 獨立驗證結果 (真實高階模型，非 Python 預測) ---")
            print(f"  InterceptSuccess : {match} {'成功' if gmat_result['intercept_success'] else '失敗'} "
                  f"(Targeter {'收斂' if gmat_result['targeter_converged'] else '⚠️ 未收斂'})")
            print(f"  MissDistance     : GMAT {gmat_result['miss_km']*1000:.3f} m   "
                  f"(Python 預測 {mission_info['miss_km']*1000:.3f} m)")
            # GMAT 自己的 DC 可以自由調整最後一棒去命中瞄準點，這是它實際收斂後的
            # 真實大小，跟 InterceptSuccess 是分開的兩件事，兩個都要看。
            print(f"  最後一棒實際 Δv  : GMAT {gmat_result['final_burn_dv_mps']:.1f} m/s   "
                  f"(Python 預測 {mission_info['final_burn_dv_mps']:.1f} m/s)  "
                  f"{dv_match} {'合規 (≤1500 m/s)' if gmat_result['final_burn_legal'] else '⚠️ 超過 1500 m/s 限制！'}")
            print(f"  T_team           : GMAT {gmat_result['t_team_sec']:.2f} s   "
                  f"(Python 預測 {mission_info['T_team']:.2f} s)")
            print(f"  報表原始檔案     : {gmat_result['report_path']}")

    # 3.5 DC 版本驗證乾淨通過後，把 GMAT 自己收斂出來的燃燒值寫死，產生一份不含
    # 任何求解器的「固定燃燒版本」——換一台電腦跑，不用擔心求解器 (DC) 的收斂行為
    # 跟我們這邊不一樣，因為這份腳本裡根本沒有求解器，單純傳播+施加燃燒。
    fixed_script_result = None
    if not args.no_gmat and not args.no_fixed_script:
        if gmat_result and gmat_result["intercept_success"] and gmat_result["targeter_converged"] \
                and gmat_result["final_burn_legal"]:
            print("\n🔒 一般版本驗證乾淨通過，產生固定燃燒版本 (適合正式繳交)...")
            script_generator(
                config["orbit_A"]["SMA"], config["orbit_A"]["ECC"], config["orbit_A"]["INC"],
                config["orbit_A"]["RAAN"], config["orbit_A"]["AOP"], config["orbit_A"]["TA"],
                config["orbit_B"]["SMA"], config["orbit_B"]["ECC"], config["orbit_B"]["INC"],
                config["orbit_B"]["RAAN"], config["orbit_B"]["AOP"], config["orbit_B"]["TA"],
                burns, times, aim_point=mission_info["aim_point"],
                max_dv=optimizer.MAX_DV, use_j2=optimizer.USE_J2,
                final_burn_fixed_vnb=gmat_result["final_burn_vnb"],
                output_filename="output_submit.txt",
            )
            fixed_script_result = run_gmat_verification(
                args.gmat_console, os.path.join("outputs", "output_submit.txt")
            )
            if fixed_script_result:
                fmatch = "✅" if fixed_script_result["intercept_success"] else "❌"
                fdv_match = "✅" if fixed_script_result["final_burn_legal"] else "❌"
                print("\n--- 🔒 固定燃燒版本驗證結果 (outputs/output_submit.txt，沒有求解器) ---")
                print(f"  InterceptSuccess : {fmatch} {'成功' if fixed_script_result['intercept_success'] else '失敗'}")
                print(f"  MissDistance     : {fixed_script_result['miss_km']*1000:.3f} m   "
                      f"(一般版本 {gmat_result['miss_km']*1000:.3f} m)")
                print(f"  最後一棒實際 Δv  : {fixed_script_result['final_burn_dv_mps']:.1f} m/s   "
                      f"{fdv_match} {'合規 (≤1500 m/s)' if fixed_script_result['final_burn_legal'] else '⚠️ 超過 1500 m/s 限制！'}")
                if fixed_script_result["intercept_success"] and fixed_script_result["final_burn_legal"]:
                    print("  👉 這份可以拿去正式繳交。")
                else:
                    print("  ⚠️ 固定版本驗證沒有通過 (理論上應該跟一般版本幾乎一樣，這不應該發生)，"
                          "先用一般版本 (outputs/output.txt) 為準，這個狀況值得回報排查。")
            else:
                print("  ⚠️ 固定版本沒有跑成功 (GMAT 呼叫失敗)，先用一般版本 (outputs/output.txt) 為準。")
        elif gmat_result:
            print("\n⚠️ 一般版本沒有完全通過驗證 (成功/收斂/合規三者其一是 false)，不產生固定燃燒版本——"
                  "這組解本身就有問題，先處理好再重跑。")

    # 4. 附加寫入執行紀錄，方便之後比較不同設定/軌道跑出來的分數
    append_run_history(config, mission_info, execution_time,
                        gmat_result=gmat_result, fixed_script_result=fixed_script_result)

    # 輸出效能報告
    if ENABLE_PROFILING:
        profiler.disable()
        stats = pstats.Stats(profiler).sort_stats('tottime')
        print("\n--- 效能分析報告 (Top 20 最耗時函式) ---")
        stats.print_stats(20)

if __name__ == '__main__':
    main()