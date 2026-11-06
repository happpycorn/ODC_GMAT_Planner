"""用法：uv run python tools/cert_check.py [局面數]

獨立檢查 SafeEvader 證書：對躲方選定軌跡每個時刻用 Lambert 求追方剛好命中的 Δv，<= D_p 即證書錯。"""
import json, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from game.core import Game
from game.rules import Rules
from game.scenarios import sample_final_scenario
from agents.final_evader import SafeEvader
from agents.final_common import kepler
from physics.lambert import lambert_min_dv
from physics import EARTH_MU

base = Rules.from_dict(json.load(open("configs/rulesets/final_official.json")))
bad = 0; n_cert = 0; n = 0; mins = []
for i in range(int(sys.argv[1]) if len(sys.argv) > 1 else 40):
    rng = np.random.default_rng([99, i])
    D = float(np.exp(rng.uniform(np.log(100), np.log(500))))
    R = base.with_(max_dv_pursuer_mps=D, max_dv_evader_mps=D,
                   capture_radius_km=float(np.exp(rng.uniform(0, np.log(20)))),
                   window_sec=float(np.exp(rng.uniform(np.log(600), np.log(3600)))))
    R, sc = sample_final_scenario(rng, R)
    g = Game.from_elements(R, sc.orbit_pursuer, sc.orbit_evader)
    E = SafeEvader(seed=i)
    for k in range(int(rng.integers(0, 4))):          # 隨機推進幾回合（雙方隨機）
        if g.done: break
        g.play_round(rng.normal(size=3) * D / 2, rng.normal(size=3) * D / 2)
    if g.done: continue
    dv_e = E.act(g.clone(), "evader"); n += 1
    if not E.last_info["certificate"]: continue
    n_cert += 1
    T = min(R.window_sec, g.time_left)
    rp, vp, re, ve = g.r("pursuer"), g.v("pursuer"), g.r("evader"), g.v("evader") + dv_e / 1000
    best = math.inf
    for tau in np.arange(1.0, T + 1e-9, 1.0):
        rt, _ = kepler(re, ve, tau, EARTH_MU)
        need, v1, _ = lambert_min_dv(EARTH_MU, rp, vp, rt, tau, 0)
        best = min(best, need * 1000)
    mins.append(best / D)
    if best <= D:
        bad += 1; print("證書錯", i, best, D)
print(f"局面 {n}、證書成立 {n_cert}、Lambert 命中反例 {bad}；證書成立時追方需求/上限 最小 {min(mins) if mins else None:.3f} 中位 {np.median(mins) if mins else None}")
