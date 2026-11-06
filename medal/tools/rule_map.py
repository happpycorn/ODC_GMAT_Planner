"""規則敏感度地圖：在基底規則附近逐軸（或兩軸交叉）改欄位，每格用**同一批幾何**跑 rollout 大腦對打，
跟基底格逐局配對（符號檢定），產出當天查表（reports/<name>.md）與機器可讀結果（configs/rule_map.json，
由 tools/rule_lookup.py 讀）。

子命令：
  run     跑格子。每局一結束就 append 到 reports/<name>.jsonl；中斷後用同一個指令重跑會跳過已完成的局。
  report  由 reports/<name>.jsonl 重寫 reports/<name>.md。
  export  把一個或多個 jsonl 合併成 configs/rule_map.json。

配對（--pairs，逗號分隔）：rr = rollout 追 vs rollout 躲；strong = 強化版 rollout 追者（E16，對手模型
多一個 rollout 躲者輕量版）vs rollout 躲；escape = rollout 追 vs 逃逸躲者。core = 三個都跑、fast = rr,escape。

例：
  uv run python tools/rule_map.py run --base configs/rulesets/ranking_like.json --name rmap_ranking \\
      --group burns --group fuel --group window --pairs fast --games 24 --seed 1 --workers 5
  uv run python tools/rule_map.py run --base configs/rulesets/symmetric.json --name rmap_symmetric \\
      --cell burns_per_turn=2 --cell fuel_pursuer_mps=1500 --pairs rr
  uv run python tools/rule_map.py run --base configs/rulesets/ranking_like.json --name rmap_ranges \\
      --ranges ranking --no-base --games 48 --pairs fast      # 規則每局從排位版分布抽（game/rule_presets.py）
  uv run python tools/rule_map.py export --name rmap_ranking --name rmap_symmetric --out configs/rule_map.json

幾何與 evaluate.py 相同（make_games，同 --seed/--scenario 的 game_id 是同一個初始幾何），每局的 agent seed
也相同（seed × 100003 + game_id），所以跟 evaluate.py 的輸出也能逐局配對。--ranges 的格子幾何同上，
規則用另一條亂數流（[seed, game_id, 9]）抽，因此也能跟基底格逐局配對。
"""
import argparse
import datetime
import json
import math
import os
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import fields

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from evaluation.stats import paired  # noqa: E402
from evaluation.tournament import Task, make_games, play, spec_name, wilson  # noqa: E402
from game.rule_presets import make_ranges  # noqa: E402
from game.rules import Rules  # noqa: E402

STRONG_ROLLOUT_PURSUER = {"name": "rollout_pursuer",
                          "opponents": ["coast", "dv_evader_fast",
                                        {"name": "rollout_evader", "candidates": ["dv_evader_fast"],
                                         "opponents": ["lambert_pursuer_fast"]}]}
PAIRS = {
    "rr": ("rollout_pursuer", "rollout_evader"),
    "strong": (STRONG_ROLLOUT_PURSUER, "rollout_evader"),
    "escape": ("rollout_pursuer", "escape_evader"),
    "lambert": ("lambert_pursuer", "rollout_evader"),
}
PAIR_SETS = {"core": ["rr", "strong", "escape"], "fast": ["rr", "escape"]}
PAIR_LABEL = {"rr": "rollout 追 vs rollout 躲", "strong": "強化版追 vs rollout 躲", "escape": "rollout 追 vs 逃逸躲",
              "lambert": "Lambert 追 vs rollout 躲（對照：Lambert 追者不會「判斷全輸就不追」）"}
PURSUER_KEYS = ["rr", "strong", "lambert"]          # 都是對 rollout 躲者
BRAIN_LABEL = {"rr": "預設 rollout 追者", "strong": "強化版 rollout 追者", "lambert": "Lambert 追者"}

