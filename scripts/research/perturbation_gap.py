"""排位賽全攝動落差研究：同一組脈衝放進官方攝動模型還打不打得中。

求解用的是 J2–J4（或點質量）模型，排位賽官方驗證開 EGM96 20×20、潮汐、NRLMSISE00 阻力、
日月第三體、SRP、相對論。這支腳本把現成解的脈衝（時間與 VNB Δv 不變）放進 GMAT 用不同
力學模型重播，量出最小距離、攔截時刻與 Earth-safe 的落差，再對太空船質量／面積／Cd／Cr
做蒙地卡羅，最後試 DifferentialCorrector 重瞄準。

只呼叫 GmatConsole（每個行程一份獨立腳本、絕對路徑），不碰 odc/。輸出寫到
outputs/research/perturbation_gap/（git 忽略）。用法（從專案根目錄）：

    uv run python scripts/research/perturbation_gap.py ladder
    uv run python scripts/research/perturbation_gap.py mc --n 60
    uv run python scripts/research/perturbation_gap.py retarget --mc 50
    uv run python scripts/research/perturbation_gap.py retarget --mode bplane --mc 50
    uv run python scripts/research/perturbation_gap.py plot

環境變數 GMAT_CONSOLE 指定執行檔；PG_WORKERS 指定同時開幾個 GMAT（預設 4，上限 4）；
MAIN_CHECKOUT 指定主 checkout（讀 outputs/ 底下的 mission.json 用，只讀不寫）。
"""
import argparse
import concurrent.futures as cf
import json
import math
import os
import re
import subprocess
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
MAIN = os.environ.get("MAIN_CHECKOUT", "/home/corn/ODC_GMAT_Planner")
GMAT_BIN = os.environ.get(
    "GMAT_CONSOLE", "/home/corn/software/GMAT/GMAT/R2026a/bin/GmatConsole")
GMAT_DATA = os.path.join(os.path.dirname(os.path.dirname(GMAT_BIN)), "data")
SPAD_SPHERE = os.path.join(GMAT_DATA, "vehicle", "spad", "SphericalModel.spo")
SPAD_SPHERE_AREA = 8.945  # SphericalModel.spo 每個方向的投影面積（m²），見檔頭資料
OUT = os.path.join(REPO, "outputs", "research", "perturbation_gap")
WORKERS = min(4, int(os.environ.get("PG_WORKERS", "4")))  # 另一個 session 在跑計時實驗，最多 4
R_EARTH = 6378.1363
MISS_KM = 5.0
EXT_SEC = 600.0     # 預定攔截時刻之後再多傳 10 分鐘，最近點可能晚到
MAX_STEP = 60.0     # 報表每步一列；限制步長讓 Hermite 內插夠準
STOP_ALT_KM = 50.0  # B 掉到這個高度就停：攔截後 B 常一路鑽進地球，MSISE 密度會讓積分器卡死

# ---------------------------------------------------------------- 解的來源
# 圓軌道兩個、雙曲線三個。kind=script 讀繳交腳本，kind=mission 讀 mission.json。
SOLUTIONS = {
    "contest_98319": dict(
        kind="script", label="contest（圓，98.319 六棒）",
        path=os.path.join(REPO, "docs", "solutions", "98.319_route4_split6_submit.txt"),
        t_max=None),
    "official_sample": dict(
        kind="mission", label="official_sample（圓，三棒）",
        path=os.path.join(MAIN, "outputs", "c4", "E5_official_sample_on", "mission.json")),
    "hyper_far": dict(
        kind="mission", label="hyper_far（雙曲線，三棒，22.6 h）",
        path=os.path.join(MAIN, "outputs", "sweeps", "budget_v1", "runs",
                          "hyper_far__B3_pop10__s1", "mission.json")),
    "hyperbolic_smoke": dict(
        kind="mission", label="hyperbolic_smoke（雙曲線，≤345 m/s）",
        path=os.path.join(MAIN, "outputs", "c4fix", "E4_hyperbolic_smoke_on", "mission.json")),
    "hyperbolic_test": dict(
        kind="mission", label="hyperbolic_test（雙曲線，五棒）",
        path=os.path.join(MAIN, "outputs", "c4", "E4_hyperbolic_test_on", "mission.json")),
}
ORBIT_KEYS = ("SMA", "ECC", "INC", "RAAN", "AOP", "TA")


