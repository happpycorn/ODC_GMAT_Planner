"""搜尋滑行容差：精確參數、設定驗證、L-SHADE 與精修/deadline 的隔離。"""
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import odc.search.optimizer as O
from odc.config.validator import ConfigValidationError, validate_config


def config():
    return json.loads((ROOT / "tests/fixtures/pipeline_smoke.json").read_text())


def check_params():
    cfg = config()
    default = O.MissionOptimizer(cfg)
    assert default.SEARCH_COAST_RTOL == 1e-12
    exact = default._scalar_params()
    assert len(exact) == 24 and exact[23] == 1e-12
    assert np.array_equal(exact, default._search_scalar_params())
    cfg["strategy"]["SEARCH_COAST_RTOL"] = 1e-9
    opt = O.MissionOptimizer(cfg)
    search = opt._search_scalar_params()
    assert search[23] == 1e-9 and opt._scalar_params()[23] == 1e-12
    assert np.array_equal(search[:23], exact[:23])
    search[0] = -1
    assert opt._scalar_params()[0] == exact[0], "搜尋參數必須是獨立副本"
    print("  ✅ 預設/精確 scalars[23]=1e-12；搜尋旋鈕與副本隔離")


def check_validation():
    for value in (0, -1e-12, 1e-3, "1e-9", None, True, float("nan"), float("inf")):
        cfg = config()
        cfg["strategy"]["SEARCH_COAST_RTOL"] = value
        try:
            validate_config(cfg)
        except ConfigValidationError as exc:
            assert "SEARCH_COAST_RTOL" in str(exc)
        else:
            raise AssertionError(f"不應接受 {value!r}")
    for value in (1e-12, 1e-9, 1e-6):
        cfg = config()
        cfg["strategy"]["SEARCH_COAST_RTOL"] = value
        validate_config(cfg)
    print("  ✅ validator 拒絕 8 種非法值，接受精確值、搜尋值及上界")


def check_case(rtol, deadline=False, polish=False):
    cfg = config()
    cfg["strategy"]["SEARCH_COAST_RTOL"] = rtol
    opt = O.MissionOptimizer(cfg)
    opt.SEED_LBFGS_POLISH = polish
    if deadline:
        opt._primer_search_deadline = time.monotonic() + 60
    sc, vec = opt._scalar_params(), opt._vector_params()
    original = sc.copy()
    x = np.asarray(opt._generate_bounds(2)).mean(axis=0)
    seen = []

    def evaluate(solution, burns, scalars, vectors):
        seen.append(scalars[23])
        return 5.0 if scalars[23] == 1e-9 else 9.0

    class Model:
        def __init__(self, **kwargs):
            self.history = SimpleNamespace(list_epoch_time=[0.0])

        def solve(self, problem, **kwargs):
            value = problem["obj_func"](x)
            return SimpleNamespace(solution=x, target=SimpleNamespace(fitness=value))

    def minimize(**kwargs):
        assert kwargs["fun"](x) == 9.0, "種子精修必須使用精確值"
        return SimpleNamespace(x=x + 0.001, fun=8.0)

    with patch.object(O, "L_SHADE", Model), patch.object(O, "fast_fitness_evaluator", evaluate), \
            patch.object(O, "minimize", minimize), \
            patch.object(opt, "_generate_seed_candidates", return_value=[x] if polish else []):
        result = opt._optimize_burn_case(2, sc, vec)
    assert np.array_equal(sc, original), "不得修改呼叫端參數"
    if polish:
        assert result[2] == 8.0, "精確重算後才與種子精修比較"
        assert seen == [1e-9, 1e-12, 1e-12]
    elif deadline:
        assert seen == [1e-12] and result[2] == 9.0
    elif rtol == 1e-12:
        assert seen == [1e-12] and result[2] == 9.0, "預設不得額外重算"
    else:
        assert seen == [1e-9, 1e-12] and result[2] == 9.0


if __name__ == "__main__":
    check_params()
    check_validation()
    check_case(1e-12)
    check_case(1e-9)
    check_case(1e-9, polish=True)
    check_case(1e-9, deadline=True)
    print("  ✅ L-SHADE 放寬、贏家精確重算、種子精修與 deadline 隔離；預設不重算")
