"""決賽逐局 JSONL 的躲方勝率、規則分桶與安全證書報表。

用法：
    .venv/bin/python tools/final_breakdown.py reports/a.jsonl [reports/b.jsonl ...] \
        --out reports/final_breakdown.md

分桶以左含右不含計算，最後一桶包含上界；表內的 k/n 是躲方勝局數／局數，
或證書成立次數／有證書紀錄的回合數。沒有資料的格子以 — 表示。
含 scenario_meta 的逐局紀錄另列對抗題分桶；每格同時顯示躲方勝率與證書比例。
"""
import argparse
from collections import Counter, defaultdict
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation.tournament import wilson  # noqa: E402
from game.core import sma_official  # noqa: E402
from game.scenarios import full_burn_dsma_km  # noqa: E402
from physics import get_r0_v0  # noqa: E402


BUCKETS = (
    ("dv", "ΔV_lim（m/s）", ("100–200", "200–350", "350–500")),
    ("radius", "R_cap（km）", ("1–3", "3–8", "8–20")),
    ("window", "T_round（秒）", ("600–1200", "1200–2400", "2400–3600")),
    ("tau", "τ* = R_cap/ΔV_lim（秒）", ("0–10", "10–30", "30 以上")),
    ("distance", "初始距離比例：初始距離 / (ΔV_lim·T_round)",
     ("0–0.5", "0.5–2", "2 以上")),
    ("zone", "安全空域偏移：|區間中心 − 初始 a| / 一發容量",
     ("0（在區間內）", "0–2", "2–4")),
)

ADVERSARIAL_BUCKETS = (
    ("family", "family（題目家族）", None),
    ("sub", "sub（題目子類）", None),
    ("zone_width_da", "zone_width_da（安全空域寬 / 一發容量）",
     ("<0.05", "0.05–0.1", "0.1–0.3", "≥0.3")),
    ("zone_offset_da", "|zone_offset_da|（中心相對躲方初始 a / 一發容量）",
     ("0–1", "1–2", "2–4", "≥4")),
    ("ap_in_zone", "ap_in_zone（追方初始 a 在安全空域內）", ("否", "是")),
    ("cross", "cross（躲方初始 a 與區間中心位於追方兩側）", ("否", "是")),
    ("dist0_over_DT", "dist0_over_DT（初始距離 / ΔV_lim·T_round）",
     ("<0.2", "0.2–1", "≥1")),
    ("epoch_gap_h", "epoch_gap_h（兩艘入軌時間差，時）",
     ("0–6", "6–12", "12–24")),
)


def _number(value):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _interval(value, edges, labels):
    if value is None:
        return "缺資料"
    if value < edges[0] or value > edges[-1]:
        return "範圍外"
    for i, label in enumerate(labels):
        if edges[i] <= value < edges[i + 1] or (i == len(labels) - 1 and value == edges[-1]):
            return label
    return "範圍外"


def _orbit_geometry(result):
    """逐局六根數 → 初始距離與躲方初始密切半長軸。舊紀錄可能沒有軌道欄位。"""
    op, oe = result.get("orbit_pursuer"), result.get("orbit_evader")
    if not isinstance(op, dict) or not isinstance(oe, dict):
        return None, None
    try:
        rp, _ = get_r0_v0(**op)
        re, ve = get_r0_v0(**oe)
        distance = math.dist(rp, re)
        a = sma_official(re, ve)
    except (KeyError, TypeError, ValueError, OverflowError):
        return None, None
    return (_number(distance), _number(a))