def _parse_submit_script(path):
    txt = open(path, encoding="ascii").read()
    sol = {"orbit_A": {}, "orbit_B": {}, "epoch": None}
    for ship, key in (("(?:ShipA|SC_Alien)", "orbit_A"), ("(?:ShipB|SC_Human)", "orbit_B")):
        for k in ORBIT_KEYS:
            m = re.search(r"^%s\.%s\s*=\s*([-\d.eE+]+);" % (ship, k), txt, re.M)
            sol[key][k] = float(m.group(1))
    sol["epoch"] = re.search(r"^(?:ShipA|SC_Alien)\.Epoch\s*=\s*'([^']+)'", txt, re.M).group(1)
    elems = {}
    for m in re.finditer(r"^BurnB(\d+)\.Element(\d)\s*=\s*([-\d.eE+]+);", txt, re.M):
        elems.setdefault(int(m.group(1)), [0.0, 0.0, 0.0])[int(m.group(2)) - 1] = float(m.group(3))
    seq = txt[txt.index("BeginMissionSequence"):]
    coasts, burns, pending = [], [], 0.0
    for m in re.finditer(r"^(Propagate[^\n]*ElapsedSecs\s*=\s*([\d.eE+-]+)\}|Maneuver BurnB(\d+)\((?:ShipB|SC_Human)\))",
                         seq, re.M):
        if m.group(2) is not None:
            pending += float(m.group(2))
        else:
            coasts.append(pending)
            pending = 0.0
            burns.append(elems[int(m.group(3))])
    coasts.append(pending)
    deg = int(re.search(r"GravityField\.Earth\.Degree\s*=\s*(\d+)", txt).group(1))
    sol.update(burns=burns, coasts=coasts, design_degree=deg)
    return sol


def _parse_mission(path):
    d = json.load(open(path, encoding="utf-8"))
    c = d["config"]
    return {
        "orbit_A": {k: float(c["orbit_A"][k]) for k in ORBIT_KEYS},
        "orbit_B": {k: float(c["orbit_B"][k]) for k in ORBIT_KEYS},
        "epoch": "21545",
        "burns": [list(map(float, b)) for b in d["burns"]],
        "coasts": list(map(float, d["times"])),
        "design_degree": int(c["strategy"].get("GRAVITY_DEGREE", 4)),
        "t_max": c["rules"].get("T_MAX_SEC"),
        "python_miss_km": d["mission_info"].get("miss_km"),
    }


def load_solution(name):
    spec = SOLUTIONS[name]
    sol = _parse_submit_script(spec["path"]) if spec["kind"] == "script" else _parse_mission(spec["path"])
    assert len(sol["coasts"]) == len(sol["burns"]) + 1, name
    sol.update(name=name, label=spec["label"], source=spec["path"])
    sol["t_plan"] = sum(sol["coasts"])
    sol["burn_times"] = list(np.cumsum(sol["coasts"][:-1]))
    return sol


# ---------------------------------------------------------------- 力學模型
def fm_spec(**kw):
    base = dict(potential="JGM2.cof", degree=4, order=0, tide="None", point_masses=(),
                relativity=False, srp=None, drag=None)
    base.update(kw)
    return base


def design_fm(sol):
    return fm_spec(degree=sol["design_degree"], order=0)


EGM = dict(potential="EGM96.cof", degree=20, order=20)
FULL = dict(EGM, tide="SolidAndPole", point_masses=("Sun", "Luna"), relativity=True,
            srp="Spherical", drag="Spherical")
FULL_SPAD = dict(FULL, srp="SPADFile", drag="SPADFile")


def ladder_rungs(sol):
    """逐項累加的力學模型階梯。第一階是解當初設計用的模型（基準 a），最後是全攝動（b）。"""
    rungs = [("design", design_fm(sol))]
    if sol["design_degree"] != 4:
        rungs.append(("J2-J4", fm_spec()))
    rungs += [
        ("EGM96 20x20", fm_spec(**EGM)),
        ("+tide", fm_spec(**EGM, tide="SolidAndPole")),
        ("+Sun/Luna", fm_spec(**EGM, tide="SolidAndPole", point_masses=("Sun", "Luna"))),
        ("+relativity", fm_spec(**EGM, tide="SolidAndPole", point_masses=("Sun", "Luna"),
                                relativity=True)),
        ("+SRP", fm_spec(**dict(FULL, drag=None))),
        ("full (spherical)", fm_spec(**FULL)),
        ("full (SPADFile)", fm_spec(**FULL_SPAD)),
        ("full, A gravity-only", fm_spec(**FULL)),
    ]
    return rungs


NOMINAL_SC = dict(mass=850.0, area=SPAD_SPHERE_AREA, cd=2.2, cr=1.8)


