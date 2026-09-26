"""core_math.izzo_max_revs 的驗證（不需要 pytest，直接 `uv run python tests/test_izzo_max_revs.py`）。

為什麼要獨立測：`fast_fitness_evaluator` 靠這支預檢跳過多圈 Lambert 必丟例外的分支（numba 內
raise+catch 每次漏 ~1.8 KB，見 core_math.izzo_max_revs）。兩個方向的錯代價不同：
  * 跳掉 izzo 解得出來的分支 → 搜尋悄悄變差、不報錯。**必須零次**，而且要對 izzo 的兩種編譯
    特化 (lambert_izzo 的 Literal[35] 版、Python 直呼的 int64 版) 都成立——兩版在退化幾何上
    丟不丟例外會不一樣 (2026-09-26 實測：近共線與 M 圈邊界各有數例)。
  * 該跳沒跳 → 只是少修一點洩漏。只要求絕大多數 (≥99%) 有跳到。
輸入涵蓋 LEO↔高軌、短/長飛行時間、順逆向、共線/近共線，每組 M=0..6。
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from poliastro.core.iod import izzo as _izzo_raw
from src.core_math import izzo_max_revs, lambert_izzo

FAILS = []
MU = 398600.4418


def check(name, cond):
    print(("  ✅ " if cond else "  ❌ ") + name)
    if not cond:
        FAILS.append(name)


def izzo_outcome(solver, r1, r2, tof, M, prograde):
    """'ok' / 'infeasible'（可行性檢查就丟，預檢該跳的）/ 'other'（其他例外，預檢不管）。"""
    try:
        solver(r1, r2, tof, M, prograde)
        return "ok"
    except ValueError as e:
        return "infeasible" if "No feasible" in str(e) else "other"
    except Exception:
        return "other"


SOLVERS = {
    "lambert_izzo (Literal[35] 特化)": lambda r1, r2, tof, M, pg: lambert_izzo(MU, r1, r2, tof, M, pg, True),
    "poliastro izzo 直呼 (int64 特化)": lambda r1, r2, tof, M, pg: _izzo_raw(MU, r1, r2, tof, M, pg, True, 35, 1e-8),
}


def main():
    rng = np.random.default_rng(12345)
    n_cases = 3000
    wrong_skip = {k: 0 for k in SOLVERS}
    n_infeasible = n_infeasible_skipped = n_multi_ok = 0
    for _ in range(n_cases):
        ra, rb = rng.uniform(6600, 60000, size=2)
        u1 = rng.normal(size=3); u1 /= np.linalg.norm(u1)
        degenerate = rng.random() < 0.05
        if degenerate:                       # 共線 / 近共線幾何：預檢刻意回「不確定」
            u2 = u1 + rng.normal(scale=1e-9, size=3) * (rng.random() < 0.5)
            u2 /= np.linalg.norm(u2)
        else:
            u2 = rng.normal(size=3); u2 /= np.linalg.norm(u2)
        r1, r2 = ra * u1, rb * u2
        tof = float(np.exp(rng.uniform(np.log(300.0), np.log(400000.0))))
        for prograde in (True, False):
            m_max = izzo_max_revs(MU, r1, r2, tof, prograde, 35, 1e-8)
            for M in range(0, 7):
                skipped = M > m_max
                for name, solver in SOLVERS.items():
                    out = izzo_outcome(solver, r1, r2, tof, M, prograde)
                    if out == "ok" and skipped:
                        wrong_skip[name] += 1
                    if name.startswith("lambert_izzo"):
                        if out == "infeasible" and not degenerate:
                            n_infeasible += 1
                            n_infeasible_skipped += skipped
                        elif out == "ok" and M >= 1:
                            n_multi_ok += 1
    cover = n_infeasible_skipped / max(1, n_infeasible)
    print(f"  {n_cases} 組幾何 × 順逆向 × M=0..6：多圈可行 {n_multi_ok} 次、"
          f"非退化幾何必丟 {n_infeasible} 次中預檢跳過 {n_infeasible_skipped} 次 ({cover:.2%})")
    for name, n in wrong_skip.items():
        check(f"從不跳過 izzo 解得出來的分支：{name}（誤跳 {n} 次）", n == 0)
    check("非退化幾何的必丟分支 ≥99% 被預檢跳過（洩漏真的有修到）", cover >= 0.99)
    check("樣本真的涵蓋多圈可行的分支（不是全被判不可行）", n_multi_ok > 500)

    # 共線拿不準 → 不跳，交給 izzo
    r = np.array([7000.0, 0.0, 0.0])
    check("共線不跳過（交給 izzo 決定）", izzo_max_revs(MU, r, 2.0 * r, 5000.0, True, 35, 1e-8) >= 6)

    if FAILS:
        print(f"\n❌ {len(FAILS)} 項失敗")
        sys.exit(1)
    print("\n✅ 全部通過")


if __name__ == "__main__":
    main()