def game_buckets(result):
    """每局的六個分桶標籤。ΔV_lim 只有雙方相同時才有單一數值。"""
    rules = result.get("rules") or {}
    dp = _number(rules.get("max_dv_pursuer_mps"))
    de = _number(rules.get("max_dv_evader_mps"))
    dv = dp if dp is not None and de is not None and math.isclose(dp, de) and dp > 0.0 else None
    radius = _number(rules.get("capture_radius_km"))
    window = _number(rules.get("window_sec"))
    distance, a = _orbit_geometry(result)
    zone = rules.get("safe_sma_km")
    labels = {
        "dv": _interval(dv, (100.0, 200.0, 350.0, 500.0), BUCKETS[0][2]),
        "radius": _interval(radius, (1.0, 3.0, 8.0, 20.0), BUCKETS[1][2]),
        "window": _interval(window, (600.0, 1200.0, 2400.0, 3600.0), BUCKETS[2][2]),
        "tau": _interval(1000.0 * radius / dv if radius is not None and dv else None,
                         (0.0, 10.0, 30.0, math.inf), BUCKETS[3][2]),
        "distance": _interval(1000.0 * distance / (dv * window)
                              if distance is not None and dv and window and window > 0 else None,
                              (0.0, 0.5, 2.0, math.inf), BUCKETS[4][2]),
    }
    if zone is None:
        labels["zone"] = "無安全空域"
    elif a is None or de is None or de <= 0.0:
        labels["zone"] = "缺資料"
    else:
        try:
            lo, hi = (float(x) for x in zone)
            capacity = full_burn_dsma_km(a, de)
            if not (math.isfinite(lo) and math.isfinite(hi) and capacity > 0.0):
                labels["zone"] = "缺資料"
            elif lo <= a <= hi:
                labels["zone"] = "0（在區間內）"
            else:
                offset = abs((lo + hi) / 2.0 - a) / capacity
                labels["zone"] = "0–2" if offset < 2.0 else "2–4" if offset <= 4.0 else "4 以上"
        except (TypeError, ValueError, OverflowError):
            labels["zone"] = "缺資料"
    return labels


def read_jsonl(paths):
    results = []
    for path in paths:
        with open(path, encoding="utf-8") as stream:
            for line_no, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{path}:{line_no} 不是有效 JSON：{exc.msg}") from exc
                needed = ("pursuer", "evader", "winner", "outcome", "rules")
                if not isinstance(row, dict) or any(key not in row for key in needed):
                    raise ValueError(f"{path}:{line_no} 缺逐局欄位 {needed}；請用 evaluate.py 產生 JSONL")
                if not isinstance(row["rules"], dict):
                    raise ValueError(f"{path}:{line_no} 的 rules 應是 JSON 物件")
                results.append(row)
    if not results:
        raise ValueError("輸入檔沒有逐局紀錄；請確認 JSONL 路徑及內容")
    return results


