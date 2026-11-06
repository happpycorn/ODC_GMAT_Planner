"""orbit_survives 末端半徑檢查（開關 ODC_STRICT_SURVIVAL，預設開——2026-10-22 使用者決定；docs/notes/orbit_survives_fix.md）。

舊行為：近地點低於「撞地高度 + 裕度」時只問剩餘時間內會不會飛過近地點，不會就判安全——漏掉
「近地點在地底下、還沒到近地點就先穿過撞地高度」。開關開（或 strict=True）時再檢查 horizon 末端的二體半徑。
這裡的測試都明確指定 strict 或設定環境變數，不受執行環境的 ODC_STRICT_SURVIVAL 影響。
"""
import math

import numpy as np
import pytest

import agents.analytic as an
from agents.analytic import _direction_set, _radius_after_coast, orbit_survives, strict_survival_enabled
from agents.base import rsw_to_eci_dv
from game.core import Game
from game.rules import Rules
from physics import EARTH_MU, RE_VAL, propagate
from physics.coast import EV_CRASH_P, coast_pair
from physics.core_math import check_constraints, reaches_perigee

ENV = "ODC_STRICT_SURVIVAL"
NEAR_P = {"sma": 6978.0, "ecc": 0.0, "inc": 51.6, "raan": 10.0, "aop": 0.0, "ta": 0.0}
E600 = {"sma": 6978.0, "ecc": 0.0, "inc": 51.6, "raan": 10.0, "aop": 0.0, "ta": 20.0}


def _coast_out(g, side, dv):
    """推 dv 之後雙方都不再推，下到結束，回傳結局。"""
    h = g.clone()
    h.history = []
    h.play_turn(dv)
    while not h.done:
        h.play_turn(np.zeros(3))
    return h.outcome


