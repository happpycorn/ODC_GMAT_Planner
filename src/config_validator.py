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

    # SMA/ECC 要嘛是橢圓/圓軌道 (SMA>0, 0<=ECC<1)，要嘛是雙曲線軌道 (SMA<0, ECC>1)
    # ——排位賽 A 是雙曲線飛越軌道 (簡報第 9 頁)，所以這裡兩種都要接受，只擋
    # 「SMA/ECC 符號兜不起來」這種物理上不成立的組合。ECC==1 (拋物線) 是退化邊界
    # 情況 (SMA 理論上無限大)，目前不支援，直接當錯誤攔下來。
    if numeric_ok.get("SMA"):
        sma = orbit_cfg["SMA"]
        if sma == 0:
            errors.append(f"{label}.SMA 不能是 0 (km)——正值代表橢圓/圓軌道，負值代表雙曲線軌道")

    if numeric_ok.get("ECC"):
        ecc = orbit_cfg["ECC"]
        if ecc < 0:
            errors.append(f"{label}.ECC 必須 >= 0，但收到 {ecc}")
        elif ecc == 1.0:
            errors.append(
                f"{label}.ECC == 1 (拋物線軌道) 目前不支援 (SMA 理論上無限大，是退化邊界情況)，"
                f"如果這是排位賽的雙曲線 A，確認一下數字是不是應該是 ECC > 1"
            )

    if numeric_ok.get("SMA") and numeric_ok.get("ECC"):
        sma, ecc = orbit_cfg["SMA"], orbit_cfg["ECC"]
        if ecc != 1.0:  # ECC==1 已經在上面單獨報過錯，這裡不用重複報
            is_elliptical = 0.0 <= ecc < 1.0
            is_hyperbolic = ecc > 1.0
            if is_elliptical and sma <= 0:
                errors.append(
                    f"{label}: ECC={ecc} 是橢圓/圓軌道 (0<=ECC<1)，但 SMA={sma} 不是正數——"
                    f"橢圓/圓軌道的 SMA 必須 > 0"
                )
            elif is_hyperbolic and sma >= 0:
                errors.append(
                    f"{label}: ECC={ecc} 是雙曲線軌道 (ECC>1)，但 SMA={sma} 不是負數——"
                    f"依慣例雙曲線軌道的 SMA 必須 < 0 (這是排位賽的 A 軌道類型，見簡報第 9 頁)"
                )

    if numeric_ok.get("INC"):
        inc = orbit_cfg["INC"]
        if not (0.0 <= inc <= 180.0):
            errors.append(f"{label}.INC 必須落在 [0, 180] 度之間，但收到 {inc}")

    # 近地點半徑要在地球表面以上，軌道才有物理意義。SMA*(1-ECC) 這個公式對橢圓
    # (SMA>0, ECC<1) 跟雙曲線 (SMA<0, ECC>1) 都成立、都會算出正的近地點半徑，
    # 不用分兩套公式——只有在 SMA/ECC 符號已經兜得起來時才檢查 (兜不起來的組合
    # 上面已經報過錯了，這裡再算只會產生誤導性的第二個錯誤)。
    if numeric_ok.get("SMA") and numeric_ok.get("ECC"):
        sma, ecc = orbit_cfg["SMA"], orbit_cfg["ECC"]
        sign_consistent = (sma > 0 and 0.0 <= ecc < 1.0) or (sma < 0 and ecc > 1.0)
        if sign_consistent:
            periapsis = sma * (1.0 - ecc)
            if periapsis < _EARTH_RE_KM:
                errors.append(
                    f"{label}: 近地點半徑 SMA*(1-ECC) = {periapsis:.1f} km 小於地球半徑 "
                    f"{_EARTH_RE_KM:.1f} km，這個軌道會穿過地球，物理上不成立 "
                    f"(SMA={sma}, ECC={ecc})"
                )


