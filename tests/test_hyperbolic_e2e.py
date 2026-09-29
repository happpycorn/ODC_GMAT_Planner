"""雙曲線拆棒 e2e 回歸（A5）：小預算 DE → 自動拆棒合法化。

驗證有解、零違規、Earth-safe 與命中容許；不賭確切分數。
結構煙霧與 validator 檢查見 test_hyperbolic_smoke.py；設定共用 hyperbolic_fixture.py。
直接執行：uv run python tests/test_hyperbolic_e2e.py
"""
SLOW = True  # 小預算 DE + 拆棒約 280 秒，僅 full 回歸執行。

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.optimizer import run_study_over_revs
from main import legalize_violating_winner
from hyperbolic_fixture import _hyper_config

_FAILED = []


def check(desc, ok):
    print(f"  {'✅' if ok else '❌'} {desc}")
    if not ok:
        _FAILED.append(desc)


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


def main():
    test_split_pipeline_e2e()
    print("\n── 收工 ──")
    if _FAILED:
        print(f"❌ {len(_FAILED)} 項未通過：{_FAILED}")
        sys.exit(1)
    print("✅ 雙曲線 e2e 回歸全過")


if __name__ == "__main__":
    main()
