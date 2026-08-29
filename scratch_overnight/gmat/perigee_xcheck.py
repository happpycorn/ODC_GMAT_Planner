"""用 GMAT 自己的近地點事件定位，驗 `reaches_perigee()`。

為什麼 (2026-08-29)：`reaches_perigee()` 是昨晚修的那個值 16.5 分的 bug 的核心，
但它到目前為止只被「56 組暴力交叉檢查」驗過，而那個暴力檢查用的是**我們自己的
傳播器** —— 等於自己驗自己。GMAT 有內建的 `{Sat.Earth.Periapsis}` 停止條件，
是完全獨立的實作，這是目前驗證矩陣裡唯一還沒有外部基準的地方。

兩種模式：
  MEASURE  dt 開很大 -> GMAT 一定找得到近地點 -> 直接比「到近地點要幾秒」（定量）
  BOUNDARY dt = m x t_pred, m 在 1.0 附近 -> 比布林值（定性，測邊界）

另外跑一次 J2/J3/J4 版本，量「Kepler 預測」跟「實際攝動軌跡」差多少 ——
docstring 宣稱「J2 在 100 秒尺度上改不動這個判斷」，那目前只是主張，沒量過。
"""
import math
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, "/home/corn/ODC_GMAT_Planner")
from src.core_math import reaches_perigee  # noqa: E402

GMAT_BIN = "/home/corn/software/GMAT/GMAT/R2026a/bin/GmatConsole"
HERE = "/home/corn/ODC_GMAT_Planner/scratch_overnight/gmat"
MU = 398600.4418          # 跟 optimizer.py:343 一致
RE = 6378.1363

# --------------------------------------------------------------------------
# 軌道根數 -> 狀態向量（自己寫，不引入外部相依）
# --------------------------------------------------------------------------
def coe2rv(a, e, inc_deg, raan_deg, aop_deg, ta_deg, mu=MU):
    inc, raan, aop, nu = (math.radians(x) for x in (inc_deg, raan_deg, aop_deg, ta_deg))
    if e < 1.0:
        p = a * (1.0 - e * e)
    else:
        p = a * (1.0 - e * e)      # a<0 for hyperbola -> p>0
    r = p / (1.0 + e * math.cos(nu))
    r_pf = np.array([r * math.cos(nu), r * math.sin(nu), 0.0])
    v_pf = math.sqrt(mu / p) * np.array([-math.sin(nu), e + math.cos(nu), 0.0])
    cO, sO = math.cos(raan), math.sin(raan)
    ci, si = math.cos(inc), math.sin(inc)
    cw, sw = math.cos(aop), math.sin(aop)
    R = np.array([
        [cO * cw - sO * sw * ci, -cO * sw - sO * cw * ci,  sO * si],
        [sO * cw + cO * sw * ci, -sO * sw + cO * cw * ci, -cO * si],
        [sw * si,                 cw * si,                 ci],
    ])
    return R @ r_pf, R @ v_pf


def analytic_t_to_perigee(r, v, mu=MU):
    """跟 core_math.reaches_perigee 同一套數學，但回傳秒數而不是布林值。"""
    r_mag = float(np.linalg.norm(r))
    energy = float(v @ v) / 2.0 - mu / r_mag
    rv = float(r @ v)
    if energy >= 0.0:
        return 0.0 if rv < 0.0 else math.inf   # 函式對雙曲線的處理（見下方討論）
    a = -mu / (2.0 * energy)
    h = np.cross(r, v)
    e = math.sqrt(max(0.0, 1.0 + (2.0 * energy * float(h @ h)) / (mu * mu)))
    if e < 1e-12:
        return math.inf
    cos_E = min(1.0, max(-1.0, (1.0 - r_mag / a) / e))
    E = math.acos(cos_E)
    if rv < 0.0:
        E = 2.0 * math.pi - E
    M = E - e * math.sin(E)
    return (2.0 * math.pi - M) / math.sqrt(mu / (a ** 3))


