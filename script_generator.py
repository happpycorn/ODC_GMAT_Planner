def script_generator(
    a_sma, a_ecc, a_inc, a_raan, a_aop, a_ta,
    b_sma, b_ecc, b_inc, b_raan, b_aop, b_ta,
    burns, times,
):
    burns_content = """
%----------------------------------------
%---------- Burns
%----------------------------------------

Create DifferentialCorrector DC1;

Create Variable diffX diffY diffZ;
GMAT diffX = 0;
GMAT diffY = 0;
GMAT diffZ = 0;
"""

    for i in range(len(burns)):
        burns_content += f"""
Create ImpulsiveBurn ImpulsiveBurn{i};
ImpulsiveBurn{i}.CoordinateSystem = Local;
ImpulsiveBurn{i}.Origin = Earth;
ImpulsiveBurn{i}.Axes = VNB;
ImpulsiveBurn{i}.Element1 = {burns[i][0]:.7f};
ImpulsiveBurn{i}.Element2 = {burns[i][1]:.7f};
ImpulsiveBurn{i}.Element3 = {burns[i][2]:.7f};
ImpulsiveBurn{i}.DecrementMass = false;
ImpulsiveBurn{i}.Isp = 300;
ImpulsiveBurn{i}.GravitationalAccel = 9.81;
"""

    mission_sequence = """
%----------------------------------------
%---------- Mission Sequence
%----------------------------------------

Create Variable MissDistance;
GMAT MissDistance = 0;

BeginMissionSequence;
"""
    
    # 執行所有「非最後一次」的推進
    for i in range(len(burns) - 1):
        mission_sequence += f"""
Propagate DefaultProp(Ship1, Ship2) {{Ship1.ElapsedSecs = {times[i]:.5f}}};
Maneuver ImpulsiveBurn{i}(Ship2);
"""

    # 最後一次點火前的等待/海岸飛行
    final_burn_idx = len(burns) - 1
    mission_sequence += f"""
Propagate DefaultProp(Ship1, Ship2) {{Ship1.ElapsedSecs = {times[final_burn_idx]:.5f}}};
"""

    # 抓取最後一次的推力與時間，填入 Target 區塊
    v, n, b = burns[final_burn_idx]
    t_final_leg = times[-1]

    mission_sequence += f"""
Target DC1;
    
    Vary DC1(ImpulsiveBurn{final_burn_idx}.Element1 = {v:.7f}, {{Perturbation = 0.0001, Lower = -3, Upper = 3, MaxStep = 0.05}});
    Vary DC1(ImpulsiveBurn{final_burn_idx}.Element2 = {n:.7f}, {{Perturbation = 0.0001, Lower = -3, Upper = 3, MaxStep = 0.05}});
    Vary DC1(ImpulsiveBurn{final_burn_idx}.Element3 = {b:.7f}, {{Perturbation = 0.0001, Lower = -3, Upper = 3, MaxStep = 0.05}});

    Maneuver ImpulsiveBurn{final_burn_idx}(Ship2);

    Propagate Synchronized DefaultProp(Ship1, Ship2) {{Ship1.ElapsedSecs = {t_final_leg:.5f}}};

    GMAT diffX = Ship1.EarthMJ2000Eq.X - Ship2.EarthMJ2000Eq.X;
    GMAT diffY = Ship1.EarthMJ2000Eq.Y - Ship2.EarthMJ2000Eq.Y;
    GMAT diffZ = Ship1.EarthMJ2000Eq.Z - Ship2.EarthMJ2000Eq.Z;

    Achieve DC1(diffX = 0.0, {{Tolerance = 0.1}});
    Achieve DC1(diffY = 0.0, {{Tolerance = 0.1}});
    Achieve DC1(diffZ = 0.0, {{Tolerance = 0.1}});
    
EndTarget;

GMAT MissDistance = sqrt((Ship1.EarthMJ2000Eq.X - Ship2.EarthMJ2000Eq.X)^2 + (Ship1.EarthMJ2000Eq.Y - Ship2.EarthMJ2000Eq.Y)^2 + (Ship1.EarthMJ2000Eq.Z - Ship2.EarthMJ2000Eq.Z)^2);
"""

    with open("output.txt", "w", encoding="utf-8") as f:
        f.write(f"""
%General Mission Analysis Tool(GMAT) Script
%Created: 2026-06-27 00:00:00

%----------------------------------------
%---------- Spacecraft
%----------------------------------------

Create Spacecraft Ship1;
Ship1.DateFormat = TAIModJulian;
Ship1.Epoch = '21545';
Ship1.CoordinateSystem = EarthMJ2000Eq;
Ship1.DisplayStateType = Keplerian;
Ship1.SMA = {a_sma};
Ship1.ECC = {a_ecc};
Ship1.INC = {a_inc};
Ship1.RAAN = {a_raan};
Ship1.AOP = {a_aop};
Ship1.TA = {a_ta};
Ship1.DryMass = 850;
Ship1.Cd = 2.2;
Ship1.Cr = 1.8;
Ship1.DragArea = 15;
Ship1.SRPArea = 1;

Create Spacecraft Ship2;
Ship2.DateFormat = TAIModJulian;
Ship2.Epoch = '21545';
Ship2.CoordinateSystem = EarthMJ2000Eq;
Ship2.DisplayStateType = Keplerian;
Ship2.SMA = {b_sma};
Ship2.ECC = {b_ecc};
Ship2.INC = {b_inc};
Ship2.RAAN = {b_raan};
Ship2.AOP = {b_aop};
Ship2.TA = {b_ta};
Ship2.DryMass = 850;
Ship2.Cd = 2.2;
Ship2.Cr = 1.8;
Ship2.DragArea = 15;
Ship2.SRPArea = 1;

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
%---------- Subscribers
%----------------------------------------

Create OpenFramesInterface DefaultOrbitView;
DefaultOrbitView.SolverIterations = Current;
DefaultOrbitView.Add = {{Ship1, Ship2, Earth}};
DefaultOrbitView.CoordinateSystem = EarthMJ2000Eq;
DefaultOrbitView.DrawObject = [ true true true ];
DefaultOrbitView.DrawTrajectory = [ true true true ];
DefaultOrbitView.Axes = On;
DefaultOrbitView.XYPlane = On;

{mission_sequence}
""")

    print("檔案已成功建立！")