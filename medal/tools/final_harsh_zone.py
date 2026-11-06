"""壓力測試：安全空域偏移逼近 6 發容量（躲方幾乎每回合都得順／逆向推）時，躲方還安不安全。

用法：uv run python tools/final_harsh_zone.py --lo 4.5 --hi 5.5 --games 40 --workers 12 --name f24_harsh_zone
暫時把 game.scenarios.FINAL_ZONE_ROUNDS 改成 (lo, hi)、FINAL_P_IN_ZONE 改成 0，其餘同 evaluate.py --rules final_ranges --scenario final。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from runtime_threads import limit_blas_threads  # noqa: E402

limit_blas_threads()

import game.scenarios as scenarios  # noqa: E402
from evaluation.tournament import make_games, markdown_report, run_tournament  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lo", type=float, default=4.5)
    ap.add_argument("--hi", type=float, default=5.5)
    ap.add_argument("--games", type=int, default=40)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--pursuers", default="capture_pursuer;lambert_pursuer")
    ap.add_argument("--evaders", default="safe_evader;heuristic_evader")
    ap.add_argument("--name", default="f24_harsh_zone")
    args = ap.parse_args()
    scenarios.FINAL_ZONE_ROUNDS = (args.lo, args.hi)
    scenarios.FINAL_P_IN_ZONE = 0.0
    games = make_games(args.games, "final_ranges", "final", args.seed)
    results = run_tournament(args.pursuers.split(";"), args.evaders.split(";"), games,
                             workers=args.workers, seed=args.seed)
    meta = {"rules": "final_ranges", "scenario": f"final（安全空域偏移 {args.lo}–{args.hi} 發、初始不在區間）",
            "games per pairing": args.games, "seed": args.seed}
    md = markdown_report(results, title=f"Tournament {args.name}", meta=meta)
    os.makedirs("reports", exist_ok=True)
    with open(f"reports/{args.name}.md", "w") as f:
        f.write(md)
    with open(f"reports/{args.name}.jsonl", "w") as f:
        for r in results:
            f.write(json.dumps(r, default=float) + "\n")
    print(md)


if __name__ == "__main__":
    main()
