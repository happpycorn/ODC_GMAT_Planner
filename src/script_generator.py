import os
import datetime

def script_generator(
    a_sma, a_ecc, a_inc, a_raan, a_aop, a_ta,
    b_sma, b_ecc, b_inc, b_raan, b_aop, b_ta,
    burns, times, aim_point, max_dv=1.5, use_j2=True,
    final_burn_fixed_vnb=None, output_filename="output.txt",
):
    """
    aim_point: (x, y, z) in km, EarthMJ2000Eq — the point the final burn's
    Target/Achieve block should actually converge onto. This is usually NOT
    ShipA's exact position: the optimizer is free to aim anywhere within the
    rule's miss-distance tolerance to save fuel (see MissionOptimizer /
    MISS_TOLERANCE_KM), so the GMAT-side targeter has to chase the SAME point
    Python optimized for — targeting ShipA exactly here would silently
    overwrite that fuel-saving design with GMAT's own (likely different,
    possibly more expensive) correction.

    final_burn_fixed_vnb: None (default) generates the normal script, where
    the final burn goes through GMAT's own Target/Vary/Achieve differential
    corrector (starting from Python's Lambert-based guess) to converge onto
    aim_point using GMAT's own higher-fidelity model. Pass a (v, n, b) tuple
    here instead to generate a "submission" variant: the final burn is fixed
    to these exact VNB components (normally GMAT's own *converged* answer
    from a prior DC run, read back from the report) and applied directly like
    every other burn — no solver runs anywhere in this script. Rationale:
    once GMAT's DC has already found and validated the correct burn once,
    baking that answer in as a constant removes any dependency on the DC
    solver behaving identically on whatever machine actually runs the
    submission — it's pure propagate-and-maneuver, nothing to "not converge".
    See METHODOLOGY.md/STATUS.md for the full reasoning.
    """
    aim_x, aim_y, aim_z = aim_point
    fixed_mode = final_burn_fixed_vnb is not None
    final_burn_idx = len(burns) - 1

    burns_content = ""
    if not fixed_mode:
        burns_content += """
%----------------------------------------
%---------- Burns
%----------------------------------------

% DC_Targeter fine-tunes ShipB's final burn direction/magnitude so that
% ShipB's final position matches the aim point chosen by the optimizer
% (may be deliberately offset from ShipA within the rule's miss tolerance).
Create DifferentialCorrector DC_Targeter;
"""
    else:
        burns_content += """
%----------------------------------------
%---------- Burns
%----------------------------------------

% Submission variant: every burn below (including the final one) is a fixed,
% pre-computed value - no DifferentialCorrector anywhere in this script. The
% final burn's Element1/2/3 are GMAT's own *converged* answer from a prior
% Target/Vary/Achieve run (see script_generator()'s docstring), not Python's
% raw estimate, so this script only needs to propagate and apply maneuvers -
% nothing here needs to "solve" or "converge".
"""

    for i in range(len(burns)):
        if fixed_mode and i == final_burn_idx:
            v, n, b = final_burn_fixed_vnb
        else:
            v, n, b = burns[i]
        burns_content += f"""
Create ImpulsiveBurn BurnB{i};
BurnB{i}.CoordinateSystem = Local;
BurnB{i}.Origin = Earth;
BurnB{i}.Axes = VNB;
BurnB{i}.Element1 = {v:.7f};
BurnB{i}.Element2 = {n:.7f};
BurnB{i}.Element3 = {b:.7f};
% DecrementMass=false: mass never decreases, so Isp/GravitationalAccel below
% are cosmetic-only (300s is a typical bipropellant value) - see the comment
% above the Spacecraft block for the full explanation.
BurnB{i}.DecrementMass = false;
BurnB{i}.Isp = 300;
BurnB{i}.GravitationalAccel = 9.81;
"""

    mission_sequence = """
%----------------------------------------
%---------- Mission Sequence
%----------------------------------------

Create Variable MissDistance InterceptSuccess FinalBurnDvMps FinalBurnLegal;
GMAT MissDistance = 0;
GMAT InterceptSuccess = 0;
GMAT FinalBurnDvMps = 0;
GMAT FinalBurnLegal = 0;

BeginMissionSequence;
"""

    # 執行所有「非最後一次」的推進
    for i in range(len(burns) - 1):
        mission_sequence += f"""
Propagate DefaultProp(ShipA, ShipB) {{ShipA.ElapsedSecs = {times[i]:.5f}}};
Maneuver BurnB{i}(ShipB);
"""

    # 最後一次點火前的等待/海岸飛行
    mission_sequence += f"""
Propagate DefaultProp(ShipA, ShipB) {{ShipA.ElapsedSecs = {times[final_burn_idx]:.5f}}};
"""

    t_final_leg = times[-1]

    if not fixed_mode:
        v, n, b = burns[final_burn_idx]
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

    % Target the aim point the optimizer actually chose (EarthMJ2000Eq, km) -
    % NOT ShipA's exact position. It may be deliberately offset from ShipA by
    % up to the rule's miss-distance tolerance to save fuel; targeting ShipA
    % exactly here would silently override that design with a different
    % (and possibly more expensive) correction.
    % Tolerance tightened to 0.01 km (10 m) per axis: the aim point can sit as
    % close as ~50-150 m inside the true 5 km miss-distance limit (see
    % MissionOptimizer.MISS_TOLERANCE_SOFT), so a loose per-axis tolerance
    % here could let the worst-case combined 3-axis error (sqrt(3)*tol) push
    % the actual miss distance over the real rule threshold.
    Achieve DC_Targeter(ShipB.EarthMJ2000Eq.X = {aim_x:.7f}, {{Tolerance = 0.01}});
    Achieve DC_Targeter(ShipB.EarthMJ2000Eq.Y = {aim_y:.7f}, {{Tolerance = 0.01}});
    Achieve DC_Targeter(ShipB.EarthMJ2000Eq.Z = {aim_z:.7f}, {{Tolerance = 0.01}});