def _fm_block(name, fm):
    L = ["Create ForceModel %s;" % name,
         "%s.CentralBody = Earth;" % name,
         "%s.PrimaryBodies = {Earth};" % name]
    if fm["point_masses"]:
        L.append("%s.PointMasses = {%s};" % (name, ", ".join(fm["point_masses"])))
    if fm["drag"]:
        L += ["%s.Drag.AtmosphereModel = NRLMSISE00;" % name,
              "%s.Drag.HistoricWeatherSource = 'CSSISpaceWeatherFile';" % name,
              "%s.Drag.PredictedWeatherSource = 'CSSISpaceWeatherFile';" % name,
              "%s.Drag.CSSISpaceWeatherFile = 'SpaceWeather-All-v1.2.txt';" % name,
              "%s.Drag.DragModel = '%s';" % (name, fm["drag"])]
    else:
        L.append("%s.Drag = None;" % name)
    if fm["srp"]:
        L += ["%s.SRP = On;" % name, "%s.SRP.SRPModel = %s;" % (name, fm["srp"])]
    else:
        L.append("%s.SRP = Off;" % name)
    L += ["%s.RelativisticCorrection = %s;" % (name, "On" if fm["relativity"] else "Off"),
          "%s.ErrorControl = RSSStep;" % name,
          "%s.GravityField.Earth.Degree = %d;" % (name, fm["degree"]),
          "%s.GravityField.Earth.Order = %d;" % (name, fm["order"]),
          "%s.GravityField.Earth.StmLimit = 100;" % name,
          "%s.GravityField.Earth.PotentialFile = '%s';" % (name, fm["potential"]),
          "%s.GravityField.Earth.TideModel = '%s';" % (name, fm["tide"])]
    return L


def _prop_block(name, fm_name):
    return ["Create Propagator %s;" % name,
            "%s.FM = %s;" % (name, fm_name),
            "%s.Type = RungeKutta89;" % name,
            "%s.InitialStepSize = 60;" % name,
            "%s.Accuracy = 1e-12;" % name,
            "%s.MinStep = 0.001;" % name,
            "%s.MaxStep = %g;" % (name, MAX_STEP),
            "%s.MaxStepAttempts = 50;" % name,
            "%s.StopIfAccuracyIsViolated = false;" % name]


def _ship_block(ship, epoch, orbit, sc):
    L = ["Create Spacecraft %s;" % ship,
         "%s.DateFormat = TAIModJulian;" % ship,
         "%s.Epoch = '%s';" % (ship, epoch),
         "%s.CoordinateSystem = EarthMJ2000Eq;" % ship,
         "%s.DisplayStateType = Keplerian;" % ship]
    L += ["%s.%s = %.15g;" % (ship, k, orbit[k]) for k in ORBIT_KEYS]
    L += ["%s.DryMass = %.10g;" % (ship, sc["mass"]),
          "%s.Cd = %.10g;" % (ship, sc["cd"]),
          "%s.Cr = %.10g;" % (ship, sc["cr"]),
          "%s.DragArea = %.10g;" % (ship, sc["area"]),
          "%s.SRPArea = %.10g;" % (ship, sc["area"]),
          # SPAD 模式下 Cd/Cr/面積都被忽略，只用 .spo 的面積表 × 比例因子 / 質量
          "%s.SPADDragFile = '%s';" % (ship, SPAD_SPHERE),
          "%s.SPADSRPFile = '%s';" % (ship, SPAD_SPHERE),
          "%s.SPADDragScaleFactor = %.10g;" % (ship, sc.get("spad_drag_scale", 1.0)),
          "%s.SPADSRPScaleFactor = %.10g;" % (ship, sc.get("spad_srp_scale", 1.0))]
    return L


def _propagate(prop, secs):
    return "Propagate %s {ShipA.ElapsedSecs = %.10f, ShipB.Earth.Altitude = %g};" % (
        prop, secs, STOP_ALT_KM)


