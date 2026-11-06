"""公告後以固定題目和規則對打，估計我方選追方或躲方的勝率。

用法：.venv/bin/python tools/role_select.py initial.json --rules announced.json
      [--budget-sec 150] [--workers 4] [--fast] [--seed 0] [--max-games 40] [--json out.json]
"""
import argparse
import json
import math
import os
import sys
import time
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import dataclass

START_MONOTONIC = time.monotonic()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from runtime_threads import limit_blas_threads  # noqa: E402

limit_blas_threads()

import numpy as np  # noqa: E402

from evaluation.tournament import _agent, _initialize_worker, _json_compatible, wilson  # noqa: E402
from game.core import Game, round_view, sma_official  # noqa: E402
from game.initial_state import align_initial_states  # noqa: E402
from game.rules import Rules  # noqa: E402
from game.scenarios import full_burn_dsma_km  # noqa: E402
from physics import EARTH_MU, RE_VAL  # noqa: E402


@dataclass(frozen=True)
class Pairing:
    role: str
    our_agent: str
    opponent: str
    pursuer: str
    evader: str


@dataclass(frozen=True)
class FixedTask:
    pairing_index: int
    rules: dict
    rp: tuple
    vp: tuple
    re: tuple
    ve: tuple
    pursuer: str
    evader: str
    seed: int


def _pairings(fast):
    capture = "capture_pursuer_fast" if fast else "capture_pursuer"
    safe = "safe_evader_fast" if fast else "safe_evader"
    return [
        Pairing("pursuer", capture, safe, capture, safe),
        Pairing("pursuer", capture, "heuristic_evader", capture, "heuristic_evader"),
        Pairing("pursuer", capture, "dv_evader", capture, "dv_evader"),
        Pairing("evader", safe, capture, capture, safe),
        Pairing("evader", safe, "lambert_pursuer", "lambert_pursuer", safe),
    ]


def _play_fixed(task):
    """子行程執行一局；與 tournament.play 使用相同的回合副本及計時口徑。"""
    start = time.perf_counter()
    P = _agent(task.pursuer)
    E = _agent(task.evader)
    P.reset(seed=task.seed)
    E.reset(seed=task.seed + 1)
    g = Game(Rules.from_dict(dict(task.rules)), task.rp, task.vp, task.re, task.ve)
    act_sec = {"pursuer": 0.0, "evader": 0.0}
    n_act = {"pursuer": 0, "evader": 0}
    while not g.done:
        dv = {}
        for side, agent in (("pursuer", P), ("evader", E)):
            t0 = time.perf_counter()
            dv[side] = agent.act(round_view(g, agent, side), side)
            act_sec[side] += time.perf_counter() - t0
            n_act[side] += 1
        g.play_round(dv["pursuer"], dv["evader"])
    summary = g.summary()
    # 同一題目在不同種子下動作及結局完全相同，才算這次配對可視作確定性。
    signature = [(rec["outcome"], tuple(tuple(round(float(x), 9) for x in burn["dv_eci_mps"])
                                         for burn in rec["burns"])) for rec in g.history]
    return {"pairing_index": task.pairing_index, "seed": task.seed,
            "winner": summary["winner"], "outcome": summary["outcome"],
            "elapsed_sec": time.perf_counter() - start,
            "act_ms_pursuer": 1000.0 * act_sec["pursuer"] / max(1, n_act["pursuer"]),
            "act_ms_evader": 1000.0 * act_sec["evader"] / max(1, n_act["evader"]),
            "info_evader": _json_compatible(getattr(E, "history_info", None)),
            "info_pursuer": _json_compatible(getattr(P, "history_info", None)),
            "signature": signature}


def _read_json(path, what):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError as exc:
        raise ValueError(f"找不到{what}檔案 {path!r}；請確認檔名與目前工作目錄") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{what}檔案 {path!r} 不是合法 JSON（第 {exc.lineno} 行、"
                         f"第 {exc.colno} 欄）；請檢查逗號、引號與 null") from exc
    except OSError as exc:
        raise ValueError(f"無法讀取{what}檔案 {path!r}：{exc}") from exc


