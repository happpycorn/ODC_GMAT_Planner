"""GMAT 一致性驗證（HAP-56）：把一整局的機動序列原封不動丟進 GMAT 重播，逐回合比對雙方位置。

訓練與搜尋用的是 physics/ 的 numba 引擎；決賽官方用 GMAT 模擬。這支工具確認兩邊對同一局
（同初始狀態、同脈衝序列、同重力模型）給出一樣的軌跡——差距遠小於捕獲半徑，勝負判定
才可信。

GMAT 端設定刻意跟 Planner 已驗證過的 script_generator 一致：
  * GravityField Degree = rules.gravity_degree、Order = 0（只有 zonal，與 core_math 相同）、JGM2.cof
  * Drag/SRP/相對論修正全關、RungeKutta89、Accuracy 1e-11
  * 初始狀態直接給 EarthMJ2000Eq 笛卡兒座標（避開六根數退化的轉換差異）
  * 脈衝用 ImpulsiveBurn（CoordinateSystem = EarthMJ2000Eq，km/s），DecrementMass = false

力學模型 `force_model`：
  * "zonal"（預設）：上面那組，跟引擎對齊，用來驗引擎正確性
  * "ranking_full"：排位賽官方驗證模型（EGM96 20×20、SolidAndPole 潮汐、NRLMSISE00 阻力、
    Sun/Luna、SRP、相對論）。ForceModel 文字逐字搬自 ~/ODC_GMAT_Planner/src/script_generator.py
    的 force_model_lines（Planner 已在 GMAT R2026a 實測可跑）；太空船參數用 Planner 的預設佔位值
    （850 kg、Cd 2.2、Cr 1.8、阻力面積 6 m²、輻射壓面積 8 m²），主辦單位還沒公布。
    引擎只有 J2–J4，這個模式量的是「官方真實世界」跟引擎的落差（彩排用）。

用法：
    uv run python tools/gmat_verify.py --pursuer lambert_pursuer --evader dv_evader --seed 0
    uv run python tools/gmat_verify.py --rules configs/rulesets/ranking_like.json --force-model ranking_full
    uv run python tools/gmat_verify.py --rules configs/rulesets/final_official.json --scenario final --evader random

金／銅牌賽（simultaneous）的回合紀錄 side == "both"：回合起點兩艘各自 Maneuver（零向量略過），
再一起 Propagate Synchronized 滑行 coast_sec；每回合結束仍 Report 一列（回合數 + 1 列）。
力學用 force_model="zonal" + gravity_degree=0 就是點質量（純二體）。
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

GMAT_CONSOLE = os.path.expanduser(os.environ.get(
    "GMAT_CONSOLE", "~/software/GMAT/GMAT/R2026a/bin/GmatConsole"))

_STATE_FIELDS = ["X", "Y", "Z", "VX", "VY", "VZ"]


FORCE_MODELS = ("zonal", "ranking_full")
# Planner gmat_env.DEFAULT_SPACECRAFT（排位賽參數未公布前的佔位）
FULL_SPACECRAFT = {"DryMass": "850", "Cd": "2.2", "Cr": "1.8", "DragArea": "6", "SRPArea": "8"}
DEFAULT_EPOCH_TAI_MJD = 21545.0


def spacecraft_parameters(overrides=None):
    """共用的雙船參數；只接受既有欄位及有限正數，保留預設值的字面格式。"""
    values = dict(FULL_SPACECRAFT)
    for key, value in (overrides or {}).items():
        if key not in values:
            raise ValueError(f"未知太空船參數：{key}")
        if not np.isfinite(float(value)) or float(value) <= 0.0:
            raise ValueError(f"{key} 必須是有限正數")
        values[key] = f"{float(value):.15g}"
    return values


def _ranking_full_fm():
    return """
