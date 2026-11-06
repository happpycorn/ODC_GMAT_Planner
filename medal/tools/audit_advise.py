"""記錄 advise 的原始候選、內部模型分數與終局；與計時分開執行。

  .venv/bin/python tools/audit_advise.py --label before --output reports/mac_advise_20261101 \
      --states docs/notes/mac_timing_states/*.json
  .venv/bin/python tools/audit_advise.py --compare reports/mac_advise_20261101/*_audit.json.gz

固定 workers=1，將每次 Lambert act、RolloutPlanner.evaluate、outcome_score 的完整精度資料依
實際呼叫順序存檔。只包裝 Python 呼叫，不改 physics 裡的 Numba 函式或演算法。
"""
import argparse
from collections import Counter
import gzip
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.bench_advise import digest, exact_result, first_difference


def record_state(game):
    import copilot
    return {**copilot.state_from_game(game, game.mover), "turn": game.turn,
            "window": [game._win_len, game._win_elapsed, game._window_used()],
            "min_dist": game.min_dist, "outcome": game.outcome}


def audit_state(path):
    import copilot
    import agents.analytic as analytic
    import agents.rollout as rollout

    trace = []
    counts = Counter()
    originals = {name: getattr(analytic, name) for name in ("intercept_scan", "closest_approach", "propagate")}
    act, evaluate, score = analytic.LambertPursuer.act, rollout.RolloutPlanner.evaluate, rollout.outcome_score

    def counted(name):
        def call(*args, **kwargs):
            counts[name] += 1
            return originals[name](*args, **kwargs)
        return call

    def traced_act(self, game, side):
        state = record_state(game)
        result = act(self, game, side)
        trace.append({"kind": "lambert_act", "state": state, "agent": dict(vars(self)),
                      "dv": result.tolist()})
        return result

    def traced_evaluate(self, game, side):
        state = record_state(game)
        result = evaluate(self, game, side)
        trace.append({"kind": "evaluate", "state": state, "side": side,
                      "candidates": self.cand_specs, "opponents": self.opp_specs,
                      "continuation": self.cont_spec,
                      "values": [[dv.tolist(), values] for dv, values in result]})
        return result

    def traced_score(game, side):
        value = score(game, side)
        trace.append({"kind": "outcome_score", "side": side, "summary": game.summary(), "score": value})
        return value

    try:
        for name in originals:
            setattr(analytic, name, counted(name))
        analytic.LambertPursuer.act = traced_act
        rollout.RolloutPlanner.evaluate = traced_evaluate
        rollout.outcome_score = traced_score
        st = json.loads(path.read_text())
        game = copilot.game_from_state(st)
        # 單獨驗證預設四個時間權重；與整場 advise 的計數分開。
        planner = rollout.RolloutPlanner("pursuer", workers=1)
        candidates = planner._candidates(game)
        probe = {"calls": dict(counts), "candidate_dv": [dv.tolist() for dv in candidates], "trace": trace[:]}
        counts.clear()
        trace.clear()
        result = copilot.advise(st, prune=True, workers=1)
        return {"state": path.name, "scan_reuse": os.environ.get("ODC_SCAN_REUSE", "default"),
                "four_weight_probe": probe, "calls": dict(counts),
                "trace_counts": dict(Counter(row["kind"] for row in trace)),
                "trace_sha256": digest(exact_result(trace)), "trace": trace, "result": result}
    finally:
        for name, original in originals.items():
            setattr(analytic, name, original)
        analytic.LambertPursuer.act = act
        rollout.RolloutPlanner.evaluate = evaluate
        rollout.outcome_score = score


def compared_payload(data):
    return exact_result({"state": data["state"], "probe": {
        k: v for k, v in data["four_weight_probe"].items() if k != "calls"},
                         "trace": data["trace"], "result": data["result"]})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--states", nargs="+", type=Path)
    ap.add_argument("--label", default="audit")
    ap.add_argument("--output", type=Path, default=Path("/tmp/mac_advise"))
    ap.add_argument("--compare", nargs="+", type=Path)
    args = ap.parse_args()
    if args.compare:
        references = {}
        for path in args.compare:
            with gzip.open(path, "rt") as f:
                for record in json.load(f):
                    payload = compared_payload(record)
                    state = record["state"]
                    if state not in references:
                        references[state] = payload
                    difference = first_difference(references[state], payload)
                    if difference:
                        raise AssertionError(f"{path} {state} 不同：{difference}")
                    print(f"{path.name} {state}：所有候選／模型分數／終局逐位元相同")
        return
    if not args.states:
        ap.error("請指定 --states 或 --compare")
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / f"{args.label}_audit.json.gz"
    if path.exists():
        ap.error(f"{path} 已存在，請另取 --label")
    results = []
    for state in args.states:
        print(f"{args.label} {state.name}：內部逐位元稽核…", flush=True)
        record = audit_state(state)
        results.append(record)
        print(json.dumps({k: v for k, v in record.items()
                          if k not in ("trace", "result", "four_weight_probe")}, ensure_ascii=False), flush=True)
        print("四權重計數：", record["four_weight_probe"]["calls"], flush=True)
    with gzip.open(path, "wt") as f:
        json.dump(results, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
