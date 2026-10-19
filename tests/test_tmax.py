"""排位賽 T_max 工具（src/tmax.py、scripts/tmax_from_boundary.py）的驗證。

直接執行：uv run python tests/test_tmax.py
由 run_regression.py 自動發現（不是 SLOW；第一次 numba 編譯約 4 秒）。

分四塊：
  1. 解析解 vs 數值傳播：點質量要一致到 1 ms；J2–J4 的差量印出來並給上界。
  2. 共用情境的 T_MAX_SEC：那些值是用「2 × 到近地點的時間」編的，等於把邊界設在 A 的初始
     距離。這裡算出精確值，記錄每個檔案差多少（hyperbolic_test 的 8000 不是用這條規則編的）。
  3. 邊界情況：A 已過近地點、邊界 < 近地點、A 已在邊界外飛走、橢圓、圓軌道、漸近線外的 TA。
  4. CLI：--write 寫回 config、MissionOptimizer 讀得到。
"""
import contextlib
import io
import json
import math
import os
import shutil
import sys
import tempfile
import warnings

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
warnings.filterwarnings("ignore")

from src.propagator import get_r0_v0
from src.tmax import (MU_EARTH, TmaxError, analytic_tmax, numeric_tmax, recommended_t_max_sec,
                      wrap_ta_deg)

FAILS = []


def check(name, cond):
    print(("  ✅ " if cond else "  ❌ ") + name)
    if not cond:
        FAILS.append(name)


def raises(fn):
    try:
        fn()
        return None
    except TmaxError as e:
        return str(e)


def load(name):
    with open(os.path.join(ROOT, "configs", "shared", name), encoding="utf-8") as fh:
        return json.load(fh)


def rv(orbit):
    return get_r0_v0(*[orbit[k] for k in ("SMA", "ECC", "INC", "RAAN", "AOP", "TA")])


def test_analytic_vs_numeric():
    print("\n── 1. 解析 vs 數值（DOP853，同 MissionOptimizer）──")
    cases = [("hyperbolic_smoke.json", 100000.0), ("hyper_far.json", 300000.0),
             ("hyperbolic_test.json", 50000.0), ("hyperbolic_smoke.json", 50000.0)]
    for name, R in cases:
        A = load(name)["orbit_A"]
        r0, v0 = rv(A)
        ana = analytic_tmax(A["SMA"], A["ECC"], A["TA"], R)
        n0 = numeric_tmax(r0, v0, R, 0, t_guess=ana.t_max_sec)
        n4 = numeric_tmax(r0, v0, R, 4, t_guess=ana.t_max_sec)
        d0, d4 = n0.t_max_sec - ana.t_max_sec, n4.t_max_sec - ana.t_max_sec
        print(f"     {name} R={R:.0f}: 解析 {ana.t_max_sec:.3f} s，點質量差 {d0:+.1e} s，J2–J4 差 {d4:+.3f} s")
        check(f"{name} R={R:.0f}：點質量數值與解析差 < 1 ms", abs(d0) < 1e-3)
        check(f"{name} R={R:.0f}：J2–J4 與解析差 < 2 s（實測 0.15–0.3 s）", abs(d4) < 2.0)
        check(f"{name} R={R:.0f}：穿越點 |r| = 邊界（1 m 內）", abs(n4.r_at_tmax_km - R) < 1e-3)
        check(f"{name} R={R:.0f}：數值近地點時刻與解析差 < 1 s",
              n0.t_periapsis_sec is not None and abs(n0.t_periapsis_sec - ana.t_periapsis_sec) < 1.0)
        check(f"{name} R={R:.0f}：建議值 = floor(min(解析, 數值))",
              recommended_t_max_sec(ana, n4) == math.floor(min(ana.t_max_sec, n4.t_max_sec)))


# 2 × 到近地點的時間，跟各檔 T_MAX_SEC 的差（秒）。改了根數或 T_MAX_SEC 就要更新這張表，
# 也要更新 docs/ranking/CONTEST_DAY.md 的說明。
SHARED_EXPECT = {
    # 檔名: (精確的 2 × t_p, 檔案裡的 T_MAX_SEC)
    "hyperbolic_smoke.json": (39947.192, 40000.0),   # 檔案進位到 4 萬，多 52.8 s
    "ranking_round.json": (39947.192, 40000.0),      # 照抄 smoke 的佔位值
    "hyper_far.json": (162512.936, 162570.0),        # 檔案多 57.1 s（當初的近地點時刻估得粗）
    "hyperbolic_test.json": (9360.615, 8000.0),      # 不是 2 × t_p，比它短 1360.6 s
}


