"""排位賽 T_max：A 過近地點後，地心距離第一次增加到任務邊界的時刻。

規則（docs/RANKING_ROUND_RULES_20261006.md）：T_max 是「A 過近地點後，地心距離**第一次增加到**
任務邊界的時刻」，邊界值開賽才公布。`MissionOptimizer` 對雙曲線 A 不猜公式，要求 config
填 `rules.T_MAX_SEC`；這個模組把「A 的軌道根數 + 邊界距離」換成那個秒數。

兩條路，互相交叉驗證：
  * `analytic_tmax`：二體 Kepler 方程（雙曲線用 M = e·sinh F − F，橢圓用 M = E − e·sin E）。
    只用 SMA/ECC/TA，跟 INC/RAAN/AOP 無關。
  * `numeric_tmax`：用 `src.propagator.propagate`（跟 MissionOptimizer 傳播 A 同一支
    DOP853、同一組 J2–J4 係數、同樣從 epoch 一口氣積到 t）找 |r(t)| 第一次往上穿過邊界。
    gravity_degree=0 時應該跟解析解一致到毫秒；=4 時差的就是 J2–J4 的影響。

時間一律從 epoch（任務開始，t=0）起算，單位秒；距離 km。

「過近地點後」怎麼判斷：|r| 往上穿過邊界時徑向速度一定 > 0，也就是一定已經過了某次近地點
（可能在 epoch 之前）。所以「t > 0 之後第一次往上穿過邊界」就等於規則的定義，不用另外
追蹤近地點；近地點時刻只拿來報告。邊界情況：
  * A 在 epoch 已經過了近地點、還在邊界內 → T_max 就是這次往外飛出邊界的時刻（附註提醒）。
  * A 在 epoch 已經過了近地點、而且已經在邊界外 → 雙曲線不會再回來，丟 TmaxError。
  * 邊界 ≤ 近地點距離 → A 的距離永遠不會「增加到」邊界，丟 TmaxError。
  * 橢圓：邊界 > 遠地點丟 TmaxError；否則取 epoch 之後第一次往外穿越（可能要等下一圈）。
  * 圓軌道、拋物線：沒有可用的定義，丟 TmaxError。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

MU_EARTH = 398600.4418  # km^3/s^2，跟 MissionOptimizer.MU 相同
RE_EARTH = 6378.137     # km，跟 src.propagator.RE_VAL 相同

_ECC_PARABOLIC_TOL = 1e-9
_ECC_CIRCULAR_TOL = 1e-8


class TmaxError(ValueError):
    """這組軌道與邊界算不出規則定義的 T_max；訊息會講原因。"""


@dataclass
class TmaxResult:
    t_max_sec: float             # 從 epoch 起算，A 第一次往外穿過邊界的時刻
    t_periapsis_sec: float       # 穿越前那次近地點的時刻（負的 = epoch 之前就過了）
    orbit_type: str              # "hyperbolic" / "elliptic"
    r0_km: float                 # epoch 時的地心距離
    rp_km: float                 # 近地點距離
    ra_km: float                 # 遠地點距離（雙曲線是 inf）
    boundary_km: float
    period_sec: float | None     # 橢圓才有
    notes: list[str] = field(default_factory=list)

    @property
    def twice_time_to_periapsis_sec(self) -> float | None:
        """舊共用情境編 T_MAX_SEC 用的「2 × 到近地點的時間」；A 已過近地點時沒有意義。"""
        if self.t_periapsis_sec <= 0.0:
            return None
        return 2.0 * self.t_periapsis_sec


def wrap_ta_deg(ta_deg: float) -> float:
    """真近點角折到 (-180, 180]。"""
    w = (float(ta_deg) + 180.0) % 360.0 - 180.0
    return 180.0 if w == -180.0 else w


def analytic_tmax(sma_km: float, ecc: float, ta_deg: float, boundary_km: float,
                  mu: float = MU_EARTH) -> TmaxResult:
    """二體解析 T_max。sma_km 依 GMAT 慣例：雙曲線為負。"""
    sma, e, R = float(sma_km), float(ecc), float(boundary_km)
    if not (math.isfinite(sma) and math.isfinite(e) and math.isfinite(R)):
        raise TmaxError("SMA/ECC/邊界必須是有限數字")
    if R <= 0.0:
        raise TmaxError(f"任務邊界必須是正的地心距離，收到 {R} km")
    if e < 0.0:
        raise TmaxError(f"ECC 不能是負的，收到 {e}")
    if abs(e - 1.0) < _ECC_PARABOLIC_TOL:
        raise TmaxError("拋物線軌道（ECC≈1）沒有 SMA 可填，這裡不支援；請改給狀態向量或確認根數")
    if e < _ECC_CIRCULAR_TOL:
        raise TmaxError("圓軌道沒有近地點，距離恆定，「過近地點後增加到邊界」沒有定義")
    if e > 1.0:
        if sma >= 0.0:
            raise TmaxError(f"ECC={e} > 1 是雙曲線，SMA 必須為負（GMAT 慣例），收到 {sma}")
        return _analytic_hyperbolic(sma, e, ta_deg, R, mu)
    if sma <= 0.0:
        raise TmaxError(f"ECC={e} < 1 是橢圓，SMA 必須為正，收到 {sma}")
    return _analytic_elliptic(sma, e, ta_deg, R, mu)


def _analytic_hyperbolic(a, e, ta_deg, R, mu):
    nu = math.radians(wrap_ta_deg(ta_deg))
    nu_inf = math.acos(-1.0 / e)
    if abs(nu) >= nu_inf:
        raise TmaxError(f"TA={ta_deg}° 在漸近線外（|TA| 必須 < {math.degrees(nu_inf):.3f}°）")
    abs_a = -a
    p = abs_a * (e * e - 1.0)
    r0 = p / (1.0 + e * math.cos(nu))
    rp = abs_a * (e - 1.0)
    n = math.sqrt(mu / abs_a ** 3)

    F0 = 2.0 * math.atanh(math.sqrt((e - 1.0) / (e + 1.0)) * math.tan(nu / 2.0))
    t0 = (e * math.sinh(F0) - F0) / n        # epoch 相對近地點的時間（負 = 還沒到）

    if R <= rp:
        raise TmaxError(
            f"任務邊界 {R:.3f} km ≤ A 的近地點距離 {rp:.3f} km：A 的距離永遠不會小於近地點，"
            "也就不會「增加到」邊界。請確認邊界是地心距離（不是高度）、根數有沒有抄錯")
    Fb = math.acosh((1.0 + R / abs_a) / e)
    tb = (e * math.sinh(Fb) - Fb) / n        # 往外穿過邊界的時刻（相對近地點）
    T = tb - t0
    notes = []
    if T <= 0.0:
        raise TmaxError(
            f"A 在 epoch 已經過了近地點（{t0:.1f} s 前）而且已經在邊界外（r0={r0:.1f} > {R:.1f} km），"
            "雙曲線不會再回來，規則定義的 T_max 不存在。請確認 TA 的正負號與邊界值")
    if t0 > 0.0:
        notes.append(f"A 在 epoch 已經過了近地點（{t0:.1f} s 前）；T_max 取這次往外飛出邊界的時刻。"
                     "確認主辦單位的定義也接受「近地點在任務開始前」")
    elif r0 < R:
        notes.append(f"A 在 epoch 已經在邊界內（r0={r0:.1f} < {R:.1f} km），正往近地點飛")
    else:
        notes.append(f"A 在 epoch 位於邊界外（r0={r0:.1f} km），先往內穿過邊界、過近地點、再往外穿出")
    return TmaxResult(t_max_sec=T, t_periapsis_sec=-t0, orbit_type="hyperbolic", r0_km=r0,
                      rp_km=rp, ra_km=math.inf, boundary_km=R, period_sec=None, notes=notes)


def _analytic_elliptic(a, e, ta_deg, R, mu):
    nu = math.radians(wrap_ta_deg(ta_deg))
    rp, ra = a * (1.0 - e), a * (1.0 + e)
    r0 = a * (1.0 - e * e) / (1.0 + e * math.cos(nu))
    n = math.sqrt(mu / a ** 3)
    period = 2.0 * math.pi / n
    if R <= rp:
        raise TmaxError(f"任務邊界 {R:.3f} km ≤ A 的近地點距離 {rp:.3f} km，A 的距離不會「增加到」邊界")
    if R > ra:
        raise TmaxError(f"任務邊界 {R:.3f} km > A 的遠地點距離 {ra:.3f} km：橢圓 A 永遠在邊界內，"
                        "規則定義的 T_max 不存在。改問主辦單位（初賽是 4 × A 的週期）")
    E0 = 2.0 * math.atan2(math.sqrt(1.0 - e) * math.sin(nu / 2.0), math.sqrt(1.0 + e) * math.cos(nu / 2.0))
    M0 = (E0 - e * math.sin(E0)) % (2.0 * math.pi)
    Eb = math.acos(max(-1.0, min(1.0, (1.0 - R / a) / e)))
    Mb = Eb - e * math.sin(Eb)
    dM = (Mb - M0) % (2.0 * math.pi)
    notes = []
    if dM <= 1e-12:
        dM += 2.0 * math.pi
        notes.append("A 在 epoch 正好在邊界上往外飛；取下一圈的穿越")
    T = dM / n
    t_peri = T - Mb / n
    if t_peri < 0.0:
        notes.append(f"A 在 epoch 已經過了近地點（{-t_peri:.1f} s 前）；T_max 取這次往外穿越邊界的時刻")
    elif M0 > Mb:
        notes.append(f"A 在 epoch 已經過了這一圈的穿越點，要等下一次近地點（{t_peri:.1f} s 後）才穿越")
    notes.append(f"橢圓 A：週期 {period:.1f} s。初賽的 T_max 是 4 × 週期 = {4 * period:.1f} s，"
                 "排位賽若真的給橢圓 A，先問主辦單位用哪個定義")
    return TmaxResult(t_max_sec=T, t_periapsis_sec=t_peri, orbit_type="elliptic", r0_km=r0,
                      rp_km=rp, ra_km=ra, boundary_km=R, period_sec=period, notes=notes)


@dataclass
class NumericTmax:
    t_max_sec: float
    t_periapsis_sec: float | None   # 掃描範圍內找到的第一個近地點（找不到 = 掃描開始前就過了）
    gravity_degree: int
    step_sec: float
    r_at_tmax_km: float


def numeric_tmax(r0, v0, boundary_km: float, gravity_degree: int = 4, t_guess: float | None = None,
                 t_end: float | None = None, step_sec: float | None = None,
                 mu: float = MU_EARTH) -> NumericTmax:
    """數值傳播找 t > 0 第一次 |r| 往上穿過邊界的時刻。

    先用固定步長分段往前推找夾住穿越的區間（分段推只用來找區間），再用 brentq 從 epoch
    一口氣傳播到 t 精修——跟 MissionOptimizer 在攔截時刻傳播 A 的呼叫方式相同。
    """
    from scipy.optimize import brentq
    from src.propagator import propagate

    r0 = np.asarray(r0, dtype=np.float64)
    v0 = np.asarray(v0, dtype=np.float64)
    R = float(boundary_km)
    deg = int(gravity_degree)
    if step_sec is None:
        # 1999.37 而不是整數：避免格點剛好落在解析解上 (那時分段推和從 epoch 推的 |r|-R
        # 可能一正一負，差 1e-9 km 就夾不住)。_root_in 也會處理端點，這只是少一次邊界情況。
        step_sec = 60.0 if t_guess is None else min(600.0, max(5.0, t_guess / 1999.37))
    if t_end is None:
        t_end = 30 * 86400.0 if t_guess is None else 2.0 * t_guess + 50.0 * step_sec

    def r_of(t):
        if t <= 0.0:
            return float(np.linalg.norm(r0))
        r, _ = propagate(mu, r0, v0, float(t), deg)
        return float(np.linalg.norm(r))

    def rdot_of(t):
        if t <= 0.0:
            r, v = r0, v0
        else:
            r, v = propagate(mu, r0, v0, float(t), deg)
        return float(np.dot(r, v) / np.linalg.norm(r))

    def _root_in(f, a, b, xtol):
        # 夾區間是用分段推的狀態找的，精修改用從 epoch 推；兩者差 ~1e-9 km，端點剛好貼著根時
        # 符號可能不一致，那時端點本身就是答案。
        fa, fb = f(a), f(b)
        if fa >= 0.0:
            return a
        if fb <= 0.0:
            return b
        return brentq(f, a, b, xtol=xtol)

    t_prev = 0.0
    r_prev, v_prev = r0.copy(), v0.copy()
    rn_prev = float(np.linalg.norm(r_prev))
    rd_prev = float(np.dot(r_prev, v_prev)) / rn_prev
    t_peri = None
    while t_prev < t_end:
        h = min(step_sec, t_end - t_prev)
        r_next, v_next = propagate(mu, r_prev, v_prev, h, deg)
        t_next = t_prev + h
        rn_next = float(np.linalg.norm(r_next))
        rd_next = float(np.dot(r_next, v_next)) / rn_next
        if t_peri is None and rd_prev < 0.0 <= rd_next:
            t_peri = _root_in(rdot_of, t_prev, t_next, 1e-6)
        if rn_prev < R <= rn_next:
            t_cross = _root_in(lambda t: r_of(t) - R, t_prev, t_next, 1e-7)
            return NumericTmax(t_max_sec=t_cross, t_periapsis_sec=t_peri, gravity_degree=deg,
                               step_sec=step_sec, r_at_tmax_km=r_of(t_cross))
        t_prev, r_prev, v_prev, rn_prev, rd_prev = t_next, r_next, v_next, rn_next, rd_next
    raise TmaxError(f"數值傳播到 t={t_end:.0f} s 都沒有往外穿過邊界 {R:.1f} km")


def recommended_t_max_sec(analytic: TmaxResult, numeric: NumericTmax | None) -> float:
    """要填進 rules.T_MAX_SEC 的值：解析與數值取早的那個，無條件捨去到整秒。

    取早的：T_max 是攔截時刻的上限，寧可把可行窗縮小一點，也不要規劃出比官方 T_max 晚的
    攔截。差距通常是秒級，對分數沒有影響（時間分在 T_max 附近已經很小）。
    """
    t = analytic.t_max_sec if numeric is None else min(analytic.t_max_sec, numeric.t_max_sec)
    return float(math.floor(t))
