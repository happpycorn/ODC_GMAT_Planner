"""金／銅牌賽躲方、安全證書與共用二體幾何的驗收測試。"""
import json
import math
import time
from pathlib import Path

import numpy as np
import pytest
from scipy.optimize import brentq, minimize_scalar

from agents import make_agent
from agents.final_common import (ReachSet, ball_ls, dsma_capacity, exact_miss, kepler, kepler_grid,
                                 linear_margin, perigee_alt_km, reach_distance, sma_after, stm_rv,
                                 stm_rv_grid, zone_slack)
from agents.final_evader import HeuristicEvader, SafeEvader, heuristic_candidates
from evaluation.tournament import Task, play
from game.core import Game, sma_official
from game.rules import Rules
from game.scenarios import sample_final_scenario
from physics import EARTH_MU, RE_VAL, get_r0_v0, propagate
from physics.lambert import lambert_min_dv


FINAL_RULES = Path(__file__).resolve().parents[1] / "configs" / "rulesets" / "final_official.json"


def _rules(**kw):
    """建立純二體、總推力無上限的同時出手規則。"""
    base = dict(turn_mode="simultaneous", rounds=6, window_sec=1200.0,
                max_dv_pursuer_mps=250.0, max_dv_evader_mps=250.0,
                fuel_pursuer_mps=math.inf, fuel_evader_mps=math.inf,
                capture_radius_km=5.0, gravity_degree=0, crash_altitude_km=0.0)
    base.update(kw)
    return Rules(**base)


def _far_game(rules=None):
    """雙方相隔半圈，供安全空域及隨機化測試使用。"""
    R = _rules() if rules is None else rules
    op = dict(sma=7000.0, ecc=0.0, inc=20.0, raan=0.0, aop=0.0, ta=180.0)
    oe = dict(sma=7100.0, ecc=0.0, inc=20.0, raan=0.0, aop=0.0, ta=0.0)
    return Game.from_elements(R, op, oe)


def _ball_samples(rng, n, radius):
    """體積均勻取樣三維推力球，回傳 km/s。"""
    unit = rng.normal(size=(n, 3))
    unit /= np.linalg.norm(unit, axis=1)[:, None]
    return unit * (rng.random(n) ** (1.0 / 3.0) * radius)[:, None]


def test_kepler_against_propagate_and_reversibility():
    """橢圓與雙曲線在短、長正時間及負時間都與引擎一致。"""
    vinf = 2.0
    ah = -EARTH_MU / vinf ** 2
    eh = 1.0 + (RE_VAL + 700.0) * vinf ** 2 / EARTH_MU
    orbits = [
        dict(sma=7000.0, ecc=0.0001, inc=25.0, raan=20.0, aop=50.0, ta=30.0),
        dict(sma=11000.0, ecc=0.3, inc=65.0, raan=80.0, aop=40.0, ta=130.0),
        dict(sma=ah, ecc=eh, inc=35.0, raan=50.0, aop=10.0, ta=30.0),
    ]
    for orbit in orbits:
        r0, v0 = get_r0_v0(**orbit)
        for dt in (1.0, 300.0, 3600.0, 20000.0):
            r, v = kepler(r0, v0, dt, EARTH_MU)
            r_ref, v_ref = propagate(EARTH_MU, r0, v0, dt, 0)
            assert np.linalg.norm(r - r_ref) < 1e-5, (orbit, dt)
            assert np.linalg.norm(v - v_ref) < 2e-8, (orbit, dt)
            rr, vv = kepler(r, v, -dt, EARTH_MU)
            assert np.linalg.norm(rr - r0) < 1e-5, (orbit, dt)
            assert np.linalg.norm(vv - v0) < 2e-8, (orbit, dt)
        taus = np.array([-30.0, 0.0, 1.0, 300.0, 3600.0])
        rg, vg = kepler_grid(r0, v0, taus, EARTH_MU)
        assert rg.shape == vg.shape == (len(taus), 3)
        for i, tau in enumerate(taus):
            ri, vi = kepler(r0, v0, tau, EARTH_MU)
            np.testing.assert_allclose(rg[i], ri, atol=1e-9)
            np.testing.assert_allclose(vg[i], vi, atol=1e-10)