def _load_inputs(initial_path, rules_path):
    raw_rules = _read_json(rules_path, "規則")
    if not isinstance(raw_rules, dict):
        raise ValueError("規則檔頂層要是 JSON 物件，欄位例如 turn_mode、window_sec、safe_sma_km")
    try:
        rules = Rules.from_dict(dict(raw_rules))
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        raise ValueError(f"規則檔格式錯誤：{exc}；請檢查單位（ΔV 用 m/s、距離與安全空域用 km、時間用秒）") from exc
    if not rules.simultaneous:
        raise ValueError("規則 turn_mode 必須是 simultaneous；請將公告規則檔的 turn_mode 設為 simultaneous")
    if rules.max_dv_pursuer_mps <= 0 or rules.max_dv_evader_mps <= 0 or rules.capture_radius_km <= 0:
        raise ValueError("規則的 max_dv_pursuer_mps、max_dv_evader_mps、capture_radius_km 都必須大於 0"
                         "（ΔV 用 m/s、R_cap 用 km）")
    raw_initial = _read_json(initial_path, "初始狀態")
    if not isinstance(raw_initial, dict):
        raise ValueError("初始狀態檔頂層要是 JSON 物件，含 pursuer 與 evader")
    try:
        aligned = align_initial_states(raw_initial)
        rp, vp = aligned["pursuer"]
        re, ve = aligned["evader"]
        game = Game(rules, rp, vp, re, ve)
    except (ValueError, KeyError, TypeError, IndexError, OverflowError) as exc:
        raise ValueError(f"初始狀態格式錯誤：{exc}；請給雙方 r_km、v_kms（EarthMJ2000Eq，km 與 km/s）"
                         "或 elements，epoch 要雙方都給或都不給；其他座標系先用 tools/gmat_state_convert.py 轉換") from exc
    return game, aligned


def _perigee_alt(r, v):
    rn = float(np.linalg.norm(r))
    h2 = float(np.dot(np.cross(r, v), np.cross(r, v)))
    energy = 0.5 * float(np.dot(v, v)) - EARTH_MU / rn
    ecc = math.sqrt(max(0.0, 1.0 + 2.0 * energy * h2 / EARTH_MU ** 2))
    return h2 / (EARTH_MU * (1.0 + ecc)) - RE_VAL


def _initial_summary(game, aligned):
    rp, vp = aligned["pursuer"]
    re, ve = aligned["evader"]
    rules = game.rules
    a_e = sma_official(re, ve)
    zone = rules.safe_sma_km
    if zone is None or not math.isfinite(a_e):
        offset = None
    elif zone[0] <= a_e <= zone[1]:
        offset = 0.0
    else:
        center = 0.5 * (zone[0] + zone[1])
        cap = full_burn_dsma_km(a_e, rules.max_dv_evader_mps) if a_e > 0 else 0.0
        offset = abs(center - a_e) / cap if cap > 0.0 else None
    dv = rules.max_dv_pursuer_mps
    return {"epoch": aligned["epoch"].isoformat() if aligned["epoch"] else None,
            "propagated_sec": aligned["propagated_sec"],
            "distance_km": float(np.linalg.norm(rp - re)),
            "pursuer": {"altitude_km": float(np.linalg.norm(rp)) - RE_VAL,
                         "perigee_alt_km": _perigee_alt(rp, vp)},
            "evader": {"altitude_km": float(np.linalg.norm(re)) - RE_VAL,
                       "perigee_alt_km": _perigee_alt(re, ve)},
            "evader_sma_km": a_e if math.isfinite(a_e) else None,
            "safe_sma_km": list(zone) if zone is not None else None,
            "zone_offset_burns": offset,
            "tau_star_sec": 1000.0 * rules.capture_radius_km / dv if dv > 0 else None,
            "dv_window_km": dv * rules.window_sec / 1000.0,
            "dv_lim_mps": dv, "capture_radius_km": rules.capture_radius_km,
            "window_sec": rules.window_sec,
            "zone_features": _zone_features(rp, vp, re, ve, rules)}


