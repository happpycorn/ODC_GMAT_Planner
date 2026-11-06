"""金／銅牌賽的同時出手攔截追方。

用躲方可能的一發建立加權模型，再以二體全窗口最近距離挑追方推力。
規則若啟用高階重力，本模組的預測仍是二體近似。
"""
import math
import time

import numpy as np
from numba import njit

from agents.base import Agent
from agents.final_common import (direction_set, dsma_capacity, exact_miss, kepler, kepler_grid,
                                 linear_margin, make_reach, perigee_alt_km, round_context,
                                 sma_after, time_grid, zone_slack)
from agents.final_evader import SafeEvader, heuristic_candidates
from physics.lambert import lambert_min_dv


@njit(cache=True)
def _distance2_at(rp, vp, re, ve, tau, mu):
    """在指定時刻重傳播兩條軌道，供最近點精修。"""
    p, _ = kepler(rp, vp, tau, mu)
    e, _ = kepler(re, ve, tau, mu)
    d = p - e
    return d[0] * d[0] + d[1] * d[1] + d[2] * d[2]


@njit(cache=True)
def _miss_matrix(rp, vp_burn, re, ve_burn, p_tracks, e_tracks, taus, mu):
    """每一對推力先掃全窗口網格，再精修最小值附近的連續時刻。"""
    out = np.empty((len(vp_burn), len(ve_burn)), dtype=np.float64)
    q = 0.6180339887498949
    for i in range(len(vp_burn)):
        for j in range(len(ve_burn)):
            best = math.inf
            best_k = 0
            for k in range(len(taus)):
                dx = p_tracks[i, k, 0] - e_tracks[j, k, 0]
                dy = p_tracks[i, k, 1] - e_tracks[j, k, 1]
                dz = p_tracks[i, k, 2] - e_tracks[j, k, 2]
                d2 = dx * dx + dy * dy + dz * dz
                if d2 < best:
                    best = d2
                    best_k = k
            if len(taus) > 1:
                lo = taus[max(0, best_k - 1)]
                hi = taus[min(len(taus) - 1, best_k + 1)]
                if hi > lo:
                    x1 = hi - q * (hi - lo)
                    x2 = lo + q * (hi - lo)
                    f1 = _distance2_at(rp, vp_burn[i], re, ve_burn[j], x1, mu)
                    f2 = _distance2_at(rp, vp_burn[i], re, ve_burn[j], x2, mu)
                    for _ in range(18):
                        if f1 <= f2:
                            hi = x2
                            x2 = x1
                            f2 = f1
                            x1 = hi - q * (hi - lo)
                            f1 = _distance2_at(rp, vp_burn[i], re, ve_burn[j], x1, mu)
                        else:
                            lo = x1
                            x1 = x2
                            f1 = f2
                            x2 = lo + q * (hi - lo)
                            f2 = _distance2_at(rp, vp_burn[i], re, ve_burn[j], x2, mu)
                    best = min(best, f1, f2)
            out[i, j] = math.sqrt(best)
    return out


