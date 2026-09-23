"""雙曲線 A 端到端回歸（A5，2026-09-22）。

STATUS.md P3 留的洞：`run_regression.py`／`tests/` **沒有任何雙曲線案例**。雙曲線輸入端
（`is_hyperbolic_A` 分支、`Ta_sec=None`、種子產生器）與拆棒管線在雙曲線幾何下都跑過（手動、
SCENARIOS.md hyperbolic_test），但沒鎖進回歸——下次動種子/搜尋/拆棒時沒有自動防護。這支補上。

分兩層：
  A. **結構煙霧（無 DE，秒級）**：`MissionOptimizer` 吃雙曲線 config 不炸，`Ta_sec is None`、
     T_max 走 override、`energy_floor_dv()` 有限、bounds 維度對、**三種種子產生器對雙曲線輸入
     都能跑完不丟例外**。這層直接守 A1/A2/A3 改種子產生器時「在雙曲線輸入上 crash」的回歸。
  B. **拆棒 e2e（一趟小預算 DE）**：對「單/雙棒都超標」的雙曲線飛越跑完整繳交路徑
     （run_study_over_revs → legalize_violating_winner），性質式斷言：有解、**零違規**、
     Earth-safe、命中 ≤ 容許。不賭確切分數（DE + SLSQP 換版本會飄），只賭性質。

config 走程式內建（configs/ 被 gitignore，測試不能依賴檔案存在）；參數同 SCENARIOS.md 的
hyperbolic_test。被 run_regression.py 自動發現。全過 exit 0，任一不過 exit 1。
"""
import os
import sys
import math

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.optimizer import MissionOptimizer, run_study_over_revs
from src.config_validator import _validate_orbit
from main import legalize_violating_winner

_FAILED = []


def check(desc, ok):
    print(f"  {'✅' if ok else '❌'} {desc}")
    if not ok:
        _FAILED.append(desc)


def _hyper_config(maxiter, popsize, revs_ensemble=False):
    """SCENARIOS.md hyperbolic_test：單/雙棒都超標的雙曲線飛越，逼 DE 交違規解測拆棒接手。
    近地點 10,000km（安全），TA=-100° 在漸近線內（arccos(-1/1.5)≈131.8°）。"""
    return {
        "orbit_A": {"SMA": -20000.0, "ECC": 1.5, "INC": 28.0, "RAAN": 50.0, "AOP": 30.0, "TA": -100.0},
        "orbit_B": {"SMA": 6800.0, "ECC": 0.0, "INC": 28.0, "RAAN": 50.0, "AOP": 0.0, "TA": 0.0},
        "rules": {
            "MAX_DV_MPS": 1500.0, "MIN_MANEUVER_INTERVAL_SEC": 100.0, "T_MAX_SEC": 8000.0,
            "k_t": 0.003982, "C_t": 6505.65, "k_v": 0.0011862, "C_v": 9064.3,
        },
        "strategy": {"GRAVITY_DEGREE": 0, "MISS_TOLERANCE_KM": 5.0, "REVS_ENSEMBLE": revs_ensemble},
        "optimization": {
            "MAX_BURNS": [2, 3], "MAXITER": maxiter, "POPSIZE": popsize, "NUM_THREADS": 1,
            "MAX_EARLY_STOP": 40, "TOL": 0.01, "SEED": 42,
        },
    }


def test_structural_smoke():
    """A 層：雙曲線 config 建得起來、種子產生器跑得完，全程無例外。無 DE，秒級。"""
    print("\n── A. 結構煙霧（雙曲線輸入端 + 種子產生器，無 DE）──")
    opt = MissionOptimizer(_hyper_config(maxiter=10, popsize=5))

    check("雙曲線 A：Ta_sec is None（週期沒有意義，不亂算）", opt.Ta_sec is None)
    check("T_max 走 rules.T_MAX_SEC override（=8000）", abs(opt.T_max - 8000.0) < 1e-6)

    floor = opt.energy_floor_dv()
    check(f"energy_floor_dv() 有限且 ≥0（={floor*1000:.1f} m/s）",
          math.isfinite(floor) and floor >= 0.0)

    # bounds 維度對（decision_variable_dims 與陣列長度兜得起來，assert 在 _generate_bounds 內）
    for nb in (1, 2, 3):
        lb, ub = opt._generate_bounds(nb)
        check(f"_generate_bounds({nb}) 上下界等長且 lb≤ub", len(lb) == len(ub) and all(l <= u for l, u in zip(lb, ub)))

    # 種子產生器：三家族對雙曲線輸入都不能丟例外（A1/A2/A3 會動這裡）。回空清單允許，crash 不允許。
    try:
        s1 = opt._generate_seed_candidates(1, 8)
        check(f"單棒種子產生器跑完不炸（產出 {len(s1)} 個）", True)
    except Exception as e:
        check(f"單棒種子產生器跑完不炸（炸了：{e!r}）", False)
    try:
        s2 = opt._generate_seed_candidates(2, 8)
        check(f"雙棒種子產生器跑完不炸（產出 {len(s2)} 個）", True)
    except Exception as e:
        check(f"雙棒種子產生器跑完不炸（炸了：{e!r}）", False)

    # 種子若有產出，維度必須對得上 bounds（否則 DE 一開局就爆）
    if s1:
        lb1, _ = opt._generate_bounds(1)
        check("單棒種子維度 == bounds 維度", all(len(np.ravel(s)) == len(lb1) for s in s1))
    if s2:
        lb2, _ = opt._generate_bounds(2)
        check("雙棒種子維度 == bounds 維度", all(len(np.ravel(s)) == len(lb2) for s in s2))


