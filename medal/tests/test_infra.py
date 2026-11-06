"""評測基礎設施：py: agent 規格、符號檢定、逐局配對。"""
import numpy as np
import pytest

from agents import CoastAgent, make_agent
from evaluation.stats import paired, sign_test


def test_py_spec_string_and_dict():
    a = make_agent("py:agents.base:CoastAgent")
    assert isinstance(a, CoastAgent)
    b = make_agent({"name": "py:agents.base:RandomAgent", "p_burn": 0.0})
    assert b.p_burn == 0.0 and np.all(b.act(None, "pursuer") == 0.0)
    with pytest.raises(KeyError):
        make_agent("py:agents.base")


def test_sign_test_matches_known_values():
    assert sign_test(0, 0) == 1.0
    assert sign_test(14, 1) == pytest.approx(2 * 16 / 2 ** 15)      # E17：p ≈ 0.001
    assert sign_test(11, 1) == pytest.approx(2 * 13 / 2 ** 12)      # E16：p ≈ 0.006
    assert sign_test(3, 3) == 1.0
    assert sign_test(1, 14) == sign_test(14, 1)


def test_paired_counts():
    a = [{"game_id": i, "family": "f", "winner": w} for i, w in enumerate(["pursuer", "pursuer", "evader", "evader"])]
    b = [{"game_id": i, "family": "f", "winner": w} for i, w in enumerate(["pursuer", "evader", "pursuer", "evader"])]
    b.append({"game_id": 9, "family": "f", "winner": "pursuer"})          # 只有一邊有的局不算
    p = paired(a, b)
    assert (p["n"], p["both"], p["only_a"], p["only_b"], p["neither"]) == (4, 1, 1, 1, 1)
    assert p["rate_a"] == 0.5 and p["p_sign"] == 1.0
    q = paired(a, b, win="evader")
    assert (q["both"], q["only_a"], q["only_b"]) == (1, 1, 1)


def test_lazy_evader_registered():
    from agents.evader_lab import LazyEvader3
    assert isinstance(make_agent("lazy_evader"), LazyEvader3)
