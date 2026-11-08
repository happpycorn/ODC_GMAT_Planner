"""金／銅牌賽離線 copilot：讀官方狀態、建議同時出手推力、記錄公告與核對提交數字。

使用方式見 ``python final_copilot.py --help``；也可用 ``python copilot.py final ...``。
所有位置、速度分別採 EarthMJ2000Eq 的 km、km/s；提交的 Δv 用 m/s。
每回合先 advise；收到主辦的回合末檔後 announce --state，反推雙方實際 Δv 並記住下一回合起點。
"""
import argparse
import datetime as dt
import hashlib
import json
import math
import os
import string
import sys
import time
from collections import Counter
from pathlib import Path

from runtime_threads import limit_blas_threads

limit_blas_threads()

import numpy as np

from agents import make_agent
from agents.final_common import (dsma_capacity, exact_miss, perigee_alt_km,
                                 round_context, zone_slack)
from agents.final_evader import heuristic_candidates
from game.core import OUTCOME_WINNER, Game, sma_official
from game.dv_recover import elapsed_sec, recover_dv
from game.initial_state import align_initial_states, parse_epoch
from game.official_io import (StateImportError, manual_entry, parse_official_state,
                             read_official_state)
from game.rules import Rules, other
from physics import EARTH_MU, RE_VAL, propagate
from physics.frames import rsw_basis


SIDES = ("pursuer", "evader")
SIDE_LABELS = {"pursuer": "追方", "evader": "逃方"}
OUTCOME_LABELS = {"capture": "攔截", "crash_pursuer": "追方撞地", "crash_evader": "逃方撞地",
                 "escape": "逃方在安全空域內", "sma_out": "逃方在安全空域外", "timeout": "回合用盡"}
DEFAULT_FORMAT_PATH = Path(__file__).resolve().parent / "configs" / "final_format.json"
HEURISTIC_CLASSES = ("away", "normal+", "normal-", "radial+", "radial-", "zone")


def _read_json(path, label):
    try:
        with open(path, encoding="utf-8-sig") as stream:
            return json.load(stream)
    except FileNotFoundError as exc:
        raise ValueError(f"找不到{label}檔案 {str(path)!r}；請確認檔名與目前工作目錄") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label}檔案 {str(path)!r} 不是合法 JSON（第 {exc.lineno} 行、第 {exc.colno} 欄）；"
                         "請檢查逗號與引號") from exc
    except OSError as exc:
        raise ValueError(f"無法讀取{label}檔案 {str(path)!r}：{exc}") from exc


def _plain(value):
    """轉成標準 JSON 可寫的值；無窮大以 null 表示。"""
    if isinstance(value, np.ndarray):
        return _plain(value.tolist())
    if isinstance(value, np.generic):
        return _plain(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _write_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as stream:
            json.dump(_plain(data), stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
    except OSError as exc:
        raise ValueError(f"無法寫入 {str(path)!r}：{exc}；請確認資料夾存在且可寫入") from exc


def _rules_from_path(path):
    raw = _read_json(path, "規則")
    if not isinstance(raw, dict):
        raise ValueError("規則檔頂層要是 JSON 物件；請填 turn_mode、window_sec 與單發上限")
    try:
        rules = Rules.from_dict(dict(raw))
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        raise ValueError(f"規則檔格式錯誤：{exc}；Δv 用 m/s、時間用秒、距離用 km") from exc
    if not rules.simultaneous:
        raise ValueError("規則 turn_mode 必須是 simultaneous；請將公告規則檔改為 simultaneous")
    if rules.max_dv_pursuer_mps <= 0 or rules.max_dv_evader_mps <= 0 or rules.capture_radius_km <= 0:
        raise ValueError("雙方 max_dv_*_mps 與 capture_radius_km 都必須大於 0；請核對公告數字")
    return rules


def _load_format(path):
    config = _read_json(path or DEFAULT_FORMAT_PATH, "提交格式")
    if not isinstance(config, dict):
        raise ValueError("提交格式檔頂層須為 JSON 物件")
    required = {"role_names", "round_base", "decimals", "dv_margin_mps", "template"}
    missing = required - set(config)
    if missing:
        raise ValueError(f"提交格式檔缺欄位 {sorted(missing)}；請參考 configs/final_format.json")
    names = config["role_names"]
    if not isinstance(names, dict) or not all(isinstance(names.get(s), str) and names[s] for s in SIDES):
        raise ValueError("提交格式的 role_names 須填 pursuer 與 evader 的非空名稱")
    if type(config["round_base"]) is not int or config["round_base"] not in (0, 1):
        raise ValueError("提交格式的 round_base 只能是 0 或 1")
    if type(config["decimals"]) is not int or not 2 <= config["decimals"] <= 10:
        raise ValueError("提交格式的 decimals 至少 2、至多 10；規則要求至少小數點後兩位")
    try:
        margin = float(config["dv_margin_mps"])
    except (TypeError, ValueError) as exc:
        raise ValueError("提交格式的 dv_margin_mps 要是 m/s 數字") from exc
    if not math.isfinite(margin) or margin < 0:
        raise ValueError("提交格式的 dv_margin_mps 必須是有限且非負的 m/s 數字")
    template = config["template"]
    if not isinstance(template, str):
        raise ValueError("提交格式的 template 須為文字")
    allowed = {"role", "round", "dvx", "dvy", "dvz"}
    fields = []
    try:
        for _, field, format_spec, conversion in string.Formatter().parse(template):
            if field is None:
                continue
            if field not in allowed or format_spec or conversion:
                raise ValueError(f"template 只允許 {sorted(allowed)} 五個欄位；收到 {field!r}")
            fields.append(field)
    except ValueError as exc:
        raise ValueError(f"提交格式 template 錯誤：{exc}") from exc
    if sorted(fields) != sorted(allowed):
        raise ValueError("提交格式 template 須將 role、round、dvx、dvy、dvz 各填一次")
    return {"role_names": {s: names[s] for s in SIDES}, "round_base": config["round_base"],
            "decimals": config["decimals"], "dv_margin_mps": margin, "template": template}


def _parse_names(value):
    if value is None:
        return None
    if os.path.isfile(value):
        result = _read_json(value, "船名對應")
    elif value.lstrip().startswith("{"):
        try:
            result = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"--names 的 JSON 錯誤：{exc}") from exc
    else:
        result = {}
        for pair in value.split(","):
            key, sep, name = pair.partition("=")
            if not sep or key.strip() not in SIDES or not name.strip():
                raise ValueError("--names 請寫 pursuer=ShipP,evader=ShipE，或給 JSON 檔路徑")
            result[key.strip()] = [name.strip()]
    if not isinstance(result, dict):
        raise ValueError("--names 須是物件，鍵為 pursuer 與 evader")
    return result


def _state_record(parsed):
    entry = {side: {"r_km": np.asarray(parsed[side][0], dtype=float).tolist(),
                    "v_kms": np.asarray(parsed[side][1], dtype=float).tolist()} for side in SIDES}
    epoch = parsed.get("epoch")
    entry["epoch"] = epoch.isoformat() if epoch is not None else None
    entry["t_sec"] = parsed.get("t_sec")
    entry["format"] = parsed.get("format")
    return entry


def _read_state_file(path):
    """同一次讀取取得原始內容與 SHA256，避免反推與重複檔案檢查讀到不同版本。"""
    try:
        raw = Path(path).read_bytes()
        return raw.decode("utf-8-sig"), hashlib.sha256(raw).hexdigest()
    except FileNotFoundError as exc:
        raise ValueError(f"找不到狀態檔 {str(path)!r}；請確認 USB 檔已複製、檔名與目前工作目錄") from exc
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"無法讀取狀態檔 {str(path)!r}：{exc}；請確認檔案是 UTF-8 文字") from exc


