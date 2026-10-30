# 此模組承接既有命令列工具的參數解析與執行流程。
# 主要入口為 main(argv=None)，沿用原工具的選項與計算。
"""排位賽當天：A 的軌道根數 + 任務邊界 → rules.T_MAX_SEC。

T_max 的定義（排位賽規則）：A 過近地點後，地心距離第一次增加到任務邊界的時刻，從任務開始
（epoch）算起。解析解（二體 Kepler）和數值傳播（跟求解器同一支 DOP853、同一組 J2–J4）
都算一次，印出兩者差多少，再給要填進 config 的值。原理與邊界情況見 odc/config/tmax.py。

用法（從專案根目錄）：
    # 已經把 A 填進 config：讀 orbit_A 和 strategy.GRAVITY_DEGREE
    uv run python scripts/tmax_from_boundary.py --config configs/ranking.json --boundary-km 100000

    # 邊界給的是高度而不是地心距離
    uv run python scripts/tmax_from_boundary.py --config configs/ranking.json --boundary-alt-km 93621.863

    # 直接打根數（INC/RAAN/AOP 只影響 J2–J4 的數值傳播）
    uv run python scripts/tmax_from_boundary.py --sma -50000 --ecc 1.2 --inc 30 --raan 0 --aop 0 --ta 230 \\
        --boundary-km 100000

    # 確認無誤後寫回 config 的 rules.T_MAX_SEC（會先印舊值）
    uv run python scripts/tmax_from_boundary.py --config configs/ranking.json --boundary-km 100000 --write
"""
import argparse
import json
import math
import os
import sys
import warnings

from odc.paths import ROOT
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")  # poliastro 的 "Wrapping true anomaly" 提示

from odc.config.tmax import (RE_EARTH, TmaxError, analytic_tmax, numeric_tmax,  # noqa: E402
                      recommended_t_max_sec, wrap_ta_deg)