def build_script(sol, fm, report_path, burns=None, sc_A=None, sc_B=None,
                 alien_grav_only=False, retarget_idx=None, summary_path=None, bplane=None):
    """固定燃燒版：報表每個積分步寫一列兩船狀態。retarget_idx 給定時改成 DC 版：
    Vary 第 retarget_idx 棒的 VNB 三分量，讓預定攔截時刻 B 的位置等於 A 的位置。"""
    burns = burns if burns is not None else sol["burns"]
    sc_A, sc_B = sc_A or NOMINAL_SC, sc_B or NOMINAL_SC
    L = ["% generated by scripts/research/perturbation_gap.py"]
    L += _ship_block("ShipA", sol["epoch"], sol["orbit_A"], sc_A)
    L += _ship_block("ShipB", sol["epoch"], sol["orbit_B"], sc_B)
    L += _fm_block("FM", fm) + _prop_block("Prop", "FM")
    if alien_grav_only:
        L += _fm_block("FMA", dict(fm, srp=None, drag=None)) + _prop_block("PropA", "FMA")
        prop = "Synchronized PropA(ShipA) Prop(ShipB)"
    else:
        prop = "Prop(ShipA, ShipB)"
    for k, b in enumerate(burns):
        L += ["Create ImpulsiveBurn BurnB%d;" % k,
              "BurnB%d.CoordinateSystem = Local;" % k,
              "BurnB%d.Origin = Earth;" % k,
              "BurnB%d.Axes = VNB;" % k]
        L += ["BurnB%d.Element%d = %.15g;" % (k, i + 1, b[i]) for i in range(3)]
        L += ["BurnB%d.DecrementMass = false;" % k]
    cols = ["ShipB.TAIModJulian"] + ["ShipB.EarthMJ2000Eq.%s" % c for c in
                                     ("X", "Y", "Z", "VX", "VY", "VZ")] + \
           ["ShipA.EarthMJ2000Eq.%s" % c for c in ("X", "Y", "Z", "VX", "VY", "VZ")]
    if retarget_idx is None:
        L += ["Create ReportFile RF;",
              "RF.SolverIterations = None;",
              "RF.Filename = '%s';" % report_path,
              "RF.Precision = 16;",
              "RF.WriteHeaders = false;",
              "RF.ZeroFill = Off;",
              "RF.Add = {%s};" % ", ".join(cols)]
    else:
        L += ["Create ReportFile RS;",
              "RS.SolverIterations = None;",
              "RS.Filename = '%s';" % summary_path,
              "RS.Precision = 16;",
              "RS.WriteHeaders = false;",
              "Create DifferentialCorrector DC;",
              "DC.MaximumIterations = 40;",
              "DC.DerivativeMethod = ForwardDifference;",
              "DC.Algorithm = NewtonRaphson;",
              "Create Variable dX dY dZ p1 p2;"]
    L.append("BeginMissionSequence;")
    for k, b in enumerate(burns):
        if sol["coasts"][k] > 0:
            L.append(_propagate(prop, sol["coasts"][k]))
        if retarget_idx is not None and k == retarget_idx:
            # 被 Vary 那棒之前的滑行留在 Target 迴圈外面，迴圈只重算這棒之後
            L.append("Target DC {SolveMode = Solve, ExitMode = SaveAndContinue};")
            for i in range(3):
                L.append("  Vary DC(BurnB%d.Element%d = %.15g, {Perturbation = 1e-6, "
                         "Lower = -2.0, Upper = 2.0, MaxStep = 0.01});" % (k, i + 1, b[i]))
        L.append("Maneuver BurnB%d(ShipB);" % k)
    L.append(_propagate(prop, sol["coasts"][-1]))
    if retarget_idx is None:
        L.append(_propagate(prop, EXT_SEC))
    else:
        L += ["  GMAT dX = ShipB.EarthMJ2000Eq.X - ShipA.EarthMJ2000Eq.X;",
              "  GMAT dY = ShipB.EarthMJ2000Eq.Y - ShipA.EarthMJ2000Eq.Y;",
              "  GMAT dZ = ShipB.EarthMJ2000Eq.Z - ShipA.EarthMJ2000Eq.Z;"]
        if bplane is None:
            # 定時瞄準：預定攔截時刻 B 的位置 = A 的位置（三個目標）
            L += ["  Achieve DC(d%s = 0, {Tolerance = 0.02});" % c for c in "XYZ"]
        else:
            # B 平面瞄準：只消掉垂直於相對速度的兩個分量；沿相對速度的分量只會讓最近點
            # 早到或晚到幾秒，規則只看 d_min，不用花 Δv 去修
            for name, e in zip(("p1", "p2"), bplane):
                L.append("  GMAT %s = dX*(%.15g) + dY*(%.15g) + dZ*(%.15g);" % ((name,) + tuple(e)))
                L.append("  Achieve DC(%s = 0, {Tolerance = 0.02});" % name)
        L += ["EndTarget;",
              "Report RS BurnB%d.Element1 BurnB%d.Element2 BurnB%d.Element3 dX dY dZ;"
              % (retarget_idx, retarget_idx, retarget_idx)]
    txt = "\n".join(L) + "\n"
    txt.encode("ascii")
    return txt


# ---------------------------------------------------------------- 執行與後處理
def run_gmat(script_txt, tag, sub):
    d = os.path.join(OUT, sub)
    os.makedirs(d, exist_ok=True)
    sp = os.path.abspath(os.path.join(d, tag + ".script"))
    open(sp, "w", encoding="ascii").write(script_txt)
    t0 = time.time()
    # nice：同機另一個 session 在量牆鐘，讓出 CPU 優先權
    try:
        p = subprocess.run(["nice", "-n", "10", GMAT_BIN, "--run", sp],
                           capture_output=True, text=True, timeout=1200)
    except subprocess.TimeoutExpired as e:
        p = subprocess.CompletedProcess(e.cmd, -9, str(e.stdout or ""), "TIMEOUT")
    open(os.path.join(d, tag + ".stdout"), "w").write(p.stdout + "\n--stderr--\n" + p.stderr)
    return p, time.time() - t0


