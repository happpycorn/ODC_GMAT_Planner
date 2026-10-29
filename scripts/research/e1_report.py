"""E1（2026-10-29）彙整：管線 sweep（e1_anchors、e1_random）＋ 兩棒 oracle → 每題一列。

輸出：
  docs/e1_frequency/<題目>.json   題目設定、管線 3 顆種子的結果列、oracle 原始輸出（含前 10 名精修結果）
  docs/e1_frequency/summary.json 每題摘要（報告表格的資料來源）
  stdout：Markdown 表格兩張（每題一列；oracle 前 10 名）
「oracle 贏」= oracle 最好合法分數 − 管線最好合法分數 ≥ 0.05（管線無合法解、oracle 有，也算贏）。
"""
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oracle_common import REPO, load_scenario  # noqa: E402

WIN = 0.05
ANCHORS = ["hyper_far", "hyperbolic_smoke"]
DOC = os.path.join(REPO, "docs", "e1_frequency")


def rows(sweep):
    p = os.path.join(REPO, "outputs", "sweeps", sweep, "results.jsonl")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def legal(r):
    f = r.get("final") or {}
    return (r.get("status") == "ok" and f.get("score") is not None and not f.get("disqualified")
            and f.get("earth_safe") is not False and (f.get("miss_km") or 0) <= 5.0 + 1e-9)


def main():
    pipe = {}
    for r in rows("e1_anchors") + rows("e1_random"):
        pipe.setdefault(r["scenario"], []).append(r)
    with open(os.path.join(REPO, "sweeps", "e1_random.json"), encoding="utf-8") as f:
        names = ANCHORS + [s["name"] for s in json.load(f)["scenarios"]]
    os.makedirs(DOC, exist_ok=True)
    summ = []
    for n in names:
        cfg, opt = load_scenario(n)
        pr = sorted(pipe.get(n, []), key=lambda r: r["seed"])
        pl = [r for r in pr if legal(r)]
        pbest = max(pl, key=lambda r: r["final"]["score"]) if pl else None
        op = os.path.join(REPO, "outputs", "research", "global_oracle", f"oracle_twoburn_{n}.json")
        orc = json.load(open(op, encoding="utf-8")) if os.path.exists(op) else None
        fin = (orc or {}).get("finalized") or []
        ol = [(i, f) for i, f in enumerate(fin) if f.get("ok") and f.get("legal")]
        ob = max(ol, key=lambda z: z[1]["score"]) if ol else None
        top = (orc or {}).get("top") or []
        s = {"scenario": n, "T_max": opt.T_max, "energy_floor_mps": opt.energy_floor_dv() * 1000,
             "pipe_runs": len(pr), "pipe_legal": len(pl),
             "pipe_status": [r["status"] for r in pr],
             "pipe_scores": [r["final"]["score"] if legal(r) else None for r in pr],
             "pipe_best": pbest["final"]["score"] if pbest else None,
             "pipe_best_seed": pbest["seed"] if pbest else None,
             "pipe_best_route": None if not pbest else
             {k: pbest["final"][k] for k in ("num_burns", "total_dv_mps", "T_team")} |
             {"presplit_burns": (pbest.get("presplit") or {}).get("num_burns")},
             "pipe_wall_max": max((r["wall_sec"] for r in pr), default=None),
             "pipe_wall_median": statistics.median([r["wall_sec"] for r in pr]) if pr else None,
             "oracle_done": orc is not None, "oracle_wall": (orc or {}).get("total_sec"),
             "oracle_legal": len(ol), "oracle_best": ob[1]["score"] if ob else None,
             "oracle_best_rank": ob[0] if ob else None}
        if ob:
            f, t = ob[1], top[ob[0]]
            lead = t.get("dv1_mps")
            s["oracle_best_route"] = {"structure": f["structure"], "M": f["M"], "t1": t["t1"], "t2": t["t2"],
                                      "t3": t["t3"], "pre_total_mps": f["pre_dv_mps"], "lead_mps": lead,
                                      "term_mps": f["pre_dv_mps"] - (lead or 0.0),
                                      "num_burns": f["num_burns"], "total_dv_mps": f["total_dv_mps"],
                                      "T_team": f["T_team"]}
        s["oracle_top"] = [{"rank": i, "est_score": t["est_score"], "structure": "1-burn" if t["dv1_mps"] is None
                            else "2-burn", "lead_mps": t["dv1_mps"], "pre_total_mps": t["dv_mps"], "M": t["M"],
                            "final": (fin[i]["score"] if i < len(fin) and fin[i].get("ok") and fin[i].get("legal")
                                      else (fin[i].get("reason") or "不合法") if i < len(fin) else None)}
                           for i, t in enumerate(top)]
        d = None if s["pipe_best"] is None or s["oracle_best"] is None else s["oracle_best"] - s["pipe_best"]
        s["diff"] = d
        s["oracle_wins"] = (d is not None and d >= WIN) or (s["pipe_best"] is None and s["oracle_best"] is not None)
        summ.append(s)
        with open(os.path.join(DOC, f"{n}.json"), "w", encoding="utf-8") as fh:
            json.dump({"config": cfg, "pipeline_rows": pr, "oracle": orc}, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(DOC, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summ, fh, ensure_ascii=False, indent=1)

    def g(v, fmt="{:.4f}"):
        return "—" if v is None else fmt.format(v)
    print("| 題目 | T_max (s) | 能量下限 (m/s) | 管線最好（合法數/3） | oracle 最好（前 10 名合法數） | 差值 | oracle 贏 | "
          "oracle 贏家：前導棒／終端棒（拆前 m/s）、M、拆後棒數／總 Δv | 管線路線 | 牆鐘 管線 max/中位 · oracle (s) |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for s in summ:
        o = s.get("oracle_best_route")
        orr = "—" if not o else (f"{g(o['lead_mps'], '{:.0f}') if o['lead_mps'] else '無（單棒）'}／{o['term_mps']:.0f}、"
                                 f"M={o['M']}、{o['num_burns']} 棒／{o['total_dv_mps']:.1f}")
        p = s["pipe_best_route"]
        prr = "—" if not p else f"{p['num_burns']} 棒／{p['total_dv_mps']:.1f}（拆前 {p['presplit_burns']} 棒）"
        print(f"| `{s['scenario']}` | {s['T_max']:.0f} | {s['energy_floor_mps']:.0f} | {g(s['pipe_best'])}（{s['pipe_legal']}/{s['pipe_runs']}） | "
              f"{g(s['oracle_best'])}（{s['oracle_legal']}） | {g(s['diff'], '{:+.4f}')} | {'是' if s['oracle_wins'] else '否'} | "
              f"{orr} | {prr} | {g(s['pipe_wall_max'], '{:.0f}')}/{g(s['pipe_wall_median'], '{:.0f}')} · {g(s['oracle_wall'], '{:.0f}')} |")
    print()
    print("| 題目 | 前 10 名（拆前排名：結構、前導棒 m/s、拆前估分 → 拆後分數） |")
    print("|---|---|")
    for s in summ:
        cells = []
        for t in s["oracle_top"]:
            fv = t["final"]
            cells.append(f"#{t['rank']} {'1' if t['structure'] == '1-burn' else '2'}棒"
                         f"{'' if t['lead_mps'] is None else ' ' + format(t['lead_mps'], '.0f')} "
                         f"{t['est_score']:.2f}→{fv:.4f}" if isinstance(fv, float) else
                         f"#{t['rank']} {t['est_score']:.2f}→{fv}")
        print(f"| `{s['scenario']}` | {'；'.join(cells) or '—'} |")


if __name__ == "__main__":
    main()
