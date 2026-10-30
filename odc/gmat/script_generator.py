# 此模組負責GMAT 任務與全攝動驗證腳本的產生。
# 主要入口為 script_generator，計算本體沿用原實作。
import os
import math
import datetime

from odc.runlog import log
from odc.config.gmat_env import (DEFAULT_EPOCH, DEFAULT_EPOCH_FORMAT, DEFAULT_SPACECRAFT,
                          FORCE_MODELS)


def _require_ascii(script_content, what="GMAT 腳本"):
    """比賽當天最不該踩的那種無聲失敗：腳本混進非 ASCII 字元。

    GMAT 的腳本語言是純 ASCII。萬一有非 ASCII 混進來（設定裡的名稱帶了中文、從別處
    貼進來的智慧引號 “ ” / 全形符號 ／ 長破折號 — 之類），寫成 UTF-8 檔 GMAT 不一定
    吃得下，而且是 GMAT 實際跑下去才炸——當天在 GMAT 的錯誤訊息裡回頭瞎猜非常慢。
    這裡在產生階段就擋，直接指出是哪一行、哪個字元。純 ASCII 的正常腳本完全不受影響。
    """
    try:
        script_content.encode("ascii")
    except UnicodeEncodeError as exc:
        bad = script_content[exc.start:exc.end]
        line_no = script_content.count("\n", 0, exc.start) + 1
        lines = script_content.splitlines()
        line_txt = lines[line_no - 1] if 1 <= line_no <= len(lines) else ""
        raise ValueError(
            f"{what}含非 ASCII 字元，GMAT 可能無法解析——請改成 ASCII。"
            f"（第 {line_no} 行，字元位置 {exc.start}）：{bad!r}\n"
            f"  → {line_txt.strip()}"
        ) from exc
    return script_content


# ---------------------------------------------------------------- 力學模型與太空船區塊
# contest_prelim 的文字必須跟改版前逐字相同（預設輸出逐位元不變，tests/test_force_model.py 釘住）。
PRELIM_SC_COMMENT = """% The DryMass/Cd/Cr/DragArea/SRPArea/BurnB*.Isp/GravitationalAccel values below
% are cosmetic: they are required fields for Spacecraft/ImpulsiveBurn objects,
% but Drag=None and SRP=Off in DefaultProp_ForceModel (see below) mean drag and
% solar radiation pressure are never actually applied, so Cd/Cr/DragArea/SRPArea
% have no effect on the propagated trajectory; BurnB*.DecrementMass = false means
% mass never decreases, so Isp/GravitationalAccel don't affect any burn's actual
% Delta-v or the resulting orbit either. The numbers below are just typical
% values for a mid-size chemical-propulsion satellite, kept here so the script
% looks complete and passes GMAT's parser - changing them will NOT change
% InterceptSuccess/FinalBurnLegal.
"""

RANKING_FULL_SC_COMMENT = """% FORCE_MODEL = ranking_full: drag and SRP are ON in DefaultProp_ForceModel, so
% DryMass/Cd/Cr/DragArea/SRPArea (or the SPAD files) below DO change the
% trajectory. They come from strategy.GMAT_SPACECRAFT / GMAT_SPACECRAFT_A in the
% config (odc/config/gmat_env.py); replace them with the organizers' values once
% announced. BurnB*.DecrementMass = false still keeps the mass constant, so
% Isp/GravitationalAccel remain cosmetic.
"""


def _g(v):
    """數字寫進腳本：850.0 → '850'、2.2 → '2.2'（跟舊腳本寫死的字面值相同）。"""
    return format(float(v), ".15g")