Create ForceModel FM;
FM.CentralBody = Earth;
FM.PrimaryBodies = {Earth};
FM.PointMasses = {Sun, Luna};
FM.Drag.AtmosphereModel = NRLMSISE00;
FM.Drag.HistoricWeatherSource = 'CSSISpaceWeatherFile';
FM.Drag.PredictedWeatherSource = 'CSSISpaceWeatherFile';
FM.Drag.CSSISpaceWeatherFile = 'SpaceWeather-All-v1.2.txt';
FM.Drag.DragModel = 'Spherical';
FM.SRP = On;
FM.SRP.SRPModel = Spherical;
FM.RelativisticCorrection = On;
FM.ErrorControl = RSSStep;
FM.GravityField.Earth.Degree = 20;
FM.GravityField.Earth.Order = 20;
FM.GravityField.Earth.StmLimit = 100;
FM.GravityField.Earth.PotentialFile = 'EGM96.cof';
FM.GravityField.Earth.TideModel = 'SolidAndPole';
"""


def _epoch(offset_sec, epoch_tai_mjd=DEFAULT_EPOCH_TAI_MJD):
    """任務曆元（TAIModJulian）；全攝動下日月位置與太空天氣跟曆元有關，逐回合推進時要跟著走。"""
    if not np.isfinite(epoch_tai_mjd) or not np.isfinite(offset_sec):
        raise ValueError("曆元及偏移必須是有限數值")
    return ("21545" if offset_sec == 0.0 and epoch_tai_mjd == DEFAULT_EPOCH_TAI_MJD
            else f"{epoch_tai_mjd + offset_sec / 86400.0:.12f}")


def _sc_block(name, r, v, force_model="zonal", epoch_offset_sec=0.0, *, spacecraft=None,
              epoch_tai_mjd=DEFAULT_EPOCH_TAI_MJD):
    lines = [f"Create Spacecraft {name};",
             f"{name}.DateFormat = TAIModJulian;",
             f"{name}.Epoch = '{_epoch(epoch_offset_sec, epoch_tai_mjd)}';",
             f"{name}.CoordinateSystem = EarthMJ2000Eq;",
             f"{name}.DisplayStateType = Cartesian;"]
    for fld, val in zip(_STATE_FIELDS, list(r) + list(v)):
        lines.append(f"{name}.{fld} = {val:.15f};")
    if force_model == "ranking_full":
        lines += [f"{name}.{k} = {v};" for k, v in spacecraft_parameters(spacecraft).items()]
    else:
        lines.append(f"{name}.DryMass = {spacecraft_parameters(spacecraft)['DryMass']};")
    return "\n".join(lines)


_SHIP = {"pursuer": "ShipP", "evader": "ShipE"}


def _burns(rec):
    """回合紀錄裡的各發（一回合多發，HAP-107）；舊格式紀錄只有一發。"""
    return rec.get("burns") or [{"t": rec["t"], "dv_eci_mps": rec["dv_eci_mps"], "dv_mps": rec["dv_mps"]}]


def _burn_name(k, j):
    return f"B{k}" if j == 0 else f"B{k}_{j}"


def game_to_script(game, report_path, force_model="zonal", dense_path=None, epoch_offset_sec=0.0, *,
                   spacecraft=None, epoch_tai_mjd=DEFAULT_EPOCH_TAI_MJD):
    """把 Game（含 history）轉成 GMAT 腳本字串。

    dense_path 給定時多一個每個積分步都寫的報表（MaxStep 60 s），給 analyze_dense 找真實最近距離。"""
    if force_model not in FORCE_MODELS:
        raise ValueError(f"force_model 必須是 {FORCE_MODELS}，收到 {force_model!r}")
    R = game.rules
    rp0, vp0 = game.initial["pursuer"]
    re0, ve0 = game.initial["evader"]
    rep_cols = " ".join(
        ["ShipP.ElapsedSecs"]
        + [f"ShipP.EarthMJ2000Eq.{f}" for f in _STATE_FIELDS]
        + [f"ShipE.EarthMJ2000Eq.{f}" for f in _STATE_FIELDS])

    parts = [
        "% Auto-generated by ODC_GMAT_DRL tools/gmat_verify.py - replay of one pursuit-evasion game",
        _sc_block("ShipP", rp0, vp0, force_model, epoch_offset_sec,
                  spacecraft=spacecraft, epoch_tai_mjd=epoch_tai_mjd),
        _sc_block("ShipE", re0, ve0, force_model, epoch_offset_sec,
                  spacecraft=spacecraft, epoch_tai_mjd=epoch_tai_mjd),
        (_ranking_full_fm() if force_model == "ranking_full" else f"""