def _read_rows(path, epoch):
    rows = []
    for line in open(path):
        parts = line.split()
        if len(parts) != 13:
            continue
        try:
            rows.append([float(x) for x in parts])
        except ValueError:
            continue
    a = np.array(rows)
    a[:, 0] = (a[:, 0] - float(epoch)) * 86400.0
    return a


def _hermite(t0, t1, p0, v0, p1, v1, s):
    """三次 Hermite：s ∈ [0,1] 的陣列 → 位置 (len(s), 3)。"""
    h = t1 - t0
    s = s[:, None]
    h00 = 2 * s**3 - 3 * s**2 + 1
    h10 = s**3 - 2 * s**2 + s
    h01 = -2 * s**3 + 3 * s**2
    h11 = s**3 - s**2
    return h00 * p0 + h10 * h * v0 + h01 * p1 + h11 * h * v1


def analyze(rows, sol, sub=64):
    """回傳最小距離、最近點時刻、第一次進 5 km 的時刻、攔截前 B 的最低高度。"""
    t = rows[:, 0]
    rB, vB, rA, vA = rows[:, 1:4], rows[:, 4:7], rows[:, 7:10], rows[:, 10:13]
    s = np.linspace(0.0, 1.0, sub + 1)
    dense_t, dense_d, dense_rb = [], [], []
    for i in range(len(t) - 1):
        h = t[i + 1] - t[i]
        if h <= 1e-6:  # 燃燒前後同一時刻兩列：速度不連續，不內插
            continue
        dr = _hermite(t[i], t[i + 1], rB[i] - rA[i], vB[i] - vA[i],
                      rB[i + 1] - rA[i + 1], vB[i + 1] - vA[i + 1], s)
        rb = _hermite(t[i], t[i + 1], rB[i], vB[i], rB[i + 1], vB[i + 1], s)
        dense_t.append(t[i] + s * h)
        dense_d.append(np.linalg.norm(dr, axis=1))
        dense_rb.append(np.linalg.norm(rb, axis=1))
    T = np.concatenate(dense_t)
    D = np.concatenate(dense_d)
    RB = np.concatenate(dense_rb)
    k = int(np.argmin(D))
    # 在最近點附近再細化一次（步長 60 s / 64 ≈ 1 s；相對速度 km/s 級時再細到 ms）
    i = min(max(int(np.searchsorted(t, T[k], side="right") - 1), 0), len(t) - 2)
    best = (D[k], T[k])
    for j in (i - 1, i, i + 1):
        if 0 <= j < len(t) - 1 and t[j + 1] - t[j] > 1e-6:
            ss = np.linspace(0, 1, 20001)
            dr = _hermite(t[j], t[j + 1], rB[j] - rA[j], vB[j] - vA[j],
                          rB[j + 1] - rA[j + 1], vB[j + 1] - vA[j + 1], ss)
            dd = np.linalg.norm(dr, axis=1)
            m = int(np.argmin(dd))
            if dd[m] < best[0]:
                best = (dd[m], t[j] + ss[m] * (t[j + 1] - t[j]))
    d_min, t_cpa = best
    hit = np.nonzero(D <= MISS_KM)[0]
    t_int = float(T[hit[0]]) if len(hit) else None
    horizon = t_int if t_int is not None else sol["t_plan"]
    pre = T <= horizon + 1e-9
    min_alt = float(RB[pre].min() - R_EARTH)
    # 預定攔截時刻的距離（舊腳本 MissDistance 的定義）
    jp = np.nonzero(np.abs(t - sol["t_plan"]) < 1e-3)[0]
    dr_plan = (rB[jp[0]] - rA[jp[0]]).tolist() if len(jp) else None
    dv_plan = (vB[jp[-1]] - vA[jp[-1]]).tolist() if len(jp) else None
    d_plan = float(np.linalg.norm(dr_plan)) if len(jp) else float("nan")
    return dict(d_min_km=float(d_min), t_cpa=float(t_cpa), t_int=t_int,
                stopped_early=bool(t[-1] < sol["t_plan"] - 1e-3),
                d_at_plan_km=d_plan, dr_plan_km=dr_plan, dv_plan_kms=dv_plan,
                min_alt_km=min_alt,
                earth_safe=bool(min_alt > 0.0), hit=bool(d_min <= MISS_KM),
                n_rows=int(len(t)))