def _escape(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def _ratio(k, n, decimals=0):
    return f"{100.0 * k / n:.{decimals}f}% ({k}/{n})" if n else "—"


def _pair(result):
    return result["pursuer"], result["evader"]


def _pair_rows(data):
    grouped = defaultdict(list)
    for result, bucket in data:
        grouped[_pair(result)].append((result, bucket))
    return dict(sorted(grouped.items()))


def _table_by_bucket(lines, title, key, labels, pairs, value_for_result):
    extras = sorted({bucket[key] for rows in pairs.values() for _, bucket in rows if bucket[key] not in labels})
    columns = tuple(labels) + tuple(extras)
    lines.extend((f"### {title}", "", "| 追方 | 躲方 | " + " | ".join(columns) + " |",
                  "|---|---|" + "---|" * len(columns)))
    for (pursuer, evader), rows in pairs.items():
        cells = []
        for label in columns:
            values = [value_for_result(result) for result, bucket in rows if bucket[key] == label]
            values = [value for value in values if value is not None]
            cells.append(_ratio(sum(values), len(values)))
        lines.append(f"| {_escape(pursuer)} | {_escape(evader)} | " + " | ".join(cells) + " |")
    lines.append("")


def _adversarial_buckets(result):
    """對抗題目的分桶標籤；缺少個別欄位時保留缺資料桶。"""
    meta = result["scenario_meta"]
    family = result.get("family")
    labels = {"family": str(family) if family is not None else "缺資料",
              "sub": str(meta["sub"]) if meta.get("sub") is not None else "缺資料"}
    labels["zone_width_da"] = _interval(
        _number(meta.get("zone_width_da")), (0.0, 0.05, 0.1, 0.3, math.inf),
        ADVERSARIAL_BUCKETS[2][2])
    offset = _number(meta.get("zone_offset_da"))
    labels["zone_offset_da"] = _interval(
        abs(offset) if offset is not None else None,
        (0.0, 1.0, 2.0, 4.0, math.inf), ADVERSARIAL_BUCKETS[3][2])
    for key in ("ap_in_zone", "cross"):
        value = meta.get(key)
        labels[key] = "是" if value is True else "否" if value is False else "缺資料"
    labels["dist0_over_DT"] = _interval(
        _number(meta.get("dist0_over_DT")), (0.0, 0.2, 1.0, math.inf),
        ADVERSARIAL_BUCKETS[6][2])
    labels["epoch_gap_h"] = _interval(
        _number(meta.get("epoch_gap_h")), (0.0, 6.0, 12.0, 24.0),
        ADVERSARIAL_BUCKETS[7][2])
    return labels


def _certificate_counts(result):
    """回傳成立數與有紀錄數，分母與既有證書報表相同。"""
    history = result.get("info_evader")
    if not isinstance(history, list):
        return 0, 0
    values = [bool(info["certificate"]) for info in history
              if isinstance(info, dict) and "certificate" in info]
    return sum(values), len(values)


def _adversarial_table(lines, title, key, labels, pairs):
    if labels is None:
        labels = sorted({bucket[key] for rows in pairs.values() for _, bucket in rows})
    extras = sorted({bucket[key] for rows in pairs.values() for _, bucket in rows
                     if bucket[key] not in labels})
    columns = tuple(labels) + tuple(extras)
    lines.extend((f"### {title}", "", "| 追方 | 躲方 | " + " | ".join(columns) + " |",
                  "|---|---|" + "---|" * len(columns)))
    for (pursuer, evader), rows in pairs.items():
        cells = []
        for label in columns:
            selected = [result for result, bucket in rows if bucket[key] == label]
            if not selected:
                cells.append("—")
                continue
            wins = sum(result["winner"] == "evader" for result in selected)
            certificates = [_certificate_counts(result) for result in selected]
            certified = sum(value for value, _ in certificates)
            recorded = sum(value for _, value in certificates)
            cells.append(f"{_ratio(wins, len(selected))} / {_ratio(certified, recorded)}")
        lines.append(f"| {_escape(pursuer)} | {_escape(evader)} | " + " | ".join(cells) + " |")
    lines.append("")


def _display_number(value):
    number = _number(value)
    return f"{number:.6g}" if number is not None else "—"


def _safe_evader_loss_lines(results):
    losses = [result for result in results
              if str(result.get("evader", "")).startswith("safe_evader")
              and result.get("winner") != "evader"]
    lines = ["## safe_evader 輸掉的局", "", f"共 {len(losses)} 局。", ""]
    if not losses:
        return lines
    lines.extend(("| game_id | family | sub | 結局 | ΔV_lim（m/s） | R_cap（km） | "
                  "T_round（秒） | meta 重點欄位 |",
                  "|---:|---|---|---|---:|---:|---:|---|"))
    meta_keys = ("a_p", "a_e", "da", "zone_width_da", "zone_offset_da",
                 "ap_in_zone", "cross", "dist0_km", "dist0_over_DT", "epoch_gap_h")
    for result in losses:
        rules = result.get("rules") or {}
        meta = result.get("scenario_meta") or {}
        dp = _display_number(rules.get("max_dv_pursuer_mps"))
        de = _display_number(rules.get("max_dv_evader_mps"))
        dv = dp if dp == de else f"P {dp} / E {de}"
        fields = []
        for key in meta_keys:
            if key not in meta:
                continue
            value = meta[key]
            if isinstance(value, bool):
                display = "是" if value else "否"
            else:
                display = _display_number(value)
            fields.append(f"{key}={display}")
        details = "、".join(fields) if fields else "—"
        lines.append(f"| {_escape(result.get('game_id', '未知'))} | "
                     f"{_escape(result.get('family', '缺資料'))} | "
                     f"{_escape(meta.get('sub', '缺資料'))} | "
                     f"{_escape(result.get('outcome', '缺資料'))} | {dv} | "
                     f"{_display_number(rules.get('capture_radius_km'))} | "
                     f"{_display_number(rules.get('window_sec'))} | {_escape(details)} |")
    lines.append("")
    return lines


def _info_records(data, side, field):
    for result, bucket in data:
        history = result.get(f"info_{side}")
        if not isinstance(history, list):
            continue
        for index, info in enumerate(history, 1):
            if not isinstance(info, dict) or field not in info:
                continue
            try:
                round_no = int(info.get("round", index))
            except (TypeError, ValueError):
                round_no = index
            yield result, bucket, round_no, info


def _captured_this_round(result, round_no):
    return result.get("outcome") == "capture" and result.get("rounds_played") == round_no


def breakdown_report(results, sources=None):
    data = [(result, game_buckets(result)) for result in results]
    pairs = _pair_rows(data)
    lines = ["# 決賽評測分桶報表", ""]
    if sources:
        lines.extend(("來源：" + "、".join(_escape(path) for path in sources), ""))
    lines.extend((f"共 {len(results)} 局、{len(pairs)} 個配對。", "",
                  "## 配對總覽", "",
                  "| 追方 | 躲方 | 局數 | 躲方勝率 | Wilson 95% 區間 | 結局分布 |",
                  "|---|---|---:|---:|---:|---|"))
    for (pursuer, evader), rows in pairs.items():
        outcomes = Counter(result["outcome"] for result, _ in rows)
        wins = sum(result["winner"] == "evader" for result, _ in rows)
        lo, hi = wilson(wins, len(rows))
        distribution = "、".join(f"{_escape(outcome)}: {count}" for outcome, count in sorted(outcomes.items()))
        lines.append(f"| {_escape(pursuer)} | {_escape(evader)} | {len(rows)} | "
                     f"{_ratio(wins, len(rows))} | {100 * lo:.1f}–{100 * hi:.1f}% | {distribution} |")
    lines.extend(("", "## 躲方勝率分桶", "",
                  "τ* = 1000 × R_cap（km）/ ΔV_lim（m/s）；初始距離比例 = 1000 × 初始距離（km）"
                  " / [ΔV_lim（m/s）× T_round（秒）]。每桶顯示勝率（勝局數/局數）。", ""))
    for key, title, labels in BUCKETS:
        _table_by_bucket(lines, title, key, labels, pairs,
                         lambda result: result["winner"] == "evader")

    cert = list(_info_records(data, "evader", "certificate"))
    if cert:
        cert_pairs = defaultdict(list)
        for result, bucket, round_no, info in cert:
            cert_pairs[_pair(result)].append((result, bucket, round_no, bool(info["certificate"])))
        lines.extend(("## 安全證書成立比例", "",
                      f"有 {len(cert)} 個躲方決策回合含 certificate 紀錄。", "",
                      "### 依回合", "",
                      "| 追方 | 躲方 | " + " | ".join(f"第 {i} 回合" for i in range(1, 7)) + " |",
                      "|---|---|" + "---|" * 6))
        for pursuer, evader in pairs:
            rows = cert_pairs.get((pursuer, evader), [])
            cells = [_ratio(sum(value for _, _, rnd, value in rows if rnd == i),
                            sum(rnd == i for _, _, rnd, _ in rows)) for i in range(1, 7)]
            lines.append(f"| {_escape(pursuer)} | {_escape(evader)} | " + " | ".join(cells) + " |")
        lines.extend(("", "### 依規則與題目分桶", ""))
        cert_data = [(result, bucket, bool(info["certificate"])) for result, bucket, _, info in cert]
        cert_grouped = {pair: [(result, bucket, value) for result, bucket, value in cert_data
                               if _pair(result) == pair] for pair in pairs}
        for key, title, labels in BUCKETS:
            extras = sorted({bucket[key] for rows in cert_grouped.values() for _, bucket, _ in rows
                             if bucket[key] not in labels})
            columns = tuple(labels) + tuple(extras)
            lines.extend((f"#### {title}", "", "| 追方 | 躲方 | " + " | ".join(columns) + " |",
                          "|---|---|" + "---|" * len(columns)))
            for pursuer, evader in pairs:
                rows = cert_grouped[(pursuer, evader)]
                cells = [_ratio(sum(value for _, bucket, value in rows if bucket[key] == label),
                                sum(bucket[key] == label for _, bucket, _ in rows)) for label in columns]
                lines.append(f"| {_escape(pursuer)} | {_escape(evader)} | " + " | ".join(cells) + " |")
            lines.append("")
        violations = [(result, round_no) for result, _, round_no, info in cert
                      if info["certificate"] and _captured_this_round(result, round_no)]
        lines.append(f"證書成立的回合被捕獲：{len(violations)} 次。")
        if violations:
            lines.append("")
            for result, round_no in violations:
                lines.append(f"- game_id={result.get('game_id', '未知')}，{_escape(result['pursuer'])} / "
                             f"{_escape(result['evader'])}，第 {round_no} 回合")
        lines.append("")

    hits = [(result, round_no, _number(info["hit_prob"]))
            for result, _, round_no, info in _info_records(data, "pursuer", "hit_prob")]
    hits = [(result, round_no, prob) for result, round_no, prob in hits if prob is not None]
    if hits:
        lines.extend(("## 追方命中機率校準", "",
                      "平均 hit_prob 與實際捕獲率均以有 hit_prob 的決策回合為分母；"
                      "實際捕獲指該回合結束時 outcome 為 capture。", "",
                      "| 追方 | 躲方 | 決策回合 | 平均 hit_prob | 實際捕獲率 |",
                      "|---|---|---:|---:|---:|"))
        for pursuer, evader in pairs:
            rows = [(result, round_no, prob) for result, round_no, prob in hits
                    if _pair(result) == (pursuer, evader)]
            if not rows:
                continue
            captures = sum(_captured_this_round(result, round_no) for result, round_no, _ in rows)
            mean_prob = sum(prob for _, _, prob in rows) / len(rows)
            lines.append(f"| {_escape(pursuer)} | {_escape(evader)} | {len(rows)} | "
                         f"{100 * mean_prob:.1f}% | {_ratio(captures, len(rows))} |")
        lines.append("")
    adversarial = [(result, _adversarial_buckets(result)) for result in results
                   if isinstance(result.get("scenario_meta"), dict)]
    if adversarial:
        adversarial_pairs = _pair_rows(adversarial)
        lines.extend(("## 對抗題目分桶", "",
                      f"有 {len(adversarial)} 局含 scenario_meta。每格依序顯示躲方勝率 / "
                      "安全證書成立比例；勝率以局數、證書以有紀錄的躲方決策回合數為分母。", ""))
        for key, title, labels in ADVERSARIAL_BUCKETS:
            _adversarial_table(lines, title, key, labels, adversarial_pairs)
    if any(str(result.get("evader", "")).startswith("safe_evader") for result in results):
        lines.extend(_safe_evader_loss_lines(results))
    return "\n".join(lines).rstrip() + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="決賽評測逐局 JSONL 的躲方勝率與分桶報表")
    ap.add_argument("inputs", nargs="+", help="evaluate.py 輸出的 reports/<name>.jsonl，可一次給多個")
    ap.add_argument("--out", help="輸出 Markdown 路徑；未給時印到終端機")
    args = ap.parse_args(argv)
    try:
        report = breakdown_report(read_jsonl(args.inputs), sources=args.inputs)
        if args.out:
            os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
            with open(args.out, "w", encoding="utf-8") as stream:
                stream.write(report)
            print(f"→ {args.out}")
        else:
            print(report, end="")
    except (OSError, ValueError) as exc:
        ap.exit(2, f"無法產生分桶報表：{exc}\n")


if __name__ == "__main__":
    main()