def _parse_state(path, names=None, order=None, *, content=None):
    parsed = (read_official_state(path, names=names, order=order) if content is None else
              parse_official_state(content, names=names, order=order))
    notes = list(parsed.get("notes", []))
    epochs = parsed.get("ship_epochs")
    if epochs and epochs.get("pursuer") is not None and epochs.get("evader") is not None:
        spec = {side: {"r_km": np.asarray(parsed[side][0]).tolist(),
                       "v_kms": np.asarray(parsed[side][1]).tolist(),
                       "epoch": epochs[side].isoformat()} for side in SIDES}
        aligned = align_initial_states(spec)
        parsed.update({side: aligned[side] for side in SIDES})
        parsed["epoch"] = aligned["epoch"]
        for side, seconds in aligned["propagated_sec"].items():
            if seconds > 0:
                notes.append(f"{side} 的 epoch 較早，已用二體傳播 {seconds:.3f} 秒對齊")
    elif epochs and any(epochs.get(side) is not None for side in SIDES):
        raise ValueError("只有一艘有 epoch；請讓兩艘都提供 epoch，或都不提供，才能對齊回合起點")
    return _state_record(parsed), notes


def _state_options(session, args):
    """指令列可覆寫本次解析方式，未指定的項目沿用舊 session 的值。"""
    names = _parse_names(args.names) if args.names is not None else session.get("names")
    order = args.order if args.order is not None else session.get("order")
    return names, order


def _used_state(sha256, state, round_no, path):
    return {"sha256": sha256, "epoch": state.get("epoch"), "round": round_no, "path": str(path)}


def _state_from_manual():
    return _state_record(manual_entry())


def _rv(state, side):
    entry = state[side]
    return np.asarray(entry["r_km"], dtype=np.float64), np.asarray(entry["v_kms"], dtype=np.float64)


def _game(session, state, round_no):
    rules = Rules.from_dict(dict(session["rules"]))
    rp, vp = _rv(state, "pursuer")
    re, ve = _rv(state, "evader")
    used = {side: 0.0 for side in SIDES}
    for rec in session["rounds"]:
        if rec["round"] >= round_no:
            break
        announcement = rec.get("announcement")
        if announcement:
            used[session["role"]] += float(np.linalg.norm(announcement.get("our_dv_mps") or rec["submission"]["dv_mps"]))
            used[other(session["role"])] += float(np.linalg.norm(announcement["opponent_dv_mps"]))
    return Game.from_snapshot(rules, rp, vp, re, ve,
                              t=(round_no - 1) * rules.window_sec,
                              round_index=round_no - 1, used=used)


def _round_record(session, round_no):
    for record in session["rounds"]:
        if record["round"] == round_no:
            return record
    record = {"round": round_no}
    session["rounds"].append(record)
    session["rounds"].sort(key=lambda rec: rec["round"])
    return record


def _full_coast_prediction(state, dv_p, dv_e, T):
    """一致性專用：按公告推力傳播完整 T_round，不因模擬事件提早停止。"""
    out = {}
    for side, dv in (("pursuer", dv_p), ("evader", dv_e)):
        r, v = _rv(state, side)
        rr, vv = propagate(EARTH_MU, r, v + np.asarray(dv, dtype=float) / 1000.0, T, 0)
        out[side] = {"r_km": rr.tolist(), "v_kms": vv.tolist()}
    out["epoch"] = None
    out["t_sec"] = None
    out["format"] = "二體預測"
    return out


def _time_offset(start, observed, dv_p, dv_e, T):
    """沿預測軌跡找最接近官方位置的時刻，回傳相對 T_round 的秒數。"""
    from scipy.optimize import minimize_scalar

    initial = {}
    for side, dv in (("pursuer", dv_p), ("evader", dv_e)):
        r, v = _rv(start, side)
        initial[side] = (r, v + np.asarray(dv, dtype=float) / 1000.0)

    def error_at(dt):
        error = 0.0
        for side in SIDES:
            r, v = initial[side]
            rr, _ = propagate(EARTH_MU, r, v, float(dt), 0)
            diff = rr - _rv(observed, side)[0]
            error += float(diff @ diff)
        return error

    span = max(180.0, min(900.0, 0.5 * T))
    answer = minimize_scalar(error_at, bounds=(max(0.0, T - span), T + span), method="bounded",
                             options={"xatol": 0.01})
    return float(answer.x - T), float(answer.fun), error_at(T)