def test_split_pipeline_e2e():
    """B 層：雙曲線飛越 → DE 交違規解 → 自動拆分合法化，性質式斷言。一趟小預算 DE。"""
    print("\n── B. 拆棒 e2e（雙曲線 × AUTO_SPLIT_LEGALIZE）──")
    cfg = _hyper_config(maxiter=50, popsize=10)
    burns, times, mi, opt = run_study_over_revs(cfg)

    check("run_study_over_revs 有回傳解（雙曲線輸入端不炸）", burns is not None and mi is not None)
    if burns is None:
        return

    # 走 main.py 的繳交路徑：違規但 Earth-safe 的贏家自動拆成合法版
    if bool(mi.get("earth_safe", True)):
        legal = legalize_violating_winner(cfg, burns, times, mi, opt)
        if legal is not None:
            burns, times, mi = legal

    cap_mps = opt.MAX_DV * 1000.0
    dv_mps = [float(np.linalg.norm(b)) * 1000.0 for b in burns]
    max_dv = max(dv_mps) if dv_mps else 0.0

    print(f"  （最終：{len(burns)} 棒，總 {mi['total_dv_mps']:.0f} m/s，"
          f"max {max_dv:.0f}/{cap_mps:.0f} m/s，score {mi['score']:.2f}）")
    check(f"零違規：每棒 ≤ 上限（max {max_dv:.0f} ≤ {cap_mps:.0f}）", max_dv <= cap_mps + 1.0)
    check("Earth-safe", bool(mi.get("earth_safe", True)))
    check(f"命中 ≤ 容許（{mi['miss_km']*1000:.0f}m ≤ {opt.MISS_TOLERANCE_KM*1000:.0f}m）",
          mi["miss_km"] <= opt.MISS_TOLERANCE_KM + 1e-6)
    check("至少一棒（解非空）", len(burns) >= 1)


def test_hyperbolic_ta_asymptote_validator():
    """A4：雙曲線 TA 漸近線檢查——|TA| 必須 < arccos(-1/e)。漸近線外要擋、內要放，
    折算 [0,360) 也要對，橢圓不受限。純檢查、決定性。"""
    print("\n── A4. 雙曲線 TA 漸近線 validator ──")
    e = 1.5
    ta_inf = math.degrees(math.acos(-1.0 / e))   # ≈131.8°

    def ta_rejected(ta, ecc=e):
        errs = []
        _validate_orbit({"SMA": -20000.0, "ECC": ecc, "INC": 30.0,
                         "RAAN": 0.0, "AOP": 0.0, "TA": ta}, "orbit_A", errs)
        return any("漸近線" in x for x in errs)

    check(f"漸近線內 TA=100° 放行（<{ta_inf:.1f}°）", not ta_rejected(100.0))
    check(f"漸近線外 TA={ta_inf+5:.1f}° 擋下", ta_rejected(ta_inf + 5.0))
    check("折算 [0,360)：TA=233.2°（=-126.8°，內）放行", not ta_rejected(360.0 - (ta_inf - 5.0)))
    check("折算 [0,360)：TA=223.2°（=-136.8°，外）擋下", ta_rejected(360.0 - (ta_inf + 5.0)))
    check("橢圓 (ECC=0.1) TA=200° 不受漸近線限制", not ta_rejected(200.0, ecc=0.1))


def main():
    test_structural_smoke()
    test_hyperbolic_ta_asymptote_validator()
    test_split_pipeline_e2e()
    print("\n── 收工 ──")
    if _FAILED:
        print(f"❌ {len(_FAILED)} 項未通過：{_FAILED}")
        sys.exit(1)
    print("✅ 雙曲線 e2e 回歸全過")


if __name__ == "__main__":
    main()