def spacecraft_physics_lines(ship, sc):
    """太空船的質量、阻力/輻射壓係數與面積；SPAD 檔有給才多寫那兩行。"""
    lines = [f"{ship}.DryMass = {_g(sc['DRY_MASS_KG'])};",
             f"{ship}.Cd = {_g(sc['CD'])};",
             f"{ship}.Cr = {_g(sc['CR'])};",
             f"{ship}.DragArea = {_g(sc['DRAG_AREA_M2'])};",
             f"{ship}.SRPArea = {_g(sc['SRP_AREA_M2'])};"]
    if sc.get("SPAD_DRAG_FILE"):
        lines.append(f"{ship}.SPADDragFile = '{sc['SPAD_DRAG_FILE']}';")
    if sc.get("SPAD_SRP_FILE"):
        lines.append(f"{ship}.SPADSRPFile = '{sc['SPAD_SRP_FILE']}';")
    return lines


def force_model_lines(name, force_model, gravity_degree, gravity_order=0, sc=None):
    """GMAT ForceModel 區塊。

    contest_prelim：JGM2 zonal（Order 由呼叫端給，script_generator 固定 0），無阻力/SRP——
    跟 Python 端對齊，文字跟改版前逐字相同。
    ranking_full：排位賽官方模型。設定沿用 scripts/research/perturbation_gap.py 在 GMAT R2026a
    實測可跑的寫法（EGM96.cof 與 CSSI 太空天氣檔都在 GMAT 安裝的 data/ 底下）。
    sc 給的是 B 的參數（兩艘共用同一個 ForceModel，gmat_env 已確保 SPAD 設定一致）。"""
    if force_model == "contest_prelim":
        return [f"Create ForceModel {name};",
                f"{name}.CentralBody = Earth;",
                f"{name}.PrimaryBodies = {{Earth}};",
                f"{name}.Drag = None;",
                f"{name}.SRP = Off;",
                f"{name}.RelativisticCorrection = Off;",
                f"{name}.ErrorControl = RSSStep;",
                f"{name}.GravityField.Earth.Degree = {gravity_degree};",
                f"{name}.GravityField.Earth.Order = {gravity_order};",
                f"{name}.GravityField.Earth.StmLimit = 100;",
                f"{name}.GravityField.Earth.PotentialFile = 'JGM2.cof';",
                f"{name}.GravityField.Earth.TideModel = 'None';"]
    if force_model != "ranking_full":
        raise ValueError(f"force_model must be one of {FORCE_MODELS}, got {force_model!r}")
    sc = sc or DEFAULT_SPACECRAFT
    drag_model = "SPADFile" if sc.get("SPAD_DRAG_FILE") else "Spherical"
    srp_model = "SPADFile" if sc.get("SPAD_SRP_FILE") else "Spherical"
    return [f"Create ForceModel {name};",
            f"{name}.CentralBody = Earth;",
            f"{name}.PrimaryBodies = {{Earth}};",
            f"{name}.PointMasses = {{Sun, Luna}};",
            f"{name}.Drag.AtmosphereModel = NRLMSISE00;",
            f"{name}.Drag.HistoricWeatherSource = 'CSSISpaceWeatherFile';",
            f"{name}.Drag.PredictedWeatherSource = 'CSSISpaceWeatherFile';",
            f"{name}.Drag.CSSISpaceWeatherFile = 'SpaceWeather-All-v1.2.txt';",
            f"{name}.Drag.DragModel = '{drag_model}';",
            f"{name}.SRP = On;",
            f"{name}.SRP.SRPModel = {srp_model};",
            f"{name}.RelativisticCorrection = On;",
            f"{name}.ErrorControl = RSSStep;",
            f"{name}.GravityField.Earth.Degree = 20;",
            f"{name}.GravityField.Earth.Order = 20;",
            f"{name}.GravityField.Earth.StmLimit = 100;",
            f"{name}.GravityField.Earth.PotentialFile = 'EGM96.cof';",
            f"{name}.GravityField.Earth.TideModel = 'SolidAndPole';"]


ORBIT_KEYS = ("SMA", "ECC", "INC", "RAAN", "AOP", "TA")
DENSE_REPORT_COLUMNS = (["SC_Human.ElapsedSecs"]
                        + [f"SC_Human.EarthMJ2000Eq.{c}" for c in ("X", "Y", "Z", "VX", "VY", "VZ")]
                        + [f"SC_Alien.EarthMJ2000Eq.{c}" for c in ("X", "Y", "Z", "VX", "VY", "VZ")])


