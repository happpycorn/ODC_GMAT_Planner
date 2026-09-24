"""C4 終端棒拆後估計的驗證（`uv run python tests/test_split_aware_terminal.py`）。

見 docs/C4_TERMINAL_SPLIT_AWARE_PLAN.md。三塊：
  1. 目標函數：同一個終端超標決策向量，旗標開/關的分數差 = 10 − 預付成本；超過 K×cap 仍扣；
     旗標關時跟舊的 16 格 scalars 逐位元相同。
  2. 挑贏家換尺：_pick_best_case / pick_best_across_revs 餵假資料（違規 88.32 vs 合法 89.25），
     旗標開選前者、關選後者。
  3. 退路：拆後估計落空時，交真實分數較好的合法備胎。

決策向量取自 docs/solutions/checkpoints/ 的 contest 拆棒前存檔（3 棒、終端 4,691 m/s ≈ 3.13× cap）。
"""

import copy
import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.optimizer import (MissionOptimizer, fast_fitness_evaluator, pick_best_across_revs,
                           mission_rank_score)
from src.scorer import calculate_score
from src.config_validator import validate_config, ConfigValidationError
import main as app

FAILS = []


def check(name, cond):
    print(("  ✅ " if cond else "  ❌ ") + name)
    if not cond:
        FAILS.append(name)


CKPT = os.path.join(ROOT, "docs", "solutions", "checkpoints", "contest_route88.32_seed0_presplit.json")
with open(CKPT, encoding="utf-8") as f:
    _ck = json.load(f)
BASE = _ck["config"]
X = np.asarray(_ck["mission_info"]["x"], dtype=np.float64)
N = int(_ck["mission_info"]["num_burns"])


def make_opt(**strategy):
    cfg = copy.deepcopy(BASE)
    cfg.setdefault("strategy", {}).update(strategy)
    return MissionOptimizer(cfg)


def score(opt, x=X, n=N):
    return -float(opt._fitness_wrapper(n)(x))


print("── 1. 目標函數（fast_fitness_evaluator）──")
off = make_opt()
on = make_opt(SPLIT_AWARE_TERMINAL=True)
s_off, s_on = score(off), score(on)
check(f"旗標關：終端超標照扣 10 分（{s_off:.4f} < 90）", s_off < 90.0)
check(f"旗標開、overhead=1.00：分數差正好 10（{s_on - s_off:.6f}）", abs((s_on - s_off) - 10.0) < 1e-9)

ov = make_opt(SPLIT_AWARE_TERMINAL=True, SPLIT_AWARE_TERMINAL_DV_OVERHEAD=1.05)
s_ov = score(ov)
check(f"overhead=1.05：分數差 < 10 且 > 0（{s_ov - s_off:.4f}）", 0.0 < s_ov - s_off < 10.0)

k3 = make_opt(SPLIT_AWARE_TERMINAL=True, SPLIT_AWARE_TERMINAL_MAX_FACTOR=3.0)
check("超過 K×cap（K=3，終端 3.13×）仍扣分", score(k3) == s_off)

nosplit = make_opt(SPLIT_AWARE_TERMINAL=True, AUTO_SPLIT_LEGALIZE=False)
check("AUTO_SPLIT_LEGALIZE 關時旗標不生效", not nosplit.SPLIT_AWARE_TERMINAL and score(nosplit) == s_off)

# 旗標關 = 舊行為逐位元：舊呼叫端只給 16 格 scalars
sp16 = off._scalar_params()[:16].copy()
vp = np.vstack([off.A_r0, off.A_v0, off.B_r0, off.B_v0])
f16 = fast_fitness_evaluator(X, N, sp16, vp)
check("旗標關時與舊 16 格 scalars 逐位元相同", f16 == off._fitness_wrapper(N)(X))
check("_scalar_params 是 19 格", off._scalar_params().shape == (19,))

m = off.mission_metrics(X, N)
check(f"mission_metrics：可拆終端違規 1 次、拆後估計 = 真實 + 10（{m['score']:.4f} → {m['score_split_est']:.4f}）",
      m["split_terminal_count"] == 1 and abs(m["score_split_est"] - m["score"] - 10.0) < 1e-9)

print("\n── 設定檢查 ──")
bad = copy.deepcopy(BASE)
bad["strategy"]["SPLIT_AWARE_TERMINAL"] = "yes"
try:
    validate_config(bad)
    check("SPLIT_AWARE_TERMINAL 非 bool 會被擋", False)
except ConfigValidationError:
    check("SPLIT_AWARE_TERMINAL 非 bool 會被擋", True)
bad = copy.deepcopy(BASE)
bad["strategy"]["SPLIT_AWARE_TERMINAL_MAX_FACTOR"] = 0.5
try:
    validate_config(bad)
    check("SPLIT_AWARE_TERMINAL_MAX_FACTOR < 1 會被擋", False)