def replay(sol, fm, tag, sub, burns=None, sc_A=None, sc_B=None, alien_grav_only=False):
    d = os.path.join(OUT, sub)
    os.makedirs(d, exist_ok=True)
    rep = os.path.abspath(os.path.join(d, tag + ".report"))
    if os.path.exists(rep):
        os.remove(rep)
    txt = build_script(sol, fm, rep, burns=burns, sc_A=sc_A, sc_B=sc_B,
                       alien_grav_only=alien_grav_only)
    p, wall = run_gmat(txt, tag, sub)
    res = dict(tag=tag, wall_s=round(wall, 2), returncode=p.returncode)
    if not os.path.exists(rep) or os.path.getsize(rep) == 0:
        res["error"] = (p.stdout[-800:] + p.stderr[-400:]).strip()
        return res
    res.update(analyze(_read_rows(rep, sol["epoch"]), sol))
    os.remove(rep)  # 報表很大，結果已經抽出來
    return res


def retarget(sol, fm, idx, tag, sub, sc=None, bplane=None):
    d = os.path.join(OUT, sub)
    os.makedirs(d, exist_ok=True)
    summ = os.path.abspath(os.path.join(d, tag + ".summary"))
    if os.path.exists(summ):
        os.remove(summ)
    txt = build_script(sol, fm, None, sc_A=sc, sc_B=sc, retarget_idx=idx, summary_path=summ,
                       bplane=bplane)
    p, wall = run_gmat(txt, tag, sub)
    conv = "converged" in p.stdout and "did not converge" not in p.stdout.lower()
    m = re.search(r"Targeting Completed in (\d+) iterations", p.stdout)
    res = dict(tag=tag, idx=idx, converged=conv, iterations=int(m.group(1)) if m else None,
               wall_s=round(wall, 2))
    if os.path.exists(summ):
        vals = [float(x) for x in open(summ).read().split()[-6:]]
        res["burn"] = vals[:3]
        res["residual_km"] = vals[3:]
        dr = np.array(vals[3:])
        if bplane is not None:
            dr = np.array([dr @ np.array(e) for e in bplane])
        res["converged"] = conv and float(np.abs(dr).max()) < 0.05
    else:
        res["error"] = (p.stdout[-800:] + p.stderr[-400:]).strip()
    return res


def pmap(fn, jobs):
    with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(fn, *j) for j in jobs]
        return [f.result() for f in futs]


def _dump(name, obj):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    json.dump(obj, open(path, "w"), indent=1, ensure_ascii=False)
    print("wrote", path)


# ---------------------------------------------------------------- 蒙地卡羅
# 範圍依據寫在 docs/research/PERTURBATION_GAP_20261019.md §3。質量與面積跨一個數量級以上，
# 用對數均勻；Cd、Cr 用均勻。A、B 各自獨立抽樣（規則沒給任何一艘的參數）。
MC_RANGES = dict(mass=(100.0, 2000.0), area=(1.0, 20.0), cd=(2.0, 2.4), cr=(1.0, 1.8))


def sample_sc(rng):
    lo, hi = MC_RANGES["mass"]
    mass = math.exp(rng.uniform(math.log(lo), math.log(hi)))
    lo, hi = MC_RANGES["area"]
    area = math.exp(rng.uniform(math.log(lo), math.log(hi)))
    return dict(mass=mass, area=area, cd=rng.uniform(*MC_RANGES["cd"]),
                cr=rng.uniform(*MC_RANGES["cr"]))


def mc_jobs(sol, n, seed, burns=None, sub="mc"):
    rng = np.random.default_rng(seed)
    jobs = []
    for i in range(n):
        a, b = sample_sc(rng), sample_sc(rng)
        jobs.append((sol, fm_spec(**FULL), "%s_mc%03d" % (sol["name"], i), sub, burns, a, b))
    return jobs


def _mc_run(sol, fm, tag, sub, burns, a, b):
    r = replay(sol, fm, tag, sub, burns=burns, sc_A=a, sc_B=b)
    r.update(solution=sol["name"], A=a, B=b)
    return r


