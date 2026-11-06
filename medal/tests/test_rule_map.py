"""規則敏感度地圖（tools/rule_map.py）、排位版規則分布（game/rule_presets.py）、查表（tools/rule_lookup.py）。"""
import json

import numpy as np
import pytest

from evaluation.tournament import make_games
from game.rule_presets import RankingRuleRanges, burns_that_fit, make_ranges
from game.rules import RuleRanges, Rules
from tools import rule_lookup, rule_map

# 2026-10-21 加 game/rule_presets.py 之前，用 master 80dc622 的 RuleRanges().sample 抽出來的值
# (window, max_dv_p, max_dv_e, fuel_p, fuel_e, capture_radius, t_max_periods, first_mover, burns, 下一個 rng.random())
RANGES_BEFORE = [
    ([0, 0], None, (130.32735750532808, 436.3546929501402, 213.31229693756472, 915.9808538577392,
                    1467.5078504037663, 15.400059002097473, 3.6232252151851294, "evader", 1, 0.5436249914654229)),
    ([1, 0], None, (160.4463119924643, 285.0969720596706, 275.2111169305176, 2192.9364536687935,
                    1065.33912707226, 3.554351777059325, 4.396959078371546, "pursuer", 1, 0.5495936876730595)),
    ([2, 0], None, (618.9828998809382, 121.73146491085585, 61.954474378759066, 310.59730353031256,
                    346.98242472123184, 8.869090757059098, 2.157653756783112, "pursuer", 1, 0.2749693679060381)),
    (123, Rules(burns_per_turn=2), (187.07236414518928, 509.19771338997106, 171.94319181147858,
                                    1581.6856533079294, 525.3613161691633, 11.390933395272992,
                                    4.731707493094698, "pursuer", 2, 0.8197545615930021)),
]


@pytest.mark.parametrize("seed,base,want", RANGES_BEFORE)
def test_rule_ranges_sample_unchanged(seed, base, want):
    """舊的 RuleRanges().sample：結果與亂數消耗（下一個亂數）都跟加 rule_presets 之前逐位元相同。"""
    rng = np.random.default_rng(seed)
    R = RuleRanges().sample(rng) if base is None else RuleRanges().sample(rng, base=base)
    got = (R.window_sec, R.max_dv_pursuer_mps, R.max_dv_evader_mps, R.fuel_pursuer_mps, R.fuel_evader_mps,
           R.capture_radius_km, R.t_max_periods, R.first_mover, R.burns_per_turn, float(rng.random()))
    assert got == want


def test_make_games_ranges_geometry_unchanged():
    """evaluate.py --rules ranges 的幾何靠同一條亂數流，抽規則多耗一個亂數就會整批變掉。"""
    a = make_games(3, "ranges", "mixed", 0)
    rng = np.random.default_rng([0, 0])
    R = RuleRanges().sample(rng)
    assert a[0][0] == R.to_dict()
    assert make_ranges("default") == RuleRanges()


def test_ranking_ranges_bounds_and_determinism():
    d = RankingRuleRanges()
    seen = set()
    for i in range(300):
        R = d.sample(np.random.default_rng([5, i]), Rules.from_dict(
            json.load(open("configs/rulesets/ranking_like.json"))))
        assert 120.0 <= R.window_sec <= 900.0
        assert 150.0 <= R.max_dv_pursuer_mps <= 400.0
        assert 0.8 * R.max_dv_pursuer_mps - 1e-9 <= R.max_dv_evader_mps <= 1.25 * R.max_dv_pursuer_mps + 1e-9
        assert 8.0 - 1e-9 <= R.fuel_pursuer_mps / R.max_dv_pursuer_mps <= 16.0 + 1e-9
        assert 8.0 - 1e-9 <= R.fuel_evader_mps / R.max_dv_evader_mps <= 16.0 + 1e-9
        assert 1.0 <= R.capture_radius_km <= 20.0 and 2.0 <= R.t_max_periods <= 6.0
        assert R.burns_per_turn in (1, 2, 3) and R.min_burn_gap_sec == 100.0
        if R.window_sec <= 200.0:
            assert R.burns_per_turn <= 2
        seen.add(R.burns_per_turn)
    assert seen == {1, 2, 3}
    r1 = d.sample(np.random.default_rng([1, 2]))
    r2 = d.sample(np.random.default_rng([1, 2]))
    assert r1 == r2
    assert make_ranges("ranking") == d