except ConfigValidationError:
    check("SPLIT_AWARE_TERMINAL_MAX_FACTOR < 1 會被擋", True)

print("\n── 2. 挑贏家換尺 ──")
# 假資料：2 棒 = 88.32 家族（終端可拆，拆後估計 98.32）；3 棒 = 89.25 家族（全合法）。
FAKE = {
    2: {"score": 88.32, "score_split_est": 98.32, "split_terminal_count": 1, "penalty_count": 1,
        "miss_km": 0.1, "dv_mps": 6182.0, "t_team": 5677.0, "earth_safe": True, "dc_converged": True},
    3: {"score": 89.25, "score_split_est": 89.25, "split_terminal_count": 0, "penalty_count": 0,
        "miss_km": 0.1, "dv_mps": 4480.0, "t_team": 6430.0, "earth_safe": True, "dc_converged": True},
}


def pick(opt):
    opt.burn_case_results = {b: {"fitness": -FAKE[b]["score"], "best_x": np.ones(4 * b + 1)}
                             for b in FAKE}
    with patch.object(opt, "mission_metrics", side_effect=lambda x, b: dict(FAKE[b])):
        return opt._pick_best_case()[0]


check("_pick_best_case 旗標關：選合法 89.25（3 棒）", pick(make_opt()) == 3)
o = make_opt(SPLIT_AWARE_TERMINAL=True)
check("_pick_best_case 旗標開：選可拆 88.32 → 98.32（2 棒）", pick(o) == 2)
check("旗標開時記下合法備胎（3 棒 89.25）",
      o.legal_backup is not None and o.legal_backup["burns"] == 3 and o.legal_backup["score"] == 89.25)
check("旗標關時不記備胎", make_opt().legal_backup is None)


def _mi(score, est, pen):
    return {"score": score, "score_split_est": est, "penalty_count": pen,
            "miss_km": 0.1, "total_dv_mps": 5000.0, "T_team": 6000.0}


cands = [(0, [0.0], [0.0], _mi(88.32, 98.32, 1)), (4, [0.0], [0.0], _mi(89.25, 89.25, 0))]
check("pick_best_across_revs split_est=False：選 89.25", pick_best_across_revs(cands)[0] == 1)
check("pick_best_across_revs split_est=True：選可拆 88.32", pick_best_across_revs(cands, split_est=True)[0] == 0)
check("舊 mission_info 沒有 score_split_est 時退回 score",
      mission_rank_score({"score": 1.5}, split_est=True) == 1.5)

print("\n── 3. 退路（拆後估計落空）──")
viol = dict(_mi(88.32, 98.32, 1), earth_safe=True, num_burns=2)


def fake_opt(backup_mi, flag=True):
    b_opt = SimpleNamespace(refine_trajectory=lambda x, b, f: ("B", "T", backup_mi))
    bk = None if backup_mi is None else {"opt": b_opt, "burns": 3, "x": None, "fitness": -1.0,
                                         "score": backup_mi["score"]}
    return SimpleNamespace(SPLIT_AWARE_TERMINAL=flag, TIEBREAK_SCORE_EPS=1e-9, legal_backup=bk), b_opt


legal = dict(_mi(89.25, 89.25, 0), earth_safe=True, num_burns=3)
opt_, b_opt = fake_opt(legal)
r = app._fallback_to_legal_backup("b", "t", viol, opt_)
check("拆棒失敗 → 交真實分數較好的合法備胎", r[2] is legal and r[3] is b_opt)

worse = dict(_mi(50.0, 50.0, 0), earth_safe=True, num_burns=3)
opt_, _ = fake_opt(worse)
r = app._fallback_to_legal_backup("b", "t", viol, opt_)
check("備胎真實分數更差 → 照舊交違規解", r[2] is viol and r[3] is opt_)

opt_, _ = fake_opt(None)
check("沒有備胎 → 原樣", app._fallback_to_legal_backup("b", "t", viol, opt_)[2] is viol)

opt_, _ = fake_opt(legal, flag=False)
check("旗標關 → 不動", app._fallback_to_legal_backup("b", "t", viol, opt_)[2] is viol)

ok_mi = dict(_mi(98.3, 98.3, 0), earth_safe=True, num_burns=6)
opt_, _ = fake_opt(legal)
check("拆棒成功（零違規）→ 不動", app._fallback_to_legal_backup("b", "t", ok_mi, opt_)[2] is ok_mi)

print()
if FAILS:
    print(f"❌ {len(FAILS)} 項失敗：" + "、".join(FAILS))
    sys.exit(1)
print("✅ 全部通過")
