"""太空船參數／曆元敏感度：固定機動序列的單窗口誤差及整場開迴路重播。

--dry-run 只寫腳本、計畫、JSON 與 Markdown，不檢查或啟動 GMAT。
E22/E26 舊報告沒有可重播向量；--generate-record 用相同規則／幾何／seed／策略重跑純引擎，
不聲稱重現當時每回合以 GMAT 重設狀態的數值。新彩排可用 --record-out 保存真實窗口起點。
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from runtime_threads import limit_blas_threads

limit_blas_threads()

import numpy as np

from game.rules import Rules, SIDES
from tools.gmat_verify import (DEFAULT_EPOCH_TAI_MJD, FULL_SPACECRAFT, GMAT_CONSOLE, _burns,
                               _read_rows, analyze_dense, earth_gate_lines, game_to_script,
                               instrument_dense_script, spacecraft_parameters, validate_dense_reports)

RECORD_SCHEMA = "odc_gmat_replay_v1"
ROOT = Path(__file__).resolve().parents[1]


def _json_default(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"不能寫成 JSON：{type(value).__name__}")


def _write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False,
                               default=_json_default) + "\n", encoding="utf-8")


def save_record(game, path, *, states_before, source):
    """存完整 Game.history 與每回合決策前雙方狀態（可包含 GMAT resync）。"""
    if len(states_before) != len(game.history):
        raise ValueError("每個回合都必須有完整的決策前狀態")
    history = [dict(rec, state_before=state) for rec, state in zip(game.history, states_before)]
    data = {"schema": RECORD_SCHEMA, "source": source, "rules": game.rules.to_dict(),
            "initial": game.initial, "t_max_sec": game.t_max, "outcome": game.outcome,
            "history": history}
    _write_json(path, data)
    return load_record(path)


def load_record(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema") != RECORD_SCHEMA or not data.get("history"):
        raise ValueError(f"需要含 history 的 {RECORD_SCHEMA} 紀錄；Markdown 摘要不能重播")
    rules = Rules.from_dict(data["rules"])
    end = 0.0
    for k, rec in enumerate(data["history"]):
        t0, duration = float(rec["t"]), float(rec["coast_sec"])
        if not np.isfinite([t0, duration]).all() or abs(t0-end) > 1e-5 or duration < 0:
            raise ValueError(f"回合 {k} 的時間不連續或不合法")
        if rec["side"] not in SIDES:
            raise ValueError(f"回合 {k} 的 side 不合法")
        for state in (data["initial"], rec["state_before"]):
            for side in SIDES:
                arr = np.asarray(state[side], dtype=float)
                if arr.shape != (2, 3) or not np.isfinite(arr).all():
                    raise ValueError(f"回合 {k} 缺少 {side} 的有限 (r, v) 狀態")
        burns = _burns(rec)
        if not burns or abs(float(burns[0]["t"])-t0) > 1e-6:
            raise ValueError(f"回合 {k} 必須從窗口起點開始（可先放零脈衝）")
        prev = t0
        for burn in burns:
            at = float(burn["t"])
            dv = np.asarray(burn["dv_eci_mps"], dtype=float)
            if (dv.shape != (3,) or not np.isfinite(dv).all() or not np.isfinite(at)
                    or at < prev-1e-6 or at > t0+duration+1e-6
                    or not np.isclose(float(burn["dv_mps"]), np.linalg.norm(dv), atol=1e-6)):
                raise ValueError(f"回合 {k} 的脈衝時間或向量不合法")
            prev = at
        end = t0+duration
    if not np.isfinite(data["t_max_sec"]) or end > data["t_max_sec"]+1e-5:
        raise ValueError("紀錄超出 T_max")
    data["rules"] = rules.to_dict()
    return data


def generate_record(path, preset="e22", max_turns=0):
    """E22 的 ★ 每回合都選 lazy_evader；直接重跑該策略，省去重做全部大腦推演。"""
    from agents import make_agent
    from game.core import Game, take_turn
    from game.scenarios import sample_scenario

    rules_path = ROOT / "configs/rulesets" / ("ranking_like.json" if preset == "e22"
                                             else "ranking_like_2burn.json")
    rules = Rules.from_dict(json.loads(rules_path.read_text()))
    scenario = sample_scenario(np.random.default_rng(0), "near_coplanar")
    game = Game.from_elements(rules, scenario.orbit_pursuer, scenario.orbit_evader)
    agents = {"pursuer": make_agent("rollout_pursuer"), "evader": make_agent("lazy_evader")}
    for agent in agents.values():
        agent.reset(seed=0)
    # E22 在 E25 生存判定修正之前，E26 則已預設開啟；不改呼叫者的環境設定。
    strict = "0" if preset == "e22" else "1"
    old_strict = os.environ.get("ODC_STRICT_SURVIVAL")
    os.environ["ODC_STRICT_SURVIVAL"] = strict
    states_before = []
    try:
        while not game.done and (max_turns <= 0 or game.turn < max_turns):
            states_before.append({side: (game.r(side).copy(), game.v(side).copy()) for side in SIDES})
            take_turn(game, agents[game.mover])
            if game.turn % 10 == 0:
                print(f"純引擎重跑：{game.turn} 回合，t={game.t:.0f} s", flush=True)
    finally:
        if old_strict is None:
            os.environ.pop("ODC_STRICT_SURVIVAL", None)
        else:
            os.environ["ODC_STRICT_SURVIVAL"] = old_strict
    source = {"kind": "engine_rerun", "preset": preset, "scenario": "near_coplanar", "seed": 0,
              "rules_path": str(rules_path.relative_to(ROOT)),
              "pursuer": "rollout_pursuer", "evader": "lazy_evader", "strict_survival": strict == "1",
              "reference_report": ("reports/e22_rehearsal_full_lazy_evader_vs_rollout.md" if preset == "e22"
                                   else "reports/e26_rehearsal_full_lazy_evader_2burn.md"),
              "note": "相同規則、幾何、seed、策略的純引擎新對局；沒有 GMAT resync，非原彩排數值重現。"}
    return save_record(game, path, states_before=states_before, source=source)


def _state(state):
    return {side: tuple(np.asarray(x, dtype=float).copy() for x in state[side]) for side in SIDES}


def engine_window(rules, state, rec):
    """固定已記錄的 ECI 脈衝，不重新決策或裁切；量到同一個窗口末。

    事件不截斷預測，另由軌跡閘門判順序；避免引擎先捕獲就少跑一段而錯比窗口長度。"""
    from physics import EARTH_MU
    from physics.coast import coast_pair

    state = _state(state)
    best, best_t = float(np.linalg.norm(state["pursuer"][0]-state["evader"][0])), float(rec["t"])
    burns = _burns(rec)
    for j, burn in enumerate(burns):
        side = rec["side"]
        state[side][1][:] += np.asarray(burn["dv_eci_mps"], dtype=float)/1000.0
        end = float(burns[j+1]["t"]) if j+1 < len(burns) else float(rec["t"]+rec["coast_sec"])
        duration = end-float(burn["t"])
        if duration <= 0:
            continue
        rp, vp, re, ve, _, _, minimum, at = coast_pair(
            *state["pursuer"], *state["evader"], duration, rules.substep_sec, EARTH_MU,
            rules.gravity_degree, -1.0, -1.0)
        state = {"pursuer": (rp, vp), "evader": (re, ve)}
        if minimum < best:
            best, best_t = float(minimum), float(burn["t"]+at)
    return {"state_after": state, "d_min_km": best, "t_min_sec": best_t}


def default_variants(base_spacecraft=None):
    base = spacecraft_parameters(base_spacecraft)
    variants = [{"name": "baseline", "spacecraft": {}, "epoch_offset_days": 0.0}]
    for key, values in (("DryMass", [float(base["DryMass"])*0.5, float(base["DryMass"])*2]),
                        ("Cd", [1.5, 3.0]), ("Cr", [1.0, 2.0]),
                        ("DragArea", [float(base["DragArea"])*0.5, float(base["DragArea"])*2]),
                        ("SRPArea", [float(base["SRPArea"])*0.5, float(base["SRPArea"])*2])):
        for label, value in zip(("low", "high"), values):
            variants.append({"name": f"{key.lower()}_{label}", "spacecraft": {key: value},
                             "epoch_offset_days": 0.0})
    variants.extend({"name": f"epoch_plus_{days:g}d".replace(".", "p"), "spacecraft": {}, "epoch_offset_days": days}
                    for days in (0.5, 30.0, 180.0))
    return variants


def resolve_variants(specs=None, *, base_spacecraft=None, epoch_tai_mjd=DEFAULT_EPOCH_TAI_MJD):
    """--variants JSON 可替換單因子清單；保留基準並自動附加最壞方向組合。"""
    base = spacecraft_parameters(base_spacecraft)
    if not np.isfinite(epoch_tai_mjd):
        raise ValueError("基準曆元必須是有限數值")
    specs = copy.deepcopy(default_variants(base) if specs is None else specs)
    if not isinstance(specs, list):
        raise ValueError("變體 JSON 必須是物件清單")
    if not any(v["name"] == "baseline" for v in specs):
        specs.insert(0, {"name": "baseline"})
    if not any(v["name"] == "combined_worst" for v in specs):
        specs.append({"name": "combined_worst", "selection": "measured_single_factor_worst",
                      "spacecraft": {"DryMass": float(base["DryMass"])*0.5, "Cd": 3, "Cr": 2,
                                     "DragArea": float(base["DragArea"])*2, "SRPArea": float(base["SRPArea"])*2},
                      "epoch_offset_days": 180.0, "provisional": True})
    out = []
    names = set()
    for spec in specs:
        name = spec["name"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name) or name in names:
            raise ValueError(f"變體名稱不合法或重複：{name}")
        names.add(name)
        overrides = spec.get("spacecraft", {})
        if name == "baseline" and (overrides or spec.get("epoch_offset_days", 0)):
            raise ValueError("baseline 不可覆寫；請用基準太空船參數及基準曆元選項")
        effective = spacecraft_parameters({**base, **overrides})
        shift = float(spec.get("epoch_offset_days", 0))
        if not np.isfinite(shift):
            raise ValueError("曆元偏移必須是有限數值")
        group = (next(iter(overrides)) if len(overrides) == 1 and shift == 0 else
                 ("epoch" if not overrides and shift != 0 else None))
        out.append({**spec, "spacecraft": effective, "epoch_offset_days": shift,
                    "epoch_tai_mjd": float(epoch_tai_mjd+shift), "group": group})
    # 基準先跑、組合最後跑，才能使用單因子實測選方向。
    return sorted(out, key=lambda v: (v["name"] != "baseline", v["name"] == "combined_worst"))


def _open_history(record, rules):
    hist = copy.deepcopy(record["history"])
    if record.get("outcome") == "capture":
        last = hist[-1]
        last["coast_sec"] = max(last["coast_sec"], min(rules.window_sec, record["t_max_sec"]-last["t"]))
    return hist


def build_plan(record, variants, output_dir, console, *, record_path=None):
    rules = Rules.from_dict(record["rules"])
    output_dir = Path(output_dir).resolve()
    # GMAT 的純 ASCII 腳本及單引號字串限制。
    if not str(output_dir).isascii() or any(c in str(output_dir) for c in "'\r\n"):
        raise ValueError("GMAT 輸出目錄必須為 ASCII 且不含單引號或換行")
    # 保留呼叫者提供的 symlink 路徑：Mac 的 GmatConsole 連到 .app 內，但啟動目錄仍須在 bin。
    console = str(Path(console).expanduser().absolute())
    windows = [engine_window(rules, rec["state_before"], rec) for rec in record["history"]]
    hist_open = _open_history(record, rules)
    state, dmin, tmin = _state(record["initial"]), float("inf"), 0.0
    for rec in hist_open:
        pred = engine_window(rules, state, rec)
        state = pred["state_after"]
        if pred["d_min_km"] < dmin:
            dmin, tmin = pred["d_min_km"], pred["t_min_sec"]
    jobs = []
    for variant in variants:
        folder = output_dir / "scripts" / variant["name"]
        folder.mkdir(parents=True, exist_ok=True)
        cases = [("window", k, rec) for k, rec in enumerate(record["history"])] + [("open_loop", None, None)]
        for kind, k, rec in cases:
            label = f"window_{k:03d}" if kind == "window" else "open_loop"
            report, dense, script_path = (folder / f"{label}{ext}" for ext in ("_report.txt", "_dense.txt", ".script"))
            if kind == "window":
                t0 = float(rec["t"])
                shifted = dict(rec, t=0.0, burns=[dict(b, t=float(b["t"])-t0) for b in _burns(rec)])
                snap = SimpleNamespace(rules=rules, initial=_state(rec["state_before"]), history=[shifted])
            else:
                t0 = 0.0
                snap = SimpleNamespace(rules=rules, initial=_state(record["initial"]), history=hist_open)
            script = instrument_dense_script(game_to_script(
                snap, str(report), "ranking_full", str(dense), epoch_offset_sec=t0,
                spacecraft=variant["spacecraft"], epoch_tai_mjd=variant["epoch_tai_mjd"]))
            script_path.write_text(script, encoding="ascii")
            duration = float(snap.history[-1]["t"]+snap.history[-1]["coast_sec"])
            jobs.append({"id": f"{variant['name']}/{label}", "variant": variant["name"], "kind": kind,
                         "turn": k, "script": str(script_path), "report": str(report), "dense": str(dense),
                         "script_sha256": hashlib.sha256(script.encode("ascii")).hexdigest(),
                         "t_offset_sec": t0, "duration_sec": duration,
                         "expected_report_rows": len(snap.history)+1,
                         "capture_times_sec": [t0+float(r["t"]+r["coast_sec"]) for r in snap.history],
                         "command": [console, "--exit", "--run", str(script_path)],
                         "cwd": str(Path(console).parent)})
    n, nv = len(windows), len(variants)
    plan = {"schema": "odc_gmat_sensitivity_v1", "record_path": str(Path(record_path).resolve()) if record_path else None,
            "source": record.get("source", {}), "rules": record["rules"], "variants": variants,
            "n_turns": n, "n_variants": nv, "gmat_calls": len(jobs),
            "runtime_estimate_sec": {"startup_per_call": 0.7*len(jobs), "per_replayed_turn": 0.7*nv*(n+n)},
            "engine_windows": windows, "engine_open_loop": {"d_min_km": dmin, "t_min_sec": tmin},
            "open_loop_extends_last_capture_window": hist_open[-1]["coast_sec"] > record["history"][-1]["coast_sec"],
            "jobs": jobs}
    _write_json(output_dir / "plan.json", plan)
    return plan


def _measure_job(job, plan):
    rows, dense = _read_rows(job["report"]), _read_rows(job["dense"])
    validate_dense_reports(rows, dense, expected_rows=job["expected_report_rows"], duration_sec=job["duration_sec"])
    dense[:, 0] += job["t_offset_sec"]
    gate = analyze_dense(dense, plan["rules"]["capture_radius_km"], rules=Rules.from_dict(plan["rules"]),
                          capture_times_sec=job["capture_times_sec"])
    out = {"status": "completed", "gate": gate}
    if job["kind"] == "window":
        pred = plan["engine_windows"][job["turn"]]
        out.update({"dpos_pursuer_km": float(np.linalg.norm(rows[-1, 1:4]-pred["state_after"]["pursuer"][0])),
                    "dpos_evader_km": float(np.linalg.norm(rows[-1, 7:10]-pred["state_after"]["evader"][0])),
                    "engine_d_min_km": pred["d_min_km"], "gmat_d_min_km": gate["d_min_km"],
                    "d_min_error_km": gate["d_min_km"]-pred["d_min_km"]})
    else:
        out.update({"engine_d_min_km": plan["engine_open_loop"]["d_min_km"], "d_min_km": gate["d_min_km"],
                    "d_min_error_km": gate["d_min_km"]-plan["engine_open_loop"]["d_min_km"],
                    "entered_capture_sphere": gate["t_enter_capture_sec"] is not None,
                    "captured": gate["t_capture_sec"] is not None, "crashed": not gate["earth_safe"]})
    return out


def execute_job(job, plan, *, timeout_sec=600, resume=False):
    """保留實際執行檔及輸出；重跑前刪舊報表，resume 只採用相同腳本的成功紀錄。"""
    marker = Path(job["script"]).with_suffix(".run.json")
    if resume and marker.exists():
        old = json.loads(marker.read_text())
        if old.get("script_sha256") == job["script_sha256"] and old.get("status") == "completed":
            try:
                return {**_measure_job(job, plan), "resumed": True, "elapsed_sec": old["elapsed_sec"]}
            except (OSError, ValueError):
                pass
    for path in (job["report"], job["dense"]):
        Path(path).unlink(missing_ok=True)
    start = time.perf_counter()
    try:
        res = subprocess.run(job["command"], cwd=job["cwd"], capture_output=True, text=True, timeout=timeout_sec)
        Path(job["script"]).with_suffix(".stdout.txt").write_text(res.stdout or "", encoding="utf-8")
        Path(job["script"]).with_suffix(".stderr.txt").write_text(res.stderr or "", encoding="utf-8")
        if res.returncode != 0:
            raise RuntimeError(f"GMAT exit {res.returncode}；詳見 stdout/stderr")
        out = _measure_job(job, plan)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        if isinstance(exc, subprocess.TimeoutExpired):
            for label, value in (("stdout", exc.stdout), ("stderr", exc.stderr)):
                if isinstance(value, bytes):
                    value = value.decode("utf-8", errors="replace")
                Path(job["script"]).with_suffix(f".{label}.txt").write_text(value or "", encoding="utf-8")
        out = {"status": "failed", "error": str(exc)}
    out["elapsed_sec"] = time.perf_counter()-start
    _write_json(marker, {**out, "script_sha256": job["script_sha256"]})
    return out


def summarize_variant(variant, jobs, measurements):
    own = [j for j in jobs if j["variant"] == variant["name"]]
    windows = [measurements[j["id"]] for j in own if j["kind"] == "window"
               and measurements.get(j["id"], {}).get("status") == "completed"]
    endpoint = [max(w["dpos_pursuer_km"], w["dpos_evader_km"]) for w in windows]
    mins = [abs(w["d_min_error_km"]) for w in windows]
    replay = next((measurements.get(j["id"]) for j in own if j["kind"] == "open_loop"), None)
    return {"variant": variant["name"], "windows_completed": len(windows),
            "windows_expected": sum(j["kind"] == "window" for j in own),
            "max_endpoint_error_km": max(endpoint) if endpoint else None,
            "median_endpoint_error_km": float(np.median(endpoint)) if endpoint else None,
            "max_abs_d_min_error_km": max(mins) if mins else None,
            "median_abs_d_min_error_km": float(np.median(mins)) if mins else None,
            "open_loop": replay,
            "failed_jobs": [j["id"] for j in own if measurements.get(j["id"], {}).get("status") == "failed"]}


def measured_combination(variants, summaries, base_epoch_tai_mjd):
    """各單因子以單窗口最大末位置誤差排序，再以最近距離誤差破同分；不宣稱全域最壞。"""
    combined = copy.deepcopy(next(v for v in variants if v["name"] == "baseline"))
    combined.update(name="combined_worst", provisional=False, selection="measured_single_factor_worst", selected={})
    for group in (*FULL_SPACECRAFT, "epoch"):
        candidates = [v for v in variants if v.get("group") == group]
        if not candidates:
            continue
        if any(summaries[v["name"]]["windows_completed"] != summaries[v["name"]]["windows_expected"]
               or summaries[v["name"]]["max_endpoint_error_km"] is None
               for v in candidates):
            raise ValueError("單因子掃描有失敗，不能選實測最壞方向")
        picked = max(candidates, key=lambda v: (summaries[v["name"]]["max_endpoint_error_km"],
                                                summaries[v["name"]]["max_abs_d_min_error_km"]))
        combined["selected"][group] = picked["name"]
        if group == "epoch":
            combined["epoch_offset_days"] = picked["epoch_offset_days"]
            combined["epoch_tai_mjd"] = base_epoch_tai_mjd+picked["epoch_offset_days"]
        else:
            combined["spacecraft"][group] = picked["spacecraft"][group]
    return combined


def write_results(output_dir, plan, measurements, *, dry_run, run_command):
    summaries = [summarize_variant(v, plan["jobs"], measurements) for v in plan["variants"]]
    out = {"dry_run": dry_run, "gmat_executed": sum(not m.get("resumed", False) for m in measurements.values()),
           "gmat_resumed": sum(m.get("resumed", False) for m in measurements.values()),
           "gmat_calls_planned": plan["gmat_calls"],
           "source": plan["source"], "variants": plan["variants"], "summaries": summaries,
           "measurements": measurements, "run_command": run_command}
    _write_json(Path(output_dir) / "results.json", out)
    estimate = plan["runtime_estimate_sec"]
    lines = ["# GMAT 太空船參數／曆元敏感度", "",
             f"- 狀態：{'dry-run，未執行 GMAT' if dry_run else 'GMAT 實測'}；{plan['n_turns']} 回合、"
             f"{plan['n_variants']} 變體、預計 {plan['gmat_calls']} 次 GMAT 呼叫。",
             f"- 紀錄來源：{plan['source'].get('note', plan['source'].get('kind', '外部紀錄'))}",
             f"- 依 E18/E22 每窗口約 0.7 s，估計約 {estimate['startup_per_call']/60:.1f}–"
             f"{estimate['per_replayed_turn']/60:.1f} 分鐘；開迴路按整場窗口數保守估計，未含 Python 分析與異常積分。",
             "- 單窗口：每回合從紀錄內該回合的雙方狀態重起，固定相同機動及時長；不累積前回合誤差。",
             "- 整場：從初始狀態固定重播同一串機動，不重設狀態；代表誤差累積的上界情境。",
             "- 最近距離為完整輸出的幾何量；捕獲成立與撞地依事件先後另判，捕獲後觸地不算撞地。",
             "- 自動組合：單因子實測後各自選單窗口最大末位置誤差方向（同分比最近距離誤差），非全域最壞搜尋。",
             "- dry-run 的 combined_worst 是高攝動預覽（小質量、大係數／面積、+180 天）；實跑會依單因子結果重寫。",
             f"- 開迴路捕獲末窗口補滿：{plan['open_loop_extends_last_capture_window']}（同 gmat_truth；撞地窗口不補）。", "",
             "| 變體 | 質量 kg | Cd | Cr | 阻力面積 m² | SRP 面積 m² | 曆元偏移 天 |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for v in plan["variants"]:
        p = v["spacecraft"]
        lines.append(f"| {v['name']} | {p['DryMass']} | {p['Cd']} | {p['Cr']} | {p['DragArea']} | {p['SRPArea']} | {v['epoch_offset_days']:g} |")
    lines += ["", "| 變體 | 成功窗口 | 末位置誤差 中位／最大 km | 最近距離絕對誤差最大 km | 開迴路最近 km | 進球／捕獲成立／撞地 |",
              "|---|---:|---:|---:|---:|---|"]

    def fmt(value):
        return "待測" if value is None else f"{value:.6f}"

    details = []
    for s in summaries:
        replay = s["open_loop"] or {}
        status = (f"{replay['entered_capture_sphere']}／{replay['captured']}／{replay['crashed']}"
                  if replay.get("status") == "completed" else replay.get("status", "待測"))
        if replay.get("crashed"):
            status = "**【撞地】" + status + "**"
        lines.append(f"| {s['variant']} | {s['windows_completed']} | {fmt(s['median_endpoint_error_km'])}／"
                     f"{fmt(s['max_endpoint_error_km'])} | {fmt(s['max_abs_d_min_error_km'])} | "
                     f"{fmt(replay.get('d_min_km'))} | {status} |")
        if replay.get("status") == "completed":
            details.extend(["", f"`{s['variant']}` 開迴路：", *["- " + line for line in earth_gate_lines(replay["gate"])], ""])
    lines.extend(details)
    failures = [(job, m["error"]) for job, m in measurements.items() if m["status"] == "failed"]
    if failures:
        lines.extend(["", *[f"- **失敗** `{job}`：{error}" for job, error in failures]])
    lines.extend(["", "沙盒外執行命令：", "", "```sh", run_command, "```", "",
                  "逐窗口數值、雙方最低半徑及事件順序見 results.json；全部實際命令、腳本路徑及 SHA-256 見 plan.json。"])
    Path(output_dir, "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument("--record", help="新格式的彩排／純引擎重跑紀錄 JSON")
    source.add_argument("--generate-record", help="先以引擎重跑 E22/E26 策略並保存紀錄 JSON")
    ap.add_argument("--preset", choices=("e22", "e26"), default="e22")
    ap.add_argument("--max-turns", type=int, default=0, help="產生紀錄時只跑前 N 回合；0 = 整場")
    ap.add_argument("--output-dir", default="runs/gmat_sensitivity")
    ap.add_argument("--variants", help="自訂變體 JSON 清單；欄位 name、spacecraft、epoch_offset_days")
    ap.add_argument("--spacecraft-json", help="基準共用太空船參數 JSON（可只改部分欄位）")
    ap.add_argument("--epoch-tai-mjd", type=float, default=DEFAULT_EPOCH_TAI_MJD)
    ap.add_argument("--gmat-console", default=GMAT_CONSOLE)
    ap.add_argument("--timeout-sec", type=float, default=600)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", action="store_true", help="採用相同腳本且報表完整的成功呼叫")
    args = ap.parse_args(argv)
    if args.max_turns < 0 or not np.isfinite(args.timeout_sec) or args.timeout_sec <= 0:
        ap.error("max-turns 不可為負，timeout-sec 必須為有限正數")
    path = args.record or args.generate_record
    record = load_record(path) if args.record else generate_record(path, args.preset, args.max_turns)
    base = json.loads(Path(args.spacecraft_json).read_text()) if args.spacecraft_json else None
    specs = json.loads(Path(args.variants).read_text()) if args.variants else None
    variants = resolve_variants(specs, base_spacecraft=base, epoch_tai_mjd=args.epoch_tai_mjd)
    plan = build_plan(record, variants, args.output_dir, args.gmat_console, record_path=path)
    command = [str(ROOT / ".venv/bin/python"), str(Path(__file__).resolve()), "--record", str(Path(path).resolve()),
               "--output-dir", str(Path(args.output_dir).resolve()), "--gmat-console", str(Path(args.gmat_console).expanduser().absolute()),
               "--epoch-tai-mjd", str(args.epoch_tai_mjd), "--timeout-sec", str(args.timeout_sec), "--resume"]
    for flag, value in (("--variants", args.variants), ("--spacecraft-json", args.spacecraft_json)):
        if value:
            command.extend([flag, str(Path(value).resolve())])
    run_command = shlex.join(command)
    measurements = {}
    write_results(args.output_dir, plan, measurements, dry_run=args.dry_run, run_command=run_command)
    print(f"執行計畫：{plan['n_turns']} 回合 × {plan['n_variants']} 變體；預計 GMAT 呼叫 {plan['gmat_calls']} 次", flush=True)
    if not args.dry_run:
        for variant in variants:
            if variant.get("selection") == "measured_single_factor_worst":
                summaries = {v["name"]: summarize_variant(v, plan["jobs"], measurements) for v in variants
                             if v["name"] != "combined_worst"}
                try:
                    combined = measured_combination(variants, summaries, args.epoch_tai_mjd)
                except ValueError as exc:
                    print(f"【組合未執行】{exc}", flush=True)
                    return 1
                variants = [v if v["name"] != "combined_worst" else combined for v in variants]
                plan = build_plan(record, variants, args.output_dir, args.gmat_console, record_path=path)
                variant = combined
                print(f"實測最壞方向組合：{combined['selected']}", flush=True)
            for job in plan["jobs"]:
                if job["variant"] != variant["name"]:
                    continue
                measurements[job["id"]] = execute_job(job, plan, timeout_sec=args.timeout_sec, resume=args.resume)
                if measurements[job["id"]]["status"] == "failed":
                    print(f"【失敗】{job['id']}：{measurements[job['id']]['error']}", flush=True)
            summary = summarize_variant(variant, plan["jobs"], measurements)
            print(f"完成 {variant['name']}：成功窗口 {summary['windows_completed']}/{plan['n_turns']}，"
                  f"末位置最大誤差 {summary['max_endpoint_error_km']} km", flush=True)
            write_results(args.output_dir, plan, measurements, dry_run=False, run_command=run_command)
    print(f"{'dry-run 完成，未啟動 GMAT' if args.dry_run else '掃描結束'}：{Path(args.output_dir).resolve()}/results.md")
    print("沙盒外完整命令：\n" + run_command)
    return int(any(m["status"] == "failed" for m in measurements.values()))


if __name__ == "__main__":
    raise SystemExit(main())
