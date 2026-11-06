"""決賽追逃賽局的純遊戲核心（與 gym 解耦）。

一個 **turn** = 輪到的一方（mover）下一發脈衝 → 雙方滑行 `window_sec`（最後一回合截到
T_max）→ 換另一方。滑行期間用 `physics.coast.coast_pair` 連續偵測捕獲 / 撞地，事件
發生就停在那個時刻結束比賽。

一回合多發（HAP-107，`Rules.burns_per_turn > 1`）：mover 可在同一窗口內、間隔至少
`min_burn_gap_sec` 下多發。`play_plan` 吃（窗口內偏移秒數, Δv）清單；`take_turn` 讓 agent
在窗口內依序決定每一發（窗口內對手不動，所以在副本上推進到下一發的時刻再問 agent
即可，任何單發 agent 都能直接用）。`burns_per_turn=1` 時 `play_turn` 的運算與舊版逐位元相同。

勝負（官方）：追者在時間+燃料內靠近到捕獲半徑 → 追者勝；躲者撐到 T_max → 躲者勝。
撞地（軌跡低於 crash_altitude）→ 撞的那方輸（佔位判定，待 HAP-50）。

T_max（開賽時定死，之後不變）：`Rules.t_max_sec` > 0 直接用；否則 `t_max_boundary_km` > 0 用排位賽定義
（飛掠方過近地點後地心距離第一次增加到任務邊界的時刻，見 boundary_exit_time）；否則 t_max_periods × 追者
初始週期（追者是雙曲線、沒有週期時改用躲者的週期）。

同時出手（金／銅牌賽正式賽制，`Rules.turn_mode = "simultaneous"`）：`play_round(dv_p, dv_e)` 在回合起點
同時施加雙方的一發，一起滑行 window_sec（= T_round），共 rounds 回合；`take_round` 讓兩邊的 agent 各自在
副本上決定，互相看不到。最後一回合結束時逃方半長軸（sma_official）落在 `safe_sma_km` → escape（躲者勝），
否則 sma_out（追者勝）；沒有 safe_sma_km 時就是 timeout。

Agent 直接吃 Game（完整狀態：雙方 r/v、燃料、時間、規則），不必經過 RL 觀測；RL 的
觀測由 game/obs.py 從 Game 組出來。
"""
import copy
import math

import numpy as np

from game.rules import SIDES, Rules, other
from physics import EARTH_MU, RE_VAL, get_r0_v0, orbital_period, propagate
from physics.coast import EV_CAPTURE, EV_CRASH_E, EV_CRASH_P, EV_NONE, coast_pair
from physics.frames import rsw_basis

OUTCOME_WINNER = {
    "capture": "pursuer",
    "crash_evader": "pursuer",
    "timeout": "evader",
    "crash_pursuer": "evader",
    "escape": "evader",
    "sma_out": "pursuer",
}


def sma_from_rv(r, v, mu=EARTH_MU):
    energy = float(v @ v) / 2.0 - mu / float(np.linalg.norm(r))
    return -mu / (2.0 * energy) if energy < 0 else math.inf


def sma_official(r, v, mu=EARTH_MU):
    """金／銅牌賽規則的半長軸 a = (2/|r| − |v|²/μ)^-1（km）：雙曲線為負，拋物線為 inf。"""
    x = 2.0 / float(np.linalg.norm(r)) - float(np.dot(v, v)) / mu
    return 1.0 / x if x != 0.0 else math.inf


def specific_energy(r, v, mu=EARTH_MU):
    """比機械能 v²/2 − μ/r（km²/s²）：< 0 橢圓、> 0 雙曲線。"""
    return float(np.dot(v, v)) / 2.0 - mu / float(np.linalg.norm(r))