def true_t_to_perigee_hyper(r, v, mu=MU):
    """雙曲線的真實到近地點時間（Kepler 的雙曲線版），用來檢查函式的保守近似。"""
    r_mag = float(np.linalg.norm(r))
    energy = float(v @ v) / 2.0 - mu / r_mag
    rv = float(r @ v)
    if energy < 0.0 or rv >= 0.0:
        return math.inf
    a = -mu / (2.0 * energy)               # a < 0
    h = np.cross(r, v)
    e = math.sqrt(1.0 + (2.0 * energy * float(h @ h)) / (mu * mu))
    cosh_H = (1.0 - r_mag / a) / e
    H = math.acosh(max(1.0, cosh_H))
    if rv < 0.0:
        H = -H                             # 進來的那一側 H<0
    M = e * math.sinh(H) - H
    n = math.sqrt(mu / (-a) ** 3)
    return -M / n                          # 近地點 M=0


# --------------------------------------------------------------------------
# 測試案例
# --------------------------------------------------------------------------
def build_cases():
    cases = []

    def add(label, r, v, dt, mode):
        cases.append({"label": label, "r": r, "v": v, "dt": float(dt), "mode": mode})

    # --- A 族：橢圓，往近地點掉 (rv<0) --------------------------------------
    for e in (0.01, 0.1, 0.3, 0.6, 0.85):
        a = 7500.0 / (1.0 - e) if e > 0.5 else 8000.0
        for ta in (200.0, 260.0, 300.0, 340.0, 359.0):
            r, v = coe2rv(a, e, 45.0, 30.0, 20.0, ta)
            tp = analytic_t_to_perigee(r, v)
            add(f"A_e{e}_ta{ta:g}", r, v, 3.0 * tp, "MEASURE")
            for m in (0.90, 0.99, 1.01, 1.10):
                add(f"A_e{e}_ta{ta:g}_m{m}", r, v, m * tp, "BOUNDARY")

    # --- B 族：橢圓，正在往外飛 (rv>0)，要繞快一整圈 ------------------------
    for e in (0.05, 0.25, 0.7):
        a = 9000.0
        for ta in (1.0, 30.0, 90.0, 150.0):
            r, v = coe2rv(a, e, 63.4, 0.0, 90.0, ta)
            tp = analytic_t_to_perigee(r, v)
            add(f"B_e{e}_ta{ta:g}", r, v, 3.0 * tp, "MEASURE")
            for m in (0.99, 1.01):
                add(f"B_e{e}_ta{ta:g}_m{m}", r, v, m * tp, "BOUNDARY")

    # --- C 族：近正圓（函式對 e<1e-12 直接回 False） ------------------------
    for e in (1e-7, 1e-4, 1e-2):
        r, v = coe2rv(7000.0, e, 45.0, 0.0, 0.0, 123.0)
        tp = analytic_t_to_perigee(r, v)
        add(f"C_e{e:g}", r, v, 3.0 * tp if math.isfinite(tp) else 10000.0, "MEASURE")

    # --- D 族：雙曲線 ------------------------------------------------------
    for e in (1.2, 2.0):
        for ta in (-60.0, -20.0, 20.0, 60.0):
            r, v = coe2rv(-9000.0, e, 30.0, 10.0, 40.0, ta)
            add(f"D_e{e}_ta{ta:g}_short", r, v, 60.0, "BOUNDARY")
            add(f"D_e{e}_ta{ta:g}_long", r, v, 20000.0, "MEASURE")

    # --- E 族：分裂燃燒家族（就是那個值 16.5 分的 bug 的形狀） --------------
    # 6978 km 圓軌道 + 一發大燒 -> 中間軌道近地點落在地表以下 -> 只滑行 100 秒
    r0, v0 = coe2rv(6978.0, 0.0, 45.0, 0.0, 0.0, 0.0)
    v_hat = v0 / np.linalg.norm(v0)
    r_hat = r0 / np.linalg.norm(r0)
    for mag in (1.3, 1.45, 1.6):
        for pitch in (150.0, 170.0, 190.0, 210.0):
            th = math.radians(pitch)
            dv = mag * (math.cos(th) * v_hat + math.sin(th) * r_hat)
            v_new = v0 + dv
            rp = None
            en = float(v_new @ v_new) / 2.0 - MU / float(np.linalg.norm(r0))
            if en < 0.0:
                a_n = -MU / (2.0 * en)
                h_n = np.cross(r0, v_new)
                e_n = math.sqrt(max(0.0, 1.0 + 2.0 * en * float(h_n @ h_n) / MU ** 2))
                rp = a_n * (1.0 - e_n)
            tag = f"E_m{mag}_p{pitch:g}" + (f"_rp{rp:.0f}" if rp else "_hyp")
            add(tag + "_dt100", r0, v_new, 100.0, "BOUNDARY")
            tpm = analytic_t_to_perigee(r0, v_new)
            if math.isfinite(tpm) and tpm > 0:
                add(tag + "_meas", r0, v_new, 3.0 * tpm, "MEASURE")
    # --- F 族：臨界傾角之外 -------------------------------------------------
    # 為什麼一定要有這族 (2026-08-29)：J2 造成的近地點進動方向由傾角決定 ——
    # i < 63.4 度近地點前進 (真實通過時刻比 Kepler 預測「晚」-> 判斷式偏保守，安全)；
    # i > 63.4 度近地點後退 (真實通過時刻比預測「早」-> 判斷式可能漏掉一次通過，
    # 那是**不安全**的方向)。A/B/E 族分別用 45/63.4/45 度，等於只測了安全側。
    # 官方題目的 B 軌道是 INC 135 度，就在不安全側，所以這族非測不可。
    for inc in (75.0, 90.0, 116.6, 135.0):
        for e in (0.02, 0.2, 0.5):
            a = 8000.0
            for ta in (250.0, 320.0, 355.0):
                r, v = coe2rv(a, e, inc, 15.0, 60.0, ta)
                tp = analytic_t_to_perigee(r, v)
                add(f"F_i{inc:g}_e{e}_ta{ta:g}", r, v, 3.0 * tp, "MEASURE")
                for m in (0.98, 0.999, 1.001, 1.02):
                    add(f"F_i{inc:g}_e{e}_ta{ta:g}_m{m}", r, v, m * tp, "BOUNDARY")

    # --- G 族：分裂燃燒，但放在官方 B 軌道的逆行幾何上 ----------------------
    r0b, v0b = coe2rv(6878.0, 0.0, 135.0, 30.0, 0.0, 60.0)
    vb = v0b / np.linalg.norm(v0b)
    rb = r0b / np.linalg.norm(r0b)
    for mag in (1.3, 1.5):
        for pitch in (160.0, 180.0, 200.0):
            th = math.radians(pitch)
            v_new = v0b + mag * (math.cos(th) * vb + math.sin(th) * rb)
            add(f"G_m{mag}_p{pitch:g}_dt100", r0b, v_new, 100.0, "BOUNDARY")
            tpm = analytic_t_to_perigee(r0b, v_new)
            if math.isfinite(tpm) and tpm > 0:
                add(f"G_m{mag}_p{pitch:g}_meas", r0b, v_new, 3.0 * tpm, "MEASURE")
                for m in (0.999, 1.001):
                    add(f"G_m{mag}_p{pitch:g}_m{m}", r0b, v_new, m * tpm, "BOUNDARY")

    return cases


