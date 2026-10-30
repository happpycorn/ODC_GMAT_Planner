"""保存預設設定、GMAT 備援路徑與設定讀取流程
主要入口為 load_or_create_config。
"""
from odc.paths import default_config_path
import os
import sys
import json
from odc.config.gmat_env import GMAT_ENV_KEYS, resolve_gmat_env, validate_gmat_env
from odc.config.validator import validate_config, ConfigValidationError
from odc.runlog import log, setup as setup_logging


# GmatConsole 路徑的最後備援值 (只在 --gmat-console 沒給、config.json 也沒有
# local.gmat_console_path 時才用得到)。這個路徑寫死在這裡、被 git 追蹤，換一台機器/
# 換一個人開發大概率對不上——所以優先順序是 --gmat-console > config 的
# local.gmat_console_path (config.json 本來就被 gitignore 排除，換人/換機器各自維護
# 自己的這塊，不用改這個檔案) > 這裡的最後備援值 (目前是我這台機器的路徑，純粹是圖
# 我自己方便，不建議依賴它)。
GMAT_CONSOLE_DEFAULT = "/Users/corn/Documents/GMAT R2026a/bin/GmatConsole"

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
        # "MAX_TOTAL_DV_MPS": null,          # 選填：總 Δv 上限，超過失格 (排位賽 3000)；
        # 沒填 = 沒有上限 (初賽)。排位賽範本見 configs/shared/ranking_round.json。
        # 主辦方公告的環境計分參數 (依軌道分布狀況，每次比賽前會公告)
        "k_t": 0.0001,
        "C_t": 11000.0,
        "k_v": 0.005,
        "C_v": 1200.0,
    },
    "strategy": {
        "EPHEM_CACHE": True,       # A 全程、B 第一棒前的固定軌道檢查點（無插值）
        "EPHEM_CACHE_STEP_SEC": 60.0,
        "GRAVITY_DEGREE": 2,  # 重力場要算到第幾階 zonal harmonic：0=純點質量, 2=J2,
                              # 3=J2+J3, 4=J2+J3+J4。不確定某一輪/場景實際開多少階擾動時
                              # 用這個切換，Python 端跟產生的 GMAT script 會同步套用
                              # (GMAT 端 Order 固定收在 0，只算 zonal 不算 tesseral，
                              # 確保兩邊模型完全對齊)，不用改程式碼
        "MISS_TOLERANCE_KM": 5.0,  # 規則只要求 Δr <= 這個值 (預設對齊規則的 5km)，可以
                                    # 彈性調小 (甚至設 0 退回精準瞄準)，讓最後一棒 Lambert
                                    # 在容許範圍內找最省油的落點，而不是死盯著 A 的精確位置
        "AUTO_SPLIT_LEGALIZE": True,  # 低邏輯棒數先找 route，若贏家超標再動態拆成合法多棒解
        "SPLIT_LEADING": False,  # 拆棒階段先等分超標前導棒，再重算終端攔截
        "SPLIT_AWARE_TERMINAL": True,  # C4：終端棒超標但拆得掉時，搜尋/挑贏家用「拆後估計分數」
                                       # 不扣 10 分；拆不出來會自動用 false 重搜當退路
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
        "TOL": 0.02,  # Score 是 0~100 分量表；只有啟用早停時才套用
        "EARLY_STOP_ENABLED": False,  # 預設跑滿 MAXITER；實驗確認品質後才考慮啟用
        "SEED": None,  # 設一個整數可以讓同一組設定每次重現一樣的結果，方便比較改動
    },
}

def load_or_create_config(filename=default_config_path()):
    """
    讀取設定檔；如果不存在，則建立一個預設的設定檔。
    不管是新建的還是讀進來的，都會跑一次 validate_config()——打錯字/型別錯/
    不合理的值 (負的 SMA、ECC 超出 [0,1) 之類) 會在這裡直接攔下來噴清楚的錯誤
    訊息，而不是讓程式一路跑到 poliastro/mealpy 深處才炸出一段看不懂的 traceback。
    驗證失敗時印出訊息並用 sys.exit(1) 結束 (而不是往上丟例外)，讓失敗訊息乾淨、
    不夾帶一堆跟問題無關的內部呼叫堆疊。
    """
    os.makedirs(os.path.dirname(filename) or ".", exist_ok=True)
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
        validate_gmat_env(config)  # GMAT 端設定（FORCE_MODEL 等），見 odc/config/gmat_env.py
    except (ConfigValidationError, ValueError) as exc:
        log.error(f"❌ {filename} 驗證失敗:\n{exc}")
        sys.exit(1)

    return config