def kepler_exit_time(r, v, boundary_km, mu=EARTH_MU):
    """二體解析：從現在起純滑行，地心距離第一次「往外」穿過 boundary_km 的時刻（秒）。

    雙曲線用 M = e·sinh F − F、橢圓用 M = E − e·sin E（同 Planner src/tmax.py 的 analytic_tmax，
    只是吃 r, v 而不是六根數）。穿越不存在時丟 ValueError（訊息講原因）。"""
    r = np.asarray(r, dtype=np.float64)
    v = np.asarray(v, dtype=np.float64)
    R = float(boundary_km)
    r0 = float(np.linalg.norm(r))
    rv = float(np.dot(r, v))
    hv = np.cross(r, v)
    h2 = float(np.dot(hv, hv))
    en = specific_energy(r, v, mu)
    e = math.sqrt(max(0.0, 1.0 + 2.0 * en * h2 / mu ** 2))
    rp = h2 / (mu * (1.0 + e))
    if R <= rp:
        raise ValueError(f"任務邊界 {R:.1f} km ≤ 近地點距離 {rp:.1f} km：地心距離不會「增加到」邊界"
                         "（邊界要給地心距離，不是高度）")
    if abs(e - 1.0) < 1e-9:
        raise ValueError("拋物線軌道（e≈1）不支援：請直接給 t_max_sec")
    if e < 1e-12:
        raise ValueError("圓軌道：地心距離不變，「過近地點後增加到邊界」沒有定義")
    if e > 1.0:
        a = -mu / (2.0 * en)                       # < 0
        n = math.sqrt(mu / (-a) ** 3)
        F0 = math.copysign(math.acosh(max(1.0, (1.0 + r0 / -a) / e)), rv)
        Fb = math.acosh((1.0 + R / -a) / e)
        T = ((e * math.sinh(Fb) - Fb) - (e * math.sinh(F0) - F0)) / n
        if T <= 0.0:
            raise ValueError(f"已經過了近地點、而且已在邊界外往外飛（r={r0:.1f} km ≥ {R:.1f} km）："
                             "雙曲線不會再回來，T_max 不存在")
        return T
    a = -mu / (2.0 * en)
    ra = a * (1.0 + e)
    if R > ra:
        raise ValueError(f"任務邊界 {R:.1f} km > 遠地點 {ra:.1f} km：橢圓軌道永遠在邊界內，T_max 不存在")
    n = math.sqrt(mu / a ** 3)
    E0 = math.acos(min(1.0, max(-1.0, (1.0 - r0 / a) / e)))
    if rv < 0.0:
        E0 = 2.0 * math.pi - E0
    Eb = math.acos(min(1.0, max(-1.0, (1.0 - R / a) / e)))
    dM = ((Eb - e * math.sin(Eb)) - (E0 - e * math.sin(E0))) % (2.0 * math.pi)
    if dM <= 1e-12:
        dM += 2.0 * math.pi                        # 剛好在邊界上往外：下一圈
    return dM / n


def boundary_exit_time(r, v, boundary_km, mu=EARTH_MU, gravity_degree=2, step_sec=120.0):
    """排位賽 T_max：從現在起純滑行，地心距離第一次「往外」穿過 boundary_km（地心距離 km）的時刻（秒）。

    規則原文是「A 過近地點後，地心距離第一次增加到任務邊界的時刻」。往外穿越時徑向速度 > 0，一定已經
    過了某次近地點（可能在開賽前），所以等於「t > 0 之後第一次往外穿越」（同 Planner src/tmax.py）。
    先用二體解析解（kepler_exit_time）確認穿越存在，再用引擎同一套重力模型（gravity_degree）分段傳播
    找穿越區間、二分到 0.1 ms——跟比賽中純滑行的那艘船真正飛出邊界的時刻一致（J2 讓它跟解析解差幾秒）。"""
    r = np.asarray(r, dtype=np.float64)
    v = np.asarray(v, dtype=np.float64)
    R = float(boundary_km)
    t_ana = kepler_exit_time(r, v, R, mu)
    t_end = 1.5 * t_ana + 3600.0
    t, rr, vv = 0.0, r.copy(), v.copy()
    rn = float(np.linalg.norm(rr))
    while t < t_end:
        h = min(step_sec, t_end - t)
        r1, v1 = propagate(mu, rr, vv, h, gravity_degree)
        rn1 = float(np.linalg.norm(r1))
        if not math.isfinite(rn1):
            break
        if rn < R <= rn1:
            lo, hi = 0.0, h
            while hi - lo > 1e-4:
                mid = 0.5 * (lo + hi)
                if float(np.linalg.norm(propagate(mu, rr, vv, mid, gravity_degree)[0])) >= R:
                    hi = mid
                else:
                    lo = mid
            return t + hi
        t, rr, vv, rn = t + h, r1, v1, rn1
    raise ValueError(f"數值傳播到 t={t_end:.0f} s 都沒有往外穿過邊界 {R:.1f} km（二體解析 {t_ana:.1f} s）")