# 排位版基底（250/3000）的掃描計畫；每個 dict 是相對基底的改動（跟基底相同的欄位會自動省略）
GROUPS = {
    "burns": [{"burns_per_turn": 2}, {"burns_per_turn": 3}],
    "fuel": [{"fuel_pursuer_mps": 3000.0, "fuel_evader_mps": 1500.0},
             {"fuel_pursuer_mps": 1500.0, "fuel_evader_mps": 3000.0},
             {"fuel_pursuer_mps": 4500.0, "fuel_evader_mps": 3000.0},
             {"fuel_pursuer_mps": 3000.0, "fuel_evader_mps": 4500.0}],
    "window": [{"window_sec": 120.0}, {"window_sec": 600.0}, {"window_sec": 900.0}],
    "maxdv": [{"max_dv_pursuer_mps": 250.0, "max_dv_evader_mps": 150.0},
              {"max_dv_pursuer_mps": 150.0, "max_dv_evader_mps": 250.0}],
    "tmax": [{"t_max_periods": 2.0}, {"t_max_periods": 6.0}],
    "radius": [{"capture_radius_km": 1.0}, {"capture_radius_km": 20.0}],
    "first": [{"first_mover": "evader"}],
    "capmode": [{"capture_mode": "endpoint"}],
    "burns_x_fuel": [{"burns_per_turn": 2, "fuel_pursuer_mps": 1500.0},
                     {"burns_per_turn": 2, "fuel_evader_mps": 4500.0},
                     {"burns_per_turn": 3, "fuel_pursuer_mps": 1500.0},
                     {"burns_per_turn": 3, "fuel_evader_mps": 4500.0}],
    "burns_x_window": [{"burns_per_turn": 2, "window_sec": 120.0},
                       {"burns_per_turn": 2, "window_sec": 600.0},
                       {"burns_per_turn": 2, "window_sec": 900.0},
                       {"burns_per_turn": 3, "window_sec": 600.0},
                       {"burns_per_turn": 3, "window_sec": 900.0}],
}
RANGES_STREAM = 9          # --ranges 的規則亂數流 = default_rng([seed, game_id, 9])
SIG = 0.05                 # 報表粗體、建議用的顯著水準（多重比較：幾十個檢定裡預期 ~5% 是偽陽性）

FIELD_TYPES = {f.name: f.type for f in fields(Rules)}
AXES = [("burns_per_turn", ("burns_per_turn",)), ("fuel", ("fuel_pursuer_mps", "fuel_evader_mps")),
        ("window_sec", ("window_sec",)), ("max_dv", ("max_dv_pursuer_mps", "max_dv_evader_mps")),
        ("t_max_periods", ("t_max_periods",)), ("capture_radius_km", ("capture_radius_km",)),
        ("first_mover", ("first_mover",)), ("capture_mode", ("capture_mode",))]
AXIS_OF_FIELD = {f: a for a, fs in AXES for f in fs}
AXIS_RANK = {a: i for i, (a, _) in enumerate(AXES)}
SHORT = {"burns_per_turn": "一回合發數", "window_sec": "窗口 s", "t_max_periods": "T_max 週期",
         "capture_radius_km": "捕獲半徑 km", "first_mover": "先手", "capture_mode": "捕獲判定",
         "gravity_degree": "重力", "min_burn_gap_sec": "機動間隔 s"}


# ------------------------------------------------------------------ 格子
def _coerce(name, v):
    if name not in FIELD_TYPES:
        raise KeyError(f"未知的規則欄位 {name!r}（可用：{sorted(FIELD_TYPES)}）")
    t = FIELD_TYPES[name]
    if t is int:
        return int(float(v))
    if t is float:
        return float(v)
    return str(v)


def parse_cell(s):
    """'window_sec=120,burns_per_turn=2' → {'window_sec': 120.0, 'burns_per_turn': 2}"""
    out = {}
    for tok in s.split(","):
        k, v = tok.split("=", 1)
        out[k.strip()] = _coerce(k.strip(), v.strip())
    return out


def normalize(ov, base):
    """只留跟基底不同的欄位，照 Rules 欄位順序。"""
    for k in ov:
        _coerce(k, ov[k])
    b = base.to_dict()
    return {k: _coerce(k, ov[k]) for k in FIELD_TYPES if k in ov and _coerce(k, ov[k]) != b[k]}


def _fmt(v):
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def cell_id(ov):
    return ",".join(f"{k}={_fmt(v)}" for k, v in ov.items()) or "base"


def axis_of(ov, ranges=None):
    if ranges:
        return "ranges"
    if not ov:
        return "base"
    axes = []
    for k in ov:
        a = AXIS_OF_FIELD.get(k, k)
        if a not in axes:
            axes.append(a)
    axes.sort(key=lambda a: AXIS_RANK.get(a, 99))
    return "×".join(axes)


