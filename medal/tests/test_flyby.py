"""雙曲線／飛掠幾何（清單第 4 項）：元素來回、邊界 T_max、各 agent 在飛掠局面下不出錯、觀測、copilot、
局勢匯入、GMAT 重播（沒有 GmatConsole 時略過）。"""
import importlib.util
import json
import math
import os

import numpy as np
import pytest

import copilot
from agents import make_agent
from game.core import (Game, boundary_exit_time, flyby_side, kepler_exit_time, sma_from_rv, specific_energy,
                       take_turn)
from game.obs import build_obs
from game.rules import Rules
from game.scenarios import FLYBY_BOUNDARY_KM, sample_scenario
from game.state_io import StateImportError, apply_report_to_state, read_gmat_report
from physics import EARTH_MU, RE_VAL, get_r0_v0, orbital_period, propagate
from physics.coast import closest_approach
from physics.frames import rv2coe

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLYBY_RULES = Rules(max_dv_pursuer_mps=250.0, max_dv_evader_mps=250.0, t_max_boundary_km=FLYBY_BOUNDARY_KM)
# Planner configs/shared/hyperbolic_smoke.json 的外星船 A（排位賽佔位情境：近地點 10,000 km、TA = −130°）
PLANNER_A = {"sma": -50000.0, "ecc": 1.2, "inc": 30.0, "raan": 0.0, "aop": 0.0, "ta": 230.0}
STRONG = {"name": "rollout_pursuer", "opponents": ["coast", "dv_evader_fast",
                                                 {"name": "rollout_evader", "candidates": ["dv_evader_fast"],
                                                  "opponents": ["lambert_pursuer_fast"]}]}


def _flyby(i, fam="flyby"):
    return sample_scenario(np.random.default_rng([1, i]), fam)


def _game(i=0, fam="flyby", rules=FLYBY_RULES):
    sc = _flyby(i, fam)
    return Game.from_elements(rules, sc.orbit_pursuer, sc.orbit_evader)


# ------------------------------------------------------------------ 元素
@pytest.mark.parametrize("i", range(5))
def test_hyperbolic_elements_roundtrip(i):
    hyp = PLANNER_A if i == 0 else _flyby(i).orbit_evader
    r, v = get_r0_v0(**hyp)
    c = rv2coe(r, v)
    assert c["sma"] < 0.0 and c["ecc"] > 1.0
    assert c["sma"] == pytest.approx(hyp["sma"], rel=1e-9) and c["ecc"] == pytest.approx(hyp["ecc"], rel=1e-9)
    r2, v2 = get_r0_v0(**c)
    assert np.allclose(r2, r, atol=1e-6) and np.allclose(v2, v, atol=1e-9)
    assert np.all(np.isfinite(r)) and np.all(np.isfinite(v))


# ------------------------------------------------------------------ 邊界 T_max
def test_kepler_exit_time_matches_element_formula_and_point_mass_propagation():
    r, v = get_r0_v0(**PLANNER_A)
    R = 100000.0
    t_ana = kepler_exit_time(r, v, R)
    e, a = PLANNER_A["ecc"], PLANNER_A["sma"]
    n = math.sqrt(EARTH_MU / (-a) ** 3)
    F0 = 2.0 * math.atanh(math.sqrt((e - 1.0) / (e + 1.0)) * math.tan(math.radians(230.0 - 360.0) / 2.0))
    Fb = math.acosh((1.0 + R / -a) / e)
    assert t_ana == pytest.approx(((e * math.sinh(Fb) - Fb) - (e * math.sinh(F0) - F0)) / n, abs=1e-6)
    assert float(r @ v) < 0.0                         # 開賽時往內飛：先過近地點再飛出去
    assert abs(boundary_exit_time(r, v, R, gravity_degree=0) - t_ana) < 1e-3
    rf, vf = propagate(EARTH_MU, r, v, t_ana, 0)
    assert abs(np.linalg.norm(rf) - R) < 1e-3 and float(rf @ vf) > 0.0


