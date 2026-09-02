"""HAP-25：量最壞情況 runtime 上界 + 降級旋鈕的邊際效果。

比賽是**固定 90 分鐘**（14:00–15:30），而且那 90 分鐘要塞下建 config、跑搜尋、GMAT
驗證、繳交。這支只量「搜尋」那一段（run_study，不含 GMAT），因為那是唯一會爆時間、
也是唯一能靠旋鈕降級的部分。目的有二：
  (1) 量出最壞情況搜尋要跑多久（上界）；
  (2) 量 CONTEST_DAY 寫的降級順序 MAX_BURNS → popsize/iters → LAMBERT_MAX_REVS
      每一格各買回多少時間，好在當天照數字退。

刻意設計成「一次一個 (場景, 旋鈕檔)」跑：符合「一次只跑一個吃 CPU 的工作」的規則，
也讓我逐步看數字、遇到病態情境能停。JIT 先暖機再計時，量到的是純搜尋時間，不含
一次性的 numba 編譯（編譯成本另外單獨回報）。

跑法：
  uv run python scratch_overnight/runtime_ceiling.py --scenario hard_mode --level full
  uv run python scratch_overnight/runtime_ceiling.py --scenario hard_mode --level deg_burns2
結果附加到 scratch_overnight/runtime_ceiling_results.json
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import warnings
warnings.filterwarnings("ignore")

from src.optimizer import MissionOptimizer

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "runtime_ceiling_results.json")

# ── 場景幾何：從易到最壞。runtime 由幾何 + T_max 決定，跟計分參數幾乎無關，
#    所以 k/C 用一組通用值就好（不影響計時，只影響分數數字）。────────────────
SCENARIOS = {
    # 初賽最實際的「最壞」：官方唯一公布的範例題（A 圓軌道、傾角差大）。初賽 A 是圓
    # 軌道，這組最能代表當天真的會遇到的難度上緣。
    "official_sample": {
        "A": {"SMA": 6978.0, "ECC": 0.0, "INC": 45.0, "RAAN": 0.0, "AOP": 0.0, "TA": 0.0},
        "B": {"SMA": 6878.0, "ECC": 0.0, "INC": 135.0, "RAAN": 30.0, "AOP": 0.0, "TA": 60.0},
    },
    # 中等難度、有離心率。
    "playground": {
        "A": {"SMA": 13000.0, "ECC": 0.3, "INC": 28.0, "RAAN": 60.0, "AOP": 40.0, "TA": 150.0},
        "B": {"SMA": 7200.0, "ECC": 0.02, "INC": 0.0, "RAAN": 0.0, "AOP": 0.0, "TA": 0.0},
    },
    # 絕對最壞之一：能量門檻 + 巨大 SMA（A SMA 十萬 → T_max ~14.5 天），早停不會救，
    # 每次評估的長弧積分也貴。
    "hard_mode": {
        "A": {"SMA": 100000.0, "ECC": 0.5, "INC": 63.4, "RAAN": 40.0, "AOP": 270.0, "TA": 0.0},
        "B": {"SMA": 6800.0, "ECC": 0.001, "INC": 0.0, "RAAN": 0.0, "AOP": 0.0, "TA": 0.0},
    },
    # 絕對最壞之二：窄窗 + 極端偏心（A SMA 15 萬 / ECC 0.93 → T_max ~27 天，深近地點
    # 讓自適應積分器狂加步數）。L-SHADE 跑滿預算都撞不到，runtime 跑好跑滿。
    "weird_test": {
        "A": {"SMA": 150000.0, "ECC": 0.93, "INC": 175.0, "RAAN": 270.0, "AOP": 333.0, "TA": 17.0},
        "B": {"SMA": 6800.0, "ECC": 0.001, "INC": 98.0, "RAAN": 45.0, "AOP": 0.0, "TA": 200.0},
    },
}

# ── 旋鈕檔：full = 當天完整設定；deg_* = 各降級旋鈕「單獨」套用，好看每格的邊際效果。
#    降級順序照 CONTEST_DAY §五/§九：MAX_BURNS → popsize/iters → LAMBERT_MAX_REVS。────
FULL_OPT = {"MAX_BURNS": [1, 2, 3], "MAXITER": 600, "POPSIZE": 20,
            "NUM_THREADS": -1, "MAX_EARLY_STOP": 60, "TOL": 0.01}
FULL_REVS = 4


def opt_for_level(level):
    """回傳 (optimization dict, lambert_max_revs)。每格降級單獨套在 full 上，不累加，
    這樣表格讀得出「這一格自己買回多少」。"""
    o = dict(FULL_OPT)
    revs = FULL_REVS
    if level == "full":
        pass
    elif level == "deg_burns2":          # 第一格：砍掉 3 棒
        o["MAX_BURNS"] = [1, 2]
    elif level == "deg_burns1":          # 更狠：只留單棒
        o["MAX_BURNS"] = [1]
    elif level == "deg_popiter":         # 第二格：族群/世代減半
        o["POPSIZE"] = 10
        o["MAXITER"] = 300
    elif level == "deg_revs0":           # 第三格：關多圈 Lambert
        revs = 0
    else:
        raise SystemExit(f"未知 level: {level}")
    return o, revs


def build_config(scenario, level, seed):
    geo = SCENARIOS[scenario]
    o, revs = opt_for_level(level)
    opt = dict(o)
    opt["SEED"] = seed
    return {
        "orbit_A": geo["A"], "orbit_B": geo["B"],
        "rules": {"MAX_DV_MPS": 1500.0, "MIN_MANEUVER_INTERVAL_SEC": 100.0,
                  "T_MAX_PERIOD_MULTIPLE": 4.0,
                  "k_t": 0.0005, "C_t": 3212.0, "k_v": 0.002, "C_v": 2241.0},
        "strategy": {"GRAVITY_DEGREE": 4, "MISS_TOLERANCE_KM": 5.0,
                     "LAMBERT_MAX_REVS": revs},
        "optimization": opt,
    }


def jit_warmup():
    """先用一個便宜情境把 numba 全部編譯起來，計時才不會把一次性編譯算進去。"""
    cfg = {
        "orbit_A": {"SMA": 7000.0, "ECC": 0.0, "INC": 10.0, "RAAN": 0.0, "AOP": 0.0, "TA": 0.0},
        "orbit_B": {"SMA": 6900.0, "ECC": 0.0, "INC": 0.0, "RAAN": 0.0, "AOP": 0.0, "TA": 30.0},
        "rules": {"MAX_DV_MPS": 1500.0, "MIN_MANEUVER_INTERVAL_SEC": 100.0,
                  "T_MAX_PERIOD_MULTIPLE": 4.0,
                  "k_t": 0.0005, "C_t": 3212.0, "k_v": 0.002, "C_v": 2241.0},
        "strategy": {"GRAVITY_DEGREE": 4, "MISS_TOLERANCE_KM": 5.0, "LAMBERT_MAX_REVS": 4},
        "optimization": {"MAX_BURNS": [1, 2, 3], "MAXITER": 3, "POPSIZE": 4,
                         "NUM_THREADS": 1, "MAX_EARLY_STOP": 3, "TOL": 0.01, "SEED": 0},
    }
    t0 = time.perf_counter()
    MissionOptimizer(cfg).run_study()
    return time.perf_counter() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", required=True, choices=list(SCENARIOS))
    ap.add_argument("--level", default="full",
                    choices=["full", "deg_burns2", "deg_burns1", "deg_popiter", "deg_revs0"])
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--maxiter", type=int, default=None,
                    help="覆寫 MAXITER，用低代數當探針再線性外推到 600（早停不觸發、各代等成本，"
                         "外推有效）")
    ap.add_argument("--out", default=RESULTS)
    args = ap.parse_args()

    print(f"\n{'='*66}\nHAP-25 runtime 量測：scenario={args.scenario}  level={args.level}  "
          f"seed={args.seed}  cores={os.cpu_count()}\n{'='*66}")

    print("→ JIT 暖機中（不計入搜尋時間）...")
    warmup_s = jit_warmup()
    print(f"  一次性 JIT/暖機成本 ≈ {warmup_s:.1f}s")

    cfg = build_config(args.scenario, args.level, args.seed)
    probe_maxiter = None
    if args.maxiter is not None:
        probe_maxiter = cfg["optimization"]["MAXITER"]      # 原本要外推到的目標代數
        cfg["optimization"]["MAXITER"] = args.maxiter
    opt = MissionOptimizer(cfg)
    print(f"→ T_max = {opt.T_max:,.0f}s ({opt.T_max/86400:.2f} 天)；"
          f"MAX_BURNS={cfg['optimization']['MAX_BURNS']}  POPSIZE={cfg['optimization']['POPSIZE']}  "
          f"MAXITER={cfg['optimization']['MAXITER']}  REVS={cfg['strategy']['LAMBERT_MAX_REVS']}")

    t0 = time.perf_counter()
    burns, times, mission_info = opt.run_study()
    search_s = time.perf_counter() - t0

    # 每個 burn case 跑了幾代 / 是否早停（跑不滿代 = 早停救了它）
    per_case = {}
    for b, rec in sorted(opt.burn_case_results.items()):
        budget = opt._maxiter_for(b)
        ran = rec.get("epochs_run", None)
        per_case[b] = {"epochs_run": ran, "budget": budget,
                       "early_stopped": (ran is not None and ran < budget)}
    score = float(mission_info["score"]) if mission_info else None

    record = {
        "scenario": args.scenario, "level": args.level, "seed": args.seed,
        "cores": os.cpu_count(),
        "T_max_days": round(opt.T_max / 86400, 2),
        "maxiter_ran": args.maxiter if args.maxiter is not None else cfg["optimization"]["MAXITER"],
        "maxiter_target": probe_maxiter,     # 非 None 代表這是探針、要外推到這個代數
        "search_sec": round(search_s, 1),
        "warmup_sec": round(warmup_s, 1),
        "wall_incl_jit_sec": round(search_s + warmup_s, 1),
        "score": None if score is None else round(score, 2),
        "max_burns": cfg["optimization"]["MAX_BURNS"],
        "popsize": cfg["optimization"]["POPSIZE"],
        "maxiter": cfg["optimization"]["MAXITER"],
        "lambert_revs": cfg["strategy"]["LAMBERT_MAX_REVS"],
        "per_case": per_case,
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    data = []
    if os.path.exists(args.out):
        try:
            with open(args.out) as f:
                data = json.load(f)
        except Exception:
            data = []
    data.append(record)
    with open(args.out, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n{'─'*66}")
    print(f"⏱  搜尋 {search_s:.1f}s（+ 一次性 JIT {warmup_s:.1f}s = 端到端 {search_s+warmup_s:.1f}s）  "
          f"分數 {record['score']}")
    es = [f"{b}棒={c['epochs_run']}/{c['budget']}{'(早停)' if c['early_stopped'] else '(跑滿)'}"
          for b, c in per_case.items()]
    print(f"   各案例世代：{'  '.join(es)}")
    print(f"   已附加到 {os.path.basename(args.out)}")


if __name__ == "__main__":
    main()
