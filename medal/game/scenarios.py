"""初始幾何產生器：回傳雙方六根數（SMA km, ECC, INC/RAAN/AOP/TA 度）。

官方決賽初始軌道未知，所以準備幾個家族並可混合抽樣：
  * default          —— 舊 final_env 的佔位軌道（固定，回歸測試用）
  * official_sample  —— 初賽官方範例題目（外星人 = 躲者、地球人 = 追者；兩軌道面夾 94°）
  * near_coplanar    —— 近圓、近共面、相位差 0.5–15°、高度差 ±150 km（典型交會問題）
  * inclined         —— 平面差到 ~20°、相位差到 ±40°
  * wild             —— 雙方獨立亂數 LEO（含逆行），類似官方範例那種刁鑽幾何
  * flyby            —— 排位賽型：躲者雙曲線飛掠（近地點高度 300–2000 km、v∞ 1–4 km/s）、追者近圓 LEO。
                        先選交會再倒推：躲者軌道上近地點附近、高度 ≤ 2000 km 的一點，開賽後 900–5400 s 經過；
                        追者圓軌道過這點附近（軌道面繞交會點徑向轉 ±60°、到達時間差 ±60 s、高度差 ±30 km、
                        軌道面側傾 ±0.3°）→ 二體倒推回 t=0。純滑行最近距離幾十～幾百 km，追者一發幾十～
                        兩百 m/s 就攔得到不動的躲者（有得打）。躲者開賽時在 FLYBY_BOUNDARY_KM 的 95% 以內，
                        配 `Rules(t_max_boundary_km=FLYBY_BOUNDARY_KM)` 時 T_max 約 2–3.5 小時。
  * flyby_pursuer    —— 同 flyby、角色對調（追者雙曲線、躲者 LEO）。
  * final            —— 金／銅牌賽正式賽制（2026/10/29 規則）：雙方 LEO、初始距離 20–1000 km，另外要出安全空域
                        （逃方半長軸區間），所以不走 sample_scenario，用 sample_final_scenario(rng, rules) 同時回傳
                        填好 safe_sma_km 的 Rules。
（mixed 只抽前三種 LEO 家族，flyby、final 家族要明指。）
"""
import math
import json
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from game.rules import Rules
from physics import EARTH_MU, RE_VAL, get_r0_v0

MIN_PERIGEE_ALT_KM = 250.0

DEFAULT_ORBIT_PURSUER = {"sma": 7000.0, "ecc": 0.0, "inc": 0.0, "raan": 0.0, "aop": 0.0, "ta": 0.0}
DEFAULT_ORBIT_EVADER = {"sma": 7100.0, "ecc": 0.01, "inc": 0.5, "raan": 0.0, "aop": 0.0, "ta": 8.0}

# 官方 2026-08-28 參賽選手注意事項第八節範例題目（原文六根數）
OFFICIAL_SAMPLE_ALIEN = {"sma": 6978.0, "ecc": 0.0, "inc": 45.0, "raan": 0.0, "aop": 0.0, "ta": 0.0}
OFFICIAL_SAMPLE_HUMAN = {"sma": 6878.0, "ecc": 0.0, "inc": 135.0, "raan": 30.0, "aop": 0.0, "ta": 60.0}


@dataclass(frozen=True)
class Scenario:
    orbit_pursuer: dict
    orbit_evader: dict
    family: str
    meta: dict = None


def _perigee_ok(o):
    return o["sma"] * (1.0 - o["ecc"]) - RE_VAL >= MIN_PERIGEE_ALT_KM


def _leo(rng, alt=(300.0, 1500.0), ecc_max=0.02, inc=None):
    sma = RE_VAL + rng.uniform(*alt)
    return {
        "sma": float(sma),
        "ecc": float(rng.uniform(0.0, ecc_max)),
        "inc": float(rng.uniform(0.0, 180.0) if inc is None else inc),
        "raan": float(rng.uniform(0.0, 360.0)),
        "aop": float(rng.uniform(0.0, 360.0)),
        "ta": float(rng.uniform(0.0, 360.0)),
    }


