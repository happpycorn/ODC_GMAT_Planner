#!/usr/bin/env python3
"""彙整 outputs/c4/ 各 run：各案例目標值、拆前/拆後估計/拆後分數、棒數、GMAT、牆鐘。

用法：uv run python scripts/c4_summary.py [--out PATH] [--md]
"""
import argparse
import json
import re
from pathlib import Path

DEFAULT_OUT_DIR = Path(__file__).resolve().parents[1] / "outputs/c4"
CASE_RE = re.compile(r"推進 (\d+) 次完成：目標值 (-?[\d.]+)")
PICK_RE = re.compile(r"最佳化完成！採用推進 (\d+) 次")


def load(p):
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def row(run_dir):
    r = {"name": run_dir.name}
    run = load(run_dir / "run.json") or {}
    r["status"] = run.get("status", "missing")
    log = (run_dir / "run.log").read_text() if (run_dir / "run.log").exists() else ""
    cases = {int(n): -float(v) for n, v in CASE_RE.findall(log)}
    r["cases"] = " ".join(f"{n}:{cases[n]:.2f}" for n in sorted(cases))
    m = PICK_RE.search(log)
    r["pick"] = m.group(1) if m else "-"

    pre = next(iter(sorted(run_dir.glob("winner_presplit_seed*.json"))), None)
    pi = (load(pre) or {}).get("mission_info", {}) if pre else {}
    r["pre"] = pi.get("score")
    r["est"] = pi.get("score_split_est", pi.get("score"))
    mi = (load(run_dir / "mission.json") or {}).get("mission_info", {})
    r["final"] = mi.get("score")
    r["burns"] = mi.get("num_burns")
    r["pen"] = mi.get("penalty_count")
    r["T"] = mi.get("T_team")
    r["dv"] = mi.get("total_dv_mps")

    ver = run.get("verification") or {}
    def g(k):
        v = ver.get(k)
        if not v:
            return "-"
        return "ok" if v.get("intercept_success") and v.get("final_burn_legal") else "FAIL"
    r["gmat"] = f"{g('dc')}/{g('fixed')}"
    r["wall"] = (run.get("timings_sec") or {}).get("solve")
    return r


def fmt(v, spec):
    return "-" if v is None else format(v, spec)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_DIR, help="C4 結果目錄（預設 outputs/c4）")
    parser.add_argument("--md", action="store_true", help="輸出 Markdown 表格")
    args = parser.parse_args()
    out_dir = args.out.resolve()
    if not out_dir.is_dir():
        parser.error(f"結果目錄不存在：{out_dir}")
    dirs = sorted(d for d in out_dir.iterdir() if d.is_dir() and ".stale" not in d.name)
    cols = ["name", "status", "cases", "pick", "pre", "est", "final", "burns", "pen", "T", "dv", "gmat", "wall"]
    specs = {"pre": ".4f", "est": ".4f", "final": ".4f", "T": ".1f", "dv": ".1f", "wall": ".0f"}
    rows = [[fmt(r[c], specs[c]) if c in specs else str(r[c] if r[c] is not None else "-") for c in cols]
            for r in map(row, dirs)]
    if args.md:
        print("| " + " | ".join(cols) + " |")
        print("|" + "---|" * len(cols))
        for x in rows:
            print("| " + " | ".join(x) + " |")
    else:
        w = [max(len(c), *(len(x[i]) for x in rows)) if rows else len(c) for i, c in enumerate(cols)]
        print("  ".join(c.ljust(w[i]) for i, c in enumerate(cols)))
        for x in rows:
            print("  ".join(v.ljust(w[i]) for i, v in enumerate(x)))


if __name__ == "__main__":
    main()