def _compare_states(predicted, observed, trajectory=None):
    pos = {side: float(np.linalg.norm(_rv(predicted, side)[0] - _rv(observed, side)[0])) for side in SIDES}
    vel = {side: float(np.linalg.norm(_rv(predicted, side)[1] - _rv(observed, side)[1])) for side in SIDES}
    worst = max(pos.values())
    status = "通過" if worst < 0.1 else ("警告" if worst <= 5.0 else "疑似錯誤")
    hints = []
    if worst > 5.0:
        for side in SIDES:
            pr, pv = _rv(predicted, side)
            rr, vv = _rv(observed, side)
            if 900 < np.linalg.norm(rr) / max(1.0, np.linalg.norm(pr)) < 1100:
                hints.append(f"{side} 的位置看起來是公尺；請除以 1000 改成 km")
            if 900 < np.linalg.norm(vv) / max(1e-12, np.linalg.norm(pv)) < 1100:
                hints.append(f"{side} 的速度看起來是 m/s；請除以 1000 改成 km/s")
        swapped = sum(float(np.linalg.norm(_rv(predicted, side)[0] - _rv(observed, other(side))[0]))
                      for side in SIDES)
        direct = sum(pos.values())
        if swapped < 0.3 * direct:
            hints.append("追方與逃方可能對調：對調後的雙方位置差明顯變小；請核對船名對應")
        if trajectory is not None:
            dt, best_err, base_err = _time_offset(trajectory["start_state"], observed,
                                                  trajectory["dv_p_mps"], trajectory["dv_e_mps"],
                                                  trajectory["T_sec"])
            if abs(dt) >= 2.0 and best_err < 0.2 * base_err:
                hints.append(f"時間可能相差 {dt:+.1f} 秒；請核對 epoch、ElapsedSecs 與回合起點／終點")
        if not hints:
            radial_close = all(abs(np.linalg.norm(_rv(predicted, side)[0]) -
                                   np.linalg.norm(_rv(observed, side)[0])) < 2.0 for side in SIDES)
            if radial_close:
                hints.append("|r| 接近但方向差很多：可能是 EarthFixed 未轉 EarthMJ2000Eq；請先轉換座標系")
        if not hints:
            hints.append("請核對雙方船名、km／km/s、EarthMJ2000Eq、epoch 與公告的實際 Δv")
    elif status == "警告":
        hints.append("可能是狀態檔四捨五入或力學模型差；請核對 epoch 與公告數值")
    return {"status": status, "position_diff_km": pos, "velocity_diff_kms": vel, "hints": hints}


def _print_consistency(result):
    print(f"一致性檢查：{result['status']}（追方位置差 {result['position_diff_km']['pursuer']:.6f} km、"
          f"速度差 {result['velocity_diff_kms']['pursuer']:.8f} km/s；逃方位置差 "
          f"{result['position_diff_km']['evader']:.6f} km、速度差 {result['velocity_diff_kms']['evader']:.8f} km/s）")
    for hint in result["hints"]:
        print(f"  提示：{hint}")


def _check_against_prediction(session, observed):
    predicted = session.get("predicted_state")
    if not predicted:
        return None
    previous = next((row for row in session["rounds"] if row["round"] == session["round"] - 1), None)
    trajectory = previous.get("actual_trajectory") if previous else None
    result = _compare_states(predicted, observed, trajectory)
    _print_consistency(result)
    if previous is not None:
        previous["consistency"] = result
    return result


def _round_dv(raw, cap, config):
    """先等比例限制，再把將要列印的三個字串重新解析為浮點數。"""
    dv = np.asarray(raw, dtype=np.float64).reshape(3).copy()
    limit = min(float(cap), float(config["dv_limit_mps"]) - config["dv_margin_mps"])
    if limit < 0:
        raise ValueError("dv_margin_mps 大於單發上限；請改小 configs/final_format.json 的餘裕")
    mag = float(np.linalg.norm(dv))
    if mag > limit and mag > 0.0:
        dv *= limit / mag
    decimals = config["decimals"]
    strings = [f"{value:.{decimals}f}" for value in dv]
    printed = np.array([float(value) for value in strings], dtype=np.float64)
    if float(np.linalg.norm(printed)) > limit + 1e-12:
        # 四捨五入讓大小超過上限：在三軸各取無條件捨去／進位的 8 種組合裡，挑不超過上限且最接近原值的。
        step = 10.0 ** (-decimals)
        lows = np.floor(dv / step) * step
        best = None
        for mask in range(8):
            cand = lows + step * np.array([(mask >> k) & 1 for k in range(3)], dtype=np.float64)
            cand_strings = [f"{value:.{decimals}f}" for value in cand]
            cand_printed = np.array([float(value) for value in cand_strings], dtype=np.float64)
            if float(np.linalg.norm(cand_printed)) <= limit + 1e-12:
                err = float(np.linalg.norm(cand_printed - dv))
                if best is None or err < best[0]:
                    best = (err, cand_printed, cand_strings)
        if best is None:
            raise ValueError("四捨五入後仍超過單發上限；請增加 configs/final_format.json 的 decimals")
        printed, strings = best[1], best[2]
    return dv, printed, strings


def _recheck(g, side, raw_scaled, printed, agent, model, config):
    limit = g.rules.max_dv(side) - config["dv_margin_mps"]
    size = float(np.linalg.norm(printed))
    checks = {"dv_limit": size <= limit + 1e-9 and size <= g.burn_cap(side) + 1e-9,
              "perigee": perigee_alt_km(g.r(side), g.v(side) + printed / 1000.0) >= agent.perigee_margin_km}
    info = {"dv_mps": size, "limit_mps": limit,
            "perigee_after_km": float(perigee_alt_km(g.r(side), g.v(side) + printed / 1000.0))}
    if side == "evader":
        ctx = round_context(g)
        miss_raw, _, _ = exact_miss(g.r("pursuer"), g.v("pursuer"), ctx["D_p"],
                                    g.r("evader"), g.v("evader") + raw_scaled / 1000.0,
                                    ctx["T"], g.mu, grid_sec=agent.grid_sec)
        miss_printed, _, _ = exact_miss(g.r("pursuer"), g.v("pursuer"), ctx["D_p"],
                                        g.r("evader"), g.v("evader") + printed / 1000.0,
                                        ctx["T"], g.mu, grid_sec=agent.grid_sec)
        raw_margin = float(miss_raw - ctx["R_cap"])
        printed_margin = float(miss_printed - ctx["R_cap"])
        checks["certificate"] = (printed_margin > agent.safety_km and
                                  (raw_margin > agent.safety_km) == (printed_margin > agent.safety_km))
        info.update({"raw_exact_margin_km": raw_margin, "exact_margin_km": printed_margin,
                     "safety_km": agent.safety_km})
    else:
        def hit_probability(dv):
            probability = 0.0
            for row in model:
                sim = g.clone()
                sim.play_round(dv, row["dv_eci_mps"])
                probability += float(row["weight"]) * (sim.outcome == "capture")
            return probability

        raw_prob = hit_probability(raw_scaled)
        printed_prob = hit_probability(printed)
        checks["hit_probability"] = abs(raw_prob - printed_prob) < 1e-6
        info.update({"raw_hit_prob": raw_prob, "hit_prob": printed_prob})
    info["checks"] = checks
    info["passed"] = all(checks.values())
    return info


