import os
import datetime

def script_generator(
    a_sma, a_ecc, a_inc, a_raan, a_aop, a_ta,
    b_sma, b_ecc, b_inc, b_raan, b_aop, b_ta,
    burns, times, max_dv=1.5,
):
    burns_content = """
%----------------------------------------
%---------- Burns
%----------------------------------------

% DC_Targeter fine-tunes ShipB's final burn direction/magnitude so that
% ShipB's final position matches ShipA's position (diffX/Y/Z -> 0).
Create DifferentialCorrector DC_Targeter;

Create Variable diffX diffY diffZ;
GMAT diffX = 0;
GMAT diffY = 0;
GMAT diffZ = 0;
"""

    for i in range(len(burns)):
        burns_content += f"""
Create ImpulsiveBurn BurnB{i};
BurnB{i}.CoordinateSystem = Local;
BurnB{i}.Origin = Earth;
BurnB{i}.Axes = VNB;
BurnB{i}.Element1 = {burns[i][0]:.7f};
BurnB{i}.Element2 = {burns[i][1]:.7f};
BurnB{i}.Element3 = {burns[i][2]:.7f};
BurnB{i}.DecrementMass = false;
BurnB{i}.Isp = 300;
BurnB{i}.GravitationalAccel = 9.81;
"""

    mission_sequence = """
%----------------------------------------
%---------- Mission Sequence
%----------------------------------------

Create Variable MissDistance InterceptSuccess;
GMAT MissDistance = 0;
GMAT InterceptSuccess = 0;

BeginMissionSequence;
"""

    # 執行所有「非最後一次」的推進
    for i in range(len(burns) - 1):
        mission_sequence += f"""
Propagate DefaultProp(ShipA, ShipB) {{ShipA.ElapsedSecs = {times[i]:.5f}}};
Maneuver BurnB{i}(ShipB);
"""

    # 最後一次點火前的等待/海岸飛行
    final_burn_idx = len(burns) - 1
    mission_sequence += f"""
Propagate DefaultProp(ShipA, ShipB) {{ShipA.ElapsedSecs = {times[final_burn_idx]:.5f}}};
"""

    # 抓取最後一次的推力與時間，填入 Target 區塊
    v, n, b = burns[final_burn_idx]
    t_final_leg = times[-1]

    mission_sequence += f"""
% Target block: start from Python's Lambert-based guess and let GMAT's own
% higher-fidelity gravity model (J2~J4) fine-tune it. If the correction is
% large or Achieve fails to converge, Python's estimate and GMAT diverge a
% lot for this solution - don't trust it as-is.
Target DC_Targeter;

    Vary DC_Targeter(BurnB{final_burn_idx}.Element1 = {v:.7f}, {{Perturbation = 0.0001, Lower = {-max_dv}, Upper = {max_dv}, MaxStep = 0.05}});
    Vary DC_Targeter(BurnB{final_burn_idx}.Element2 = {n:.7f}, {{Perturbation = 0.0001, Lower = {-max_dv}, Upper = {max_dv}, MaxStep = 0.05}});
    Vary DC_Targeter(BurnB{final_burn_idx}.Element3 = {b:.7f}, {{Perturbation = 0.0001, Lower = {-max_dv}, Upper = {max_dv}, MaxStep = 0.05}});
    % Note: Lower/Upper are set to the rule's DeltaV_lim (1500 m/s). If the
    % correction gets stuck at this bound (Achieve fails), this burn cannot
    % converge within the legal limit - try a different solution.

    Maneuver BurnB{final_burn_idx}(ShipB);

    Propagate Synchronized DefaultProp(ShipA, ShipB) {{ShipA.ElapsedSecs = {t_final_leg:.5f}}};

    GMAT diffX = ShipA.EarthMJ2000Eq.X - ShipB.EarthMJ2000Eq.X;
    GMAT diffY = ShipA.EarthMJ2000Eq.Y - ShipB.EarthMJ2000Eq.Y;
    GMAT diffZ = ShipA.EarthMJ2000Eq.Z - ShipB.EarthMJ2000Eq.Z;

    Achieve DC_Targeter(diffX = 0.0, {{Tolerance = 0.1}});
    Achieve DC_Targeter(diffY = 0.0, {{Tolerance = 0.1}});
    Achieve DC_Targeter(diffZ = 0.0, {{Tolerance = 0.1}});

EndTarget;

% No need to eyeball the 3D view: compute the final relative distance here,
% compare it against the rule's 5 km threshold, and store it as a 0/1 flag
% that also gets written to the report file.
GMAT MissDistance = sqrt((ShipA.EarthMJ2000Eq.X - ShipB.EarthMJ2000Eq.X)^2 + (ShipA.EarthMJ2000Eq.Y - ShipB.EarthMJ2000Eq.Y)^2 + (ShipA.EarthMJ2000Eq.Z - ShipB.EarthMJ2000Eq.Z)^2);

If MissDistance <= 5
   GMAT InterceptSuccess = 1;
EndIf;

Report Report_Intercept ShipB.ElapsedSecs MissDistance InterceptSuccess;
"""

    script_content = f"""
%General Mission Analysis Tool(GMAT) Script
%Created: 2026-06-27 00:00:00
%
% ShipA = Spacecraft A (the alien ship, passive, gravity only)
% ShipB = Spacecraft B (the earth ship, active maneuvers, does the intercept)
% To check whether the intercept succeeded, no need to eyeball the 3D view:
% after running, open GMAT_InterceptReport.txt (location depends on your
% GMAT output folder setting) and look at the InterceptSuccess column:
% 1 = success, 0 = failure. MissDistance (km) is on the same row.

%----------------------------------------
%---------- Spacecraft
%----------------------------------------

Create Spacecraft ShipA;
ShipA.DateFormat = TAIModJulian;
ShipA.Epoch = '21545';
ShipA.CoordinateSystem = EarthMJ2000Eq;
ShipA.DisplayStateType = Keplerian;
ShipA.SMA = {a_sma};
ShipA.ECC = {a_ecc};
ShipA.INC = {a_inc};
ShipA.RAAN = {a_raan};
ShipA.AOP = {a_aop};
ShipA.TA = {a_ta};
ShipA.DryMass = 850;
ShipA.Cd = 2.2;
ShipA.Cr = 1.8;
ShipA.DragArea = 15;
ShipA.SRPArea = 1;

Create Spacecraft ShipB;
ShipB.DateFormat = TAIModJulian;
ShipB.Epoch = '21545';
ShipB.CoordinateSystem = EarthMJ2000Eq;
ShipB.DisplayStateType = Keplerian;
ShipB.SMA = {b_sma};
ShipB.ECC = {b_ecc};
ShipB.INC = {b_inc};
ShipB.RAAN = {b_raan};
ShipB.AOP = {b_aop};
ShipB.TA = {b_ta};
ShipB.DryMass = 850;
ShipB.Cd = 2.2;
ShipB.Cr = 1.8;
ShipB.DragArea = 15;
ShipB.SRPArea = 1;

%----------------------------------------
%---------- ForceModels
%----------------------------------------

Create ForceModel DefaultProp_ForceModel;
DefaultProp_ForceModel.CentralBody = Earth;
DefaultProp_ForceModel.PrimaryBodies = {{Earth}};
DefaultProp_ForceModel.Drag = None;
DefaultProp_ForceModel.SRP = Off;
DefaultProp_ForceModel.RelativisticCorrection = Off;
DefaultProp_ForceModel.ErrorControl = RSSStep;
DefaultProp_ForceModel.GravityField.Earth.Degree = 4;
DefaultProp_ForceModel.GravityField.Earth.Order = 4;
DefaultProp_ForceModel.GravityField.Earth.StmLimit = 100;
DefaultProp_ForceModel.GravityField.Earth.PotentialFile = 'JGM2.cof';
DefaultProp_ForceModel.GravityField.Earth.TideModel = 'None';

%----------------------------------------
%---------- Propagators
%----------------------------------------

Create Propagator DefaultProp;
DefaultProp.FM = DefaultProp_ForceModel;
DefaultProp.Type = RungeKutta89;
DefaultProp.InitialStepSize = 60;
DefaultProp.Accuracy = 9.999999999999999e-12;
DefaultProp.MinStep = 0.001;
DefaultProp.MaxStep = 2700;
DefaultProp.MaxStepAttempts = 50;
DefaultProp.StopIfAccuracyIsViolated = true;

{burns_content}

%----------------------------------------
%---------- Subscribers (3D view + text report)
%----------------------------------------

% 3D orbit view: uses the standard OrbitView (no extra plugin needed, works
% on any GMAT install). Default camera looks at Earth from a diagonal
% offset; ShipA=red, ShipB=green, Earth=gray for quick visual ID.
% This is just a visual aid - you can still freely rotate/zoom it in GMAT.
Create OrbitView View_Intercept;
View_Intercept.SolverIterations = Current;
View_Intercept.Add = {{ShipA, ShipB, Earth}};
View_Intercept.CoordinateSystem = EarthMJ2000Eq;
View_Intercept.ViewPointReference = Earth;
View_Intercept.ViewPointVector = [ 40000 40000 40000 ];
View_Intercept.ViewDirection = Earth;
View_Intercept.ViewScaleFactor = 1.3;
View_Intercept.ViewUpCoordinateSystem = EarthMJ2000Eq;
View_Intercept.ViewUpAxis = Z;
View_Intercept.OrbitColor = [ 255 65280 12632256 ];
View_Intercept.TargetColor = [ 8421504 8421504 8421504 ];
View_Intercept.XYPlane = On;
View_Intercept.Axes = On;
View_Intercept.Grid = Off;
View_Intercept.DataCollectFrequency = 1;
View_Intercept.UpdatePlotFrequency = 50;
View_Intercept.NumPointsToRedraw = 0;
View_Intercept.ShowPlot = true;

% Text report: after the run, just open this file and read the numbers -
% no need to squint at the 3D plot.
% Columns: ShipB elapsed time (s) | final MissDistance (km) | InterceptSuccess (1=success/0=fail)
Create ReportFile Report_Intercept;
Report_Intercept.SolverIterations = Current;
Report_Intercept.Filename = 'GMAT_InterceptReport.txt';
Report_Intercept.WriteHeaders = true;
Report_Intercept.Precision = 10;
Report_Intercept.ColumnWidth = 20;

{mission_sequence}
"""

    # outputs/output.txt 永遠是「最新一次」的固定路徑 (README/GMAT 流程照舊指向這裡)，
    # 同時把同樣的內容備份一份帶時間戳記的版本到 outputs/history/，避免像剛剛那樣
    # 一次測試/爛解就把前面跑出來的好結果蓋掉，想找回舊版本直接去 history 資料夾撈。
    output_path = os.path.join("outputs", "output.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(script_content)

    history_dir = os.path.join("outputs", "history")
    os.makedirs(history_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = os.path.join(history_dir, f"output_{stamp}.txt")
    with open(archive_path, "w", encoding="utf-8") as f:
        f.write(script_content)

    print(f"檔案已成功建立！(outputs/output.txt，備份於 {archive_path})")
    print("執行完後記得看 GMAT_InterceptReport.txt 確認 InterceptSuccess")
