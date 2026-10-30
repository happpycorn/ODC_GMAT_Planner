# 此模組負責軌跡最低半徑與交件安全閘門。
# 主要入口為 analyze_radius_report，計算本體沿用原實作。
"""Independent GMAT radius gate; instrumentation belongs only in executed.script."""
import math
import re
from pathlib import Path

import numpy as np

from odc.gmat.retarget import _hermite

MIN_PERIAPSIS = 6378.137 + 100.0
RADIUS_TOL_KM = 1e-3
def _columns(script):
    # 2026-10-30 起 B 叫 SC_Human（對齊官方題目腳本）；之前產的腳本叫 ShipB，照樣要能驗。
    ship = "ShipB" if re.search(r"(?m)^\s*Create Spacecraft ShipB\s*;", script) else "SC_Human"
    return [f"{ship}.ElapsedSecs"] + [
        f"{ship}.EarthMJ2000Eq.{c}" for c in ("X", "Y", "Z", "VX", "VY", "VZ")]


def instrument_radius_report(script, report_path):
    """Add a subscriber and burn boundary samples without changing mission values."""
    cols = _columns(script)
    columns = " ".join(cols)
    report = f"Report EarthGate {columns};"
    declarations = ("Create ReportFile EarthGate;\n"
                    f"EarthGate.Filename = '{Path(report_path).as_posix()}';\n"
                    "EarthGate.SolverIterations = None;\n"
                    "EarthGate.WriteHeaders = false;\n"
                    "EarthGate.Precision = 16;\n"
                    "EarthGate.ZeroFill = Off;\n"
                    f"EarthGate.Add = {{{', '.join(cols)}}};\n")
    # Keep solver diagnostics beside the executed copy as well (GMAT's default
    # points into its installation directory, which may be read-only).
    for solver in re.findall(r"(?m)^\s*Create DifferentialCorrector\s+(\w+)\s*;", script):
        destination = Path(report_path).parent / f"{solver}.data"
        declarations += f"{solver}.ReportFile = '{destination.as_posix()}';\n"
    # Report every integrator step with <=60 s spacing, matching retarget replay.
    script = re.sub(r"(?m)^([ \t]*\w+\.MaxStep\s*=\s*)([\d.eE+-]+)(\s*;)",
                    lambda m: m[1] + str(min(float(m[2]), 60.0)) + m[3], script)
    script, count = re.subn(r"(?m)^[ \t]*BeginMissionSequence\s*;",
                            lambda m: declarations + m[0] + "\n" + report, script)
    if count != 1:
        raise ValueError("腳本需包含唯一的 BeginMissionSequence。")
    # Same-time pre/post-burn rows prevent interpolation across a velocity jump.
    script = re.sub(r"(?m)^([ \t]*Maneuver[^\n]*;)[ \t]*$",
                    lambda m: report + "\n" + m[1] + "\n" + report, script)
    return script + "\n" + report + "\n"


def analyze_radius_report(path, intercept_sec):
    """64 subdivisions per GMAT interval, also sampling the exact cutoff endpoint."""
    rows = []
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        values = [float(v) for v in line.split()]
        if len(values) != 7 or not all(math.isfinite(v) for v in values):
            raise ValueError("半徑報表格式不完整或包含非有限值")
        rows.append(values)
    rows = np.asarray(rows, dtype=float)
    if rows.ndim != 2 or len(rows) < 2 or not math.isfinite(intercept_sec) or intercept_sec < 0:
        raise ValueError("半徑報表不足以檢查完整軌跡")
    t = rows[:, 0]
    if abs(t[0]) > 1e-3 or t[-1] < intercept_sec - 1e-3 or np.any(np.diff(t) < -1e-6):
        raise ValueError("半徑報表未涵蓋 t=0 至攔截時刻，或時序不正確")
    mask = (t >= 0) & (t <= intercept_sec)
    radii = np.linalg.norm(rows[mask, 1:4], axis=1)
    k = int(np.argmin(radii))
    minimum, at_sec = float(radii[k]), float(t[mask][k])
    for a, b in zip(rows[:-1], rows[1:]):
        gap = b[0] - a[0]
        if gap <= 1e-6 or a[0] >= intercept_sec:
            continue
        end = min(b[0], intercept_sec)
        # At least as dense as retarget, even for scripts with sparse reports.
        sub = max(64, int(math.ceil(gap / (60.0 / 64))))
        s = np.linspace(0.0, (end-a[0])/gap, sub+1)
        rb = _hermite(a[0], b[0], a[1:4], a[4:7], b[1:4], b[4:7], s)
        radii = np.linalg.norm(rb, axis=1)
        k = int(np.argmin(radii))
        if radii[k] < minimum:
            minimum, at_sec = float(radii[k]), float(a[0] + s[k]*gap)
    return {"earth_safe": minimum >= MIN_PERIAPSIS - RADIUS_TOL_KM,
            "min_radius_before_intercept_km": minimum,
            "min_radius_time_sec": at_sec,
            "min_periapsis_km": MIN_PERIAPSIS,
            "radius_acceptance_km": MIN_PERIAPSIS - RADIUS_TOL_KM,
            "radius_report_path": str(path)}