Create ForceModel FM;
FM.CentralBody = Earth;
FM.PrimaryBodies = {{Earth}};
FM.Drag = None;
FM.SRP = Off;
FM.RelativisticCorrection = Off;
FM.ErrorControl = RSSStep;
FM.GravityField.Earth.Degree = {int(R.gravity_degree)};
FM.GravityField.Earth.Order = 0;
FM.GravityField.Earth.StmLimit = 100;
FM.GravityField.Earth.PotentialFile = 'JGM2.cof';
FM.GravityField.Earth.TideModel = 'None';
""") + f"""
Create Propagator Prop;
Prop.FM = FM;
Prop.Type = RungeKutta89;
Prop.InitialStepSize = 60;
Prop.Accuracy = 9.999999999999999e-12;
Prop.MinStep = 0.001;
Prop.MaxStep = {60 if dense_path else 2700};
Prop.MaxStepAttempts = 50;
Prop.StopIfAccuracyIsViolated = {"false" if force_model == "ranking_full" else "true"};
""",
    ]
    for k, rec in enumerate(game.history):
        for j, b in enumerate(_burns(rec)):
            dv = np.asarray(b["dv_eci_mps"]) / 1000.0
            name = _burn_name(k, j)
            parts.append(f"""Create ImpulsiveBurn {name};
{name}.CoordinateSystem = EarthMJ2000Eq;
{name}.Element1 = {dv[0]:.15f};
{name}.Element2 = {dv[1]:.15f};
{name}.Element3 = {dv[2]:.15f};
{name}.DecrementMass = false;
{name}.Isp = 300;
{name}.GravitationalAccel = 9.81;""")
    parts.append(f"""
