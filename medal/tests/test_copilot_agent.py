"""copilot ★ 當 agent（agents/copilot_agent.py）與 copilot.advise 的快速模式（prune / budget_sec）。

小規模、決定性：短時限（3600 s = 12 回合）、快速版大腦與對手模型。"""
import numpy as np

import copilot
from agents import make_agent
from agents.copilot_agent import CopilotAgent, brain_label
from game.core import Game, take_turn
from game.rules import Rules

RANKING = Rules(max_dv_pursuer_mps=250.0, max_dv_evader_mps=250.0, fuel_pursuer_mps=3000.0,
                fuel_evader_mps=3000.0, t_max_sec=3600.0)
P_ORB = {"sma": 6978.0, "ecc": 0.0, "inc": 51.6, "raan": 10.0, "aop": 0.0, "ta": 0.0}
E_ORB = {"sma": 6990.0, "ecc": 0.001, "inc": 51.7, "raan": 10.1, "aop": 0.0, "ta": 1.0}     # ~120 km

E_BRAINS = ["lazy_evader", "dv_evader_fast", "escape_evader"]
E_OPPS = ["coast", "lambert_pursuer_fast"]
P_BRAINS = ["lambert_pursuer_fast", {"name": "lambert_pursuer_fast", "time_weight_mps": 60.0}, "coast"]
P_OPPS = ["coast", "dv_evader_fast"]


def _state(role, rules=RANKING, pre=1):
    """先讓雙方各用快速解析大腦下 pre 個回合，回傳輪到 role 的局勢檔。"""
    g = Game.from_elements(rules, P_ORB, E_ORB)
    P, E = make_agent("lambert_pursuer_fast"), make_agent("dv_evader_fast")
    n = 0
    while n < pre or g.mover != role:
        take_turn(g, P if g.mover == "pursuer" else E)
        n += 1
    return copilot.state_from_game(g, role)


def _key(r):
    return (r["opponent"], r["outcome"], r["t_end"], r["used_pursuer_mps"], r["used_evader_mps"], r["min_dist_km"])


def _check_prune_matches(st, brains, opps):
    full = copilot.advise(st, brains, opps)
    fast = copilot.advise(st, brains, opps, prune=True, with_situation=False)
    assert fast["ranking"][0]["brain"] == full["ranking"][0]["brain"]
    for a_full, a_fast in zip(full["advice"], fast["advice"]):
        assert np.allclose(a_full["burn"]["eci_mps"], a_fast["burn"]["eci_mps"])
        if a_fast["table_status"] == "complete":
            assert [_key(r) for r in a_fast["rollouts"]] == [_key(r) for r in a_full["rollouts"]]
        else:
            assert a_fast["table_status"] == "pruned"
    n_full = sum(len(a["rollouts"]) for a in full["advice"])
    n_fast = sum(len(a["rollouts"]) for a in fast["advice"])
    assert n_fast <= n_full
    return full, fast


def test_prune_gives_same_star_evader():
    full, fast = _check_prune_matches(_state("evader"), E_BRAINS, E_OPPS)
    assert full["ranking"][0]["brain"] == "lazy_evader"
    assert fast["staged"]["pruned"]               # 燒油的大腦推演到一半就確定輸給 lazy


def test_prune_gives_same_star_pursuer():
    _check_prune_matches(_state("pursuer"), P_BRAINS, P_OPPS)


def test_rank_wins_orders_by_wins_first():
    mk = lambda win, d=10.0: {"we_win": win, "t_end": 1000.0, "min_dist_km": d,
                              "used_pursuer_mps": 100.0, "used_evader_mps": 100.0}
    advice = [{"brain": "close_loser", "rollouts": [mk(True), mk(False, 100.0), mk(False, 120.0)]},
              {"brain": "two_wins", "rollouts": [mk(True), mk(True), mk(False, 500.0)]}]
    assert copilot.rank_advice(advice, "pursuer")[0]["brain"] == "close_loser"          # 預設：最壞 −100 > −500
    assert copilot.rank_advice(advice, "pursuer", order="wins")[0]["brain"] == "two_wins"


def test_prune_matches_under_rank_wins():
    for role, brains, opps in (("pursuer", P_BRAINS, P_OPPS), ("evader", E_BRAINS, E_OPPS)):
        st = _state(role)
        a = copilot.advise(st, brains, opps, rank="wins", with_situation=False)
        b = copilot.advise(st, brains, opps, rank="wins", prune=True, with_situation=False)
        assert a["ranking"][0]["brain"] == b["ranking"][0]["brain"]
        assert a["rank"] == b["rank"] == "wins"
        assert all(x["table_status"] == "complete" for x in a["advice"])


