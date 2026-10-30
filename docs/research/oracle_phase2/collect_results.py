"""一次性彙整：階段 2 四臂比較的 sweep 結果 → runs.csv、各 run 的小檔、summary 用的表。

用法（在 repo 根目錄）：
    uv run python docs/research/oracle_phase2/collect_results.py --sweeps outputs/sweeps --out docs/research/oracle_phase2

讀 outputs/sweeps/phase2_arm<X>/results.jsonl（sweep_params.py 的逐 run 記錄）＋各 run 目錄的
mission.json、winner_presplit_seed<S>.json、oracle_candidates_seed<S>.json、run.log（Oracle comparison 表），
輸出：
  * runs.csv：每個 run 一列。
  * runs/<題>_<臂>_s<種子>/：mission.json、winner_presplit_seed*.json、oracle_candidates_seed*.json。
  * tables.md：每題每臂的彙整表（summary.md 直接貼）。
合法 = sweep 狀態 ok、未失格、Earth-safe、miss ≤ 5 km（penalty_count 另列）。
oracle 勝出 = run.log 有兩次「拆棒前贏家已存檔」：_solve_with_oracle 只在選了 oracle 候選時才再存一次
（2026-10-30 更正：原本用「最終分數對得上 oracle 列、對不上 DE 列」判定，分數差 ~1e-6 的平手會誤判成 DE 勝；
§6 排名鍵在分數平手時比 Δr／ΔV，oracle 候選常靠這個勝出）。oracle_margin = 最終分數 − 表中 DE 列拆後分數。
臂 C 的 winner_presplit 在 oracle 勝出時是 oracle 候選的拆前路線（main._solve_with_oracle 會覆寫）；
DE 自己的拆前前導棒另外從表的 DE 列取（de_leading_mps，只有臂 C 有意義）。
"""
import argparse
import csv
import glob
import json
import os
import re
import shutil
import statistics

ARMS = "ABCD"
SCENARIOS = ["e1_r4", "e1_r5", "e1_r8", "hyper_far", "hyperbolic_smoke", "contest"]
MISS_TOL_KM = 5.0


