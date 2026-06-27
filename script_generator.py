def script_generator(
    a_sma, a_ecc, a_inc, a_raan, a_aop, a_ta,
    b_sma, b_ecc, b_inc, b_raan, b_aop, b_ta,
    burns, times,
):
    burns_content = """
%----------------------------------------
%---------- Burns
%----------------------------------------
"""

    for i in range(len(burns)):
        burns_content += f"""

Create ImpulsiveBurn ImpulsiveBurn{i};
ImpulsiveBurn{i}.CoordinateSystem = Local;
ImpulsiveBurn{i}.Origin = Earth;
ImpulsiveBurn{i}.Axes = VNB;
ImpulsiveBurn{i}.Element1 = {burns[i][0]};
ImpulsiveBurn{i}.Element2 = {burns[i][1]};
ImpulsiveBurn{i}.Element3 = {burns[i][2]};
ImpulsiveBurn{i}.DecrementMass = false;
ImpulsiveBurn{i}.Isp = 300;
ImpulsiveBurn{i}.GravitationalAccel = 9.81;
"""

    mission_sequence = """
%----------------------------------------
%---------- Mission Sequence
%----------------------------------------

"""
    for i in range(len(burns)):
        mission_sequence += f"""
BeginMissionSequence;
Propagate DefaultProp(Ship1, Ship2) {{Ship1.ElapsedSecs = {times[i]:.2f}}};
Maneuver ImpulsiveBurn{i}(Ship2);
"""
    mission_sequence += f"Propagate DefaultProp(Ship1, Ship2) {{Ship1.ElapsedSecs = {times[-1]:.2f}}};"

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
Ship1.SPADDragScaleFactor = 1;
Ship1.SPADSRPScaleFactor = 1;
Ship1.AtmosDensityScaleFactor = 1;
Ship1.ExtendedMassPropertiesModel = 'None';
Ship1.NAIFId = -10000001;
Ship1.NAIFIdReferenceFrame = -9000001;
Ship1.OrbitColor = Red;
Ship1.TargetColor = Teal;
Ship1.OrbitErrorCovariance = [ 1e+70 0 0 0 0 0 ; 0 1e+70 0 0 0 0 ; 0 0 1e+70 0 0 0 ; 0 0 0 1e+70 0 0 ; 0 0 0 0 1e+70 0 ; 0 0 0 0 0 1e+70 ];
Ship1.CdSigma = 1e+70;
Ship1.CrSigma = 1e+70;
Ship1.Id = 'SatId';
Ship1.Attitude = CoordinateSystemFixed;
Ship1.SPADSRPInterpolationMethod = Bilinear;
Ship1.SPADSRPScaleFactorSigma = 1e+70;
Ship1.SPADDragInterpolationMethod = Bilinear;
Ship1.SPADDragScaleFactorSigma = 1e+70;
Ship1.AtmosDensityScaleFactorSigma = 1e+70;
Ship1.ModelFile = 'aura.3ds';
Ship1.ModelOffsetX = 0;
Ship1.ModelOffsetY = 0;
Ship1.ModelOffsetZ = 0;
Ship1.ModelRotationX = 0;
Ship1.ModelRotationY = 0;
Ship1.ModelRotationZ = 0;
Ship1.ModelScale = 1;
Ship1.AttitudeDisplayStateType = 'Quaternion';
Ship1.AttitudeRateDisplayStateType = 'AngularVelocity';
Ship1.AttitudeCoordinateSystem = EarthMJ2000Eq;
Ship1.EulerAngleSequence = '321';

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
Ship2.SPADDragScaleFactor = 1;
Ship2.SPADSRPScaleFactor = 1;
Ship2.AtmosDensityScaleFactor = 1;
Ship2.ExtendedMassPropertiesModel = 'None';
Ship2.NAIFId = -10000001;
Ship2.NAIFIdReferenceFrame = -9000001;
Ship2.OrbitColor = Blue;
Ship2.TargetColor = Teal;
Ship2.OrbitErrorCovariance = [ 1e+70 0 0 0 0 0 ; 0 1e+70 0 0 0 0 ; 0 0 1e+70 0 0 0 ; 0 0 0 1e+70 0 0 ; 0 0 0 0 1e+70 0 ; 0 0 0 0 0 1e+70 ];
Ship2.CdSigma = 1e+70;
Ship2.CrSigma = 1e+70;
Ship2.Id = 'SatId';
Ship2.Attitude = CoordinateSystemFixed;
Ship2.SPADSRPInterpolationMethod = Bilinear;
Ship2.SPADSRPScaleFactorSigma = 1e+70;
Ship2.SPADDragInterpolationMethod = Bilinear;
Ship2.SPADDragScaleFactorSigma = 1e+70;
Ship2.AtmosDensityScaleFactorSigma = 1e+70;
Ship2.ModelFile = 'aura.3ds';
Ship2.ModelOffsetX = 0;
Ship2.ModelOffsetY = 0;
Ship2.ModelOffsetZ = 0;
Ship2.ModelRotationX = 0;
Ship2.ModelRotationY = 0;
Ship2.ModelRotationZ = 0;
Ship2.ModelScale = 1;
Ship2.AttitudeDisplayStateType = 'Quaternion';
Ship2.AttitudeRateDisplayStateType = 'AngularVelocity';
Ship2.AttitudeCoordinateSystem = EarthMJ2000Eq;
Ship2.EulerAngleSequence = '321';

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
DefaultOrbitView.UpperLeft = [ 0.1925170068027211 0.1924686192468619 ];
DefaultOrbitView.Size = [ 0.3693877551020408 0.3096234309623431 ];
DefaultOrbitView.RelativeZOrder = 92;
DefaultOrbitView.Maximized = false;
DefaultOrbitView.Add = {{Ship1, Ship2, Earth}};
DefaultOrbitView.View = {{DefaultOrbitView_View}};
DefaultOrbitView.CoordinateSystem = EarthMJ2000Eq;
DefaultOrbitView.DrawObject = [ true true true ];
DefaultOrbitView.DrawTrajectory = [ true true true ];
DefaultOrbitView.DrawAxes = [ false false false ];
DefaultOrbitView.DrawXYPlane = [ false false false ];
DefaultOrbitView.DrawLabel = [ true true true ];
DefaultOrbitView.DrawUsePropLabel = [ false false false ];
DefaultOrbitView.DrawCenterPoint = [ true true true ];
DefaultOrbitView.DrawEndPoints = [ true true true ];
DefaultOrbitView.DrawVelocity = [ false false false ];
DefaultOrbitView.DrawGrid = [ false false false ];
DefaultOrbitView.DrawLineWidth = [ 2 2 2 ];
DefaultOrbitView.DrawMarkerSize = [ 10 10 10 ];
DefaultOrbitView.DrawFontSize = [ 20 20 20 ];
DefaultOrbitView.Axes = On;
DefaultOrbitView.AxesLength = 12756.2726;
DefaultOrbitView.AxesLabels = On;
DefaultOrbitView.FrameLabel = Off;
DefaultOrbitView.XYPlane = On;
DefaultOrbitView.EclipticPlane = Off;
DefaultOrbitView.EnableStars = On;
DefaultOrbitView.StarCatalog = 'inp_StarsHYGv3.txt';
DefaultOrbitView.StarCount = 40000;
DefaultOrbitView.MinStarMag = -2;
DefaultOrbitView.MaxStarMag = 6;
DefaultOrbitView.MinStarPixels = 1;
DefaultOrbitView.MaxStarPixels = 10;
DefaultOrbitView.MinStarDimRatio = 0.5;
DefaultOrbitView.ShowPlot = true;
DefaultOrbitView.ShowToolbar = true;
DefaultOrbitView.SolverIterLastN = 1;
DefaultOrbitView.ShowVR = false;
DefaultOrbitView.PlaybackTimeScale = 3600;
DefaultOrbitView.MultisampleAntiAliasing = On;
DefaultOrbitView.MSAASamples = 2;
DefaultOrbitView.DrawFontPosition = {{'Top-Right', 'Top-Right', 'Top-Right'}};

