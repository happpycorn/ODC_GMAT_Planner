# 此模組承接既有命令列工具的參數解析與執行流程。
# 主要入口為 main(argv=None)，沿用原工具的選項與計算。
"""排位賽當天：官方 k_t、C_t、k_v、C_v（含單位）→ 工具單位（m/s），並驗算。

k_v、C_v 的單位**必須明講**（沒有預設值）：初賽官方給的是 km/s 制，照抄會錯。
原理與檢查項目見 odc/config/scoring_params.py。

用法（從專案根目錄）：
    # 初賽範例示範：照抄 vs 換對，參考解各得幾分
    uv run python scripts/check_scoring_params.py --demo-prelim

    # 當天：官方數字 + 單位；有參考解就加 --ref-*
    uv run python scripts/check_scoring_params.py \\
        --kt 0.003982 --kt-unit 1/s --Ct 3763.526 --Ct-unit s \\
        --kv 1.1862 --kv-unit "1/(km/s)" --Cv 2.955723 --Cv-unit km/s \\
        --ref-dv 2.241427 --ref-dv-unit km/s --ref-t 3211.737

    # 讀 config 的 T_MAX_SEC / MAX_TOTAL_DV_MPS 做範圍檢查，確認後寫回 rules
    uv run python scripts/check_scoring_params.py --config configs/ranking.json ... --write
"""
import argparse
import json
import os
import sys

from odc.paths import ROOT
sys.path.insert(0, str(ROOT))

from odc.config.scoring_params import (PRELIM_OFFICIAL, PRELIM_REF, ToolParams, UnitError,  # noqa: E402
                                convert, looks_calibrated, nearest_grid, sanity_warnings,
                                saturated, score_terms, to_mps, to_sec, unit_hypotheses)


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="計分參數單位換算與驗算")
    ap.add_argument("--demo-prelim", action="store_true", help="用初賽範例示範（不需要其他參數）")
    ap.add_argument("--kt", type=float)
    ap.add_argument("--kt-unit", default="1/s", help="1/s（預設）、1/min、1/h")
    ap.add_argument("--Ct", type=float)
    ap.add_argument("--Ct-unit", default="s", help="s（預設）、min、h")
    ap.add_argument("--kv", type=float)
    ap.add_argument("--kv-unit", help="必填：1/(m/s) 或 1/(km/s)")
    ap.add_argument("--Cv", type=float)
    ap.add_argument("--Cv-unit", help="必填：m/s 或 km/s")
    ap.add_argument("--ref-dv", type=float, help="官方參考解的總 Δv")
    ap.add_argument("--ref-dv-unit", default="m/s", help="m/s（預設）或 km/s")
    ap.add_argument("--ref-t", type=float, help="官方參考解的攔截時刻（從任務開始）")
    ap.add_argument("--ref-t-unit", default="s")
    ap.add_argument("--ref-dmin-km", type=float, default=5.0, help="參考解最小距離（預設 5 = 攔截成功）")
    ap.add_argument("--config", help="讀 rules.T_MAX_SEC / MAX_TOTAL_DV_MPS；配 --write 寫回計分參數")
    ap.add_argument("--tmax", type=float, help="T_max（秒），沒有 --config 時用")
    ap.add_argument("--write", action="store_true", help="把換算後的值寫進 --config 的 rules")
    return ap.parse_args(argv)


def _fmt_terms(t):
    return (f"距離 {t.dist:6.2f} + 時間 {t.time:6.2f} + 燃料 {t.fuel:6.2f}"
            + (f" − 違規 {t.penalty:.0f}" if t.penalty else "") + f" = {t.total:7.3f}")