def cell_label(ov, base, ranges=None):
    if ranges:
        return f"規則分布 {ranges}（每局抽）"
    if not ov:
        return "基底"
    R = base.with_(**ov)
    parts, seen = [], set()
    for k in ov:
        a = AXIS_OF_FIELD.get(k, k)
        if a in seen:
            continue
        seen.add(a)
        if a == "fuel":
            parts.append(f"燃料 追{_fmt(R.fuel_pursuer_mps)}/躲{_fmt(R.fuel_evader_mps)}")
        elif a == "max_dv":
            parts.append(f"單發 追{_fmt(R.max_dv_pursuer_mps)}/躲{_fmt(R.max_dv_evader_mps)}")
        else:
            parts.append(f"{SHORT.get(k, k)} {_fmt(ov[k])}")
    return " × ".join(parts)


def _cell_sort_key(c):
    ax = c["axis"]
    first = ax.split("×")[0]
    rank = (0 if ax == "base" else 1000 if ax == "ranges" else
            (100 if "×" in ax else 0) + AXIS_RANK.get(first, 99) + 1)
    vals = tuple((0, v) if isinstance(v, (int, float)) else (1, str(v)) for v in c["overrides"].values())
    return (rank, ax, vals)


# ------------------------------------------------------------------ 執行
def _play_timed(task):
    t0 = time.perf_counter()
    r = play(task)
    r["wall_s"] = time.perf_counter() - t0
    return r


def git_commit():
    try:
        h = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                           cwd=ROOT).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], capture_output=True,
                               text=True, cwd=ROOT).stdout.strip()
        return (h or "unknown") + ("-dirty" if dirty else "")
    except OSError:
        return "unknown"