def test_burns_that_fit_matches_plan_turn():
    assert burns_that_fit(120.0, 3, 100.0) == 2
    assert burns_that_fit(200.0, 3, 100.0) == 2      # 第 3 發在 200 s = 窗口結束，下不了
    assert burns_that_fit(300.0, 3, 100.0) == 3
    assert burns_that_fit(90.0, 2, 100.0) == 1
    assert burns_that_fit(900.0, 1, 100.0) == 1


def test_cell_parsing_and_ids():
    base = Rules.from_dict(json.load(open("configs/rulesets/ranking_like.json")))
    ov = rule_map.parse_cell("burns_per_turn=2,window_sec=120")
    assert ov == {"burns_per_turn": 2, "window_sec": 120.0}
    assert isinstance(ov["burns_per_turn"], int)
    norm = rule_map.normalize(ov, base)
    assert list(norm) == ["window_sec", "burns_per_turn"]                    # Rules 欄位順序
    assert rule_map.cell_id(norm) == "window_sec=120,burns_per_turn=2"
    assert rule_map.axis_of(norm) == "burns_per_turn×window_sec"
    fuel = rule_map.normalize({"fuel_pursuer_mps": 3000.0, "fuel_evader_mps": 1500.0}, base)
    assert fuel == {"fuel_evader_mps": 1500.0}                               # 跟基底相同的欄位省略
    assert rule_map.axis_of(fuel) == "fuel"
    assert rule_map.cell_label(fuel, base) == "燃料 追3000/躲1500"
    assert rule_map.cell_id({}) == "base"
    with pytest.raises(KeyError):
        rule_map.parse_cell("windw_sec=3")


def test_ranges_cell_keeps_base_geometry():
    base = Rules(max_dv_pursuer_mps=250.0, max_dv_evader_mps=250.0)
    pairs = [("x", "coast", "coast")]
    tasks = rule_map.build_tasks(base, [("base", {}, None), ("ranges:ranking", {}, "ranking")], pairs, 4, 1, "mixed")
    by = {}
    for meta, t in tasks:
        by.setdefault(meta["cell"], []).append(t)
    geom = make_games(4, base.to_dict(), "mixed", 1)
    for cell in ("base", "ranges:ranking"):
        for t, (_, op, oe, fam) in zip(by[cell], geom):
            assert (t.orbit_pursuer, t.orbit_evader, t.family) == (op, oe, fam)
            assert t.seed == 1 * 100003 + t.game_id
    assert all(t.rules == base.to_dict() for t in by["base"])
    assert len({json.dumps(t.rules, sort_keys=True) for t in by["ranges:ranking"]}) == 4


def _row(cell, pair, gi, win, ov=None, rules=None):
    return {"cell": cell, "overrides": ov or {}, "ranges": None, "pair": pair, "family": "fam",
            "base": Rules().to_dict(), "rules": rules or Rules().with_(**(ov or {})).to_dict(),
            "pursuer": pair + "_p", "evader": pair + "_e", "game_id": gi,
            "winner": "pursuer" if win else "evader", "outcome": "capture" if win else "timeout",
            "min_dist_km": 0.0 if win else 50.0, "used_pursuer_mps": 1.0, "used_evader_mps": 2.0,
            "act_ms_pursuer": 1.0, "act_ms_evader": 1.0, "wall_s": 1.0, "seed": 1, "scenario": "mixed",
            "commit": "abc"}


def _synthetic_rows():
    rows = []
    for gi in range(12):
        rows.append(_row("base", "rr", gi, gi < 3))                       # 3/12
        rows.append(_row("base", "strong", gi, gi < 4))                   # 4/12
        rows.append(_row("base", "escape", gi, gi < 11))                  # 11/12
        ov = {"burns_per_turn": 2}
        rows.append(_row("burns_per_turn=2", "rr", gi, gi < 12, ov))     # 12/12：9 局只有本格抓到
        rows.append(_row("burns_per_turn=2", "strong", gi, gi < 12, ov))
        ov2 = {"window_sec": 900.0}
        rows.append(_row("window_sec=900", "rr", gi, gi < 2, ov2))
        rows.append(_row("window_sec=900", "strong", gi, gi < 11, ov2))  # 強化版 11 對 rollout 2
    return rows


