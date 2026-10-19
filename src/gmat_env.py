"""GMAT 端的環境設定：力學模型開關、太空船物理參數、任務曆元（2026-10-19）。

這些設定只影響**產生的 GMAT 腳本**，不影響 Python 端的搜尋物理（Python 只算 J2–J4）。
所以刻意不放進 `src/config_validator.py`：那個檔案在 `pipeline_artifacts.PHYSICS_FILES`
裡，一改就會讓既有的 mission.json 全部讀不回來（`--from-mission` 會拒絕），而全攝動
重瞄準正是要拿既有方案來改。驗證改在 main.py 讀設定時呼叫 `validate_gmat_env`，
產腳本前 `resolve_gmat_env` 也會再擋一次。

設定都在 `strategy` 底下，全部選填，沒填就跟以前逐位元相同：

    "FORCE_MODEL": "contest_prelim" | "ranking_full"
        contest_prelim（預設）：JGM2 zonal、Degree = GRAVITY_DEGREE、Order 0、無阻力/SRP/
            第三體——跟 Python 端完全對齊的初賽模型，腳本內容跟改版前逐位元相同。
        ranking_full：排位賽官方驗證的模型——EGM96 20×20、SolidAndPole 潮汐、NRLMSISE00
            阻力（CSSI 太空天氣檔）、Sun/Luna 第三體、SRP、相對論修正。
    "GMAT_SPACECRAFT": {"DRY_MASS_KG", "CD", "CR", "DRAG_AREA_M2", "SRP_AREA_M2",
                        "SPAD_DRAG_FILE", "SPAD_SRP_FILE"}
        兩艘船共用的物理參數。預設值就是舊腳本寫死的 850 kg / 2.2 / 1.8 / 6 m² / 8 m²。
        SPAD_*_FILE 給絕對路徑時，該項改用 SPADFile 模型（規則寫阻力與輻射壓都用 SPADFile，
        但主辦單位還沒公布檔案）。
    "GMAT_SPACECRAFT_A": {...}
        只覆寫 A（外星船）的部分欄位；規則沒給任何一艘的參數，所以允許兩艘不同。
    "GMAT_EPOCH": "21545", "GMAT_EPOCH_FORMAT": "TAIModJulian"
        任務曆元（決定日月位置與太空天氣）。預設是舊腳本的 2000-01-01 12:00 TAI。
"""

FORCE_MODELS = ("contest_prelim", "ranking_full")
DEFAULT_FORCE_MODEL = "contest_prelim"

# 舊腳本寫死的值；預設輸出要逐位元不變，所以預設值不能改。
DEFAULT_SPACECRAFT = {
    "DRY_MASS_KG": 850.0,
    "CD": 2.2,
    "CR": 1.8,
    "DRAG_AREA_M2": 6.0,
    "SRP_AREA_M2": 8.0,
    "SPAD_DRAG_FILE": None,
    "SPAD_SRP_FILE": None,
}
_POSITIVE_KEYS = ("DRY_MASS_KG", "DRAG_AREA_M2", "SRP_AREA_M2")
_SPAD_KEYS = ("SPAD_DRAG_FILE", "SPAD_SRP_FILE")
DEFAULT_EPOCH = "21545"
DEFAULT_EPOCH_FORMAT = "TAIModJulian"
EPOCH_FORMATS = ("TAIModJulian", "UTCModJulian", "TTModJulian", "A1ModJulian",
                 "TAIGregorian", "UTCGregorian", "TTGregorian", "A1Gregorian")

# 只有這幾個 strategy 欄位屬於 GMAT 端；重瞄準時允許用 --config 覆寫存檔裡的值
GMAT_ENV_KEYS = ("FORCE_MODEL", "GMAT_SPACECRAFT", "GMAT_SPACECRAFT_A",
                 "GMAT_EPOCH", "GMAT_EPOCH_FORMAT")


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf")


def _script_safe(s):
    """會被寫進 GMAT 單引號字串的值：ASCII、不含引號和換行。"""
    return isinstance(s, str) and s.isascii() and not any(c in s for c in "'\"\n\r;")