def _near(rng, base, d_alt, d_plane_deg, d_phase_deg, ecc_max):
    o = dict(base)
    o["sma"] = float(base["sma"] + rng.uniform(-d_alt, d_alt))
    o["ecc"] = float(rng.uniform(0.0, ecc_max))
    o["inc"] = float(np.clip(base["inc"] + rng.uniform(-d_plane_deg, d_plane_deg), 0.0, 180.0))
    o["raan"] = float((base["raan"] + rng.uniform(-d_plane_deg, d_plane_deg)) % 360.0)
    sign = 1.0 if rng.random() < 0.5 else -1.0
    o["ta"] = float((base["ta"] + sign * rng.uniform(*d_phase_deg)) % 360.0)
    return o


# ------------------------------------------------------------------ 雙曲線飛掠（排位賽型）
FLYBY_BOUNDARY_KM = 40000.0          # flyby 家族假設的任務邊界（地心距離）；configs/rulesets/flyby_*.json 用同一個值
FLYBY_PERIGEE_ALT_KM = (300.0, 2000.0)
FLYBY_VINF_KMS = (1.0, 4.0)
FLYBY_LEO_MAX_ALT_KM = 2000.0        # 交會點（= LEO 方軌道高度）上限
FLYBY_T_ENC_SEC = (900.0, 5400.0)    # 開賽到設計交會的時間
FLYBY_CROSS_DEG = 60.0               # LEO 方軌道面繞交會點徑向相對飛掠方軌道面轉的角度上限
FLYBY_MISS = {"dt_sec": 60.0, "dh_km": 30.0, "tilt_deg": 0.3}   # 讓純滑行差一點撞上的偏差上限


def _hyp_time_from_ta(e, a, nu, mu=EARTH_MU):
    """雙曲線（a < 0）真近點角 nu（弧度）→ 距近地點的時間（秒，近地點前為負）。"""
    F = 2.0 * math.atanh(math.sqrt((e - 1.0) / (e + 1.0)) * math.tan(nu / 2.0))
    return (e * math.sinh(F) - F) / math.sqrt(mu / (-a) ** 3)


def _hyp_ta_from_time(e, a, t, mu=EARTH_MU):
    """雙曲線距近地點 t 秒時的真近點角（弧度）：解 e·sinh F − F = M（Newton）。"""
    M = t * math.sqrt(mu / (-a) ** 3)
    F = math.asinh(M / e)
    for _ in range(100):
        dF = (e * math.sinh(F) - F - M) / (e * math.cosh(F) - 1.0)
        F -= dF
        if abs(dF) < 1e-14:
            break
    return 2.0 * math.atan(math.sqrt((e + 1.0) / (e - 1.0)) * math.tanh(F / 2.0))


def _rotate(axis, ang, x):
    """x 繞單位向量 axis 轉 ang 弧度（Rodrigues）。"""
    k = axis / np.linalg.norm(axis)
    return x * math.cos(ang) + np.cross(k, x) * math.sin(ang) + k * float(k @ x) * (1.0 - math.cos(ang))


def _pqw(inc, raan, aop):
    """六根數角度（度）→ 近焦點座標軸 P、Q、W（ECI），同 physics.get_r0_v0 的 Rz(raan)·Rx(inc)·Rz(aop)。"""
    i, O, w = (math.radians(x) for x in (inc, raan, aop))
    cO, sO, ci, si, cw, sw = math.cos(O), math.sin(O), math.cos(i), math.sin(i), math.cos(w), math.sin(w)
    P = np.array([cO * cw - sO * sw * ci, sO * cw + cO * sw * ci, sw * si])
    Q = np.array([-cO * sw - sO * cw * ci, -sO * sw + cO * cw * ci, cw * si])
    W = np.array([sO * si, -cO * si, ci])
    return P, Q, W


def _circular_through(u_hat, w_hat, radius, t_arrive, mu=EARTH_MU):
    """軌道面法向 w_hat、半徑 radius 的圓軌道，t_arrive 秒後經過方向 u_hat（須在軌道面內）→ 六根數。"""
    w = w_hat / np.linalg.norm(w_hat)
    node = np.cross([0.0, 0.0, 1.0], w)
    if np.linalg.norm(node) < 1e-9:
        node, raan = np.array([1.0, 0.0, 0.0]), 0.0
    else:
        node = node / np.linalg.norm(node)
        raan = math.degrees(math.atan2(node[1], node[0])) % 360.0
    u_tgt = math.atan2(float(u_hat @ np.cross(w, node)), float(u_hat @ node))
    u0 = u_tgt - t_arrive * math.sqrt(mu / radius ** 3)
    return {"sma": float(radius), "ecc": 0.0, "inc": math.degrees(math.acos(float(np.clip(w[2], -1.0, 1.0)))),
            "raan": raan, "aop": 0.0, "ta": math.degrees(u0) % 360.0}