# --------------------------------------------------------------------------
# GMAT 腳本產生（純 ASCII！非 ASCII 會讓 GMAT 直接拒絕解析）
# --------------------------------------------------------------------------
def write_script(cases, script_path, report_path, gravity):
    L = []
    A = L.append
    A("% Perigee-crossing cross-check: GMAT event location vs analytic predicate")
    A("% ASCII only. Generated by perigee_xcheck.py")
    A("")
    A("Create Spacecraft Sat")
    A("GMAT Sat.DateFormat = TAIModJulian")
    A("GMAT Sat.Epoch = '21545'")
    A("GMAT Sat.CoordinateSystem = EarthMJ2000Eq")
    A("GMAT Sat.DisplayStateType = Cartesian")
    A("")
    A("Create ForceModel FM")
    A("GMAT FM.CentralBody = Earth")
    if gravity == "twobody":
        A("GMAT FM.PointMasses = {Earth}")
    else:
        A("GMAT FM.PrimaryBodies = {Earth}")
        A("GMAT FM.GravityField.Earth.PotentialFile = 'JGM2.cof'")
        A("GMAT FM.GravityField.Earth.Degree = 4")
        A("GMAT FM.GravityField.Earth.Order = 0")
    A("GMAT FM.Drag = None")
    A("GMAT FM.SRP = Off")
    A("")
    A("Create Propagator Prop")
    A("GMAT Prop.FM = FM")
    A("GMAT Prop.Type = RungeKutta89")
    A("GMAT Prop.InitialStepSize = 1")
    A("GMAT Prop.Accuracy = 1e-13")
    A("GMAT Prop.MinStep = 0")
    A("GMAT Prop.MaxStep = 600")
    A("")
    A("Create ReportFile rf")
    A("GMAT rf.Filename = '%s'" % report_path)
    A("GMAT rf.Precision = 16")
    A("GMAT rf.WriteHeaders = false")
    A("GMAT rf.ColumnWidth = 26")
    A("")
    A("Create Variable cid t0 t1 el")
    A("")
    A("BeginMissionSequence")
    A("")
    for i, c in enumerate(cases):
        r, v = c["r"], c["v"]
        A("%% case %d %s" % (i, c["label"]))
        for name, val in zip(("X", "Y", "Z"), r):
            A("GMAT Sat.%s = %.17g" % (name, val))
        for name, val in zip(("VX", "VY", "VZ"), v):
            A("GMAT Sat.%s = %.17g" % (name, val))
        A("GMAT cid = %d" % i)
        A("GMAT t0 = Sat.TAIModJulian")
        A("Propagate Prop(Sat) {Sat.Earth.Periapsis, Sat.ElapsedSecs = %.17g}" % c["dt"])
        A("GMAT t1 = Sat.TAIModJulian")
        A("GMAT el = (t1 - t0) * 86400")
        A("Report rf cid el Sat.RMAG Sat.Earth.TA")
        A("")
    txt = "\n".join(L) + "\n"
    txt.encode("ascii")            # 非 ASCII 就直接在這裡炸，不要拿去餵 GMAT
    with open(script_path, "w") as f:
        f.write(txt)