def full_perturbation_script(orbit_A, orbit_B, burns, times, env, *, gravity_degree=4,
                             report_path=None, retarget_idx=None, bplane=None,
                             summary_path=None, vary_bound_kms=2.0,
                             ext_sec=600.0, max_step=60.0, stop_alt_km=50.0):
    """全攝動重瞄準用的兩種 GMAT 腳本（回傳腳本文字，不寫檔）。

    retarget_idx 為 None：重播版。每個積分步寫一列兩船狀態到 report_path（MaxStep 限在
    max_step 秒，讓 Python 端用 Hermite 內插找最近點），預定攔截時刻之後再多傳 ext_sec 秒
    （最近點可能晚到）。
    retarget_idx 給定：B 平面 DC 版。Vary 第 retarget_idx 棒的 VNB 三分量，只 Achieve
    「預定攔截時刻相對位置在 bplane 兩個單位向量上的投影 = 0」（垂直於相對速度的兩個分量）；
    沿相對速度的分量只會讓最近點早到或晚到幾秒，不花 Δv 去修。收斂後把該棒三分量和相對
    位置寫到 summary_path。不用「預定時刻位置對齊」：那在 hyper_far 會多花 272 m/s、
    把最後一棒推到 361 m/s（docs/research/PERTURBATION_GAP_20261019.md §4）。

    每段 Propagate 都帶 SC_Human 高度 stop_alt_km 的停止條件：攔截後 B 常一路鑽進大氣層，
    MSISE 密度會讓 RK89 卡在最小步長。所有路徑都必須是絕對路徑（GmatConsole 會切到 bin/）。
    燃燒/滑行時間的寫法跟繳交腳本一致（滑行 .5f），重播的才是會被繳交的那一份。"""
    sc_A, sc_B = env["sc_A"], env["sc_B"]
    fm = env["force_model"]
    dc = retarget_idx is not None
    if dc and (bplane is None or summary_path is None):
        raise ValueError("B 平面 DC 版需要 bplane（兩個單位向量）與 summary_path")
    if not dc and report_path is None:
        raise ValueError("重播版需要 report_path")
    for path in (report_path, summary_path):
        if path is not None and (not str(path).startswith("/") or any(c in str(path) for c in "'\n\r")):
            raise ValueError(f"GMAT 輸出路徑必須是不含引號的絕對路徑：{path!r}")
    L = ["% generated by odc/gmat/script_generator.py full_perturbation_script",
         f"% FORCE_MODEL = {fm}; " + ("B-plane DifferentialCorrector on BurnB%d" % retarget_idx
                                       if dc else "dense replay report")]
    for ship, orbit, sc in (("SC_Alien", orbit_A, sc_A), ("SC_Human", orbit_B, sc_B)):
        L += [f"Create Spacecraft {ship};",
              f"{ship}.DateFormat = {env['epoch_format']};",
              f"{ship}.Epoch = '{env['epoch']}';",
              f"{ship}.CoordinateSystem = EarthMJ2000Eq;",
              f"{ship}.DisplayStateType = Keplerian;"]
        L += [f"{ship}.{k} = {float(orbit[k])!r};" for k in ORBIT_KEYS]
        L += spacecraft_physics_lines(ship, sc)
    L += force_model_lines("FM", fm, gravity_degree, 0, sc_B)
    L += ["Create Propagator Prop;", "Prop.FM = FM;", "Prop.Type = RungeKutta89;",
          "Prop.InitialStepSize = 60;", "Prop.Accuracy = 1e-12;", "Prop.MinStep = 0.001;",
          f"Prop.MaxStep = {_g(max_step)};", "Prop.MaxStepAttempts = 50;",
          "Prop.StopIfAccuracyIsViolated = false;"]
    for k, b in enumerate(burns):
        L += [f"Create ImpulsiveBurn BurnB{k};", f"BurnB{k}.CoordinateSystem = Local;",
              f"BurnB{k}.Origin = Earth;", f"BurnB{k}.Axes = VNB;"]
        L += [f"BurnB{k}.Element{i + 1} = {float(b[i])!r};" for i in range(3)]
        L += [f"BurnB{k}.DecrementMass = false;"]
    if dc:
        L += ["Create ReportFile RS;", "RS.SolverIterations = None;",
              f"RS.Filename = '{summary_path}';", "RS.Precision = 16;", "RS.WriteHeaders = false;",
              "Create DifferentialCorrector DC;", "DC.MaximumIterations = 40;",
              "DC.DerivativeMethod = ForwardDifference;", "DC.Algorithm = NewtonRaphson;",
              "Create Variable dX dY dZ p1 p2;"]
    else:
        L += ["Create ReportFile RF;", "RF.SolverIterations = None;",
              f"RF.Filename = '{report_path}';", "RF.Precision = 16;", "RF.WriteHeaders = false;",
              "RF.ZeroFill = Off;", "RF.Add = {%s};" % ", ".join(DENSE_REPORT_COLUMNS)]

    def prop(secs):
        return ("Propagate Prop(SC_Alien, SC_Human) {SC_Alien.ElapsedSecs = %.5f, SC_Human.Earth.Altitude = %s};"
                % (secs, _g(stop_alt_km)))
    L.append("BeginMissionSequence;")
    for k, b in enumerate(burns):
        if times[k] > 0:
            L.append(prop(times[k]))
        if dc and k == retarget_idx:
            # 被 Vary 那棒之前的滑行留在 Target 迴圈外面，迴圈只重算這棒之後
            L.append("Target DC {SolveMode = Solve, ExitMode = SaveAndContinue};")
            for i in range(3):
                # 上下限要比原本的分量大，不然卡在邊界看起來像發散（研究報告 §6）
                bound = max(float(vary_bound_kms), abs(float(b[i])) + 0.5)
                L.append(f"  Vary DC(BurnB{k}.Element{i + 1} = {float(b[i])!r}, {{Perturbation = 1e-6, "
                         f"Lower = {-bound!r}, Upper = {bound!r}, MaxStep = 0.01}});")
        L.append(f"Maneuver BurnB{k}(SC_Human);")
    L.append(prop(times[-1]))
    if dc:
        L += [f"  GMAT d{c} = SC_Human.EarthMJ2000Eq.{c} - SC_Alien.EarthMJ2000Eq.{c};" for c in "XYZ"]
        for name, e in zip(("p1", "p2"), bplane):
            L.append(f"  GMAT {name} = dX*({float(e[0])!r}) + dY*({float(e[1])!r}) + dZ*({float(e[2])!r});")
            L.append(f"  Achieve DC({name} = 0, {{Tolerance = 0.02}});")
        k = retarget_idx
        L += ["EndTarget;",
              f"Report RS BurnB{k}.Element1 BurnB{k}.Element2 BurnB{k}.Element3 dX dY dZ;"]
    elif ext_sec > 0:
        L.append(prop(ext_sec))
    return _require_ascii("\n".join(L) + "\n", "全攝動重瞄準腳本")