Create GroundTrack DefaultGroundTrackPlot;
DefaultGroundTrackPlot.SolverIterations = Current;
DefaultGroundTrackPlot.UpperLeft = [ 0.4047619047619048 0.4675732217573222 ];
DefaultGroundTrackPlot.Size = [ 0.4163265306122449 0.3629707112970711 ];
DefaultGroundTrackPlot.RelativeZOrder = 90;
DefaultGroundTrackPlot.Maximized = false;
DefaultGroundTrackPlot.CentralBody = Earth;
DefaultGroundTrackPlot.Add = {{Ship1, Ship2}};
DefaultGroundTrackPlot.DataCollectFrequency = 1;
DefaultGroundTrackPlot.UpdatePlotFrequency = 50;
DefaultGroundTrackPlot.NumPointsToRedraw = 0;
DefaultGroundTrackPlot.MaxPlotPoints = 20000;
DefaultGroundTrackPlot.ShowPlot = true;

%----------------------------------------
%---------- User Objects
%----------------------------------------

Create OpenFramesView DefaultOrbitView_View;
DefaultOrbitView_View.ViewFrame = CoordinateSystem;
DefaultOrbitView_View.ViewTrajectory = Off;
DefaultOrbitView_View.InertialFrame = Off;
DefaultOrbitView_View.SetDefaultLocation = On;
DefaultOrbitView_View.DefaultEye = [ 30000 0 0 ];
DefaultOrbitView_View.DefaultCenter = [ 0 0 0 ];
DefaultOrbitView_View.DefaultUp = [ 0 0 1 ];
DefaultOrbitView_View.SetCurrentLocation = On;
DefaultOrbitView_View.CurrentEye = [ 9965.899370474219 -7960.359075847184 27153.51787745298 ];
DefaultOrbitView_View.CurrentCenter = [ -3.637978807091713e-12 0 -3.637978807091713e-12 ];
DefaultOrbitView_View.CurrentUp = [ -0.8272102470879261 0.3790966391791704 0.4147396114139451 ];
DefaultOrbitView_View.FOVy = 45;

{mission_sequence}

""")

    print("檔案已成功建立！")