def _flyby_pair(rng, boundary_km=FLYBY_BOUNDARY_KM):
    """(LEO 方六根數, 雙曲線方六根數)：先選交會點與時刻、再二體倒推回 t=0（見模組說明）。"""
    mu = EARTH_MU
    for _ in range(1000):
        rpe = RE_VAL + rng.uniform(*FLYBY_PERIGEE_ALT_KM)
        vinf = rng.uniform(*FLYBY_VINF_KMS)
        a = -mu / vinf ** 2
        e = 1.0 + rpe * vinf ** 2 / mu
        p = a * (1.0 - e * e)
        r_max = RE_VAL + FLYBY_LEO_MAX_ALT_KM
        nu_lim = math.acos(min(1.0, max(-1.0, (p / r_max - 1.0) / e))) if r_max > rpe else 0.0
        nu_enc = rng.uniform(-nu_lim, nu_lim)            # 交會點：近地點前後、高度 ≤ LEO 上限
        t_enc = rng.uniform(*FLYBY_T_ENC_SEC)
        nu0 = _hyp_ta_from_time(e, a, _hyp_time_from_ta(e, a, nu_enc) - t_enc)
        if p / (1.0 + e * math.cos(nu0)) > 0.95 * boundary_km:
            continue                                     # 開賽時要在任務邊界內
        hyp = {"sma": float(a), "ecc": float(e), "inc": math.degrees(math.acos(rng.uniform(-1.0, 1.0))),
               "raan": float(rng.uniform(0.0, 360.0)), "aop": float(rng.uniform(0.0, 360.0)),
               "ta": math.degrees(nu0) % 360.0}
        P, Q, W = _pqw(hyp["inc"], hyp["raan"], hyp["aop"])
        u_enc = math.cos(nu_enc) * P + math.sin(nu_enc) * Q
        r_enc = p / (1.0 + e * math.cos(nu_enc))
        # LEO 方：軌道面繞交會點徑向轉 ψ，再繞自己的沿軌道方向側傾一點（交會點落在軌道面外 → 側向偏差）
        w_leo = _rotate(u_enc, math.radians(rng.uniform(-FLYBY_CROSS_DEG, FLYBY_CROSS_DEG)), W)
        w_leo = _rotate(np.cross(w_leo, u_enc),
                        math.radians(rng.uniform(-FLYBY_MISS["tilt_deg"], FLYBY_MISS["tilt_deg"])), w_leo)
        aim = u_enc - float(u_enc @ w_leo) * w_leo        # 軌道面內最接近交會點的方向
        radius = r_enc + rng.uniform(-FLYBY_MISS["dh_km"], FLYBY_MISS["dh_km"])
        if radius - RE_VAL < MIN_PERIGEE_ALT_KM:
            continue
        leo = _circular_through(aim / np.linalg.norm(aim), w_leo, radius,
                                t_enc + rng.uniform(-FLYBY_MISS["dt_sec"], FLYBY_MISS["dt_sec"]))
        return leo, hyp
    raise RuntimeError("flyby 場景抽樣 1000 次都不合法，檢查參數")


def sample_scenario(rng: np.random.Generator, family: str = "mixed") -> Scenario:
    if family == "mixed":
        family = str(rng.choice(["near_coplanar", "inclined", "wild"], p=[0.5, 0.3, 0.2]))
    if family in ("flyby", "flyby_pursuer"):
        leo, hyp = _flyby_pair(rng)
        return Scenario(leo, hyp, family) if family == "flyby" else Scenario(hyp, leo, family)
    for _ in range(100):
        if family == "default":
            return Scenario(dict(DEFAULT_ORBIT_PURSUER), dict(DEFAULT_ORBIT_EVADER), family)
        if family == "official_sample":
            return Scenario(dict(OFFICIAL_SAMPLE_HUMAN), dict(OFFICIAL_SAMPLE_ALIEN), family)
        if family == "near_coplanar":
            p = _leo(rng, ecc_max=0.01, inc=rng.uniform(0.0, 100.0))
            e = _near(rng, p, 150.0, 2.0, (0.5, 15.0), 0.02)
        elif family == "inclined":
            p = _leo(rng, ecc_max=0.01, inc=rng.uniform(0.0, 100.0))
            e = _near(rng, p, 300.0, 20.0, (0.5, 40.0), 0.03)
        elif family == "wild":
            p = _leo(rng, ecc_max=0.02)
            e = _leo(rng, ecc_max=0.05)
        else:
            raise ValueError(f"未知場景家族：{family!r}")
        if _perigee_ok(p) and _perigee_ok(e):
            return Scenario(p, e, family)
    raise RuntimeError("場景抽樣 100 次都不合法，檢查家族參數")