EndTarget;
"""
    else:
        # 固定版本：最後一棒跟其他棒一樣直接施加，沒有 Target/Vary/Achieve，
        # 沒有任何求解器要「跑」——單純傳播 + 施加燃燒。
        mission_sequence += f"""
% Submission variant: no solver here - this burn's Element1/2/3 are already
% GMAT's own converged answer (baked in above), so we just apply it directly
% like every other burn and propagate to the intercept time.
Maneuver BurnB{final_burn_idx}(ShipB);

Propagate DefaultProp(ShipA, ShipB) {{ShipA.ElapsedSecs = {t_final_leg:.5f}}};
"""

    mission_sequence += f"""
% No need to eyeball the 3D view: compute the final relative distance here,
% compare it against the rule's 5 km threshold, and store it as a 0/1 flag
% that also gets written to the report file.
GMAT MissDistance = sqrt((ShipA.EarthMJ2000Eq.X - ShipB.EarthMJ2000Eq.X)^2 + (ShipA.EarthMJ2000Eq.Y - ShipB.EarthMJ2000Eq.Y)^2 + (ShipA.EarthMJ2000Eq.Z - ShipB.EarthMJ2000Eq.Z)^2);

If MissDistance <= 5
   GMAT InterceptSuccess = 1;
EndIf;

