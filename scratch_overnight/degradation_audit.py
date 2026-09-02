"""HAP-26 / CP4：極端幾何盤點 + 無解優雅降級稽核。

問的不是「解好不好」，是「工具會不會在極端／無解的題目上崩潰或空手」。優雅降級的定義：
  1. run_study **絕不 uncaught crash**（單一 case 崩潰要被接住、其他 case 續跑）；
  2. 有違規解時要回一個**有標記的最佳努力解**（penalty_count>0 或最大單棒超標），
     而不是回 None 空手——空手代表隊友當天看到「任務終止」卻不知道還有沒有東西能交。
  3. 真的全軍覆沒（每個候選都撞地球／Lambert 全不收斂）時，回乾淨的 None 也可以，
     但要能跟「其實有違規解卻回 None」區分開來——後者是 bug。

因為測的是控制流不是解品質，用**極小搜尋預算**跑（快）。每個幾何**單獨一個行程**
（--geometry NAME），硬崩潰只會損失那一組、不影響其他組已寫進 JSON 的結果。

跑法：
  uv run python scratch_overnight/degradation_audit.py --geometry hyper_fast
  # 或掃全部（外層 shell 迴圈，一次一個）：
  for g in $(uv run python scratch_overnight/degradation_audit.py --list); do
      uv run python scratch_overnight/degradation_audit.py --geometry $g; done
結果附加到 scratch_overnight/degradation_audit_results.json
"""

import argparse
import json
import math
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import warnings
warnings.filterwarnings("ignore")

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "degradation_audit_results.json")

# expect: feasible（該找到合法解）/ violating（無合法解、但該回有標記的違規解）/
#          none_ok（可能全軍覆沒、回 None 可接受）/ edge（退化幾何、只要求不崩潰）
GEOMS = {
    "official_sample": {
        "expect": "feasible",
        "A": {"SMA": 6978.0, "ECC": 0.0, "INC": 45.0, "RAAN": 0.0, "AOP": 0.0, "TA": 0.0},
        "B": {"SMA": 6878.0, "ECC": 0.0, "INC": 135.0, "RAAN": 30.0, "AOP": 0.0, "TA": 60.0},
        "kc": (0.0005, 3212.0, 0.002, 2241.0),
    },
    "hyperbolic_smoke": {           # A 雙曲線飛越，文件記 ✅ 851 m/s
        "expect": "feasible",
        "A": {"SMA": -50000.0, "ECC": 1.2, "INC": 30.0, "RAAN": 0.0, "AOP": 0.0, "TA": 230.0},
        "B": {"SMA": 7000.0, "ECC": 0.001, "INC": 0.0, "RAAN": 0.0, "AOP": 0.0, "TA": 0.0},
        "t_max_sec": 40000.0, "kc": (0.0001, 25000.0, 0.002, 1500.0),
    },
    "hard_mode": {                  # 能量門檻、要拆棒；文件記違規／很難
        "expect": "violating",
        "A": {"SMA": 100000.0, "ECC": 0.5, "INC": 63.4, "RAAN": 40.0, "AOP": 270.0, "TA": 0.0},
        "B": {"SMA": 6800.0, "ECC": 0.001, "INC": 0.0, "RAAN": 0.0, "AOP": 0.0, "TA": 0.0},
        "kc": (0.000002, 1800000.0, 0.05, 1200.0),
    },
    "hyper_far": {                  # 雙曲線 + 能量門檻，下限>上限 → 違規
        "expect": "violating",
        "A": {"SMA": -125000.0, "ECC": 1.2, "INC": 30.0, "RAAN": 0.0, "AOP": 0.0, "TA": 229.67},
        "B": {"SMA": 7000.0, "ECC": 0.001, "INC": 0.0, "RAAN": 0.0, "AOP": 0.0, "TA": 0.0},
        "t_max_sec": 162570.0, "kc": (0.00002, 100000.0, 0.0015, 2500.0),
    },
    "hyper_fast": {                 # 相位鎖死、證明無解 → 該回有標記的違規解（荒謬超標）
        "expect": "violating",
        "A": {"SMA": -2500.0, "ECC": 5.0, "INC": 30.0, "RAAN": 0.0, "AOP": 0.0, "TA": 269.63},
        "B": {"SMA": 7000.0, "ECC": 0.001, "INC": 0.0, "RAAN": 0.0, "AOP": 0.0, "TA": 0.0},
        "t_max_sec": 9101.0, "kc": (0.0004, 6000.0, 0.001, 4000.0),
    },
    "weird_test": {                 # 窄窗、極端偏心
        "expect": "feasible",
        "A": {"SMA": 150000.0, "ECC": 0.93, "INC": 175.0, "RAAN": 270.0, "AOP": 333.0, "TA": 17.0},
        "B": {"SMA": 6800.0, "ECC": 0.001, "INC": 98.0, "RAAN": 45.0, "AOP": 0.0, "TA": 200.0},
        "kc": (0.0001, 11000.0, 0.005, 1200.0),
    },
    "antialigned": {                # 逆行、極大平面差（相對傾角 ~170°）
        "expect": "violating",
        "A": {"SMA": 8000.0, "ECC": 0.1, "INC": 175.0, "RAAN": 0.0, "AOP": 0.0, "TA": 0.0},
        "B": {"SMA": 7000.0, "ECC": 0.001, "INC": 5.0, "RAAN": 0.0, "AOP": 0.0, "TA": 180.0},
        "kc": (0.0001, 11000.0, 0.005, 1200.0),
    },
    "identical": {                  # 退化：A、B 同一條軌道（Δr 起始 0，轉移角退化）
        "expect": "edge",
        "A": {"SMA": 7000.0, "ECC": 0.0, "INC": 30.0, "RAAN": 0.0, "AOP": 0.0, "TA": 0.0},
        "B": {"SMA": 7000.0, "ECC": 0.0, "INC": 30.0, "RAAN": 0.0, "AOP": 0.0, "TA": 0.0},
        "kc": (0.0001, 11000.0, 0.005, 1200.0),
    },
}

