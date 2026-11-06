"""對打評測 CLI。

例：
    uv run python evaluate.py --pursuers lambert_pursuer,minimax_pursuer \
        --evaders coast,random,dv_evader,minimax_evader --games 40 --rules ranges --scenario mixed
    # 規則已知時（例如公告後）：--rules configs/rules_final.json
    # 金／銅牌賽正式賽制（同時出手、安全空域由題目產生器填）：
    #   --rules configs/rulesets/final_official.json --scenario final
    #   --rules final_ranges --scenario final （逐局抽 ΔV_lim、R_cap、T_round）
    # 對抗安全空域題目：--rules final_ranges --scenario final_adv_cover
    # RL 策略：--pursuers sb3:runs/xxx/pursuer.zip

輸出 reports/<name>.md（報表）與 reports/<name>.jsonl（逐局原始紀錄）。
"""
import argparse
import datetime
import json
import os

from runtime_threads import limit_blas_threads

limit_blas_threads()

from evaluation.tournament import make_games, markdown_report, run_tournament


def _specs(s):
    out = []
    for tok in s.split(";") if ";" in s else s.split(","):
        tok = tok.strip()
        if tok:
            out.append(json.loads(tok) if tok.startswith("{") else tok)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pursuers", default="lambert_pursuer")
    ap.add_argument("--evaders", default="coast,random,dv_evader")
    ap.add_argument("--games", type=int, default=20)
    ap.add_argument("--rules", default="default", help="default / ranges / final_ranges（搭配 final 或 final_adv_*）/ 規則 JSON 檔路徑")
    ap.add_argument("--scenario", default="mixed", help="幾何家族（見 game/scenarios.py）；final 或 final_adv_<kind> = 金／銅牌賽題目")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--name", default=None)
    args = ap.parse_args()

    rules = args.rules
    if rules not in ("default", "ranges", "final_ranges"):
        with open(rules) as f:
            rules = json.load(f)
    games = make_games(args.games, rules, args.scenario, args.seed)
    pursuers, evaders = _specs(args.pursuers), _specs(args.evaders)
    print(f"{len(pursuers)} 追者 × {len(evaders)} 躲者 × {args.games} 局 = {len(pursuers) * len(evaders) * args.games} 場")
    results = run_tournament(pursuers, evaders, games, workers=args.workers, seed=args.seed)

    name = args.name or datetime.datetime.now().strftime("tour_%Y%m%d_%H%M%S")
    os.makedirs("reports", exist_ok=True)
    meta = {"rules": args.rules, "scenario": args.scenario, "games per pairing": args.games, "seed": args.seed}
    md = markdown_report(results, title=f"Tournament {name}", meta=meta)
    with open(f"reports/{name}.md", "w") as f:
        f.write(md)
    with open(f"reports/{name}.jsonl", "w") as f:
        for r in results:
            f.write(json.dumps(r, default=float) + "\n")
    print(md)
    print(f"→ reports/{name}.md")


if __name__ == "__main__":
    main()