def test_boundary_exit_time_rejects_undefined_cases():
    r, v = get_r0_v0(**PLANNER_A)                      # 近地點 10,000 km
    with pytest.raises(ValueError, match="近地點"):
        kepler_exit_time(r, v, 9000.0)
    rf, vf = propagate(EARTH_MU, r, v, kepler_exit_time(r, v, 100000.0) + 100.0, 0)
    with pytest.raises(ValueError, match="不會再回來"):
        kepler_exit_time(rf, vf, 100000.0)
    rl, vl = get_r0_v0(7000.0, 0.001, 30.0, 0.0, 0.0, 0.0)
    with pytest.raises(ValueError, match="遠地點"):
        kepler_exit_time(rl, vl, 40000.0)
    with pytest.raises(ValueError):
        Rules(t_max_boundary_km=-1.0)
    # 橢圓也有定義（遠地點在邊界外）：下一次往外穿越
    rg, vg = get_r0_v0(24000.0, 0.72, 10.0, 0.0, 0.0, 0.0)
    t = boundary_exit_time(rg, vg, 30000.0, gravity_degree=0)
    assert 0.0 < t < orbital_period(24000.0) / 2.0
    rf, vf = propagate(EARTH_MU, rg, vg, t, 0)
    assert abs(np.linalg.norm(rf) - 30000.0) < 1e-3 and float(rf @ vf) > 0.0


@pytest.mark.parametrize("fam,side", [("flyby", "evader"), ("flyby_pursuer", "pursuer")])
def test_boundary_t_max_rule(fam, side):
    sc = _flyby(0, fam)
    g = Game.from_elements(FLYBY_RULES, sc.orbit_pursuer, sc.orbit_evader)
    assert g.t_max_basis == f"boundary({side})"
    assert flyby_side(g.r("pursuer"), g.v("pursuer"), g.r("evader"), g.v("evader")) == side
    r0, v0 = g.initial[side]
    assert g.t_max == boundary_exit_time(r0, v0, FLYBY_BOUNDARY_KM, gravity_degree=2)
    rf, vf = propagate(EARTH_MU, r0, v0, g.t_max, 2)               # 純滑行（J2）剛好在 T_max 飛出邊界
    assert abs(np.linalg.norm(rf) - FLYBY_BOUNDARY_KM) < 0.01 and float(rf @ vf) > 0.0
    assert abs(g.t_max - kepler_exit_time(r0, v0, FLYBY_BOUNDARY_KM)) < 10.0   # J2 只差幾秒
    assert 3600.0 <= g.t_max <= 4 * 3600.0
    while not g.done:
        g.play_turn(np.zeros(3))
    assert g.outcome == "timeout" and abs(g.t - g.t_max) < 1e-6


def test_t_max_precedence_and_default_rule_unchanged():
    sc = _flyby(1)
    g = Game.from_elements(FLYBY_RULES.with_(t_max_sec=1234.0), sc.orbit_pursuer, sc.orbit_evader)
    assert g.t_max == 1234.0 and g.t_max_basis == "t_max_sec"
    assert Rules().t_max_boundary_km == 0.0
    p = {"sma": 7000.0, "ecc": 0.0, "inc": 10.0, "raan": 0.0, "aop": 0.0, "ta": 0.0}
    e = {"sma": 7050.0, "ecc": 0.001, "inc": 10.2, "raan": 0.0, "aop": 0.0, "ta": 5.0}
    g = Game.from_elements(Rules(), p, e)
    rp, vp = g.initial["pursuer"]
    assert g.t_max == Rules().t_max_periods * orbital_period(sma_from_rv(rp, vp))    # 跟舊公式逐位元相同
    assert g.t_max_basis == "periods(pursuer)"
    # 追者是雙曲線、規則是週期倍數：舊版 T_max = inf（比賽永遠不超時），現在改用躲者週期
    sc = _flyby(1, "flyby_pursuer")
    g = Game.from_elements(Rules(), sc.orbit_pursuer, sc.orbit_evader)
    re_, ve_ = g.initial["evader"]
    assert g.t_max_basis == "periods(evader)" and g.t_max == 4.0 * orbital_period(sma_from_rv(re_, ve_))
    with pytest.raises(ValueError, match="都沒有週期"):
        Game.from_elements(Rules(), sc.orbit_pursuer, PLANNER_A)
    # 中途快照：給 t_max 就用給的，不重算邊界
    h = Game.from_snapshot(FLYBY_RULES, *g.initial["pursuer"], *g.initial["evader"], t=600.0, t_max=5000.0)
    assert h.t_max == 5000.0 and h.time_left == 4400.0