# ---------------------------------------------------------------- 指令
def cmd_ladder(args):
    jobs = []
    for name in args.solutions:
        sol = load_solution(name)
        for rung, fm in ladder_rungs(sol):
            tag = "%s__%s" % (name, re.sub(r"[^A-Za-z0-9]+", "_", rung).strip("_"))
            jobs.append((sol, rung, fm, tag))

    def one(sol, rung, fm, tag):
        r = replay(sol, fm, tag, "ladder", alien_grav_only=(rung == "full, A gravity-only"))
        r.update(solution=sol["name"], rung=rung)
        print("%-18s %-22s d_min=%10.3f km  t_cpa-t_plan=%8.2f s  alt=%8.1f km  %5.1fs" % (
            sol["name"], rung, r.get("d_min_km", float("nan")),
            r.get("t_cpa", float("nan")) - sol["t_plan"], r.get("min_alt_km", float("nan")),
            r["wall_s"]), flush=True)
        return r
    res = pmap(one, jobs)
    sols = {n: {k: v for k, v in load_solution(n).items() if k != "label"} for n in args.solutions}
    _dump("ladder.json", dict(solutions=sols, results=res))


def cmd_mc(args):
    jobs = []
    for k, name in enumerate(args.solutions):
        jobs += mc_jobs(load_solution(name), args.n, args.seed + k)
    res = pmap(_mc_run, jobs)
    for name in args.solutions:
        d = np.array([r["d_min_km"] for r in res if r["solution"] == name and "d_min_km" in r])
        print("%-18s n=%d  hit=%.0f%%  median=%.2f km  p90=%.2f km  max=%.2f km" % (
            name, len(d), 100 * np.mean(d <= MISS_KM), np.median(d),
            np.percentile(d, 90), d.max()))
    _dump("mc.json", res)