def flyby_side(rp, vp, re, ve, mu=EARTH_MU):
    """飛掠方 = 初始比能量較高的一方（雙曲線那方；排位賽的外星船 A）。"""
    return "evader" if specific_energy(re, ve, mu) > specific_energy(rp, vp, mu) else "pursuer"


class Game:
    def __init__(self, rules: Rules, rp, vp, re, ve, mu: float = EARTH_MU):
        self.rules = rules
        self.mu = float(mu)
        self._r = {"pursuer": np.asarray(rp, dtype=np.float64).copy(),
                   "evader": np.asarray(re, dtype=np.float64).copy()}
        self._v = {"pursuer": np.asarray(vp, dtype=np.float64).copy(),
                   "evader": np.asarray(ve, dtype=np.float64).copy()}
        self.used = {"pursuer": 0.0, "evader": 0.0}
        self.t = 0.0
        if rules.t_max_sec <= 0 and rules.simultaneous:
            self.t_max = rules.rounds * float(rules.window_sec)
            self.t_max_basis = "rounds"
        elif rules.t_max_sec > 0:
            self.t_max = float(rules.t_max_sec)
            self.t_max_basis = "t_max_sec"
        elif rules.t_max_boundary_km > 0:
            side = flyby_side(self._r["pursuer"], self._v["pursuer"], self._r["evader"], self._v["evader"], mu)
            self.t_max = boundary_exit_time(self._r[side], self._v[side], rules.t_max_boundary_km, mu,
                                            rules.gravity_degree)
            self.t_max_basis = f"boundary({side})"
        else:
            self.t_max_basis = "periods(pursuer)"
            T = orbital_period(sma_from_rv(self._r["pursuer"], self._v["pursuer"], mu), mu)
            if not math.isfinite(T):
                # 追者初始軌道是雙曲線：沒有週期，T_max 會變 inf、比賽永遠不會超時 → 改用躲者的週期
                T = orbital_period(sma_from_rv(self._r["evader"], self._v["evader"], mu), mu)
                self.t_max_basis = "periods(evader)"
                if not math.isfinite(T):
                    raise ValueError("雙方初始軌道都沒有週期（雙曲線）：請用 t_max_sec 或 t_max_boundary_km 指定 T_max")
            self.t_max = rules.t_max_periods * T
        self.mover = rules.first_mover
        self.turn = 0
        self.outcome = None
        self.min_dist = self.distance()
        self.initial = {s: (self._r[s].copy(), self._v[s].copy()) for s in SIDES}
        self.history = []
        self._win_len = None        # 進行中窗口的長度；None = 不在窗口中途（下一發是回合的第一發）
        self._win_elapsed = 0.0
        self._pending = None        # 進行中窗口的回合紀錄
        if self.min_dist <= rules.capture_radius_km:
            self.outcome = "capture"

    # ------------------------------------------------------------------ 建構
    @classmethod
    def from_elements(cls, rules: Rules, orbit_pursuer: dict, orbit_evader: dict, mu: float = EARTH_MU):
        rp, vp = get_r0_v0(**orbit_pursuer, mu=mu)
        re, ve = get_r0_v0(**orbit_evader, mu=mu)
        g = cls(rules, rp, vp, re, ve, mu)
        g.initial_elements = {"pursuer": dict(orbit_pursuer), "evader": dict(orbit_evader)}
        return g

    @classmethod
    def from_snapshot(cls, rules: Rules, rp, vp, re, ve, *, t=0.0, t_max=None, used=None, mover=None,
                      mu: float = EARTH_MU, round_index=None):
        """從比賽進行中的某個狀態建 Game（copilot 用：當天看到的是中途狀態）。

        t_max 給絕對秒數（從比賽開始算）；未給時沿用 rules 的定義（以「此刻」的狀態算週期或飛出
        邊界的時刻，只適合 t=0）。
        """
        R = rules if t_max is None else rules.with_(t_max_sec=float(t_max))
        g = cls(R, rp, vp, re, ve, mu)
        g.t = float(t)
        g.used = {"pursuer": 0.0, "evader": 0.0, **(used or {})}
        g.mover = mover or R.first_mover
        if R.simultaneous:
            # round_index = 已完成的回合數；沒給時用 t 推（每回合都滑滿 window_sec）
            g.turn = int(round_index) if round_index is not None else int(round(g.t / R.window_sec))
        if g.t >= g.t_max - 1e-6 and g.outcome is None:
            g.outcome = g._terminal_outcome() if R.simultaneous else "timeout"
        return g

    def clone(self) -> "Game":
        g = copy.copy(self)
        g._r = {s: a.copy() for s, a in self._r.items()}
        g._v = {s: a.copy() for s, a in self._v.items()}
        g.used = dict(self.used)
        g.history = list(self.history)
        if self._pending is not None:
            g._pending = {**self._pending, "burns": list(self._pending["burns"])}
        return g

    def alternating_view(self, side) -> "Game":
        """simultaneous 局給舊 agent 用的副本：同一個狀態、同一個 T_max，但規則換成回合交替、輪到 side，
        讓為交替賽制寫的 agent（內部用 play_turn 模擬）照常運作。只是決策用的模型，真的局不受影響。"""
        g = self.clone()
        g.rules = self.rules.with_(turn_mode="alternating", t_max_sec=self.t_max, first_mover=side)
        g.mover = side
        return g

    # ------------------------------------------------------------------ 查詢
    def r(self, side):
        return self._r[side]

    def v(self, side):
        return self._v[side]

    def distance(self) -> float:
        return float(np.linalg.norm(self._r["pursuer"] - self._r["evader"]))

    def fuel_left(self, side) -> float:
        return max(0.0, self.rules.fuel(side) - self.used[side])

    def burn_cap(self, side) -> float:
        """這一發最多能推多少 m/s（單次上限與剩餘燃料取小）。"""
        return min(self.rules.max_dv(side), self.fuel_left(side))

    @property
    def time_left(self) -> float:
        return max(0.0, self.t_max - self.t)

    @property
    def done(self) -> bool:
        return self.outcome is not None

    @property
    def winner(self):
        return OUTCOME_WINNER.get(self.outcome)

    @property
    def crash_radius(self) -> float:
        return RE_VAL + self.rules.crash_altitude_km

    def period(self, side) -> float:
        """該方當前密切軌道週期（雙曲線時回傳 6000 s 當尺度，避免 inf 傳下去）。"""
        a = sma_from_rv(self._r[side], self._v[side], self.mu)
        return orbital_period(a, self.mu) if math.isfinite(a) else 6000.0

    def next_window(self) -> float:
        """這一發之後最多還能滑行多久：回合開始時是整個窗口，窗口中途是窗口剩下的部分。"""
        if self._win_len is None:
            return min(self.rules.window_sec, self.time_left)
        return max(0.0, self._win_len - self._win_elapsed)

    @property
    def mid_window(self) -> bool:
        return self._win_len is not None

    # ------------------------------------------------------------------ 推進
    def clip_dv(self, side, dv_eci_mps) -> np.ndarray:
        dv = np.asarray(dv_eci_mps, dtype=np.float64).reshape(3)
        if not np.all(np.isfinite(dv)):
            return np.zeros(3)
        mag = float(np.linalg.norm(dv))
        cap = self.burn_cap(side)
        if mag > cap:
            dv = dv * (cap / mag) if mag > 0 else np.zeros(3)
        return dv

    def play_turn(self, dv_eci_mps) -> dict:
        """輪到的一方施加脈衝（自動裁到合法）並滑行一個窗口。回傳這個 turn 的紀錄。

        窗口中途（多發）呼叫時，這一發之後滑完窗口剩下的部分並結束回合。"""
        return self.sub_burn(dv_eci_mps, math.inf)

    def sub_burn(self, dv_eci_mps, coast_sec):
        """輪到的一方推一發，雙方滑行 min(coast_sec, 窗口剩餘)。窗口滑完（或比賽結束）時結束
        回合、換手並回傳回合紀錄；否則回傳 None（仍在同一窗口，可再推下一發）。"""
        if self.rules.simultaneous:
            raise RuntimeError("simultaneous 賽制請用 play_round（雙方同時出手）")
        if self.done:
            raise RuntimeError("比賽已結束")
        side = self.mover
        if self._win_len is None:
            self._win_len = min(self.rules.window_sec, self.time_left)
            self._win_elapsed = 0.0
            self._pending = {"turn": self.turn, "side": side, "t": self.t, "burns": [],
                             "window_min_dist_km": math.inf, "t_window_min": self.t}
        P = self._pending
        dv = self.clip_dv(side, dv_eci_mps)
        mag = float(np.linalg.norm(dv))
        r_b, v_b = self._r[side].copy(), self._v[side].copy()
        dv_rsw = rsw_basis(r_b, v_b) @ dv
        self._v[side] = self._v[side] + dv / 1000.0
        self.used[side] += mag
        P["burns"].append({"t": self.t, "dv_eci_mps": dv, "dv_rsw_mps": dv_rsw, "dv_mps": mag,
                           "r_before": r_b, "v_before": v_b})

        dt = min(coast_sec, self._win_len - self._win_elapsed)
        R = self.rules
        continuous = R.capture_mode == "continuous"
        rp, vp, re, ve, t_el, ev, dmin, t_dmin = coast_pair(
            self._r["pursuer"], self._v["pursuer"], self._r["evader"], self._v["evader"],
            dt, R.substep_sec, self.mu, R.gravity_degree, R.capture_radius_km if continuous else -1.0,
            self.crash_radius)
        self._win_elapsed += float(t_el)
        window_over = self._win_elapsed >= self._win_len - 1e-9
        if not continuous and window_over and ev == EV_NONE and float(np.linalg.norm(rp - re)) <= R.capture_radius_km:
            ev = EV_CAPTURE                      # endpoint 模式：只看回合結束瞬間
        self._r["pursuer"], self._v["pursuer"] = rp, vp
        self._r["evader"], self._v["evader"] = re, ve
        t0 = self.t
        self.t += float(t_el)
        self.min_dist = min(self.min_dist, float(dmin))
        if float(dmin) < P["window_min_dist_km"]:
            P["window_min_dist_km"], P["t_window_min"] = float(dmin), t0 + float(t_dmin)

        if ev == EV_CAPTURE:
            self.outcome = "capture"
        elif ev == EV_CRASH_P:
            self.outcome = "crash_pursuer"
        elif ev == EV_CRASH_E:
            self.outcome = "crash_evader"
        elif self.t >= self.t_max - 1e-6:
            self.outcome = "timeout"
        if not (window_over or self.done):
            return None

        first = P["burns"][0]
        rec = {
            "turn": P["turn"], "side": side, "t": P["t"], "dv_eci_mps": first["dv_eci_mps"],
            "dv_rsw_mps": first["dv_rsw_mps"],
            "dv_mps": first["dv_mps"] if len(P["burns"]) == 1 else float(sum(b["dv_mps"] for b in P["burns"])),
            "r_before": first["r_before"], "v_before": first["v_before"], "coast_sec": self._win_elapsed,
            "window_min_dist_km": P["window_min_dist_km"], "t_window_min": P["t_window_min"],
            "distance_after_km": self.distance(), "outcome": self.outcome,
            "rp_after": rp.copy(), "vp_after": vp.copy(), "re_after": re.copy(), "ve_after": ve.copy(),
            "burns": P["burns"],
        }
        self.history.append(rec)
        self.turn += 1
        self.mover = other(side)
        self._win_len, self._win_elapsed, self._pending = None, 0.0, None
        return rec

    def _window_used(self):
        """進行中窗口已下的（非零）發：回傳 (窗口內已過秒數, 已下發數, 最後一發的偏移或 None)。"""
        if self._win_len is None:
            return 0.0, 0, None
        offs = [b["t"] - self._pending["t"] for b in self._pending["burns"] if b["dv_mps"] > 0.0]
        return self._win_elapsed, len(offs), (offs[-1] if offs else None)

    def play_plan(self, burns) -> dict:
        """下完這個回合（剩下的部分）：burns = [(窗口內偏移秒數, ECI Δv m/s), ...]，偏移從窗口開始算。

        不合法的發會被丟掉：偏移不在「現在～窗口結束」之間、跟前一發間隔 < min_burn_gap_sec、
        超過 burns_per_turn 發（含這個窗口已經下的）。零向量不算一發。回傳回合紀錄。"""
        if self.rules.simultaneous:
            raise RuntimeError("simultaneous 賽制請用 play_round（雙方同時出手）")
        if self.done:
            raise RuntimeError("比賽已結束")
        R = self.rules
        start, n_used, prev = self._window_used()
        win = self._win_len if self._win_len is not None else self.next_window()
        plan = sorted(((float(o), np.asarray(d, dtype=np.float64).reshape(3)) for o, d in burns),
                      key=lambda x: x[0])
        kept = []
        for o, d in plan:
            if n_used + len(kept) >= R.burns_per_turn:
                break
            if not (start - 1e-6 <= o < win) or not np.any(d):
                continue
            last = kept[-1][0] if kept else prev
            if last is not None and o - last < R.min_burn_gap_sec - 1e-6:
                continue
            kept.append((max(o, start), d))
        if not kept or kept[0][0] > start:
            kept.insert(0, (start, np.zeros(3)))   # 第一發之前先滑行（零向量不算一發）
        rec = None
        for i, (o, d) in enumerate(kept):
            nxt = kept[i + 1][0] if i + 1 < len(kept) else math.inf
            rec = self.sub_burn(d, nxt - o)
            if rec is not None:
                break
        return rec

    def play_round(self, dv_pursuer_eci_mps, dv_evader_eci_mps) -> dict:
        """simultaneous 賽制的一回合：雙方的一發（自動等比例縮到上限）在回合起點同時施加，一起滑行
        window_sec（最後截到 T_max），連續偵測捕獲／撞地，事件發生就停在那個時刻結束比賽。
        最後一回合滑完沒有事件時判終局（見 _terminal_outcome）。回傳的回合紀錄就是主辦單位每回合
        公告的內容：雙方實際 Δv、最近距離與時刻、是否攔截、逃方半長軸、回合結束時的狀態。"""
        R = self.rules
        if not R.simultaneous:
            raise RuntimeError("play_round 只用在 simultaneous 賽制；回合交替請用 play_turn")
        if self.done:
            raise RuntimeError("比賽已結束")
        t0 = self.t
        burns = []
        for side, dv_in in (("pursuer", dv_pursuer_eci_mps), ("evader", dv_evader_eci_mps)):
            sub = np.asarray(dv_in, dtype=np.float64).reshape(3).copy()
            dv = self.clip_dv(side, sub)
            mag = float(np.linalg.norm(dv))
            r_b, v_b = self._r[side].copy(), self._v[side].copy()
            burns.append({"side": side, "t": t0, "dv_eci_mps": dv, "dv_rsw_mps": rsw_basis(r_b, v_b) @ dv,
                          "dv_mps": mag, "r_before": r_b, "v_before": v_b, "dv_submitted_mps": sub,
                          "scaled": bool(not np.array_equal(dv, sub))})
        for b in burns:                       # 兩發都用回合起點的狀態算完才一起施加
            self._v[b["side"]] = self._v[b["side"]] + b["dv_eci_mps"] / 1000.0
            self.used[b["side"]] += b["dv_mps"]

        dt = min(float(R.window_sec), self.time_left)
        continuous = R.capture_mode == "continuous"
        rp, vp, re, ve, t_el, ev, dmin, t_dmin = coast_pair(
            self._r["pursuer"], self._v["pursuer"], self._r["evader"], self._v["evader"],
            dt, R.substep_sec, self.mu, R.gravity_degree, R.capture_radius_km if continuous else -1.0,
            self.crash_radius)
        if not continuous and ev == EV_NONE and float(np.linalg.norm(rp - re)) <= R.capture_radius_km:
            ev = EV_CAPTURE                      # endpoint 模式：只看回合結束瞬間
        self._r["pursuer"], self._v["pursuer"] = rp, vp
        self._r["evader"], self._v["evader"] = re, ve
        self.t += float(t_el)
        self.min_dist = min(self.min_dist, float(dmin))
        if ev == EV_CAPTURE:
            self.outcome = "capture"
        elif ev == EV_CRASH_P:
            self.outcome = "crash_pursuer"
        elif ev == EV_CRASH_E:
            self.outcome = "crash_evader"
        elif self.t >= self.t_max - 1e-6:
            self.outcome = self._terminal_outcome()

        rec = {
            "round": self.turn + 1, "turn": self.turn, "side": "both", "t": t0, "burns": burns,
            "coast_sec": float(t_el), "window_min_dist_km": float(dmin), "t_window_min": t0 + float(t_dmin),
            "distance_after_km": self.distance(), "outcome": self.outcome,
            "rp_after": rp.copy(), "vp_after": vp.copy(), "re_after": re.copy(), "ve_after": ve.copy(),
            "sma_evader_km": sma_official(re, ve, self.mu),
        }
        self.history.append(rec)
        self.turn += 1
        return rec

    def _terminal_outcome(self) -> str:
        """simultaneous 撐完所有回合時的結局：沒有安全空域 → timeout；逃方 a 在 [lo, hi] → escape，否則 sma_out。"""
        if self.rules.safe_sma_km is None:
            return "timeout"
        lo, hi = self.rules.safe_sma_km
        a = sma_official(self._r["evader"], self._v["evader"], self.mu)
        return "escape" if lo <= a <= hi else "sma_out"

    def set_state(self, side, r, v):
        """把某方的位置速度換成外部給的值（彩排時讓帳本跟 GMAT 的「真實世界」同步）。"""
        if self.mid_window:
            raise RuntimeError("窗口中途不能換狀態")
        self._r[side] = np.asarray(r, dtype=np.float64).reshape(3).copy()
        self._v[side] = np.asarray(v, dtype=np.float64).reshape(3).copy()

    def summary(self) -> dict:
        out = {
            "outcome": self.outcome, "winner": self.winner, "t_end": self.t, "t_max": self.t_max,
            "turns": self.turn, "min_dist_km": self.min_dist, "final_dist_km": self.distance(),
            "used_pursuer_mps": self.used["pursuer"], "used_evader_mps": self.used["evader"],
        }
        if self.rules.simultaneous:
            out["rounds_played"] = self.turn
            out["final_sma_evader_km"] = sma_official(self._r["evader"], self._v["evader"], self.mu)
        return out


