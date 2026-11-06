"""對打評測系統：追者集合 × 躲者集合 × 同一批（規則, 幾何）→ 捕獲率矩陣與報表。

* 所有配對用**同一批**隨機（規則, 幾何）——成對比較，差異不會被抽樣雜訊淹沒。
* agent 用可 pickle 的規格（字串 / dict / "sb3:path"）傳進子行程，在子行程內建構。
* 報表：捕獲率（Wilson 95% 區間）、結局分布、燃料、最近距離、每步決策時間。
"""
import json
import math
import os
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass

from runtime_threads import limit_blas_threads

import numpy as np

from game.core import Game, round_view, take_turn
from game.rules import RuleRanges, Rules
from game.scenarios import sample_adversarial_scenario, sample_final_rules, sample_final_scenario, sample_scenario


@dataclass
class Task:
    pursuer: object
    evader: object
    rules: dict
    orbit_pursuer: dict
    orbit_evader: dict
    family: str
    game_id: int
    seed: int
    meta: dict = None


def spec_name(spec):
    if isinstance(spec, str):
        return spec
    if isinstance(spec, dict):
        kw = {k: v for k, v in spec.items() if k != "name"}
        return f"{spec['name']}({','.join(f'{k}={v}' for k, v in kw.items())})"
    return repr(spec)


def make_games(n_games, rules="default", scenario="mixed", seed=0):
    """一般題回傳 4 元素；對抗題再附第 5 元素 meta。rules: "default" / "ranges" / "final_ranges" / dict / Rules。

    金／銅牌賽題目的安全空域由情境產生器逐局填進 rules。"""
    if rules == "final_ranges" and not scenario.startswith("final"):
        raise ValueError('rules="final_ranges" 只能搭配 scenario="final" 或 "final_adv_<kind>"')
    out = []
    for i in range(n_games):
        rng = np.random.default_rng([seed, i])
        if rules == "ranges":
            R = RuleRanges().sample(rng)
        elif rules == "final_ranges":
            R = sample_final_rules(rng)
        elif rules == "default":
            R = Rules()
        else:
            R = Rules.from_dict(rules)
        if scenario == "final":
            R, sc = sample_final_scenario(rng, R)
        elif scenario.startswith("final_adv_"):
            R, sc = sample_adversarial_scenario(rng, R, scenario.removeprefix("final_adv_"))
        else:
            sc = sample_scenario(rng, scenario)
        game = (R.to_dict(), sc.orbit_pursuer, sc.orbit_evader, sc.family)
        out.append((*game, sc.meta) if scenario.startswith("final_adv_") else game)
    return out


_AGENT_CACHE = {}


def _agent(spec):
    from agents import make_agent
    key = json.dumps(spec, sort_keys=True, default=str)
    if key not in _AGENT_CACHE:
        _AGENT_CACHE[key] = make_agent(spec)
    return _AGENT_CACHE[key]