def test_stm_rv_against_propagate_difference():
    """速度到未來位置的雅可比與獨立數值微分一致。"""
    r0, v0 = get_r0_v0(sma=7600.0, ecc=0.12, inc=45.0, raan=20.0, aop=10.0, ta=60.0)
    h = 1e-5
    taus = np.array([1.0, 300.0, 1200.0, 3600.0])
    grid = stm_rv_grid(r0, v0, taus, EARTH_MU)
    assert grid.shape == (len(taus), 3, 3)
    for i, tau in enumerate(taus):
        ref = np.empty((3, 3))
        for j in range(3):
            dv = np.zeros(3)
            dv[j] = h
            rp = propagate(EARTH_MU, r0, v0 + dv, tau, 0)[0]
            rm = propagate(EARTH_MU, r0, v0 - dv, tau, 0)[0]
            ref[:, j] = (rp - rm) / (2.0 * h)
        phi = stm_rv(r0, v0, tau, EARTH_MU)
        assert np.linalg.norm(phi - ref) / np.linalg.norm(ref) < 1e-5
        np.testing.assert_allclose(grid[i], phi, rtol=1e-9, atol=1e-7)


def _ball_reference(Phi, d, D):
    """以 SciPy Brent 求信賴域乘子，獨立核對最小殘差。"""
    U, s, Vt = np.linalg.svd(Phi)
    c = U.T @ d
    z0 = np.divide(c, s, out=np.zeros_like(c), where=s > 1e-14)
    if np.linalg.norm(z0) <= D and np.all(s > 1e-14):
        y = Vt.T @ z0
        return np.linalg.norm(Phi @ y - d)

    def f(lam):
        return np.sum((s * c / (s * s + lam)) ** 2) - D * D

    hi = max(1.0, np.max(s * s))
    while f(hi) > 0.0:
        hi *= 2.0
    lam = brentq(f, 1e-18, hi, xtol=1e-15)
    y = Vt.T @ (s * c / (s * s + lam))
    return np.linalg.norm(Phi @ y - d)


def test_ball_ls_against_scipy():
    """一般矩陣、近奇異矩陣與退化矩陣皆滿足球約束最小平方。"""
    rng = np.random.default_rng(319)
    for i in range(24):
        U, _ = np.linalg.qr(rng.normal(size=(3, 3)))
        V, _ = np.linalg.qr(rng.normal(size=(3, 3)))
        s = 10.0 ** rng.uniform(-1.0, 1.0, size=3)
        if i % 3 == 0:
            s[-1] = 1e-8
        Phi = U @ np.diag(s) @ V.T
        d = rng.normal(size=3)
        D = rng.uniform(0.05, 1.0)
        dist, y = ball_ls(Phi, d, D)
        ref = _ball_reference(Phi, d, D)
        assert abs(dist - ref) < 1e-6 * max(ref, 1.0) + 1e-9, (i, dist, ref)
        assert np.linalg.norm(y) <= D + 1e-8
        assert abs(np.linalg.norm(Phi @ y - d) - dist) < 1e-7
    Phi = np.diag([2.0, 3.0, 4.0])
    d = Phi @ np.array([0.1, -0.2, 0.05])
    dist, y = ball_ls(Phi, d, 1.0)
    assert dist < 1e-10 and np.linalg.norm(Phi @ y - d) < 1e-10
    dist, y = ball_ls(np.zeros((3, 3)), d, 1.0)
    assert dist == pytest.approx(np.linalg.norm(d), abs=1e-10)
    assert np.linalg.norm(y) <= 1.0 + 1e-10


def test_reach_distance_and_zone_tools():
    """零推力可達集合退化為名義位置，安全空域的零發餘裕正確。"""
    g = _far_game()
    taus = np.array([1.0, 10.0, 100.0])
    reach = ReachSet(g.r("pursuer"), g.v("pursuer"), 0.0, taus, EARTH_MU)
    x = reach.r_nom + np.array([3.0, 4.0, 0.0])
    np.testing.assert_allclose(reach_distance(reach, x), 5.0, atol=1e-9)
    assert zone_slack(7000.0, (6990.0, 7010.0), 0, 100.0, 100.0) == 0.0
    assert zone_slack(6800.0, (6990.0, 7010.0), 0, 100.0, 100.0) == -190.0
    assert math.isinf(zone_slack(6800.0, None, 0, 100.0, 100.0))


def test_sma_capacity_crosses_parabolic_boundary():
    """推滿一發跨拋物線時，較小推力仍可到達高正半長軸。"""
    re = np.array([7000.0, 0.0, 0.0])
    ve = np.array([0.0, 10.6, 0.0])
    up, down = dsma_capacity(re, ve, 250.0)
    assert math.isinf(up) and math.isfinite(down) and down > 0.0
    zone = (350000.0, 450000.0)
    rp = -re
    vp = np.array([0.0, -math.sqrt(EARTH_MU / 7000.0), 0.0])
    g = Game(_rules(safe_sma_km=zone), rp, vp, re, ve)
    named = {name: dv for name, dv, _ in heuristic_candidates(g)}
    assert "zone" in named
    assert sma_after(re, ve, named["zone"] / 1000.0) == pytest.approx(400000.0, abs=1.0)