def plan_turn(game, agent, first_dv=None):
    """問 agent 這個回合（剩下的部分）要怎麼推，回傳 play_plan 吃的 [(偏移秒數, Δv)]，不改動 game。

    burns_per_turn=1：只問一次（first_dv 給定就直接用它）。多發：在副本上推這一發、滑行
    min_burn_gap_sec 後再問 agent 下一發——窗口內對手不動，所以副本的未來就是真實的未來。
    可以從窗口中途開始（rollout 推演候選時會這樣用）。"""
    side = game.mover
    R = game.rules
    if R.burns_per_turn <= 1:
        return [(0.0, agent.act(game, side) if first_dv is None else first_dv)]
    sim = game.clone()
    sim.history = []
    off, n_used, prev = sim._window_used()
    win = sim._win_len if sim.mid_window else sim.next_window()
    if prev is not None and off - prev < R.min_burn_gap_sec - 1e-6:      # 離上一發太近：先等
        wait = prev + R.min_burn_gap_sec - off
        if off + wait >= win - 1e-9 or sim.sub_burn(np.zeros(3), wait) is not None:
            return []
        first_dv = None                       # 原本想現在推的那發已經不合法
    burns = []
    for i in range(R.burns_per_turn - n_used):
        off = sim._win_elapsed if sim.mid_window else 0.0
        dv = sim.clip_dv(side, first_dv if (i == 0 and first_dv is not None) else agent.act(sim, side))
        if np.any(dv):
            burns.append((off, dv))
        if i == R.burns_per_turn - n_used - 1 or off + R.min_burn_gap_sec >= win - 1e-9:
            break
        if sim.sub_burn(dv, R.min_burn_gap_sec) is not None:   # 比賽在這段滑行中結束
            break
    return burns


def take_turn(game, agent, first_dv=None) -> dict:
    """輪到的一方交給 agent 下完這個回合（可能多發）。burns_per_turn=1 時就是
    game.play_turn(agent.act(game, mover))（或 first_dv）。"""
    if game.rules.burns_per_turn <= 1:
        return game.play_turn(agent.act(game, game.mover) if first_dv is None else first_dv)
    return game.play_plan(plan_turn(game, agent, first_dv))


def round_view(game, agent, side) -> "Game":
    """simultaneous 回合起點給 agent 的副本。agent 有 `simultaneous_aware = True` 時拿同賽制的副本
    （可以自己用 play_round 模擬）；舊 agent 拿 Game.alternating_view。"""
    return game.clone() if getattr(agent, "simultaneous_aware", False) else game.alternating_view(side)


def take_round(game, agent_pursuer, agent_evader) -> dict:
    """simultaneous 賽制：兩邊的 agent 各自拿回合起點的副本決定這一發（互相看不到、也改不到真的
    game），再同時執行。"""
    dv_p = agent_pursuer.act(round_view(game, agent_pursuer, "pursuer"), "pursuer")
    dv_e = agent_evader.act(round_view(game, agent_evader, "evader"), "evader")
    return game.play_round(dv_p, dv_e)