Create ReportFile Rep;
Rep.Filename = '{report_path}';
Rep.WriteHeaders = false;
Rep.Precision = 16;
Rep.ColumnWidth = 26;
""" + (f"""
Create ReportFile RF;
RF.SolverIterations = None;
RF.Filename = '{dense_path}';
RF.Precision = 16;
RF.WriteHeaders = false;
RF.ZeroFill = Off;
RF.Add = {{{rep_cols.replace(" ", ", ")}}};
""" if dense_path else "") + f"""
BeginMissionSequence;
Report Rep {rep_cols};""")
    for k, rec in enumerate(game.history):
        seq = []
        bs = _burns(rec)
        for j, b in enumerate(bs):
            if b["dv_mps"] > 0.0:
                # simultaneous 紀錄（side == "both"）每發帶自己的 side，同一時刻依序施加、滑行段長 0
                seq.append(f"Maneuver {_burn_name(k, j)}({_SHIP[b.get('side', rec['side'])]});")
            # 這一發到下一發（或窗口結束）的滑行；單發時就是整個窗口
            end = (bs[j + 1]["t"] - rec["t"]) if j + 1 < len(bs) else rec["coast_sec"]
            seg = end - (b["t"] - rec["t"])
            if seg > 0.0:
                # ⚠️ 停止條件的 ElapsedSecs 是「從這個 Propagate 指令開始」算的（報表裡的
                # ElapsedSecs 才是從初始 epoch 起算）——所以這裡要給這段的長度，不是累積時間
                seq.append(f"Propagate Synchronized Prop(ShipP, ShipE) {{ShipP.ElapsedSecs = {seg:.9f}}};")
        seq.append(f"Report Rep {rep_cols};")
        parts.append("\n".join(seq))
    script = "\n".join(parts) + "\n"
    script.encode("ascii")   # GMAT 腳本必須是純 ASCII（Planner 踩過的雷）
    return script


def instrument_dense_script(script):
    """只在執行副本補初末、窗口末及脈衝前後取樣，避免跨速度跳變內插。

    game_to_script 的預設文字保持相容；密集驗證及敏感度計畫共用這個插樁。"""
    match = re.search(r"^RF.Add = \{([^}]+)\};$", script, re.MULTILINE)
    if match is None:
        raise ValueError("密集驗證腳本缺少 RF.Add")
    report = "Report RF " + match[1].replace(",", "") + ";"
    script = script.replace("BeginMissionSequence;", "BeginMissionSequence;\n" + report, 1)
    script = re.sub(r"^Maneuver [^\n]+;$", lambda m: report + "\n" + m[0] + "\n" + report,
                    script, flags=re.MULTILINE)
    return re.sub(r"^Report Rep [^\n]+;$", lambda m: m[0] + "\n" + report,
                  script, flags=re.MULTILINE)


def run_gmat(script, console=GMAT_CONSOLE, timeout=600, dense=False):
    """跑 GMAT，回傳報表陣列 (n_rows, 13)：t, P(x..vz), E(x..vz)。

    dense=True 時腳本裡的 __DENSE__ 會換成暫存檔路徑，回傳 (回合報表, 密集報表)。"""
    if not os.path.exists(console):
        raise FileNotFoundError(f"找不到 GmatConsole：{console}（可用環境變數 GMAT_CONSOLE 指定）")
    if dense:
        script = instrument_dense_script(script)
    with tempfile.TemporaryDirectory(prefix="gmat_verify_") as td:
        rep = os.path.join(td, "replay_report.txt")
        spath = os.path.join(td, "replay.script")
        dpath = os.path.join(td, "dense_report.txt")
        with open(spath, "w") as f:
            f.write(script.replace("__REPORT__", rep).replace("__DENSE__", dpath))
        res = subprocess.run([console, "--exit", "--run", spath], cwd=os.path.dirname(console),
                             capture_output=True, text=True, timeout=timeout)
        if res.returncode != 0 or not os.path.exists(rep):
            tail = "\n".join((res.stdout or "").strip().splitlines()[-20:])
            raise RuntimeError(f"GMAT 執行失敗（exit {res.returncode}）：\n{tail}")
        rows = np.loadtxt(rep, ndmin=2)
        if dense:
            dense_rows = _read_rows(dpath)
            validate_dense_reports(rows, dense_rows)
            return rows, dense_rows
        return rows


def _read_rows(path):
    """密集報表 → (n, 13)；格式不對的列略過（GMAT 偶爾會寫半行）。"""
    out = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.split()
            if len(parts) != 13:
                continue
            try:
                vals = [float(x) for x in parts]
            except ValueError:
                continue
            if all(np.isfinite(vals)):
                out.append(vals)
    return np.array(out, dtype=float).reshape(-1, 13)


def validate_dense_reports(rows, dense, *, expected_rows=None, duration_sec=None):
    """半行、提前停止或缺一整段資料不能被解讀為閘門通過。"""
    for array in (rows, dense):
        if (array.ndim != 2 or array.shape[1] != 13 or not len(array)
                or not np.all(np.isfinite(array)) or np.any(np.diff(array[:, 0]) < -1e-6)):
            raise ValueError("GMAT 報表不是完整、有限且按時間排序的 (n, 13) 陣列")
    duration = float(rows[-1, 0]) if duration_sec is None else float(duration_sec)
    if ((expected_rows is not None and len(rows) != expected_rows)
            or abs(rows[0, 0]) > 1e-3 or abs(dense[0, 0]) > 1e-3
            or abs(rows[-1, 0]-duration) > 1e-3 or abs(dense[-1, 0]-duration) > 1e-3
            or np.any(np.diff(dense[:, 0]) > 60.001)):
        raise ValueError("GMAT 報表未完整涵蓋預定窗口／整場，或密集輸出有缺口")


def _hermite(t0, t1, p0, v0, p1, v1, s):
    h = t1 - t0
    s = s[:, None]
    return ((2 * s**3 - 3 * s**2 + 1) * p0 + (s**3 - 2 * s**2 + s) * h * v0
            + (-2 * s**3 + 3 * s**2) * p1 + (s**3 - s**2) * h * v1)


def _curve_stats(t0, t1, p0, v0, p1, v1, s, level):
    """共用 Hermite 細分；極小值黃金分割精修，第一次觸界二分精修。"""
    h = t1 - t0
    d = np.linalg.norm(_hermite(t0, t1, p0, v0, p1, v1, s), axis=1)
    a, b, c = 2*p0 - 2*p1 + h*(v0 + v1), -3*p0 + 3*p1 - h*(2*v0 + v1), h*v0

    def norm(x):
        return float(np.linalg.norm(((a*x + b)*x + c)*x + p0))

    candidates = [(float(x), float(y)) for x, y in zip(s, d)]
    minima = list(np.nonzero((d[1:-1] < d[:-2]) & (d[1:-1] <= d[2:]))[0] + 1)
    # 極小值緊靠端點時也要精修，避免整個觸界區間落在第一／最後一格之間。
    if d[0] < d[1] and p0 @ v0 < 0.0:
        minima.append(0)
    if d[-1] < d[-2] and p1 @ v1 > 0.0:
        minima.append(len(s) - 1)
    for k in minima:
        lo, hi = float(s[max(0, k-1)]), float(s[min(len(s)-1, k+1)])
        ratio = 0.6180339887498949
        left, right = hi - ratio*(hi-lo), lo + ratio*(hi-lo)
        fl, fr = norm(left), norm(right)
        for _ in range(36):
            if fl < fr:
                hi, right, fr = right, left, fl
                left = hi - ratio*(hi-lo)
                fl = norm(left)
            else:
                lo, left, fl = left, right, fr
                right = lo + ratio*(hi-lo)
                fr = norm(right)
        candidates.extend([(left, fl), (right, fr)])
    best_s, best = min(candidates, key=lambda pair: pair[1])
    inside = [x for x, value in candidates if value <= level]
    hit = None
    if inside:
        hi = min(inside)
        if hi == 0.0:
            hit = float(t0)
        else:
            lo = float(s[max(0, int(np.searchsorted(s, hi, side="left"))-1)])
            for _ in range(42):
                mid = (lo + hi)*0.5
                if norm(mid) <= level:
                    hi = mid
                else:
                    lo = mid
            hit = float(t0 + hi*h)
    return best, float(t0 + best_s*h), hit


def _position_at(rows, at):
    """端點捕獲模式用：以同一套 Hermite 取指定窗口末的位置。"""
    k = int(np.searchsorted(rows[:, 0], at, side="right")) - 1
    if k < 0 or at > rows[-1, 0] + 1e-6:
        raise ValueError("捕獲判定時刻超出密集報表範圍")
    if abs(rows[k, 0] - at) <= 1e-6:
        return rows[k, 1:4], rows[k, 7:10]
    a, b = rows[k], rows[k+1]
    s = np.array([(at-a[0]) / (b[0]-a[0])])
    return (_hermite(a[0], b[0], a[1:4], a[4:7], b[1:4], b[4:7], s)[0],
            _hermite(a[0], b[0], a[7:10], a[10:13], b[7:10], b[10:13], s)[0])


def analyze_dense(rows, capture_radius_km, sub=64, *, rules=None, capture_times_sec=None):
    """GMAT 密集軌跡的幾何量及事件順序；門檻與 game.core.Game.crash_radius 相同。

    三條曲線（相對位置及雙方地心位置）使用相同 Hermite 細分。t_enter_capture_sec 是
    幾何觸球；t_capture_sec 只有捕獲先發生才有值。最低半徑涵蓋完整輸出，即使捕獲後
    觸界仍會回報，但不判撞地。同時觸界時撞地優先（physics.coast.coast_pair）。
    endpoint 模式須另給真正的窗口末時刻；機動間的報表列不是窗口末。"""
    from game.rules import Rules
    from physics import RE_VAL

    rules = rules or Rules()
    rows = np.asarray(rows, dtype=float)
    if (rows.ndim != 2 or rows.shape[1] != 13 or not len(rows)
            or not np.all(np.isfinite(rows)) or np.any(np.diff(rows[:, 0]) < -1e-6)):
        raise ValueError("密集報表須為有限、按時間排序的非空 (n, 13) 陣列")
    if not isinstance(sub, int) or sub < 2:
        raise ValueError("Hermite 細分數須為至少 2 的整數")
    t = rows[:, 0]
    dr, dv = rows[:, 1:4] - rows[:, 7:10], rows[:, 4:7] - rows[:, 10:13]
    crash_radius = float(RE_VAL + rules.crash_altitude_km)
    curves = [(dr, dv, capture_radius_km), (rows[:, 1:4], rows[:, 4:7], crash_radius),
              (rows[:, 7:10], rows[:, 10:13], crash_radius)]
    stats = []
    for pos, _, level in curves:
        radii = np.linalg.norm(pos, axis=1)
        k = int(np.argmin(radii))
        hits = np.nonzero(radii <= level)[0]
        stats.append([float(radii[k]), float(t[k]), float(t[hits[0]]) if len(hits) else None])
    s = np.linspace(0.0, 1.0, sub+1)
    for i in range(len(t)-1):
        if t[i+1] - t[i] <= 1e-6:  # 脈衝前後同時刻：速度不連續，不內插
            continue
        for j, (pos, vel, level) in enumerate(curves):
            minimum, at, hit = _curve_stats(t[i], t[i+1], pos[i], vel[i], pos[i+1], vel[i+1], s, level)
            if minimum < stats[j][0]:
                stats[j][:2] = [minimum, at]
            if hit is not None and (stats[j][2] is None or hit < stats[j][2]):
                stats[j][2] = hit
    t_enter = stats[0][2]
    t_cap = t_enter
    if rules.capture_mode == "endpoint":
        if capture_times_sec is None:
            raise ValueError("endpoint 模式必須提供 capture_times_sec（真正的窗口末）")
        t_cap = None
        for at in sorted(set([float(t[0]), *map(float, capture_times_sec)])):
            rp, re = _position_at(rows, at)
            if np.linalg.norm(rp-re) <= capture_radius_km:
                t_cap = at
                break
    radii = {}
    crash_events = []
    for side, st in zip(("pursuer", "evader"), stats[1:]):
        minimum, at, hit = st
        radii[side] = {"min_radius_km": minimum, "t_min_sec": at, "t_crossing_sec": hit,
                       "crossed_crash_radius": hit is not None}
        if hit is not None:
            crash_events.append((hit, f"crash_{side}"))
    # 雙方同時撞地時追者優先，與 coast_pair 的列舉順序一致。
    crash = min(crash_events, key=lambda event: event[0]) if crash_events else None
    # 二分精修的數值時間精度；不放寬任何半徑門檻。
    crash_first = crash is not None and (t_cap is None or crash[0] <= t_cap + 1e-8)
    first_event = crash[1] if crash_first else ("capture" if t_cap is not None else None)
    event_time = crash[0] if crash_first else t_cap
    if crash and t_cap is not None:
        order = "crash_before_capture" if crash_first else "capture_before_crash"
    else:
        order = "crash_only" if crash else ("capture_only" if t_cap is not None else "none")
    return {"d_min_km": stats[0][0], "t_min_sec": stats[0][1],
            "t_enter_capture_sec": t_enter, "t_capture_candidate_sec": t_cap,
            "t_capture_sec": t_cap if first_event == "capture" else None,
            "n_rows": int(len(t)), "earth_radius_km": float(RE_VAL), "crash_radius_km": crash_radius,
            "radii": radii, "earth_safe": not crash_first, "crash_before_capture": bool(crash_first),
            "event_order": order, "first_event": first_event, "t_event_sec": event_time}


def earth_gate_lines(out):
    """CLI 與 Markdown 共用的判定文字，避免把撞地後觸球印成追者勝。"""
    lines = [f"GMAT 撞地門檻：地心半徑 ≤ {out['crash_radius_km']:.6f} km（引擎規則）"]
    for side, label in (("pursuer", "追者"), ("evader", "躲者")):
        r = out["radii"][side]
        lines.append(f"{label}最低地心半徑 {r['min_radius_km']:.6f} km @ t={r['t_min_sec']:.6f} s"
                     + (f"；首次觸及撞地門檻 t={r['t_crossing_sec']:.6f} s"
                        if r['crossed_crash_radius'] else "；全程未觸及撞地門檻"))
    if out["crash_before_capture"]:
        label = "追者" if out["first_event"] == "crash_pursuer" else "躲者"
        lines.append(f"【撞地閘門未通過】{label}先撞地 @ t={out['t_event_sec']:.6f} s；捕獲不成立")
    elif out["first_event"] == "capture":
        lines.append(f"撞地閘門通過：捕獲先發生 @ t={out['t_capture_sec']:.6f} s"
                     + ("；捕獲後觸及門檻不算撞地" if out["event_order"] == "capture_before_crash" else ""))
    else:
        lines.append("撞地閘門通過：輸出範圍內無撞地、無捕獲")
    return lines


def gmat_step(rules, state, rec, force_model="ranking_full", console=GMAT_CONSOLE, *,
              spacecraft=None, epoch_tai_mjd=DEFAULT_EPOCH_TAI_MJD, with_analysis=False):
    """GMAT 當真實世界推進一個回合：從 state（rec 開始時刻雙方的 (r, v)）施加 rec 的各發、滑行
    rec 的窗口，回傳回合結束時的新 state。曆元跟著 rec["t"] 走。比每回合從頭重播整局快很多。
    with_analysis=True 時回傳 (state, analyze_dense 結果)，事件時間為整場的絕對秒數。"""
    from types import SimpleNamespace
    t0 = float(rec["t"])
    shifted = dict(rec, t=0.0, burns=[dict(b, t=float(b["t"]) - t0) for b in _burns(rec)])
    snap = SimpleNamespace(rules=rules, initial=state, history=[shifted])
    script = game_to_script(snap, "__REPORT__", force_model, epoch_offset_sec=t0,
                            dense_path="__DENSE__" if with_analysis else None,
                            spacecraft=spacecraft, epoch_tai_mjd=epoch_tai_mjd)
    if with_analysis:
        rows, dense = run_gmat(script, console, dense=True)
        validate_dense_reports(rows, dense, expected_rows=2, duration_sec=float(rec["coast_sec"]))
        dense = dense.copy()
        dense[:, 0] += t0
        analysis = analyze_dense(dense, rules.capture_radius_km, rules=rules,
                                 capture_times_sec=[t0 + float(rec["coast_sec"])])
    else:
        rows = run_gmat(script, console)
    last = rows[-1]
    state = {"pursuer": (last[1:4].copy(), last[4:7].copy()), "evader": (last[7:10].copy(), last[10:13].copy())}
    return (state, analysis) if with_analysis else state


def gmat_truth(game, force_model="ranking_full", console=GMAT_CONSOLE, *,
               spacecraft=None, epoch_tai_mjd=DEFAULT_EPOCH_TAI_MJD):
    """GMAT 重播整局（密集報表），回傳真實最近距離與捕獲時刻（官方會用的判定）。

    引擎在捕獲的瞬間就結束比賽，最後一個窗口只滑到事件時刻；那樣 GMAT 只看得到「剛好碰到邊界」。
    所以捕獲時把最後一個窗口補滿（到窗口結束或 T_max），讓 GMAT 自己判斷有沒有進去。撞地時不補：
    太空船已經在大氣層裡，全攝動模型的阻力會讓積分器步長縮到幾乎停住（tests/test_flyby.py 實測：3000 s
    的局重播 147 s、密集報表 15 萬列），而且撞地之後的接近也不算數（攔截前穿越地球才失格）。"""
    from types import SimpleNamespace
    hist = list(game.history)
    if hist and game.outcome == "capture":
        last = hist[-1]
        full = min(game.rules.window_sec, game.t_max - last["t"])
        if full > last["coast_sec"]:
            hist[-1] = dict(last, coast_sec=full)
    snap = SimpleNamespace(rules=game.rules, initial=game.initial, history=hist)
    rows, dense = run_gmat(game_to_script(snap, "__REPORT__", force_model, dense_path="__DENSE__",
                                         spacecraft=spacecraft, epoch_tai_mjd=epoch_tai_mjd),
                           console, dense=True)
    duration = float(hist[-1]["t"] + hist[-1]["coast_sec"]) if hist else 0.0
    validate_dense_reports(rows, dense, expected_rows=len(hist)+1, duration_sec=duration)
    out = analyze_dense(dense, game.rules.capture_radius_km, rules=game.rules,
                        capture_times_sec=rows[:, 0])
    out["final_dist_km"] = float(np.linalg.norm(rows[-1, 1:4] - rows[-1, 7:10]))
    return out


def verify_game(game, console=GMAT_CONSOLE, force_model="zonal", *,
                spacecraft=None, epoch_tai_mjd=DEFAULT_EPOCH_TAI_MJD):
    """重播並比對。回傳 dict：逐回合雙方位置差 (km)、最大差、GMAT 端最終距離。"""
    script = game_to_script(game, "__REPORT__", force_model, dense_path="__DENSE__",
                            spacecraft=spacecraft, epoch_tai_mjd=epoch_tai_mjd)
    rows, dense = run_gmat(script, console, dense=True)
    n = len(game.history)
    if rows.shape[0] != n + 1:
        raise RuntimeError(f"GMAT 報表列數 {rows.shape[0]} ≠ 回合數+1 = {n + 1}")
    duration = float(game.history[-1]["t"] + game.history[-1]["coast_sec"]) if n else 0.0
    validate_dense_reports(rows, dense, expected_rows=n+1, duration_sec=duration)
    per_turn = []
    for k, rec in enumerate(game.history):
        row = rows[k + 1]
        dp = float(np.linalg.norm(row[1:4] - rec["rp_after"]))
        de = float(np.linalg.norm(row[7:10] - rec["re_after"]))
        dt = float(row[0] - (rec["t"] + rec["coast_sec"]))
        per_turn.append({"turn": k, "t_end": rec["t"] + rec["coast_sec"], "dpos_pursuer_km": dp,
                         "dpos_evader_km": de, "dt_sec": dt,
                         "dist_ours_km": rec["distance_after_km"],
                         "dist_gmat_km": float(np.linalg.norm(row[1:4] - row[7:10]))})
    return {
        **analyze_dense(dense, game.rules.capture_radius_km, rules=game.rules, capture_times_sec=rows[:, 0]),
        "turns": n,
        "max_dpos_km": max((max(p["dpos_pursuer_km"], p["dpos_evader_km"]) for p in per_turn), default=0.0),
        "max_dt_sec": max((abs(p["dt_sec"]) for p in per_turn), default=0.0),
        "final_dist_ours_km": game.distance(),
        "final_dist_gmat_km": per_turn[-1]["dist_gmat_km"] if per_turn else float(np.linalg.norm(rows[0, 1:4] - rows[0, 7:10])),
        "per_turn": per_turn,
    }


def main():
    from agents import make_agent
    from game.core import Game, take_round, take_turn
    from game.rules import RuleRanges, Rules
    from game.scenarios import sample_final_scenario, sample_scenario

    ap = argparse.ArgumentParser()
    ap.add_argument("--pursuer", default="lambert_pursuer")
    ap.add_argument("--evader", default="dv_evader")
    ap.add_argument("--rules", default="default", help="default / ranges / 規則 JSON 檔")
    ap.add_argument("--scenario", default="near_coplanar")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--gravity-degree", type=int, default=None)
    ap.add_argument("--force-model", default="zonal", choices=FORCE_MODELS)
    ap.add_argument("--gmat-console", default=GMAT_CONSOLE)
    ap.add_argument("--spacecraft-json", help="太空船參數覆寫 JSON（共用於雙方）")
    ap.add_argument("--epoch-tai-mjd", type=float, default=DEFAULT_EPOCH_TAI_MJD)
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    if args.rules == "ranges":
        R = RuleRanges().sample(rng)
    elif args.rules == "default":
        R = Rules()
    else:
        import json
        R = Rules.from_dict(json.load(open(args.rules)))
    if args.gravity_degree is not None:
        R = R.with_(gravity_degree=args.gravity_degree)
    if args.scenario == "final":
        R, sc = sample_final_scenario(rng, R)
    else:
        sc = sample_scenario(rng, args.scenario)
    g = Game.from_elements(R, sc.orbit_pursuer, sc.orbit_evader)
    P, E = make_agent(args.pursuer), make_agent(args.evader)
    while not g.done:
        if R.simultaneous:
            take_round(g, P, E)
        else:
            take_turn(g, P if g.mover == "pursuer" else E)
    print("game:", g.summary())
    import json
    params = json.load(open(args.spacecraft_json)) if args.spacecraft_json else None
    out = verify_game(g, console=args.gmat_console, force_model=args.force_model,
                      spacecraft=params, epoch_tai_mjd=args.epoch_tai_mjd)
    for p in out["per_turn"]:
        print(f"  turn {p['turn']:3d} t={p['t_end']:9.1f}s  ΔP={1000 * p['dpos_pursuer_km']:8.2f} m  "
              f"ΔE={1000 * p['dpos_evader_km']:8.2f} m  dist ours/GMAT = {p['dist_ours_km']:.4f} / {p['dist_gmat_km']:.4f} km")
    print(f"max position difference: {1000 * out['max_dpos_km']:.2f} m over {out['turns']} turns")
    for line in earth_gate_lines(out):
        print(line)


if __name__ == "__main__":
    main()