def script_generator(
    a_sma, a_ecc, a_inc, a_raan, a_aop, a_ta,
    b_sma, b_ecc, b_inc, b_raan, b_aop, b_ta,
    burns, times, aim_point, max_dv=1.5, gravity_degree=2,
    final_burn_fixed_vnb=None, output_filename="output.txt",
    model_scale=0.5, output_dir="outputs", report_filename="GMAT_InterceptReport.txt",
    force_model="contest_prelim", sc_A=None, sc_B=None,
    epoch=DEFAULT_EPOCH, epoch_format=DEFAULT_EPOCH_FORMAT,
):
    """
    force_model / sc_A / sc_B / epoch / epoch_format: GMAT-side environment, see
    odc/config/gmat_env.py (main.py passes resolve_gmat_env(config)). The defaults
    reproduce the pre-2026-10-19 script byte for byte: "contest_prelim" is the
    JGM2 zonal model aligned with Python; "ranking_full" switches the ForceModel
    to the ranking round's official model (EGM96 20x20, SolidAndPole tides,
    NRLMSISE00 drag, Sun/Luna, SRP, relativity) and makes the spacecraft
    DryMass/Cd/Cr/areas physically meaningful. gravity_degree only applies to
    contest_prelim. Note the normal (DC) variant still aims at a fixed-time
    position; under ranking_full use main.py --retarget-full-perturbation
    (B-plane DC) instead - see docs/research/PERTURBATION_GAP_20261019.md section 4.

    gravity_degree: highest zonal (m=0) harmonic to include, matching Python's
    strategy.GRAVITY_DEGREE exactly (0=point mass, 2=J2, 3=J2+J3, 4=J2+J3+J4).
    Sets GMAT's GravityField.Earth.Degree; Order is always pinned to 0
    regardless of this value (see the comment near the Degree/Order lines
    below for why).

    aim_point: (x, y, z) in km, EarthMJ2000Eq — the point the final burn's
    Target/Achieve block should actually converge onto. This is usually NOT
    SC_Alien's exact position: the optimizer is free to aim anywhere within the
    rule's miss-distance tolerance to save fuel (see MissionOptimizer /
    MISS_TOLERANCE_KM), so the GMAT-side targeter has to chase the SAME point
    Python optimized for — targeting SC_Alien exactly here would silently
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
    if any(c in str(report_filename) for c in ("'", "\n", "\r")):
        raise ValueError("GMAT report filename contains invalid characters")
    aim_x, aim_y, aim_z = aim_point
    fixed_mode = final_burn_fixed_vnb is not None
    final_burn_idx = len(burns) - 1

    burns_content = ""
    if not fixed_mode:
        burns_content += """