# ------------------------------------------------------------------ 場景家族
def test_flyby_family_design():
    for i in range(30):
        sc = _flyby(i)
        hyp, leo = sc.orbit_evader, sc.orbit_pursuer
        assert sc.family == "flyby" and hyp["ecc"] > 1.0 and hyp["sma"] < 0.0
        assert 300.0 - 1e-6 <= hyp["sma"] * (1.0 - hyp["ecc"]) - RE_VAL <= 2000.0 + 1e-6
        assert 1.0 - 1e-9 <= math.sqrt(EARTH_MU / -hyp["sma"]) <= 4.0 + 1e-9
        assert leo["ecc"] == 0.0 and 250.0 <= leo["sma"] - RE_VAL <= 2030.0
        r0, v0 = get_r0_v0(**hyp)
        assert np.linalg.norm(r0) <= 0.95 * FLYBY_BOUNDARY_KM and float(r0 @ v0) < 0.0      # 邊界內、往內飛
        sw = _flyby(i, "flyby_pursuer")
        assert sw.family == "flyby_pursuer" and sw.orbit_pursuer == hyp and sw.orbit_evader == leo
    # 有得打：純滑行差一點撞上（> 捕獲半徑、< 幾百 km），追者一發就攔得到不動的躲者
    from agents.analytic import pursuer_need
    for i in range(6):
        g = _game(i)
        d, _, _ = closest_approach(g.r("pursuer"), g.v("pursuer"), g.r("evader"), g.v("evader"), g.t_max, 60.0,
                                   g.mu, 2)
        need, tof = pursuer_need(g)
        assert 5.0 < d < 600.0 and need < 600.0 and 0.0 < tof < g.t_max


def test_mixed_sampling_unchanged():
    """mixed 不能抽到 flyby，也不能改變亂數消耗（數字來自加 flyby 之前的 game/scenarios.py）。"""
    want = [("inclined", 6727.305228723433, 252.75634820139373), ("wild", 7592.179736094129, 299.4756672732498),
            ("near_coplanar", 7399.684047485319, 32.67845916465653), ("wild", 7710.634324129925, 220.0829160718739)]
    for i, (fam, sma, ta) in enumerate(want):
        sc = sample_scenario(np.random.default_rng([0, i]), "mixed")
        assert (sc.family, sc.orbit_pursuer["sma"], sc.orbit_evader["ta"]) == (fam, sma, ta)


# ------------------------------------------------------------------ agent
def _evader_lab_spec():
    if importlib.util.find_spec("agents.evader_lab") is None:
        return []
    import agents.evader_lab as lab
    return ["py:agents.evader_lab:LazyEvader3"] if hasattr(lab, "LazyEvader3") else []


def _sb3(side):
    p = os.path.join(ROOT, "models", f"{side}.zip")
    return ["sb3:" + p] if os.path.exists(p) else []


PURSUERS = ["coast", "lambert_pursuer", "lambert_pursuer_fast", "rollout_pursuer", STRONG] + _sb3("pursuer")
EVADERS = ["coast", "dv_evader", "dv_evader_fast", "escape_evader", "rollout_evader"] + _sb3("evader") + _evader_lab_spec()


def _check_turns(g, P, E, n_turns):
    P.reset(seed=0)
    E.reset(seed=1)
    for _ in range(n_turns):
        if g.done:
            break
        side = g.mover
        rec = take_turn(g, P if side == "pursuer" else E)
        assert math.isfinite(rec["dv_mps"]) and rec["dv_mps"] <= g.rules.max_dv(side) + 1e-6
        for s in ("pursuer", "evader"):
            assert np.all(np.isfinite(g.r(s))) and np.all(np.isfinite(g.v(s)))
        assert math.isfinite(g.min_dist)


@pytest.mark.parametrize("fam", ["flyby", "flyby_pursuer"])
@pytest.mark.parametrize("spec", PURSUERS, ids=lambda s: s if isinstance(s, str) else "strong_rollout")
def test_pursuer_agents_on_flyby(fam, spec):
    _check_turns(_game(2, fam), make_agent(spec), make_agent("dv_evader_fast"), 4)


@pytest.mark.parametrize("fam", ["flyby", "flyby_pursuer"])
@pytest.mark.parametrize("spec", EVADERS)
def test_evader_agents_on_flyby(fam, spec):
    _check_turns(_game(2, fam), make_agent("lambert_pursuer_fast"), make_agent(spec), 4)


@pytest.mark.parametrize("fam", ["flyby", "flyby_pursuer"])
def test_lambert_pursuer_intercepts_passive_flyby(fam):
    g = _game(1, fam)
    P, E = make_agent("lambert_pursuer"), make_agent("coast")
    while not g.done:
        take_turn(g, P if g.mover == "pursuer" else E)
    assert g.outcome == "capture" and g.used["pursuer"] < 600.0, g.summary()