def _json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def oracle_table(run_dir):
    try:
        lines = open(os.path.join(run_dir, "run.log"), encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        return None
    for i, l in enumerate(lines):
        if "Oracle comparison:" in l:
            rows = []
            for r in lines[i + 1:]:
                m = re.match(r"^(DE|oracle) / (\S+) / ([-\d.]+) / ([-\d.]+) / (\d+) / ([-\d.]+) / (True|False)$", r.strip())
                if not m:
                    break
                rows.append(dict(source=m[1], rank=m[2], leading=float(m[3]), score=float(m[4]),
                                 burns=int(m[5]), total=float(m[6]), dq=m[7] == "True"))
            return rows
    return None


def collect(sweeps, out):
    rows = []
    for arm in ARMS:
        res = os.path.join(sweeps, f"phase2_arm{arm}", "results.jsonl")
        if not os.path.exists(res):
            continue
        for line in open(res, encoding="utf-8"):
            r = json.loads(line)
            run_dir = os.path.join(os.path.dirname(os.path.dirname(sweeps)), r["run_dir"]) \
                if not os.path.isabs(r["run_dir"]) else r["run_dir"]
            if not os.path.isdir(run_dir):
                run_dir = os.path.join(sweeps, f"phase2_arm{arm}", "runs", os.path.basename(r["run_dir"]))
            seed = r["seed"]
            f = r.get("final") or {}
            mission = _json(os.path.join(run_dir, "mission.json")) or {}
            mi = mission.get("mission_info", {})
            pre = _json(os.path.join(run_dir, f"winner_presplit_seed{seed}.json")) or {}
            pre_burns = [sum(c * c for c in b) ** 0.5 * 1000.0 for b in pre.get("burns", [])]
            orc = _json(os.path.join(run_dir, f"oracle_candidates_seed{seed}.json"))
            table = oracle_table(run_dir)
            de_row = next((t for t in (table or []) if t["source"] == "DE"), None)
            oracle_won = None
            if table is not None and mi and arm == "C":
                log_text = open(os.path.join(run_dir, "run.log"), encoding="utf-8", errors="replace").read()
                oracle_won = log_text.count("拆棒前贏家已存檔") >= 2
            orc_scores = [t["score"] for t in (table or []) if t["source"] == "oracle" and not t["dq"]]
            legal = (r["status"] == "ok" and not f.get("disqualified") and bool(f.get("earth_safe", True))
                     and f.get("miss_km") is not None and f["miss_km"] <= MISS_TOL_KM)
            row = {
                "scenario": r["scenario"], "arm": arm, "seed": seed,
                "commit": (r.get("git") or {}).get("commit", "")[:7],
                "status": r["status"], "legal": legal,
                "score": f.get("score"), "disqualified": f.get("disqualified"),
                "earth_safe": f.get("earth_safe"), "miss_km": f.get("miss_km"),
                "penalty_count": f.get("penalty_count"), "num_burns": f.get("num_burns"),
                "total_dv_mps": f.get("total_dv_mps"),
                "wall_sec": r.get("wall_sec"), "search_sec": r.get("search_sec"), "split_sec": r.get("split_sec"),
                "cold_compile": bool(r.get("numba_cache_written")),
                "presplit_num_burns": (r.get("presplit") or {}).get("num_burns"),
                "presplit_leading_mps": ";".join(f"{b:.1f}" for b in pre_burns[:-1]),
                "presplit_terminal_mps": round(pre_burns[-1], 1) if pre_burns else None,
                # 只有臂 C（ORACLE_TWOBURN）表裡的 DE 前導棒是拆前值；D 的是拆後第一棒（main 只在 C 設 _oracle_presplit_leading_mps）
                "de_leading_mps": None if de_row is None or arm != "C" else de_row["leading"],
                "de_post_score": None if de_row is None else de_row["score"],
                "oracle_wall_sec": None if orc is None else round(orc.get("wall_sec", 0.0), 1),
                "oracle_n_candidates": None if orc is None else len(orc.get("candidates", [])),
                "oracle_best_post_score": max(orc_scores) if orc_scores else None,
                "oracle_won": oracle_won,
                "oracle_margin": (None if de_row is None or not mi or arm != "C"
                                  else round(float(mi["score"]) - de_row["score"], 6)),
            }
            rows.append(row)
            dest = os.path.join(out, "runs", f"{r['scenario']}_{arm}_s{seed}")
            os.makedirs(dest, exist_ok=True)
            for pat in ("mission.json", "winner_presplit_seed*.json", "oracle_candidates_seed*.json"):
                for src in glob.glob(os.path.join(run_dir, pat)):
                    shutil.copy2(src, dest)
    rows.sort(key=lambda x: (SCENARIOS.index(x["scenario"]), x["arm"], x["seed"]))
    with open(os.path.join(out, "runs.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return rows


def tables(rows):
    out = ["| 題目 | 臂 | 種子 0–4 合法分數 | 最好 | 中位 | 合法數 | 牆鐘中位／最大 (s) | oracle 勝出 | oracle 牆鐘中位 (s) | commit |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    best = []
    for sc in SCENARIOS:
        for arm in ARMS:
            rs = sorted((r for r in rows if r["scenario"] == sc and r["arm"] == arm), key=lambda r: r["seed"])
            if not rs:
                continue
            cells = [f"{r['score']:.4f}" if r["legal"] else ("失格" if r["disqualified"] else r["status"]) for r in rs]
            legal = [r for r in rs if r["legal"]]
            sc_l = [r["score"] for r in legal]
            walls = [r["wall_sec"] for r in rs if r["wall_sec"] is not None]
            ow = [r["oracle_wall_sec"] for r in rs if r["oracle_wall_sec"] is not None]
            wins = (f"{sum(bool(r['oracle_won']) for r in rs)}/{len(rs)}" if arm == "C" else "—")
            commits = "/".join(sorted({r["commit"] for r in rs}))
            out.append(f"| {sc} | {arm} | {' '.join(cells)} | "
                       f"{(max(sc_l) if sc_l else float('nan')):.4f} | "
                       f"{(statistics.median(sc_l) if sc_l else float('nan')):.4f} | {len(legal)}/{len(rs)} | "
                       f"{statistics.median(walls):.0f}／{max(walls):.0f} | {wins} | "
                       f"{(f'{statistics.median(ow):.0f}' if ow else '—')} | {commits} |")
            if legal:
                b = max(legal, key=lambda r: r["score"])
                best.append(f"| {sc} | {arm} | s{b['seed']} | {b['score']:.4f} | {b['num_burns']} | "
                            f"{b['total_dv_mps']:.1f} | `runs/{sc}_{arm}_s{b['seed']}/mission.json` |")
    out += ["", "每題每臂最好的 run（Mac 拿它的 mission.json 做全攝動重瞄準＋GMAT）：", "",
            "| 題目 | 臂 | 種子 | 分數 | 棒數 | 總 Δv (m/s) | 檔案 |", "|---|---|---|---|---|---|---|"] + best
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweeps", default="outputs/sweeps")
    ap.add_argument("--out", default="docs/research/oracle_phase2")
    a = ap.parse_args()
    rows = collect(os.path.abspath(a.sweeps), a.out)
    md = tables(rows)
    open(os.path.join(a.out, "tables.md"), "w", encoding="utf-8").write(md + "\n")
    print(md)


if __name__ == "__main__":
    main()