def bplane_basis(v_rel):
    """垂直於相對速度的兩個單位向量。"""
    u = np.array(v_rel) / np.linalg.norm(v_rel)
    a = np.array([0.0, 0.0, 1.0]) if abs(u[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    e1 = np.cross(u, a)
    e1 /= np.linalg.norm(e1)
    return [e1.tolist(), np.cross(u, e1).tolist()]


def _with_burn(burns, idx, burn):
    new = [list(x) for x in burns]
    new[idx] = list(burn)
    return new


def _burn_candidates(sol):
    n = len(sol["burns"])
    return [i for i in range(n) if np.linalg.norm(sol["burns"][i]) > 1e-9
            and sum(sol["coasts"][i + 1:]) > 0]


def _anchor_j2j4(sol):
    """點質量設計的解先在 J2–J4 下用 DC 修最後一棒，當作「現行管線（GRAVITY_DEGREE=4）
    會產出的對等計畫」，這樣量到的全攝動落差才是 J2–J4 → 全攝動，不混進 J2 本身。"""
    idx = _burn_candidates(sol)[-1]
    r = retarget(sol, fm_spec(), idx, sol["name"] + "__anchor_j2j4", "retarget")
    if not r.get("converged"):
        return None, r
    plan = dict(sol, burns=_with_burn(sol["burns"], idx, r["burn"]),
                name=sol["name"] + "_j2j4", design_degree=4)
    r["check_j2j4"] = replay(plan, fm_spec(), plan["name"] + "__j2j4", "retarget")
    return plan, r


def cmd_retarget(args):
    """全攝動（標稱參數）下用 DC 改單一一棒（每個非零棒都試），再重播與蒙地卡羅。
    --mode fixed：預定攔截時刻位置對齊（現有腳本 DC 的做法）；--mode bplane：只消垂直分量。"""
    full = fm_spec(**FULL)
    sfx = "" if args.mode == "fixed" else "_" + args.mode
    plans, anchors = [], []
    for name in args.solutions:
        sol = load_solution(name)
        plans.append(sol)
        if sol["design_degree"] != 4:
            plan, r = _anchor_j2j4(sol)
            anchors.append(dict(r, solution=name))
            print("anchor", name, r.get("converged"), r.get("check_j2j4", {}).get("d_min_km"),
                  flush=True)
            if plan:
                plans.append(plan)
    bases = {}
    if args.mode == "bplane":
        noms = pmap(lambda plan: replay(plan, full, plan["name"] + "__nominal", "retarget" + sfx),
                    [(plan,) for plan in plans])
        bases = {plan["name"]: bplane_basis(r["dv_plan_kms"]) for plan, r in zip(plans, noms)}
    jobs = [(plan, None) for plan in plans if plan["name"].endswith("_j2j4")]
    jobs += [(plan, idx) for plan in plans for idx in _burn_candidates(plan)]

    def one(plan, idx):
        if idx is None:  # 錨定後的計畫原封不動放進全攝動
            r = replay(plan, full, plan["name"] + "__full", "retarget" + sfx)
            r.update(solution=plan["name"], idx=None)
            return r
        tag = "%s__dc_b%d" % (plan["name"], idx)
        r = retarget(plan, full, idx, tag, "retarget" + sfx, bplane=bases.get(plan["name"]))
        r.update(solution=plan["name"], design_degree=plan["design_degree"],
                 n_burns=len(plan["burns"]), coast_after_s=sum(plan["coasts"][idx + 1:]))
        if "burn" in r:
            old = np.array(plan["burns"][idx])
            r["old_burn_mps"] = float(np.linalg.norm(old) * 1000)
            r["new_burn_mps"] = float(np.linalg.norm(r["burn"]) * 1000)
            r["delta_vec_mps"] = float(np.linalg.norm(np.array(r["burn"]) - old) * 1000)
            r["delta_total_dv_mps"] = r["new_burn_mps"] - r["old_burn_mps"]
            r["new_burns"] = _with_burn(plan["burns"], idx, r["burn"])
            r["replay"] = replay(plan, full, tag + "_replay", "retarget" + sfx,
                                 burns=r["new_burns"])
        print(json.dumps({k: v for k, v in r.items() if k not in ("new_burns", "error")},
                         ensure_ascii=False, default=float), flush=True)
        return r
    out = pmap(one, jobs)
    _dump("retarget%s.json" % sfx, dict(anchors=anchors, results=out, mode=args.mode))
    if args.mc:
        # 每個計畫挑一個重瞄準結果做蒙地卡羅：最後一棒收斂就用它（比賽當天最自然的做法），
        # 否則用收斂者裡修正量最小的
        mjobs = []
        for k, plan in enumerate(plans):
            ok = [r for r in out if r["solution"] == plan["name"] and r.get("idx") is not None
                  and r.get("converged") and r.get("replay", {}).get("hit")]
            if not ok:
                continue
            last = [r for r in ok if r["idx"] == _burn_candidates(plan)[-1]
                    and r["delta_vec_mps"] < 50.0]
            pick = last[0] if last else min(ok, key=lambda r: r["delta_vec_mps"])
            for j in mc_jobs(plan, args.mc, args.seed + k, burns=pick["new_burns"],
                             sub="retarget%s_mc" % sfx):
                mjobs.append(j[:2] + (j[2].replace("_mc", "_b%d_mc" % pick["idx"]),) + j[3:])
        mc = pmap(_mc_run, mjobs)
        for r in mc:
            r["retarget_idx"] = int(re.search(r"_b(\d+)_mc", r["tag"]).group(1))
        _dump("retarget%s_mc.json" % sfx, mc)


def cmd_plot(args):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    def load(fn):
        path = os.path.join(OUT, fn)
        return json.load(open(path)) if os.path.exists(path) else []
    series = [("original burns", load("mc.json"), "#4C72B0"),
              ("fixed-time DC retarget", load("retarget_mc.json"), "#DD8452"),
              ("B-plane DC retarget", load("retarget_bplane_mc.json"), "#55A868")]
    names = [n for n in SOLUTIONS if any(r["solution"] == n for r in series[0][1])]
    fig, axes = plt.subplots(len(names), 1, figsize=(7.5, 2.2 * len(names)), sharex=True)
    axes = np.atleast_1d(axes)
    bins = np.logspace(-3, 3, 61)
    for ax, name in zip(axes, names):
        for label, rows, color in series:
            d = np.array([r["d_min_km"] for r in rows if r["solution"] == name and "d_min_km" in r])
            if len(d):
                ax.hist(np.clip(d, 1e-3, 1e3), bins=bins, color=color, alpha=0.6,
                        label="%s (n=%d, %.0f%% <= 5 km)" % (label, len(d), 100 * np.mean(d <= MISS_KM)))
        ax.axvline(MISS_KM, color="k", ls="--", lw=1)
        ax.set_xscale("log")
        ax.set_title(name, fontsize=9, loc="left")
        ax.legend(fontsize=7, loc="upper left")
        ax.tick_params(labelsize=7)
    axes[-1].set_xlabel("d_min under full perturbation, Monte Carlo over mass/area/Cd/Cr [km] (dashed: 5 km)")
    fig.tight_layout()
    fig_dir = os.path.join(REPO, "docs", "figures")
    os.makedirs(fig_dir, exist_ok=True)
    path = os.path.join(fig_dir, "perturbation_gap_mc_20261019.png")
    fig.savefig(path, dpi=130)
    print("wrote", path)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    for c in ("ladder", "mc", "retarget", "plot"):
        p = sp.add_parser(c)
        p.add_argument("--solutions", nargs="+", default=list(SOLUTIONS))
        p.add_argument("--n", type=int, default=60)
        p.add_argument("--mc", type=int, default=0)
        p.add_argument("--seed", type=int, default=20261019)
        p.add_argument("--mode", choices=("fixed", "bplane"), default="fixed")
    args = ap.parse_args()
    {"ladder": cmd_ladder, "mc": cmd_mc, "retarget": cmd_retarget, "plot": cmd_plot}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
