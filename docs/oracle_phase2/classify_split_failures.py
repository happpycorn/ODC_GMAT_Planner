"""一次性分析：階段 2 四臂比較，B／D 臂 DE 贏家（拆前）的拆棒合法化失敗分類。

用法（在 repo 根目錄）：
    uv run python docs/oracle_phase2/classify_split_failures.py \
        --sweeps outputs/sweeps --out docs/oracle_phase2/split_failures.csv

判定「拆棒合法化失敗」（DE 贏家 = winner_presplit_seed<S>.json，B/D 臂沒有 oracle 候選蓋掉它）：
  * run.log 有 C4 退路（「C4：拆後估計落空」）→ 失敗（之後被 C4 救回也算）；或
  * 最終 mission 仍有超標棒／失格／不 Earth-safe（拆不出、拆後失格、拆後不 Earth-safe）。
  贏家本來就沒有超標棒（不用拆）的不列。失敗原因取 run.log 原文：先找「拆棒前贏家已存檔」之後的
  拆棒訊息；SPLIT_LEADING 開時贏家可能在 C2 比較階段已拆過（_legalize_stage 快取命中、存檔後不再印），
  那時改取存檔前最後一則拆棒訊息並註明「快取」。

等分後終端需求（log 沒印這個數字，所以自己算）：
  1. 拆前贏家的 mission_info.x 用 src.oracle_twoburn.route_from_standard_x 解碼成前導棒／滑行，
     target 照 main.legalize_violating_winner 算 A(抵達) + 瞄準偏移。
  2. 前導棒用 src.burn_splitter.presplit_leading 照產品參數（cap = MAX_DV_SOFT、min_coast）等分。
  3. 等分前後各用 burn_splitter._terminal_state（J2–J4 傳播，跟拆棒器步驟 1 相同）走到終端棒起點，
     _lam_best（產品 Lambert 分支政策、LAMBERT_MAX_REVS 用贏家 config 的值）求二體猜測，
     再 _shoot_final（J2–J4 shooting 修正）命中 target——跟拆棒器貪婪段用同一套。
     終端需求 = |v_needed − v_term|。等分前用同法重算一次（terminal_pre_calc），與 mission 的
     拆前終端棒（terminal_pre_mps）對照，兩者差太多表示重算不可信。
分類：
  * 無前導棒等分：沒有前導棒 > 單棒上限（250 m/s）。
  * 前導棒等分後終端需求暴增：terminal_post / terminal_pre > 1.5，或等分後總 Δv（前導 + 終端需求）> 總上限。
  * 終端棒本身拆不開：其餘。
"""
import argparse
import csv
import glob
import json
import math
import os
import re
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from src.optimizer import MissionOptimizer  # noqa: E402
from src.oracle_twoburn import route_from_standard_x  # noqa: E402
from src.burn_splitter import presplit_leading, _terminal_state, _lam_best, _shoot_final  # noqa: E402

FAIL_PATTERNS = ("前導棒等分：", "HAP-67 自動拆分：這個違規解", "仍失格", "C4：")
PRESPLIT_MARK = "拆棒前贏家已存檔"


def _sph(rr, th, ph):
    st = math.sin(th)
    return np.array([rr * st * math.cos(ph), rr * st * math.sin(ph), rr * math.cos(th)])


def terminal_need(opt, t0, dvs, coasts, tfin, target):
    r, v, t = _terminal_state(t0, dvs, coasts, mu=opt.MU, j2=opt.J2_VAL, j3=opt.J3_VAL,
                              j4=opt.J4_VAL, re=opt.RE_VAL, B_r0=opt.B_r0, B_v0=opt.B_v0,
                              ephem=opt.ephem)
    vg, _ = _lam_best(r, target, tfin, v, opt.MU, opt.LAMBERT_MAX_REVS)
    if vg is None:
        return float("nan"), float("nan")
    vs, miss = _shoot_final(r, vg, target, tfin, opt.MU, opt.J2_VAL, opt.J3_VAL, opt.J4_VAL, opt.RE_VAL)
    return float(np.linalg.norm(vs - v)) * 1000.0, float(miss)