def _brute_tracks(r0, v0, dv_pool, taus):
    """傳播所有隨機追方推力；同題五個躲方動作共用結果。"""
    tracks = np.empty((len(dv_pool), len(taus), 3), dtype=np.float64)
    for i, dv in enumerate(dv_pool):
        tracks[i] = kepler_grid(r0, v0 + dv, taus, EARTH_MU)[0]
    return tracks


def _brute_nearest(tracks, rp, vp, dv_pool, re, ve, taus):
    """網格找最近的八條軌跡，再逐條做連續時間精修。"""
    eg = kepler_grid(re, ve, taus, EARTH_MU)[0]
    delta = tracks - eg[None, :, :]
    d2 = np.einsum("ijk,ijk->ij", delta, delta)
    per_burn = np.min(d2, axis=1)
    idx = np.argpartition(per_burn, 8)[:8]
    best = math.sqrt(float(np.min(per_burn)))
    for i in idx:
        j = int(np.argmin(d2[i]))
        lo, hi = taus[max(0, j - 1)], taus[min(len(taus) - 1, j + 1)]

        def distance(tau):
            pp = kepler(rp, vp + dv_pool[i], tau, EARTH_MU)[0]
            ee = kepler(re, ve, tau, EARTH_MU)[0]
            return float(np.linalg.norm(pp - ee))

        if hi > lo:
            sol = minimize_scalar(distance, bounds=(lo, hi), method="bounded",
                                  options={"xatol": 1e-5})
            best = min(best, float(sol.fun))
    return best


def test_linearization_and_exact_miss_against_random_bruteforce():
    """20 題各五個躲方推力，追方每題取樣兩萬發，核對非線性最佳回應。"""
    rng = np.random.default_rng(20261101)
    R0 = _rules()
    T, D = 1200.0, 250.0
    taus = np.linspace(0.0, T, 41)
    abs_errors, rel_errors = [], []
    for case in range(20):
        R, sc = sample_final_scenario(rng, R0)
        g = Game.from_elements(R, sc.orbit_pursuer, sc.orbit_evader)
        rp, vp = g.r("pursuer"), g.v("pursuer")
        re, ve = g.r("evader"), g.v("evader")
        pool = _ball_samples(rng, 20_000, D / 1000.0)
        tracks = _brute_tracks(rp, vp, pool, taus)
        reach = ReachSet(rp, vp, D, np.arange(5.0, T + 1e-9, 5.0), EARTH_MU)
        for dv_e in _ball_samples(rng, 5, D / 1000.0):
            ve_burn = ve + dv_e
            brute = _brute_nearest(tracks, rp, vp, pool, re, ve_burn, taus)
            miss, dv_p, tau = exact_miss(rp, vp, D, re, ve_burn, T, EARTH_MU, grid_sec=5.0)
            # 最近點可能在回合起點的右極限，實作可用 τ=0 代表該邊界。
            assert math.isfinite(miss) and 0.0 <= tau <= T
            assert np.linalg.norm(dv_p) <= D / 1000.0 + 1e-8
            pp = kepler(rp, vp + dv_p, tau, EARTH_MU)[0]
            ee = kepler(re, ve_burn, tau, EARTH_MU)[0]
            assert abs(np.linalg.norm(pp - ee) - miss) < 1e-3
            assert miss <= brute + 0.05, (case, miss, brute)
            linear, _ = linear_margin(reach, re, ve_burn, R.capture_radius_km)
            err = abs(linear + R.capture_radius_km - miss)
            abs_errors.append(err)
            rel_errors.append(err / max(miss, R.capture_radius_km))
    print("線性化與非線性距離誤差："
          f"中位數 {np.median(abs_errors):.6f} km，最大 {np.max(abs_errors):.6f} km；"
          f"相對中位數 {np.median(rel_errors):.3%}，最大 {np.max(rel_errors):.3%}"
          "（相對分母至少為捕獲半徑）")
    assert np.median(rel_errors) < 0.10


