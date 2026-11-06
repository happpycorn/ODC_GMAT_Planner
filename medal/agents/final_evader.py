"""金／銅牌賽的安全證書躲方與直覺躲方。

幾何計算採二體近似；規則若啟用非零重力階數，證書也只是二體近似。
"""
import math
import time

import numpy as np

from agents.base import Agent
from agents.final_common import (direction_set, dsma_capacity, dsma_capacity_worst, exact_miss, kepler, linear_margins_batch,
                                 make_reach, perigee_alt_km, round_context, sma_after, zone_slack)
from game.core import sma_official
from physics import EARTH_MU
from physics.frames import rsw_basis


def _zone_distance(a, zone):
    """半長軸離安全區間的距離。"""
    if zone is None:
        return 0.0
    if not math.isfinite(a):
        return math.inf
    return max(zone[0] - a, a - zone[1], 0.0)


class SafeEvader(Agent):
    """以追方單發可達集合挑閃避脈衝，再用非線性二體傳播驗證。"""

    name = "safe_evader"
    simultaneous_aware = True

    def __init__(self, n_dirs=150, mags=(0.5, 1.0), safety_km=2.0, grid_sec=5.0,
                 perigee_margin_km=30.0, near_opt_tol=0.05, n_verify=10, lookahead=True, seed=None,
                 zone_dirs=60):
        self.n_dirs = int(n_dirs)
        # 安全空域很窄時（E29：寬 0.02 發容量 ≈ 14 km），固定的 {0.5, 1}×上限推不進去；每回合另外列 zone_dirs 個方向
        # 「推完 a 剛好在區間中心」的大小（二分），讓躲方能精準入區、也能提早入區保留閃避空間。0 = 關閉（舊行為）。
        self.zone_dirs = int(zone_dirs)
        self.mags = tuple(float(x) for x in mags)
        self.safety_km = float(safety_km)
        self.grid_sec = float(grid_sec)
        self.perigee_margin_km = float(perigee_margin_km)
        self.near_opt_tol = float(near_opt_tol)
        self.n_verify = int(n_verify)
        self.lookahead = bool(lookahead)
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.last_info = {}
        self.history_info = []
        self._last_reach = None

    def reset(self, seed=None):
        """重設抽籤序列與每局紀錄。"""
        self.rng = np.random.default_rng(self.seed if seed is None else seed)
        self.last_info = {}
        self.history_info = []
        self._last_reach = None

    def _taus(self, T, grid_sec=None):
        """建立含起點極限與窗口終點的時間網格。"""
        h = self.grid_sec if grid_sec is None else grid_sec
        if T <= 0.0:
            return np.array([0.0])
        return np.r_[0.0, np.arange(h, T, h), T].astype(np.float64)

    def _candidates(self, r, v, D, zone=None):
        """零推與 Fibonacci 球面、RSW 六軸的所有指定推力大小；有安全空域時再加「推完 a 剛好落在區間中心」的候選。"""
        dirs = direction_set(self.n_dirs, r, v)
        pieces = [np.zeros((1, 3), dtype=np.float64)]
        for mag in self.mags:
            if mag > 0.0:
                pieces.append(np.asarray(dirs, dtype=np.float64) * (mag * D))
        if zone is not None and self.zone_dirs > 0 and D > 0.0:
            landing = _zone_landing(r, v, D, zone, direction_set(self.zone_dirs, r, v))
            if len(landing):
                pieces.append(landing)
        return np.concatenate(pieces, axis=0)

    def _lookahead_scores(self, game, rows, ctx):
        """假設追方本回合純滑行，粗估前段候選下一回合的最佳閃避。"""
        if not self.lookahead or ctx["burns_left_after"] <= 0 or ctx["T"] <= 0.0:
            return
        selected = [i for i, row in enumerate(rows) if row["feasible"] and row["safe"]]
        if not selected:
            return
        selected.sort(key=lambda i: rows[i]["score"], reverse=True)
        selected = selected[:15]
        T = ctx["T"]
        rp_next, vp_next = kepler(game.r("pursuer"), game.v("pursuer"), T, game.mu)
        taus = self._taus(T, max(self.grid_sec, 30.0))
        reach_next = make_reach(rp_next, vp_next, ctx["D_p"], taus, game.mu)
        D = ctx["D_e"]
        for i in selected:
            row = rows[i]
            re_next, ve_next = kepler(game.r("evader"), game.v("evader") + row["dv_eci_mps"] / 1000.0,
                                      T, game.mu)
            dirs = direction_set(20, re_next, ve_next)
            coarse = dirs * D
            if D <= 0.0:
                coarse = np.zeros((1, 3), dtype=np.float64)
            margins, _ = linear_margins_batch(reach_next, re_next, ve_next, coarse, ctx["R_cap"], refine=False)
            best = float(np.max(margins))
            scale = 3.0 * ctx["R_cap"] + 20.0
            row["score"] += 0.20 * float(np.clip(best / scale, 0.0, 1.0))

    def evaluate(self, game) -> list[dict]:
        """評估每個候選的硬條件、線性安全餘量與分數；不改動賽局。"""
        ctx = round_context(game)
        re, ve = game.r("evader"), game.v("evader")
        rp, vp = game.r("pursuer"), game.v("pursuer")
        D = ctx["D_e"]
        dvs = self._candidates(re, ve, D, ctx["zone"])
        zone = ctx["zone"]
        n_after = ctx["burns_left_after"]
        perigees = np.empty(len(dvs), dtype=np.float64)
        axes = np.empty(len(dvs), dtype=np.float64)
        ups = np.zeros(len(dvs), dtype=np.float64)
        downs = np.zeros(len(dvs), dtype=np.float64)
        slacks = np.full(len(dvs), math.inf, dtype=np.float64)
        zone_dists = np.zeros(len(dvs), dtype=np.float64)
        for i, dv in enumerate(dvs):
            vv = ve + dv / 1000.0
            perigees[i] = perigee_alt_km(re, vv)
            axes[i] = sma_after(re, ve, dv / 1000.0)
            if zone is not None:
                ups[i], downs[i] = dsma_capacity_worst(re, vv, D)   # 之後可能在遠地點出手（E29）
                slacks[i] = zone_slack(axes[i], zone, n_after, ups[i], downs[i])
                zone_dists[i] = _zone_distance(axes[i], zone)

        peri_ok = perigees >= self.perigee_margin_km
        if not np.any(peri_ok):
            peri_ok = perigees >= float(np.max(perigees)) - 1e-9
        feasible = peri_ok.copy()
        if zone is not None:
            zone_ok = feasible & (slacks >= -1e-9)
            if np.any(zone_ok):
                feasible = zone_ok
            else:
                best = float(np.min(zone_dists[feasible]))
                feasible &= zone_dists <= best + 5.0 + 1e-9

        # 追方可達集合只建一次；批次掃過全部躲方候選。
        reach = make_reach(rp, vp, ctx["D_p"], self._taus(ctx["T"]), game.mu)
        self._last_reach = reach
        margins, _ = linear_margins_batch(reach, re, ve, dvs, ctx["R_cap"], refine=True)
        rows = []
        cap_score = 3.0 * ctx["R_cap"] + 20.0
        zone_center = 0.0 if zone is None else 0.5 * (zone[0] + zone[1])
        for i, dv in enumerate(dvs):
            margin = float(margins[i])
            safe = bool(feasible[i] and margin > self.safety_km)
            margin_score = float(np.clip(margin / cap_score, 0.0, 1.0))
            score = 0.65 * margin_score
            if zone is not None:
                cap_ref = max(ups[i], downs[i])
                if not math.isfinite(cap_ref):
                    cap_ref = max(1.0, zone[1] - zone[0], 0.1 * abs(zone_center))
                scale = max(1.0, (n_after + 1) * cap_ref)
                slack_score = float(np.clip(slacks[i] / scale, 0.0, 1.0))
                score += 0.20 * slack_score
                if n_after <= 1:
                    center_scale = max(1.0, 0.5 * (zone[1] - zone[0]) + 0.25 * cap_ref)
                    score += 0.15 * float(np.clip(1.0 - abs(axes[i] - zone_center) / center_scale, 0.0, 1.0))
            score -= 1e-5 * float(np.linalg.norm(dv)) / max(D, 1.0)
            rows.append({"dv_eci_mps": dv.copy(), "linear_margin_km": margin,
                         "feasible": bool(feasible[i]), "safe": safe, "score": score,
                         "zone_slack_km": float(slacks[i]), "a_after_km": float(axes[i])})
        self._lookahead_scores(game, rows, ctx)
        return rows

    def act(self, game, side):
        """從高分安全候選隨機挑選，逐一做非線性最佳回應驗證。"""
        if side != "evader":
            raise ValueError("SafeEvader 只能擔任 evader")
        start = time.perf_counter()
        ctx = round_context(game)
        rows = self.evaluate(game)
        safe = [i for i, row in enumerate(rows) if row["safe"]]
        tried = set()
        exact_by_index = {}
        selected = None
        certified = False
        while safe and len(tried) < self.n_verify:
            best = max(rows[i]["score"] for i in safe)
            near = [i for i in safe if rows[i]["score"] >= best - self.near_opt_tol]
            i = int(self.rng.choice(near))
            row = rows[i]
            dv = row["dv_eci_mps"]
            miss, _, _ = exact_miss(game.r("pursuer"), game.v("pursuer"), ctx["D_p"],
                                    game.r("evader"), game.v("evader") + dv / 1000.0, ctx["T"], game.mu,
                                    grid_sec=self.grid_sec, reach_p=self._last_reach)
            exact_by_index[i] = float(miss - ctx["R_cap"])
            tried.add(i)
            if exact_by_index[i] > self.safety_km:
                selected = i
                certified = True
                break
            safe.remove(i)
        if selected is None:
            feasible = [i for i, row in enumerate(rows) if row["feasible"]]
            selected = max(feasible, key=lambda i: exact_by_index.get(i, rows[i]["linear_margin_km"]))

        row = rows[selected]
        dv = row["dv_eci_mps"].copy()
        info = {"round": ctx["round"], "n_cands": len(rows),
                "n_feasible": sum(x["feasible"] for x in rows), "n_safe": sum(x["safe"] for x in rows),
                "certificate": certified, "linear_margin_km": row["linear_margin_km"],
                "exact_margin_km": exact_by_index.get(selected, math.nan), "zone_slack_km": row["zone_slack_km"],
                "a_after_km": row["a_after_km"], "dv_mps": float(np.linalg.norm(dv)),
                "time_s": time.perf_counter() - start}
        self.last_info = info
        self.history_info.append(info.copy())
        return dv