def _validate_rules(rules_cfg, errors: list, orbit_a_cfg=None):
    """rules：主辦方規定/公告的數字 (ΔV_lim、機動間隔、T_max 倍數、k_t/C_t/k_v/C_v)。"""
    if not isinstance(rules_cfg, dict):
        errors.append(f"rules 應該是一個物件，但收到 {type(rules_cfg).__name__}")
        return

    required = ["MAX_DV_MPS", "MIN_MANEUVER_INTERVAL_SEC",
                "k_t", "C_t", "k_v", "C_v"]

    # T_MAX_PERIOD_MULTIPLE 是**有條件**必填的。「T_max = 倍數 × A 的週期」這條公式
    # 只在 A 是橢圓/圓軌道時成立，A 是雙曲線時 (排位賽) 根本沒有週期，這個欄位沒有
    # 意義，該填的是 T_MAX_SEC。原本這裡把它列成無條件必填，跟下面 T_MAX_SEC 那段
    # 註解自己寫的「這裡不主動要求」互相矛盾，導致排位賽格式的 config (雙曲線 A +
    # T_MAX_SEC) 在驗證階段就被擋下，連 optimizer 都進不去。
    # 判斷規則：只要給了有效的 T_MAX_SEC，就不需要週期倍數 (覆寫值優先，見 optimizer)；
    # 沒給覆寫值時，A 是橢圓才要求它，A 是雙曲線則要求 T_MAX_SEC。
    has_override = (rules_cfg.get("T_MAX_SEC") is not None)
    a_is_hyperbolic = False
    if isinstance(orbit_a_cfg, dict):
        a_ecc = orbit_a_cfg.get("ECC")
        a_is_hyperbolic = _is_number(a_ecc) and a_ecc > 1.0
    if not has_override:
        if a_is_hyperbolic:
            errors.append(
                "orbit_A 是雙曲線軌道 (ECC>1，排位賽)，沒有週期可以套用 "
                "T_MAX_PERIOD_MULTIPLE，必須改用 rules.T_MAX_SEC 直接指定 T_max 秒數"
            )
        else:
            required.append("T_MAX_PERIOD_MULTIPLE")

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

    # T_MAX_SEC：選填的 T_max 直接覆寫值 (單位秒)。「T_max = 4×A的週期」這個公式
    # 只在 A 是橢圓/圓軌道時有意義——A 是雙曲線軌道時 (排位賽) 沒有週期可言，
    # T_max 要怎麼定義官方目前還沒公告 (見簡報第 9 頁「詳細競賽與計分規則擬定後，
    # 將公告」)。等公告後不管公式是什麼，都可以直接把算出來的秒數填在這裡覆寫，
    # 不用等程式碼跟著改。SMA/ECC 都合法時 (通過上面的橢圓/雙曲線一致性檢查)，
    # 只有 A 是雙曲線且沒有給這個覆寫值時才會在 optimizer.py 初始化時報錯——這裡
    # 不主動要求，因為 A 是橢圓軌道時 (初賽) 完全不需要這個欄位。
    if "T_MAX_SEC" in rules_cfg and rules_cfg["T_MAX_SEC"] is not None:
        v = rules_cfg["T_MAX_SEC"]
        if not _is_number(v) or v <= 0:
            errors.append(f"rules.T_MAX_SEC 必須是 >0 的數字 (單位秒) 或 null，但收到 {v!r}")

    for f in ("k_t", "C_t", "k_v", "C_v"):
        if f in rules_cfg and not _is_number(rules_cfg[f]):
            errors.append(f"rules.{f} 必須是有限數字，但收到 {rules_cfg[f]!r}")


_VALID_GRAVITY_DEGREES = (0, 2, 3, 4)