% The Target/Vary/Achieve block above (normal mode) is free to move this burn
% anywhere within its Lower/Upper bounds to hit the aim point - Python's
% predicted magnitude for this burn is NOT necessarily what GMAT actually
% converged to. Compute the real magnitude here so a violation of the rule's
% 1500 m/s per-burn limit can never happen without showing up in the report
% (previously this was invisible: InterceptSuccess only checked distance,
% never the Delta-v GMAT's own corrector actually used). In fixed-burn mode
% this just confirms the baked-in value is still legal.
GMAT FinalBurnDvMps = sqrt(BurnB{final_burn_idx}.Element1^2 + BurnB{final_burn_idx}.Element2^2 + BurnB{final_burn_idx}.Element3^2) * 1000;

If FinalBurnDvMps <= {max_dv * 1000.0:.1f}
   GMAT FinalBurnLegal = 1;
EndIf;

% Element1/2/3 of the final burn are reported too so main.py can read back
% GMAT's own converged answer (normal mode) and bake it into the fixed-burn
% submission variant - see script_generator()'s docstring.
Report Report_Intercept ShipB.ElapsedSecs MissDistance InterceptSuccess FinalBurnDvMps FinalBurnLegal BurnB{final_burn_idx}.Element1 BurnB{final_burn_idx}.Element2 BurnB{final_burn_idx}.Element3;
"""

    # J2 開關：不確定的話用 use_j2 切換，跟 Python 端的 USE_J2 保持同步，不要一邊有
    # 擾動一邊沒有 —— Degree/Order=4 涵蓋 J2~J4 等項；關掉就退回純點質量 (0/0)。
    gravity_degree = 4 if use_j2 else 0
    gravity_order = 4 if use_j2 else 0

    header_note = (
        "% SUBMISSION VARIANT: every burn (including the final one) is a fixed\n"
        "% value - no solver runs in this script. See the comment near 'Burns' below.\n"
        if fixed_mode else
        "% NORMAL VARIANT: the final burn is found by GMAT's own DifferentialCorrector\n"
        "% (Target/Vary/Achieve). See the comment near 'Burns' below.\n"
    )

    script_content = f"""
%General Mission Analysis Tool(GMAT) Script
%Created: 2026-06-27 00:00:00
%
{header_note}%
% ShipA = Spacecraft A (the alien ship, passive, gravity only)
% ShipB = Spacecraft B (the earth ship, active maneuvers, does the intercept)
% To check whether the intercept succeeded, no need to eyeball the 3D view:
% after running, open GMAT_InterceptReport.txt (location depends on your
% GMAT output folder setting) and check TWO columns, both must be 1:
% - InterceptSuccess: 1 = got within the 5 km miss-distance rule, 0 = failed
% - FinalBurnLegal: 1 = the final burn's ACTUAL post-convergence magnitude
%   (FinalBurnDvMps) stayed within the 1500 m/s rule limit, 0 = violated it.
%   This is the burn GMAT's own targeter is free to adjust to hit the aim
%   point, so its real magnitude can differ from what Python predicted -
%   InterceptSuccess alone does NOT tell you whether this burn is legal.

%----------------------------------------
%---------- Spacecraft
%----------------------------------------

% The DryMass/Cd/Cr/DragArea/SRPArea/BurnB*.Isp/GravitationalAccel values below
% are cosmetic: they are required fields for Spacecraft/ImpulsiveBurn objects,
% but Drag=None and SRP=Off in DefaultProp_ForceModel (see below) mean drag and
% solar radiation pressure are never actually applied, so Cd/Cr/DragArea/SRPArea
% have no effect on the propagated trajectory; BurnB*.DecrementMass = false means
% mass never decreases, so Isp/GravitationalAccel don't affect any burn's actual
% Delta-v or the resulting orbit either. The numbers below are just typical
% values for a mid-size chemical-propulsion satellite, kept here so the script
% looks complete and passes GMAT's parser - changing them will NOT change
% InterceptSuccess/FinalBurnLegal.
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
ShipA.DragArea = 6;
ShipA.SRPArea = 8;

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
ShipB.DragArea = 6;
ShipB.SRPArea = 8;

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
DefaultProp_ForceModel.GravityField.Earth.Degree = {gravity_degree};
DefaultProp_ForceModel.GravityField.Earth.Order = {gravity_order};
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
% Columns: ShipB elapsed time (s) | final MissDistance (km) | InterceptSuccess
% (1=success/0=fail) | FinalBurnDvMps (actual post-convergence magnitude of
% the last burn, m/s) | FinalBurnLegal (1=<=1500 m/s, 0=violated the limit) |
% final burn's Element1/2/3 (VNB components, km/s)
Create ReportFile Report_Intercept;
Report_Intercept.SolverIterations = Current;
Report_Intercept.Filename = 'GMAT_InterceptReport.txt';
Report_Intercept.WriteHeaders = true;
Report_Intercept.Precision = 10;
Report_Intercept.ColumnWidth = 20;

{mission_sequence}
"""

    # outputs/<output_filename> 永遠是「這個變體最新一次」的固定路徑，同時把同樣的
    # 內容備份一份帶時間戳記的版本到 outputs/history/，避免像剛剛那樣一次測試/爛解
    # 就把前面跑出來的好結果蓋掉，想找回舊版本直接去 history 資料夾撈。
    output_path = os.path.join("outputs", output_filename)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(script_content)

    history_dir = os.path.join("outputs", "history")
    os.makedirs(history_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    stem, ext = os.path.splitext(output_filename)
    archive_path = os.path.join(history_dir, f"{stem}_{stamp}{ext}")
    with open(archive_path, "w", encoding="utf-8") as f:
        f.write(script_content)

    print(f"📄 GMAT script 已建立：outputs/{output_filename} (備份於 {archive_path})")
    return output_path