# ------------------------------------------------------------------ 金／銅牌賽正式賽制
FINAL_RULE_RANGES = {
    "dv_lim_mps": (100.0, 500.0),
    "capture_radius_km": (1.0, 20.0),
    "window_sec": (600.0, 3600.0),
}
FINAL_RULES_BASE = Rules.from_dict({
    "turn_mode": "simultaneous",
    "rounds": 6,
    "window_sec": 1200.0,
    "burns_per_turn": 1,
    "max_dv_pursuer_mps": 250.0,
    "max_dv_evader_mps": 250.0,
    "fuel_pursuer_mps": None,
    "fuel_evader_mps": None,
    "capture_radius_km": 5.0,
    "capture_mode": "continuous",
    "safe_sma_km": None,
    "t_max_sec": 0.0,
    "gravity_degree": 0,
    "crash_altitude_km": 0.0,
})


def sample_final_rules(rng: np.random.Generator, base: Rules = FINAL_RULES_BASE) -> Rules:
    """抽金／銅牌賽的三個待公告參數；雙方使用相同的 ΔV_lim。"""
    def draw(name):
        lo, hi = FINAL_RULE_RANGES[name]
        return float(math.exp(rng.uniform(math.log(lo), math.log(hi))))

    dv_lim = draw("dv_lim_mps")
    return Rules.from_dict(base).with_(
        max_dv_pursuer_mps=dv_lim,
        max_dv_evader_mps=dv_lim,
        capture_radius_km=draw("capture_radius_km"),
        window_sec=draw("window_sec"),
    )


FINAL_ALT_KM = (400.0, 1500.0)       # 雙方軌道高度（sma − RE）
FINAL_ECC_MAX = 0.01
FINAL_MIN_PERIGEE_ALT_KM = 300.0
FINAL_DIST_KM = (20.0, 1000.0)       # 初始距離
FINAL_P_IN_ZONE = 0.2                # 初始 a 就在安全空域內的題目比例
FINAL_ZONE_ROUNDS = (1.0, 4.0)       # 其餘題目：區間中心距初始 a 要幾回合「順／逆向全推 ΔV_lim」
FINAL_ZONE_WIDTH_ROUNDS = (0.3, 1.0)  # 區間寬度（回合的 Δa）
FINAL_ZONE_MIN_ALT_KM = 300.0        # 區間下界至少 RE + 這個值（逆向推太多會撞地，改出順向的題）


def full_burn_dsma_km(sma_km, dv_mps, mu=EARTH_MU):
    """近圓軌道順向（或逆向）推 dv 一發的半長軸變化 Δa ≈ 2·a^{3/2}·Δv/√μ（km）。"""
    return 2.0 * sma_km ** 1.5 * (dv_mps / 1000.0) / math.sqrt(mu)


def _final_pair(rng):
    """(追方, 逃方) 六根數：同軌道面相位差，或小平面差（≤ 1°）加相位差；初始距離在 FINAL_DIST_KM。"""
    for _ in range(1000):
        e = _leo(rng, alt=FINAL_ALT_KM, ecc_max=FINAL_ECC_MAX, inc=rng.uniform(0.0, 100.0))
        p = dict(e)
        p["sma"] = float(e["sma"] + rng.uniform(-50.0, 50.0))
        p["ecc"] = float(rng.uniform(0.0, FINAL_ECC_MAX))
        if rng.random() < 0.5:                                   # 小平面差
            p["inc"] = float(np.clip(e["inc"] + rng.uniform(-1.0, 1.0), 0.0, 180.0))
            p["raan"] = float((e["raan"] + rng.uniform(-1.0, 1.0)) % 360.0)
        sign = 1.0 if rng.random() < 0.5 else -1.0
        p["ta"] = float((e["ta"] + sign * rng.uniform(0.1, 8.0)) % 360.0)
        ok = all(FINAL_ALT_KM[0] <= o["sma"] - RE_VAL <= FINAL_ALT_KM[1]
                 and o["sma"] * (1.0 - o["ecc"]) - RE_VAL >= FINAL_MIN_PERIGEE_ALT_KM for o in (p, e))
        if not ok:
            continue
        d = float(np.linalg.norm(get_r0_v0(**p)[0] - get_r0_v0(**e)[0]))
        if FINAL_DIST_KM[0] <= d <= FINAL_DIST_KM[1]:
            return p, e
    raise RuntimeError("final 場景抽樣 1000 次都不合法，檢查參數")