def test_cell_stats_paired_and_advice():
    stats = {c["id"]: c for c in rule_map.cell_stats(_synthetic_rows())}
    b2 = stats["burns_per_turn=2"]
    assert b2["pairs"]["rr"]["k"] == 12 and b2["pairs"]["rr"]["n"] == 12
    v = b2["pairs"]["rr"]["vs_base"]
    assert (v["only_cell"], v["only_base"]) == (9, 0) and v["p"] == pytest.approx(2 / 2 ** 9)
    assert b2["advice"]["favored"] == "pursuer"
    w = stats["window_sec=900"]
    assert w["pursuer_compare"]["only_strong"] == 9 and w["pursuer_compare"]["only_rollout"] == 0
    assert w["advice"]["pursuer_brain"] == "strong"
    base = stats["base"]
    assert "vs_base" not in base["pairs"]["rr"]
    assert base["advice"]["pursuer_brain"] == "n.s."                       # 3 vs 4：分不出來
    assert base["evader_compare"]["only_rollout"] == 8                    # 逃逸被抓 11、rollout 被抓 3
    assert "不要逃逸" in base["advice"]["as_evader"]
    order = [c["id"] for c in rule_map.cell_stats(_synthetic_rows())]
    assert order == ["base", "burns_per_turn=2", "window_sec=900"]
    md = rule_map.markdown(list(stats.values()), "t")
    assert "**+9/−0" in md


def test_run_cells_appends_and_resumes(tmp_path):
    base = Rules(t_max_periods=0.3, max_dv_pursuer_mps=250.0, fuel_pursuer_mps=500.0)
    path = str(tmp_path / "m.jsonl")
    cells = [("base", {}, None), ("window_sec=600", {"window_sec": 600.0}, None)]
    pairs = [("cc", "coast", "coast")]
    assert rule_map.run_cells(base, cells, pairs, 2, 1, "mixed", 1, path, {"family": "t"}, log=lambda *a, **k: None) == 4
    rows = rule_map.load_rows(path)
    assert len(rows) == 4 and {r["cell"] for r in rows} == {"base", "window_sec=600"}
    assert all(r["family"] == "t" and r["pair"] == "cc" for r in rows)
    assert rule_map.run_cells(base, cells, pairs, 2, 1, "mixed", 1, path, log=lambda *a, **k: None) == 0
    with pytest.raises(SystemExit):           # 同名檔、規則不同 → 拒絕混在一起
        rule_map.run_cells(base.with_(capture_radius_km=9.0), cells, pairs, 2, 1, "mixed", 1, path,
                           log=lambda *a, **k: None)


def _map(tmp_path):
    rows = _synthetic_rows()
    rdir = tmp_path / "reports"
    rdir.mkdir()
    with open(rdir / "m.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    out = tmp_path / "map.json"
    rule_map.export(["m"], str(out), reports_dir=str(rdir))
    return json.load(open(out))


def test_export_and_lookup(tmp_path):
    doc = _map(tmp_path)
    assert {c["id"] for c in doc["cells"]} == {"base", "burns_per_turn=2", "window_sec=900"}
    near = rule_lookup.nearest(Rules(window_sec=850.0), doc, top=3)
    assert near[0][1]["id"] == "window_sec=900"
    near2 = rule_lookup.nearest(Rules(burns_per_turn=2, window_sec=280.0), doc, top=1)
    assert near2[0][1]["id"] == "burns_per_turn=2"
    flags = dict(rule_lookup.out_of_range(Rules(window_sec=1200.0, gravity_degree=4, capture_radius_km=5.0), doc))
    assert "window_sec" in flags and "gravity_degree" in flags
    assert "capture_radius_km" not in flags
    txt = rule_lookup.render(Rules(window_sec=1200.0), doc, top=2)
    assert "超出地圖範圍" in txt and "window_sec" in txt
