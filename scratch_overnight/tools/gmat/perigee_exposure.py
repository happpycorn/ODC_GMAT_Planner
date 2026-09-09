"""量「漏掉的近地點通過」到底暴露多少半徑。

背景：J2 交叉檢查在 i > 63.4 度找到 16 組 ours=False / GMAT=True —— 判斷式說
「這段弧不經過近地點」，但攝動下實際經過了，於是 check_constraints 被跳過。

但跳過不代表沒檢查：不經過近地點的分支改成檢查兩個端點的半徑。所以真正的問題是
**終點半徑比真近地點高多少** —— 那個差值就是安檢的漏洞寬度。拿 GMAT 量。
"""
import math, os, sys
import numpy as np
sys.path.insert(0, "/home/corn/ODC_GMAT_Planner")
sys.path.insert(0, "/home/corn/ODC_GMAT_Planner/scratch_overnight/gmat")
from src.core_math import reaches_perigee
import perigee_xcheck as X

rows = np.load(os.path.join(X.HERE, "perigee_xcheck_j2.npy"))
cases = X.build_cases()

# 找出所有不安全方向的案例
unsafe = []
for row, c in zip(rows, cases):
    cid, el, rmag_p, ta = row
    dt = c["dt"]
    r = np.ascontiguousarray(c["r"]); v = np.ascontiguousarray(c["v"])
    ours = bool(reaches_perigee(r, v, X.MU, dt))
    gmat = el < dt - max(1e-5, 1e-9 * dt)
    if (not ours) and gmat:
        unsafe.append({"case": c, "t_peri": el, "r_peri": rmag_p, "late": dt - el})
print("unsafe-direction cases: %d" % len(unsafe))

# 用 GMAT 把同一組狀態剛好飛 dt 秒，量終點半徑
ep_cases = [dict(u["case"], mode="ENDPOINT") for u in unsafe]
sp = os.path.join(X.HERE, "perigee_exposure.script")
rp = os.path.join(X.HERE, "perigee_exposure.report")

def write_endpoint_script(cs, script_path, report_path):
    L = ["% Endpoint radius after propagating exactly dt (J2/J3/J4). ASCII only.", "",
         "Create Spacecraft Sat",
         "GMAT Sat.DateFormat = TAIModJulian", "GMAT Sat.Epoch = '21545'",
         "GMAT Sat.CoordinateSystem = EarthMJ2000Eq",
         "GMAT Sat.DisplayStateType = Cartesian", "",
         "Create ForceModel FM", "GMAT FM.CentralBody = Earth",
         "GMAT FM.PrimaryBodies = {Earth}",
         "GMAT FM.GravityField.Earth.PotentialFile = 'JGM2.cof'",
         "GMAT FM.GravityField.Earth.Degree = 4",
         "GMAT FM.GravityField.Earth.Order = 0",
         "GMAT FM.Drag = None", "GMAT FM.SRP = Off", "",
         "Create Propagator Prop", "GMAT Prop.FM = FM",
         "GMAT Prop.Type = RungeKutta89", "GMAT Prop.InitialStepSize = 1",
         "GMAT Prop.Accuracy = 1e-13", "GMAT Prop.MinStep = 0", "GMAT Prop.MaxStep = 600", "",
         "Create ReportFile rf", "GMAT rf.Filename = '%s'" % report_path,
         "GMAT rf.Precision = 16", "GMAT rf.WriteHeaders = false",
         "GMAT rf.ColumnWidth = 26", "",
         "Create Variable cid t0 t1 el", "", "BeginMissionSequence", ""]
    for i, c in enumerate(cs):
        L.append("%% case %d %s" % (i, c["label"]))
        for n, val in zip(("X", "Y", "Z"), c["r"]):
            L.append("GMAT Sat.%s = %.17g" % (n, val))
        for n, val in zip(("VX", "VY", "VZ"), c["v"]):
            L.append("GMAT Sat.%s = %.17g" % (n, val))
        L.append("GMAT cid = %d" % i)
        L.append("GMAT t0 = Sat.TAIModJulian")
        L.append("Propagate Prop(Sat) {Sat.ElapsedSecs = %.17g}" % c["dt"])
        L.append("GMAT t1 = Sat.TAIModJulian")
        L.append("GMAT el = (t1 - t0) * 86400")
        L.append("Report rf cid el Sat.RMAG Sat.Earth.TA")
        L.append("")
    txt = "\n".join(L) + "\n"
    txt.encode("ascii")
    open(script_path, "w").write(txt)

write_endpoint_script(ep_cases, sp, rp)
erows, out, err = X.run_gmat(sp, rp)
print("endpoint rows: %d" % len(erows))

print("\n%-34s %8s %8s %11s %11s %10s" % ("case", "dt", "late_s", "r_perigee", "r_endpoint", "exposure_m"))
worst = 0.0
for u, er in zip(unsafe, erows):
    c = u["case"]
    r_end = er[2]
    expo = (r_end - u["r_peri"]) * 1000.0
    worst = max(worst, expo)
    print("%-34s %8.1f %8.2f %11.3f %11.3f %10.1f"
          % (c["label"], c["dt"], u["late"], u["r_peri"], r_end, expo))
print("\nWORST exposure: %.1f m   (MIN_PERIAPSIS margin is RE+100 km = 100000 m)" % worst)
print("ratio to the 100 km safety margin: %.2e" % (worst / 100000.0))