def test_exact_miss_lambert_reachable():
    """Lambert 一發可達的躲方軌跡，非線性最佳回應應找到交會。"""
    re, ve = get_r0_v0(sma=7100.0, ecc=0.001, inc=20.0, raan=0.0, aop=0.0, ta=0.0)
    w = np.cross(re, ve)
    w /= np.linalg.norm(w)
    rp, vp = re + 70.0 * w, ve.copy()
    tau_enc = 600.0
    re_enc = kepler(re, ve, tau_enc, EARTH_MU)[0]
    dv_lambert, _, _ = lambert_min_dv(EARTH_MU, rp, vp, re_enc, tau_enc, 0)
    assert dv_lambert < 0.250
    miss, dv_p, tau = exact_miss(rp, vp, 250.0, re, ve, 1200.0, EARTH_MU)
    assert miss < 0.01, (miss, dv_p, tau)


def test_safe_evader_certificate_against_play_round():
    """宣稱通過的證書，對球內及球面各一千發追方推力都不得被捕獲。"""
    rng = np.random.default_rng(6801)
    cases = []
    for seed in range(100):
        R, sc = sample_final_scenario(np.random.default_rng(seed), _rules())
        g = Game.from_elements(R, sc.orbit_pursuer, sc.orbit_evader)
        if g.distance() > 650.0:
            cases.append(g)
        if len(cases) == 3:
            break
    assert len(cases) == 3
    certified = 0
    for g in cases:
        agent = SafeEvader(seed=104)
        dv_e = agent.act(g.clone(), "evader")
        if not agent.last_info["certificate"]:
            continue
        certified += 1
        ball = _ball_samples(rng, 1000, g.burn_cap("pursuer") / 1000.0) * 1000.0
        sphere = rng.normal(size=(1000, 3))
        sphere /= np.linalg.norm(sphere, axis=1)[:, None]
        sphere *= g.burn_cap("pursuer")
        for dv_p in np.vstack([ball, sphere]):
            sim = g.clone()
            sim.play_round(dv_p, dv_e)
            assert sim.outcome != "capture", (agent.last_info, dv_p)
    assert certified >= 1


def test_final_round_reaches_zone_and_escapes():
    """最後一發起點離安全區間半發容量時，推完進區間且終局逃脫。"""
    g0 = _far_game()
    re, ve = g0.r("evader"), g0.v("evader")
    up, _ = dsma_capacity(re, ve, 250.0)
    a0 = sma_official(re, ve)
    zone = (a0 + 0.43 * up, a0 + 0.57 * up)
    R = g0.rules.with_(safe_sma_km=zone)
    T = R.window_sec
    g = Game.from_snapshot(R, g0.r("pursuer"), g0.v("pursuer"), re, ve,
                           t=5 * T, round_index=5)
    agent = SafeEvader(seed=7)
    dv_e = agent.act(g.clone(), "evader")
    a_after = sma_after(re, ve, dv_e / 1000.0)
    assert zone[0] <= a_after <= zone[1]
    g.play_round(np.zeros(3), dv_e)
    assert g.outcome == "escape"


def test_zone_pressure_keeps_remaining_burns_feasible():
    """剩三發而區間差約兩發半容量時，決策仍保留後續可行性。"""
    g0 = _far_game()
    re, ve = g0.r("evader"), g0.v("evader")
    up, down = dsma_capacity(re, ve, 250.0)
    a0 = sma_official(re, ve)
    zone = (a0 + 2.5 * up, a0 + 2.7 * up)
    R = g0.rules.with_(safe_sma_km=zone)
    T = R.window_sec
    g = Game.from_snapshot(R, g0.r("pursuer"), g0.v("pursuer"), re, ve,
                           t=3 * T, round_index=3)
    dv_e = SafeEvader(seed=17).act(g, "evader")
    a_after = sma_after(re, ve, dv_e / 1000.0)
    assert zone_slack(a_after, zone, 2, up, down) >= 0.0


def test_seed_reproducibility_and_choice_diversity():
    """相同種子重現動作；安全選項充足時不同種子至少選出兩種。"""
    g = _far_game(_rules(safe_sma_km=None))
    kw = dict(n_dirs=60, mags=(1.0,), grid_sec=10.0, lookahead=False)
    a = SafeEvader(seed=27, **kw)
    b = SafeEvader(seed=27, **kw)
    first = a.act(g.clone(), "evader")
    np.testing.assert_array_equal(first, b.act(g.clone(), "evader"))
    a.reset(27)
    np.testing.assert_array_equal(a.act(g.clone(), "evader"), first)
    choices = {tuple(SafeEvader(seed=s, **kw).act(g.clone(), "evader")) for s in range(10)}
    assert len(choices) >= 2