def _zone_features(rp, vp, re, ve, rules):
    """安全空域對抗特徵（E29）：寬度、是否蓋住追方 a、是否要穿過追方軌道、6 發全推到不到得了。

    「到得了」用同一點連續沿速度方向推滿（近圓軌道的近似），只當旗標；勝率仍以模擬為準。"""
    zone = rules.safe_sma_km
    if zone is None:
        return {"flags": [], "reachable": True}
    from agents.final_common import sma_after
    a_p, a_e = sma_official(rp, vp), sma_official(re, ve)
    lo, hi = zone
    center = 0.5 * (lo + hi)
    da = full_burn_dsma_km(a_e, rules.max_dv_evader_mps) if a_e > 0 else math.nan
    width_da = (hi - lo) / da if da > 0 else math.nan
    ap_in = bool(lo <= a_p <= hi)
    cross = bool((a_e - a_p) * (center - a_p) < 0.0) and not lo <= a_e <= hi
    v = np.asarray(ve, dtype=float).copy()
    burns_needed = 0.0
    if not lo <= a_e <= hi:
        sign = 1.0 if a_e < lo else -1.0
        a_prev = a_e
        burns_needed = math.inf
        for k in range(1, rules.rounds + 1):
            v = v + sign * v / np.linalg.norm(v) * (rules.max_dv_evader_mps / 1000.0)
            a_k = float(sma_after(np.asarray(re, dtype=float), v, np.zeros(3)))
            near = lo if sign > 0 else hi
            if (a_k - near) * sign >= 0.0 or not math.isfinite(a_k) or a_k < 0:
                burns_needed = (k - 1) + (abs(near - a_prev) / abs(a_k - a_prev) if a_k != a_prev else 1.0)
                break
            a_prev = a_k
    reachable = burns_needed <= rules.rounds
    dist = float(np.linalg.norm(np.asarray(rp) - np.asarray(re)))
    flags = []
    if not reachable:
        flags.append(f"6 發都沿速度方向推滿也到不了安全空域：躲方必輸（sma_out）")
    elif burns_needed >= 4.5:
        flags.append(f"安全空域很遠（約 {burns_needed:.1f} 發）：躲方幾乎每回合都得往同方向推，推力好猜")
    if math.isfinite(width_da) and width_da < 0.1:
        flags.append(f"安全空域很窄（寬 {width_da:.3f} 發容量）：躲方最後一回合要精準入區")
    if ap_in:
        flags.append("安全空域蓋住追方的 a：躲方入區後跟追方週期相近、相對漂移慢")
    if cross:
        flags.append("躲方要穿過追方的 a 才到得了安全空域")
    if dist < 0.2 * rules.max_dv_pursuer_mps * rules.window_sec / 1000.0:
        flags.append(f"初始距離很近（{dist:.1f} km < 0.2·ΔV_lim·T_round）")
    return {"a_p": a_p, "a_e": a_e, "zone_width_burns": width_da, "ap_in_zone": ap_in, "cross": cross,
            "burns_needed": burns_needed, "reachable": reachable, "flags": flags}


def _task(pairing_index, pairing, game, seed):
    return FixedTask(pairing_index, game.rules.to_dict(),
                     tuple(float(x) for x in game.r("pursuer")),
                     tuple(float(x) for x in game.v("pursuer")),
                     tuple(float(x) for x in game.r("evader")),
                     tuple(float(x) for x in game.v("evader")),
                     pairing.pursuer, pairing.evader, seed)


def _stop_pool(executor):
    """硬截止時終止仍在計算的 worker，避免 executor 等待長局超出預算。"""
    processes = list((getattr(executor, "_processes", None) or {}).values())
    for process in processes:
        if process.is_alive():
            process.terminate()
    executor.shutdown(wait=False, cancel_futures=True)
    for process in processes:
        process.join(timeout=0.1)