_FIELDS = ("SMA", "ECC", "INC", "RAAN", "AOP", "TA")


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="由任務邊界算排位賽 T_max（秒，從 epoch 起算）")
    ap.add_argument("--config", help="讀 orbit_A 與 strategy.GRAVITY_DEGREE 的 config")
    for f in _FIELDS:
        ap.add_argument(f"--{f.lower()}", type=float, help=f"A 的 {f}（蓋掉 config）")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--boundary-km", type=float, help="任務邊界的地心距離（km）")
    g.add_argument("--boundary-alt-km", type=float,
                   help=f"任務邊界的高度（km），會加上地球半徑 {RE_EARTH} km")
    ap.add_argument("--gravity-degree", type=int, choices=(0, 2, 3, 4),
                    help="數值傳播的重力階數（預設讀 config，沒有就用 4）")
    ap.add_argument("--no-numeric", action="store_true", help="只算解析解（省掉 numba 編譯幾秒）")
    ap.add_argument("--write", action="store_true", help="把建議值寫進 --config 的 rules.T_MAX_SEC")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    cfg = None
    orbit = {}
    if args.config:
        with open(args.config, encoding="utf-8") as fh:
            cfg = json.load(fh)
        orbit.update(cfg.get("orbit_A", {}))
    for f in _FIELDS:
        v = getattr(args, f.lower())
        if v is not None:
            orbit[f] = v
    missing = [f for f in ("SMA", "ECC", "TA") if f not in orbit]
    if missing:
        print(f"缺 A 的 {missing}：給 --config 或 --sma/--ecc/--ta", file=sys.stderr)
        return 2
    if args.write and not args.config:
        print("--write 需要 --config", file=sys.stderr)
        return 2

    boundary = args.boundary_km if args.boundary_km is not None else args.boundary_alt_km + RE_EARTH
    deg = args.gravity_degree
    if deg is None:
        deg = int((cfg or {}).get("strategy", {}).get("GRAVITY_DEGREE", 4))

    print("=" * 66)
    print("排位賽 T_max：A 過近地點後，地心距離第一次增加到任務邊界的時刻")
    print("=" * 66)
    print("  A: " + "  ".join(f"{f}={orbit.get(f)}" for f in _FIELDS))
    if args.boundary_alt_km is not None:
        print(f"  任務邊界：高度 {args.boundary_alt_km} km + R_E {RE_EARTH} = 地心距離 {boundary:.3f} km")
    else:
        print(f"  任務邊界：地心距離 {boundary:.3f} km（若官方給的是高度，改用 --boundary-alt-km）")

    try:
        ana = analytic_tmax(orbit["SMA"], orbit["ECC"], orbit["TA"], boundary)
    except TmaxError as e:
        print(f"\n❌ 算不出 T_max：{e}")
        if args.boundary_km is not None and "近地點距離" in str(e):
            print(f"   如果官方給的 {args.boundary_km} km 其實是高度，改用 --boundary-alt-km"
                  f"（地心距離 = {args.boundary_km + RE_EARTH:.3f} km）")
        return 1

    print(f"\n【解析解（二體 Kepler，{ana.orbit_type}）】")
    print(f"  TA 折算        {wrap_ta_deg(orbit['TA']):10.4f} °")
    print(f"  r0             {ana.r0_km:12.3f} km")
    print(f"  近地點 r_p     {ana.rp_km:12.3f} km（高度 {ana.rp_km - RE_EARTH:.3f} km）")
    if math.isfinite(ana.ra_km):
        print(f"  遠地點 r_a     {ana.ra_km:12.3f} km")
    print(f"  近地點時刻     {ana.t_periapsis_sec:12.3f} s（負 = epoch 之前）")
    print(f"  T_max          {ana.t_max_sec:12.3f} s（{ana.t_max_sec / 3600.0:.3f} h）")
    if ana.twice_time_to_periapsis_sec is not None:
        print(f"  （對照：舊共用情境的「2 × 到近地點」= {ana.twice_time_to_periapsis_sec:.3f} s，"
              "只有邊界 = A 的初始距離時才相等）")
    for n in ana.notes:
        print(f"  註：{n}")

    num = None
    if not args.no_numeric:
        from odc.physics.propagator import get_r0_v0
        for f in ("INC", "RAAN", "AOP"):
            orbit.setdefault(f, 0.0)
        r0, v0 = get_r0_v0(*[orbit[f] for f in _FIELDS])
        print(f"\n【數值交叉驗證（DOP853，同 MissionOptimizer；首次呼叫要 numba 編譯幾秒）】")
        try:
            num0 = numeric_tmax(r0, v0, boundary, 0, t_guess=ana.t_max_sec)
            print(f"  點質量         {num0.t_max_sec:12.3f} s   與解析差 {num0.t_max_sec - ana.t_max_sec:+.2e} s"
                  "（應 < 1e-3 s，否則根數或程式有問題）")
            if deg != 0:
                num = numeric_tmax(r0, v0, boundary, deg, t_guess=ana.t_max_sec)
                print(f"  GRAVITY_DEGREE={deg} {num.t_max_sec:10.3f} s   與解析差 {num.t_max_sec - ana.t_max_sec:+.3f} s"
                      "（J2–J4 的影響）")
            else:
                num = num0
            if abs(num0.t_max_sec - ana.t_max_sec) > 1e-3:
                print("  ⚠️  點質量數值解跟解析解差超過 1 ms，先別填，查根數（TA 正負號、SMA 符號）")
        except TmaxError as e:
            print(f"  ⚠️  數值傳播沒找到穿越：{e}")
            num = None

    rec = recommended_t_max_sec(ana, num)
    print("\n【要填的值】")
    print(f"  rules.T_MAX_SEC = {rec:.0f}")
    print("  （解析與數值取早的、捨去到整秒。主辦單位若直接公布 T_max 秒數，以官方數字為準。）")

    if args.write:
        rules = cfg.setdefault("rules", {})
        old = rules.get("T_MAX_SEC")
        rules["T_MAX_SEC"] = rec
        with open(args.config, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print(f"\n  已寫入 {args.config}：rules.T_MAX_SEC {old} → {rec:.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
