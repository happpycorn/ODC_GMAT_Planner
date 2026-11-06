"""躲者打法實驗室（研究筆記 docs/notes/evader_improvement.md）。

診斷（排位版規則 250/3000、seed 1、24 局）：強化版 rollout 追者抓到 rollout 躲者的 17 局裡，躲者**全部**
把 3000 m/s 用光，被抓的時刻都在後段（t ≈ 20,000–27,000 s，T_max ≈ 23,000–27,000 s）。躲者前段幾乎
每回合推滿 250 m/s——推演勝局的 tie-break 偏好「終局距離遠」，續行 dv_evader_fast 也幾乎每回合推，
所以推演看不出「留油」的價值；燃料先燒完，有耐心的追者再用剩下的油慢慢收網。

這裡的躲者（都用 `py:agents.evader_lab:<類別>` 規格引用，不改既有程式）：

* LazyEvader —— 平常不推；只有「我這回合滑行完，追者下一回合一發就能在窗口內（含一點寬限）抓到」
  或「我這個窗口內就會被抓」時才閃，閃法 = DvEvader。省油、讓追者先出手。
* LazyEvader2 —— LazyEvader 補上窗口邊界的盲點（純滑行交會落在追者窗口最開始幾秒時看不到），
  閃避時優先選推完就沒有這種威脅的候選。
* LazyEvader3 —— LazyEvader2 + 嚴格的存活檢查（strict_survives：近地點在地底下的軌跡，還沒到近地點就先撞地，
  orbit_survives 會漏判；對稱規則下大推力閃避在比賽尾聲踩過）。**建議用這個。**
* ReserveRolloutEvader —— RolloutPlanner（躲者）：推演的續行換成 LazyEvader、勝局分數改成燃料戰
  餘裕（自己剩油多、追者用油多、未來最近距離大），候選多 DvEvader 解的縮小版（0.5×、0.25×）。
  對手模型維持預設 Lambert 系（E19：換更強的對手模型反而變差）。
"""
import math

import numpy as np

from agents.analytic import (SAFETY_MARGIN_KM, DvEvader, need_horizon, orbit_survives, pursuer_need,
                             rescue_burn)
from agents.base import rsw_to_eci_dv
from agents.rollout import RolloutPlanner, _pool, _worker_agent, outcome_score
from game.core import take_turn
from physics.coast import closest_approach
from physics.core_math import check_constraints
from physics.intercept import min_intercept
from physics.propagator import propagate


def inwindow_need(game, slack_sec=60.0, n_tof=12):
    """追者此刻一發、在這個窗口內（再加 slack 秒寬限）攔截躲者所需的最小 Δv（m/s）。

    寬限是為了「轉移時間剛好比窗口長一點」的攔截：交會發生在躲者窗口剛開始，躲者推了也來不及閃。"""
    R = game.rules
    hi = min(game.next_window() + slack_sec, game.time_left)
    if hi <= 15.0:
        return math.inf
    dv, _, _ = min_intercept(game.mu, R.gravity_degree, game.r("pursuer"), game.v("pursuer"),
                             game.r("evader"), game.v("evader"), 10.0, hi, n_tof, 0, game.crash_radius, 1, 8)
    return float(dv) * 1000.0


def pursuer_reach_cap(game):
    """追者下一個回合最多能推多少（多發規則下整個窗口加總，保守估計）。"""
    R = game.rules
    return min(game.fuel_left("pursuer"), R.max_dv_pursuer_mps * max(1, R.burns_per_turn))


class LazyEvader(DvEvader):
    """平常不推，受威脅才閃（閃法 = DvEvader 的候選與評分）。

    威脅：(1) 不推的話軌道撐不到比賽結束；(2) 不推的話這個窗口內就被抓；(3) 不推的話，下一回合追者
    在窗口內（+slack）攔截所需 Δv ≤ 追者可用推力 + margin；(4)（可選）短 horizon 的追擊所需 Δv
    < need_gate_mps。"""
    name = "lazy_evader"

    def __init__(self, margin_mps=40.0, slack_sec=60.0, need_gate_mps=0.0, directions="full", mags=(1.0, 0.4),
                 **kw):
        super().__init__(directions=directions, mags=mags, **kw)
        self.margin_mps = float(margin_mps)
        self.slack_sec = float(slack_sec)
        self.need_gate_mps = float(need_gate_mps)
        self.name = "lazy_evader"

    def threatened(self, game, side="evader"):
        if not orbit_survives(game, side, np.zeros(3)):
            return True
        g = game.clone()
        g.history = []
        g.play_turn(np.zeros(3))
        if g.done:
            return g.winner == "pursuer"
        cap = pursuer_reach_cap(g)
        if cap <= 0.0:
            return False
        if inwindow_need(g, self.slack_sec) <= cap + self.margin_mps:
            return True
        if self.need_gate_mps > 0.0:
            need, _ = pursuer_need(g, horizon=need_horizon(g, self.horizon_windows), max_revs=self.max_revs,
                                   pts_per_period=16, n_refine=1)
            if need < self.need_gate_mps:
                return True
        return False

    def act(self, game, side):
        assert side == "evader"
        if game.burn_cap(side) <= 0.0 or not self.threatened(game, side):
            return np.zeros(3)
        return super().act(game, side)