def test_safe_evader_perigee_margin_and_evaluate_api():
    """選出的推力維持近地點餘裕；公開評估不改動 Game。"""
    g = _far_game(_rules(safe_sma_km=None))
    re, ve = get_r0_v0(sma=RE_VAL + 120.0, ecc=0.0, inc=20.0,
                       raan=0.0, aop=0.0, ta=0.0)
    g.set_state("evader", re, ve)
    before = g.r("evader").copy(), g.v("evader").copy(), g.turn, len(g.history)
    agent = SafeEvader(n_dirs=60, mags=(1.0,), grid_sec=10.0,
                       lookahead=False, perigee_margin_km=30.0, seed=4)
    rows = agent.evaluate(g)
    assert rows
    keys = {"dv_eci_mps", "linear_margin_km", "feasible", "safe", "score",
            "zone_slack_km", "a_after_km"}
    assert all(keys <= row.keys() for row in rows)
    np.testing.assert_array_equal(g.r("evader"), before[0])
    np.testing.assert_array_equal(g.v("evader"), before[1])
    assert (g.turn, len(g.history)) == before[2:]
    dv = agent.act(g.clone(), "evader")
    assert perigee_alt_km(re, ve + dv / 1000.0) >= 30.0 - 1e-6
    assert len(agent.history_info) == 1
    assert set(("round", "n_cands", "n_feasible", "n_safe", "certificate",
                "linear_margin_km", "exact_margin_km", "zone_slack_km",
                "a_after_km", "dv_mps", "time_s")) <= agent.last_info.keys()


def test_heuristic_evader_candidates_and_final_zone_burn():
    """啟發式權重正規化、單發合法，安全空域項準確到區間中心。"""
    g0 = _far_game()
    re, ve = g0.r("evader"), g0.v("evader")
    up, _ = dsma_capacity(re, ve, 250.0)
    a0 = sma_official(re, ve)
    center = a0 + 0.5 * up
    R = g0.rules.with_(safe_sma_km=(center - 5.0, center + 5.0))
    early = Game.from_snapshot(R, g0.r("pursuer"), g0.v("pursuer"), re, ve,
                               t=0.0, round_index=0)
    early_names = {name for name, _, _ in heuristic_candidates(early)}
    assert {"away", "normal+", "normal-", "radial+", "radial-", "zone", "zero"} <= early_names
    g = Game.from_snapshot(R, g0.r("pursuer"), g0.v("pursuer"), re, ve,
                           t=5 * R.window_sec, round_index=5)
    candidates = heuristic_candidates(g)
    assert sum(w for _, _, w in candidates) == pytest.approx(1.0)
    assert all(np.linalg.norm(dv) <= g.burn_cap("evader") + 1e-8
               and w >= 0.0 for _, dv, w in candidates)
    named = {name: dv for name, dv, _ in candidates}
    assert list(named) == ["zone"]
    assert abs(sma_after(re, ve, named["zone"] / 1000.0) - center) <= 1.0
    agent = HeuristicEvader(seed=3)
    np.testing.assert_allclose(agent.act(g.clone(), "evader"), named["zone"], atol=1e-8)


def test_safe_evader_decision_time():
    """排除首次 JIT 編譯後，長回合完整版與快速版達到時間限制。"""
    g0 = _far_game(_rules(window_sec=3600.0, safe_sma_km=None))
    full = SafeEvader(seed=43)
    fast = make_agent({"name": "safe_evader_fast", "seed": 43})
    full.act(g0.clone(), "evader")
    fast.act(g0.clone(), "evader")
    t0 = time.perf_counter()
    full.act(g0.clone(), "evader")
    full_s = time.perf_counter() - t0
    t0 = time.perf_counter()
    fast.act(g0.clone(), "evader")
    fast_s = time.perf_counter() - t0
    print(f"SafeEvader 決策時間：完整版 {full_s:.3f} s；快速版 {fast_s:.3f} s")
    assert full_s < 3.0
    assert fast_s < 0.5


def test_final_tournament_agents_one_game_each():
    """官方佔位規則與 final 題目可完成兩種躲方各一局對打。"""
    with FINAL_RULES.open() as f:
        R0 = Rules.from_dict(json.load(f))
    R, sc = sample_final_scenario(np.random.default_rng(331), R0)
    outcomes = {"capture", "crash_pursuer", "crash_evader", "escape", "sma_out"}
    for evader in ("safe_evader", "heuristic_evader"):
        task = Task("lambert_pursuer", evader, R.to_dict(), sc.orbit_pursuer,
                    sc.orbit_evader, sc.family, 0, 331)
        out = play(task)
        assert out["outcome"] in outcomes
        assert 1 <= out["rounds_played"] <= 6
