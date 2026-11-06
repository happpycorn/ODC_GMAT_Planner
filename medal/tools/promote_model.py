"""從訓練 run 挑出最好的快照，評測後複製到 models/（當天 copilot / evaluate 用的固定位置）。

挑法：讀 runs/<run>/metrics.jsonl，每個角色取「對評測對手平均勝率」最高的快照；
可再用 --games 跑一次較大的確認評測（同一批規則/幾何）才複製。

例：
    uv run python tools/promote_model.py --run sp2 --games 60
    → models/pursuer.zip(.json)、models/evader.zip(.json)、models/PROMOTED.md
"""
import argparse
import datetime
import json
import os
import shutil
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def best_snapshots(run_dir):
    best = {}
    with open(os.path.join(run_dir, "metrics.jsonl")) as f:
        for line in f:
            rec = json.loads(line)
            score = float(np.mean(list(rec["win_rate_vs"].values())))
            if rec["role"] not in best or score > best[rec["role"]][0]:
                best[rec["role"]] = (score, rec)
    return best


def main():
    from evaluation.tournament import make_games, markdown_report, run_tournament

    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--games", type=int, default=0, help="> 0 時跑確認評測")
    ap.add_argument("--rules", default="ranges")
    ap.add_argument("--scenario", default="mixed")
    ap.add_argument("--out", default="models")
    args = ap.parse_args()

    run_dir = os.path.join("runs", args.run)
    best = best_snapshots(run_dir)
    os.makedirs(args.out, exist_ok=True)
    lines = [f"# 已部署模型（{datetime.datetime.now():%Y-%m-%d %H:%M}）", ""]
    for role, (score, rec) in best.items():
        src = rec["model"]
        lines.append(f"## {role}: `{src}`（{rec['stage']}，訓練平均勝率 {100 * score:.0f}%）")
        lines.append("")
        lines.append("訓練中評測：" + ", ".join(f"{k}={100 * v:.0f}%" for k, v in rec["win_rate_vs"].items()))
        lines.append("")
        if args.games > 0:
            games = make_games(args.games, args.rules, args.scenario, seed=424242)
            me = "sb3:" + src
            if role == "pursuer":
                res = run_tournament([me, "lambert_pursuer"], ["coast", "dv_evader_fast", "dv_evader"], games)
            else:
                res = run_tournament(["lambert_pursuer", {"name": "lambert_pursuer", "time_weight_mps": 60.0}],
                                     [me, "dv_evader"], games)
            lines.append(markdown_report(res, title=f"確認評測 {role}").replace("# ", "### ", 1))
        dst = os.path.join(args.out, f"{role}.zip")
        shutil.copy(src, dst)
        shutil.copy(os.path.splitext(src)[0] + ".json", os.path.splitext(dst)[0] + ".json")
        print(f"{role}: {src} → {dst}")
    with open(os.path.join(args.out, "PROMOTED.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