def coast_threat(game, cap_mps, margin_mps=40.0, slack_sec=60.0, substep=20.0):
    """game = 追者回合開始的狀態。雙方都滑行時，追者窗口（+slack）內的最近接近 d（時刻 t）若
    ≤ 捕獲半徑 + (cap+margin)·t，追者這回合推一發（甚至不推）就能進捕獲球。補 inwindow_need 的盲點：
    交會時間很短（< 10 s，或捕獲半徑相對 TOF 很大）時，「精確攔截所需 Δv」會嚴重高估。"""
    R = game.rules
    H = min(game.next_window() + slack_sec, game.time_left)
    if H <= 0.0:
        return False
    d, t, _ = closest_approach(game.r("pursuer"), game.v("pursuer"), game.r("evader"), game.v("evader"),
                               H, substep, game.mu, R.gravity_degree)
    reach = (cap_mps + margin_mps) if cap_mps > 0.0 else 0.0
    return d <= R.capture_radius_km + reach * t / 1000.0


class LazyEvader2(LazyEvader):
    """LazyEvader + 補窗口邊界的盲點。

    診斷（seed 1 第 21 局，反制追者 = rollout 追者、對手模型 LazyEvader）：雙方純滑行、相對速度 ~6.5 km/s，
    交會落在追者窗口開始後 6 s。LazyEvader 的窗口內 Lambert 掃描從 TOF 10 s 起、DvEvader 的評分從 TOF 60 s
    起，都看不到 → 一滴油都沒用就被抓。修正：(1) 威脅多一條 coast_threat；(2) 閃避時推完仍有
    coast_threat 的候選重罰（優先選推完就安全的），其餘照 DvEvader 評分。"""
    name = "lazy_evader2"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.name = "lazy_evader2"

    def _survives(self, game, side, dv):
        return orbit_survives(game, side, dv)

    def _post_threat(self, g):
        """g = 我這回合推完（或不推）滑完窗口、追者回合開始的狀態。"""
        if g.done:
            return g.winner == "pursuer"
        cap = pursuer_reach_cap(g)
        if coast_threat(g, cap, self.margin_mps, self.slack_sec):
            return True
        if cap <= 0.0:
            return False
        if inwindow_need(g, self.slack_sec) <= cap + self.margin_mps:
            return True
        if self.need_gate_mps > 0.0:
            need, _ = pursuer_need(g, horizon=need_horizon(g, self.horizon_windows), max_revs=self.max_revs,
                                   pts_per_period=16, n_refine=1)
            return need < self.need_gate_mps
        return False

    def threatened(self, game, side="evader"):
        if not self._survives(game, side, np.zeros(3)):
            return True
        g = game.clone()
        g.history = []
        g.play_turn(np.zeros(3))
        return self._post_threat(g)

    def act(self, game, side):
        assert side == "evader"
        cap = game.burn_cap(side)
        if cap <= 0.0 or not self.threatened(game, side):
            return np.zeros(3)
        doomed = not self._survives(game, side, np.zeros(3))
        best = (-math.inf, np.zeros(3))
        cands = [np.zeros(3)] + [d * m * cap for d in self.dirs for m in self.mags]
        for k, dv_rsw in enumerate(cands):
            dv = rsw_to_eci_dv(game, side, dv_rsw)
            if (k > 0 or doomed) and not self._survives(game, side, dv):
                continue
            g = game.clone()
            g.history = []
            g.play_turn(dv)
            s = self._score(g, float(np.linalg.norm(dv_rsw)))
            if not g.done and coast_threat(g, pursuer_reach_cap(g), self.margin_mps, self.slack_sec):
                s -= 1e7
            if s > best[0]:
                best = (s, dv)
        if best[0] == -math.inf and doomed:
            rb = rescue_burn(game, side)
            return rb if rb is not None else np.zeros(3)
        return best[1]


