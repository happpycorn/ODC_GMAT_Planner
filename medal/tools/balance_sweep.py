"""規則平衡掃描：在規則參數網格上跑「最強解析追者 vs 最強解析躲者」，畫出追者勝率地圖。

用途：官方規則公告前，先知道哪些規則區域對哪一方有利；公告後查表就知道抽到哪個角色時
該「求勝」還是「求距離/求省油」。所有格子用**同一批**初始幾何（成對比較）。

例：
    uv run python tools/balance_sweep.py \
        --axis max_dv_evader_mps=150,375,750,1500 --axis fuel_evader_mps=750,1500,3000 \
        --games 24 --scenario mixed --name balance_dv_fuel
    # 以正式規則為基底再掃：--base configs/rules_final.json
"""
import argparse
import itertools
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation.tournament import run_tournament, wilson  # noqa: E402
from game.rules import Rules  # noqa: E402
from game.scenarios import sample_scenario  # noqa: E402


def parse_axis(s):
    name, vals = s.split("=", 1)
    out = []
    for v in vals.split(","):
        v = v.strip()
        try:
            out.append(float(v))
        except ValueError:
            out.append(v)
    return name.strip(), out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--axis", action="append", required=True, help="欄位=值1,值2,...（Rules 欄位名）")
    ap.add_argument("--base", default=None, help="基底規則 JSON（預設 Rules()）")
    ap.add_argument("--pursuer", default="lambert_pursuer")
    ap.add_argument("--evader", default="dv_evader")
    ap.add_argument("--games", type=int, default=24)
    ap.add_argument("--scenario", default="mixed")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--name", default="balance")
    args = ap.parse_args()

    base = Rules.from_dict(json.load(open(args.base))) if args.base else Rules()
    axes = [parse_axis(a) for a in args.axis]
    scen = []
    for i in range(args.games):
        sc = sample_scenario(np.random.default_rng([args.seed, i]), args.scenario)
        scen.append((sc.orbit_pursuer, sc.orbit_evader, sc.family))

    cells = {}
    for combo in itertools.product(*[vals for _, vals in axes]):
        R = base.with_(**{name: val for (name, _), val in zip(axes, combo)})
        games = [(R.to_dict(), op, oe, fam) for op, oe, fam in scen]
        res = run_tournament([args.pursuer], [args.evader], games, workers=args.workers, seed=args.seed,
                             progress=False)
        k = sum(r["winner"] == "pursuer" for r in res)
        cells[combo] = (k, len(res), float(np.median([r["min_dist_km"] for r in res])))
        print(f"  {dict(zip([a for a, _ in axes], combo))}: 追者勝 {k}/{len(res)}", flush=True)

    lines = [f"# 規則平衡掃描 {args.name}", "",
             f"- 追者 `{args.pursuer}` vs 躲者 `{args.evader}`，每格 {args.games} 局（同一批 `{args.scenario}` 幾何）",
             f"- 基底規則：`{json.dumps(base.to_dict(), ensure_ascii=False)}`", "",
             "格內：追者勝率 [95% 區間]（最近距離中位數 km）", ""]
    if len(axes) == 2:
        (n0, v0), (n1, v1) = axes
        lines.append(f"| {n0} \\ {n1} | " + " | ".join(str(x) for x in v1) + " |")
        lines.append("|---|" + "---|" * len(v1))
        for a in v0:
            row = []
            for b in v1:
                k, n, md = cells[(a, b)]
                lo, hi = wilson(k, n)
                row.append(f"{100 * k / n:.0f}% [{100 * lo:.0f}–{100 * hi:.0f}] ({md:.0f})")
            lines.append(f"| {a} | " + " | ".join(row) + " |")
    else:
        names = [n for n, _ in axes]
        lines.append("| " + " | ".join(names) + " | 追者勝率 | 最近距離中位數 km |")
        lines.append("|" + "---|" * (len(names) + 2))
        for combo, (k, n, md) in cells.items():
            lo, hi = wilson(k, n)
            lines.append("| " + " | ".join(str(c) for c in combo) +
                         f" | {100 * k / n:.0f}% [{100 * lo:.0f}–{100 * hi:.0f}] | {md:.1f} |")
    md = "\n".join(lines) + "\n"
    os.makedirs("reports", exist_ok=True)
    with open(f"reports/{args.name}.md", "w") as f:
        f.write(md)
    print(md)


if __name__ == "__main__":
    main()