@pytest.mark.parametrize("fam", ["flyby", "flyby_pursuer"])
def test_obs_finite_on_flyby(fam):
    g = _game(3, fam)
    for s in ("pursuer", "evader"):
        assert np.all(np.isfinite(build_obs(g, s)))
    while g.time_left > 900.0:                         # 飛掠方快到邊界（三、四萬 km）時也要有限
        g.play_turn(np.zeros(3))
    for s in ("pursuer", "evader"):
        assert np.all(np.isfinite(build_obs(g, s)))


# ------------------------------------------------------------------ copilot
def test_perigee_alt_matches_old_formula_on_ellipse_and_is_finite_on_hyperbola():
    r, v = get_r0_v0(7100.0, 0.01, 30.0, 10.0, 20.0, 40.0)
    c = rv2coe(r, v)
    assert copilot._perigee_alt(r, v) == pytest.approx(c["sma"] * (1 - c["ecc"]) - RE_VAL, abs=1e-6)
    r, v = get_r0_v0(**PLANNER_A)
    assert copilot._perigee_alt(r, v) == pytest.approx(10000.0 - RE_VAL, abs=1e-6)
    assert copilot._orbit_type(r, v).startswith("hyperbolic")


@pytest.mark.parametrize("role", ["pursuer", "evader"])
def test_copilot_advise_on_flyby_has_no_nan(role, capsys):
    g = _game(4)
    st = json.loads(json.dumps(copilot.state_from_game(g, role)))
    brains = ["lambert_pursuer"] if role == "pursuer" else ["dv_evader_fast"]
    out = copilot.advise(st, brains=brains, opp_models=["coast"])
    s = out["situation"]
    for k in ("distance_km", "coast_closest_approach_km", "pursuer_need_short_mps", "pursuer_need_full_mps",
              "time_left"):
        assert not math.isnan(s[k]), k
    assert math.isfinite(s["pursuer_need_full_mps"])
    for side in ("pursuer", "evader"):
        assert math.isfinite(s["perigee_alt_km"][side])
    assert 300.0 - 1e-3 <= s["perigee_alt_km"]["evader"] <= 2000.0 + 1e-3
    assert s["orbit_type"]["evader"].startswith("hyperbolic") and s["orbit_type"]["pursuer"] == "elliptic"
    a = out["advice"][0]
    assert np.isfinite(a["burn"]["magnitude_mps"]) and a["rollouts"][0]["outcome"] in (
        "capture", "timeout", "crash_pursuer", "crash_evader")
    copilot.print_advice(out, role)
    assert "飛掠" in capsys.readouterr().out


# ------------------------------------------------------------------ GMAT 報表匯入
KEP_HDR = ("ShipP.ElapsedSecs ShipP.Earth.SMA ShipP.Earth.ECC ShipP.EarthMJ2000Eq.INC ShipP.EarthMJ2000Eq.RAAN "
           "ShipP.EarthMJ2000Eq.AOP ShipP.Earth.TA ShipE.Earth.SMA ShipE.Earth.ECC ShipE.EarthMJ2000Eq.INC "
           "ShipE.EarthMJ2000Eq.RAAN ShipE.EarthMJ2000Eq.AOP ShipE.Earth.TA")
CART_HDR = ("ShipP.ElapsedSecs ShipP.EarthMJ2000Eq.X ShipP.EarthMJ2000Eq.Y ShipP.EarthMJ2000Eq.Z "
            "ShipP.EarthMJ2000Eq.VX ShipP.EarthMJ2000Eq.VY ShipP.EarthMJ2000Eq.VZ "
            "ShipE.EarthMJ2000Eq.X ShipE.EarthMJ2000Eq.Y ShipE.EarthMJ2000Eq.Z "
            "ShipE.EarthMJ2000Eq.VX ShipE.EarthMJ2000Eq.VY ShipE.EarthMJ2000Eq.VZ")