def strict_survives(game, side, dv_eci_mps, margin_km=SAFETY_MARGIN_KM, floor_km=10.0, step_sec=60.0):
    """比 orbit_survives 嚴：近地點低於「撞地高度 + margin」時不看「二體近地點時刻在不在比賽結束後」，而是實際
    （J2）推到比賽結束 + 300 s，任何取樣點低於撞地半徑 + floor_km 就算不安全。

    orbit_survives 對「近地點在地底下」的軌跡會漏判：還沒到近地點就先撞地（對稱規則 seed 1 第 3 局：剩 1,350 s 時
    往下 + 往後推 1500 m/s，近地點在地表下 2,000 km、近地點時刻在比賽結束後，783 s 後撞地）。"""
    r = game.r(side)
    v = game.v(side) + np.asarray(dv_eci_mps, dtype=np.float64) / 1000.0
    if check_constraints(r, v, game.mu, game.crash_radius + margin_km):
        return True
    lim = game.crash_radius + floor_km
    t_end, t = game.time_left + 300.0, 0.0
    while t < t_end:
        dt = min(step_sec, t_end - t)
        r, v = propagate(game.mu, r, v, dt, game.rules.gravity_degree)
        t += dt
        if float(np.linalg.norm(r)) < lim:
            return False
    return True


class LazyEvader3(LazyEvader2):
    """LazyEvader2 + 嚴格的存活檢查（strict_survives）：閃避候選與「不推會不會撞地」都用實際推進判斷。"""
    name = "lazy_evader3"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.name = "lazy_evader3"

    def _survives(self, game, side, dv):
        return strict_survives(game, side, dv)


# ------------------------------------------------------------------ 推演：燃料戰餘裕分數
def fuelwar_score(h, side, w_own=100.0, w_opp=100.0, w_margin=20.0, margin_cap_km=100.0):
    """躲者視角。贏：1000 + 自己剩油比例×w_own + 追者已用油比例×w_opp + 未來最近距離（封頂）×w_margin；
    輸：同預設（撐越久越好）。h.min_dist 必須是推演開始後才累計的最近距離。"""
    if side != "evader":
        return outcome_score(h, side)
    R = h.rules
    if h.winner == "evader":
        fe = h.fuel_left("evader") / max(R.fuel_evader_mps, 1.0)
        fp = h.fuel_left("pursuer") / max(R.fuel_pursuer_mps, 1.0)
        md = min(h.min_dist, margin_cap_km) / margin_cap_km
        return 1000.0 + w_own * fe + w_opp * (1.0 - fp) + w_margin * md
    return 500.0 * h.t / h.t_max


def lab_play_out(game, dv, side, cont, opp, score="fuelwar"):
    """同 agents.rollout.play_out，但最近距離從推演開始重新累計、分數可選 fuelwar。"""
    opp.reset(seed=0)
    h = game.clone()
    h.history = []
    h.min_dist = h.distance()
    take_turn(h, cont, first_dv=dv)
    while not h.done:
        take_turn(h, cont if h.mover == side else opp)
    return outcome_score(h, side) if score == "default" else fuelwar_score(h, side)


def _lab_task(args):
    game, dv, side, cont_spec, opp_spec, score = args
    return lab_play_out(game, dv, side, _worker_agent(cont_spec), _worker_agent(opp_spec), score)


class ReserveRolloutEvader(RolloutPlanner):
    """rollout 躲者 + 省油：續行 LazyEvader、勝局分數看燃料戰餘裕、候選多縮小版的閃避。"""

    def __init__(self, candidates=None, opponents=None, continuation="py:agents.evader_lab:LazyEvader",
                 scales=(0.5, 0.25), score="fuelwar", workers=0, name="reserve_rollout_evader", **kw):
        super().__init__("evader", candidates=candidates, opponents=opponents, continuation=continuation,
                         workers=workers, name=name, **kw)
        self.scales = tuple(scales)
        self.score = score

    def _candidates(self, game):
        base = super()._candidates(game)          # [0, 各候選 agent 的輸出, extra_rsw_fracs]（已去重）
        out = []
        for c in base + [c * s for c in base[1:] for s in self.scales]:
            if all(np.linalg.norm(c - o) > 0.5 for o in out):
                out.append(c)
        return out

    def evaluate(self, game, side):
        cands = self._candidates(game)
        if self.workers > 1:
            g = game.clone()
            g.history = []
            tasks = [(g, dv, side, self.cont_spec, o, self.score) for dv in cands for o in self.opp_specs]
            flat = list(_pool(self.workers).map(_lab_task, tasks))
            k = len(self.opp_specs)
            return [(dv, flat[i * k:(i + 1) * k]) for i, dv in enumerate(cands)]
        return [(dv, [lab_play_out(game, dv, side, self.cont, o, self.score) for o in self.opp_agents])
                for dv in cands]
