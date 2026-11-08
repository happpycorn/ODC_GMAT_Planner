"""把一場 organizer 對局寫成 GMAT 腳本，在 GMAT GUI 打開按 Run 就能看。在 medal/ 下跑：
    .venv/bin/python ../docs/final/mock_drill_close_20261107/gmat_replay.py <organizer_log.json> <輸出 .script>
起點讀本資料夾的 usb/initial_state.csv，推力讀 organizer_log.json（超過 200 m/s 的照主辦規則等比例縮放）。
力學：純二體（Earth 點質量）。每回合起點兩艘各一發 ImpulsiveBurn（EarthMJ2000Eq），再同步滑行 900 s。
視窗：3D 軌道（EarthMJ2000Eq）、以躲方為原點的 RSW 相對運動、雙方距離、雙方半長軸。
另寫一個每 5 s 報表（同資料夾 *_report.txt）：時間、雙方 ECI 位置、追方在躲方 RSW 的位置、距離，可以跟 trajectory.csv 對。
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.getcwd())
from final_copilot import _parse_state, _rv  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
spec = __import__("importlib.util").util.spec_from_file_location("org", os.path.join(HERE, "organizer.py"))
org = __import__("importlib.util").util.module_from_spec(spec)
spec.loader.exec_module(org)

P, E = org.NAMES["pursuer"], org.NAMES["evader"]
W = org.RULES["window_sec"]
CAP = org.RULES["max_dv_pursuer_mps"]
STEP = 5.0
EPOCH = org.START.strftime("%d %b %Y %H:%M:%S.000")


def sc(name, r, v, color):
    s = [f"Create Spacecraft {name};", f"{name}.DateFormat = UTCGregorian;", f"{name}.Epoch = '{EPOCH}';",
         f"{name}.CoordinateSystem = EarthMJ2000Eq;", f"{name}.DisplayStateType = Cartesian;"]
    s += [f"{name}.{k} = {x:.12f};" for k, x in zip(("X", "Y", "Z", "VX", "VY", "VZ"), list(r) + list(v))]
    s += [f"{name}.DryMass = 500;", f"{name}.OrbitColor = {color};", f"{name}.TargetColor = {color};"]
    return "\n".join(s)


def main():
    log = json.load(open(sys.argv[1], encoding="utf-8"))
    out = os.path.abspath(sys.argv[2])
    report = os.path.splitext(out)[0] + "_report.txt"
    st, _ = _parse_state(os.path.join(HERE, "usb/initial_state.csv"), names={"pursuer": [P], "evader": [E]})
    rp, vp = _rv(st, "pursuer")
    re, ve = _rv(st, "evader")
    role = log["role"]
    opp = "pursuer" if role == "evader" else "evader"

    L = [f"% ODC medal drill replay (close scenario): we = {role}, opponent seed {log['opp_seed']}; made by gmat_replay.py",
         sc(P, rp, vp, "[235 104 52]"), sc(E, re, ve, "[42 120 214]"), """
Create ForceModel FM;
FM.CentralBody = Earth;
FM.PrimaryBodies = {Earth};
FM.Drag = None;
FM.SRP = Off;
FM.RelativisticCorrection = Off;
FM.ErrorControl = RSSStep;
FM.GravityField.Earth.Degree = 0;
FM.GravityField.Earth.Order = 0;
FM.GravityField.Earth.PotentialFile = 'JGM2.cof';

Create Propagator Prop;
Prop.FM = FM;
Prop.Type = RungeKutta89;
Prop.InitialStepSize = 10;
Prop.Accuracy = 1e-12;
Prop.MinStep = 0.001;
Prop.MaxStep = 5;

