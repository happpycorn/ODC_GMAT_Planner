"""規則公布當天的查表：給一組規則，列出規則敏感度地圖（configs/rule_map.json）裡最接近的格子、
預期勝率、建議大腦，並標出哪些欄位超出地圖範圍（那些欄位的影響地圖沒量過，數字只能當方向）。

    uv run python tools/rule_lookup.py configs/rules_final.json
    uv run python tools/rule_lookup.py configs/rules_final.json --top 5 --map configs/rule_map.json

規則檔格式同 configs/rules_template.json（沒填的欄位用 Rules() 預設——注意預設是 1500/3000 佔位值）。
「距離」是各欄位差異的加權和（對數尺度：窗口/單發/燃料/T_max 差 2 倍 ≈ 1；一回合多一發 = 1.5；
燃料差 2 倍 = 1.5），只用來排序；每個格子都會列出它跟你的規則差在哪些欄位。
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.rule_presets import burns_that_fit  # noqa: E402
from game.rules import Rules  # noqa: E402
from tools.rule_map import AXES, SIG, _fmt  # noqa: E402

WEIGHTS = {"window": 1.0, "radius": 0.5, "burns": 1.5, "dv_p": 1.0, "dv_e": 1.0, "fuel_p": 1.5, "fuel_e": 1.5,
           "tmax": 1.0, "first": 0.5, "capmode": 1.0, "gravity": 0.25, "gap": 0.5, "crash": 0.02}
LEO_PERIOD_SEC = 5700.0      # t_max_sec 指定絕對秒數時，粗略換算成週期用（LEO ~95 分鐘）
NUM_FIELDS = ["window_sec", "capture_radius_km", "max_dv_pursuer_mps", "max_dv_evader_mps", "fuel_pursuer_mps",
              "fuel_evader_mps", "t_max_periods"]
CAT_FIELDS = ["first_mover", "capture_mode", "gravity_degree", "crash_altitude_km"]


def _log2(x):
    return math.log2(max(float(x), 1e-9))


def eff_burns(R):
    return burns_that_fit(R.window_sec, R.burns_per_turn, R.min_burn_gap_sec)


def tmax_periods(R):
    return R.t_max_periods if R.t_max_sec <= 0 else R.t_max_sec / LEO_PERIOD_SEC


def features(R):
    b = eff_burns(R)
    return {"window": _log2(R.window_sec), "radius": _log2(R.capture_radius_km), "burns": float(b),
            "dv_p": _log2(R.max_dv_pursuer_mps), "dv_e": _log2(R.max_dv_evader_mps),
            "fuel_p": _log2(R.fuel_pursuer_mps), "fuel_e": _log2(R.fuel_evader_mps),
            "tmax": _log2(tmax_periods(R)), "first": float(R.first_mover != "pursuer"),
            "capmode": float(R.capture_mode != "continuous"), "gravity": float(R.gravity_degree),
            "gap": _log2(R.min_burn_gap_sec) if b > 1 else 0.0, "crash": float(R.crash_altitude_km)}


def distance(R, cell_rules):
    fa, fb = features(R), features(Rules.from_dict(cell_rules))
    return math.sqrt(sum((WEIGHTS[k] * (fa[k] - fb[k])) ** 2 for k in fa))


def point_cells(doc):
    return [c for c in doc["cells"] if c.get("rules")]


def nearest(R, doc, top=3):
    out = [(distance(R, c["rules"]), c) for c in point_cells(doc)]
    out.sort(key=lambda x: x[0])
    return out[:top]


def diff_fields(R, cell_rules):
    a, b = R.to_dict(), cell_rules
    keys = NUM_FIELDS + CAT_FIELDS + ["t_max_sec"]
    out = [f"{k} {_fmt(b[k])}→{_fmt(a[k])}" for k in keys if a[k] != b[k]]
    eb_a, eb_b = eff_burns(R), eff_burns(Rules.from_dict(b))
    if eb_a != eb_b:
        out.append(f"發數 {eb_b}→{eb_a}")
    return out


def out_of_range(R, doc):
    """[(欄位, 說明)]：數值欄位在所有測過的格子的最小～最大之外、類別欄位沒測過、或衍生量（燃料發數、燃料比）超出。"""
    cells = [Rules.from_dict(c["rules"]) for c in point_cells(doc)]
    flags = []
    if not cells:
        return [("map", "地圖是空的")]
    for f in NUM_FIELDS:
        vals = [getattr(c, f) for c in cells]
        lo, hi = min(vals), max(vals)
        v = tmax_periods(R) if f == "t_max_periods" else getattr(R, f)
        if v < lo * (1 - 1e-9) or v > hi * (1 + 1e-9):
            flags.append((f, f"{v:g} 在測過的 {lo:g}–{hi:g} 之外"))
    if R.t_max_sec > 0:
        flags.append(("t_max_sec", f"指定絕對 {R.t_max_sec:g} s；地圖用「N × 追者週期」，這裡粗估 LEO 95 分鐘 = "
                                   f"{tmax_periods(R):.1f} 週期"))
    for f in CAT_FIELDS:
        seen = sorted({getattr(c, f) for c in cells}, key=str)
        if getattr(R, f) not in seen:
            flags.append((f, f"{getattr(R, f)} 沒測過（地圖只有 {', '.join(map(str, seen))}）"))
    b = eff_burns(R)
    bs = [eff_burns(c) for c in cells]
    if b < min(bs) or b > max(bs):
        flags.append(("burns_per_turn", f"有效 {b} 發/回合在測過的 {min(bs)}–{max(bs)} 之外"))
    if b > 1 and R.min_burn_gap_sec not in {c.min_burn_gap_sec for c in cells if eff_burns(c) > 1}:
        flags.append(("min_burn_gap_sec", f"{R.min_burn_gap_sec:g} s 沒測過（多發格子都是 100 s）"))
    derived = {"燃料發數 追（燃料/單發）": lambda r: r.fuel_pursuer_mps / max(r.max_dv_pursuer_mps, 1e-9),
               "燃料發數 躲": lambda r: r.fuel_evader_mps / max(r.max_dv_evader_mps, 1e-9),
               "燃料比 追/躲": lambda r: r.fuel_pursuer_mps / max(r.fuel_evader_mps, 1e-9)}
    for name, fn in derived.items():
        vals = [fn(c) for c in cells]
        v = fn(R)
        if v < min(vals) * (1 - 1e-9) or v > max(vals) * (1 + 1e-9):
            flags.append((name, f"{v:.2f} 在測過的 {min(vals):.2f}–{max(vals):.2f} 之外"))
    return flags


def _rate(st):
    if not st:
        return "未跑"
    lo, hi = st["ci"]
    s = f"{100 * st['rate']:.0f}% [{100 * lo:.0f}–{100 * hi:.0f}] n={st['n']}"
    v = st.get("vs_base")
    if v:
        s += f"（vs 基底 +{v['only_cell']}/−{v['only_base']} p={v['p']:.2g}{' ✱' if v['p'] < SIG else ''}）"
    return s


def describe(R):
    b = eff_burns(R)
    return (f"單發 追{_fmt(R.max_dv_pursuer_mps)}/躲{_fmt(R.max_dv_evader_mps)} m/s、燃料 追{_fmt(R.fuel_pursuer_mps)}/"
            f"躲{_fmt(R.fuel_evader_mps)} m/s（{R.fuel_pursuer_mps / R.max_dv_pursuer_mps:.1f}/"
            f"{R.fuel_evader_mps / R.max_dv_evader_mps:.1f} 發）、窗口 {_fmt(R.window_sec)} s、"
            f"{b} 發/回合（間隔 {_fmt(R.min_burn_gap_sec)} s）、半徑 {_fmt(R.capture_radius_km)} km、"
            f"T_max {tmax_periods(R):.1f} 週期、先手 {R.first_mover}、{R.capture_mode}、J{R.gravity_degree}")


def cell_block(i, d, c, R):
    a = c.get("advice", {})
    P = c["pairs"]
    diffs = diff_fields(R, c["rules"])
    lines = [f"{i}. [{c.get('family')}] {c['label']}（距離 {d:.2f}；跟你的規則差：{'、'.join(diffs) or '無'}）",
             f"   rollout 追 vs rollout 躲：{_rate(P.get('rr'))}",
             f"   強化版追 vs rollout 躲：{_rate(P.get('strong'))}",
             f"   rollout 追 vs 逃逸躲：  {_rate(P.get('escape'))}"]
    if P.get("lambert"):
        lines.append(f"   Lambert 追 vs rollout 躲：{_rate(P.get('lambert'))}")
    for key, name in (("pursuer_compare", "strong"), ("lambert_compare", "lambert")):
        cp = c.get(key)
        if cp:
            lines.append(f"   追者大腦（同局配對）：{name} 獨贏 {cp[f'only_{name}']}、rollout 獨贏 {cp['only_rollout']}，"
                         f"p={cp['p']:.2g}")
    if a.get("as_pursuer"):
        lines.append(f"   抽到追者：{a['as_pursuer']}")
    if a.get("as_evader"):
        lines.append(f"   抽到躲者：{a['as_evader']}")
    return lines


def axis_effects(R, doc, family, source):
    """你的規則跟該基底不同的軸：列出那個軸上所有測過的單軸格子（相對基底的效果）。"""
    cells = [c for c in doc["cells"] if c.get("source") == source and c.get("rules")]
    base = next((c for c in cells if c["id"] == "base"), None)
    if base is None:
        return []
    b = base["rules"]
    a = R.to_dict()
    lines = []
    for axis, flds in AXES:
        differs = any(a[f] != b[f] for f in flds)
        if axis == "burns_per_turn":
            differs = eff_burns(R) != eff_burns(Rules.from_dict(b))
        if not differs:
            continue
        on_axis = [c for c in cells if c["axis"] == axis]
        if not on_axis:
            lines.append(f"  - {axis}：這個基底沒有掃這個軸")
            continue
        for c in on_axis:
            lines.append(f"  - {c['label']}：rr {_rate(c['pairs'].get('rr'))}；strong {_rate(c['pairs'].get('strong'))}")
    if lines:
        lines.insert(0, f"各軸單獨的效果（基底 [{family}]：rr {_rate(base['pairs'].get('rr'))}；"
                        f"strong {_rate(base['pairs'].get('strong'))}）")
    return lines


def render(R, doc, top=3):
    lines = ["規則：" + describe(R), ""]
    flags = out_of_range(R, doc)
    if flags:
        lines.append("⚠ 超出地圖範圍的欄位（這些影響地圖沒量過，下面的數字只能當方向參考）：")
        lines += [f"  - {f}：{msg}" for f, msg in flags]
    else:
        lines.append("全部欄位都在地圖範圍內。")
    lines += ["", "最接近的格子（勝率 = 追者勝率；✱ = 跟基底逐局配對 p < 0.05）："]
    near = nearest(R, doc, top)
    for i, (d, c) in enumerate(near, 1):
        lines += cell_block(i, d, c, R)
    if near and near[0][0] > 1.0:
        lines.append("  （最近的格子距離 > 1：跟任何測過的格子都差了一個軸的一步以上，請搭配下面的各軸效果看）")
    if near:
        lines += [""] + axis_effects(R, doc, near[0][1].get("family"), near[0][1].get("source"))
    rng_cells = [c for c in doc["cells"] if c.get("ranges")]
    for c in rng_cells:
        lines += ["", f"規則不確定時的平均（{c['label']}，[{c.get('family')}] 幾何）：",
                  f"  rr {_rate(c['pairs'].get('rr'))}", f"  strong {_rate(c['pairs'].get('strong'))}",
                  f"  escape {_rate(c['pairs'].get('escape'))}"]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rules", help="規則 JSON（configs/rules_final.json）")
    ap.add_argument("--map", default="configs/rule_map.json")
    ap.add_argument("--top", type=int, default=3)
    args = ap.parse_args()
    with open(args.rules) as f:
        R = Rules.from_dict(json.load(f))
    with open(args.map) as f:
        doc = json.load(f)
    print(render(R, doc, args.top))


if __name__ == "__main__":
    main()
