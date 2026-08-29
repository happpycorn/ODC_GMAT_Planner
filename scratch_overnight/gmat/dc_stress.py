"""DC 演算法比較，但要先讓 targeter 真的有事做。

第一版比不出東西：Python 給的初始猜測誤差只有 2.3 m，已經在 Achieve 容許 (10 m) 內，
DC 第一次 nominal pass 就收斂，五種演算法輸出位元相同。

所以這裡故意把初始猜測打歪 —— 那正是比賽當天真正的失效模式（Python 端算歪了，
要靠 GMAT 的 targeter 救回來）。另外也測把容許收到 0.1 m，逼它做真正的迭代。
"""
import os, re, subprocess, time

GMAT_BIN = "/home/corn/software/GMAT/GMAT/R2026a/bin/GmatConsole"
HERE = "/home/corn/ODC_GMAT_Planner/scratch_overnight/gmat"
BASE = "/home/corn/ODC_GMAT_Planner/outputs/output.txt"

ALGOS = [
    ("NR_fwd",   ["GMAT DC_Targeter.Algorithm = 'NewtonRaphson';",
                  "GMAT DC_Targeter.DerivativeMethod = 'ForwardDifference';"]),
    ("NR_ctr",   ["GMAT DC_Targeter.Algorithm = 'NewtonRaphson';",
                  "GMAT DC_Targeter.DerivativeMethod = 'CentralDifference';"]),
    ("NR_bwd",   ["GMAT DC_Targeter.Algorithm = 'NewtonRaphson';",
                  "GMAT DC_Targeter.DerivativeMethod = 'BackwardDifference';"]),
    ("Broyden",  ["GMAT DC_Targeter.Algorithm = 'Broyden';"]),
    ("ModBroy",  ["GMAT DC_Targeter.Algorithm = 'ModifiedBroyden';"]),
]
VARY_RE = re.compile(r"(Vary DC_Targeter\(BurnB2\.Element(\d)\s*=\s*)(-?[\d.eE+]+)(,)")
ACH_RE = re.compile(r"(Achieve DC_Targeter\([^,]+,\s*\{Tolerance\s*=\s*)([\d.eE+-]+)(\})")
base = open(BASE, encoding="utf-8").read()
base.encode("ascii")
anchor = "Create DifferentialCorrector DC_Targeter;"


def build(algo_lines, perturb, tol):
    txt = base.replace(anchor, anchor + "\n" + "\n".join(algo_lines))
    # 把初始猜測按元素號輪流 +/- 打歪，避免三個同向剛好變成純量縮放
    def bump(m):
        sign = 1.0 if int(m.group(2)) % 2 else -1.0
        return "%s%.9g%s" % (m.group(1), float(m.group(3)) * (1.0 + sign * perturb), m.group(4))
    txt = VARY_RE.sub(bump, txt)
    if tol is not None:
        txt = ACH_RE.sub(lambda m: "%s%g%s" % (m.group(1), tol, m.group(3)), txt)
    return txt


def run(name, txt):
    rep = os.path.join(HERE, "dcs_%s.report" % name)
    txt = re.sub(r"Report_Intercept\.Filename = '[^']*';",
                 "Report_Intercept.Filename = '%s';" % rep, txt)
    txt.encode("ascii")
    sp = os.path.join(HERE, "dcs_%s.script" % name)
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
                pass
    m = re.search(r"Targeting Completed in (\d+) iterations", p.stdout)
    iters = int(m.group(1)) if m else -1
    conv = "The Targeter converged!" in p.stdout
    return row, wall, iters, conv


print("%-9s %-7s %-9s %9s %10s %6s %6s %7s" %
      ("algo", "perturb", "tol_km", "miss_km", "dv_mps", "conv", "iters", "wall_s"))
for tol, perturbs in ((None, (0.0, 0.02, 0.10, 0.35)), (1e-4, (0.10,))):
    for perturb in perturbs:
        for name, lines in ALGOS:
            tag = "%s_p%03d_t%s" % (name, round(perturb * 100), "def" if tol is None else "tight")
            row, wall, iters, conv = run(tag, build(lines, perturb, tol))
            miss = row[1] if row else float("nan")
            dv = row[3] if row else float("nan")
            print("%-9s %-7s %-9s %9.5f %10.3f %6s %6d %7.1f"
                  % (name, "%.0f%%" % (perturb * 100),
                     "0.01" if tol is None else "%g" % tol,
                     miss, dv, "Y" if conv else "N", iters, wall))
        print()