def sample_final_scenario(rng: np.random.Generator, rules):
    """金／銅牌賽題目：回傳 (填好 safe_sma_km 的 Rules, Scenario(family="final"))。

    安全空域以逃方初始 a（sma_official）為基準、用逃方的 ΔV_lim 估一回合全推的 Δa：FINAL_P_IN_ZONE 的題目
    初始 a 就在區間內；其餘題目區間中心偏 1–4 回合、寬 0.3–1 回合的 Δa（下界太低會撞地時改成順向）。"""
    from game.core import sma_official
    from game.rules import Rules
    R = Rules.from_dict(rules)
    op, oe = _final_pair(rng)
    a0 = sma_official(*get_r0_v0(**oe))
    da = full_burn_dsma_km(a0, R.max_dv_evader_mps)
    width = float(rng.uniform(*FINAL_ZONE_WIDTH_ROUNDS)) * da
    if rng.random() < FINAL_P_IN_ZONE:
        center = a0 + float(rng.uniform(-0.4, 0.4)) * width
    else:
        offset = float(rng.uniform(*FINAL_ZONE_ROUNDS)) * da
        center = a0 + offset if rng.random() < 0.5 else a0 - offset
        if center - width / 2.0 < RE_VAL + FINAL_ZONE_MIN_ALT_KM:
            center = a0 + offset
    zone = (center - width / 2.0, center + width / 2.0)
    return R.with_(safe_sma_km=zone), Scenario(op, oe, "final")


FAMILIES = ("default", "official_sample", "near_coplanar", "inclined", "wild", "mixed", "flyby", "flyby_pursuer")


# ------------------------------------------------------------------ 金／銅牌賽對抗題
ADVERSARIAL_KINDS = ("cover", "narrow", "cross", "far", "close", "taiwan")
TAIWAN_BANK_PATH = Path(__file__).resolve().parents[1] / "configs/scenarios/taiwan_launch_bank.json"
ADV_DIST_KM = (20.0, 1500.0)
ADV_MAX_TRIES = 2000


@lru_cache(maxsize=4)
def _taiwan_pairs(path):
    """第一次抽台灣題才讀題庫；以路徑作快取鍵，測試也能替換題庫。"""
    with open(path, encoding="utf-8") as stream:
        pairs = json.load(stream).get("pairs")
    if not isinstance(pairs, list) or not pairs:
        raise ValueError(f"台灣入軌題庫沒有 pairs：{path}")
    return pairs


def _adv_plane(rng, evader, pursuer, near_distance=None):
    """各半機率同平面／小平面差；近距離題縮小傾角以保留可抽到的相位。"""
    if rng.random() < 0.5:
        return
    span = 0.5 if near_distance is None else min(0.5, math.degrees(0.1 * near_distance / evader["sma"]))
    pursuer["inc"] = float(np.clip(evader["inc"] + rng.uniform(-span, span), 0.0, 180.0))
    pursuer["raan"] = float((evader["raan"] + rng.uniform(-span, span)) % 360.0)


