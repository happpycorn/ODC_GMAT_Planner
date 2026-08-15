import os
import math
import datetime

def script_generator(
    a_sma, a_ecc, a_inc, a_raan, a_aop, a_ta,
    b_sma, b_ecc, b_inc, b_raan, b_aop, b_ta,
    burns, times, aim_point, max_dv=1.5, gravity_degree=2,
    final_burn_fixed_vnb=None, output_filename="output.txt",
    model_scale=0.5,
):
    """
    gravity_degree: highest zonal (m=0) harmonic to include, matching Python's
    strategy.GRAVITY_DEGREE exactly (0=point mass, 2=J2, 3=J2+J3, 4=J2+J3+J4).
    Sets GMAT's GravityField.Earth.Degree; Order is always pinned to 0
    regardless of this value (see the comment near the Degree/Order lines
    below for why).

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
    to these exact VNB components and applied directly like every other burn
    — no solver runs anywhere in this script. Rationale: once a burn value has
    already been found and validated once, baking it in as a constant removes
    any dependency on a solver behaving identically on whatever machine
    actually runs the submission — it's pure propagate-and-maneuver, nothing
    to "not converge".

    This value normally comes from one of two sources (see main.py):
    (a) GMAT's own *converged* DC answer, read back from a prior normal-mode
        run — the usual, most-trusted case. The DC's Vary bounds are clamped
        to [-max_dv, max_dv], so a value from this source is always legal by
        construction.
    (b) A fallback: Python's own refine_lambert_burn result, used when the
        normal DC-based script failed to converge or missed the target. This
        happens whenever the true required burn exceeds max_dv — the DC's
        Vary bounds structurally cannot reach it, so it can never converge no
        matter how good the underlying solution is (the rules only deduct 10
        points per violating maneuver, they don't disqualify — see
        Regulations section 5 — so an over-limit-but-intercepting solution
        can still be worth submitting). A value from this source is NOT
        guaranteed legal — check FinalBurnLegal in the report.
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

    # 重力場階數：gravity_degree 直接對應 Python 端的 strategy.GRAVITY_DEGREE
    # (0=點質量, 2=J2, 3=J2+J3, 4=J2+J3+J4)，不要讓兩邊各算各的、開的擾動項不一樣。
    #
    # Order 這裡刻意固定收在 0 (2026-08-14 改)，不管 Degree 是多少——GMAT 的
    # Degree/Order 分別對應球諧重力場的 n (階) / m (序)，m=0 那一整排就是 zonal
    # harmonic (J2/J3/J4，跟緯度有關、不跟經度有關)，m>0 是 tesseral/sectoral
    # (經度也有關的重力異常項)。Python 端 (core_math.fast_dynamics) 目前只實作了
    # zonal 項，沒有能力算 tesseral——如果這裡讓 Order 跟著 Degree 一起開到 4
    # (像原本 use_j2 那樣)，GMAT 會多算一堆 Python 端完全沒有的重力異常，兩邊注定
    # 對不齊。固定 Order=0 讓 GMAT 只算 zonal，跟 Python 端做的事完全一致，才有
    # 意義比較兩者的傳播結果——這個決定犧牲了 GMAT 端的「真實感」(真實地球重力場
    # 本來就不是純 zonal) 換取「兩邊模型對齊、可以互相驗證」，是刻意的取捨。
    gravity_order = 0

    # 3D 視角的相機距離：依實際軌道大小算，不要寫死 (2026-08-15 改)。
    #
    # 原本 ViewPointVector 固定 [40000 40000 40000] (距地心約 69,000 km)，遠地點
    # 十幾萬公里的情境開起來整條軌道都在畫面外，每次都要手動拉遠才看得到全貌。
    # 改成用「A/B 之中最大的遠地點」推算：相機放在 2.5 倍那個距離的對角線方向上，
    # 這個倍率實測在小軌道 (LEO 圓軌道) 到大橢圓 (遠地點 19 萬公里) 都能一眼看完。
    #
    # 雙曲線 A (排位賽情境) 沒有遠地點 (SMA<0、ECC>1)，退回用近地點的 8 倍當尺度
    # ——雙曲線的「看得到的部分」大致就在近地點附近幾倍半徑內。
    def _orbit_extent(sma, ecc):
        if sma > 0.0 and ecc < 1.0:
            return sma * (1.0 + ecc)          # 橢圓/圓：遠地點
        return abs(sma * (1.0 - ecc)) * 8.0   # 雙曲線：近地點的幾倍

    view_extent = max(_orbit_extent(a_sma, a_ecc), _orbit_extent(b_sma, b_ecc))
    # 對角線方向 [1,1,1] 的每軸分量：|V| = 分量 × sqrt(3)，要讓 |V| = 2.5 × extent
    view_axis = view_extent * 2.5 / math.sqrt(3.0)

    # 追蹤視角的相機距離也要依情境算 (2026-08-15)。原本寫死 [500 0 200] (距 ShipB
    # 約 540 km)，但 B 本身離地心才 7,000 km 上下，相機貼那麼近的結果是整個畫面被
    # 地球塞滿，連地球全貌都看不到，更別說看出飛船相對軌道在哪。
    #
    # 取「B 的遠地點」跟一個下限的較大者：地球半徑 6,378 km，相機大約要離地心
    # 30,000 km 以上才能把整顆地球舒服地framed 進畫面，所以下限抓 20,000 km
    # (加上 B 自己的軌道半徑後大致就落在那個範圍)。B 的軌道很大時則跟著放大，
    # 不然遠地點十幾萬公里的情境又會變成貼太近。
    chase_dist = max(20000.0, _orbit_extent(b_sma, b_ecc) * 1.5)
    # 方向沿用原本的「後上方」比例 (500:200 = 5:2)，只是整體拉遠
    chase_back = chase_dist * 5.0 / math.sqrt(29.0)
    chase_up = chase_dist * 2.0 / math.sqrt(29.0)

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
% Trajectory colors belong on the Spacecraft in R2026a, not on the OrbitView
% (OrbitView.OrbitColor/TargetColor were removed - setting them there is
% silently ignored and emits an interpreter warning). Purely a visual aid.
ShipA.OrbitColor = Red;
ShipA.TargetColor = Gray;
% ModelScale: GMAT defaults to 3.0, which only suits small-orbit scenes. The
% camera distance now scales with orbit size (see View_Intercept) but the
% spacecraft model does not shrink with it, so a large scene ends up as a
% screenful of spacecraft - worst in the ShipB chase view, whose camera sits
% only ~540 km from the ship. Raise strategy.GMAT_MODEL_SCALE if it is too small.
ShipA.ModelScale = {model_scale};

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
ShipB.OrbitColor = Lime;
ShipB.TargetColor = Gray;
ShipB.ModelScale = {model_scale};

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
View_Intercept.ViewPointVector = [ {view_axis:.0f} {view_axis:.0f} {view_axis:.0f} ];
View_Intercept.ViewDirection = Earth;
View_Intercept.ViewScaleFactor = 1.0;
View_Intercept.ViewUpCoordinateSystem = EarthMJ2000Eq;
View_Intercept.ViewUpAxis = Z;
View_Intercept.XYPlane = On;
View_Intercept.Axes = On;
View_Intercept.Grid = Off;
View_Intercept.DataCollectFrequency = 1;
View_Intercept.UpdatePlotFrequency = 50;
View_Intercept.NumPointsToRedraw = 0;
View_Intercept.ShowPlot = true;

% Second 3D view (2026-08-14 added): a chase camera anchored near ShipB,
% always aimed at ShipA. The view above is a fixed Earth-centered overview of
% the whole scene; this one is "what B sees" - the camera follows ShipB
% (ViewPointReference=ShipB moves with it every frame) and keeps ShipA in
% frame, making the final-approach geometry/alignment much easier to read
% visually than the wide Earth view.
%
% BUGFIX (2026-08-14, found by real GMAT testing): the first version put
% ViewPointVector=[500 500 500] in the EarthMJ2000Eq frame - a FIXED inertial
% direction, not something that tracks ShipB's own position. ShipB's orbital
% radius (~6400-7000km for a typical LEO) is only a few hundred km bigger than
% Earth's own radius (6378km), and the offset's magnitude (~866km) is bigger
% than that margin - so whenever ShipB's orbital phase put it in roughly the
% opposite direction from the fixed [500 500 500] vector, the offset
% subtracted more from ShipB's distance-from-Earth than that margin allowed,
% putting the camera INSIDE the Earth (looked like being swallowed by the
% planet). Fixed by defining the offset in a coordinate system anchored on
% ShipB itself with an axis that always points radially outward from Earth
% (Axes=ObjectReferenced, XAxis=R with Primary=Earth/Secondary=ShipB) instead
% of a fixed inertial direction - the camera is now always further from Earth
% than ShipB by construction, regardless of orbital phase.
Create CoordinateSystem ShipBChaseFrame;
ShipBChaseFrame.Origin = ShipB;
ShipBChaseFrame.Axes = ObjectReferenced;
ShipBChaseFrame.XAxis = R;
ShipBChaseFrame.ZAxis = N;
ShipBChaseFrame.Primary = Earth;
ShipBChaseFrame.Secondary = ShipB;

% NON-ASCII WARNING: keep every comment in this file plain ASCII - GMAT's
% parser rejects the whole script outright if any non-ASCII character sneaks
% in (bit this exact bug once already, see commit 887e64e and STATUS.md).
Create OrbitView View_ShipBChase;
View_ShipBChase.SolverIterations = Current;
View_ShipBChase.Add = {{ShipA, ShipB, Earth}};
View_ShipBChase.CoordinateSystem = ShipBChaseFrame;
View_ShipBChase.ViewPointReference = ShipB;
View_ShipBChase.ViewPointVector = [ {chase_back:.0f} 0 {chase_up:.0f} ];
View_ShipBChase.ViewDirection = ShipA;
View_ShipBChase.ViewScaleFactor = 1.0;
View_ShipBChase.ViewUpCoordinateSystem = EarthMJ2000Eq;
View_ShipBChase.ViewUpAxis = Z;
View_ShipBChase.XYPlane = Off;
View_ShipBChase.Axes = On;
View_ShipBChase.Grid = Off;
View_ShipBChase.DataCollectFrequency = 1;
View_ShipBChase.UpdatePlotFrequency = 50;
View_ShipBChase.NumPointsToRedraw = 0;
View_ShipBChase.ShowPlot = true;

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
    # outputs/ 整個被 .gitignore 排除，全新 git clone 下來這個資料夾根本不存在
    # (git 不會建立空資料夾)，這裡的 makedirs 之前漏了，寫檔案前一定要先確保資料夾在。
    os.makedirs("outputs", exist_ok=True)
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