def test_shared_configs():
    print("\n── 2. 共用雙曲線情境的 T_MAX_SEC 對照 ──")
    for name, (twice_tp, cfg_t) in SHARED_EXPECT.items():
        cfg = load(name)
        A = cfg["orbit_A"]
        r0, v0 = rv(A)
        r0n = float(np.linalg.norm(r0))
        ana = analytic_tmax(A["SMA"], A["ECC"], A["TA"], r0n)
        check(f"{name}：T_MAX_SEC 跟表上一致（{cfg_t}）", cfg["rules"]["T_MAX_SEC"] == cfg_t)
        check(f"{name}：2 × t_p = {twice_tp} s（±1 ms）",
              abs(ana.twice_time_to_periapsis_sec - twice_tp) < 1e-3)
        # 邊界 = A 的初始距離時，對稱性讓「過近地點後回到邊界」剛好等於 2 × t_p
        check(f"{name}：邊界 = r0 時 T_max = 2 × t_p（對稱性）",
              abs(ana.t_max_sec - ana.twice_time_to_periapsis_sec) < 1e-6)
        n4 = numeric_tmax(r0, v0, r0n, 4, t_guess=ana.t_max_sec)
        print(f"     {name}: 2×t_p {twice_tp:.3f}，J2–J4 數值 {n4.t_max_sec:.3f}，"
              f"檔案 {cfg_t:.0f}（差 {cfg_t - twice_tp:+.1f} s）")


def test_edge_cases():
    print("\n── 3. 邊界情況 ──")
    sma, e = -50000.0, 1.2
    rp = -sma * (e - 1.0)

    # A 一開始就在近地點之後、還在邊界內 → T_max 是往外飛出邊界的時刻
    ana = analytic_tmax(sma, e, 30.0, 20000.0)
    check("已過近地點（TA=+30°）：t_periapsis < 0", ana.t_periapsis_sec < 0.0)
    check("已過近地點：T_max > 0 且有附註", ana.t_max_sec > 0.0 and any("已經過了近地點" in n for n in ana.notes))
    check("已過近地點：沒有「2 × t_p」可對照", ana.twice_time_to_periapsis_sec is None)
    A = {"SMA": sma, "ECC": e, "INC": 30.0, "RAAN": 0.0, "AOP": 0.0, "TA": 30.0}
    r0, v0 = rv(A)
    n0 = numeric_tmax(r0, v0, 20000.0, 0, t_guess=ana.t_max_sec)
    check("已過近地點：數值解一致（點質量 < 1 ms）", abs(n0.t_max_sec - ana.t_max_sec) < 1e-3)
    check("已過近地點：數值掃描找不到近地點（在 epoch 之前）", n0.t_periapsis_sec is None)

    # TA 寫成 [0,360) 或 (-180,180] 結果相同
    a1 = analytic_tmax(sma, e, 230.0, 100000.0)
    a2 = analytic_tmax(sma, e, -130.0, 100000.0)
    check("TA=230° 與 -130° 結果相同", abs(a1.t_max_sec - a2.t_max_sec) < 1e-9)
    check("wrap_ta_deg(180) = 180、(-180) = 180", wrap_ta_deg(180.0) == 180.0 and wrap_ta_deg(-180.0) == 180.0)

    # 已過近地點而且已經在邊界外 → 雙曲線不會回來
    msg = raises(lambda: analytic_tmax(sma, e, 100.0, 20000.0))
    check("已過近地點且在邊界外：TmaxError", msg is not None and "不會再回來" in msg)

    # 邊界 < 近地點、= 近地點
    msg = raises(lambda: analytic_tmax(sma, e, -100.0, rp - 1.0))
    check("邊界 < 近地點：TmaxError", msg is not None and "近地點距離" in msg)
    check("邊界 = 近地點：TmaxError", raises(lambda: analytic_tmax(sma, e, -100.0, rp)) is not None)
    check("邊界 ≤ 0：TmaxError", raises(lambda: analytic_tmax(sma, e, -100.0, 0.0)) is not None)

    # 邊界剛好大於近地點：T_max ≈ 近地點時刻
    ana = analytic_tmax(sma, e, -100.0, rp * (1.0 + 1e-9))
    check("邊界略大於近地點：T_max ≈ 近地點時刻（< 1 s）", abs(ana.t_max_sec - ana.t_periapsis_sec) < 1.0)

    # TA 在漸近線外、SMA 符號錯、拋物線、圓
    check("TA 在漸近線外：TmaxError", raises(lambda: analytic_tmax(sma, 1.5, 140.0, 1e5)) is not None)
    check("ECC>1 但 SMA>0：TmaxError", raises(lambda: analytic_tmax(50000.0, 1.2, 0.0, 1e5)) is not None)
    check("拋物線：TmaxError", raises(lambda: analytic_tmax(-1e5, 1.0, 0.0, 1e5)) is not None)
    check("圓軌道：TmaxError", raises(lambda: analytic_tmax(7000.0, 0.0, 0.0, 8000.0)) is not None)

    # 橢圓：一般情況、邊界 > 遠地點、要等下一圈
    a_el, e_el = 13000.0, 0.3        # playground 的 A
    ra = a_el * (1 + e_el)
    msg = raises(lambda: analytic_tmax(a_el, e_el, 150.0, ra + 1.0))
    check("橢圓邊界 > 遠地點：TmaxError", msg is not None and "遠地點" in msg)
    A = load("playground.json")["orbit_A"]
    r0, v0 = rv(A)
    for R, ta in ((15000.0, A["TA"]), (15000.0, 20.0), (12000.0, 20.0)):
        ana = analytic_tmax(a_el, e_el, ta, R)
        A2 = dict(A, TA=ta)
        r0, v0 = rv(A2)
        n0 = numeric_tmax(r0, v0, R, 0, t_guess=ana.t_max_sec)
        check(f"橢圓 TA={ta} R={R:.0f}：點質量數值與解析差 < 1 ms（{ana.t_max_sec:.1f} s）",
              abs(n0.t_max_sec - ana.t_max_sec) < 1e-3)
        check(f"橢圓 TA={ta} R={R:.0f}：T_max < 1 個週期", 0.0 < ana.t_max_sec < ana.period_sec)
    ana_next = analytic_tmax(a_el, e_el, 150.0, 12000.0)  # TA=150° 已過穿越點，要等下一圈
    check("橢圓已過這一圈的穿越點：近地點在 epoch 之後、T_max 在近地點之後",
          0.0 < ana_next.t_periapsis_sec < ana_next.t_max_sec)
    check("橢圓已過穿越點：附註提醒要等下一圈", any("下一次近地點" in n for n in ana_next.notes))