def _zone_landing(r, v, D, zone, dirs):
    """每個方向上「推完 a 剛好是區間中心」的推力（m/s，大小 ≤ D）；到不了的方向略過。

    沿固定方向 d 推 m，|v + m·d|² 在 m ≤ D（≪ 軌道速度）內單調，所以 1/a 單調、二分即可。"""
    lo_z, hi_z = zone
    xt = 1.0 / (0.5 * (lo_z + hi_z))
    rn = float(np.linalg.norm(r))
    D_kms = D / 1000.0
    out = []
    for d in dirs:
        def recip(m):
            w = v + d * m
            return 2.0 / rn - float(w @ w) / EARTH_MU
        x0, x1 = recip(0.0), recip(D_kms)
        if not (min(x0, x1) <= xt <= max(x0, x1)) or x0 == xt:
            continue
        lo, hi = 0.0, D_kms
        for _ in range(48):
            mid = 0.5 * (lo + hi)
            if (recip(mid) - xt) * (x0 - xt) > 0.0:
                lo = mid
            else:
                hi = mid
        out.append(d * (0.5 * (lo + hi) * 1000.0))
    return np.asarray(out, dtype=np.float64).reshape(-1, 3)


def _zone_burn(r, v, zone, D):
    """以半長軸倒數二分推力，跨越拋物線時仍可瞄準區間中心。"""
    a = sma_official(r, v)
    if zone is None or zone[0] <= a <= zone[1] or D <= 0.0:
        return None
    target = 0.5 * (zone[0] + zone[1])
    if target == 0.0:
        target = zone[1] if zone[1] > 0.0 else zone[0]
    x0 = 2.0 / np.linalg.norm(r) - float(v @ v) / EARTH_MU
    xt = 1.0 / target
    sign = 1.0 if xt < x0 else -1.0
    direction = sign * v / np.linalg.norm(v)
    def reciprocal(mag):
        w = v + direction * (mag / 1000.0)
        return 2.0 / np.linalg.norm(r) - float(w @ w) / EARTH_MU
    xf = reciprocal(D)
    reached = (min(x0, xf) <= xt <= max(x0, xf))
    if not reached:
        return direction * D
    lo, hi = 0.0, D
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        xm = reciprocal(mid)
        if (xm > xt) == (sign > 0.0):
            lo = mid
        else:
            hi = mid
    return direction * (0.5 * (lo + hi))