def test_hyperbolic_keplerian_report_import(tmp_path):
    path = tmp_path / "kep.txt"
    path.write_text(KEP_HDR + "\n0 7000 0.001 0 0 0 0 -50000 1.2 30 0 0 230\n")
    st = apply_report_to_state(copilot.template_state(), read_gmat_report(path), "ShipP", "ShipE")
    assert st["evader"]["elements"]["sma"] == -50000.0 and st["evader"]["elements"]["ecc"] == 1.2
    st["rules"] = FLYBY_RULES.to_dict()
    st["t_max_sec"] = 40000.0
    g = copilot.game_from_state(st)
    assert np.allclose(g.r("evader"), get_r0_v0(**PLANNER_A)[0])
    for line, msg in (("0 7000 0 0 0 0 0 50000 1.2 30 0 0 230", "負"),        # 雙曲線 SMA 寫成正的
                      ("0 7000 0 0 0 0 0 -50000 1.2 30 0 0 150", "漸近線"),   # TA 在漸近線外
                      ("0 7000 0 0 0 0 0 -50000000 1.2 30 0 0 230", "公尺")):
        path.write_text(KEP_HDR + "\n" + line + "\n")
        with pytest.raises(StateImportError, match=msg):
            apply_report_to_state({}, read_gmat_report(path), "ShipP", "ShipE")


def test_hyperbolic_cartesian_report_import(tmp_path):
    g = _game(0)                                     # 躲者開賽時在 3 萬多 km、往內飛
    vals = [0.0, *g.r("pursuer"), *g.v("pursuer"), *g.r("evader"), *g.v("evader")]
    path = tmp_path / "rep.txt"
    path.write_text(CART_HDR + "\n" + " ".join(f"{x:.12f}" for x in vals) + "\n")
    st = apply_report_to_state(copilot.template_state(), read_gmat_report(path), "ShipP", "ShipE")
    st["rules"], st["t_max_sec"] = FLYBY_RULES.to_dict(), g.t_max
    h = copilot.game_from_state(st)
    assert np.allclose(h.r("evader"), g.r("evader"), atol=1e-9) and h.t_max == g.t_max


# ------------------------------------------------------------------ GMAT 重播
GMAT = pytest.mark.skipif(not os.path.exists(os.path.expanduser(os.environ.get(
    "GMAT_CONSOLE", "~/software/GMAT/GMAT/R2026a/bin/GmatConsole"))), reason="GmatConsole 不在這台機器上")


def _played_flyby(deg, fam="flyby", t_max_sec=0.0):
    g = _game(0, fam, FLYBY_RULES.with_(gravity_degree=deg, t_max_sec=t_max_sec))
    P, E = make_agent("lambert_pursuer"), make_agent("dv_evader_fast")
    while not g.done:
        take_turn(g, P if g.mover == "pursuer" else E)
    return g


@GMAT
@pytest.mark.parametrize("deg", [0, 2, 4])
def test_gmat_replay_matches_engine_on_flyby(deg):
    from tools.gmat_verify import verify_game
    g = _played_flyby(deg)
    out = verify_game(g)
    assert out["turns"] > 20 and out["max_dt_sec"] < 1e-3
    assert out["max_dpos_km"] < 0.01, out["per_turn"][-3:]           # 三小時、幾十發：10 m 內


@GMAT
def test_gmat_full_perturbation_flyby_pursuer_runs(monkeypatch):
    """全攝動（排位賽官方模型）重播雙曲線追者：跑得完、落差在公里級以內、密集判定可用（只下前 3000 s 省時間）。

    這局 LEO 躲者（dv_evader_fast）在 2453 s 自己撞地（agents.analytic.orbit_survives 沒檢查弧終點，見
    docs/notes/flyby_geometry.md）：gmat_truth 不能把撞地後的窗口補滿，否則 GMAT 在大氣層裡積分 2 分多鐘。"""
    from tools.gmat_verify import gmat_truth, verify_game
    monkeypatch.setenv("ODC_STRICT_SURVIVAL", "0")   # 這局要重現舊行為的撞地（E25 預設開之後不會撞）
    g = _played_flyby(2, "flyby_pursuer", t_max_sec=3000.0)
    assert specific_energy(*g.initial["pursuer"]) > 0.0 and len(g.history) >= 5
    assert g.outcome == "crash_evader"
    out = verify_game(g, force_model="ranking_full")
    assert out["max_dpos_km"] < 5.0
    truth = gmat_truth(g, "ranking_full")
    # 撞地那個窗口的 g.min_dist 會含撞地之後的那一小段（physics/coast.py coast_pair，見筆記），所以比撞地瞬間的距離
    assert truth["n_rows"] < 5000 and abs(truth["final_dist_km"] - g.distance()) < 5.0
    assert truth["d_min_km"] <= truth["final_dist_km"] + 1e-6
