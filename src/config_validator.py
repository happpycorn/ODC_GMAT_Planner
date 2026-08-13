# src/config_validator.py
"""
config.json 的欄位驗證。

目的很單純：在真正拿去初始化軌道 (poliastro)/最佳化器 (mealpy) 之前，先把整份
設定檔掃過一輪，把「打錯字/填了型別不對或不合理的值」這種錯誤，從程式深處某個
難以理解的 numpy/poliastro/mealpy 例外，攔在最前面變成一句講清楚「哪個欄位、
為什麼不對」的訊息。

只做「型別/值域合不合理」層級的檢查 (例如 ECC 是不是 [0,1)、SMA 是不是正數)，
不做「跟這次賽事規則是否吻合」的語意檢查 (例如今年 k_t 應該是多少)，那個還是要
使用者自己核對官方規則文件。

硬錯誤 (欄位缺漏/型別錯/物理上不成立) 用 ConfigValidationError 一次全部列出來，
呼叫端接住就能印出來後乾淨結束，不會噴一長串 traceback。
軟性可疑值 (例如 MISS_TOLERANCE_KM 設超過 5 會被 optimizer 悄悄夾回 5) 只印警告，
不擋執行。
"""
import math

_EARTH_RE_KM = 6378.137
_ORBIT_FIELDS = ("SMA", "ECC", "INC", "RAAN", "AOP", "TA")


class ConfigValidationError(ValueError):
    """設定檔驗證失敗；訊息裡會列出每一個問題欄位跟原因。"""
    pass


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _validate_orbit(orbit_cfg, label: str, errors: list):
    if not isinstance(orbit_cfg, dict):
        errors.append(f"{label} 應該是一個物件，但收到 {type(orbit_cfg).__name__}")
        return

    missing = [f for f in _ORBIT_FIELDS if f not in orbit_cfg]
    if missing:
        errors.append(f"{label} 缺少欄位: {missing}")

    numeric_ok = {}
    for f in _ORBIT_FIELDS:
        if f not in orbit_cfg:
            continue
        v = orbit_cfg[f]
        ok = _is_number(v)
        numeric_ok[f] = ok
        if not ok:
            errors.append(f"{label}.{f} 應該是有限數字，但收到 {v!r} ({type(v).__name__})")

    if numeric_ok.get("SMA"):
        sma = orbit_cfg["SMA"]
        if sma <= 0:
            errors.append(f"{label}.SMA 必須 > 0 (km)，但收到 {sma}")

    if numeric_ok.get("ECC"):
        ecc = orbit_cfg["ECC"]
        if not (0.0 <= ecc < 1.0):
            errors.append(
                f"{label}.ECC 必須落在 [0, 1) 之間 (目前程式只處理橢圓/圓軌道；"
                f"雙曲線軌道是排位賽/四強賽場景，還沒實作)，但收到 {ecc}"
            )

    if numeric_ok.get("INC"):
        inc = orbit_cfg["INC"]
        if not (0.0 <= inc <= 180.0):
            errors.append(f"{label}.INC 必須落在 [0, 180] 度之間，但收到 {inc}")

    # 近地點半徑要在地球表面以上，軌道才有物理意義 (SMA、ECC 都合法時才檢查)
    if numeric_ok.get("SMA") and numeric_ok.get("ECC"):
        sma, ecc = orbit_cfg["SMA"], orbit_cfg["ECC"]
        if sma > 0 and 0.0 <= ecc < 1.0:
            periapsis = sma * (1.0 - ecc)
            if periapsis < _EARTH_RE_KM:
                errors.append(
                    f"{label}: 近地點半徑 SMA*(1-ECC) = {periapsis:.1f} km 小於地球半徑 "
                    f"{_EARTH_RE_KM:.1f} km，這個軌道會穿過地球，物理上不成立 "
                    f"(SMA={sma}, ECC={ecc})"
                )