def _json_compatible(value):
    """將 agent 紀錄中的 numpy 值轉成可輸出 JSON 的 Python 值。"""
    if isinstance(value, np.ndarray):
        return _json_compatible(value.tolist())
    if isinstance(value, np.generic):
        return _json_compatible(value.item())
    if isinstance(value, dict):
        return {k: _json_compatible(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_compatible(v) for v in value]
    return value


def play(task: Task) -> dict:
    P = _agent(task.pursuer)
    E = _agent(task.evader)
    P.reset(seed=task.seed)
    E.reset(seed=task.seed + 1)
    g = Game.from_elements(Rules.from_dict(task.rules), task.orbit_pursuer, task.orbit_evader)
    t_act = {"pursuer": 0.0, "evader": 0.0}
    n_act = {"pursuer": 0, "evader": 0}
    while not g.done:
        if g.rules.simultaneous:             # 同時出手：每回合雙方各在副本上決定一次（同 game.core.take_round）
            dv = {}
            for side, agent in (("pursuer", P), ("evader", E)):
                t0 = time.perf_counter()
                dv[side] = agent.act(round_view(g, agent, side), side)
                t_act[side] += time.perf_counter() - t0
                n_act[side] += 1
            g.play_round(dv["pursuer"], dv["evader"])
            continue
        side = g.mover
        agent = P if side == "pursuer" else E
        t0 = time.perf_counter()
        take_turn(g, agent)                  # 一回合多發時會多次問 agent（HAP-107）
        t_act[side] += time.perf_counter() - t0
        n_act[side] += 1
    s = g.summary()
    s.update({
        "pursuer": spec_name(task.pursuer), "evader": spec_name(task.evader), "family": task.family,
        "game_id": task.game_id, "rules": task.rules,
        "orbit_pursuer": dict(task.orbit_pursuer), "orbit_evader": dict(task.orbit_evader),
        "act_ms_pursuer": 1e3 * t_act["pursuer"] / max(n_act["pursuer"], 1),
        "act_ms_evader": 1e3 * t_act["evader"] / max(n_act["evader"], 1),
        "info_pursuer": _json_compatible(getattr(P, "history_info", None)),
        "info_evader": _json_compatible(getattr(E, "history_info", None)),
    })
    if task.meta is not None:
        s["scenario_meta"] = _json_compatible(task.meta)
    return s


def _initialize_worker():
    limit_blas_threads()
    from agents.scan_reuse import reset_scan_reuse
    reset_scan_reuse()


def run_tournament(pursuers, evaders, games, workers=None, seed=0, progress=True):
    tasks = []
    for gi, game in enumerate(games):
        if len(game) not in (4, 5):
            raise ValueError(f"第 {gi} 局要有 4 或 5 個欄位，實際有 {len(game)} 個")
        R, op, oe, fam = game[:4]
        meta = game[4] if len(game) == 5 else None
        for p in pursuers:
            for e in evaders:
                tasks.append(Task(p, e, R, op, oe, fam, gi, seed * 100003 + gi, meta))
    workers = workers or max(1, (os.cpu_count() or 2) - 2)
    results = []
    t0 = time.time()
    if workers == 1:
        for i, t in enumerate(tasks):
            results.append(play(t))
            if progress and (i + 1) % max(1, len(tasks) // 20) == 0:
                print(f"  {i + 1}/{len(tasks)} games  {time.time() - t0:.0f}s", flush=True)
    else:
        with ProcessPoolExecutor(max_workers=workers, initializer=_initialize_worker) as ex:
            for i, r in enumerate(ex.map(play, tasks, chunksize=1)):
                results.append(r)
                if progress and (i + 1) % max(1, len(tasks) // 20) == 0:
                    print(f"  {i + 1}/{len(tasks)} games  {time.time() - t0:.0f}s", flush=True)
    return results


def wilson(k, n, z=1.96):
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def summarize(results):
    ps = sorted({r["pursuer"] for r in results}, key=lambda x: [r["pursuer"] for r in results].index(x))
    es = sorted({r["evader"] for r in results}, key=lambda x: [r["evader"] for r in results].index(x))
    cell = {}
    for p in ps:
        for e in es:
            rs = [r for r in results if r["pursuer"] == p and r["evader"] == e]
            k = sum(r["winner"] == "pursuer" for r in rs)
            n = len(rs)
            outcomes = {}
            for r in rs:
                outcomes[r["outcome"]] = outcomes.get(r["outcome"], 0) + 1
            cell[(p, e)] = {
                "n": n, "pursuer_wins": k, "rate": k / n if n else math.nan, "ci": wilson(k, n),
                "outcomes": outcomes,
                "min_dist_med": float(np.median([r["min_dist_km"] for r in rs])) if rs else math.nan,
                "fuel_p": float(np.mean([r["used_pursuer_mps"] for r in rs])) if rs else math.nan,
                "fuel_e": float(np.mean([r["used_evader_mps"] for r in rs])) if rs else math.nan,
                "ms_p": float(np.mean([r["act_ms_pursuer"] for r in rs])) if rs else math.nan,
                "ms_e": float(np.mean([r["act_ms_evader"] for r in rs])) if rs else math.nan,
            }
    return ps, es, cell


def markdown_report(results, title="Tournament", meta=None):
    ps, es, cell = summarize(results)
    lines = [f"# {title}", ""]
    if meta:
        for k, v in meta.items():
            lines.append(f"- **{k}**: {v}")
        lines.append("")
    lines += ["## 追者勝率（捕獲 + 躲者撞地；同時出手賽制另含 sma_out），列 = 追者、欄 = 躲者", ""]
    lines.append("| 追者 \\ 躲者 | " + " | ".join(es) + " | 平均 |")
    lines.append("|---|" + "---|" * (len(es) + 1))
    for p in ps:
        row = [f"{100 * cell[(p, e)]['rate']:.0f}% [{100 * cell[(p, e)]['ci'][0]:.0f}–{100 * cell[(p, e)]['ci'][1]:.0f}]"
               for e in es]
        avg = np.mean([cell[(p, e)]["rate"] for e in es])
        lines.append(f"| {p} | " + " | ".join(row) + f" | {100 * avg:.0f}% |")
    lines.append("| **躲者平均存活** | " + " | ".join(
        f"{100 * (1 - np.mean([cell[(p, e)]['rate'] for p in ps])):.0f}%" for e in es) + " | |")
    lines += ["", "## 細節", "",
              "| 追者 | 躲者 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E |",
              "|---|---|---|---|---|---|---|"]
    for p in ps:
        for e in es:
            c = cell[(p, e)]
            oc = ", ".join(f"{k}:{v}" for k, v in sorted(c["outcomes"].items()))
            lines.append(f"| {p} | {e} | {c['n']} | {oc} | {c['min_dist_med']:.1f} | "
                         f"{c['fuel_p']:.0f} / {c['fuel_e']:.0f} | {c['ms_p']:.1f} / {c['ms_e']:.1f} |")
    fams = sorted({r["family"] for r in results})
    if len(fams) > 1:
        lines += ["", "## 依幾何家族的追者勝率（所有配對平均）", "", "| 家族 | n | 追者勝率 |", "|---|---|---|"]
        for f in fams:
            rs = [r for r in results if r["family"] == f]
            lines.append(f"| {f} | {len(rs)} | {100 * np.mean([r['winner'] == 'pursuer' for r in rs]):.0f}% |")
    return "\n".join(lines) + "\n"