# 極小預算：測的是控制流（會不會崩／空手），不是解品質。
TINY_OPT = {"MAX_BURNS": [1, 2], "MAXITER": 25, "POPSIZE": 5,
            "NUM_THREADS": -1, "MAX_EARLY_STOP": 25, "TOL": 0.01, "SEED": 777}


def build_config(g):
    kt, ct, kv, cv = g["kc"]
    rules = {"MAX_DV_MPS": 1500.0, "MIN_MANEUVER_INTERVAL_SEC": 100.0,
             "T_MAX_PERIOD_MULTIPLE": 4.0, "k_t": kt, "C_t": ct, "k_v": kv, "C_v": cv}
    if "t_max_sec" in g:
        rules["T_MAX_SEC"] = g["t_max_sec"]      # 雙曲線 A 必填（見 script/optimizer）
    return {
        "orbit_A": g["A"], "orbit_B": g["B"], "rules": rules,
        "strategy": {"GRAVITY_DEGREE": 2, "MISS_TOLERANCE_KM": 5.0, "LAMBERT_MAX_REVS": 2},
        "optimization": dict(TINY_OPT),
    }


def audit_one(name):
    from src.optimizer import MissionOptimizer

    g = GEOMS[name]
    rec = {"geometry": name, "expect": g["expect"]}
    try:
        cfg = build_config(g)
        opt = MissionOptimizer(cfg)
        rec["T_max_sec"] = round(float(opt.T_max), 1)
        max_dv = opt.MAX_DV                      # km/s
        burns, times, mission_info = opt.run_study()

        if burns is None or mission_info is None:
            rec["outcome"] = "empty"             # 回 None 空手
            # 有沒有任何 case 其實跑出了非零分（score>0 ↔ fitness<0）的解？
            # 有的話「空手回 None」就是 bug——那個違規解本該被回報成最佳努力。
            fits = [r.get("fitness") for r in opt.burn_case_results.values()
                    if r.get("fitness") is not None]
            rec["best_case_fitness"] = round(float(min(fits)), 3) if fits else None
            rec["any_case_had_solution"] = any(f < 0 for f in fits)
        else:
            rec["outcome"] = "solution"
            rec["num_burns"] = int(mission_info["num_burns"])
            rec["score"] = round(float(mission_info["score"]), 2)
            rec["penalty_count"] = int(mission_info["penalty_count"])
            rec["dc_converged"] = bool(mission_info["dc_converged"])
            # 最大單棒超標倍數（>3 會觸發「荒謬超標」警告 = 明確標記無合法解）
            wr = 0.0
            for vnb in burns:
                wr = max(wr, float(np.linalg.norm(np.asarray(vnb, dtype=float))) / max_dv)
            rec["worst_burn_ratio"] = round(wr, 2)
            rec["flagged_infeasible"] = bool(wr > 3.0 or mission_info["penalty_count"] > 0)
    except SystemExit as exc:
        # config_validator 對非法輸入的預期拒絕（例如雙曲線沒給 T_MAX_SEC）——這是
        # 設計內的 fail-fast，不算崩潰，但要記下來。
        rec["outcome"] = "rejected"
        rec["detail"] = str(exc)
    except Exception as exc:
        rec["outcome"] = "crash"                 # 這才是真正的問題
        rec["exc_type"] = type(exc).__name__
        rec["detail"] = str(exc)
        rec["traceback"] = traceback.format_exc()[-1500:]
    return rec


def verdict(rec):
    """把 outcome 對照 expect 轉成一句人看的結論。"""
    o, e = rec["outcome"], rec["expect"]
    if o == "crash":
        return "❌ 崩潰（uncaught）"
    if o == "solution":
        if e == "feasible" and rec.get("penalty_count", 0) == 0:
            return "✅ 找到合法解"
        if rec.get("flagged_infeasible"):
            return "✅ 有標記的違規解（優雅降級）"
        return "✅ 有解（未觸發違規標記）"
    if o == "empty":
        if rec.get("any_case_had_solution"):
            return "⚠️ 空手回 None，但其實有 case 有解 → 該回最佳努力解"
        return "◽ 全軍覆沒、乾淨回 None（可接受）"
    if o == "rejected":
        return "◽ 設計內拒絕（fail-fast）"
    return "? " + o


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--geometry", choices=list(GEOMS))
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--out", default=RESULTS)
    args = ap.parse_args()

    if args.list:
        print(" ".join(GEOMS))
        return
    if not args.geometry:
        ap.error("需要 --geometry 或 --list")

    print(f"\n{'='*60}\nHAP-26 降級稽核：{args.geometry}（預期 {GEOMS[args.geometry]['expect']}）\n{'='*60}")
    rec = audit_one(args.geometry)

    data = []
    if os.path.exists(args.out):
        try:
            with open(args.out) as f:
                data = json.load(f)
        except Exception:
            data = []
    data = [r for r in data if r.get("geometry") != args.geometry]   # 同名覆蓋，重跑不堆疊
    data.append(rec)
    with open(args.out, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n{'─'*60}")
    print(f"  {args.geometry:<18} {verdict(rec)}")
    extra = {k: rec[k] for k in ("score", "penalty_count", "worst_burn_ratio",
                                 "num_burns", "dc_converged", "exc_type") if k in rec}
    if extra:
        print(f"  細節：{extra}")
    print(f"  已寫入 {os.path.basename(args.out)}")


if __name__ == "__main__":
    main()