def _simulate(game, pairings, budget_sec, workers, max_games, seed):
    deadline = START_MONOTONIC + budget_sec
    work_deadline = deadline - min(2.0, 0.05 * budget_sec)
    results = [[] for _ in pairings]
    probe_games = [0] * len(pairings)
    actual_games = 0
    timed_out = False
    executor = ProcessPoolExecutor(max_workers=workers, initializer=_initialize_worker)
    pending = {}
    try:
        # 第一波：每個配對各一局；第一局的耗時包含該 worker 的 JIT 暖機。
        for i, pairing in enumerate(pairings):
            game_seed = seed + 1000003 * i
            future = executor.submit(_play_fixed, _task(i, pairing, game, game_seed))
            pending[future] = i
        while pending and time.monotonic() < work_deadline:
            done, _ = wait(pending, timeout=max(0.0, work_deadline - time.monotonic()),
                           return_when=FIRST_COMPLETED)
            for future in done:
                i = pending.pop(future)
                results[i].append(future.result())
                actual_games += 1
                print(f"初測 {actual_games}/{len(pairings)}：{pairings[i].our_agent} 對 "
                      f"{pairings[i].opponent}，{results[i][-1]['elapsed_sec']:.1f} 秒", flush=True)
        if pending:
            timed_out = True

        # 已知兩個 agent 都不使用隨機抽樣時，再用不同種子確認動作及結局相同。
        deterministic = [False] * len(pairings)
        potential = {"lambert_pursuer", "lambert_pursuer_fast", "dv_evader", "dv_evader_fast"}
        if not timed_out:
            for i, pairing in enumerate(pairings):
                if pairing.pursuer in potential and pairing.evader in potential:
                    probe = executor.submit(_play_fixed, _task(i, pairing, game, seed + 1000003 * i + 1))
                    pending[probe] = i
            while pending and time.monotonic() < work_deadline:
                done, _ = wait(pending, timeout=max(0.0, work_deadline - time.monotonic()),
                               return_when=FIRST_COMPLETED)
                for future in done:
                    i = pending.pop(future)
                    result = future.result()
                    actual_games += 1
                    if result["signature"] == results[i][0]["signature"]:
                        deterministic[i] = True
                        probe_games[i] += 1
                    else:
                        results[i].append(result)
            if pending:
                timed_out = True

        # 用第一波各局實測秒數估可完成的額外局數，平均分給需要抽樣的配對。
        if not timed_out:
            active = [i for i in range(len(pairings)) if not deterministic[i] and len(results[i]) < max_games]
            cost = np.mean([results[i][0]["elapsed_sec"] for i in active]) if active else math.inf
            remaining = max(0.0, work_deadline - time.monotonic())
            extra = 0 if not math.isfinite(cost) or cost <= 0 else int(0.85 * remaining * workers / cost)
            extra = min(extra, sum(max_games - len(results[i]) for i in active))
            targets = [len(rows) for rows in results]
            for j in range(extra):
                available = [i for i in active if targets[i] < max_games]
                if not available:
                    break
                i = min(available, key=lambda x: (targets[x], (x - j) % len(pairings)))
                targets[i] += 1
            print(f"第一波後剩餘 {remaining:.1f} 秒；依實測每局 {cost:.1f} 秒，"
                  f"預計再跑 {sum(targets) - sum(len(x) for x in results)} 局。", flush=True)
            next_rep = [len(rows) for rows in results]
            # 保持至多 workers 個待執行任務，依目前局數輪流補齊，避免某組獨占預算。
            while time.monotonic() < work_deadline:
                while len(pending) < workers:
                    available = [i for i in active if next_rep[i] < targets[i]]
                    if not available:
                        break
                    i = min(available, key=lambda x: (next_rep[x], x))
                    predicted = results[i][-1]["elapsed_sec"]
                    if time.monotonic() + min(predicted, cost) * 0.8 > work_deadline:
                        targets[i] = next_rep[i]
                        continue
                    game_seed = seed + 1000003 * i + 9973 * next_rep[i]
                    future = executor.submit(_play_fixed, _task(i, pairings[i], game, game_seed))
                    pending[future] = i
                    next_rep[i] += 1
                if not pending:
                    break
                done, _ = wait(pending, timeout=max(0.0, work_deadline - time.monotonic()),
                               return_when=FIRST_COMPLETED)
                for future in done:
                    i = pending.pop(future)
                    results[i].append(future.result())
                    actual_games += 1
                    if actual_games % 20 == 0:
                        print(f"追加完成 {actual_games} 局，剩餘 {max(0.0, work_deadline - time.monotonic()):.1f} 秒", flush=True)
            if pending:
                timed_out = True
        if timed_out:
            for future in list(pending):
                if future.done() and not future.cancelled():
                    try:
                        result = future.result()
                    except Exception:
                        continue
                    results[pending[future]].append(result)
                    actual_games += 1
            pending.clear()
            _stop_pool(executor)
        else:
            executor.shutdown(wait=True)
    except BaseException:
        _stop_pool(executor)
        raise
    return results, deterministic, probe_games, actual_games, timed_out


def _fmt_pct(value):
    return "—" if value is None else f"{max(0.0, 100.0 * value):.1f}%"   # Wilson 下界的 -0.0 印成 0.0


def _summary_rows(results, pairings, deterministic, probe_games):
    rows = []
    for i, pairing in enumerate(pairings):
        rs = results[i]
        n = len(rs)
        wins = sum(r["winner"] == pairing.role for r in rs)
        rate = wins / n if n else None
        ci = list(wilson(wins, n)) if n else [None, None]
        outcomes = dict(sorted(Counter(r["outcome"] for r in rs).items()))
        ms_key = f"act_ms_{pairing.role}"
        avg_ms = float(np.mean([r[ms_key] for r in rs])) if rs else None
        rows.append({"our_role": pairing.role, "our_agent": pairing.our_agent,
                     "opponent": pairing.opponent, "wins": wins, "n_games": n,
                     "n_simulated": n + probe_games[i], "probe_games": probe_games[i],
                     "win_rate": rate, "ci95": ci, "outcomes": outcomes,
                     "avg_decision_ms": avg_ms, "deterministic": deterministic[i],
                     "avg_game_sec": float(np.mean([r["elapsed_sec"] for r in rs])) if rs else None})
    return rows