def report(p: ToolParams, t_max=None, max_total=3000.0, ref=None, raw=None):
    """印換算結果與驗算。ref = (dmin_km, t_sec, dv_mps)；raw = (k_v, C_v) 原始數字。回傳是否有警告。"""
    print("\n【換算成工具單位】")
    print(f"  k_t = {p.k_t:.10g} 1/s")
    print(f"  C_t = {p.C_t:.10g} s")
    print(f"  k_v = {p.k_v:.10g} 1/(m/s)")
    print(f"  C_v = {p.C_v:.10g} m/s")
    print(f"  無單位乘積：k_t·C_t = {p.k_t * p.C_t:.4f}、k_v·C_v = {p.k_v * p.C_v:.4f}"
          "（初賽 14.99、3.506；換算不會改變它們）")
    print("\n  config 的 rules 要填：")
    print("    " + json.dumps(p.as_rules(), ensure_ascii=False))

    print("\n【分數地形（看起來合不合理）】")
    dvs = [0.0, 500.0, 1000.0, 2000.0, 3000.0]
    print("  燃料項：" + "  ".join(f"{d:.0f} m/s→{score_terms(p, 5, 0, d).fuel:5.2f}" for d in dvs))
    ts = [0.0, p.C_t] + ([t_max] if t_max else [])
    print("  時間項：" + "  ".join(f"{t:.0f} s→{score_terms(p, 5, t, 0).time:5.2f}" for t in ts))
    if t_max:
        print(f"  C_t / T_max = {p.C_t / t_max:.3f}（<0.30 主攻快解；>0.70 省油解可能有戲）")
    ts_slope = p.k_t * 25 / 4
    print(f"  拐點斜率：時間 {ts_slope:.4g} 分/s、燃料 {p.k_v * 25 / 4:.4g} 分/(m/s)"
          f"，早 1 秒最多值 {p.k_t / p.k_v:.3f} m/s（上界）")

    warns = sanity_warnings(p, t_max, max_total)
    print("\n【數量級檢查】")
    if warns:
        for w in warns:
            print(f"  ⚠️  {w}")
    else:
        print("  ✅ 沒看到異常（C_v 是 m/s 量級、乘積在合理範圍）")

    if ref is not None:
        dmin, t_ref, dv_ref = ref
        terms = score_terms(p, dmin, t_ref, dv_ref)
        print(f"\n【參考解驗算】Δr_min={dmin} km、T={t_ref} s、ΔV={dv_ref} m/s")
        print(f"  {_fmt_terms(terms)}")
        g, d = nearest_grid(terms.total, 1.0)
        if looks_calibrated(terms):
            print(f"  ✅ 落在整數 {g:.0f} 分（差 {d:+.4f}）：跟初賽一樣是照參考解校準的，單位應該換對了")
        else:
            print(f"  ⚠️  不在整數上（最近 {g:.0f}，差 {d:+.3f}）。初賽參考解剛好 90.00；不是整數不一定錯，"
                  "但先看下面哪一種單位解讀會落在整數")
        for name, val in (("時間", terms.time), ("燃料", terms.fuel)):
            g5, d5 = nearest_grid(val, 0.5)
            if saturated(val):
                mark = "⚠️ 飽和在 0 或 25，這項的參數多半換錯"
            else:
                mark = "整齊" if abs(d5) < 0.01 else "不整齊"
            print(f"    {name}項 {val:.4f}（最近的 0.5 倍數 {g5:.1f}，{mark}）")
        if raw is not None:
            print("\n  k_v、C_v 的四種單位解讀（k_t、C_t 已換算）：")
            for h in unit_hypotheses(p.k_t, p.C_t, raw[0], raw[1], dmin, t_ref, dv_ref):
                flag = "← 整數" if h.calibrated else ""
                print(f"    {h.label:28s} {_fmt_terms(h.terms)} {flag}")
    return bool(warns)


def demo_prelim():
    print("=" * 72)
    print("示範：初賽範例題目（官方 kv = 1.1862 (km/s)^-1、Cv = 2.955723 km/s）")
    print("參考解 ΔV = 2.241427 km/s、T = 3211.737 s、成功攔截")
    print("=" * 72)
    o = PRELIM_OFFICIAL
    ref = (PRELIM_REF["dmin_km"], PRELIM_REF["t_sec"], PRELIM_REF["dv_mps"])

    print("\n### 錯誤示範：k_v、C_v 照抄、當成 m/s 制")
    wrong = ToolParams(o["k_t"], o["C_t"], o["k_v"], o["C_v"])
    report(wrong, ref=ref)

    print("\n" + "-" * 72)
    print("### 正確：標明單位後換算")
    right = convert(**o)
    report(right, ref=ref, raw=(o["k_v"], o["C_v"]))
    return 0


def main(argv=None):
    args = parse_args(argv)
    if args.demo_prelim:
        return demo_prelim()

    need = [n for n in ("kt", "Ct", "kv", "Cv") if getattr(args, n) is None]
    if need:
        print(f"缺 {need}（或用 --demo-prelim 看示範）", file=sys.stderr)
        return 2
    if not args.kv_unit or not args.Cv_unit:
        print("--kv-unit 和 --Cv-unit 必填：初賽官方給的是 1/(km/s) 與 km/s，照抄會錯", file=sys.stderr)
        return 2
    if args.write and not args.config:
        print("--write 需要 --config", file=sys.stderr)
        return 2
    if (args.ref_dv is None) != (args.ref_t is None):
        print("--ref-dv 和 --ref-t 要一起給", file=sys.stderr)
        return 2

    cfg = None
    t_max, max_total = args.tmax, 3000.0
    if args.config:
        with open(args.config, encoding="utf-8") as fh:
            cfg = json.load(fh)
        rules = cfg.get("rules", {})
        t_max = rules.get("T_MAX_SEC", t_max)
        max_total = rules.get("MAX_TOTAL_DV_MPS", max_total)

    try:
        p = convert(args.kt, args.kt_unit, args.Ct, args.Ct_unit, args.kv, args.kv_unit, args.Cv, args.Cv_unit)
        ref = None
        if args.ref_dv is not None:
            ref = (args.ref_dmin_km, to_sec(args.ref_t, args.ref_t_unit), to_mps(args.ref_dv, args.ref_dv_unit))
    except UnitError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 2

    print("=" * 72)
    print("計分參數換算")
    print(f"  官方：k_t={args.kt} {args.kt_unit}、C_t={args.Ct} {args.Ct_unit}、"
          f"k_v={args.kv} {args.kv_unit}、C_v={args.Cv} {args.Cv_unit}")
    print("=" * 72)
    if t_max is None:
        print("  （沒有 T_max：加 --config 或 --tmax 才會檢查 C_t / T_max）")
    report(p, t_max=t_max, max_total=max_total, ref=ref, raw=(args.kv, args.Cv) if ref else None)

    if args.write:
        rules = cfg.setdefault("rules", {})
        old = {k: rules.get(k) for k in ("k_t", "C_t", "k_v", "C_v")}
        rules.update(p.as_rules())
        with open(args.config, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print(f"\n  已寫入 {args.config}：{old} → {p.as_rules()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