def _adv_orbit_pair(rng, rules, kind, sub):
    """依半長軸相對位置抽雙方 LEO，接著以相位控制開局距離。"""
    evader = _leo(rng, alt=FINAL_ALT_KM, ecc_max=FINAL_ECC_MAX, inc=rng.uniform(0.0, 100.0))
    a_e = evader["sma"]
    da = full_burn_dsma_km(a_e, rules.max_dv_evader_mps)
    if kind == "cover":
        delta = (1.0 if rng.random() < 0.5 else -1.0) * rng.uniform(1.0, 2.5) * da
    elif kind == "cross":
        delta = (1.0 if rng.random() < 0.5 else -1.0) * rng.uniform(0.5, 1.5) * da
    elif kind == "far":
        delta = (1.0 if rng.random() < 0.5 else -1.0) * rng.uniform(0.5, 2.0) * da
    elif kind == "narrow":
        delta = (1.0 if rng.random() < 0.5 else -1.0) * rng.uniform(0.0, 0.5) * da
    else:
        delta = (1.0 if rng.random() < 0.5 else -1.0) * rng.uniform(2.0, 15.0)
    pursuer = dict(evader)
    pursuer["sma"] = float(a_e + delta)
    if kind == "close":
        # 同偏心率讓徑向差以 Δa 為主，較能精確抽出 20–100 km 的開局距離。
        min_dist = max(ADV_DIST_KM[0], 2.0 * rules.capture_radius_km) if sub == "close_frac" else ADV_DIST_KM[0]
        max_dist = (0.2 * rules.max_dv_evader_mps / 1000.0 * rules.window_sec
                    if sub == "close_frac" else 100.0)
        if max_dist <= min_dist + 5.0:
            return None, None, "close_frac 距離上限低於 20 km 或 2·R_cap"
        target_dist = float(rng.uniform(min_dist + 2.0, max_dist - 2.0))
        _adv_plane(rng, evader, pursuer, target_dist)
    else:
        pursuer["ecc"] = float(rng.uniform(0.0, FINAL_ECC_MAX))
        _adv_plane(rng, evader, pursuer)
        min_target = max(ADV_DIST_KM[0] + 10.0, abs(delta) + 20.0)
        if min_target >= ADV_DIST_KM[1] - 10.0:
            return None, None, "半長軸差已超過初始距離上限"
        target_dist = float(rng.uniform(min_target, ADV_DIST_KM[1] - 10.0))
    # 圓軌道的餘弦定理給相位初值；橢圓軌道與平面微擾由下方拒絕抽樣篩掉。
    cosine = (pursuer["sma"] ** 2 + a_e ** 2 - target_dist ** 2) / (2.0 * pursuer["sma"] * a_e)
    if not -1.0 <= cosine <= 1.0:
        return None, None, "目標距離與兩軌道半長軸不相容"
    phase = math.degrees(math.acos(cosine))
    pursuer["ta"] = float((evader["ta"] + (phase if rng.random() < 0.5 else -phase)) % 360.0)
    return pursuer, evader, None


def _adv_zone(rng, kind, sub, a_p, a_e, da, min_lo):
    """回傳區間；負向 far 若碰到安全高度下界，要求重抽朝正向的追方。"""
    zone_mode = sub if kind == "taiwan" else "cover" if kind == "close" else kind
    if zone_mode == "narrow":
        width = (0.02 if sub == "w002" else rng.uniform(0.05, 0.1)) * da
        offset = rng.uniform(1.0, 4.0) * da
        center = a_e + (offset if rng.random() < 0.5 else -offset)
    else:
        width = rng.uniform(0.3, 1.0) * da
        sign = 1.0 if a_p >= a_e else -1.0
        if zone_mode == "cover":
            center = a_p + (sign * 0.4 * width if kind == "close" else rng.uniform(-0.4, 0.4) * width)
        elif zone_mode == "cross":
            center = a_p + sign * rng.uniform(0.5, 2.0) * da
        elif zone_mode == "far":
            center = a_e + sign * rng.uniform(4.5, 5.5) * da
            if sign < 0.0 and center - width / 2.0 < min_lo:
                return None, "far 負向安全空域低於 300 km，須重抽正向追方"
        else:
            raise ValueError(f"未知的安全空域模式：{zone_mode!r}")
    lo, hi = float(center - width / 2.0), float(center + width / 2.0)
    if lo < min_lo:
        return None, "安全空域下界低於 300 km"
    return (lo, hi), None