def run_gmat(script_path, report_path):
    if os.path.exists(report_path):
        os.remove(report_path)
    p = subprocess.run([GMAT_BIN, "--run", script_path],
                       capture_output=True, text=True, timeout=3600)
    rows = []
    if os.path.exists(report_path):
        for line in open(report_path):
            parts = line.split()
            if len(parts) == 4:
                try:
                    rows.append([float(x) for x in parts])
                except ValueError:
                    pass
    return rows, p.stdout[-3000:], p.stderr[-3000:]


if __name__ == "__main__":
    gravity = sys.argv[1] if len(sys.argv) > 1 else "twobody"
    cases = build_cases()
    sp = os.path.join(HERE, "perigee_xcheck_%s.script" % gravity)
    rp = os.path.join(HERE, "perigee_xcheck_%s.report" % gravity)
    write_script(cases, sp, rp, gravity)
    print("cases: %d  script: %s" % (len(cases), sp))
    rows, out, err = run_gmat(sp, rp)
    print("report rows: %d" % len(rows))
    if len(rows) != len(cases):
        print("---- GMAT stdout tail ----"); print(out)
        print("---- GMAT stderr tail ----"); print(err)
    np.save(os.path.join(HERE, "perigee_xcheck_%s.npy" % gravity),
            np.array(rows, dtype=float) if rows else np.zeros((0, 4)))