def load_rows(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def resolve_pairs(tokens):
    """['core'] / ['rr', 'escape'] / [('key', p_spec, e_spec)] → [(key, p_spec, e_spec)]"""
    out = []
    for t in tokens:
        if isinstance(t, tuple):
            out.append(t)
        elif t in PAIR_SETS:
            out += [(k, *PAIRS[k]) for k in PAIR_SETS[t]]
        else:
            out.append((t, *PAIRS[t]))
    return out


def build_tasks(base, cells, pairs, n_games, seed, scenario):
    """cells = [(cell_id, overrides, ranges_name 或 None)] → [(meta, Task)]，依格子、配對、局的順序。"""
    geom = make_games(n_games, base.to_dict(), scenario, seed)
    out = []
    for cid, ov, rng_name in cells:
        dist = make_ranges(rng_name) if rng_name else None
        for key, p, e in pairs:
            for gi, game in enumerate(geom):
                sampled_rules, op, oe, fam = game[:4]
                scenario_meta = game[4] if len(game) == 5 else None
                sampled_base = Rules.from_dict(sampled_rules)
                if dist is not None:
                    R = dist.sample(np.random.default_rng([seed, gi, RANGES_STREAM]), sampled_base)
                else:
                    R = sampled_base.with_(**ov)
                meta = {"cell": cid, "overrides": ov, "ranges": rng_name, "pair": key}
                out.append((meta, Task(p, e, R.to_dict(), op, oe, fam, gi, seed * 100003 + gi,
                                       scenario_meta)))
    return out


def run_cells(base, cells, pairs, n_games, seed, scenario, workers, path, extra_meta=None, log=print):
    """跑還沒跑過的局，每局結束就 append 一行到 path。回傳這次跑的局數。"""
    have = {(r["cell"], r["pursuer"], r["evader"], r["game_id"]): r for r in load_rows(path)}
    todo = []
    for meta, task in build_tasks(base, cells, resolve_pairs(pairs), n_games, seed, scenario):
        key = (meta["cell"], spec_name(task.pursuer), spec_name(task.evader), task.game_id)
        if key in have:
            if have[key]["rules"] != task.rules:
                raise SystemExit(f"{path} 裡 {key[:2]} 第 {key[3]} 局的規則跟這次不同；換一個 --name")
            continue
        todo.append((meta, task))
    log(f"{len(todo)} 局要跑（{path} 已有 {len(have)} 局）", flush=True)
    common = {"seed": seed, "scenario": scenario, "base": base.to_dict(), "commit": git_commit(),
              **(extra_meta or {})}
    t0 = time.time()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a") as f:
        def emit(i, meta, r):
            r.update(meta)
            r.update(common)
            f.write(json.dumps(r, default=float) + "\n")
            f.flush()
            log(f"[{i + 1}/{len(todo)} {time.time() - t0:.0f}s] {meta['cell']} {meta['pair']} g{r['game_id']}: "
                f"{r['outcome']} ({r['wall_s']:.0f}s)", flush=True)
        if workers <= 1:
            for i, (meta, task) in enumerate(todo):
                emit(i, meta, _play_timed(task))
        else:
            with ProcessPoolExecutor(max_workers=workers) as ex:
                futs = {ex.submit(_play_timed, task): meta for meta, task in todo}
                for i, fut in enumerate(as_completed(futs)):
                    emit(i, futs[fut], fut.result())
    return len(todo)


# ------------------------------------------------------------------ 統計
def group_rows(rows):
    cells = {}
    for r in rows:
        c = cells.setdefault(r["cell"], {"overrides": r["overrides"], "ranges": r.get("ranges"),
                                         "family": r.get("family"), "base": r.get("base"), "pairs": {}})
        c["pairs"].setdefault(r.get("pair") or f"{r['pursuer']}|{r['evader']}", []).append(r)
    for c in cells.values():
        for rs in c["pairs"].values():
            rs.sort(key=lambda r: r["game_id"])
    return cells


def pair_stats(rs, base_rs=None):
    n = len(rs)
    k = sum(r["winner"] == "pursuer" for r in rs)
    lo, hi = wilson(k, n)
    st = {"n": n, "k": k, "rate": k / n if n else math.nan, "ci": [lo, hi],
          "game_ids": [r["game_id"] for r in rs],
          "wins": "".join("1" if r["winner"] == "pursuer" else "0" for r in rs),
          "outcomes": dict(Counter(r["outcome"] for r in rs)),
          "min_dist_med_km": float(np.median([r["min_dist_km"] for r in rs])),
          "fuel_used_p": float(np.mean([r["used_pursuer_mps"] for r in rs])),
          "fuel_used_e": float(np.mean([r["used_evader_mps"] for r in rs])),
          "ms_p": float(np.mean([r["act_ms_pursuer"] for r in rs])),
          "ms_e": float(np.mean([r["act_ms_evader"] for r in rs])),
          "wall_s": float(np.mean([r.get("wall_s", math.nan) for r in rs]))}
    if base_rs is not None:
        p = paired(base_rs, rs, "pursuer")
        st["vs_base"] = {"n": p["n"], "only_base": p["only_a"], "only_cell": p["only_b"], "p": p["p_sign"]}
    return st


def advise(S, cmps, cmp_e):
    """cmps：{"strong": rr vs strong 配對, "lambert": rr vs lambert 配對}；cmp_e：rr vs escape（躲者存活）。"""
    out = {}
    cands = [k for k in PURSUER_KEYS if k in S]
    if not cands:
        return out
    best_k = max(cands, key=lambda k: (S[k]["rate"], -PURSUER_KEYS.index(k)))
    sig = {k: c for k, c in cmps.items() if c and c["p"] < SIG}
    if best_k != "rr" and best_k in sig and sig[best_k][f"only_{best_k}"] > sig[best_k]["only_rollout"]:
        c = sig[best_k]
        out["pursuer_brain"] = best_k
        brain = f"用{BRAIN_LABEL[best_k]}（顯著優於 rollout：+{c[f'only_{best_k}']}/−{c['only_rollout']} p={c['p']:.2g}）"
    elif best_k == "rr" and any(c[f"only_{k}"] < c["only_rollout"] for k, c in sig.items()):
        out["pursuer_brain"] = "rr"
        worse = "、".join(BRAIN_LABEL[k] for k, c in sig.items() if c[f"only_{k}"] < c["only_rollout"])
        brain = f"用預設 rollout 追者（顯著優於{worse}）"
    else:
        out["pursuer_brain"] = "n.s."
        brain = (f"{BRAIN_LABEL[best_k]}點估計最高，但跟其他追者大腦看不出差異，照 copilot ★" if len(cands) > 1
                 else f"用{BRAIN_LABEL[best_k]}")
    best = S[best_k]
    lo, hi = best["ci"]
    out["favored"] = "pursuer" if lo > 0.5 else "evader" if hi < 0.5 else "even"
    out["best_pursuer"] = best_k
    out["best_pursuer_rate"] = best["rate"]
    out["best_pursuer_ci"] = best["ci"]
    txt = {"pursuer": "追者有利", "evader": "躲者有利", "even": "看不出誰有利（區間跨 50%）"}[out["favored"]]
    out["as_pursuer"] = f"{txt}；{brain}；預期勝率 {100 * best['rate']:.0f}% [{100 * lo:.0f}–{100 * hi:.0f}]（對 rollout 躲者）"
    ev = "用 rollout 躲者"
    out["evader_brain"] = "rollout"
    if cmp_e:
        if cmp_e["p"] < SIG and cmp_e["only_escape"] > cmp_e["only_rollout"]:
            ev, out["evader_brain"] = "逃逸大腦存活顯著較高（對 rollout 追者），優先考慮 escape_evader", "escape"
        elif cmp_e["p"] < SIG:
            ev = "用 rollout 躲者，不要逃逸（逃逸顯著較差）"
        else:
            ev += f"（逃逸看不出差異，p={cmp_e['p']:.2g}）"
    out["as_evader"] = (f"{ev}；預期存活 {100 * (1 - best['rate']):.0f}% [{100 * (1 - hi):.0f}–{100 * (1 - lo):.0f}]"
                        f"（對我們最強的追者：{BRAIN_LABEL[best_k]}）")
    return out


def cell_stats(rows):
    cells = group_rows(rows)
    base = cells.get("base")
    out = []
    for cid, c in cells.items():
        S = {pk: pair_stats(rs, base["pairs"].get(pk) if base and cid != "base" else None)
             for pk, rs in c["pairs"].items()}
        cmps, cmp_e = {}, None
        for k in PURSUER_KEYS[1:]:
            if "rr" in c["pairs"] and k in c["pairs"]:
                p = paired(c["pairs"]["rr"], c["pairs"][k], "pursuer")
                cmps[k] = {"n": p["n"], "only_rollout": p["only_a"], f"only_{k}": p["only_b"], "p": p["p_sign"]}
        if "rr" in c["pairs"] and "escape" in c["pairs"]:
            p = paired(c["pairs"]["rr"], c["pairs"]["escape"], "evader")
            cmp_e = {"n": p["n"], "only_rollout": p["only_a"], "only_escape": p["only_b"], "p": p["p_sign"]}
        base_rules = Rules.from_dict(c["base"]) if c.get("base") else Rules()
        rules = None if c["ranges"] else c["pairs"][next(iter(c["pairs"]))][0]["rules"]
        out.append({"family": c.get("family"), "id": cid, "axis": axis_of(c["overrides"], c["ranges"]),
                    "label": cell_label(c["overrides"], base_rules, c["ranges"]),
                    "overrides": c["overrides"], "ranges": c["ranges"], "rules": rules, "pairs": S,
                    "pursuer_compare": cmps.get("strong"), "lambert_compare": cmps.get("lambert"),
                    "evader_compare": cmp_e, "advice": advise(S, cmps, cmp_e)})
    out.sort(key=_cell_sort_key)
    return out


# ------------------------------------------------------------------ 報表
def _rate(st):
    if not st:
        return "—"
    lo, hi = st["ci"]
    return f"{100 * st['rate']:.0f}% [{100 * lo:.0f}–{100 * hi:.0f}]"


def _delta(st):
    if not st or "vs_base" not in st:
        return "—"
    v = st["vs_base"]
    s = f"+{v['only_cell']}/−{v['only_base']} p={v['p']:.2g}"
    return f"**{s}**" if v["p"] < SIG else s


def _cmp(c, a, b):
    if not c:
        return "—"
    s = f"+{c[b]}/−{c[a]} p={c['p']:.2g}"
    return f"**{s}**" if c["p"] < SIG else s


def markdown(stats, name):
    base = next((c for c in stats if c["id"] == "base"), None)
    any_rows = stats[0]["pairs"][next(iter(stats[0]["pairs"]))] if stats else None
    n = any_rows["n"] if any_rows else 0
    lines = [f"# 規則敏感度地圖 {name}", ""]
    fam = stats[0].get("family") if stats else None
    if base and base.get("rules"):
        R = base["rules"]
        lines.append(f"- 基底 `{fam}`：單發 追{_fmt(R['max_dv_pursuer_mps'])}/躲{_fmt(R['max_dv_evader_mps'])}、燃料 "
                     f"追{_fmt(R['fuel_pursuer_mps'])}/躲{_fmt(R['fuel_evader_mps'])}、窗口 {_fmt(R['window_sec'])} s、"
                     f"半徑 {_fmt(R['capture_radius_km'])} km、T_max {_fmt(R['t_max_periods'])} 週期、"
                     f"先手 {R['first_mover']}、{R['burns_per_turn']} 發/回合、{R['capture_mode']}、J{R['gravity_degree']}")
    lines += [f"- 每格 n = {n} 局（同一批幾何；各格 n 見細節表）",
              "- 配對：" + "；".join(f"{k} = {v}" for k, v in PAIR_LABEL.items()),
              f"- 格內：追者勝率 [95% Wilson 區間]。「vs 基底」= 跟基底格同一局逐局配對：+只有本格抓到 / −只有基底抓到，"
              f"p = 雙尾精確符號檢定；**粗體** = p < {SIG}（幾十個檢定裡約 5% 會是偽陽性，單一個 p≈0.03 要保守看）", "",
              "## 追者勝率", ""]
    keys = [k for k in ("rr", "strong", "lambert", "escape") if any(k in c["pairs"] for c in stats)]
    lines.append("| 軸 | 格子 | " + " | ".join(f"{k} | {k} vs 基底" for k in keys) + " |")
    lines.append("|---|---|" + "---|---|" * len(keys))
    for c in stats:
        S = c["pairs"]
        lines.append(f"| {c['axis']} | {c['label']} | " +
                     " | ".join(f"{_rate(S.get(k))} | {_delta(S.get(k))}" for k in keys) + " |")
    lines += ["", "## 大腦選擇與建議", "",
              "強化/Lambert vs rollout 追者：同格同局配對（+只有該大腦抓到 / −只有 rollout 抓到）；"
              "逃逸 vs rollout 躲者：對 rollout 追者的存活（+只有逃逸活下來 / −只有 rollout 躲者活下來）。", "",
              "| 格子 | 強化 vs rollout 追者 | Lambert vs rollout 追者 | 逃逸 vs rollout 躲者 | 抽到追者 | 抽到躲者 |",
              "|---|---|---|---|---|---|"]
    for c in stats:
        a = c["advice"]
        lines.append(f"| {c['label']} | {_cmp(c['pursuer_compare'], 'only_rollout', 'only_strong')} | "
                     f"{_cmp(c.get('lambert_compare'), 'only_rollout', 'only_lambert')} | "
                     f"{_cmp(c['evader_compare'], 'only_rollout', 'only_escape')} | {a.get('as_pursuer', '—')} | "
                     f"{a.get('as_evader', '—')} |")
    lines += ["", "## 細節", "",
              "| 格子 | 配對 | n | 結局 | 最近距離中位數 km | 燃料 P / E (m/s) | 決策 ms P / E | 每局 s |",
              "|---|---|---|---|---|---|---|---|"]
    for c in stats:
        for pk, st in c["pairs"].items():
            oc = ", ".join(f"{k}:{v}" for k, v in sorted(st["outcomes"].items()))
            lines.append(f"| {c['label']} | {pk} | {st['n']} | {oc} | {st['min_dist_med_km']:.1f} | "
                         f"{st['fuel_used_p']:.0f} / {st['fuel_used_e']:.0f} | {st['ms_p']:.0f} / {st['ms_e']:.0f} | "
                         f"{st['wall_s']:.0f} |")
    commits = sorted({c for c in (stats and [s.get("commit") for s in stats]) if c})
    if commits:
        lines += ["", f"- commit：{', '.join(commits)}"]
    return "\n".join(lines) + "\n"


def write_report(name, reports_dir="reports"):
    rows = load_rows(os.path.join(reports_dir, f"{name}.jsonl"))
    stats = cell_stats(rows)
    for c in stats:
        c["commit"] = ",".join(sorted({r.get("commit", "?") for r in rows if r["cell"] == c["id"]}))
    md = markdown(stats, name)
    with open(os.path.join(reports_dir, f"{name}.md"), "w") as f:
        f.write(md)
    return md


def export(names, out, reports_dir="reports"):
    cells, meta = [], {}
    for name in names:
        rows = load_rows(os.path.join(reports_dir, f"{name}.jsonl"))
        if not rows:
            raise SystemExit(f"{reports_dir}/{name}.jsonl 沒有資料")
        for c in cell_stats(rows):
            c["source"] = name
            c["commits"] = sorted({r.get("commit", "?") for r in rows if r["cell"] == c["id"]})
            cells.append(c)
        meta[name] = {"seed": rows[0]["seed"], "scenario": rows[0]["scenario"], "family": rows[0].get("family"),
                      "base_rules": rows[0]["base"]}
    doc = {"_comment": "tools/rule_map.py export 產生；tools/rule_lookup.py 讀。勝率 = 追者勝率（同一批幾何），"
                       "vs_base = 跟同一 source 的基底格逐局配對（符號檢定）",
           "generated": datetime.datetime.now().isoformat(timespec="seconds"), "sig_level": SIG,
           "pairs": {k: {"label": PAIR_LABEL[k], "pursuer": spec_name(p), "evader": spec_name(e)}
                     for k, (p, e) in PAIRS.items()},
           "sources": meta, "cells": cells}
    with open(out, "w") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1, default=float)
    return doc