%----------------------------------------
%---------- Burns
%----------------------------------------

% DC_Targeter fine-tunes SC_Human's final burn direction/magnitude so that
% SC_Human's final position matches the aim point chosen by the optimizer
% (may be deliberately offset from SC_Alien within the rule's miss tolerance).
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
Propagate DefaultProp(SC_Alien, SC_Human) {{SC_Alien.ElapsedSecs = {times[i]:.5f}}};
Maneuver BurnB{i}(SC_Human);
"""

    # 最後一次點火前的等待/海岸飛行
    mission_sequence += f"""
Propagate DefaultProp(SC_Alien, SC_Human) {{SC_Alien.ElapsedSecs = {times[final_burn_idx]:.5f}}};
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

    Maneuver BurnB{final_burn_idx}(SC_Human);

    Propagate Synchronized DefaultProp(SC_Alien, SC_Human) {{SC_Alien.ElapsedSecs = {t_final_leg:.5f}}};

    % Target the aim point the optimizer actually chose (EarthMJ2000Eq, km) -
    % NOT SC_Alien's exact position. It may be deliberately offset from SC_Alien by
    % up to the rule's miss-distance tolerance to save fuel; targeting SC_Alien
    % exactly here would silently override that design with a different
    % (and possibly more expensive) correction.
    % Tolerance tightened to 0.01 km (10 m) per axis: the aim point can sit as
    % close as ~50-150 m inside the true 5 km miss-distance limit (see
    % MissionOptimizer.MISS_TOLERANCE_SOFT), so a loose per-axis tolerance
    % here could let the worst-case combined 3-axis error (sqrt(3)*tol) push
    % the actual miss distance over the real rule threshold.
    Achieve DC_Targeter(SC_Human.EarthMJ2000Eq.X = {aim_x:.7f}, {{Tolerance = 0.01}});
    Achieve DC_Targeter(SC_Human.EarthMJ2000Eq.Y = {aim_y:.7f}, {{Tolerance = 0.01}});
    Achieve DC_Targeter(SC_Human.EarthMJ2000Eq.Z = {aim_z:.7f}, {{Tolerance = 0.01}});

EndTarget;
"""
    else:
        # 固定版本：最後一棒跟其他棒一樣直接施加，沒有 Target/Vary/Achieve，
        # 沒有任何求解器要「跑」——單純傳播 + 施加燃燒。
        mission_sequence += f"""
% Submission variant: no solver here - this burn's Element1/2/3 are already
% GMAT's own converged answer (baked in above), so we just apply it directly
% like every other burn and propagate to the intercept time.
Maneuver BurnB{final_burn_idx}(SC_Human);

Propagate DefaultProp(SC_Alien, SC_Human) {{SC_Alien.ElapsedSecs = {t_final_leg:.5f}}};
"""

    mission_sequence += f"""
% No need to eyeball the 3D view: compute the final relative distance here,
% compare it against the rule's 5 km threshold, and store it as a 0/1 flag
% that also gets written to the report file.
GMAT MissDistance = sqrt((SC_Alien.EarthMJ2000Eq.X - SC_Human.EarthMJ2000Eq.X)^2 + (SC_Alien.EarthMJ2000Eq.Y - SC_Human.EarthMJ2000Eq.Y)^2 + (SC_Alien.EarthMJ2000Eq.Z - SC_Human.EarthMJ2000Eq.Z)^2);

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
Report Report_Intercept SC_Human.ElapsedSecs MissDistance InterceptSuccess FinalBurnDvMps FinalBurnLegal BurnB{final_burn_idx}.Element1 BurnB{final_burn_idx}.Element2 BurnB{final_burn_idx}.Element3;
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


    header_note = (
        "% SUBMISSION VARIANT: every burn (including the final one) is a fixed\n"
        "% value - no solver runs in this script. See the comment near 'Burns' below.\n"
        if fixed_mode else
        "% NORMAL VARIANT: the final burn is found by GMAT's own DifferentialCorrector\n"
        "% (Target/Vary/Achieve). See the comment near 'Burns' below.\n"
    )

    if force_model not in FORCE_MODELS:
        raise ValueError(f"force_model must be one of {FORCE_MODELS}, got {force_model!r}")
    full_model = force_model == "ranking_full"
    sc_A = {**DEFAULT_SPACECRAFT, **(sc_A or {})}
    sc_B = {**DEFAULT_SPACECRAFT, **(sc_B or {})}
    if full_model:
        header_note += (
            "% FORCE MODEL: ranking_full (EGM96 20x20, SolidAndPole tides, NRLMSISE00\n"
            "% drag, Sun/Luna, SRP, relativity) - the ranking round's official model.\n"
        )
        sc_comment = RANKING_FULL_SC_COMMENT
    else:
        sc_comment = PRELIM_SC_COMMENT
    phys_A = "\n".join(spacecraft_physics_lines("SC_Alien", sc_A))
    phys_B = "\n".join(spacecraft_physics_lines("SC_Human", sc_B))
    fm_block = "\n".join(force_model_lines("DefaultProp_ForceModel", force_model, gravity_degree,
                                            gravity_order, sc_B))

    script_content = f"""
%General Mission Analysis Tool(GMAT) Script
%Created: 2026-06-27 00:00:00
%
{header_note}%
% SC_Alien = Spacecraft A (the alien ship, passive, gravity only)
% SC_Human = Spacecraft B (the earth ship, active maneuvers, does the intercept)
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

{sc_comment}Create Spacecraft SC_Alien;
SC_Alien.DateFormat = {epoch_format};
SC_Alien.Epoch = '{epoch}';
SC_Alien.CoordinateSystem = EarthMJ2000Eq;
SC_Alien.DisplayStateType = Keplerian;
SC_Alien.SMA = {a_sma};
SC_Alien.ECC = {a_ecc};
SC_Alien.INC = {a_inc};
SC_Alien.RAAN = {a_raan};
SC_Alien.AOP = {a_aop};
SC_Alien.TA = {a_ta};
{phys_A}
% Trajectory colors belong on the Spacecraft in R2026a, not on the OrbitView
% (OrbitView.OrbitColor/TargetColor were removed - setting them there is
% silently ignored and emits an interpreter warning). Purely a visual aid.
SC_Alien.OrbitColor = Red;
SC_Alien.TargetColor = Gray;
% ModelScale: GMAT defaults to 3.0, which only suits small-orbit scenes. The
% camera distance now scales with orbit size (see View_Intercept) but the
% spacecraft model does not shrink with it, so a large scene ends up as a
% screenful of spacecraft. Raise strategy.GMAT_MODEL_SCALE if it is too small.
SC_Alien.ModelScale = {model_scale};

Create Spacecraft SC_Human;
SC_Human.DateFormat = {epoch_format};
SC_Human.Epoch = '{epoch}';
SC_Human.CoordinateSystem = EarthMJ2000Eq;
SC_Human.DisplayStateType = Keplerian;
SC_Human.SMA = {b_sma};
SC_Human.ECC = {b_ecc};
SC_Human.INC = {b_inc};
SC_Human.RAAN = {b_raan};
SC_Human.AOP = {b_aop};
SC_Human.TA = {b_ta};
{phys_B}
SC_Human.OrbitColor = Lime;
SC_Human.TargetColor = Gray;
SC_Human.ModelScale = {model_scale};

%----------------------------------------
%---------- ForceModels
%----------------------------------------

{fm_block}

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
% offset; SC_Alien=red, SC_Human=green, Earth=gray for quick visual ID.
% This is just a visual aid - you can still freely rotate/zoom it in GMAT.
Create OrbitView View_Intercept;
View_Intercept.SolverIterations = Current;
View_Intercept.Add = {{SC_Alien, SC_Human, Earth}};
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

% NON-ASCII WARNING: keep every comment in this file plain ASCII - GMAT's
% parser rejects the whole script outright if any non-ASCII character sneaks
% in (bit this exact bug once already, see commit 887e64e and STATUS.md).
% Text report: after the run, just open this file and read the numbers -
% no need to squint at the 3D plot.
% Columns: SC_Human elapsed time (s) | final MissDistance (km) | InterceptSuccess
% (1=success/0=fail) | FinalBurnDvMps (actual post-convergence magnitude of
% the last burn, m/s) | FinalBurnLegal (1=<=1500 m/s, 0=violated the limit) |
% final burn's Element1/2/3 (VNB components, km/s)
Create ReportFile Report_Intercept;
Report_Intercept.SolverIterations = Current;
Report_Intercept.Filename = '{report_filename}';
Report_Intercept.WriteHeaders = true;
Report_Intercept.Precision = 10;
Report_Intercept.ColumnWidth = 20;

{mission_sequence}
"""

    # GMAT 的腳本語言是純 ASCII，寫檔前 fail-fast 擋掉非 ASCII（見 _require_ascii）。
    _require_ascii(script_content)

    # outputs/<output_filename> 永遠是「這個變體最新一次」的固定路徑，同時把同樣的
    # 內容備份一份帶時間戳記的版本到 outputs/history/，避免像剛剛那樣一次測試/爛解
    # 就把前面跑出來的好結果蓋掉，想找回舊版本直接去 history 資料夾撈。
    # outputs/ 整個被 .gitignore 排除，全新 git clone 下來這個資料夾根本不存在
    # (git 不會建立空資料夾)，這裡的 makedirs 之前漏了，寫檔案前一定要先確保資料夾在。
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, output_filename)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(script_content)

    history_dir = os.path.join(output_dir, "history")
    os.makedirs(history_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    stem, ext = os.path.splitext(output_filename)
    archive_path = os.path.join(history_dir, f"{stem}_{stamp}{ext}")
    with open(archive_path, "w", encoding="utf-8") as f:
        f.write(script_content)

    log.info(f"📄 GMAT script 已建立：{output_path} (備份於 {archive_path})")
    return output_path
