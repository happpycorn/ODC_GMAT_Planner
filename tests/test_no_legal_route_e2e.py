"""找不到合法路線的 e2e（`uv run python tests/test_no_legal_route_e2e.py`）。

真的用子行程跑一次 main.py：hyperbolic_test 幾何、排位賽規則，但總 Δv 上限設 300 m/s——
低於這個幾何的能量下限（~697 m/s），所以不可能有合法路線。驗證：
  * 結束碼 3（EXIT_NO_LEGAL_ROUTE），不是一般錯誤的 1
  * run 目錄有 no_legal_route.json（含違規量），沒有 mission.json、沒有任何腳本
  * log 明講「找不到合法路線」並給下一步建議
單元層級（不跑搜尋）的檢查在 tests/test_ranking_penalty_v2.py 第 7 塊。
"""
SLOW = True  # 子行程完整跑一次極小預算的 main.py（import + numba 讀快取 + 搜尋），約 20–60 秒。

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FAILS = []


def check(name, cond):
    print(("  ✅ " if cond else "  ❌ ") + name)
    if not cond:
        FAILS.append(name)


cfg = json.loads((ROOT / "configs" / "shared" / "hyperbolic_test.json").read_text(encoding="utf-8"))
cfg["rules"].update({"MAX_DV_MPS": 250.0, "MAX_TOTAL_DV_MPS": 300.0})
cfg["optimization"].update({"MAXITER": 3, "POPSIZE": 2, "MAX_BURNS": [1, 2], "SEED": 0, "NUM_THREADS": 2})
cfg["strategy"].update({"REVS_ENSEMBLE": False})

print("── main.py 子行程：總 Δv 上限 300 m/s < 能量下限 ──")
with tempfile.TemporaryDirectory() as td:
    cfg_path = Path(td) / "cfg.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    run_dir = Path(td) / "run"
    proc = subprocess.run([sys.executable, "main.py", "--config", str(cfg_path), "--run-dir", str(run_dir),
                           "--stop-after", "solve"],
                          cwd=ROOT, capture_output=True, text=True, timeout=600)
    out = proc.stdout + proc.stderr
    check(f"結束碼 3（實際 {proc.returncode}）", proc.returncode == 3)
    check("沒有 Python traceback", "Traceback" not in out)
    log_text = (run_dir / "run.log").read_text(encoding="utf-8") if (run_dir / "run.log").exists() else ""
    check("log 明講「找不到合法路線」", "找不到合法路線" in log_text)
    check("log 有下一步建議（MAXITER、feasibility.py）", "MAXITER" in log_text and "feasibility.py" in log_text)
    produced = sorted(p.name for p in run_dir.iterdir()) if run_dir.exists() else []
    check(f"有 no_legal_route.json、沒有 mission.json / 腳本（{produced}）",
          "no_legal_route.json" in produced and "mission.json" not in produced
          and not any(n.endswith(".script") for n in produced))
    if "no_legal_route.json" in produced:
        d = json.loads((run_dir / "no_legal_route.json").read_text(encoding="utf-8"))
        v = d["violations"]
        check(f"違規量：總 Δv {v['total_dv_mps']:,.1f} 超上限 300 的量 = {v['total_dv_excess_mps']:,.1f}",
              v["max_total_dv_mps"] == 300.0
              and abs(v["total_dv_excess_mps"] - (v["total_dv_mps"] - 300.0)) < 1e-6
              and v["total_dv_excess_mps"] > 0.0)
        check("per_burn_dv_mps 與 burns 一樣長", len(v["per_burn_dv_mps"]) == len(d["burns"]))
    run_json = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    check("run.json status = no_legal_route", run_json.get("status") == "no_legal_route")
    if FAILS:
        print(out[-3000:])

print()
if FAILS:
    print(f"❌ {len(FAILS)} 項失敗：" + "、".join(FAILS))
    sys.exit(1)
print("✅ 全部通過")
