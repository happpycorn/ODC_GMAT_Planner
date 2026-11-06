"""追者打法實驗室：怎麼抓「受威脅才閃」的躲者（研究筆記 docs/notes/pursuer_vs_lazy.md）。

規格用 `py:agents.pursuer_lab:<類別>` 引用，不改既有程式。

背景：`agents.evader_lab.LazyEvader3` 平常不推，只有「追者下一個窗口（+60 s）一發攔得到」或「雙方滑行會在追者
窗口內接近到追者推得到」時才用 DvEvader 的閃法（26 方向 × {1.0, 0.4} × 單發上限）。回合交替下躲者永遠在追者
窗口前最後出手，閃避的位移有 ~(窗口 + t) 秒的槓桿、追者修正只有 t 秒，所以單發上限相同時「一個窗口內收掉」不可能；
唯一的路是燃料消耗戰：讓它反覆閃到剩油 ≲ 100 m/s（單發上限 250 時），再在它閃完後的窗口內收掉。

* HarassPursuer —— 燃料消耗戰追者：
  1. 這個窗口內一發抓得到 → 抓（模擬確認）。
  2. 「逼角」：用躲者模型（預設 LazyEvader3，決定性、每步毫秒級）模擬它對各候選的閃避，閃完後我方窗口內抓得到
     → 選最省的那發。躲者油多時幾乎不會成立，剩油少時才會。
  3. 否則選「Δv + λ×等待的決策數」最小、讓躲者模型在之後 k_max 個決策內判定受威脅的一發（零推力也是候選：
     閃避後的相對運動常會自己繞回來，等它回來不花油）。
  4. 都做不到 → 接近：一圈內最省的單發攔截，推得完才推（推不完就推上限、但只在時間還夠時）。
"""
import math

import numpy as np

from agents.analytic import _direction_set, rescue_burn, safe_radius
from agents.base import Agent, rsw_to_eci_dv
from agents.evader_lab import strict_survives
from physics.intercept import best_lambert, intercept_scan, min_intercept, shoot_j2
from physics.propagator import propagate


def _lambert_dv(game, tof, max_revs=0, shoot=True):
    """追者此刻一發、tof 秒後到躲者（純滑行）的位置所需 Δv（ECI m/s）；無解回傳 None。"""
    mu, gd = game.mu, game.rules.gravity_degree
    rp, vp = game.r("pursuer"), game.v("pursuer")
    r_t, _ = propagate(mu, game.r("evader"), game.v("evader"), float(tof), gd)
    d, v1 = best_lambert(mu, rp, vp, r_t, float(tof), int(max_revs), safe_radius(game))
    if not math.isfinite(d):
        return None
    if shoot and gd > 0 and tof <= 1500.0:
        v1s, miss = shoot_j2(mu, gd, rp, v1, r_t, float(tof), 6, 1e-3)
        if math.isfinite(miss) and miss < 1.0:
            v1 = v1s
    return (v1 - vp) * 1000.0


def window_capture(game, n_tof=24):
    """追者回合：這個窗口內一發（≤ 上限）抓得到就回傳該 Δv（已用模擬確認），否則 None。"""
    cap = game.burn_cap("pursuer")
    w = game.next_window()
    if cap <= 0.0 or w <= 10.0:
        return None
    R = game.rules
    dv, tof, v1 = min_intercept(game.mu, R.gravity_degree, game.r("pursuer"), game.v("pursuer"),
                                game.r("evader"), game.v("evader"), 10.0, w, n_tof, 0, safe_radius(game), 3, 12)
    if not math.isfinite(dv) or dv * 1000.0 > cap * 1.02:
        return None
    r_t, _ = propagate(game.mu, game.r("evader"), game.v("evader"), tof, R.gravity_degree)
    v1s, miss = shoot_j2(game.mu, R.gravity_degree, game.r("pursuer"), v1, r_t, tof, 6, 1e-3)
    if math.isfinite(miss) and miss < 1.0:
        v1 = v1s
    cand = game.clip_dv("pursuer", (v1 - game.v("pursuer")) * 1000.0)
    h = game.clone()
    h.history = []
    h.play_turn(cand)
    return cand if h.winner == "pursuer" else None


