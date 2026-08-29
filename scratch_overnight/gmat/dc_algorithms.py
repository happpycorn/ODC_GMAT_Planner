"""DifferentialCorrector 的替代演算法：Broyden / ModifiedBroyden / 中央差分。

為什麼 (2026-08-29)：繳交腳本的 `Create DifferentialCorrector DC_Targeter;` 一直吃
GMAT 預設值 = NewtonRaphson + ForwardDifference。文件寫 Algorithm 還可以設
Broyden / ModifiedBroyden，DerivativeMethod 還可以設 Central/BackwardDifference。
比賽當天最怕的是 Targeter 在某個情境不收斂，多知道一組備援設定就是保險。

基準腳本用我們自己產生的官方範例題目 normal variant（outputs/output.txt）。
"""
import os, re, subprocess, sys, time

GMAT_BIN = "/home/corn/software/GMAT/GMAT/R2026a/bin/GmatConsole"
HERE = "/home/corn/ODC_GMAT_Planner/scratch_overnight/gmat"
BASE = "/home/corn/ODC_GMAT_Planner/outputs/output.txt"

VARIANTS = [
    ("baseline_NR_fwd",   ["GMAT DC_Targeter.Algorithm = 'NewtonRaphson';",
                           "GMAT DC_Targeter.DerivativeMethod = 'ForwardDifference';"]),
    ("NR_central",        ["GMAT DC_Targeter.Algorithm = 'NewtonRaphson';",
                           "GMAT DC_Targeter.DerivativeMethod = 'CentralDifference';"]),
    ("NR_backward",       ["GMAT DC_Targeter.Algorithm = 'NewtonRaphson';",
                           "GMAT DC_Targeter.DerivativeMethod = 'BackwardDifference';"]),
    ("Broyden",           ["GMAT DC_Targeter.Algorithm = 'Broyden';"]),
    ("ModifiedBroyden",   ["GMAT DC_Targeter.Algorithm = 'ModifiedBroyden';"]),
]

base = open(BASE, encoding="utf-8").read()
base.encode("ascii")          # 基準腳本本身必須是純 ASCII
anchor = "Create DifferentialCorrector DC_Targeter;"
assert anchor in base

results = []
for name, settings in VARIANTS:
    rep = os.path.join(HERE, "dc_%s.report" % name)
    txt = base.replace(anchor, anchor + "\n" + "\n".join(settings))
    txt = re.sub(r"Report_Intercept\.Filename = '[^']*';",
                 "Report_Intercept.Filename = '%s';" % rep, txt)
    assert rep in txt
    txt.encode("ascii")
    sp = os.path.join(HERE, "dc_%s.script" % name)
    open(sp, "w").write(txt)
    if os.path.exists(rep):
        os.remove(rep)
    t0 = time.time()
    p = subprocess.run([GMAT_BIN, "--run", sp], capture_output=True, text=True, timeout=1800)
    wall = time.time() - t0
    row = None
    if os.path.exists(rep):
        lines = [l for l in open(rep) if l.strip()]
        if len(lines) >= 2:
            try:
                row = [float(x) for x in lines[-1].split()]
            except ValueError:
                row = None
    # GMAT 會印出 targeter 的收斂訊息，從 stdout 撈迭代數
    it = len(re.findall(r"Iteration\s+\d+", p.stdout))
    converged = "converged" in p.stdout.lower() and "not converged" not in p.stdout.lower()
    results.append((name, row, wall, it, converged, p.stdout[-1200:]))

print("%-18s %10s %10s %8s %8s %7s %6s" %
      ("variant", "miss_km", "dv_mps", "success", "legal", "wall_s", "iters"))
for name, row, wall, it, conv, out in results:
    if row is None:
        print("%-18s %10s  ---- NO REPORT ----  wall=%.1f" % (name, "-", wall))
        continue
    _, miss, succ, dv, legal = row[0], row[1], row[2], row[3], row[4]
    print("%-18s %10.6f %10.3f %8.0f %8.0f %7.1f %6d"
          % (name, miss, dv, succ, legal, wall, it))

bad = [r for r in results if r[1] is None]
if bad:
    for name, _, _, _, _, out in bad:
        print("\n---- %s stdout tail ----\n%s" % (name, out))