class CapturePursuer(Agent):
    """以躲方加權推力模型最大化本回合捕獲機率。"""

    name = "capture_pursuer"
    simultaneous_aware = True

    def __init__(self, n_dirs=100, mags=(0.5, 1.0),
                 lambert_fracs=(0.05, 0.1, 0.2, 0.3, 0.45, 0.6, 0.8, 1.0),
                 max_model=30, w_zero=0.1, w_heuristic=0.4, w_safe=0.5,
                 hit_margin_km=0.2, grid_sec=5.0, perigee_margin_km=30.0,
                 lookahead=True, model_evader=None, seed=None):
        self.n_dirs = int(n_dirs)
        self.mags = tuple(float(x) for x in mags)
        self.lambert_fracs = tuple(float(x) for x in lambert_fracs)
        self.max_model = int(max_model)
        self.w_zero = float(w_zero)
        self.w_heuristic = float(w_heuristic)
        self.w_safe = float(w_safe)
        self.hit_margin_km = float(hit_margin_km)
        self.grid_sec = float(grid_sec)
        self.perigee_margin_km = float(perigee_margin_km)
        self.lookahead = bool(lookahead)
        self.model_evader = ({"n_dirs": 60, "mags": (1.0,), "grid_sec": 10.0,
                              "lookahead": False} if model_evader is None else dict(model_evader))
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.last_info = {}
        self.history_info = []

    def reset(self, seed=None):
        """重設模型抽樣序列及整局診斷紀錄。"""
        self.rng = np.random.default_rng(self.seed if seed is None else seed)
        self.last_info = {}
        self.history_info = []

    def _evader_model(self, game):
        """合併同一推力的來源，回傳權重和為一的躲方候選。"""
        ctx = round_context(game)
        re, ve = game.r("evader"), game.v("evader")
        raw = []
        if self.w_zero > 0.0:
            raw.append(("zero", np.zeros(3), self.w_zero, None))
        if self.w_heuristic > 0.0:
            for name, dv, weight in heuristic_candidates(game):
                raw.append((name, dv, self.w_heuristic * weight, None))
        if self.w_safe > 0.0:
            rows = SafeEvader(**self.model_evader).evaluate(game.clone())
            safe = [row for row in rows if row["safe"]]
            if safe:
                safe.sort(key=lambda row: row["score"], reverse=True)
                if len(safe) > self.max_model:
                    n_top = max(1, self.max_model // 2)
                    top = safe[:n_top]
                    rest = safe[n_top:]
                    sampled = self.rng.choice(len(rest), size=self.max_model - len(top), replace=False)
                    safe = top + [rest[int(i)] for i in sampled]
            else:
                safe = sorted(rows, key=lambda row: row["linear_margin_km"], reverse=True)[:5]
            if safe:
                weight = self.w_safe / len(safe)
                for row in safe:
                    raw.append(("safe", row["dv_eci_mps"], weight, row["zone_slack_km"]))

        # 短期內撞地的閃法不列入模型；安全區間不可及的閃法保留少量人類失誤機率。
        merged = {}
        for name, dv_in, weight, slack in raw:
            dv = np.asarray(dv_in, dtype=np.float64).reshape(3)
            if weight <= 0.0 or perigee_alt_km(re, ve + dv / 1000.0) < 0.0:
                continue
            if slack is None and ctx["zone"] is not None:
                v_after = ve + dv / 1000.0
                a_after = sma_after(re, ve, dv / 1000.0)
                up, down = dsma_capacity(re, v_after, ctx["D_e"])
                slack = zone_slack(a_after, ctx["zone"], ctx["burns_left_after"], up, down)
            if slack is not None and slack < 0.0:
                weight *= 0.1
            key = tuple(np.round(dv, 9))
            if key in merged:
                merged[key]["weight"] += float(weight)
            else:
                merged[key] = {"kind": name, "dv_eci_mps": dv.copy(), "weight": float(weight)}
        if not merged:
            # 當所有模型來源都被剔除時，仍提供一個可評分的保底軌跡。
            merged[(0.0, 0.0, 0.0)] = {"kind": "zero", "dv_eci_mps": np.zeros(3), "weight": 1.0}
        model = list(merged.values())
        total = sum(row["weight"] for row in model)
        for row in model:
            row["weight"] /= total

        # 連續零推是可觀測的對手習慣；用目前零推機率作似然，逐回合提高純滑行對手的後驗。
        # 一旦曾觀測到非零推力，純滑行假說便失效，原始權重繼續適用。
        if game.history and self.w_zero > 0.0:
            observed = []
            for rec in game.history:
                burns = [burn for burn in rec.get("burns", ()) if burn["side"] == "evader"]
                if burns:
                    observed.append(float(burns[0]["dv_mps"]) <= 1e-6)
            if observed and all(observed):
                p_zero = sum(row["weight"] for row in model if np.linalg.norm(row["dv_eci_mps"]) <= 1e-6)
                if p_zero > 0.0:
                    prior = min(0.99, self.w_zero)
                    odds = prior / max(1e-12, 1.0 - prior)
                    odds *= p_zero ** (-len(observed))
                    posterior = odds / (1.0 + odds)
                    for row in model:
                        row["weight"] *= 1.0 - posterior
                        if np.linalg.norm(row["dv_eci_mps"]) <= 1e-6:
                            row["weight"] += posterior
        model.sort(key=lambda row: row["weight"], reverse=True)
        return model

    def _pursuer_candidates(self, game, model, ctx):
        """收集 Lambert、最佳回應、方向球與零推，並剔除不安全軌道。"""
        rp, vp = game.r("pursuer"), game.v("pursuer")
        re, ve = game.r("evader"), game.v("evader")
        D, T = ctx["D_p"], ctx["T"]
        candidates = [("zero", np.zeros(3, dtype=np.float64))]
        for row in model[:15]:
            ve_burn = ve + row["dv_eci_mps"] / 1000.0
            for frac in self.lambert_fracs:
                tau = frac * T
                if tau <= 0.0:
                    continue
                target, _ = kepler(re, ve_burn, tau, game.mu)
                need, v1, _ = lambert_min_dv(game.mu, rp, vp, target, tau, 0)
                if not math.isfinite(need):
                    continue
                dv = (v1 - vp) * 1000.0
                norm = float(np.linalg.norm(dv))
                if norm > D and norm > 0.0:
                    dv *= D / norm
                candidates.append(("lambert", dv))

        if T > 0.0:
            reach = make_reach(rp, vp, D, time_grid(T, self.grid_sec), game.mu)
            for row in model[:10]:
                ve_burn = ve + row["dv_eci_mps"] / 1000.0
                _, dv_kms, _ = exact_miss(rp, vp, D, re, ve_burn, T, game.mu,
                                           grid_sec=self.grid_sec, reach_p=reach)
                candidates.append(("best_response", dv_kms * 1000.0))

        if D > 0.0:
            directions = direction_set(self.n_dirs, rp, vp)
            for mag in self.mags:
                if mag > 0.0:
                    candidates.extend(("direction", direction * (mag * D)) for direction in directions)
        kept = []
        seen = set()
        for kind, dv in candidates:
            if not np.all(np.isfinite(dv)):
                continue
            key = tuple(np.round(dv, 6))
            if key in seen:
                continue
            if perigee_alt_km(rp, vp + dv / 1000.0) < self.perigee_margin_km:
                continue
            seen.add(key)
            kept.append((kind, dv.copy()))
        if not kept:
            # 已在碰撞軌道又沒有足夠推力時，選近地點最高的候選以爭取存活。
            kind, dv = max(candidates, key=lambda item: perigee_alt_km(rp, vp + item[1] / 1000.0))
            kept.append((kind, dv.copy()))
        return kept

    def _next_margins(self, game, model, ctx, p_end, vp_end, shortlist):
        """只替主分數接近最優的前十發估下一回合的可達距離。"""
        out = {}
        top_model = model[:5]
        total = sum(row["weight"] for row in top_model)
        taus = np.r_[0.0, time_grid(ctx["T"], max(self.grid_sec, 30.0))]
        next_states = []
        for row in top_model:
            re_next, ve_next = kepler(game.r("evader"),
                                      game.v("evader") + row["dv_eci_mps"] / 1000.0,
                                      ctx["T"], game.mu)
            next_states.append((row["weight"] / total, re_next, ve_next))
        for i in shortlist:
            reach = make_reach(p_end[i], vp_end[i], ctx["D_p"], taus, game.mu)
            margin = 0.0
            for weight, re_next, ve_next in next_states:
                value, _ = linear_margin(reach, re_next, ve_next, ctx["R_cap"])
                margin += weight * value
            out[i] = float(margin)
        return out

    def act(self, game, side):
        """按加權命中率、下一回合餘裕與實際賽局驗證選一發。"""
        if side != "pursuer":
            raise ValueError("CapturePursuer 只能擔任 pursuer")
        start = time.perf_counter()
        ctx = round_context(game)
        model = self._evader_model(game)
        candidates = self._pursuer_candidates(game, model, ctx)
        rp, vp = game.r("pursuer"), game.v("pursuer")
        re, ve = game.r("evader"), game.v("evader")
        taus = np.r_[0.0, time_grid(ctx["T"], self.grid_sec)]
        dv_p = np.stack([dv for _, dv in candidates])
        dv_e = np.stack([row["dv_eci_mps"] for row in model])
        vp_burn = vp[None, :] + dv_p / 1000.0
        ve_burn = ve[None, :] + dv_e / 1000.0
        p_tracks = np.empty((len(candidates), len(taus), 3), dtype=np.float64)
        e_tracks = np.empty((len(model), len(taus), 3), dtype=np.float64)
        p_end = np.empty((len(candidates), 3), dtype=np.float64)
        vp_end = np.empty((len(candidates), 3), dtype=np.float64)
        e_end = np.empty((len(model), 3), dtype=np.float64)
        for i in range(len(candidates)):
            p_tracks[i], velocities = kepler_grid(rp, vp_burn[i], taus, game.mu)
            p_end[i], vp_end[i] = p_tracks[i, -1], velocities[-1]
        for j in range(len(model)):
            e_tracks[j], _ = kepler_grid(re, ve_burn[j], taus, game.mu)
            e_end[j] = e_tracks[j, -1]
        misses = _miss_matrix(rp, vp_burn, re, ve_burn, p_tracks, e_tracks, taus, game.mu)
        weights = np.array([row["weight"] for row in model], dtype=np.float64)
        hits = misses <= ctx["R_cap"] - self.hit_margin_km
        primary = hits @ weights
        expected_miss = misses @ weights
        expected_end = np.linalg.norm(p_end[:, None, :] - e_end[None, :, :], axis=2) @ weights
        has_next = ctx["burns_left_after"] > 0

        def shortlist():
            best = float(np.max(primary))
            near = [i for i in range(len(candidates)) if best - primary[i] < 0.02]
            # 同一命中率下先挑靠近模型中心的候選，避免任意排序截斷追擊路線。
            if has_next:
                near.sort(key=lambda i: (-primary[i], expected_end[i]))
            else:
                near.sort(key=lambda i: (-primary[i], expected_miss[i]))
            return near[:10]

        next_margins = (self._next_margins(game, model, ctx, p_end, vp_end, shortlist())
                        if has_next and self.lookahead else {})

        def choose():
            near = shortlist()
            if not has_next:
                return min(near, key=lambda i: (expected_miss[i], -primary[i]))
            if self.lookahead:
                return min(near, key=lambda i: (next_margins.get(i, math.inf),
                                                expected_end[i], -primary[i]))
            return min(near, key=lambda i: (expected_end[i], -primary[i]))

        chosen = choose()
        predicted = float(primary[chosen])
        for attempt in range(3):
            # 優先驗證貢獻命中率最大的幾種躲方推力；失準就更正並重新排序。
            selected = sorted(range(len(model)), key=lambda j: (float(weights[j] * hits[chosen, j]),
                                                                  float(weights[j])), reverse=True)[:5]
            changed = False
            for j in selected:
                sim = game.clone()
                sim.play_round(dv_p[chosen], dv_e[j])
                actual = sim.outcome == "capture"
                if actual != bool(hits[chosen, j]):
                    hits[chosen, j] = actual
                    changed = True
            if not changed:
                break
            primary[chosen] = float(hits[chosen] @ weights)
            if attempt == 2:
                break
            if has_next and self.lookahead:
                missing = [i for i in shortlist() if i not in next_margins]
                next_margins.update(self._next_margins(game, model, ctx, p_end, vp_end, missing))
            revised = choose()
            if revised != chosen:
                chosen = revised
                predicted = float(primary[chosen])

        info = {"round": ctx["round"], "n_model": len(model), "n_cands": len(candidates),
                "hit_prob": predicted, "hit_prob_verified": float(primary[chosen]),
                "expected_end_dist_km": float(expected_end[chosen]),
                "next_margin_km": next_margins.get(chosen) if has_next and self.lookahead else None,
                "chosen_kind": candidates[chosen][0], "dv_mps": float(np.linalg.norm(dv_p[chosen])),
                "time_s": time.perf_counter() - start}
        self.last_info = info
        self.history_info.append(info.copy())
        return dv_p[chosen].copy()
