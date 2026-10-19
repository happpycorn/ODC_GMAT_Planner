"""全攝動 B 平面重瞄準的端到端測試：真的呼叫 GmatConsole（找不到就略過，不算失敗）。

情境是一棒的 LEO 攔截（B 7000 km → A 7100 km、傾角差 0.1°，2900 s 轉移，153 m/s），
Python 端在 J2–J4 下打靶到離 A 3.5 km（跟正式管線的瞄準方式一樣）。兩個案例：
1. 單棒上限 250 m/s：重瞄準應該通過，產生全攝動固定燃燒繳交腳本，GMAT 驗證命中。
2. 同一方案但單棒上限 160 m/s：重瞄準後那棒約 164 m/s → 失格 → 保留原方案、不產繳交腳本。
每個案例 3–4 個 GMAT 行程、串行執行（同時只有一個），合計約 20 秒。

GmatConsole 的位置依序找：環境變數 GMAT_CONSOLE → configs/config.json 的
local.gmat_console_path → 開發機的預設安裝路徑。
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import main as app
from src.pipeline_artifacts import save_mission
from src.runlog import setup
from src.scorer import calculate_score

DEFAULT_CONSOLE = "/home/corn/software/GMAT/GMAT/R2026a/bin/GmatConsole"
FAILS = []


def check(desc, ok):
    print(("  PASS  " if ok else "  FAIL  ") + desc)
    if not ok:
        FAILS.append(desc)


def find_console():
    cands = [os.environ.get("GMAT_CONSOLE")]
    try:
        cfg = json.loads((ROOT / "configs" / "config.json").read_text(encoding="utf-8"))
        cands.append(cfg.get("local", {}).get("gmat_console_path"))
    except (OSError, ValueError):
        pass
    cands.append(DEFAULT_CONSOLE)
    return next((c for c in cands if c and os.path.isfile(c)), None)


def make_mission(path, max_dv_mps):
    # 打靶數值由 J2–J4 的 propagate_dop853 + Lambert + Newton 求得（離 A 3.500 km）
    cfg = copy.deepcopy(app.DEFAULT_CONFIG)
    cfg["orbit_A"] = {"SMA": 7100.0, "ECC": 0.0, "INC": 28.6, "RAAN": 0.0, "AOP": 0.0, "TA": 358.0}
    cfg["orbit_B"] = {"SMA": 7000.0, "ECC": 0.0005, "INC": 28.5, "RAAN": 0.0, "AOP": 0.0, "TA": 0.0}
    cfg["rules"].update(MAX_DV_MPS=max_dv_mps, MAX_TOTAL_DV_MPS=3000.0)
    cfg["strategy"]["GRAVITY_DEGREE"] = 4
    o = app.MissionOptimizer(cfg)
    dv = 153.1487
    mi = {"x": [300.0, 0.0, 0.0, 0.0, 0.0], "num_burns": 1,
          "score": float(calculate_score(3.5, 3200.0, dv, 0, o.k_t, o.C_t, o.k_v, o.C_v)),
          "miss_km": 3.5, "total_dv_mps": dv, "T_team": 3200.0, "penalty_count": 0,
          "over_dv_count": 0, "disqualified": False, "dq_reasons": [], "dc_converged": True,
          "earth_safe": True, "aim_point": [-6931.156256526555, -1282.8697138999337, -709.1402767549347],
          "final_burn_dv_mps": dv, "min_arc_radius_km": 7000.0}
    burns = [(0.021482683192711106, 0.008781615388229944, 0.15137998610769107)]
    save_mission(path, cfg, burns, [300.0, 2900.0], mi)
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(console, root, name, max_dv_mps):
    src = root / f"{name}_src" / "mission.json"
    sha = make_mission(src, max_dv_mps)
    folder = root / name
    app.main(["--from-mission", str(src), "--retarget-full-perturbation", "--gmat-console", console,
              "--run-dir", str(folder), "-q"])
    setup()
    rec = json.loads((folder / "retarget.json").read_text(encoding="utf-8"))
    check(f"{name}：原 mission.json 沒被改動", hashlib.sha256(src.read_bytes()).hexdigest() == sha)
    return folder, rec


def main():
    console = find_console()
    if console is None:
        print("SKIP：找不到 GmatConsole（設 GMAT_CONSOLE 或 configs/config.json 的 local.gmat_console_path）")
        return 0
    print(f"=== 全攝動 B 平面重瞄準端到端（{console}）===")
    with tempfile.TemporaryDirectory(prefix="odc-retarget-e2e-") as d:
        root = Path(d)
        folder, rec = run(console, root, "accept", 250.0)
        res = rec["result"]
        orig = res["original"]["replay"]
        print(f"  原方案全攝動 d_min {orig.get('d_min_km', float('nan')):.4f} km")
        check("通過（accepted）", rec["status"] == "accepted" and res["accepted"])
        check("DC 收斂且 ≤ 10 次迭代", res["dc"]["converged"] and (res["dc"]["iterations"] or 99) <= 10)
        rt = res.get("retargeted", {})
        print(f"  重瞄準後 d_min {rt.get('d_min_km', float('nan')):.4f} km，"
              f"單棒 {rt.get('burn_change', {}).get('new_mps', float('nan')):.3f} m/s")
        check("重瞄準後 d_min ≤ 5 km", rt.get("d_min_km", 99.0) <= 5.0)
        check("單棒 ≤ 250 m/s、不失格", not rt["legality"]["disqualified"]
              and max(rt["legality"]["burn_dv_mps"]) <= 250.0)
        fixed = res["fixed_script_verification"]
        check("全攝動固定燃燒繳交腳本 GMAT 驗證命中且末棒合規",
              bool(fixed) and fixed["intercept_success"] and fixed["final_burn_legal"])
        check("繳交腳本自報的 Δr 跟密集重播的 d_min 差 < 50 m",
              bool(fixed) and abs(fixed["miss_km"] - rt["d_min_km"]) < 0.05)
        sub = (folder / "output_submit.txt").read_text(encoding="ascii")
        check("繳交腳本是全攝動模型、沒有求解器",
              "EGM96.cof" in sub and "NRLMSISE00" in sub and "Target DC_Targeter" not in sub)

        folder, rec = run(console, root, "reject", 160.0)
        res = rec["result"]
        print(f"  reasons: {res['reasons']}")
        check("單棒上限 160 m/s：重瞄準失格 → rejected", rec["status"] == "rejected"
              and any("失格" in r for r in res["reasons"]))
        check("rejected 不產生繳交腳本", not (folder / "output_submit.txt").exists()
              and rec["submission_script"] is None)
        check("run.log 有保留原方案的警告",
              "保留原方案" in (folder / "run.log").read_text(encoding="utf-8"))
    if FAILS:
        print(f"\n❌ {len(FAILS)} 項失敗")
        return 1
    print("\n✅ 全部通過")
    return 0


if __name__ == "__main__":
    sys.exit(main())
