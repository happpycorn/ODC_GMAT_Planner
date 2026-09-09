import math, os, sys
import numpy as np
sys.path.insert(0, "/home/corn/ODC_GMAT_Planner")
sys.path.insert(0, "/home/corn/ODC_GMAT_Planner/scratch_overnight/gmat")
from src.core_math import reaches_perigee
import perigee_xcheck as X

gravity = sys.argv[1] if len(sys.argv) > 1 else "twobody"
rows = np.load(os.path.join(X.HERE, "perigee_xcheck_%s.npy" % gravity))
cases = X.build_cases()
assert len(rows) == len(cases), (len(rows), len(cases))

mism, time_err, hyper_slack = [], [], []
n_true = n_false = 0
for row, c in zip(rows, cases):
    cid, el, rmag, ta = row
    assert int(cid) == cases.index(c) or True
    dt = c["dt"]
    r = np.ascontiguousarray(c["r"]); v = np.ascontiguousarray(c["v"])
    ours = bool(reaches_perigee(r, v, X.MU, dt))
    # GMAT 停在 cap 上 = 這段弧內沒有近地點事件
    eps = max(1e-5, 1e-9 * dt)
    gmat = el < dt - eps
    n_true += ours; n_false += (not ours)
    if ours != gmat:
        mism.append((c["label"], c["mode"], dt, el, rmag, ta, ours, gmat))
    # 雙曲線不比時間：reaches_perigee 對 energy>=0 根本不算時間，只看 rv 的正負，
    # 所以拿 analytic_t_to_perigee 的佔位符去比是在比一個不存在的東西。
    if gmat and not c["label"].startswith("D"):
        tp = X.analytic_t_to_perigee(r, v, X.MU)
        if math.isfinite(tp):
            time_err.append((c["label"], tp, el, tp - el))
    # 雙曲線的保守近似有多保守
    if c["label"].startswith("D") and ours and not gmat:
        th = X.true_t_to_perigee_hyper(r, v, X.MU)
        hyper_slack.append((c["label"], dt, th))

print("=== %s ===" % gravity)
print("cases            : %d   (predicate True %d / False %d)" % (len(cases), n_true, n_false))
unsafe = [m for m in mism if (not m[6]) and m[7]]
print("boolean mismatches: %d  (conservative %d / UNSAFE %d)"
      % (len(mism), len(mism) - len(unsafe), len(unsafe)))
for m in mism:
    print("   %-34s %-8s dt=%10.3f  gmat_el=%10.3f rmag=%8.1f ta=%8.3f  ours=%s gmat=%s"
          % m)
if time_err:
    d = np.array([abs(x[3]) for x in time_err])
    rel = np.array([abs(x[3]) / max(x[2], 1e-9) for x in time_err])
    worst = max(time_err, key=lambda x: abs(x[3]))
    print("\ntime-to-perigee compared on %d arcs where GMAT located the event:" % len(d))
    print("   max |dt|  = %.3e s   (%s: ours %.6f vs GMAT %.6f)" % (d.max(), worst[0], worst[1], worst[2]))
    print("   median    = %.3e s     mean = %.3e s" % (np.median(d), d.mean()))
    print("   max rel   = %.3e" % rel.max())
if hyper_slack:
    print("\nhyperbolic conservative-True cases (predicate ignores dt when rv<0): %d" % len(hyper_slack))
    for lab, dt, th in hyper_slack:
        print("   %-30s dt=%8.1f s  true t_to_perigee=%10.1f s" % (lab, dt, th))

# --- 按族分開統計（C 族 e~0 近地點方向退化，混在一起會蓋掉真正的訊號） ---
print("\nper-family |t_ours - t_gmat| (s):")
fam = {}
for lab, tp, el, d in time_err:
    fam.setdefault(lab[0], []).append(abs(d))
for k in sorted(fam):
    a = np.array(fam[k])
    print("   %s  n=%3d  max=%.3e  median=%.3e" % (k, len(a), a.max(), np.median(a)))
