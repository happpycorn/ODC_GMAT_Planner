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

# GmatConsole 路徑的最後備援值 (只在 --gmat-console 沒給、config.json 也沒有
# local.gmat_console_path 時才用得到)。這個路徑寫死在這裡、被 git 追蹤，換一台機器/
# 換一個人開發大概率對不上——所以優先順序是 --gmat-console > config 的
# local.gmat_console_path (config.json 本來就被 gitignore 排除，換人/換機器各自維護
# 自己的這塊，不用改這個檔案) > 這裡的最後備援值 (目前是我這台機器的路徑，純粹是圖
# 我自己方便，不建議依賴它)。
GMAT_CONSOLE_DEFAULT = "/Users/corn/Documents/GMAT R2026a/bin/GmatConsole"

# 是否開啟效能分析 (True: 顯示 Top 20 耗時函式)。預設關閉：這份報告主要反映的是主行程
# 「等待」子行程/執行緒的時間，不太能看出真正的運算熱點在哪，平常跑正式結果會被這一大
# 串洗版；真的要抓效能瓶頸時再手動打開。
ENABLE_PROFILING = False

# config 分四大塊 + 一塊選填，各自對應「誰決定這個數字」：
# - orbit_A / orbit_B：軌道六根數
# - rules：主辦方規定/公告的數字，我們不能改，只能照填 (ΔV_lim、機動間隔、T_max
#   倍數是規則白紙黑字寫的常數；k_t/C_t/k_v/C_v 是每次比賽前才公告的計分參數)
# - strategy：我們自己的任務設計選項，不是規則要求，但會影響算出來的任務規劃
# - optimization：純演算法搜尋設定，只影響「找不找得到好解、要跑多久」，不影響
#   規則本身怎麼定義
# - local (選填，這裡不生成，自己要用再手動加)：跟任務/規則無關的「這台機器」設定，
#   目前只有 {"gmat_console_path": "/你的路徑/GmatConsole"}——換電腦/換人開發常常
#   不一樣，寫在這裡而不是 --gmat-console 每次都要打，也不會污染到 git (config.json
#   本來就被 gitignore 排除)。
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
        "T_MAX_PERIOD_MULTIPLE": 4.0,        # T_max = 這個值 × A 的軌道週期 (只在 A
                                              # 是橢圓/圓軌道時有意義，初賽適用)
        # "T_MAX_SEC": null,                 # 選填：直接指定 T_max 秒數，會蓋過上面
        # 那條「週期×倍數」公式。排位賽 A 是雙曲線軌道 (沒有週期)，官方公告 T_max
        # 定義方式後，把算出來的秒數填在這裡——orbit_A.ECC>=1 時這個欄位是必填，
        # 不然 optimizer 初始化會直接報錯 (週期公式對雙曲線沒有意義)。
        # 主辦方公告的環境計分參數 (依軌道分布狀況，每次比賽前會公告)
        "k_t": 0.0001,
        "C_t": 11000.0,
        "k_v": 0.005,
        "C_v": 1200.0,
    },
    "strategy": {
        "GRAVITY_DEGREE": 2,  # 重力場要算到第幾階 zonal harmonic：0=純點質量, 2=J2,
                              # 3=J2+J3, 4=J2+J3+J4。不確定某一輪/場景實際開多少階擾動時
                              # 用這個切換，Python 端跟產生的 GMAT script 會同步套用
                              # (GMAT 端 Order 固定收在 0，只算 zonal 不算 tesseral，
                              # 確保兩邊模型完全對齊)，不用改程式碼
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
        "--gmat-console", default=None,
        help="GmatConsole 執行檔路徑，用來自動跑無頭驗證。不給的話依序改抓 config.json 的"
             "local.gmat_console_path、再來是這台機器上寫死的最後備援值"
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
        print(f"⚠️ 找不到 GmatConsole ({console_path})，略過自動 GMAT 驗證。"
              f"每次都要打 --gmat-console 太麻煩的話，可以在 config.json 裡加："
              f'\n   "local": {{"gmat_console_path": "你的 GmatConsole 完整路徑"}}'
              f"\n（這個設定只在你自己的 config.json 裡，不會跟著 git 到處跑）。"
              f"不想跑 GMAT 驗證就用 --no-gmat 關掉這個提示。")
        return None

    bin_dir = os.path.dirname(console_path)
    report_path = os.path.normpath(os.path.join(bin_dir, "..", "output", "GMAT_InterceptReport.txt"))

    # 關鍵防護 (2026-08-14 抓到的真 bug)：GMAT 執行失敗時 (腳本解析錯誤、跑到一半
    # 崩潰...) 不一定會清掉舊的報表檔——如果上一次執行 (可能是完全不同的 config/
    # 情境) 留下的報表檔還在，下面的 `os.path.exists(report_path)` 檢查會誤判成
    #「這次執行成功了」，讀到的其實是上一次殘留的舊資料，安靜地回傳一份看起來合
    # 理、實際上完全對不上這次腳本的假結果。實測抓到過：這次 script 因為某個非
    # ASCII 字元被 GMAT 解析器整個拒絕，但因為報表檔沒被清掉，讀回來的是前一次
    # (完全不同情境) 的殘留報表，main.py 印出一份看似正常、實則張冠李戴的驗證結果。
    # 修法：跑之前先把舊報表刪掉，讓「檔案存在」這件事只可能代表「這次真的寫出來
    # 了」，不會被殘留檔案騙過去。
    if os.path.exists(report_path):
        try:
            os.remove(report_path)
        except OSError as exc:
            print(f"⚠️ 無法清除舊的報表檔 ({report_path}): {exc}，這次驗證結果可能不可靠。")

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

    # returncode 非 0 (腳本解析失敗、執行中崩潰...) 也要當失敗處理，不要只看報表
    # 檔存不存在——雖然上面已經先清掉舊檔案，這裡多一層檢查讓失敗訊息更明確、
    # 直接把 GMAT 自己回報的錯誤內容印出來，不用使用者自己去猜為什麼沒有報表。
    if result.returncode != 0:
        print(f"⚠️ GmatConsole 執行失敗 (exit code {result.returncode})，GMAT 輸出末段：")
        print("\n".join(stdout.strip().splitlines()[-15:]))
        return None

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
                        fixed_script_result=None, fixed_script_source=None,
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
            # "gmat_dc"：一般版本乾淨通過，燃燒值來自 GMAT DC 收斂後的答案 (最可信)。
            # "python_fallback"：一般版本 (DC) 沒有乾淨通過 (通常是 DC 的 Vary 邊界卡在
            # 合法 Δv 範圍、搆不到 Python 認為需要的值)，改用 Python 自己算出的燃燒值
            # 繞過 DC 直接驗證——這種情況下 final_burn_legal 可能是 false，代表這個方案
            # 命中但超標，依規則第 5 節扣 10 分/次，不是取消資格，仍然是可評估的方案。
            "source": fixed_script_source,
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

    # GmatConsole 路徑解析順序：--gmat-console > config.json 的 local.gmat_console_path
    # > 這裡寫死的最後備援值 (見 GMAT_CONSOLE_DEFAULT 的說明)。
    gmat_console_path = (
        args.gmat_console
        or config.get("local", {}).get("gmat_console_path")
        or GMAT_CONSOLE_DEFAULT
    )

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
        max_dv=optimizer.MAX_DV, gravity_degree=optimizer.GRAVITY_DEGREE
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
        gmat_result = run_gmat_verification(gmat_console_path, os.path.join("outputs", "output.txt"))
        if gmat_result:
            match = "✅" if gmat_result["intercept_success"] else "❌"
            dv_match = "✅" if gmat_result["final_burn_legal"] else "❌"
            # 三欄對照 (GMAT / Python / 差距)：這份報告最重要的用途就是看兩個模型
            # 差多遠，差距那一欄直接算好，不要讓使用者自己心算。
            d_miss = abs(gmat_result['miss_km'] - mission_info['miss_km']) * 1000.0
            d_dv = abs(gmat_result['final_burn_dv_mps'] - mission_info['final_burn_dv_mps'])
            print(f"\n── GMAT 驗證：一般版本 (含 DC 求解器) {'─' * 22}")
            print(f"  {'':<12}{'GMAT':>14}{'Python':>14}{'差距':>12}")
            print(f"  {'Δr_min':<12}{gmat_result['miss_km']*1000:>13,.3f}m"
                  f"{mission_info['miss_km']*1000:>13,.3f}m{d_miss:>11,.3f}m")
            # GMAT 自己的 DC 可以自由調整最後一棒去命中瞄準點，這是它實際收斂後的
            # 真實大小，跟 InterceptSuccess 是分開的兩件事，兩個都要看。
            print(f"  {'最後一棒 Δv':<10}{gmat_result['final_burn_dv_mps']:>13,.1f}m/s"
                  f"{mission_info['final_burn_dv_mps']:>11,.1f}m/s{d_dv:>9,.1f}m/s")
            print(f"  {'T_team':<12}{gmat_result['t_team_sec']:>13,.2f}s"
                  f"{mission_info['T_team']:>13,.2f}s")
            print(f"  命中 {match} {'成功' if gmat_result['intercept_success'] else '失敗'}"
                  f"   Targeter {'✅ 收斂' if gmat_result['targeter_converged'] else '⚠️ 未收斂'}"
                  f"   最後一棒 {dv_match} {'合規' if gmat_result['final_burn_legal'] else '超過上限'}")
            print(f"  報表：{gmat_result['report_path']}")

    # 3.5 產生「固定燃燒版本」(不含任何求解器，單純傳播+施加燃燒)。
    #
    # 燃燒值來源分兩種情況：
    # (a) 一般版本 (DC) 驗證乾淨通過 → 用 GMAT 自己收斂出的值 (最可信，GMAT 高精度模型
    #     自己找到的答案)。
    # (b) 一般版本沒有乾淨通過 (DC 沒收斂 / 命中失敗) → 改用 Python 自己 (refine_lambert_burn)
    #     算出的值當 fallback。這個分支存在的理由：DC 的 Vary 邊界寫死卡在合法 Δv 範圍
    #     (script_generator 的 max_dv 參數)，如果真正需要的燃燒本來就超過規則上限，DC
    #     不管怎樣都不可能收斂到那個值——這不代表 Python 找到的方案是垃圾，只代表「透過
    #     GMAT DC 求解」這條路線走不通。而規則第 5 節明講：單次燃燒超標只是每次扣 10 分
    #     (扣到 0 分為止)，不是直接取消資格，所以「命中但超標」仍然是一個可能值得採用、
    #     至少值得誠實跑出來看看分數的方案，不該被 DC 收斂失敗吃掉、變成一份根本產生不出來
    #     的結果。用 Python 自己的值繞過 DC 直接驗證，才知道這個方案實際上能不能重現、
    #     真正的 Δv 是多少。
    #
    # 兩種情況都需要先確認 mission_info["dc_converged"] (Python 端 refine_lambert_burn
    # 有沒有在它自己的模型內收斂到瞄準點)——如果連 Python 自己都沒收斂，代表這組解本身
    # 就沒有一個自洽的燃燒值可以拿來 fallback，兩條路都走不通。
    fixed_script_result = None
    fixed_script_source = None  # "gmat_dc" | "python_fallback" | None，寫進 run_history 方便回頭查
    if not args.no_gmat and not args.no_fixed_script:
        clean_dc = bool(
            gmat_result and gmat_result["intercept_success"]
            and gmat_result["targeter_converged"] and gmat_result["final_burn_legal"]
        )
        final_burn_vnb = None
        if clean_dc:
            fixed_script_source = "gmat_dc"
            final_burn_vnb = gmat_result["final_burn_vnb"]
            print("\n🔒 一般版本 (GMAT DC) 驗證乾淨通過，用 GMAT 收斂後的值產生固定燃燒版本...")
        elif mission_info["dc_converged"]:
            fixed_script_source = "python_fallback"
            final_burn_vnb = tuple(burns[-1])
            reason = "GMAT 呼叫失敗/找不到 GmatConsole" if gmat_result is None else (
                "Targeter 未收斂" if not gmat_result["targeter_converged"] else
                "命中失敗 (Δr > 5km)" if not gmat_result["intercept_success"] else
                "最後一棒超過 Δv 上限"
            )
            print(f"\n⚠️ 一般版本 (GMAT DC) 沒有乾淨通過（{reason}），"
                  f"改用 Python 自己算出的燃燒值產生固定燃燒版本，繞過 DC 直接驗證這個方案"
                  f"能不能重現、真正的 Δv 是多少...")
        else:
            print("\n⚠️ 一般版本沒有通過，Python 自己的模型也沒收斂到瞄準點——這組解本身"
                  "沒有可信的燃燒值可以拿來當 fallback，先處理好再重跑。")

        if final_burn_vnb is not None:
            script_generator(
                config["orbit_A"]["SMA"], config["orbit_A"]["ECC"], config["orbit_A"]["INC"],
                config["orbit_A"]["RAAN"], config["orbit_A"]["AOP"], config["orbit_A"]["TA"],
                config["orbit_B"]["SMA"], config["orbit_B"]["ECC"], config["orbit_B"]["INC"],
                config["orbit_B"]["RAAN"], config["orbit_B"]["AOP"], config["orbit_B"]["TA"],
                burns, times, aim_point=mission_info["aim_point"],
                max_dv=optimizer.MAX_DV, gravity_degree=optimizer.GRAVITY_DEGREE,
                final_burn_fixed_vnb=final_burn_vnb,
                output_filename="output_submit.txt",
            )
            fixed_script_result = run_gmat_verification(
                gmat_console_path, os.path.join("outputs", "output_submit.txt")
            )
            if fixed_script_result:
                fmatch = "✅" if fixed_script_result["intercept_success"] else "❌"
                fdv_match = "✅" if fixed_script_result["final_burn_legal"] else "⚠️"
                src_label = "GMAT DC 收斂後的值" if fixed_script_source == "gmat_dc" \
                    else "Python 自己算的值 (DC 沒有乾淨通過的 fallback)"
                print(f"\n── GMAT 驗證：固定燃燒版本 (無求解器，建議繳交這份) {'─' * 8}")
                print(f"  檔案：outputs/output_submit.txt　燃燒值來源：{src_label}")
                print(f"  Δr_min {fixed_script_result['miss_km']*1000:>12,.3f} m"
                      f"   最後一棒 Δv {fixed_script_result['final_burn_dv_mps']:>9,.1f} m/s {fdv_match}")
                print(f"  命中 {fmatch} {'成功' if fixed_script_result['intercept_success'] else '失敗'}"
                      f"   {'合規' if fixed_script_result['final_burn_legal'] else '⚠️ 超過每棒上限'}")
                if fixed_script_result["intercept_success"] and fixed_script_result["final_burn_legal"]:
                    print("  👉 命中且合規，可以直接繳交。")
                elif fixed_script_result["intercept_success"]:
                    print("  👉 命中但超標：依規則第 5 節每次違規扣 10 分（不是取消資格），這份仍可繳交。")
                    print("     但先確認沒有更好的合法解——用 feasibility.py 看合法解存不存在，")
                    print("     再用 sweep_burns.py 或加大棒數/預算找找看。")
                else:
                    print("  ⚠️ 沒有命中。來源若是 GMAT DC 的值，理論上該跟一般版本一致，這不該發生；")
                    print("     若是 Python fallback，代表這組解本身站不住腳（模型在這個時間尺度上有落差），")
                    print("     不建議採用。")
            else:
                print("  ⚠️ 固定版本沒有跑成功 (GMAT 呼叫失敗)。")

    # 4. 附加寫入執行紀錄，方便之後比較不同設定/軌道跑出來的分數
    append_run_history(config, mission_info, execution_time,
                        gmat_result=gmat_result, fixed_script_result=fixed_script_result,
                        fixed_script_source=fixed_script_source)

    # 輸出效能報告
    if ENABLE_PROFILING:
        profiler.disable()
        stats = pstats.Stats(profiler).sort_stats('tottime')
        print("\n--- 效能分析報告 (Top 20 最耗時函式) ---")
        stats.print_stats(20)

if __name__ == '__main__':
    main()