def _validate_rules(rules_cfg, errors: list):
    """rules：主辦方規定/公告的數字 (ΔV_lim、機動間隔、T_max 倍數、k_t/C_t/k_v/C_v)。"""
    if not isinstance(rules_cfg, dict):
        errors.append(f"rules 應該是一個物件，但收到 {type(rules_cfg).__name__}")
        return

    required = ["MAX_DV_MPS", "MIN_MANEUVER_INTERVAL_SEC", "T_MAX_PERIOD_MULTIPLE",
                "k_t", "C_t", "k_v", "C_v"]
    missing = [f for f in required if f not in rules_cfg]
    if missing:
        errors.append(f"rules 缺少欄位: {missing}")

    # 這三個是規則規定的數字 (ΔV_lim/機動間隔下限/T_max 週期倍數)，必須是正數才有意義
    if "MAX_DV_MPS" in rules_cfg:
        v = rules_cfg["MAX_DV_MPS"]
        if not _is_number(v) or v <= 0:
            errors.append(f"rules.MAX_DV_MPS 必須是 >0 的數字 (單位 m/s)，但收到 {v!r}")
    if "MIN_MANEUVER_INTERVAL_SEC" in rules_cfg:
        v = rules_cfg["MIN_MANEUVER_INTERVAL_SEC"]
        if not _is_number(v) or v < 0:
            errors.append(f"rules.MIN_MANEUVER_INTERVAL_SEC 必須是 >=0 的數字 (單位秒)，但收到 {v!r}")
    if "T_MAX_PERIOD_MULTIPLE" in rules_cfg:
        v = rules_cfg["T_MAX_PERIOD_MULTIPLE"]
        if not _is_number(v) or v <= 0:
            errors.append(f"rules.T_MAX_PERIOD_MULTIPLE 必須是 >0 的數字，但收到 {v!r}")

    for f in ("k_t", "C_t", "k_v", "C_v"):
        if f in rules_cfg and not _is_number(rules_cfg[f]):
            errors.append(f"rules.{f} 必須是有限數字，但收到 {rules_cfg[f]!r}")


def _validate_strategy(strategy_cfg, errors: list):
    """strategy：我們自己的任務設計選項，不是規則要求 (USE_J2、MISS_TOLERANCE_KM)。"""
    if not isinstance(strategy_cfg, dict):
        errors.append(f"strategy 應該是一個物件，但收到 {type(strategy_cfg).__name__}")
        return

    required = ["USE_J2", "MISS_TOLERANCE_KM"]
    missing = [f for f in required if f not in strategy_cfg]
    if missing:
        errors.append(f"strategy 缺少欄位: {missing}")

    if "USE_J2" in strategy_cfg and not isinstance(strategy_cfg["USE_J2"], bool):
        errors.append(f"strategy.USE_J2 必須是 true/false，但收到 {strategy_cfg['USE_J2']!r}")

    if "MISS_TOLERANCE_KM" in strategy_cfg:
        v = strategy_cfg["MISS_TOLERANCE_KM"]
        if not _is_number(v) or v < 0:
            errors.append(f"strategy.MISS_TOLERANCE_KM 必須是 >=0 的數字，但收到 {v!r}")


def _validate_local(local_cfg, errors: list):
    """local：跟任務/規則完全無關、純粹是「這台機器」的設定 (目前只有 GMAT 路徑)。
    選填區塊——config.json 本來就被 gitignore 排除，換電腦/換人開發本來就該各自維護
    自己的這個區塊，不應該寫死在 main.py 裡進 git。"""
    if not isinstance(local_cfg, dict):
        errors.append(f"local 應該是一個物件，但收到 {type(local_cfg).__name__}")
        return
    if "gmat_console_path" in local_cfg and not isinstance(local_cfg["gmat_console_path"], str):
        errors.append(f"local.gmat_console_path 必須是字串 (路徑)，但收到 {local_cfg['gmat_console_path']!r}")