def heuristic_candidates(game, side="evader") -> list[tuple[str, np.ndarray, float]]:
    """列出人類直覺閃法；權重只在合法且近地點安全的項目間正規化。"""
    r, v = game.r(side), game.v(side)
    other = "pursuer" if side == "evader" else "evader"
    D = game.burn_cap(side)
    basis = rsw_basis(r, v)
    away = r - game.r(other)
    away_norm = float(np.linalg.norm(away))
    if away_norm <= 1e-12:
        away = basis[0].copy()
    else:
        away = away / away_norm
    raw = [("away", away * D, 0.25), ("normal+", basis[2] * D, 0.10),
           ("normal-", -basis[2] * D, 0.10), ("radial+", basis[0] * D, 0.05),
           ("radial-", -basis[0] * D, 0.05)]
    zone = game.rules.safe_sma_km
    if zone is not None:
        dv_zone = _zone_burn(r, v, zone, D)
        if dv_zone is not None:
            raw.append(("zone", dv_zone, 0.30))
    raw.append(("zero", np.zeros(3), 0.15))
    kept = [(name, np.asarray(dv, dtype=np.float64), weight) for name, dv, weight in raw
            if perigee_alt_km(r, v + dv / 1000.0) >= 30.0]
    if not kept:
        return []
    if zone is not None and any(name == "zone" for name, _, _ in kept):
        ctx = round_context(game)
        a = sma_official(r, v)
        up, down = dsma_capacity(r, v, D)
        n_burns = ctx["burns_left_after"] + 1
        cap_one = up if a < zone[0] else down
        pressure = zone_slack(a, zone, n_burns, up, down) < cap_one
        final_reachable = n_burns == 1 and zone[0] <= sma_after(r, v, next(dv for name, dv, _ in kept
                                                                              if name == "zone") / 1000.0) <= zone[1]
        if final_reachable:
            kept = [(name, dv, 1.0) for name, dv, _ in kept if name == "zone"]
        elif pressure and len(kept) > 1:
            other_sum = sum(w for name, _, w in kept if name != "zone")
            kept = [(name, dv, 0.8 if name == "zone" else 0.2 * w / other_sum)
                    for name, dv, w in kept]
    total = sum(weight for _, _, weight in kept)
    return [(name, dv, weight / total) for name, dv, weight in kept]


class HeuristicEvader(Agent):
    """依直覺閃法的權重隨機挑選一發。"""

    name = "heuristic_evader"
    simultaneous_aware = True

    def __init__(self, seed=None):
        self.seed = seed
        self.rng = np.random.default_rng(seed)

    def reset(self, seed=None):
        """每局重設隨機序列。"""
        self.rng = np.random.default_rng(self.seed if seed is None else seed)

    def act(self, game, side):
        """按權重抽一個近地點安全的脈衝。"""
        rows = heuristic_candidates(game, side)
        if not rows:
            return np.zeros(3)
        index = int(self.rng.choice(len(rows), p=[row[2] for row in rows]))
        return rows[index][1].copy()
