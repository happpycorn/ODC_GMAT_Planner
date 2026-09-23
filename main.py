import os
import sys
import math
import time
import json
import warnings
import argparse
import datetime
import subprocess
import multiprocessing
import copy
import cProfile
import pstats

# 引入重構後的新模組
import numpy as np
from src.optimizer import (MissionOptimizer, run_study_over_revs,
                           reconstruct_mission_logs, tiebreak_rank_key)
from src.primer import intercept_primer_profile, insert_node_seed
from src.script_generator import script_generator
from src.config_validator import validate_config, ConfigValidationError
from src.core_math import propagate_dop853, fast_norm, to_vnb_frame
from src.scorer import calculate_score
from src.burn_splitter import legalize_route, _simulate_free
from src.runlog import log, setup as setup_logging

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
        "REVS_ENSEMBLE": True,  # 預設在 REVS=0 與 REVS=LAMBERT_MAX_REVS 各跑一次完整搜尋、
                                # 取規則§6 較好的那趟 (換掉 seed×REVS 相依脆弱性，成本約
                                # 1.8×)。設 false 只跑一次 (用 LAMBERT_MAX_REVS)——T_max
                                # 天級跑不完 90 分鐘時的降級第一段，見 CONTEST_DAY §4.1。
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
        log.warning(f"⚠️ 找不到 {filename}，正在自動生成預設設定檔...")
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        config = DEFAULT_CONFIG
    else:
        with open(filename, "r", encoding="utf-8") as f:
            try:
                config = json.load(f)
            except json.JSONDecodeError as exc:
                log.error(f"❌ {filename} 不是合法的 JSON: {exc}")
                sys.exit(1)

    try:
        validate_config(config)
    except ConfigValidationError as exc:
        log.error(f"❌ {filename} 驗證失敗:\n{exc}")
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
    # 執行期輸出的詳略（HAP-68）。預設終端機只印事件級摘要，完整 DEBUG 一律寫進
    # outputs/run.log，事後要追細節去撈那個檔就好。
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="終端機印出完整 DEBUG（每趟完整報告、逐項比對、VNB 向量、scipy 迭代碎念）"
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true",
        help="終端機只印 WARNING 以上（適合排程/批次跑）；完整細節照樣寫進 outputs/run.log"
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
        log.warning(f"⚠️ 找不到 GmatConsole ({console_path})，略過自動 GMAT 驗證。"
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
            log.warning(f"⚠️ 無法清除舊的報表檔 ({report_path}): {exc}，這次驗證結果可能不可靠。")

    log.info("\n🛰️  正在呼叫 GmatConsole 做無頭驗證...")
    try:
        result = subprocess.run(
            [console_path, "--exit", "--run", os.path.abspath(script_path)],
            cwd=bin_dir, capture_output=True, text=True, timeout=timeout_sec
        )
    except subprocess.TimeoutExpired:
        log.warning(f"⚠️ GmatConsole 超過 {timeout_sec} 秒沒結束，放棄這次驗證。")
        return None
    except Exception as exc:
        log.warning(f"⚠️ 呼叫 GmatConsole 失敗: {exc}")
        return None

    stdout = result.stdout or ""
    targeter_converged = "The Targeter converged!" in stdout

    # returncode 非 0 (腳本解析失敗、執行中崩潰...) 也要當失敗處理，不要只看報表
    # 檔存不存在——雖然上面已經先清掉舊檔案，這裡多一層檢查讓失敗訊息更明確、
    # 直接把 GMAT 自己回報的錯誤內容印出來，不用使用者自己去猜為什麼沒有報表。
    if result.returncode != 0:
        tail = "\n".join(stdout.strip().splitlines()[-15:])
        log.warning(f"⚠️ GmatConsole 執行失敗 (exit code {result.returncode})，GMAT 輸出末段：\n{tail}")
        return None

    if not os.path.exists(report_path):
        tail = "\n".join(stdout.strip().splitlines()[-15:])
        log.warning(f"⚠️ GMAT 執行完但找不到報表檔 ({report_path})，可能腳本執行有誤，GMAT 輸出末段：\n{tail}")
        return None

    with open(report_path, "r", encoding="utf-8") as f:
        lines = [ln for ln in f.read().strip().splitlines() if ln.strip()]
    if len(lines) < 2:
        log.warning(f"⚠️ 報表檔 ({report_path}) 內容看起來不完整: {lines}")
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
        log.warning(f"⚠️ 報表檔格式解析失敗: {lines[-1]!r}")
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
    log.info(f"📒 執行紀錄已附加到 {path}")


def print_score_breakdown(mission_info, optimizer):
    """把最終分數拆成三塊，並印出當前工作點的「交換率」（HAP-38）。

    純加印，完全不改任何計算：三塊的公式跟 src/scorer.calculate_score 逐字一致，
    輸入直接取 mission_info 裡計分當下用的同一組值（T_team 就是計分用的 intercept_time、
    total_dv_mps/miss_km/penalty_count 也都是），所以三塊加起來一定等於 mission_info
    ["score"]——會順手驗一次，對不上就印警告（代表某處算法漂移了，該查）。

    「交換率」= 計分 sigmoid 在當前工作點的斜率。時間/燃料兩項都是 S=25/(1+e^{k(x-C)})，
    dS/dx = -k·(25-S)·S/25，所以：
      • 每早到 1 秒的價值   = k_t·(25-score_time)·score_time/25   分/秒
      • 每省 1 m/s 的價值   = k_v·(25-score_dv)·score_dv/25       分/(m/s)
    兩者相除就是「省 1 秒 相當於 省多少 m/s」——比賽當天決定「要不要燒油換早到」時，
    這個數字直接告訴你損益平衡點，不用再自己心算 sigmoid。飽和（斜率≈0）時價值趨近 0，
    那一項再怎麼推都幾乎不加分，也一眼看得出來。
    """
    dr = float(mission_info["miss_km"])            # km
    T = float(mission_info["T_team"])              # s（= 計分用的 intercept_time）
    dv = float(mission_info["total_dv_mps"])       # m/s
    pen = int(mission_info["penalty_count"])
    k_t, C_t = optimizer.k_t, optimizer.C_t
    k_v, C_v = optimizer.k_v, optimizer.C_v

    score_dist = 50.0 * math.exp(-(max(dr, 5.0) - 5.0) / 100.0)
    score_time = 25.0 / (1.0 + math.exp(min(k_t * (T - C_t), 700.0)))
    score_dv = 25.0 / (1.0 + math.exp(min(k_v * (dv - C_v), 700.0)))
    penalty = pen * 10.0
    total = max(score_dist + score_time + score_dv - penalty, 0.0)

    # 每單位的邊際價值（sigmoid 斜率，恆為非負，代表「往好的方向改」能拿回的分數）
    val_per_sec = k_t * (25.0 - score_time) * score_time / 25.0     # 分 / 秒
    val_per_mps = k_v * (25.0 - score_dv) * score_dv / 25.0         # 分 / (m/s)

    lines = [f"\n── 分數拆解與交換率 {'─' * 30}",
             f"  距離   {score_dist:>6.2f} / 50   (Δr_min {dr*1000:,.0f} m；≤5,000 m 時地板滿分 50)",
             f"  時間   {score_time:>6.2f} / 25   (T {T:,.0f} s vs C_t {C_t:,.0f} s；每早到 1 s ≈ +{val_per_sec:.4g} 分)",
             f"  燃料   {score_dv:>6.2f} / 25   (ΔV {dv:,.0f} m/s vs C_v {C_v:,.0f} m/s；每省 1 m/s ≈ +{val_per_mps:.4g} 分)",
             f"  違規   {-penalty:>6.2f}        ({pen} 次 × -10)",
             f"  {'─' * 5}",
             f"  合計   {total:>6.2f} / 100"]

    # 交換率：省 1 秒 相當於 省多少 m/s（燃料/時間邊際價值之比）
    if val_per_mps > 1e-12 and val_per_sec > 1e-12:
        mps_per_sec = val_per_sec / val_per_mps
        lines.append(f"  ⇄ 交換率：省 1 秒 ≈ 省 {mps_per_sec:,.2f} m/s"
                     f"（花 ≤{mps_per_sec:,.2f} m/s 換早到 1 秒才划算；反過來省 1 m/s ≈ 早到 "
                     f"{1.0/mps_per_sec:,.2f} 秒）")
    else:
        which = []
        if val_per_sec <= 1e-12:
            which.append("時間項已飽和（再早到幾乎不加分）")
        if val_per_mps <= 1e-12:
            which.append("燃料項已飽和（再省油幾乎不加分）")
        lines.append(f"  ⇄ 交換率：{'、'.join(which)}——這一側推不動分數了。")
    log.info("\n".join(lines))

    # 自我驗算：三塊必須加得回 mission_info 記錄的分數（對不上代表算法漂移）
    recorded = float(mission_info["score"])
    if abs(total - recorded) > 1e-6:
        log.warning(f"⚠️ 拆解 {total:.6f} 與記錄分數 {recorded:.6f} 不一致"
                    f"（差 {abs(total-recorded):.2e}）——計分算法可能有處漂移了，請查。")


def _primer_diagnose_winner(mission_info, opt):
    """對 DE 贏家（標準決策向量、未拆棒前）算 primer 剖面（C1 診斷）。

    重播用 `reconstruct_mission_logs` 拿到每發脈衝的絕對時刻與 ECI Δv（跟計分同一條
    路徑，保證診斷的就是被評分的那條解），再餵 `intercept_primer_profile`。回傳 profile
    dict（含 verdict / worst_arc / 各弧 p_peak / p_peak_frac），無法診斷時回 None。
    """
    x = mission_info.get("x")
    N = int(mission_info.get("num_burns", 0))
    if x is None or N < 1:
        return None
    mu, j2, j3, j4, re = opt.MU, opt.J2_VAL, opt.J3_VAL, opt.J4_VAL, opt.RE_VAL
    try:
        logs, times, *_ = reconstruct_mission_logs(
            np.asarray(x, dtype=np.float64), N, opt.MIN_COAST_TIME, opt.T_max,
            opt.A_r0, opt.A_v0, opt.B_r0, opt.B_v0, mu, j2, j3, j4, re,
            lambert_max_revs=opt.LAMBERT_MAX_REVS)
    except Exception as exc:                       # 重播偶發 Lambert 不收斂等，診斷不該擋管線
        log.debug(f"primer 診斷重播失敗，略過：{exc}")
        return None
    t0 = float(logs[0]["time"])
    r0, v0 = propagate_dop853(opt.B_r0, opt.B_v0, t0, 60.0, mu, j2, j3, j4, re)
    impulses = [(float(bl["time"]), np.asarray(bl["dv_vec"], dtype=np.float64)) for bl in logs]
    return intercept_primer_profile(r0, v0, impulses, float(times[-1]), mu)


def primer_guided_research(config, burns, times, mission_info, optimizer):
    """C2（2026-09-22）：primer 引導的條件式重搜。

    先跑預設（中間棒夾 cap，便宜穩健，已在 run_study_over_revs 跑完）→ 對贏家算 primer：
      - `|p|≤1` 全程（verdict=optimal-ish）→ 結構已（局部）最優，**收工不重搜**。這是圓
        軌道攔截 0/14 的物理原因（見 memory odc-split-aware-not-needed），也是本函式對
        當前題型的預設行為：只多印一行最優性證書，不改結果、不加成本。
      - `|p|>1`（verdict=add-node）→ 該處缺節點 / 節點放錯 → 才付昂貴的寬範圍搜尋：開
        `SPLIT_AWARE_SEARCH`（中間棒上界由 B1 的 energy_floor 動態算）、在 primer 指的弧
        用 `insert_node_seed` 注入一顆插棒種子、以 N+1 棒重搜，最後照規則§6 取兩者較優的。

    只在理論（primer）說會賺時才重搜——把「SPLIT_AWARE 該不該開、種子放哪」從用猜的
    變成 primer 指的。回傳勝出的 (burns, times, mission_info, optimizer)；沿用原解時回 None。
    旗標 strategy.PRIMER_GUIDED_RESEARCH=false 可整個關掉（連診斷都不跑）。
    """
    strat = config.get("strategy", {})
    if not bool(strat.get("PRIMER_GUIDED_RESEARCH", True)):
        return None
    if not isinstance(mission_info, dict) or mission_info.get("x") is None:
        return None

    prof = _primer_diagnose_winner(mission_info, optimizer)
    if prof is None:
        return None

    N = int(mission_info["num_burns"])
    if prof["verdict"] == "optimal-ish":
        log.info(f"🧭 primer 診斷：全程 |p|≤1（max|p|={prof['max_peak']:.3f}）"
                 f"——結構已（局部）最優，不需加棒、不重搜。")
        return None

    warc = prof["worst_arc"]
    a = prof["arcs"][warc]
    frac = a["p_peak_frac"]
    log.info(f"🧭 primer 診斷：max|p|={prof['max_peak']:.3f}>1（add-node）——第 {warc} 段"
             f"（{a['kind']}）峰值落在 {frac*100:.0f}% 處，該插一發中途棒。開 SPLIT_AWARE "
             f"+ 插棒種子，以 {N + 1} 棒重搜。")

    # 重搜設定：開 SPLIT_AWARE（B1 動態上界自動生效）、鎖定 N+1 棒（是否真的比原解好交給
    # §6 比較把關，不好就沿用原解）。其餘設定沿用。
    cfg2 = copy.deepcopy(config)
    s2 = cfg2.setdefault("strategy", {})
    s2["SPLIT_AWARE_SEARCH"] = True
    cfg2["optimization"] = dict(cfg2.get("optimization", {}))
    cfg2["optimization"]["MAX_BURNS"] = [N + 1]

    seed = insert_node_seed(np.asarray(mission_info["x"], dtype=np.float64), N,
                            warc, frac, optimizer.T_max, optimizer.MIN_COAST_TIME)

    b2, t2, mi2, opt2 = run_study_over_revs(cfg2, external_seeds={N + 1: [seed]})
    if b2 is None or not isinstance(mi2, dict):
        log.info("🧭 primer 重搜這趟沒跑出可用解，沿用原解。")
        return None

    eps = optimizer.TIEBREAK_SCORE_EPS
    key_old = tiebreak_rank_key(mission_info["score"], mission_info["miss_km"],
                                mission_info["total_dv_mps"], mission_info["T_team"], eps=eps)
    key_new = tiebreak_rank_key(mi2["score"], mi2["miss_km"],
                                mi2["total_dv_mps"], mi2["T_team"], eps=eps)
    if key_new < key_old:
        log.info(f"🧭 primer 重搜勝出：{mission_info['score']:.4f} → {mi2['score']:.4f}"
                 f"（{N} → {N + 1} 棒，Δv {mission_info['total_dv_mps']:,.0f} → "
                 f"{mi2['total_dv_mps']:,.0f} m/s），採用重搜解。")
        return b2, t2, mi2, opt2
    log.info(f"🧭 primer 重搜未勝過原解（重搜 {mi2['score']:.4f} vs 原 "
             f"{mission_info['score']:.4f}），沿用原解。")
    return None


def legalize_violating_winner(config, burns, times, mission_info, optimizer):
    """HAP-67 Stage 2 接線：DE 贏家若有「超標但 Earth-safe」的違規棒，自動把它拆成合法
    多棒版（`burn_splitter.legalize_route`）並回傳新的 (burns_vnb, times, mission_info)；
    拆不出或沒違規就回 None（呼叫端沿用原解）。

    這是「先給大致路線(允許違規)、再拆分」方法論的正式接線：DE 只管找路線、允許違規，
    真正把違規合法化交給確定性拆分器 + joint NLP（目標函數=真實 calculate_score）。驗證
    見 docs/HAP67_SPLIT_PIPELINE_PLAN.md（contest.json：88.32 含 −10 → 98.31 零違規、
    GMAT 定燒命中、+9.99 分）。

    預設開；strategy.AUTO_SPLIT_LEGALIZE=false 可關（退回舊行為：違規解原樣交出去）。
    """
    if not bool(config.get("strategy", {}).get("AUTO_SPLIT_LEGALIZE", True)):
        return None
    if int(mission_info.get("penalty_count", 0)) <= 0:
        return None  # 沒有違規棒，沒東西要拆

    opt = optimizer
    mu, j2, j3, j4, re = opt.MU, opt.J2_VAL, opt.J3_VAL, opt.J4_VAL, opt.RE_VAL
    mc, T_max = opt.MIN_COAST_TIME, opt.T_max
    x = np.asarray(mission_info["x"], dtype=np.float64)
    N0 = int(mission_info["num_burns"])

    def _p(r, v, tt):
        return propagate_dop853(r, v, float(tt), 60.0, mu, j2, j3, j4, re)

    def _sph(rr, th, ph):
        st = math.sin(th)
        return np.array([rr * st * math.cos(ph), rr * st * math.sin(ph), rr * math.cos(th)])

    # 解碼標準決策向量 → route（球座標慣例跟 reconstruct_mission_logs 逐字一致）
    t0 = float(x[0]); cur = t0
    r, v = _p(opt.B_r0, opt.B_v0, t0)
    leading_dvs, leading_coasts, idx = [], [], 1
    for _ in range(1, N0):
        dvv = _sph(x[idx], x[idx + 1], x[idx + 2]); cf = x[idx + 3]; idx += 4
        mx = T_max - cur - mc
        tco = mc + cf * (mx - mc) if mx > mc else mc
        leading_dvs.append(dvv); leading_coasts.append(tco)
        v = v + dvv; r, v = _p(r, v, tco); cur += tco
    flf = x[-4]; mxf = T_max - cur
    tfin = mc + flf * (mxf - mc) if mxf > mc else mc
    icpt = cur + tfin
    r_A, _ = _p(opt.A_r0, opt.A_v0, icpt)
    target = r_A + _sph(x[-3], x[-2], x[-1])

    res = legalize_route(
        t0=t0, leading_dvs=leading_dvs, leading_coasts=leading_coasts,
        terminal_coast=tfin, target=target,
        cap=opt.MAX_DV_SOFT, min_coast=mc, mu=mu, j2=j2, j3=j3, j4=j4, re=re,
        min_periapsis=opt.MIN_PERIAPSIS, max_revs=opt.LAMBERT_MAX_REVS,
        A_r0=opt.A_r0, A_v0=opt.A_v0, B_r0=opt.B_r0, B_v0=opt.B_v0,
        k_t=opt.k_t, C_t=opt.C_t, k_v=opt.k_v, C_v=opt.C_v, T_max=T_max,
        miss_tol=opt.MISS_TOLERANCE_SOFT, n_span=1, maxiter=80)
    if res is None or not res["feasible"]:
        log.info("⚠️ HAP-67 自動拆分：這個違規解在段數上限內拆不出合法版，沿用原解。")
        return None

    # free-ECI 結果 → 每棒「燒前狀態」→ VNB；組回 script_generator / mission_info 要的格式
    Nf = int(res["N"]); xf = np.asarray(res["x"], dtype=np.float64)
    t0f = float(xf[0]); coastsf = xf[1:1 + Nf]; dvsf = xf[1 + Nf:].reshape(Nf, 3)
    rr, vv = _p(opt.B_r0, opt.B_v0, t0f); states = []
    for i in range(Nf):
        states.append((rr.copy(), vv.copy())); vv = vv + dvsf[i]; rr, vv = _p(rr, vv, coastsf[i])
    m = _simulate_free(xf, Nf, mu, j2, j3, j4, re, opt.A_r0, opt.A_v0, opt.B_r0, opt.B_v0)
    burns_vnb = [tuple(float(c) for c in to_vnb_frame(rp, vp, dvsf[i]))
                 for i, (rp, vp) in enumerate(states)]
    times_new = [float(t0f)] + [float(c) for c in coastsf]
    new_mi = {
        "x": xf, "num_burns": Nf,
        "score": float(res["score"]), "miss_km": float(res["miss_km"]),
        "total_dv_mps": float(res["total_dv_mps"]), "T_team": float(m["T_team"]),
        "penalty_count": 0,
        # 拆分解每棒都是直接算好的 ECI 燒、legalize_route 已驗證命中容許球內，沒有「Lambert
        # 猜測靠 DC 收斂」這回事，本來就自洽——對齊 dc_converged 語意設 True。
        "dc_converged": True,
        "aim_point": tuple(float(c) for c in m["r_final"]),
        "final_burn_dv_mps": float(res["dv_mps"][-1]),
        "earth_safe": bool(float(np.min(m["arc_minr"])) >= opt.MIN_PERIAPSIS - 1e-3),
        "min_arc_radius_km": float(np.min(m["arc_minr"])),
    }
    log.info(f"\n🔧 HAP-67 自動拆分：違規解 {mission_info['score']:.4f}（{mission_info['penalty_count']} 次違規）"
             f" → 合法 {new_mi['score']:.4f}（{Nf} 棒、零違規、總Δv {new_mi['total_dv_mps']:,.0f} m/s）"
             f"，差 {new_mi['score']-mission_info['score']:+.4f} 分。")
    return burns_vnb, times_new, new_mi


def _solve_pipeline(config):
    """一顆 SEED 的完整求解：搜尋 → C2 primer 條件式重搜 →（Earth-safe 時）拆棒合法化。
    回傳 (burns, times, mission_info, optimizer)；搜尋失敗回 (None, None, None, None)。
    **不印 Earth-safe 警告**——那只該對最終勝出解印一次（見 main / run_seed_portfolio），
    不然 seed-portfolio 會對每顆中間候選都吼一次。"""
    burns, times, mi, opt = run_study_over_revs(config)
    if burns is None or times is None:
        return None, None, None, None
    _c2 = primer_guided_research(config, burns, times, mi, opt)
    if _c2 is not None:
        burns, times, mi, opt = _c2
    if bool(mi.get("earth_safe", True)):
        _legal = legalize_violating_winner(config, burns, times, mi, opt)
        if _legal is not None:
            burns, times, mi = _legal
    return burns, times, mi, opt


def run_seed_portfolio(config):
    """Seed-portfolio 小模式（2026-09-22）：跑 N 顆 SEED 各自完整求解（含拆棒合法化），
    照規則§6 留**拆後**分最高的那顆。

    動機（本 session contest 分析）：單一 SEED 是決定性的，但可能抽到「低籤」——落在略差
    的盆地 / 拆棒後差那 0.01。跑幾顆再留拆後最高分，幾乎免費穩拿家族高端（實測 +0.008）。
    這是繳交前的品質旋鈕，不是搜尋演算法改動。

    N = strategy.SEED_PORTFOLIO_N（預設 1 = 關，行為與單跑逐位元相同）。基準 SEED 取
    optimization.SEED（沒設用 0），跑 base..base+N-1 保證可重現。回傳勝出的
    (burns, times, mission_info, optimizer)。"""
    N = max(1, int(config.get("strategy", {}).get("SEED_PORTFOLIO_N", 1)))
    if N == 1:
        return _solve_pipeline(config)

    base = config.get("optimization", {}).get("SEED")
    base = 0 if base is None else int(base)
    best = None
    table = [f"\n🎰 Seed-portfolio：跑 {N} 顆 SEED，§6 留拆後分最高（避開低籤）",
             f"   {'SEED':>6}{'Score':>10}{'Δr_min(m)':>13}{'ΔV_team(m/s)':>15}{'棒數':>6}"]
    for i in range(N):
        sd = base + i
        cfg = copy.deepcopy(config)
        cfg.setdefault("optimization", {})["SEED"] = sd
        log.info(f"\n🎰 Seed-portfolio 第 {i + 1}/{N} 顆（SEED={sd}）")
        b, t, mi, opt = _solve_pipeline(cfg)
        if b is None or not isinstance(mi, dict):
            table.append(f"   {sd:>6}   （全軍覆沒，不列入挑選）")
            continue
        key = tiebreak_rank_key(mi["score"], mi["miss_km"], mi["total_dv_mps"],
                                mi["T_team"], eps=opt.TIEBREAK_SCORE_EPS)
        table.append(f"   {sd:>6}{mi['score']:>10.4f}{mi['miss_km'] * 1000:>13,.1f}"
                     f"{mi['total_dv_mps']:>15,.1f}{mi['num_burns']:>6}")
        if best is None or key < best[0]:
            best = (key, sd, b, t, mi, opt)
    if best is None:
        log.error("Seed-portfolio：所有 SEED 都沒跑出可用解。")
        return None, None, None, None
    table.append(f"   → 採用 SEED={best[1]}（Score {best[4]['score']:.4f}，{best[4]['num_burns']} 棒）")
    log.info("\n".join(table))
    return best[2], best[3], best[4], best[5]


def main():
    # 效能分析器設定
    if ENABLE_PROFILING:
        profiler = cProfile.Profile()
        profiler.enable()

    multiprocessing.freeze_support()
    warnings.filterwarnings("ignore")

    args = parse_args()

    # 執行期日誌（HAP-68）：終端機依 -v/-q 決定詳略，完整 DEBUG 一律落到 outputs/run.log
    # （mode='w'，只留最新一次），終端機再怎麼精簡都追得回細節。
    os.makedirs("outputs", exist_ok=True)
    setup_logging(verbose=args.verbose, quiet=args.quiet,
                  logfile=os.path.join("outputs", "run.log"))

    config = load_or_create_config(args.config)

    # GmatConsole 路徑解析順序：--gmat-console > config.json 的 local.gmat_console_path
    # > 這裡寫死的最後備援值 (見 GMAT_CONSOLE_DEFAULT 的說明)。
    gmat_console_path = (
        args.gmat_console
        or config.get("local", {}).get("gmat_console_path")
        or GMAT_CONSOLE_DEFAULT
    )

    start_time = time.perf_counter()

    # 1. 啟動最佳化器（含 L-SHADE、NLP 微調、C2 primer 條件式重搜、拆棒合法化——整條
    #    「一顆 SEED → 一個可交解」的求解流程包在 _solve_pipeline 裡）。外面再包一層
    #    seed-portfolio：strategy.SEED_PORTFOLIO_N>1 時跑 N 顆 SEED、§6 留拆後分最高的
    #    避開低籤（預設 1 = 關，行為與單跑相同）。內層每顆仍走 REVS 集成
    #    (REVS_ENSEMBLE)。回傳的 optimizer 是勝出解的實例，後面產腳本/印拆解都用它。
    burns, times, mission_info, optimizer = run_seed_portfolio(config)

    if burns is None or times is None:
        log.error("任務終止。")
        return

    # Earth-safe 硬性閘門 (2026-09-09, HAP-48)：初賽證實「軌跡穿過地表」是官方失格線
    # (撞地球的隊伍被判 F)。搜尋端 (fast_fitness_evaluator) 本來就會避開撞地球的解，
    # 但當 T_max 內根本沒有 Earth-safe 合法解時，搜尋只能回報「最不爛」的違規解，那有
    # 可能是鑽地球的。這裡在繳交路徑上再擋一次（對最終勝出解印一次）：撞地球就不產生
    # 繳交腳本、大聲標記，避免重演「分數漂亮但物理不成立、送出去被失格」(見作廢的 99.996)。
    earth_safe = bool(mission_info.get("earth_safe", True))
    if not earth_safe:
        alt = mission_info.get("min_arc_radius_km", float("nan")) - 6378.137
        log.warning("\n" + "🔴" * 30
                    + f"\n  警告：這個解的軌跡會穿過地球 (全程最低高度 {alt:,.0f} km，低於地表)。"
                    + "\n  官方會判此類軌跡失格 (初賽已證實)，**不會產生繳交腳本，絕對不可繳交**。"
                    + "\n  通常代表 T_max 內沒有 Earth-safe 合法解 —— 用 feasibility.py 確認，"
                    + "\n  或放寬 T_max / 調整棒數再重跑。仍會產出 outputs/output.txt 供診斷。"
                    + "\n" + "🔴" * 30)

    # 分數拆解 + 交換率（純加印，不改計算；見 print_score_breakdown）
    print_score_breakdown(mission_info, optimizer)

    # 2. 產出 GMAT 腳本 (打靶邊界跟著規則的 ΔV_lim 走，避免 GMAT 端偷偷超標)
    script_generator(
        config["orbit_A"]["SMA"], config["orbit_A"]["ECC"], config["orbit_A"]["INC"],
        config["orbit_A"]["RAAN"], config["orbit_A"]["AOP"], config["orbit_A"]["TA"],
        config["orbit_B"]["SMA"], config["orbit_B"]["ECC"], config["orbit_B"]["INC"],
        config["orbit_B"]["RAAN"], config["orbit_B"]["AOP"], config["orbit_B"]["TA"],
        burns, times, aim_point=mission_info["aim_point"],
        max_dv=optimizer.MAX_DV, gravity_degree=optimizer.GRAVITY_DEGREE,
        model_scale=config.get("strategy", {}).get("GMAT_MODEL_SCALE", 0.5),
    )

    end_time = time.perf_counter()
    execution_time = end_time - start_time

    minute_note = f" (約 {execution_time / 60:.2f} 分鐘)" if execution_time > 60 else ""
    log.info(f"\n⏳ 總計算時間: {execution_time:.2f} 秒{minute_note}")

    # 3. 自動呼叫 GMAT 做無頭驗證，不用再手動開 GUI 點來點去
    gmat_result = None
    if args.no_gmat:
        log.info("（跳過了 GMAT 驗證，記得手動開 GMAT 跑一次 outputs/output.txt 確認 InterceptSuccess）")
    else:
        gmat_result = run_gmat_verification(gmat_console_path, os.path.join("outputs", "output.txt"))
        if gmat_result:
            match = "✅" if gmat_result["intercept_success"] else "❌"
            dv_match = "✅" if gmat_result["final_burn_legal"] else "❌"
            # 一般版本 (DC) 結果：終端機給一行事件摘要 (命中/Targeter/最後一棒)；GMAT vs Python
            # 的逐項比對表是診斷細節，收進 DEBUG（-v 或 outputs/run.log 看，見準則：GMAT 表 → -v）。
            d_miss = abs(gmat_result['miss_km'] - mission_info['miss_km']) * 1000.0
            d_dv = abs(gmat_result['final_burn_dv_mps'] - mission_info['final_burn_dv_mps'])
            log.info(f"🛰️ GMAT 一般版(DC)：命中 {match} {'成功' if gmat_result['intercept_success'] else '失敗'}"
                     f"   Targeter {'✅收斂' if gmat_result['targeter_converged'] else '⚠️未收斂'}"
                     f"   最後一棒 {dv_match} {'合規' if gmat_result['final_burn_legal'] else '超過上限'}"
                     f"   (Δr {gmat_result['miss_km']*1000:,.0f}m)")
            log.debug(
                f"── GMAT 驗證：一般版本 (含 DC 求解器) {'─' * 22}\n"
                f"  {'':<12}{'GMAT':>14}{'Python':>14}{'差距':>12}\n"
                f"  {'Δr_min':<12}{gmat_result['miss_km']*1000:>13,.3f}m"
                f"{mission_info['miss_km']*1000:>13,.3f}m{d_miss:>11,.3f}m\n"
                f"  {'最後一棒 Δv':<10}{gmat_result['final_burn_dv_mps']:>13,.1f}m/s"
                f"{mission_info['final_burn_dv_mps']:>11,.1f}m/s{d_dv:>9,.1f}m/s\n"
                f"  {'T_team':<12}{gmat_result['t_team_sec']:>13,.2f}s"
                f"{mission_info['T_team']:>13,.2f}s\n"
                f"  報表：{gmat_result['report_path']}")

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
    if not earth_safe:
        # Earth-safe 閘門擋下 (HAP-48)：撞地球的解不產生繳交腳本，避免手滑送出去被失格。
        log.warning("⛔ Earth-safe 閘門：此解撞地球，跳過『固定燃燒版本』繳交腳本的產生。")
    elif not args.no_gmat and not args.no_fixed_script:
        clean_dc = bool(
            gmat_result and gmat_result["intercept_success"]
            and gmat_result["targeter_converged"] and gmat_result["final_burn_legal"]
        )
        final_burn_vnb = None
        if clean_dc:
            fixed_script_source = "gmat_dc"
            final_burn_vnb = gmat_result["final_burn_vnb"]
            log.info("🔒 一般版本 (GMAT DC) 驗證乾淨通過，用 GMAT 收斂後的值產生固定燃燒版本...")
        elif mission_info["dc_converged"]:
            fixed_script_source = "python_fallback"
            final_burn_vnb = tuple(burns[-1])
            reason = "GMAT 呼叫失敗/找不到 GmatConsole" if gmat_result is None else (
                "Targeter 未收斂" if not gmat_result["targeter_converged"] else
                "命中失敗 (Δr > 5km)" if not gmat_result["intercept_success"] else
                "最後一棒超過 Δv 上限"
            )
            # 為什麼要 fallback（DC 的 Vary 邊界搆不到需求量級等）寫在上面這段區塊註解裡。
            log.info(f"⚠️ 一般版本 (GMAT DC) 沒有乾淨通過（{reason}），改用 Python 自算的燃燒值"
                     f"產生固定燃燒版本...")
        else:
            log.warning("⚠️ 一般版本沒有通過，Python 自己的模型也沒收斂到瞄準點——這組解本身"
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
                model_scale=config.get("strategy", {}).get("GMAT_MODEL_SCALE", 0.5),
            )
            fixed_script_result = run_gmat_verification(
                gmat_console_path, os.path.join("outputs", "output_submit.txt")
            )
            if fixed_script_result:
                fmatch = "✅" if fixed_script_result["intercept_success"] else "❌"
                fdv_match = "✅" if fixed_script_result["final_burn_legal"] else "⚠️"
                src_label = "GMAT DC 收斂後的值" if fixed_script_source == "gmat_dc" \
                    else "Python 自己算的值 (DC fallback)"
                # 這是要繳交的那份，結果留一行事件級摘要（命中/合規/Δr）；細節(檔名/來源/Δr精確值)
                # 收進 DEBUG。
                log.info(f"📤 固定燃燒版(建議繳交)：命中 {fmatch} "
                         f"{'成功' if fixed_script_result['intercept_success'] else '失敗'}"
                         f"   最後一棒 {fdv_match} {'合規' if fixed_script_result['final_burn_legal'] else '超過每棒上限'}"
                         f"   (Δr {fixed_script_result['miss_km']*1000:,.0f}m, "
                         f"Δv {fixed_script_result['final_burn_dv_mps']:,.0f} m/s)")
                log.debug(f"  檔案：outputs/output_submit.txt　燃燒值來源：{src_label}")
                if fixed_script_result["intercept_success"] and fixed_script_result["final_burn_legal"]:
                    log.info("  👉 命中且合規，可以直接繳交。")
                elif fixed_script_result["intercept_success"]:
                    log.info("  👉 命中但超標：依規則第 5 節每次違規扣 10 分（非取消資格），仍可繳交；"
                             "但先用 feasibility.py / sweep_burns.py 確認沒有更好的合法解。")
                else:
                    log.warning("  ⚠️ 沒有命中：DC 來源不該發生；Python fallback 代表這組解站不住腳，不建議採用。")
            else:
                log.warning("  ⚠️ 固定版本沒有跑成功 (GMAT 呼叫失敗)。")

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