def _validate_strategy(strategy_cfg, errors: list):
    """strategy：我們自己的任務設計選項，不是規則要求 (GRAVITY_DEGREE、MISS_TOLERANCE_KM)。"""
    if not isinstance(strategy_cfg, dict):
        errors.append(f"strategy 應該是一個物件，但收到 {type(strategy_cfg).__name__}")
        return

    required = ["GRAVITY_DEGREE", "MISS_TOLERANCE_KM"]
    missing = [f for f in required if f not in strategy_cfg]
    if missing:
        errors.append(f"strategy 缺少欄位: {missing}")

    # GRAVITY_DEGREE：2026-08-14 從原本的 USE_J2 布林值換成這個——比賽當天實際
    # 開的重力擾動階數不一定跟現在假設的一樣，開放成可調的階數比單純 on/off 更
    # 貼近實際情況。0=點質量, 2=J2, 3=J2+J3, 4=J2+J3+J4，其他值 (例如 1，沒有
    # 對應的 zonal harmonic) 沒有意義，直接擋下來。
    if "GRAVITY_DEGREE" in strategy_cfg:
        v = strategy_cfg["GRAVITY_DEGREE"]
        if not (_is_int(v) and v in _VALID_GRAVITY_DEGREES):
            errors.append(
                f"strategy.GRAVITY_DEGREE 必須是 {_VALID_GRAVITY_DEGREES} 其中一個整數 "
                f"(0=點質量, 2=J2, 3=J2+J3, 4=J2+J3+J4)，但收到 {v!r}"
            )

    if "MAX_DV_MARGIN_MPS" in strategy_cfg:
        v = strategy_cfg["MAX_DV_MARGIN_MPS"]
        if not (_is_number(v) and v >= 0):
            errors.append(f"strategy.MAX_DV_MARGIN_MPS 必須是 >=0 的數字，但收到 {v!r}")

    if "LAMBERT_MAX_REVS" in strategy_cfg:
        v = strategy_cfg["LAMBERT_MAX_REVS"]
        if not (_is_int(v) and v >= 0):
            errors.append(f"strategy.LAMBERT_MAX_REVS 必須是 >=0 的整數，但收到 {v!r}")
        elif v > 5:
            errors.append(
                f"strategy.LAMBERT_MAX_REVS={v} 太大了。每多一圈就多算 4 組 Lambert，"
                "而飛行時間根本不夠繞那麼多圈時那些呼叫只會失敗、白花時間。"
                "T_max 是 A 的 4 個週期，設到 2~3 就涵蓋得差不多了")

    if "TIEBREAK_SCORE_EPS" in strategy_cfg:
        v = strategy_cfg["TIEBREAK_SCORE_EPS"]
        if not (_is_number(v) and v >= 0):
            errors.append(f"strategy.TIEBREAK_SCORE_EPS 必須是 >=0 的數字，但收到 {v!r}")
        elif v > 1.0:
            errors.append(
                f"strategy.TIEBREAK_SCORE_EPS={v} 太大了（分數量表是 0~100）。這個值是"
                "「分數差多少以內算打平」的門檻，設得太大等於讓平手判定去覆蓋真實的"
                "分數差距，方向是錯的。想賭官方比到小數點後兩位就設 0.005 左右")

    if "TIEBREAK_POLISH" in strategy_cfg and not isinstance(strategy_cfg["TIEBREAK_POLISH"], bool):
        errors.append("strategy.TIEBREAK_POLISH 必須是 true/false，但收到 "
                      f"{strategy_cfg['TIEBREAK_POLISH']!r}")

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
        if f not in opt_cfg:
            continue
        v = opt_cfg[f]
        if f == "MAXITER" and isinstance(v, dict):
            # MAXITER 允許是 {燃燒次數: 世代數} 字典，不只是單一整數——sweep_burns.py
            # 的粗掃階段依決策變數維度分配公平預算時會用這個形式 (見
            # src/optimizer.py 的 MissionOptimizer._maxiter_for)。一般手寫的
            # config.json 幾乎不會用到，但驗證邏輯要支援，不然粗掃階段自己組出來的
            # stage_config 會被這裡誤判成壞設定直接擋下來。
            bad_items = {
                k: val for k, val in v.items()
                if not (_is_int(k) and k >= 1 and _is_int(val) and val >= 1)
            }
            if bad_items:
                errors.append(
                    f"optimization.MAXITER 字典的每個 key 都必須是 >=1 的燃燒次數"
                    f"整數、value 都必須是 >=1 的世代數整數，但有不合法的項目: {bad_items!r}"
                )
            mb = opt_cfg.get("MAX_BURNS")
            if isinstance(mb, list):
                missing_keys = [b for b in mb if b not in v]
                if missing_keys:
                    errors.append(
                        f"optimization.MAXITER 字典沒有涵蓋 MAX_BURNS 裡的燃燒次數: "
                        f"{missing_keys}"
                    )
            continue
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
        # 傳 orbit_A 進去：T_MAX_PERIOD_MULTIPLE 是否必填，取決於 A 是橢圓還是雙曲線
        _validate_rules(config["rules"], errors, config.get("orbit_A"))
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