def _certificates(results, pairings):
    counts = {i: [0, 0] for i in range(1, 7)}
    for pairing, rs in zip(pairings, results):
        if pairing.role != "evader":
            continue
        for result in rs:
            for info in result.get("info_evader") or []:
                round_num = info.get("round")
                if round_num in counts and "certificate" in info:
                    counts[round_num][1] += 1
                    counts[round_num][0] += bool(info["certificate"])
    return [{"round": i, "certified": a, "n_rounds": n,
             "rate": a / n if n else None} for i, (a, n) in counts.items()]


def _recommend(rows, initial=None):
    feats = (initial or {}).get("zone_features") or {}
    if feats.get("reachable") is False:
        return {"role": "pursuer", "text": "建議選：追方；躲方 6 發全推也到不了安全空域（必定 sma_out），不必看勝率表",
                "pursuer_vs_safe_rate": rows[0]["win_rate"], "evader_vs_capture_rate": rows[3]["win_rate"],
                "all_pursuer_avg_rate": None, "all_evader_avg_rate": None, "override": "zone_unreachable"}
    p = rows[0]["win_rate"]
    e = rows[3]["win_rate"]
    avg_p = float(np.mean([r["win_rate"] for r in rows[:3] if r["win_rate"] is not None])) \
        if any(r["win_rate"] is not None for r in rows[:3]) else None
    avg_e = float(np.mean([r["win_rate"] for r in rows[3:] if r["win_rate"] is not None])) \
        if any(r["win_rate"] is not None for r in rows[3:]) else None
    if p is None or e is None:
        role, label = "unknown", "資料不足，請增加時間預算再評估"
    elif abs(p - e) >= 0.10:
        role, label = ("pursuer", "追方") if p > e else ("evader", "躲方")
    elif avg_p is None or avg_e is None or abs(avg_p - avg_e) < 0.05:
        role, label = "tie", "差不多，依隊伍熟練度選"
    else:
        role, label = ("pursuer", "追方") if avg_p > avg_e else ("evader", "躲方")
    text = (f"建議選：{label}；我方當追方 vs 最強對手（safe_evader）勝率 {_fmt_pct(p)}、"
            f"當躲方 vs 最強對手（capture_pursuer）勝率 {_fmt_pct(e)}")
    return {"role": role, "text": text, "pursuer_vs_safe_rate": p,
            "evader_vs_capture_rate": e, "all_pursuer_avg_rate": avg_p, "all_evader_avg_rate": avg_e}