def _check_spacecraft(name, sc, errors):
    if not isinstance(sc, dict):
        errors.append(f"strategy.{name} 應該是物件，但收到 {type(sc).__name__}")
        return
    unknown = sorted(set(sc) - set(DEFAULT_SPACECRAFT))
    if unknown:
        errors.append(f"strategy.{name} 有不認得的欄位 {unknown}；可用欄位：{list(DEFAULT_SPACECRAFT)}")
    for k in _POSITIVE_KEYS:
        if k in sc and not (_is_number(sc[k]) and sc[k] > 0):
            errors.append(f"strategy.{name}.{k} 必須是 >0 的數字，但收到 {sc[k]!r}")
    for k in ("CD", "CR"):
        if k in sc and not (_is_number(sc[k]) and sc[k] >= 0):
            errors.append(f"strategy.{name}.{k} 必須是 >=0 的數字，但收到 {sc[k]!r}")
    for k in _SPAD_KEYS:
        if k in sc and sc[k] is not None and not (_script_safe(sc[k]) and sc[k].startswith("/")):
            # GmatConsole 會把工作目錄切到 bin/，相對路徑會找不到檔案
            errors.append(f"strategy.{name}.{k} 必須是 ASCII 絕對路徑（不含引號），但收到 {sc[k]!r}")


def validate_gmat_env(config, errors=None):
    """檢查 strategy 裡 GMAT 端的欄位。給了 errors 串列就附加進去，否則有錯直接丟 ValueError。"""
    own = errors is None
    errors = [] if own else errors
    strat = (config or {}).get("strategy", {}) if isinstance(config, dict) else {}
    if isinstance(strat, dict):
        fm = strat.get("FORCE_MODEL", DEFAULT_FORCE_MODEL)
        if fm not in FORCE_MODELS:
            errors.append(f"strategy.FORCE_MODEL 必須是 {FORCE_MODELS} 其中一個，但收到 {fm!r}")
        for name in ("GMAT_SPACECRAFT", "GMAT_SPACECRAFT_A"):
            if name in strat:
                _check_spacecraft(name, strat[name], errors)
        ep = strat.get("GMAT_EPOCH", DEFAULT_EPOCH)
        if not (_script_safe(ep) and ep.strip()):
            errors.append(f"strategy.GMAT_EPOCH 必須是非空 ASCII 字串（GMAT 的 Epoch 寫法），但收到 {ep!r}")
        epf = strat.get("GMAT_EPOCH_FORMAT", DEFAULT_EPOCH_FORMAT)
        if epf not in EPOCH_FORMATS:
            errors.append(f"strategy.GMAT_EPOCH_FORMAT 必須是 {EPOCH_FORMATS} 其中一個，但收到 {epf!r}")
        if not errors:
            env = _resolve_unchecked(strat)
            for k in _SPAD_KEYS:
                if (env["sc_A"][k] is None) != (env["sc_B"][k] is None):
                    # 兩艘船共用同一個 ForceModel，DragModel/SRPModel 只能二選一
                    errors.append(f"{k} 要嘛兩艘船都給、要嘛都不給（兩艘共用同一個 ForceModel）")
    if own and errors:
        raise ValueError("GMAT 環境設定有誤：\n" + "\n".join(f"  - {e}" for e in errors))
    return errors


def _resolve_unchecked(strat):
    sc_B = dict(DEFAULT_SPACECRAFT)
    sc_B.update(strat.get("GMAT_SPACECRAFT") or {})
    sc_A = dict(sc_B)
    sc_A.update(strat.get("GMAT_SPACECRAFT_A") or {})
    return {
        "force_model": strat.get("FORCE_MODEL", DEFAULT_FORCE_MODEL),
        "sc_A": sc_A, "sc_B": sc_B,
        "epoch": strat.get("GMAT_EPOCH", DEFAULT_EPOCH),
        "epoch_format": strat.get("GMAT_EPOCH_FORMAT", DEFAULT_EPOCH_FORMAT),
    }


def resolve_gmat_env(config, force_model=None):
    """config → script_generator 要的關鍵字參數（force_model / sc_A / sc_B / epoch / epoch_format）。
    force_model 給定時蓋過設定（全攝動重瞄準一律用 ranking_full）。"""
    validate_gmat_env(config)
    env = _resolve_unchecked(config.get("strategy", {}))
    if force_model is not None:
        if force_model not in FORCE_MODELS:
            raise ValueError(f"force_model 必須是 {FORCE_MODELS} 其中一個，但收到 {force_model!r}")
        env["force_model"] = force_model
    return env