def _validate_optimization(opt_cfg, errors: list):
    if not isinstance(opt_cfg, dict):
        errors.append(f"optimization 應該是一個物件，但收到 {type(opt_cfg).__name__}")
        return

    required = ["MAX_BURNS", "MAXITER", "POPSIZE", "NUM_THREADS", "MAX_EARLY_STOP", "TOL"]
    missing = [f for f in required if f not in opt_cfg]
    if missing:
        errors.append(f"optimization 缺少欄位: {missing}")

    if "MAX_BURNS" in opt_cfg:
        mb = opt_cfg["MAX_BURNS"]
        if not isinstance(mb, list) or len(mb) == 0:
            errors.append(f"optimization.MAX_BURNS 必須是非空陣列 (推進次數清單)，但收到 {mb!r}")
        else:
            bad = [b for b in mb if not (_is_int(b) and b >= 1)]
            if bad:
                errors.append(
                    f"optimization.MAX_BURNS 裡每個值都必須是 >=1 的整數 (推進次數)，"
                    f"但有不合法的值: {bad}"
                )

    for f in ("MAXITER", "MAX_EARLY_STOP", "POPSIZE"):
        if f in opt_cfg:
            v = opt_cfg[f]
            if not (_is_int(v) and v >= 1):
                errors.append(f"optimization.{f} 必須是 >=1 的整數，但收到 {v!r}")

    if "NUM_THREADS" in opt_cfg:
        v = opt_cfg["NUM_THREADS"]
        if not _is_int(v):
            errors.append(f"optimization.NUM_THREADS 必須是整數 (<=0 代表自動判斷)，但收到 {v!r}")

    if "TOL" in opt_cfg:
        v = opt_cfg["TOL"]
        if not _is_number(v) or v < 0:
            errors.append(f"optimization.TOL 必須是 >=0 的數字，但收到 {v!r}")

    if "SEED" in opt_cfg:
        v = opt_cfg["SEED"]
        if v is not None and not _is_int(v):
            errors.append(f"optimization.SEED 必須是整數或 null，但收到 {v!r}")


def validate_config(config) -> None:
    """
    驗證整份 config；有任何硬錯誤就一次收集起來丟 ConfigValidationError，
    軟性可疑值直接印警告 (不中斷)。全部通過才會正常 return。
    """
    if not isinstance(config, dict):
        raise ConfigValidationError(f"設定檔最外層必須是一個物件 (dict)，但收到 {type(config).__name__}")

    errors: list = []

    # config 分四塊必填 + 一塊選填：orbit_A/orbit_B (軌道)、rules (主辦方規定/公告，
    # 我們不能改)、strategy (我們自己的任務設計選項)、optimization (純演算法搜尋設定)。
    # local (選填) 是跟任務/規則完全無關的「這台機器」設定 (目前只有 GMAT 路徑)，沒有
    # 也完全合法，不列進 top_required。
    top_required = ["orbit_A", "orbit_B", "rules", "strategy", "optimization"]
    missing = [k for k in top_required if k not in config]
    if missing:
        errors.append(f"config 缺少欄位: {missing}")

    if "orbit_A" in config:
        _validate_orbit(config["orbit_A"], "orbit_A", errors)
    if "orbit_B" in config:
        _validate_orbit(config["orbit_B"], "orbit_B", errors)
    if "rules" in config:
        _validate_rules(config["rules"], errors)
    if "strategy" in config:
        _validate_strategy(config["strategy"], errors)
    if "local" in config:
        _validate_local(config["local"], errors)
    if "optimization" in config:
        _validate_optimization(config["optimization"], errors)

    if errors:
        header = f"設定檔驗證失敗，共 {len(errors)} 個問題:"
        body = "\n".join(f"  - {e}" for e in errors)
        raise ConfigValidationError(f"{header}\n{body}")

    # --- 軟性可疑值：不擋執行，但值得提醒使用者 ---
    rules_cfg = config.get("rules", {})
    strategy_cfg = config.get("strategy", {})
    warnings = []
    if _is_number(strategy_cfg.get("MISS_TOLERANCE_KM")) and strategy_cfg["MISS_TOLERANCE_KM"] > 5.0:
        warnings.append(
            f"strategy.MISS_TOLERANCE_KM={strategy_cfg['MISS_TOLERANCE_KM']} 超過規則門檻 5km，"
            f"optimizer 會悄悄把它夾回 5.0，不會真的用到你設的值"
        )
    if _is_number(rules_cfg.get("k_t")) and rules_cfg["k_t"] < 0:
        warnings.append("rules.k_t < 0 會讓時間分數隨任務時間變長反而變高，方向可能跟規則的意圖相反，請確認不是打錯正負號")
    if _is_number(rules_cfg.get("k_v")) and rules_cfg["k_v"] < 0:
        warnings.append("rules.k_v < 0 會讓 Δv 分數隨油耗變大反而變高，方向可能跟規則的意圖相反，請確認不是打錯正負號")

    for w in warnings:
        print(f"⚠️  設定檔警告: {w}")