def _best_alternative(g, side, agent, model, config):
    """重驗失敗時找可提交的候選；只有失敗才做較重的搜尋。"""
    if side == "evader":
        rows = agent.evaluate(g.clone())
        options = [row["dv_eci_mps"] for row in sorted(rows, key=lambda row: row["score"], reverse=True)
                   if row["feasible"] and row["safe"]][:20]
    else:
        options = [dv for _, dv in agent._pursuer_candidates(g.clone(), model, round_context(g))][:40]
    config = {**config, "dv_limit_mps": g.rules.max_dv(side)}
    for option in options:
        raw_scaled, printed, strings = _round_dv(option, g.burn_cap(side), config)
        result = _recheck(g, side, raw_scaled, printed, agent, model, config)
        if result["passed"]:
            return raw_scaled, printed, strings, result
    return None


def _format_submission(role, round_no, values, config):
    return config["template"].format(role=config["role_names"][role],
                                      round=round_no + config["round_base"] - 1,
                                      dvx=values[0], dvy=values[1], dvz=values[2])


def _predicted_round(g, our_side, our_dv, opponent_dv):
    sim = g.clone()
    if our_side == "pursuer":
        record = sim.play_round(our_dv, opponent_dv)
    else:
        record = sim.play_round(opponent_dv, our_dv)
    return {"state": {side: {"r_km": sim.r(side).tolist(), "v_kms": sim.v(side).tolist()}
                      for side in SIDES},
            "distance_km": sim.distance(), "outcome": record["outcome"],
            "coast_sec": record["coast_sec"]}


def _prediction_scenarios(g, side, dv, model):
    zero = _predicted_round(g, side, dv, np.zeros(3))
    scenarios = []
    if side == "pursuer":
        representatives = model[:3]
        for row in representatives:
            scenarios.append({"kind": row["kind"], "weight": float(row["weight"]),
                              "opponent_dv_mps": row["dv_eci_mps"],
                              **_predicted_round(g, side, dv, row["dv_eci_mps"])})
    else:
        ctx = round_context(g)
        _, best_dv_kms, tau = exact_miss(g.r("pursuer"), g.v("pursuer"), ctx["D_p"],
                                         g.r("evader"), g.v("evader") + dv / 1000.0,
                                         ctx["T"], g.mu)
        best = best_dv_kms * 1000.0
        scenarios.append({"kind": "追方最佳回應", "weight": 1.0, "opponent_dv_mps": best,
                          "closest_time_sec": float(tau), **_predicted_round(g, side, dv, best)})
    return {"zero_opponent": zero, "representative": scenarios}


def _posterior_weights(preferences):
    """先驗 (1,4,5) 對應 agent 預設 (0.1,0.4,0.5)；公告各加一票。"""
    counts = Counter(preferences)
    zero = 1 + counts["zero"]
    heuristic = 4 + sum(counts[kind] for kind in HEURISTIC_CLASSES)
    safe = 5 + counts["other"]
    total = zero + heuristic + safe
    return {"w_zero": zero / total, "w_heuristic": heuristic / total, "w_safe": safe / total}


def _classify_opponent(g, side, dv):
    actual = np.asarray(dv, dtype=float)
    magnitude = float(np.linalg.norm(actual))
    if magnitude <= 0.05:
        return "zero"
    candidates = heuristic_candidates(g, side)
    matches = []
    for kind, expected, _ in candidates:
        expected_size = float(np.linalg.norm(expected))
        if kind == "zero" or expected_size <= 0:
            continue
        angle = math.degrees(math.acos(float(np.clip(np.dot(actual, expected) /
                                                      (magnitude * expected_size), -1.0, 1.0))))
        size_diff = abs(magnitude - expected_size)
        if angle < 15.0 and size_diff <= max(0.5, 0.1 * expected_size):
            matches.append((angle, size_diff, kind))
    return min(matches)[2] if matches else "other"


def _print_state(parsed):
    print(f"偵測格式：{parsed.get('format') or '手動輸入'}；EarthMJ2000Eq，位置 km、速度 km/s")
    if parsed.get("epoch"):
        print(f"共同 epoch：{parsed['epoch']}")
    if parsed.get("t_sec") is not None:
        print(f"ElapsedSecs：{parsed['t_sec']:.3f} 秒")
    for side in SIDES:
        r, v = _rv(parsed, side)
        print(f"{side}：r={np.array2string(r, precision=9)} km，v={np.array2string(v, precision=9)} km/s")
        print(f"  |r|={np.linalg.norm(r):.6f} km，|v|={np.linalg.norm(v):.9f} km/s，"
              f"高度={np.linalg.norm(r) - RE_VAL:.6f} km，近地點高度={perigee_alt_km(r, v):.3f} km")


def _cmd_new(args):
    rules = _rules_from_path(args.rules)
    names = _parse_names(args.names)
    content, sha256 = _read_state_file(args.initial)
    state, notes = _parse_state(args.initial, names=names, order=args.order, content=content)
    config = _load_format(args.format)
    if config["dv_margin_mps"] >= rules.max_dv(args.role):
        raise ValueError("提交餘裕 dv_margin_mps 不得大於等於我方 ΔV_lim；請修改格式設定檔")
    session = {"version": 1, "rules": rules.to_dict(), "role": args.role,
               "format": config, "round": 1, "initial": state,
               "current_state": state, "predicted_state": None,
               "rounds": [], "opponent_preferences": {}, "names": names, "order": args.order,
               "used_states": [_used_state(sha256, state, 0, args.initial)]}
    _write_json(args.out, session)
    print(f"已建立 session：{args.out}；我方 {config['role_names'][args.role]}，第 1 回合")
    _print_state(state)
    for note in notes:
        print(f"  解析註記：{note}")
    if rules.safe_sma_km is None:
        print("警告：safe_sma_km 為 null；尚無安全空域。請核對公告並更新規則檔後重新 new。")
    if rules.gravity_degree != 0:
        print("警告：安全證書採二體近似；公告若規定純二體，請把 gravity_degree 設為 0。")
    return 0


def _cmd_parse(args):
    state, notes = _parse_state(args.path, names=_parse_names(args.names), order=args.order)
    _print_state(state)
    for note in notes:
        print(f"  解析註記：{note}")
    return 0


def _cmd_manual(args):
    state = _state_from_manual()
    _write_json(args.out, state)
    print(f"已存手動狀態：{args.out}")
    return 0


