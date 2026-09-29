"""雙曲線結構煙霧回歸：輸入、種子產生器與 TA 漸近線驗證，無 DE。

直接執行：uv run python tests/test_hyperbolic_smoke.py
由 run_regression.py 自動發現，包含在 --quick 中。
"""
import os
import sys
import math

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.optimizer import MissionOptimizer
from src.config_validator import _validate_orbit
from hyperbolic_fixture import _hyper_config

_FAILED = []


def check(desc, ok):
    print(f"  {'✅' if ok else '❌'} {desc}")
    if not ok:
        _FAILED.append(desc)


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
    print("\n── 收工 ──")
    if _FAILED:
        print(f"❌ {len(_FAILED)} 項未通過：{_FAILED}")
        sys.exit(1)
    print("✅ 雙曲線 smoke 回歸全過")


if __name__ == "__main__":
    main()
