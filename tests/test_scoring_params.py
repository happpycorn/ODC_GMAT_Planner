"""計分參數換算與驗算工具（src/scoring_params.py、scripts/check_scoring_params.py）。

直接執行：uv run python tests/test_scoring_params.py
由 run_regression.py 自動發現（純 Python，秒級）。

核心案例是初賽範例題目：官方 kv = 1.1862 (km/s)^-1、Cv = 2.955723 km/s，參考解
2,241.427 m/s @ 3,211.737 s 換對單位剛好 90.00 分，照抄只有 72.50 分。
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from src.scoring_params import (PRELIM_OFFICIAL, PRELIM_REF, ToolParams, UnitError, convert,
                                looks_calibrated, sanity_warnings, score_terms, to_mps, to_sec,
                                unit_hypotheses)

FAILS = []


def check(name, cond):
    print(("  ✅ " if cond else "  ❌ ") + name)
    if not cond:
        FAILS.append(name)


REF = (PRELIM_REF["dmin_km"], PRELIM_REF["t_sec"], PRELIM_REF["dv_mps"])


def test_conversion():
    print("\n── 1. 單位換算 ──")
    p = convert(**PRELIM_OFFICIAL)
    check("初賽 k_v 1.1862 1/(km/s) → 0.0011862 1/(m/s)（沒有浮點尾巴）", p.k_v == 0.0011862)
    check("初賽 C_v 2.955723 km/s → 2955.723 m/s", p.C_v == 2955.723)
    check("k_t、C_t 照抄", p.k_t == 0.003982 and p.C_t == 3763.526)
    check("跟 configs/shared/official_sample.json 的 rules 一致", p.as_rules() == {
        k: json.load(open(os.path.join(ROOT, "configs", "shared", "official_sample.json"),
                          encoding="utf-8"))["rules"][k] for k in ("k_t", "C_t", "k_v", "C_v")})
    q = convert(0.06, "1/min", 1.5, "h", 1.0, "s/km", 2.0, "kmps")
    check("1/min、h、s/km、kmps 別名", (q.k_t, q.C_t, q.k_v, q.C_v) == (0.001, 5400.0, 0.001, 2000.0))
    check("(km/s)^-1、(m/s)^-1 寫法", convert(1, "s^-1", 1, "sec", 1, "(km/s)^-1", 1, "m/s").k_v == 0.001
          and convert(1, "1/s", 1, "s", 1, "(m/s)⁻¹", 1, "m/s").k_v == 1.0)
    check("無單位乘積在一致換算下不變", abs(p.k_v * p.C_v - 1.1862 * 2.955723) < 1e-9)
    try:
        convert(1, "1/s", 1, "s", 1, "furlong", 1, "m/s")
        check("看不懂的單位丟 UnitError", False)
    except UnitError:
        check("看不懂的單位丟 UnitError", True)
    check("to_mps / to_sec", to_mps(2.241427, "km/s") == 2241.427 and to_sec(2, "min") == 120.0)


def test_reference_check():
    print("\n── 2. 參考解驗算（初賽 90.00）──")
    from src.scorer import calculate_score
    p = convert(**PRELIM_OFFICIAL)
    t = score_terms(p, *REF)
    check(f"換對：總分 {t.total:.4f} = 90.00（±0.005）", abs(t.total - 90.0) < 0.005)
    check(f"分項 50 / {t.time:.3f} / {t.fuel:.3f} ≈ 50 / 22.5 / 17.5",
          abs(t.dist - 50) < 1e-9 and abs(t.time - 22.5) < 0.005 and abs(t.fuel - 17.5) < 0.005)
    check("跟 src.scorer.calculate_score 相同", abs(t.total - calculate_score(
        REF[0], REF[1], REF[2], 0, p.k_t, p.C_t, p.k_v, p.C_v)) < 1e-9)
    check("換對：looks_calibrated", looks_calibrated(t))

    o = PRELIM_OFFICIAL
    wrong = ToolParams(o["k_t"], o["C_t"], o["k_v"], o["C_v"])
    tw = score_terms(wrong, *REF)
    check(f"照抄：總分 {tw.total:.3f} = 72.50，燃料項 0", abs(tw.total - 72.5) < 0.005 and tw.fuel < 1e-6)
    check("照抄：不算 calibrated", not looks_calibrated(tw))

    hyps = unit_hypotheses(p.k_t, p.C_t, o["k_v"], o["C_v"], *REF)
    good = [h for h in hyps if h.calibrated]
    check("四種解讀裡只有 k_v 1/(km/s)、C_v km/s 一種落在整數",
          len(good) == 1 and "1/(km/s)" in good[0].label and "C_v 當 km/s" in good[0].label)
    sat = [h for h in hyps if "C_v 當 km/s" in h.label and "1/(m/s)" in h.label][0]
    check(f"飽和的解讀（燃料 25、總分 {sat.terms.total:.2f}）就算湊到 .5 也不算", not sat.calibrated)
    # 飽和的整數（50 + 25 + 25 = 100）也不能算 calibrated
    sat_int = score_terms(ToolParams(1.0, 1e9, 1.0, 1e9), 5.0, 0.0, 0.0)
    check("50+25+25=100 是整數但飽和，不算 calibrated", abs(sat_int.total - 100) < 1e-9
          and not looks_calibrated(sat_int))


def test_sanity_warnings():
    print("\n── 3. 數量級檢查（沒有參考解時）──")
    o = PRELIM_OFFICIAL
    p = convert(**o)
    check("換對：沒有警告", sanity_warnings(p, t_max_sec=23204.0) == [])
    w = sanity_warnings(ToolParams(o["k_t"], o["C_t"], o["k_v"], o["C_v"]))
    check("照抄：C_v 太小、k_v 太大都有警告", any("C_v" in x for x in w) and any("k_v =" in x for x in w))
    half = sanity_warnings(ToolParams(o["k_t"], o["C_t"], o["k_v"] / 1000, o["C_v"]))
    check("只換 k_v 沒換 C_v：乘積警告", any("k_v·C_v" in x for x in half))
    half = sanity_warnings(ToolParams(o["k_t"], o["C_t"], o["k_v"], o["C_v"] * 1000))
    check("只換 C_v 沒換 k_v：乘積警告", any("k_v·C_v" in x for x in half))
    check("C_t 給分鐘當秒：k_t·C_t 警告",
          any("k_t·C_t" in x for x in sanity_warnings(ToolParams(o["k_t"], 62.7, p.k_v, p.C_v))))
    check("C_t > T_max：警告", any("T_max" in x for x in sanity_warnings(p, t_max_sec=3000.0)))
    # 共用的排位賽佔位情境本來就是 m/s 制，不該有警告
    for name in ("ranking_round.json", "hyperbolic_smoke.json", "hyper_far.json"):
        r = json.load(open(os.path.join(ROOT, "configs", "shared", name), encoding="utf-8"))["rules"]
        w = sanity_warnings(ToolParams(r["k_t"], r["C_t"], r["k_v"], r["C_v"]), r.get("T_MAX_SEC"))
        check(f"{name}：沒有警告", w == [])


def test_cli():
    print("\n── 4. CLI ──")
    import check_scoring_params as cli

    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = cli.main(["--demo-prelim"])
    text = out.getvalue()
    check("--demo-prelim 回 0，印出 72.500 與 90.000", rc == 0 and "72.500" in text and "90.000" in text)

    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        rc = cli.main(["--kt", "0.003982", "--Ct", "3763.526", "--kv", "1.1862", "--Cv", "2.955723"])
    check("沒給 --kv-unit / --Cv-unit：回 2 並說明", rc == 2 and "km/s" in err.getvalue())

    tmp = tempfile.mkdtemp()
    try:
        path = os.path.join(tmp, "ranking.json")
        shutil.copy(os.path.join(ROOT, "configs", "shared", "ranking_round.json"), path)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = cli.main(["--config", path, "--kt", "0.003982", "--Ct", "3763.526",
                           "--kv", "1.1862", "--kv-unit", "1/(km/s)", "--Cv", "2.955723", "--Cv-unit", "km/s",
                           "--ref-dv", "2.241427", "--ref-dv-unit", "km/s", "--ref-t", "3211.737", "--write"])
        with open(path, encoding="utf-8") as fh:
            r = json.load(fh)["rules"]
        check("--write 回 0，寫入換算後的值",
              rc == 0 and (r["k_t"], r["C_t"], r["k_v"], r["C_v"]) == (0.003982, 3763.526, 0.0011862, 2955.723))
        check("--write 保留 MAX_DV_MPS / MAX_TOTAL_DV_MPS / T_MAX_SEC",
              r["MAX_DV_MPS"] == 250.0 and r["MAX_TOTAL_DV_MPS"] == 3000.0 and r["T_MAX_SEC"] == 40000.0)
        check("參考解驗算印出 ✅ 整數", "落在整數 90 分" in out.getvalue())
    finally:
        shutil.rmtree(tmp)


def main():
    test_conversion()
    test_reference_check()
    test_sanity_warnings()
    test_cli()
    print("\n── 收工 ──")
    if FAILS:
        print(f"❌ {len(FAILS)} 項未通過：{FAILS}")
        sys.exit(1)
    print("✅ 計分參數工具全過")


if __name__ == "__main__":
    main()