def _cmd_advise(args):
    session = _read_json(args.session, "session")
    if session.get("finished"):
        finished = session["finished"]
        outcome = OUTCOME_LABELS.get(finished["outcome"], finished["outcome"])
        raise ValueError(f"比賽已在第 {finished['round']} 回合結束（{outcome}）；不用再交。")
    round_no = session["round"]
    rules = Rules.from_dict(dict(session["rules"]))
    if args.round is not None and args.round != round_no:
        raise ValueError(f"session 現在是第 {round_no} 回合，--round 卻是 {args.round}；"
                         "請先 announce 上一回合，或核對 session 檔")
    if round_no > rules.rounds:
        raise ValueError(f"{rules.rounds} 回合已結束；請用 show 查看整場紀錄")
    if args.manual and args.state:
        raise ValueError("--manual 與 --state 只能選一個；請移除其中一個")
    if args.manual:
        state = _state_from_manual()
        notes = []
    elif args.state:
        names, order = _state_options(session, args)
        state, notes = _parse_state(args.state, names=names, order=order)
        session.update(names=names, order=order)
    else:
        state = session["current_state"]
        notes = []
    if args.manual or args.state:
        _check_against_prediction(session, state)
        session["current_state"] = state
    for note in notes:
        print(f"解析註記：{note}")
    g = _game(session, state, round_no)
    if g.done:
        raise ValueError("目前狀態已達終局或在捕獲半徑內；請核對官方狀態與回合數")
    side = session["role"]
    agent_name = ("capture_pursuer" if side == "pursuer" else "safe_evader") + ("_fast" if args.fast else "")
    seed = args.seed if args.seed is not None else round_no
    weights = _posterior_weights(session.get("opponent_preferences", {})) if side == "pursuer" else {}
    agent = make_agent({"name": agent_name, "seed": seed, **weights})
    model = []
    if side == "pursuer":
        original_model = agent._evader_model

        def capture_model(game):
            rows = original_model(game)
            model.extend({"kind": row["kind"], "dv_eci_mps": row["dv_eci_mps"].copy(),
                          "weight": row["weight"]} for row in rows)
            return rows

        agent._evader_model = capture_model
    started = time.perf_counter()
    raw = np.asarray(agent.act(g.clone(), side), dtype=np.float64)
    decide_sec = time.perf_counter() - started
    config = {**session["format"], "dv_limit_mps": rules.max_dv(side)}
    raw_scaled, printed, strings = _round_dv(raw, g.burn_cap(side), config)
    recheck = _recheck(g, side, raw_scaled, printed, agent, model, config)
    if not recheck["passed"]:
        print("！！！ 警告：建議值四捨五入重驗未通過，請先看下列失敗項目 ！！！")
        for name, passed in recheck["checks"].items():
            if not passed:
                print(f"  未通過：{name}")
        alternative = _best_alternative(g, side, agent, model, config)
        if alternative is not None:
            raw_scaled, printed, strings, recheck = alternative
            print("已找到通過重驗的替代提交值；以下提交行使用替代值。")
        else:
            print("找不到通過全部重驗的替代值；請依警告與安全餘量人工判斷，必要時重讀官方狀態。")
    line = _format_submission(side, round_no, strings, config)
    predictions = _prediction_scenarios(g, side, printed, model)
    rec = _round_record(session, round_no)
    rec["start_state"] = state
    rec["distance_km"] = g.distance()
    rec["evader_sma_km"] = sma_official(g.r("evader"), g.v("evader"))
    rec["advice"] = {"agent": agent_name, "seed": seed, "raw_dv_mps": raw,
                     "scaled_dv_mps": raw_scaled, "agent_info": agent.last_info,
                     "decide_sec": decide_sec, "weights": weights, "model": model}
    rec["submission"] = {"dv_mps": printed, "line": line, "recheck": recheck}
    rec["predictions"] = predictions
    _write_json(args.session, session)

    ctx = round_context(g)
    a = sma_official(g.r("evader"), g.v("evader"))
    zone = rules.safe_sma_km
    print(f"第 {round_no}/{rules.rounds} 回合；我方 {session['format']['role_names'][side]}；"
          f"雙方距離 {g.distance():.3f} km")
    print(f"近地點高度：追方 {perigee_alt_km(g.r('pursuer'), g.v('pursuer')):.3f} km、"
          f"逃方 {perigee_alt_km(g.r('evader'), g.v('evader')):.3f} km")
    print(f"逃方 a = {a:.3f} km；安全空域：{f'[{zone[0]:.3f}, {zone[1]:.3f}] km' if zone else '未公告'}")
    if zone is not None:
        up, down = dsma_capacity(g.r("evader"), g.v("evader"), ctx["D_e"])
        slack = zone_slack(a, zone, ctx["burns_left_after"] + 1, up, down)
        one = up if a < zone[0] else down
        distance = max(zone[0] - a, a - zone[1], 0.0)
        need_burns = distance / one if one > 0 and math.isfinite(one) else (0.0 if distance == 0 else math.inf)
        print(f"安全空域容量：還差約 {need_burns:.2f} 發；含本回合剩 {ctx['burns_left_after'] + 1} 發；"
              f"保守餘裕 {slack:.3f} km")
    tau_star = 1000.0 * rules.capture_radius_km / ctx["D_p"] if ctx["D_p"] > 0 else math.inf
    print(f"τ* = {tau_star:.3f} 秒（R_cap / 追方 ΔV_lim）")
    print(f"建議 Δv ECI m/s：{np.array2string(raw, precision=6)}；"
          f"RSW m/s：{np.array2string(rsw_basis(g.r(side), g.v(side)) @ raw, precision=6)}；"
          f"|Δv|={np.linalg.norm(raw):.6f} m/s")
    info = agent.last_info
    if side == "evader":
        print(f"安全證書：{'成立' if info['certificate'] else '未成立'}；"
              f"線性 margin {info['linear_margin_km']:.3f} km；"
              f"非線性 margin {info['exact_margin_km']:.3f} km")
    else:
        print(f"估計命中率 {info['hit_prob']:.2%}；模型最高權重躲方推法：" +
              "、".join(f"{row['kind']} {row['weight']:.1%}" for row in model[:4]))
        print(f"對手偏好用拉普拉斯平滑：先驗 zero/heuristic/safe = 1/4/5 票，"
              f"公告每次加 1 票；目前權重 {weights['w_zero']:.3f}/"
              f"{weights['w_heuristic']:.3f}/{weights['w_safe']:.3f}")
    r, v = g.r(side), g.v(side)
    v_after = v + printed / 1000.0
    print(f"提交值推完：近地點高度 {perigee_alt_km(r, v_after):.3f} km；"
          f"a = {sma_official(r, v_after):.3f} km")
    print(f"重驗：{'通過' if recheck['passed'] else '未通過'}；"
          f"|Δv|={recheck['dv_mps']:.6f} m/s ≤ {recheck['limit_mps']:.6f} m/s；"
          f"近地點 {recheck['perigee_after_km']:.3f} km")
    if side == "evader":
        print(f"  四捨五入前／後非線性 margin：{recheck['raw_exact_margin_km']:.6f} / "
              f"{recheck['exact_margin_km']:.6f} km；安全門檻 {recheck['safety_km']:.3f} km")
    else:
        print(f"  四捨五入前／後完整模型加權命中率：{recheck['raw_hit_prob']:.6f} / "
              f"{recheck['hit_prob']:.6f}")
    print("手寫核對（ECI m/s，注意正負號）：" +
          "  ".join(f"{axis} = {value:+.{config['decimals']}f}" for axis, value in zip("XYZ", printed)))
    print(f"本回合決策 {decide_sec:.3f} 秒；agent={agent_name}；seed={seed}")
    print(f"提交：{line}")
    return 0