def first_threat(g, model, k_max):
    """g = 躲者回合開始（追者剛推完、滑完窗口）。之後追者都不推、躲者沒被威脅也不推：回傳第一個讓躲者模型判定
    受威脅的決策序號 k（0 = 就是這一回合），比賽先結束時回傳 ('end', winner)，k_max 內都沒有回傳 None。"""
    h = g.clone()
    h.history = []
    for k in range(k_max):
        if h.done:
            return ("end", h.winner)
        if model.threatened(h, "evader"):
            return k
        h.play_turn(np.zeros(3))
        if h.done:
            return ("end", h.winner)
        h.play_turn(np.zeros(3))
    return None


def cornered(g, model, n_tof=24):
    """g = 躲者回合開始。用躲者模型模擬它這回合的閃避，閃完後追者這個窗口內一發抓得到 → True。"""
    h = g.clone()
    h.history = []
    model.reset(seed=0)
    h.play_turn(h.clip_dv("evader", model.act(h, "evader")))
    if h.done:
        return h.winner == "pursuer"
    return window_capture(h, n_tof) is not None


class HarassPursuer(Agent):
    """燃料消耗戰追者（見模組說明）。model：躲者模型（要有 threatened(game) 與 act）。"""
    name = "harass_pursuer"

    def __init__(self, model="py:agents.evader_lab:LazyEvader3", k_max=10, lam_mps=15.0,
                 fracs=(0.1, 0.25, 0.5, 1.0), lam_scales=(1.0, 0.75, 0.5, 0.25), corner_top=6,
                 approach_revs=1, reserve_caps=1.0, reserve_mps=None, lam_clip=(5.0, 200.0),
                 finisher="lambert_pursuer", empty_mps=1.0):
        from agents import make_agent
        self.model = make_agent(model)
        self.k_max = int(k_max)
        self.lam_mps = lam_mps                         # 每多等一個躲者決策值多少 m/s；"adaptive" = 可用油 / 剩餘決策數
        # 留給收尾（躲者沒油後的攔截）的油：逼閃、接近的推力不能用掉這些。預設 = 1 發單發上限（250 級規則 250 m/s、
        # 對稱 1500 級規則 1500 m/s；固定 250 的話對稱規則下會把油燒光、收不了尾）；reserve_mps 給定時直接用它
        self.reserve_caps = float(reserve_caps)
        self.reserve_fixed = None if reserve_mps is None else float(reserve_mps)
        self.lam_clip = tuple(lam_clip)
        self.finisher = make_agent(finisher)           # 躲者沒油（≤ empty_mps）之後：純攔截
        self.empty_mps = float(empty_mps)
        self.fracs = tuple(fracs)
        self.lam_scales = tuple(lam_scales)
        self.corner_top = int(corner_top)
        self.approach_revs = int(approach_revs)
        self.dirs = _direction_set("full")
        self.log = []

    def reset(self, seed=None):
        self.model.reset(seed)
        self.finisher.reset(seed)
        self.log = []

    def reserve(self, game):
        if self.reserve_fixed is not None:
            return self.reserve_fixed
        return self.reserve_caps * game.rules.max_dv_pursuer_mps

    def lam(self, game):
        """等待一個躲者決策的代價（m/s）。adaptive：把可用的油平均攤到剩下的決策上——油多時願意花錢換快，
        時間多時願意等自然相對運動帶回來（要逼它閃 D 次時，每次可用 (油−保留)/D、可等 (決策數−2)/D，比值與 D 無關）。"""
        if self.lam_mps != "adaptive":
            return float(self.lam_mps)
        k_left = game.time_left / (2.0 * game.rules.window_sec)
        lam = (game.fuel_left("pursuer") - self.reserve(game)) / max(k_left - 2.0, 1.0)
        return float(np.clip(lam, *self.lam_clip))

    # ------------------------------------------------------------------ 候選
    def _tofs(self, game):
        w = game.next_window()
        W = game.rules.window_sec
        out = [w * f for f in (0.5, 1.0)]
        for k in range(min(self.k_max, 8)):
            base = w + W + 2 * W * k
            out += [base + x for x in (0.0, 120.0, 240.0, 360.0)]
        return [t for t in out if 10.0 <= t <= game.time_left]

    def spend_cap(self, game):
        """非捕獲用途（逼閃、接近）這一發最多推多少：單發上限，且推完要留 reserve(game)。"""
        return max(0.0, min(game.burn_cap("pursuer"), game.fuel_left("pursuer") - self.reserve(game)))

    def candidates(self, game):
        cap = self.spend_cap(game)
        cands = [np.zeros(3)]
        if cap <= 0.0:
            return cands
        for tof in self._tofs(game):
            dv = _lambert_dv(game, tof, shoot=False)
            if dv is None:
                continue
            for s in self.lam_scales:
                c = dv * s
                m = float(np.linalg.norm(c))
                cands.append(c * (cap / m) if m > cap else c)
        for d in self.dirs:
            for f in self.fracs:
                cands.append(rsw_to_eci_dv(game, "pursuer", d * f * cap))
        out = []
        for c in cands:
            if all(np.linalg.norm(c - o) > 0.5 for o in out):
                out.append(c)
        out.sort(key=lambda c: float(np.linalg.norm(c)))
        return out

    # ------------------------------------------------------------------ 決策
    def approach(self, game):
        """一圈（或剩餘時間）內「Δv + λ×等待」最小的單發攔截：推得完就推，推不完就推到可花的上限。"""
        cap = self.spend_cap(game)
        H = min(game.time_left, game.period("pursuer") * 1.0)
        if cap <= 0.0 or H <= 120.0:
            return np.zeros(3)
        R = game.rules
        n = int(np.clip(math.ceil(H / game.period("pursuer") * 48), 12, 96))
        tofs, dvs, v1s, _, _ = intercept_scan(game.mu, R.gravity_degree, game.r("pursuer"), game.v("pursuer"),
                                              game.r("evader"), game.v("evader"), 60.0, H, n, self.approach_revs,
                                              safe_radius(game))
        score = dvs * 1000.0 + self.lam(game) * tofs / (2.0 * R.window_sec)   # 跟威脅候選同一把尺：Δv + λ×等待
        if not np.any(np.isfinite(score)):
            return np.zeros(3)
        i = int(np.argmin(score))
        d = (v1s[i] - game.v("pursuer")) * 1000.0
        mag = float(np.linalg.norm(d))
        if mag > cap:
            d *= cap / mag
        for _ in range(6):
            if strict_survives(game, "pursuer", d):
                return d
            d = d * 0.5
        return np.zeros(3)

    def act(self, game, side):
        assert side == "pursuer"
        cap_dv = window_capture(game)
        if cap_dv is not None:
            self.log.append(("capture", game.t, float(np.linalg.norm(cap_dv))))
            return cap_dv
        if game.fuel_left("evader") <= self.empty_mps:  # 躲者沒油了：純攔截
            dv = self.finisher.act(game, side)
            self.log.append(("finish", game.t, float(np.linalg.norm(dv))))
            return dv
        lam = self.lam(game)
        best = (math.inf, None, None)
        immediate = []                                 # 讓躲者這回合就受威脅的候選（逼角檢查用）
        # 存活檢查用 strict_survives：orbit_survives 對「近地點在地底下」會漏判（seed 5 第 8 局實際撞地過）
        doomed = not strict_survives(game, "pursuer", np.zeros(3))
        for dv in self.candidates(game):
            mag = float(np.linalg.norm(dv))
            if mag >= best[0] and len(immediate) >= self.corner_top:
                break                                  # 依 Δv 排序：後面的只會更貴
            if (mag > 0.0 or doomed) and not strict_survives(game, "pursuer", dv):
                continue
            g = game.clone()
            g.history = []
            g.play_turn(dv)
            if g.done:
                if g.winner == "pursuer":
                    best = (mag - 1e6, dv, "capture")
                continue
            k = first_threat(g, self.model, self.k_max)
            if not isinstance(k, int):
                if isinstance(k, tuple) and k[1] == "pursuer" and mag < best[0]:
                    best = (mag, dv, "end")
                continue
            if k == 0 and len(immediate) < self.corner_top:
                immediate.append((mag, dv, g))
            s = mag + lam * k
            if s < best[0]:
                best = (s, dv, k)
        for mag, dv, g in immediate:                   # 逼角：閃完後抓得到
            if cornered(g, self.model):
                self.log.append(("corner", game.t, mag))
                return dv
        if best[1] is not None:
            self.log.append(("threat", game.t, float(np.linalg.norm(best[1])), best[2]))
            return best[1]
        if doomed:                                     # 連不推都會撞地、候選也救不回來
            rb = rescue_burn(game, "pursuer")
            if rb is not None:
                self.log.append(("rescue", game.t, float(np.linalg.norm(rb))))
                return rb
        dv = self.approach(game)
        self.log.append(("approach", game.t, float(np.linalg.norm(dv))))
        return dv