def _print_report(report):
    initial = report["initial"]
    zone = initial["safe_sma_km"]
    print("\n題目摘要")
    print(f"初始距離 {initial['distance_km']:.1f} km；追方高度/近地點 "
          f"{initial['pursuer']['altitude_km']:.1f}/{initial['pursuer']['perigee_alt_km']:.1f} km；"
          f"躲方高度/近地點 {initial['evader']['altitude_km']:.1f}/{initial['evader']['perigee_alt_km']:.1f} km")
    if zone is None:
        zone_text = "無"
    else:
        offset = initial["zone_offset_burns"]
        zone_text = (f"[{zone[0]:.1f}, {zone[1]:.1f}] km；中心偏移約 "
                     + (f"{offset:.2f} 發容量" if offset is not None else "無法估算（半長軸或單發容量不適用）"))
    a_text = f"{initial['evader_sma_km']:.1f} km" if initial["evader_sma_km"] is not None else "非有限"
    print(f"躲方初始 a {a_text}；安全空域 {zone_text}")
    print(f"τ* {initial['tau_star_sec']:.1f} 秒；ΔV_lim·T_round {initial['dv_window_km']:.1f} km")
    feats = initial.get("zone_features") or {}
    if feats.get("flags"):
        print("題目特徵（安全空域對抗，E29）：")
        for flag in feats["flags"]:
            print(f"  - {flag}")
    print("\n| 我方 | 對手 | 我方勝率（Wilson 95%） | 局數 | 結局分布 | 平均決策 ms | 備註 |")
    print("|---|---|---:|---:|---|---:|---|")
    for row in report["pairings"]:
        label = "追方" if row["our_role"] == "pursuer" else "躲方"
        ci = row["ci95"]
        rate = _fmt_pct(row["win_rate"])
        interval = f" [{_fmt_pct(ci[0])}, {_fmt_pct(ci[1])}]" if ci[0] is not None else ""
        outcomes = "、".join(f"{k}:{v}" for k, v in row["outcomes"].items()) or "—"
        ms = f"{row['avg_decision_ms']:.1f}" if row["avg_decision_ms"] is not None else "—"
        note = "確定性（另 1 局驗證）" if row["deterministic"] else ""
        print(f"| {label} {row['our_agent']} | {row['opponent']} | {rate}{interval} | "
              f"{row['n_games']} | {outcomes} | {ms} | {note} |")
    print("\n安全證書（我方躲方）")
    print("| 回合 | 成立 / 總數 | 比例 |")
    print("|---:|---:|---:|")
    for row in report["certificate_by_round"]:
        print(f"| {row['round']} | {row['certified']} / {row['n_rounds']} | {_fmt_pct(row['rate'])} |")
    print(f"\n{report['recommendation']['text']}")
    print(f"實際執行 {report['total_games']} 局，牆鐘 {report['elapsed_sec']:.1f} 秒。")
    if report["timed_out"]:
        print("時間預算已到；未完成的局數未計入勝率。")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("initial", help="雙方初始 r_km/v_kms 或 elements；epoch 可不同，單位為 km、km/s")
    parser.add_argument("--rules", required=True, help="主辦公告的規則 JSON（turn_mode 必須是 simultaneous）")
    parser.add_argument("--budget-sec", type=float, default=150.0, help="總牆鐘上限，含 JIT 暖機（預設 150）")
    parser.add_argument("--workers", type=int, default=4, help="平行行程數（預設 4）")
    parser.add_argument("--fast", action="store_true", help="safe_evader 與 capture_pursuer 改用快速版")
    parser.add_argument("--seed", type=int, default=0, help="種子起點（預設 0）")
    parser.add_argument("--max-games", type=int, default=40, help="每組最多計入幾局（預設 40）")
    parser.add_argument("--json", dest="json_path", help="另外將題目、勝率、證書與建議寫為 JSON")
    args = parser.parse_args(argv)
    try:
        if args.budget_sec <= 0 or not math.isfinite(args.budget_sec):
            raise ValueError("--budget-sec 要是大於 0 的有限秒數")
        if args.workers < 1:
            raise ValueError("--workers 至少為 1")
        if args.max_games < 1:
            raise ValueError("--max-games 至少為 1")
        if args.seed < 0:
            raise ValueError("--seed 必須是非負整數")
        game, aligned = _load_inputs(args.initial, args.rules)
        initial = _initial_summary(game, aligned)
        warnings = []
        if game.rules.safe_sma_km is None:
            warnings.append("沒有安全空域條件；撐完回合即算躲方勝")
            print(f"警告：{warnings[-1]}", file=sys.stderr)
        pairings = _pairings(args.fast)
        results, deterministic, probe_games, actual_games, timed_out = _simulate(
            game, pairings, args.budget_sec, args.workers, args.max_games, args.seed)
        rows = _summary_rows(results, pairings, deterministic, probe_games)
        report = {"initial": initial,
                  "settings": {"budget_sec": args.budget_sec, "workers": args.workers,
                               "fast": args.fast, "seed": args.seed, "max_games": args.max_games},
                  "pairings": rows, "certificate_by_round": _certificates(results, pairings),
                  "recommendation": _recommend(rows, initial), "total_games": actual_games,
                  "elapsed_sec": time.monotonic() - START_MONOTONIC,
                  "timed_out": timed_out, "warnings": warnings}
        _print_report(report)
        if args.json_path:
            try:
                with open(args.json_path, "w", encoding="utf-8") as f:
                    json.dump(report, f, ensure_ascii=False, indent=2, allow_nan=False)
                    f.write("\n")
            except OSError as exc:
                raise ValueError(f"無法寫入 JSON {args.json_path!r}：{exc}；請確認資料夾存在且可寫") from exc
            print(f"→ {args.json_path}")
        return 0
    except (ValueError, RuntimeError, KeyError, TypeError) as exc:
        print(f"錯誤：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