def _recovery_hints(start, observed, elapsed, recovery):
    """回推失準時檢查船名對調與常見單位、座標系錯誤。"""
    hints = []
    direct = sum(row["position_residual_km"] for row in recovery.values())
    swapped = sum(recover_dv(*_rv(start, side), *_rv(observed, other(side)), elapsed)
                  ["position_residual_km"] for side in SIDES)
    if swapped < 0.3 * direct:
        hints.append(f"追方與逃方可能對調：對調後回推殘差合計 {swapped:.3f} km，"
                     f"原本 {direct:.3f} km，明顯變小；請核對船名對應或用 --names 修正。")
    for side in SIDES:
        r0, v0 = _rv(start, side)
        r1, v1 = _rv(observed, side)
        if 900 < np.linalg.norm(r1) / max(1.0, np.linalg.norm(r0)) < 1100:
            hints.append(f"{SIDE_LABELS[side]}的位置看起來是公尺；請除以 1000 改成 km。")
        if 900 < np.linalg.norm(v1) / max(1e-12, np.linalg.norm(v0)) < 1100:
            hints.append(f"{SIDE_LABELS[side]}的速度看起來是 m/s；請除以 1000 改成 km/s。")
    if not hints and all(abs(np.linalg.norm(_rv(start, side)[0]) -
                             np.linalg.norm(_rv(observed, side)[0])) < 2.0 for side in SIDES):
        hints.append("|r| 接近但回推方向差很多：可能是 EarthFixed 未轉 EarthMJ2000Eq；請核對座標系。")
    return hints


def _announce_recovered(args, session, rec, rules, observed, notes, sha256, names, order,
                        typed_opponent, typed_our):
    """先完整核對，通過或明確強制採用後才寫回 session。"""
    round_no = session["round"]
    start = rec["start_state"]
    elapsed, source = elapsed_sec(start, observed, rules.window_sec)
    same_positions = all(np.linalg.norm(_rv(start, side)[0] - _rv(observed, side)[0]) < 1e-6
                         for side in SIDES)
    if abs(elapsed) <= 1.0 or (source != "epoch" and same_positions):
        raise ValueError("這是本回合起點的狀態，不是回合末。請放主辦剛發的檔。")
    warnings = []
    if source != "T_round" and abs(elapsed - rules.window_sec) > 1.0:
        warnings.append(f"檔案時間比回合起點晚 {elapsed:.1f} s，但 T_round 是 {rules.window_sec:.1f} s："
                        f"T_round 抄錯，或主辦提早結束本回合（攔截／撞地）？已用 {elapsed:.1f} s 反推。")
    recovery = {side: recover_dv(*_rv(start, side), *_rv(observed, side), elapsed) for side in SIDES}
    actual = {side: np.asarray(recovery[side]["dv_mps"], dtype=float) for side in SIDES}
    problems = []
    for side in SIDES:
        residual = recovery[side]["position_residual_km"]
        size = float(np.linalg.norm(actual[side]))
        label, cap = SIDE_LABELS[side], rules.max_dv(side)
        if residual > 5.0:
            problems.append(f"回推{label}回不到本回合起點（差 {residual:.3f} km）")
        if size > cap + 0.5:
            problems.append(f"{label}反推 Δv {size:.2f} m/s 超過上限 {cap:g} m/s")
    if problems:
        message = "／".join(problems) + ("：這份檔可能不是本回合結束的狀態、船名對調、單位錯，"
                                      "或 T_round／ΔV_lim 抄錯。核對後再放一次；確定要用就加 --force。")
        hints = _recovery_hints(start, observed, elapsed, recovery)
        if not args.force:
            raise ValueError("\n".join([message, *hints]))
        warnings.extend([f"已用 --force 強制寫入。{message}", *hints])
    for side in SIDES:
        row = recovery[side]
        if row["position_residual_km"] > 0.01:
            warnings.append(f"{SIDE_LABELS[side]}回推位置殘差 {row['position_residual_km']:.6f} km，"
                            "超過 0.01 km；請核對檔案精度、時間與力學模型。")
        if row["lambert_diff_mps"] is not None and row["lambert_diff_mps"] > 0.01:
            warnings.append(f"{SIDE_LABELS[side]}的 Lambert 交叉核對差 {row['lambert_diff_mps']:.6f} m/s，"
                            "超過 0.01 m/s；請核對官方狀態。")

    our_side, opponent = session["role"], other(session["role"])
    submitted = np.asarray(rec["submission"]["dv_mps"], dtype=float)
    delta = actual[our_side] - submitted
    difference = float(np.linalg.norm(delta))
    if difference > 0.05:
        axis = int(np.argmax(np.abs(delta)))
        warnings.append(f"主辦執行的我方 Δv 跟提交行差 {difference:.2f} m/s"
                        f"（{'XYZ'[axis]} 軸 {delta[axis]:+.2f} m/s）。"
                        "可能主辦抄錯或手寫錯，馬上找工作人員核對。")
    if np.linalg.norm(actual[our_side]) < 0.01 and np.linalg.norm(submitted) > 0.0:
        warnings.append("主辦當我們沒交（逾時）？馬上找工作人員。")
    if typed_our is not None:
        difference = float(np.linalg.norm(typed_our - actual[our_side]))
        if difference > 0.05:
            warnings.append(f"你打的我方 Δv 跟檔案反推差 {difference:.2f} m/s；以檔案反推值為準。")
    if typed_opponent is not None:
        difference = float(np.linalg.norm(typed_opponent - actual[opponent]))
        if difference > 0.05:
            warnings.append(f"你打的對手 Δv 跟檔案反推差 {difference:.2f} m/s；以檔案反推值為準。")

    g = _game(session, start, round_no)
    classified = _classify_opponent(g, opponent, actual[opponent])
    result = g.play_round(actual["pursuer"], actual["evader"])
    a = float(result["sma_evader_km"])
    zone = rules.safe_sma_km
    round_result = {"min_dist_km": float(result["window_min_dist_km"]),
                    "t_min_sec": float(result["t_window_min"] - result["t"]),
                    "outcome": result["outcome"], "evader_sma_km": a,
                    "in_zone": bool(zone[0] <= a <= zone[1]) if zone is not None else None}
    predicted = _full_coast_prediction(start, actual["pursuer"], actual["evader"], elapsed)
    consistency = _compare_states(predicted, observed)
    rec["announcement"] = {"source": "state", "opponent_dv_mps": actual[opponent],
                           "our_dv_mps": actual[our_side], "typed_opponent_dv_mps": typed_opponent,
                           "typed_our_dv_mps": typed_our, "opponent_class": classified,
                           "dt_sec": elapsed, "dt_source": source, "recovery": recovery,
                           "warnings": warnings, "state_path": str(args.state)}
    rec["round_result"] = round_result
    rec["consistency"] = consistency
    rec["actual_prediction"] = predicted
    rec["actual_trajectory"] = {"start_state": start, "dv_p_mps": actual["pursuer"],
                                "dv_e_mps": actual["evader"], "T_sec": elapsed}
    preferences = Counter(session.get("opponent_preferences", {}))
    preferences[classified] += 1
    session.update(current_state=observed, predicted_state=observed, round=round_no + 1,
                   names=names, order=order, opponent_preferences=dict(preferences))
    session.setdefault("used_states", []).append(_used_state(sha256, observed, round_no, args.state))
    if result["outcome"] is not None:
        session["finished"] = {"outcome": result["outcome"], "winner": OUTCOME_WINNER[result["outcome"]],
                               "round": round_no}
    _write_json(args.session, session)

    print(f"反推：{'警告' if warnings else '通過'}")
    print(f"第 {round_no} 回合；反推時間 {elapsed:.3f} s；時間來源 {source}")
    for side in SIDES:
        size = float(np.linalg.norm(actual[side]))
        full = "；已推滿上限（可能被縮放）" if abs(size - rules.max_dv(side)) <= 0.01 else ""
        numbers = ", ".join(f"{value:.4f}" for value in actual[side])
        print(f"{SIDE_LABELS[side]}實際 Δv = ({numbers}) m/s；|Δv| = {size:.4f} m/s{full}")
        row = recovery[side]
        lambert = (f"{row['lambert_diff_mps']:.6f} m/s" if row["lambert_diff_mps"] is not None else
                   "未交叉核對（超過半週期或無解）")
        print(f"  回推位置殘差 {row['position_residual_km']:.6f} km；Lambert 差 {lambert}")
    print(f"本回合最近距離 {round_result['min_dist_km']:.6f} km；"
          f"發生於回合開始後 {round_result['t_min_sec']:.3f} 秒")
    if start.get("epoch"):
        instant = parse_epoch(start["epoch"]) + dt.timedelta(seconds=round_result["t_min_sec"])
        print(f"最近距離 UTC 時刻：{instant.astimezone(dt.timezone.utc).isoformat()}")
    print(f"是否攔截：{'是' if result['outcome'] == 'capture' else '否'}")
    zone_text = (f"安全空域 [{zone[0]:.3f}, {zone[1]:.3f}] {'內' if round_result['in_zone'] else '外'}"
                 if zone is not None else "安全空域未公告")
    print(f"逃方 a = {a:.6f} km，{zone_text}")
    _print_consistency(consistency)
    for note in notes:
        print(f"解析註記：{note}")
    for warning in warnings:
        print(f"警告：{warning}")
    if session.get("finished"):
        finished = session["finished"]
        print(f"比賽應已結束：{OUTCOME_LABELS[finished['outcome']]}，"
              f"{SIDE_LABELS[finished['winner']]}獲勝（以主辦公告為準）")
    print(f"下一回合：{session['round']}")
    return 0