# ------------------------------------------------------------------ CLI
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--base", default=None, help="基底規則 JSON（預設 Rules()）")
    r.add_argument("--name", required=True)
    r.add_argument("--group", action="append", default=[], help=f"掃描計畫：{', '.join(GROUPS)}")
    r.add_argument("--cell", action="append", default=[], help="自訂格子：欄位=值,欄位=值")
    r.add_argument("--ranges", default=None, help="加一個「規則每局從分布抽」的格子（ranking / default）")
    r.add_argument("--no-base", action="store_true", help="不跑基底格（例如基底已在別的 --name 裡）")
    r.add_argument("--pairs", default="core", help="rr,strong,escape 或 core / fast")
    r.add_argument("--games", type=int, default=24)
    r.add_argument("--seed", type=int, default=1)
    r.add_argument("--scenario", default="mixed")
    r.add_argument("--workers", type=int, default=5)
    rp = sub.add_parser("report")
    rp.add_argument("--name", required=True)
    ex = sub.add_parser("export")
    ex.add_argument("--name", action="append", required=True)
    ex.add_argument("--out", default="configs/rule_map.json")
    args = ap.parse_args()

    if args.cmd == "report":
        print(write_report(args.name))
        return
    if args.cmd == "export":
        doc = export(args.name, args.out)
        print(f"→ {args.out}（{len(doc['cells'])} 格）")
        return

    if args.base:
        with open(args.base) as f:
            base = Rules.from_dict(json.load(f))
        family = os.path.splitext(os.path.basename(args.base))[0]
    else:
        base, family = Rules(), "default"
    ovs = [] if args.no_base else [{}]
    for g in args.group:
        ovs += GROUPS[g]
    ovs += [parse_cell(c) for c in args.cell]
    cells, seen = [], set()
    for ov in ovs:
        ov = normalize(ov, base)
        cid = cell_id(ov)
        if cid not in seen:
            seen.add(cid)
            cells.append((cid, ov, None))
    if args.ranges:
        cells.append((f"ranges:{args.ranges}", {}, args.ranges))
    pairs = [t.strip() for t in args.pairs.split(",") if t.strip()]
    print(f"{len(cells)} 格 × {len(resolve_pairs(pairs))} 配對 × {args.games} 局：{[c[0] for c in cells]}", flush=True)
    run_cells(base, cells, pairs, args.games, args.seed, args.scenario, args.workers,
              os.path.join("reports", f"{args.name}.jsonl"), extra_meta={"family": family})
    md = write_report(args.name)
    print(md.split("## 大腦選擇")[0])


if __name__ == "__main__":
    main()