# ------------------------------------------------------------------ 開關
def test_switch_default_is_on(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    assert an.STRICT_SURVIVAL_DEFAULT == 1           # 2026-10-22 使用者決定預設開（E25）；ODC_STRICT_SURVIVAL=0 回舊行為
    assert strict_survival_enabled() is True
    for val, want in (("1", True), ("on", True), ("true", True), ("0", False), ("off", False), ("", True),
                      ("看不懂", True)):
        monkeypatch.setenv(ENV, val)
        assert strict_survival_enabled() is want, val
    monkeypatch.setattr(an, "STRICT_SURVIVAL_DEFAULT", 0)
    monkeypatch.delenv(ENV)
    assert strict_survival_enabled() is False
    monkeypatch.setenv(ENV, "1")                     # 環境變數優先於模組常數
    assert strict_survival_enabled() is True


# ------------------------------------------------------------------ E22：對稱規則尾聲的大推力閃避
def _e22_game():
    """同 tests/test_evader_lab.py：對稱 1500/3000、剩 1350 s 輪到躲者（重現 seed 1 第 3 局的型態）。"""
    g = Game.from_elements(Rules(t_max_sec=1650.0), NEAR_P, E600)
    g.play_turn(np.zeros(3))
    return g


def test_e22_crash_before_underground_perigee(monkeypatch):
    g = _e22_game()
    dv = rsw_to_eci_dv(g, "evader", np.array([-1061.0, -1061.0, 0.0]))     # 往下 + 往後推 1500 m/s
    r, v = g.r("evader"), g.v("evader") + dv / 1000.0
    assert not check_constraints(r, v, g.mu, g.crash_radius)           # 近地點在地表下
    assert not reaches_perigee(r, v, g.mu, g.time_left)                # 近地點時刻在比賽結束後
    assert _radius_after_coast(r, v, g.mu, g.time_left) < g.crash_radius
    assert orbit_survives(g, "evader", dv, strict=False)               # 舊行為的漏判
    assert not orbit_survives(g, "evader", dv, strict=True)
    monkeypatch.setenv(ENV, "1")
    assert not orbit_survives(g, "evader", dv)
    monkeypatch.setenv(ENV, "0")
    assert orbit_survives(g, "evader", dv)
    monkeypatch.delenv(ENV)
    assert not orbit_survives(g, "evader", dv)                         # 預設開（2026-10-22）= 修正後行為
    assert _coast_out(g, "evader", dv) == "crash_evader"               # 引擎真的撞地
    for strict in (False, True):                                       # 不推：兩邊都安全
        assert orbit_survives(g, "evader", np.zeros(3), strict=strict)


def test_e22_dv_evader_candidates_strict_never_crash():
    """DvEvader 的 53 個候選：開關開時通過的候選推完滑到結束都不撞地；舊行為放行的候選裡有會撞地的。"""
    g = _e22_game()
    cap = g.burn_cap("evader")
    cands = [d * m * cap for d in _direction_set("full") for m in (1.0, 0.4)]
    old_crash = 0
    for c in cands:
        dv = rsw_to_eci_dv(g, "evader", c)
        old, new = orbit_survives(g, "evader", dv, strict=False), orbit_survives(g, "evader", dv, strict=True)
        assert old or not new                                         # 開了只會更嚴
        out = _coast_out(g, "evader", dv)
        if new:
            assert out != "crash_evader", c
        elif old and out == "crash_evader":
            old_crash += 1
    assert old_crash >= 1


# ------------------------------------------------------------------ E23：飛掠局（實際對局抓出來的快照）
# evaluate.py 同款對局（configs/rulesets/flyby_ranking_like.json、seed 1、舊行為）那一發之前的狀態，數字是 repr 原樣。
FLYBY = Rules(max_dv_pursuer_mps=250.0, max_dv_evader_mps=250.0, fuel_pursuer_mps=3000.0, fuel_evader_mps=3000.0,
              t_max_boundary_km=40000.0)
E23_CASES = {
    # --scenario flyby_pursuer 第 1 局，rollout 追者 vs sb3 躲者（LEO）：t=3900 s 起躲者每一發舊檢查都放行，
    # 這一發推完純滑行在 7999 s 撞地（比賽 8045 s 結束；實際對局 7412 s 撞地、躲者輸）
    "flyby_pursuer_g1_sb3_evader": {
        "t": 3900.0, "t_max": 8045.274696350098, "used": {"pursuer": 500.0, "evader": 1500.0}, "mover": "evader",
        "rp": [-9743.49975697229, 9321.206328398039, 13067.691708079174],
        "vp": [-6.752713520063695, 1.2031753503057119, 2.5883472510933108],
        "re": [-6712.521639324753, 5185.256803558351, 4771.119842780223],
        "ve": [-4.758285960688499, -2.548935827691318, -2.4057856197383023],
        "dv": [33.157668619555366, 107.4106501607557, 223.3014134387857]},
    # --scenario flyby 第 1 局，Lambert 追者 vs escape 躲者：追者已追不到、t=6000 s 朝攔截解推 250 m/s，
    # 推完純滑行在 7980 s 撞地（實際對局 7897 s 撞地）
    "flyby_g1_lambert_pursuer": {
        "t": 6000.0, "t_max": 8045.274696350098, "used": {"pursuer": 2349.5876583350228, "evader": 2500.0},
        "mover": "pursuer",
        "rp": [-10294.101478268107, -2156.8178089536614, -1575.6229390176081],
        "vp": [1.839408236764811, -3.098301826077669, -3.325868064218374],
        "re": [-23033.745318400583, 14456.554426749219, 22278.170995319033],
        "ve": [-6.660579276751461, 1.951423683463962, 3.5525174260568577],
        "dv": [-142.55747987421046, 118.33350190944898, 167.85275469220193]},
}


def _snapshot_game(s):
    f = lambda xs: np.array(xs, dtype=np.float64)                       # noqa: E731
    return Game.from_snapshot(FLYBY, f(s["rp"]), f(s["vp"]), f(s["re"]), f(s["ve"]), t=s["t"], t_max=s["t_max"],
                              used=s["used"], mover=s["mover"]), f(s["dv"])


@pytest.mark.parametrize("name", sorted(E23_CASES))
def test_e23_flyby_snapshots(name, monkeypatch):
    s = E23_CASES[name]
    g, dv = _snapshot_game(s)
    side = s["mover"]
    assert orbit_survives(g, side, dv, strict=False)                   # 舊行為放行
    assert not orbit_survives(g, side, dv, strict=True)
    monkeypatch.setenv(ENV, "1")
    assert not orbit_survives(g, side, dv)
    assert _coast_out(g, side, dv) == f"crash_{side}"                  # 而且真的撞地


# ------------------------------------------------------------------ 一般軌道：兩邊一致
@pytest.mark.parametrize("family", ["default", "near_coplanar", "inclined", "wild", "flyby", "flyby_pursuer"])
def test_ordinary_orbits_agree(family):
    """各幾何家族開賽狀態、26 方向 × 4 種大小的推力：只有「近地點低於門檻、到不了近地點」那一支會不同，
    而且開了只會更嚴；開賽時 horizon = 整場，LEO 一定飛得到近地點，所以兩邊完全一致。"""
    from evaluation.tournament import make_games
    rules = {"t_max_boundary_km": 40000.0} if family.startswith("flyby") else "default"
    for R, op, oe, _ in make_games(3, rules, family, seed=7):
        g = Game.from_elements(Rules.from_dict(R), op, oe)
        for side in ("pursuer", "evader"):
            for strict in (False, True):
                assert orbit_survives(g, side, np.zeros(3), strict=strict)
            for d in _direction_set("full"):
                for frac in (0.05, 0.2, 0.5, 1.0):
                    dv = rsw_to_eci_dv(g, side, d * frac * g.burn_cap(side))
                    old = orbit_survives(g, side, dv, strict=False)
                    new = orbit_survives(g, side, dv, strict=True)
                    assert old or not new
                    if old != new:
                        r, v = g.r(side), g.v(side) + dv / 1000.0
                        assert not check_constraints(r, v, g.mu, an.safe_radius(g))
                        assert not reaches_perigee(r, v, g.mu, g.time_left)
                        assert family.startswith("flyby")              # LEO 開賽不會走到這一支


# ------------------------------------------------------------------ 跟引擎（J2 連續撞地偵測）比
def _random_leaky_cases(n, seed):
    """LEO 近圓 + 0–1.5 km/s 任意方向推力 + horizon 60–6000 s，只留舊行為漏判那一支（近地點 < 門檻、到不了近地點）。"""
    rng = np.random.default_rng(seed)
    out = []
    while len(out) < n:
        rmag = RE_VAL + rng.uniform(250.0, 1500.0)
        rh = rng.normal(size=3)
        rh /= np.linalg.norm(rh)
        th = rng.normal(size=3)
        th -= (th @ rh) * rh
        th /= np.linalg.norm(th)
        d = rng.normal(size=3)
        d /= np.linalg.norm(d)
        r = rh * rmag
        v = th * math.sqrt(EARTH_MU / rmag) + d * rng.uniform(0.0, 1.5)
        h = rng.uniform(60.0, 6000.0)
        if check_constraints(r, v, EARTH_MU, RE_VAL + 150.0) or reaches_perigee(r, v, EARTH_MU, h):
            continue
        out.append((r, v, h))
    return out


def test_strict_never_approves_an_engine_crash():
    rules = Rules()
    far_r, far_v = np.array([0.0, 0.0, 42164.0]), np.array([3.07, 0.0, 0.0])
    old_bad = new_bad = 0
    for r, v, h in _random_leaky_cases(150, seed=3):
        g = Game.from_snapshot(rules, r, v, far_r, far_v, t=0.0, t_max=h, mover="pursuer")
        crash = coast_pair(r, v, far_r, far_v, h, rules.substep_sec, g.mu, rules.gravity_degree, -1.0,
                           g.crash_radius)[5] == EV_CRASH_P
        assert orbit_survives(g, "pursuer", np.zeros(3), strict=False)          # 漏判那一支：舊行為全放行
        if crash:
            old_bad += 1
            new_bad += orbit_survives(g, "pursuer", np.zeros(3), strict=True)
    assert old_bad >= 30                                                 # 這一支真的常撞地
    assert new_bad == 0


def test_radius_after_coast_matches_two_body_propagation():
    for r, v, h in _random_leaky_cases(40, seed=11):
        r2, _ = propagate(EARTH_MU, r, v, h, 0)
        assert abs(_radius_after_coast(r, v, EARTH_MU, h) - float(np.linalg.norm(r2))) < 1e-3
    r = np.array([RE_VAL + 400.0, 0.0, 0.0])
    assert _radius_after_coast(r, np.array([0.0, math.sqrt(EARTH_MU / r[0]), 0.0]), EARTH_MU, 3000.0) == \
        pytest.approx(r[0], abs=1e-9)                                  # 正圓
    assert _radius_after_coast(r, np.array([11.0, 3.0, 0.0]), EARTH_MU, 3000.0) == math.inf   # 往外飛的雙曲線


def test_outbound_hyperbola_with_low_perigee_is_safe_both_ways():
    """雙曲線、往外飛（已過近地點）：密切近地點可以在地底下，但半徑單調增加 → 兩邊都安全。"""
    r = np.array([RE_VAL + 600.0, 0.0, 0.0])
    v = np.array([11.0, 3.0, 0.0])                                      # 幾乎徑向往外、比能量 > 0
    g = Game.from_snapshot(Rules(), r, v, np.array([0.0, 0.0, 42164.0]), np.array([3.07, 0.0, 0.0]),
                           t=0.0, t_max=5000.0, mover="pursuer")
    assert float(v @ v) / 2.0 - g.mu / float(np.linalg.norm(r)) > 0.0
    assert not check_constraints(r, v, g.mu, g.crash_radius)               # 密切近地點在地底下
    for strict in (False, True):
        assert orbit_survives(g, "pursuer", np.zeros(3), strict=strict)