def _cmd_announce(args):
    if args.state is None and args.opponent_dv is None:
        raise ValueError("請給主辦的回合末狀態檔 --state（建議），或手打對手實際 Δv --opponent-dv X Y Z")
    session = _read_json(args.session, "session")
    if args.state:
        content, sha256 = _read_state_file(args.state)
        for used in session.get("used_states", []):
            if used["sha256"] == sha256:
                raise ValueError(f"這份檔第 {used['round']} 回合已經用過了（{used['path']}）。"
                                 "請放主辦剛發的回合末狀態檔。")
        names, order = _state_options(session, args)
        observed, notes = _parse_state(args.state, names=names, order=order, content=content)
    round_no = session["round"]
    rules = Rules.from_dict(dict(session["rules"]))
    if round_no > rules.rounds:
        raise ValueError("所有回合已公告；請用 show 查看紀錄")
    rec = _round_record(session, round_no)
    if "submission" not in rec or "start_state" not in rec:
        raise ValueError(f"第 {round_no} 回合尚未 advise；請先產生並抄下提交行")
    opp_dv = np.asarray(args.opponent_dv, dtype=float) if args.opponent_dv is not None else None
    if opp_dv is not None and not np.all(np.isfinite(opp_dv)):
        raise ValueError("對手公告 Δv 有非有限數字；請重新輸入三個 ECI m/s 數字")
    official_our = np.asarray(args.our_dv, dtype=float) if args.our_dv is not None else None
    if official_our is not None and not np.all(np.isfinite(official_our)):
        raise ValueError("我方公告 Δv 有非有限數字；請重新輸入三個 ECI m/s 數字")
    if args.state:
        return _announce_recovered(args, session, rec, rules, observed, notes, sha256, names, order,
                                   opp_dv, official_our)
    g = _game(session, rec["start_state"], round_no)
    opponent = other(session["role"])
    submitted = np.asarray(rec["submission"]["dv_mps"], dtype=float)
    classified = _classify_opponent(g, opponent, opp_dv)
    rec["announcement"] = {"opponent_dv_mps": opp_dv, "our_dv_mps": official_our,
                           "opponent_class": classified}
    if official_our is not None and np.linalg.norm(official_our - submitted) > 1e-4:
        print("警告：主辦公告的我方實際 Δv 與提交行不同；可能抄錯或被等比例縮放，請核對手寫抄本。")
    preferences = Counter(session.get("opponent_preferences", {}))
    preferences[classified] += 1
    session["opponent_preferences"] = dict(preferences)
    if session["role"] == "pursuer":
        dv_p, dv_e = submitted, opp_dv
    else:
        dv_p, dv_e = opp_dv, submitted
    predicted = _full_coast_prediction(rec["start_state"], dv_p, dv_e, rules.window_sec)
    trajectory = {"start_state": rec["start_state"], "dv_p_mps": dv_p,
                  "dv_e_mps": dv_e, "T_sec": rules.window_sec}
    rec["actual_trajectory"] = trajectory
    rec["actual_prediction"] = predicted
    session["round"] = round_no + 1
    session["predicted_state"] = predicted
    session["current_state"] = predicted
    print(f"已記錄第 {round_no} 回合公告；對手 Δv 分類：{classified}；"
          f"累積偏好 {dict(preferences)}")
    _write_json(args.session, session)
    print(f"下一回合：{session['round']}；已將公告雙方 Δv 的二體預測寫入 session")
    return 0