% Evader-centred RSW: X = radial (up +), Y = along-track (ahead +), Z = orbit normal
Create CoordinateSystem EvaderRSW;
EvaderRSW.Origin = """ + E + """;
EvaderRSW.Axes = ObjectReferenced;
EvaderRSW.XAxis = R;
EvaderRSW.ZAxis = N;
EvaderRSW.Primary = Earth;
EvaderRSW.Secondary = """ + E + ";"]

    names = []
    for k, rd in enumerate(log["rounds"]):
        dv = {role: np.array(rd["our_dv"], float), opp: np.array(rd["opp_dv"], float)}
        for side, ship in (("pursuer", P), ("evader", E)):
            d = dv[side]
            n = np.linalg.norm(d)
            if n > CAP:
                d = d * CAP / n
            if n == 0:
                continue
            b = f"R{k + 1}_{'P' if side == 'pursuer' else 'E'}"
            names.append((k, b, ship))
            L.append(f"Create ImpulsiveBurn {b};\n{b}.CoordinateSystem = EarthMJ2000Eq;\n"
                     + "\n".join(f"{b}.Element{i + 1} = {x / 1000.0:.12f};" for i, x in enumerate(d))
                     + f"\n{b}.DecrementMass = false;")

    L.append(f"""
Create Variable Dist I;
Create ReportFile Rep;
Rep.Filename = '{report}';
Rep.Precision = 16;
Rep.WriteHeaders = false;

Create OrbitView View3D;
View3D.Add = {{{P}, {E}, Earth}};
View3D.CoordinateSystem = EarthMJ2000Eq;
View3D.ViewPointReference = Earth;
View3D.ViewDirection = Earth;
View3D.ViewScaleFactor = 2.5;
View3D.ViewUpCoordinateSystem = EarthMJ2000Eq;
View3D.ViewUpAxis = Z;
View3D.Axes = On;
View3D.Grid = Off;
View3D.EnableConstellations = Off;
View3D.SolverIterations = None;

Create OrbitView RelView;
RelView.Add = {{{P}, {E}}};
RelView.CoordinateSystem = EvaderRSW;
RelView.ViewPointReference = {E};
RelView.ViewPointVector = [0 0 300];
RelView.ViewDirection = {E};
RelView.ViewScaleFactor = 1;
RelView.ViewUpCoordinateSystem = EvaderRSW;
RelView.ViewUpAxis = X;
RelView.Axes = On;
RelView.Grid = On;
RelView.EnableConstellations = Off;
RelView.SolverIterations = None;

Create XYPlot DistPlot;
DistPlot.XVariable = {P}.ElapsedSecs;
DistPlot.YVariables = {{Dist}};
DistPlot.ShowGrid = true;
DistPlot.SolverIterations = None;

Create XYPlot SmaPlot;
SmaPlot.XVariable = {P}.ElapsedSecs;
SmaPlot.YVariables = {{{P}.Earth.SMA, {E}.Earth.SMA}};
SmaPlot.ShowGrid = true;
SmaPlot.SolverIterations = None;

BeginMissionSequence;""")
    # 每 STEP 秒推一步、自己算距離（GMAT 的 RMAG 不能拿太空船當原點）
    dist = (f"Dist = sqrt(({P}.X - {E}.X)^2 + ({P}.Y - {E}.Y)^2 + ({P}.Z - {E}.Z)^2);")
    row = (f"Report Rep {P}.ElapsedSecs {P}.X {P}.Y {P}.Z {E}.X {E}.Y {E}.Z "
           f"{P}.EvaderRSW.X {P}.EvaderRSW.Y {P}.EvaderRSW.Z Dist;")
    L += [dist, row]
    for k in range(len(log["rounds"])):
        L.append(f"% ---- round {k + 1} ----")
        for kk, b, ship in names:
            if kk == k:
                L.append(f"Maneuver {b}({ship});")
        L += [f"For I = 1:1:{int(round(W / STEP))};",
              f"   Propagate Synchronized Prop({P}, {E}) {{{P}.ElapsedSecs = {STEP:.1f}}};",
              "   " + dist, "   " + row, "EndFor;"]
    script = "\n".join(L) + "\n"
    script.encode("ascii")  # GMAT 腳本要純 ASCII
    with open(out, "w", encoding="ascii") as f:
        f.write(script)
    print(f"→ {out}\n  報表：{report}")


if __name__ == "__main__":
    main()