# ------------------------------------------------------------------ 偵測懶躲者的包裝

def evader_decisions(game):
    """從 game.history 重建躲者每個決策當下的局面：回傳 [(Game 快照, 躲者這回合推了多少 m/s)]。"""
    from game.core import Game
    out = []
    used = {"pursuer": 0.0, "evader": 0.0}
    prev = None
    for rec in game.history:
        if rec["side"] == "evader":
            if prev is None:
                rp, vp = game.initial["pursuer"]
            else:
                rp, vp = prev["rp_after"], prev["vp_after"]
            g = Game.from_snapshot(game.rules, rp, vp, rec["r_before"], rec["v_before"], t=rec["t"],
                                   t_max=game.t_max, used=dict(used), mover="evader", mu=game.mu)
            out.append((g, float(rec["dv_mps"])))
        used[rec["side"]] += float(rec["dv_mps"])
        prev = rec
    return out


class LazyHunter(Agent):
    """偵測「受威脅才閃」的躲者，偵測到才改打燃料消耗戰；否則跟 active（預設 rollout 追者）逐步相同。

    每個躲者決策用兩把尺檢查（都只看當時的局面）：嚴格 = 躲者模型自己的威脅測試（LazyEvader3：40 m/s、60 s）；
    寬鬆 = probe（150 m/s、300 s）。
      * 吻合：推了且嚴格判定受威脅，或沒推且嚴格判定沒受威脅；
      * 不吻合：嚴格判定受威脅卻沒推（真的 LazyEvader3 不會這樣）；
      * 主動：寬鬆都判定沒受威脅卻推了（rollout_evader、dv_evader 第一、二個決策就會這樣）。
    吻合 ≥ n_lazy 次、而且還沒出現過不吻合或主動 → 換成 HarassPursuer；之後只要出現主動，永遠換回 active。
    （不吻合只擋「換過去」：換過去之後門檻較緊的懶躲者變體也會有不吻合，仍然當懶躲者打。）"""
    name = "lazy_hunter"

    def __init__(self, active="rollout_pursuer", harass=None, n_lazy=2, burn_eps_mps=5.0,
                 probe=None):
        from agents import make_agent
        self.active = make_agent(active)
        self.harass = HarassPursuer(**(harass or {}))
        self.probe = make_agent(probe or {"name": "py:agents.evader_lab:LazyEvader3", "margin_mps": 150.0,
                                          "slack_sec": 300.0})
        self.n_lazy = int(n_lazy)
        self.burn_eps = float(burn_eps_mps)
        self.reset()

    def reset(self, seed=None):
        self.active.reset(seed)
        self.harass.reset(seed)
        self.mode = "active"
        self._seen = 0
        self.counts = {"match": 0, "mismatch": 0, "active": 0}
        self.switches = []

    def _update(self, game):
        decs = evader_decisions(game)
        for g, dv in decs[self._seen:]:
            burned = dv > self.burn_eps
            strict = self.harass.model.threatened(g, "evader")
            if burned == strict:
                self.counts["match"] += 1
            elif strict:
                self.counts["mismatch"] += 1
            elif not self.probe.threatened(g, "evader"):
                self.counts["active"] += 1
        self._seen = len(decs)
        c = self.counts
        if c["active"] > 0:
            mode = "active"
        elif self.mode == "harass":
            mode = "harass"
        elif c["mismatch"] == 0 and c["match"] >= self.n_lazy:
            mode = "harass"
        else:
            mode = "active"
        if mode != self.mode:
            self.switches.append((game.t, mode))
            self.mode = mode

    def act(self, game, side):
        assert side == "pursuer"
        if not game.mid_window:
            self._update(game)
        return (self.harass if self.mode == "harass" else self.active).act(game, side)