def _cmd_show(args):
    session = _read_json(args.session, "session")
    rules = Rules.from_dict(dict(session["rules"]))
    print(f"金／銅牌賽 session：我方 {session['format']['role_names'][session['role']]}；"
          f"已記錄 {len(session['rounds'])}/{rules.rounds} 回合；目前第 {session['round']} 回合")
    for rec in sorted(session["rounds"], key=lambda row: row["round"]):
        start = rec.get("start_state")
        distance = rec.get("distance_km")
        a = rec.get("evader_sma_km")
        if start and distance is None:
            distance = float(np.linalg.norm(_rv(start, "pursuer")[0] - _rv(start, "evader")[0]))
        if start and a is None:
            a = sma_official(*_rv(start, "evader"))
        print(f"第 {rec['round']} 回合：距離 {distance:.3f} km、逃方 a {a:.3f} km" if distance is not None else
              f"第 {rec['round']} 回合：尚無起點狀態")
        if rec.get("submission"):
            print(f"  我方提交：{rec['submission']['line']}")
        if rec.get("announcement"):
            announcement = rec["announcement"]
            if announcement.get("source") == "state":
                print(f"  反推來源：{announcement['state_path']}；"
                      f"{announcement['dt_sec']:.3f} s（{announcement['dt_source']}）")
            else:
                print("  公告來源：手動輸入 Δv")
            print(f"  我方公告 Δv：{announcement.get('our_dv_mps') or rec['submission']['dv_mps']} m/s；"
                  f"對手公告 Δv：{announcement['opponent_dv_mps']} m/s；"
                  f"分類 {announcement['opponent_class']}")
        if rec.get("round_result"):
            result = rec["round_result"]
            outcome = OUTCOME_LABELS.get(result["outcome"], "尚未結束")
            zone_text = "內" if result["in_zone"] else "外"
            if result["in_zone"] is None:
                zone_text = "未公告"
            print(f"  回合結果：最近距離 {result['min_dist_km']:.6f} km，"
                  f"回合開始後 {result['t_min_sec']:.3f} 秒；{outcome}；"
                  f"逃方 a = {result['evader_sma_km']:.6f} km，安全空域{zone_text}")
        if rec.get("consistency"):
            result = rec["consistency"]
            print(f"  一致性檢查：{result['status']}；位置差 "
                  f"P {result['position_diff_km']['pursuer']:.6f} / "
                  f"E {result['position_diff_km']['evader']:.6f} km")
    if session.get("finished"):
        finished = session["finished"]
        print(f"比賽應已在第 {finished['round']} 回合結束：{OUTCOME_LABELS[finished['outcome']]}，"
              f"{SIDE_LABELS[finished['winner']]}獲勝（以主辦公告為準）")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("new", help="公告規則與初始狀態建立整場 session")
    p.add_argument("--rules", required=True, help="公告規則 JSON（turn_mode 必須 simultaneous）")
    p.add_argument("--initial", required=True, help="官方初始狀態檔")
    p.add_argument("--role", choices=SIDES, required=True, help="我方角色")
    p.add_argument("--out", required=True, help="輸出的 session JSON")
    p.add_argument("--format", help="提交格式 JSON；預設 configs/final_format.json")
    p.add_argument("--names", help="船名對應：pursuer=ShipP,evader=ShipE 或 JSON 檔")
    p.add_argument("--order", help="無法依船名判斷時，指定檔案順序，如 pursuer,evader")

    p = sub.add_parser("advise", help="產生本回合建議、重驗提交值")
    p.add_argument("session", help="new 建立的 session JSON")
    p.add_argument("--state", help="本回合官方起點狀態檔")
    p.add_argument("--round", type=int, help="核對回合數")
    p.add_argument("--fast", action="store_true", help="用快速版 agent")
    p.add_argument("--seed", type=int, help="隨機種子；預設為回合數")
    p.add_argument("--manual", action="store_true", help="逐項輸入本回合雙方狀態")
    p.add_argument("--names", help="船名對應；指定後寫回 session，未指定時沿用 session")
    p.add_argument("--order", help="檔案內雙方順序；指定後寫回 session，未指定時沿用 session")

    p = sub.add_parser("announce", help="由主辦回合末狀態反推雙方 Δv，或記錄手動公告")
    p.add_argument("session", help="new 建立的 session JSON")
    p.add_argument("--opponent-dv", nargs=3, type=float, metavar=("X", "Y", "Z"),
                   help="對手實際 Δv；有 --state 時僅供比對，單位 m/s")
    p.add_argument("--our-dv", nargs=3, type=float, metavar=("X", "Y", "Z"),
                   help="我方實際 Δv；有 --state 時僅供比對，單位 m/s")
    p.add_argument("--state", help="主辦剛發的回合末狀態檔；反推後直接作為下一回合起點")
    p.add_argument("--names", help="船名對應；指定後寫回 session，未指定時沿用 session")
    p.add_argument("--order", help="檔案內雙方順序；指定後寫回 session，未指定時沿用 session")
    p.add_argument("--force", action="store_true", help="強制採用殘差或 Δv 超限的狀態檔並列印警告")

    p = sub.add_parser("manual", help="手動輸入狀態並存為 JSON")
    p.add_argument("--out", required=True)

    p = sub.add_parser("parse", help="只解析官方 USB 狀態檔並印出單位與軌道摘要")
    p.add_argument("path")
    p.add_argument("--names", help="船名對應：pursuer=ShipP,evader=ShipE 或 JSON 檔")
    p.add_argument("--order", help="無法依船名判斷時，指定檔案順序，如 pursuer,evader")

    p = sub.add_parser("show", help="印整場 session 摘要")
    p.add_argument("session")

    args = parser.parse_args(argv)
    try:
        return {"new": _cmd_new, "advise": _cmd_advise, "announce": _cmd_announce,
                "manual": _cmd_manual, "parse": _cmd_parse, "show": _cmd_show}[args.cmd](args)
    except (ValueError, KeyError, TypeError, IndexError, RuntimeError, StateImportError) as exc:
        print(f"錯誤：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
