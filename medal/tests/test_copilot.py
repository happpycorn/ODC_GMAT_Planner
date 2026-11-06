"""copilot CLI：範本 → 建議 → GMAT 腳本、中途狀態重建。"""
import json
import os

import numpy as np

import copilot
from game.core import Game
from game.rules import Rules


def test_template_roundtrip_and_advise(tmp_path, capsys):
    path = tmp_path / "state.json"
    assert copilot.main(["init", str(path)]) == 0
    st = json.loads(path.read_text())
    st["rules"]["t_max_sec"] = 6000.0
    st["t_max_sec"] = 6000.0
    path.write_text(json.dumps(st))
    out = copilot.advise(st, rollouts=True, opp_models=["coast"])
    assert out["advice"]
    for a in out["advice"]:
        assert np.isfinite(a["burn"]["magnitude_mps"])
        assert a["burn"]["magnitude_mps"] <= Rules().max_dv_pursuer_mps + 1e-6
        assert a["rollouts"][0]["outcome"] in ("capture", "timeout", "crash_pursuer", "crash_evader")
    copilot.print_advice(out, "pursuer")
    printed = capsys.readouterr().out
    assert "戰況" in printed and "★ 推薦" in printed
    assert len(out["ranking"]) == len(out["advice"])


def test_rank_advice_prefers_worst_case_win():
    mk = lambda win, t=1000.0, d=10.0: {"we_win": win, "t_end": t, "min_dist_km": d,
                                        "used_pursuer_mps": 100.0, "used_evader_mps": 100.0}
    advice = [
        {"brain": "greedy", "rollouts": [mk(True), mk(True), mk(False, d=500.0)]},
        {"brain": "robust", "rollouts": [mk(True), mk(True), mk(True, t=5000.0)]},
    ]
    ranking = copilot.rank_advice(advice, "pursuer")
    assert ranking[0]["brain"] == "robust"
    ranking_e = copilot.rank_advice(
        [{"brain": "early_loss", "rollouts": [mk(False, t=2000.0)]},
         {"brain": "late_loss", "rollouts": [mk(False, t=9000.0)]}], "evader")
    assert ranking_e[0]["brain"] == "late_loss"


def test_mid_game_snapshot_matches_live_game():
    R = Rules(t_max_sec=8000.0)
    g = Game.from_elements(R, {"sma": 7000.0, "ecc": 0.0, "inc": 30.0, "raan": 0.0, "aop": 0.0, "ta": 0.0},
                           {"sma": 7060.0, "ecc": 0.001, "inc": 30.3, "raan": 0.2, "aop": 0.0, "ta": 6.0})
    g.play_turn(np.array([10.0, 20.0, 0.0]))
    g.play_turn(np.array([0.0, -5.0, 3.0]))
    st = copilot.state_from_game(g, "pursuer")
    h = copilot.game_from_state(json.loads(json.dumps(st)))
    assert h.t == g.t and h.t_max == g.t_max and h.mover == g.mover
    assert h.used == g.used
    assert np.allclose(h.r("evader"), g.r("evader")) and np.allclose(h.v("pursuer"), g.v("pursuer"))


def test_advise_writes_ascii_gmat_script(tmp_path):
    path = tmp_path / "state.json"
    copilot.main(["init", str(path)])
    script = tmp_path / "burn.script"
    assert copilot.main(["advise", str(path), "--no-rollout", "--brains", "lambert_pursuer",
                         "--gmat", str(script)]) == 0
    text = script.read_text()
    text.encode("ascii")
    assert "Create ImpulsiveBurn B0" in text and "Propagate Synchronized" in text