def sample_adversarial_scenario(rng: np.random.Generator, rules, kind: str) -> tuple[Rules, Scenario]:
    """金／銅牌賽安全空域對抗題；最多拒絕抽樣 2000 次，逐題回報幾何中繼資料。"""
    if kind not in ADVERSARIAL_KINDS:
        raise ValueError(f"未知對抗題種類：{kind!r}（可用：{ADVERSARIAL_KINDS}）")
    from game.core import sma_official
    from physics.frames import rv2coe

    rule = Rules.from_dict(rules)
    min_lo = RE_VAL + FINAL_ZONE_MIN_ALT_KM
    if kind == "narrow":
        sub = "w05_10" if rng.random() < 0.5 else "w002"
    elif kind == "close":
        # 極短 T_round 時 close_frac 的上限會小於共同的 20 km 下限。
        frac_limit = 0.2 * rule.max_dv_evader_mps / 1000.0 * rule.window_sec
        frac_floor = max(ADV_DIST_KM[0], 2.0 * rule.capture_radius_km)
        sub = "close_frac" if frac_limit > frac_floor + 5.0 and rng.random() < 0.5 else "close_km"
    elif kind == "taiwan":
        sub = ("cover", "narrow", "cross", "far")[int(rng.integers(4))]
        pairs = _taiwan_pairs(str(TAIWAN_BANK_PATH))
    else:
        sub = None

    rejected = Counter()
    for _ in range(ADV_MAX_TRIES):
        epoch_gap_h = None
        if kind == "taiwan":
            pair = pairs[int(rng.integers(len(pairs)))]
            try:
                pursuer, evader = (rv2coe(pair[side]["r_km"], pair[side]["v_kms"])
                                    for side in ("pursuer", "evader"))
                epoch_gap_h = float(pair["epoch_gap_h"])
            except (KeyError, TypeError, ValueError) as exc:
                rejected[f"題庫狀態欄位錯誤：{exc}"] += 1
                continue
        else:
            pursuer, evader, reason = _adv_orbit_pair(rng, rule, kind, sub)
            if reason:
                rejected[reason] += 1
                continue
        if not all(FINAL_ALT_KM[0] <= o["sma"] - RE_VAL <= FINAL_ALT_KM[1]
                   and 0.0 <= o["ecc"] <= FINAL_ECC_MAX
                   and o["sma"] * (1.0 - o["ecc"]) - RE_VAL >= FINAL_MIN_PERIGEE_ALT_KM
                   for o in (pursuer, evader)):
            rejected["LEO 高度、偏心率或近地點不合法"] += 1
            continue
        rp, vp = get_r0_v0(**pursuer)
        re, ve = get_r0_v0(**evader)
        dist = float(np.linalg.norm(rp - re))
        if kind != "taiwan" and not ADV_DIST_KM[0] <= dist <= ADV_DIST_KM[1]:
            rejected["初始距離不在 20–1500 km"] += 1
            continue
        if kind == "close":
            if sub == "close_frac" and not (2.0 * rule.capture_radius_km <= dist <
                                              0.2 * rule.max_dv_evader_mps / 1000.0 * rule.window_sec):
                rejected["close_frac 距離不在 2·R_cap 到 0.2·D·T 之間"] += 1
                continue
            if sub == "close_km" and not 20.0 <= dist <= 100.0:
                rejected["close_km 距離不在 20–100 km"] += 1
                continue
        if dist <= rule.capture_radius_km:
            rejected["開局已在捕獲半徑內"] += 1
            continue
        a_p, a_e = sma_official(rp, vp), sma_official(re, ve)
        da = full_burn_dsma_km(a_e, rule.max_dv_evader_mps)
        zone, reason = _adv_zone(rng, kind, sub, a_p, a_e, da, min_lo)
        if reason:
            rejected[reason] += 1
            continue
        center = (zone[0] + zone[1]) / 2.0
        meta = {
            "kind": kind,
            "sub": sub,
            "a_p": float(a_p),
            "a_e": float(a_e),
            "da": float(da),
            "zone_width_da": float((zone[1] - zone[0]) / da),
            "zone_offset_da": float((center - a_e) / da),
            "ap_in_zone": bool(zone[0] <= a_p <= zone[1]),
            "cross": bool((a_e - a_p) * (center - a_p) < 0.0),
            "dist0_km": dist,
            "dist0_over_DT": float(1000.0 * dist / (rule.max_dv_evader_mps * rule.window_sec)),
        }
        if kind == "taiwan":
            meta["epoch_gap_h"] = epoch_gap_h
        return rule.with_(safe_sma_km=zone), Scenario(pursuer, evader, f"final_adv_{kind}", meta)
    details = "、".join(f"{name} {count} 次" for name, count in rejected.most_common())
    raise RuntimeError(f"{kind} 對抗題拒絕抽樣 {ADV_MAX_TRIES} 次仍抽不到合法題目：{details}")