def test_cli():
    print("\n── 4. CLI ──")
    import tmax_from_boundary as cli
    from src.optimizer import MissionOptimizer

    tmp = tempfile.mkdtemp()
    try:
        path = os.path.join(tmp, "ranking.json")
        shutil.copy(os.path.join(ROOT, "configs", "shared", "ranking_round.json"), path)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = cli.main(["--config", path, "--boundary-km", "100000", "--write"])
        text = out.getvalue()
        check("CLI --write 回傳 0", rc == 0)
        with open(path, encoding="utf-8") as fh:
            cfg = json.load(fh)
        check("寫回的 T_MAX_SEC = 40918（解析 40918.466、J2–J4 40918.697 取早捨去）",
              cfg["rules"]["T_MAX_SEC"] == 40918.0)
        check("其他欄位保留（k_t、orbit_A、_comment）",
              cfg["rules"]["k_t"] == 0.0001 and cfg["orbit_A"]["TA"] == 230.0 and "_comment_scenario" in cfg)
        check("輸出有印出解析與數值的差", "與解析差" in text and "GRAVITY_DEGREE=4" in text)
        check("MissionOptimizer 讀得到新的 T_max", MissionOptimizer(cfg).T_max == 40918.0)

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = cli.main(["--sma", "-50000", "--ecc", "1.2", "--ta", "230", "--boundary-km", "5000",
                           "--no-numeric"])
        check("邊界 < 近地點：CLI 回 1，提示可能是高度", rc == 1 and "--boundary-alt-km" in out.getvalue())

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = cli.main(["--sma", "-50000", "--ecc", "1.2", "--ta", "230",
                           "--boundary-alt-km", str(100000 - 6378.137), "--no-numeric"])
        check("--boundary-alt-km 加上地球半徑（= 地心 100000 km）",
              rc == 0 and "rules.T_MAX_SEC = 40918" in out.getvalue())
    finally:
        shutil.rmtree(tmp)


def main():
    test_analytic_vs_numeric()
    test_shared_configs()
    test_edge_cases()
    test_cli()
    print("\n── 收工 ──")
    if FAILS:
        print(f"❌ {len(FAILS)} 項未通過：{FAILS}")
        sys.exit(1)
    print("✅ T_max 工具全過")


if __name__ == "__main__":
    main()
