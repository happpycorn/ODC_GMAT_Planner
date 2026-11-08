"""GUI 公告念回與 USB 比對所需的二體小工具；只用 Python 標準函式庫。"""
import math
import re
from datetime import datetime, timedelta, timezone

MU = 398600.4418
R_EARTH = 6378.137
SIDES = (("pursuer", "追方"), ("evader", "逃方"))


def epoch_utc(value):
    text = str(value if value is not None else "").strip()
    if not text:
        return None
    if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", text):
        return datetime(1941, 1, 5, 12, tzinfo=timezone.utc) + timedelta(days=float(text))
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        # 不依賴電腦的語系設定辨認 GMAT 英文月份。
        match = re.fullmatch(r"(\d{1,2}) ([A-Za-z]{3}) (\d{4}) (\d\d:\d\d:\d\d(?:\.\d+)?)", text)
        if not match:
            raise ValueError("時間看不懂")
        day, month, year, clock = match.groups()
        months = "jan feb mar apr may jun jul aug sep oct nov dec".split()
        parsed = datetime.fromisoformat(f"{year}-{months.index(month.lower()) + 1:02d}-{int(day):02d}T{clock}")
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def utc_text(value):
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z") if value else None


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def norm(a):
    return math.sqrt(dot(a, a))


def orbit_summary(r, v):
    rn, vn = norm(r), norm(v)
    if rn == 0:
        return {"r_km": r, "v_kms": v, "radius_km": 0, "speed_kms": vn,
                "altitude_km": -R_EARTH, "perigee_alt_km": -R_EARTH,
                "sma_km": None, "period_min": None}
    rv, energy = dot(r, v), vn * vn / 2 - MU / rn
    eccentricity = norm([((vn * vn - MU / rn) * x - rv * y) / MU for x, y in zip(r, v)])
    cross = [r[1] * v[2] - r[2] * v[1], r[2] * v[0] - r[0] * v[2], r[0] * v[1] - r[1] * v[0]]
    perigee = dot(cross, cross) / (MU * (1 + eccentricity))
    a = -MU / (2 * energy) if abs(energy) > 1e-14 else None
    period = 2 * math.pi * math.sqrt(a ** 3 / MU) / 60 if a and a > 0 else None
    values = {"r_km": r, "v_kms": v, "radius_km": rn, "speed_kms": vn,
              "altitude_km": rn - R_EARTH, "perigee_alt_km": perigee - R_EARTH,
              "sma_km": a, "period_min": period}
    return {key: (None if isinstance(val, float) and not math.isfinite(val) else val)
            for key, val in values.items()}


def propagate(r, v, seconds):
    """通用變數 f/g 二體傳播；USB 比對時把兩份資料推到同一時刻。"""
    if abs(seconds) < 1e-10:
        return list(r), list(v)
    radius, root_mu = norm(r), math.sqrt(MU)
    if radius == 0:
        raise ValueError("位置在地心，不能推算；請核對位置六格與單位")
    alpha, rv = 2 / radius - dot(v, v) / MU, dot(r, v) / root_mu
    # 以短段求根，避免多圈或雙曲線初猜造成溢位。
    if abs(seconds) > 300:
        count = math.ceil(abs(seconds) / 300)
        for _ in range(count):
            r, v = propagate(r, v, seconds / count)
        return r, v

    def stumpff(z):
        if abs(z) < 1e-5:
            return (0.5 - z / 24 + z * z / 720 - z ** 3 / 40320,
                    1 / 6 - z / 120 + z * z / 5040 - z ** 3 / 362880)
        if z > 0:
            x = math.sqrt(z)
            return (1 - math.cos(x)) / z, (x - math.sin(x)) / x ** 3
        x = math.sqrt(-z)
        return (math.cosh(x) - 1) / (-z), (math.sinh(x) - x) / x ** 3

    chi = root_mu * seconds / radius
    for _ in range(80):
        z = alpha * chi * chi
        c, s = stumpff(z)
        f = rv * chi ** 2 * c + (1 - alpha * radius) * chi ** 3 * s + radius * chi - root_mu * seconds
        derivative = rv * chi * (1 - z * s) + (1 - alpha * radius) * chi ** 2 * c + radius
        step = f / derivative
        chi -= step
        if abs(step) < 1e-11:
            break
    else:
        raise ValueError("時間對齊算不出來；請核對兩份檔案的時間、位置與速度")
    c, s = stumpff(alpha * chi * chi)
    f, g = 1 - chi ** 2 * c / radius, seconds - chi ** 3 * s / root_mu
    out_r = [f * x + g * y for x, y in zip(r, v)]
    out_radius = norm(out_r)
    fdot = root_mu / (out_radius * radius) * (alpha * chi ** 3 * s - chi)
    gdot = 1 - chi ** 2 * c / out_radius
    return out_r, [fdot * x + gdot * y for x, y in zip(r, v)]