def analyze_presplit(path):
    p = json.load(open(path, encoding="utf-8"))
    cfg = p["config"]
    mi = p["mission_info"]
    opt = MissionOptimizer(cfg)
    x = np.asarray(mi["x"], dtype=np.float64)
    N = int(mi["num_burns"])
    t0, dvs, coasts = route_from_standard_x(opt, x, N)
    lead, lead_coasts, tfin = dvs[:-1], coasts[:-1], coasts[-1]
    icpt = t0 + sum(coasts)
    r_A, _ = opt.state_A(icpt)
    target = r_A + _sph(x[-3], x[-2], x[-1])
    burn_mag = [float(np.linalg.norm(b)) * 1000.0 for b in p["burns"]]
    cap = opt.MAX_DV * 1000.0
    out = {
        "leading_mps": [round(b, 3) for b in burn_mag[:-1]],
        "terminal_pre_mps": round(burn_mag[-1], 3),
        "presplit_total_mps": round(float(mi["total_dv_mps"]), 3),
        "max_total_mps": opt.MAX_TOTAL_DV_MPS,
        "cap_mps": cap,
        "has_over_leading": any(b > cap + 1e-6 for b in burn_mag[:-1]),
    }
    pre, pre_miss = terminal_need(opt, t0, lead, lead_coasts, tfin, target)
    out["terminal_pre_calc_mps"], out["terminal_pre_calc_miss_km"] = round(pre, 3), round(pre_miss, 4)
    out.update(terminal_post_mps=None, terminal_post_miss_km=None, post_total_mps=None, presplit_note="")
    if out["has_over_leading"]:
        route = presplit_leading(t0, lead, lead_coasts, tfin, cap=opt.MAX_DV_SOFT, min_coast=opt.MIN_COAST_TIME)
        if route is None:
            out["presplit_note"] = "presplit_leading 回 None（時間不夠）"
        else:
            t0p, ldv, lco, tf = route
            post, post_miss = terminal_need(opt, t0p, ldv, lco, tf, target)
            out["terminal_post_mps"], out["terminal_post_miss_km"] = round(post, 3), round(post_miss, 4)
            out["post_total_mps"] = round(sum(float(np.linalg.norm(d)) * 1000.0 for d in ldv) + post, 3)
    return out