def test_staged_reuses_identical_rollout_tables():
    """強化版 rollout 追者的情況：另一個大腦第一發相同、推演表續行規格相同 → 推演結果直接沿用，數字不變。"""
    a = {"name": "rollout_pursuer", "candidates": ["lambert_pursuer_fast"], "opponents": ["coast"],
         "continuation": "lambert_pursuer_fast"}
    b = {**a, "workers": 1, "_table_cont": dict(a)}
    st = _state("pursuer")
    full = copilot.advise(st, [a, b], P_OPPS)
    fast = copilot.advise(st, [a, b], P_OPPS, prune=True, with_situation=False)
    assert fast["staged"]["rollouts_reused"] == len(P_OPPS)
    assert [[_key(r) for r in x["rollouts"]] for x in fast["advice"]] == \
           [[_key(r) for r in x["rollouts"]] for x in full["advice"]]
    assert fast["ranking"][0]["brain"] == full["ranking"][0]["brain"] == a


def test_value_upper_bound_never_below_final_value():
    for role, brains, opps in (("evader", E_BRAINS, E_OPPS), ("pursuer", P_BRAINS, P_OPPS)):
        st = _state(role)
        g = copilot.game_from_state(st)
        for b in brains:
            agent = make_agent(b)
            plan = [(0.0, g.clip_dv(role, agent.act(g, role)))]
            for o in opps:
                ubs = []
                r = copilot.rollout(g, role, plan, agent, make_agent(o),
                                    stop=lambda h: ubs.append(copilot._value_upper_bound(h, role)) and False)
                assert ubs and min(ubs) >= copilot._rollout_value({**r, "we_win": r["winner"] == role}, role)


def test_default_advise_output_unchanged_keys():
    out = copilot.advise(_state("pursuer"), ["lambert_pursuer_fast"], ["coast"])
    assert "staged" not in out
    assert set(out["advice"][0]) == {"brain", "decide_sec", "burn", "plan", "safe_after_burn", "rollouts"}


def test_budget_zero_falls_back_to_first_brain():
    st = _state("evader")
    out = copilot.advise(st, E_BRAINS, E_OPPS, prune=True, budget_sec=0.0, with_situation=False)
    assert [a["brain"] for a in out["advice"]] == ["lazy_evader"]
    assert out["advice"][0]["table_status"] == "timeout"
    assert "ranking" not in out and out["staged"]["skipped"] == E_BRAINS[1:]
    agent = CopilotAgent(brains=E_BRAINS, opponents=E_OPPS, budget_sec=0.0)
    g = copilot.game_from_state(st)
    assert np.allclose(agent.act(g, "evader"), make_agent("lazy_evader").act(g, "evader"))
    assert agent.decisions[-1]["star"] == "lazy_evader" and not agent.decisions[-1]["ranked"]


def _play(rules, pursuer, evader):
    g = Game.from_elements(rules, P_ORB, E_ORB)
    while not g.done:
        take_turn(g, pursuer if g.mover == "pursuer" else evader)
    return g


def test_single_brain_copilot_equals_brain():
    """只有一個大腦時 ★ 就是它：整局跟直接用那個大腦逐位元相同（局勢檔往返、原始 Δv 都沒失真）。"""
    for rules in (RANKING, RANKING.with_(burns_per_turn=2, min_burn_gap_sec=100.0)):
        cp = CopilotAgent(brains=["lambert_pursuer_fast"], opponents=["coast"], workers=1)
        cp.reset(seed=0)
        a = _play(rules, cp, make_agent("dv_evader_fast"))
        b = _play(rules, make_agent("lambert_pursuer_fast"), make_agent("dv_evader_fast"))
        assert a.summary() == b.summary()
        assert np.array_equal(a.r("pursuer"), b.r("pursuer")) and np.array_equal(a.v("evader"), b.v("evader"))
        n_turns = sum(1 for h in a.history if h["side"] == "pursuer")
        assert len(cp.decisions) == n_turns       # 多發規則也是一個窗口只跑一次 advise


def test_copilot_agent_plays_star_plan():
    st = _state("evader")
    g = copilot.game_from_state(st)
    agent = CopilotAgent(brains=E_BRAINS, opponents=E_OPPS)
    dv = agent.act(g, "evader")
    out = copilot.advise(st, E_BRAINS, E_OPPS)
    top = out["ranking"][0]["brain"]
    star = next(a for a in out["advice"] if a["brain"] == top)
    assert np.allclose(dv, star["burn"]["eci_mps"], atol=1e-3)
    assert agent.decisions[-1]["star"] == brain_label(top)


def test_brain_label():
    assert brain_label({"name": "rollout_pursuer", "workers": 4}) == "rollout_pursuer"
    assert brain_label({**copilot.STRONG_ROLLOUT_PURSUER, "workers": 1}) == "strong_rollout_pursuer"
    assert brain_label({"name": "lambert_pursuer", "time_weight_mps": 60.0}) == "lambert_pursuer(time_weight_mps=60.0)"
    assert brain_label("sb3:/x/models/evader.zip") == "sb3:evader.zip"