def log_reason(run_dir):
    try:
        lines = open(os.path.join(run_dir, "run.log"), encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        return "", False
    mark = next((i for i, l in enumerate(lines) if PRESPLIT_MARK in l), None)
    hits_after = [l for l in (lines[mark + 1:] if mark is not None else [])
                  if any(k in l for k in FAIL_PATTERNS)]
    c4 = any("C4：拆後估計落空" in l for l in hits_after)
    parts = [h.strip() for h in hits_after[:4]]
    if not any("C4：" not in h for h in hits_after):
        before = [l for l in (lines[:mark] if mark is not None else lines)
                  if any(k in l for k in FAIL_PATTERNS) and "C4：" not in l]
        if before:
            parts.insert(0, "（快取，取自存檔前）" + before[-1].strip())
    return " | ".join(parts), c4


def classify(a):
    if not a["has_over_leading"]:
        return "無前導棒等分"
    post = a["terminal_post_mps"]
    if post is None or (isinstance(post, float) and math.isnan(post)):
        return "前導棒等分失敗（無法算終端需求）"
    ratio = post / a["terminal_pre_mps"] if a["terminal_pre_mps"] > 0 else float("inf")
    if ratio > 1.5 or (a["max_total_mps"] is not None and a["post_total_mps"] > a["max_total_mps"]):
        return "前導棒等分後終端需求暴增"
    return "終端棒本身拆不開"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweeps", default=os.path.join(ROOT, "outputs", "sweeps"))
    ap.add_argument("--arms", default="BD")
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "oracle_phase2", "split_failures.csv"))
    ap.add_argument("--leading-ok-out", default=None,
                    help="另寫一份：前導棒超標但拆棒成功的 run，也算等分前後終端需求（對照用）")
    args = ap.parse_args()
    ok_rows = []
    rows = []
    for arm in args.arms:
        for run_dir in sorted(glob.glob(os.path.join(args.sweeps, f"phase2_arm{arm}", "runs", "*__s*"))):
            name = os.path.basename(run_dir)
            m = re.match(r"(.+)__(.+)__s(\d+)$", name)
            if not m:
                continue
            scen, seed = m[1], int(m[3])
            pre = glob.glob(os.path.join(run_dir, "winner_presplit_seed*.json"))
            mission_p = os.path.join(run_dir, "mission.json")
            if not pre or not os.path.exists(mission_p):
                continue
            pmi = json.load(open(pre[0], encoding="utf-8"))["mission_info"]
            fmi = json.load(open(mission_p, encoding="utf-8"))["mission_info"]
            needed_split = (pmi.get("over_dv_count") or 0) > 0
            if not needed_split:
                continue
            reason, c4 = log_reason(run_dir)
            final_bad = (bool(fmi.get("disqualified")) or (fmi.get("over_dv_count") or 0) > 0
                         or not bool(fmi.get("earth_safe", True)))
            if not (c4 or final_bad):
                if args.leading_ok_out:
                    a = analyze_presplit(pre[0])
                    if a["has_over_leading"]:
                        ok_rows.append({"scenario": scen, "arm": arm, "seed": seed,
                                        "leading_mps": ";".join(f"{v:.1f}" for v in a["leading_mps"]),
                                        "terminal_pre_mps": a["terminal_pre_mps"],
                                        "terminal_post_mps": a["terminal_post_mps"],
                                        "terminal_ratio": (None if a["terminal_post_mps"] is None else
                                                           round(a["terminal_post_mps"] / a["terminal_pre_mps"], 3)),
                                        "post_total_mps": a["post_total_mps"], "final_score": fmi.get("score"),
                                        "final_num_burns": fmi.get("num_burns")})
                continue
            a = analyze_presplit(pre[0])
            ratio = (a["terminal_post_mps"] / a["terminal_pre_mps"]
                     if a["terminal_post_mps"] is not None and a["terminal_pre_mps"] > 0 else None)
            rows.append({
                "scenario": scen, "arm": arm, "seed": seed, "category": classify(a),
                "leading_mps": ";".join(f"{v:.1f}" for v in a["leading_mps"]),
                "terminal_pre_mps": a["terminal_pre_mps"],
                "terminal_pre_calc_mps": a["terminal_pre_calc_mps"],
                "terminal_post_mps": a["terminal_post_mps"],
                "terminal_ratio": None if ratio is None else round(ratio, 3),
                "presplit_total_mps": a["presplit_total_mps"], "post_total_mps": a["post_total_mps"],
                "shoot_miss_pre_km": a["terminal_pre_calc_miss_km"], "shoot_miss_post_km": a["terminal_post_miss_km"],
                "rescued_by_c4": c4 and not final_bad,
                "final_score": fmi.get("score"), "final_disqualified": fmi.get("disqualified"),
                "final_earth_safe": fmi.get("earth_safe"), "final_num_burns": fmi.get("num_burns"),
                "note": a["presplit_note"], "log_reason": reason,
            })
            print(f"{scen} {arm} s{seed}: {rows[-1]['category']}  lead={rows[-1]['leading_mps']} "
                  f"term {a['terminal_pre_mps']:.1f} → {a['terminal_post_mps']}", flush=True)
    fields = ["scenario", "arm", "seed", "category", "leading_mps", "terminal_pre_mps", "terminal_pre_calc_mps",
              "terminal_post_mps", "terminal_ratio", "presplit_total_mps", "post_total_mps",
              "shoot_miss_pre_km", "shoot_miss_post_km", "rescued_by_c4", "final_score",
              "final_disqualified", "final_earth_safe", "final_num_burns", "note", "log_reason"]
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} 筆 → {args.out}")
    if args.leading_ok_out and ok_rows:
        with open(args.leading_ok_out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(ok_rows[0]))
            w.writeheader()
            w.writerows(ok_rows)
        print(f"前導棒等分成功 {len(ok_rows)} 筆 → {args.leading_ok_out}")


if __name__ == "__main__":
    main()
