"""決賽當天 copilot（HAP-104）：輸入當前局勢 → 建議機動 + 對多種對手模型的後續推演 + GMAT 驗證腳本。

當天流程（見 CONTEST_DAY_FINAL.md）：
  1. `copilot.py init state.json`             產生局勢檔範本，照官方畫面/報表填數字
  2. `copilot.py advise state.json`           看戰況、各大腦的建議脈衝、推演到比賽結束的結果
  3. `copilot.py advise state.json --gmat out.script [--verify]`
                                              產生「從現在狀態施加建議脈衝並滑行一窗口」的 GMAT 腳本，
                                              拿去會場測試電腦先跑（--verify 在本機 GMAT 比對）
  4. 對手動完、官方更新狀態後，改 state.json 再 advise
  時間緊：`advise state.json --prune`（★ 不變、推演表只做到能確定 ★ 為止）、再緊加 `--budget-sec 20`
  （超時就停，★ 只在做完的大腦裡選）；決策時間與建議見 docs/notes/copilot_eval.md

金／銅牌賽（同時出手、6 回合）：`copilot.py final new|advise|announce|parse|manual|show ...`（見 final_copilot.py）。

演練模式（不需要真比賽）：
  `copilot.py drill --role pursuer --opponent dv_evader --rules default`
  每回合印出建議並自動採用第一個大腦的建議，模擬整場；可 `--interactive` 手動選。

局勢檔（JSON）欄位：
  rules        規則（game/rules.py 的欄位；官方公告後填正式值）
  role         我方角色 pursuer / evader
  mover        現在輪到誰
  t_elapsed_sec, t_max_sec  比賽已經過 / 總時限（秒，從開賽起算）
  fuel_used_mps {"pursuer": .., "evader": ..}
  pursuer / evader: {"elements": {sma,ecc,inc,raan,aop,ta}} 或 {"r_km": [..], "v_kms": [..]}
                   （EarthMJ2000Eq；六根數的角度單位是度）
"""
import argparse
import json
import math
import os
import sys
import time
from functools import wraps

from runtime_threads import limit_blas_threads

limit_blas_threads()  # 在 numpy／agents 匯入之前設定，spawn 子行程也會繼承。

import numpy as np

from agents import make_agent
from agents.analytic import need_horizon, orbit_survives, pursuer_need
from agents.scan_reuse import decision_scope, scan_reuse_enabled
from game.core import Game, plan_turn, take_turn
from game.rules import Rules, other
from game.scenarios import DEFAULT_ORBIT_EVADER, DEFAULT_ORBIT_PURSUER, sample_scenario
from physics import EARTH_MU, RE_VAL, get_r0_v0
from physics.coast import closest_approach
from physics.frames import rsw_basis, vnb_basis

# 第一個是預設採用的大腦。rollout 規劃器是目前評測最強（reports/rollout_eval_default.md）：
# 追者對 DvEvader 50%（LambertPursuer 17%）、躲者對 LambertPursuer 存活 93%，決策 ~140 ms
# 強化版 rollout 追者：對手模型多一個 rollout 躲者輕量版（E16：排位版規則 250/3000 下對 rollout 躲者
# 29% → 71%，對稱 1500/3000 下略弱）——規則相依，所以只當候選大腦，由推演表排序決定用不用。
# 每步 ~2.4 s，推演表裡它只決定第一發，之後交給預設 rollout 追者（_table_cont），不然一次推演要好幾分鐘。
STRONG_ROLLOUT_PURSUER = {"name": "rollout_pursuer",
                          "opponents": ["coast", "dv_evader_fast",
                                        {"name": "rollout_evader", "candidates": ["dv_evader_fast"],
                                         "opponents": ["lambert_pursuer_fast"]}],
                          "_table_cont": "rollout_pursuer"}
DEFAULT_BRAINS = {"pursuer": ["rollout_pursuer", "lambert_pursuer",
                              {"name": "lambert_pursuer", "time_weight_mps": 60.0}, STRONG_ROLLOUT_PURSUER],
                  # lazy_evader（受威脅才閃，E22）：排位版與對稱規則下對我們所有追者都最強、每步 ~ms、省油；
                  # escape_evader 只當參考：燃料與單發上限都大且對稱時實測最強（88% vs 72%），
                  # 但隨機規則下會輸 rollout（HAP-108，docs/EXPERIMENTS.md E12）
                  "evader": ["lazy_evader", "rollout_evader", "dv_evader", "escape_evader"]}
# 推演用的對手模型。躲者側加 rollout 追者：只用 Lambert 系模型時推演會過度樂觀（HAP-108 教訓）
DEFAULT_OPP_MODELS = {"pursuer": ["coast", "dv_evader_fast", "dv_evader", "escape_evader"],
                      "evader": ["coast", "lambert_pursuer", {"name": "lambert_pursuer", "time_weight_mps": 60.0},
                                 "rollout_pursuer"]}


# ------------------------------------------------------------------ 局勢檔
def template_state():
    rules = Rules()
    g = Game.from_elements(rules, DEFAULT_ORBIT_PURSUER, DEFAULT_ORBIT_EVADER)
    return {
        "_comment": "照官方畫面填。rules 欄位見 game/rules.py；位置可給 elements（度）或 r_km/v_kms（EarthMJ2000Eq）",
        "rules": rules.to_dict(),
        "role": "pursuer",
        "mover": "pursuer",
        "t_elapsed_sec": 0.0,
        "t_max_sec": g.t_max,
        "fuel_used_mps": {"pursuer": 0.0, "evader": 0.0},
        "pursuer": {"elements": dict(DEFAULT_ORBIT_PURSUER)},
        "evader": {"elements": dict(DEFAULT_ORBIT_EVADER)},
    }


def _rv(entry):
    if "elements" in entry:
        return get_r0_v0(**entry["elements"])
    return np.asarray(entry["r_km"], dtype=float), np.asarray(entry["v_kms"], dtype=float)


def game_from_state(st):
    rules = Rules.from_dict(st["rules"])
    rp, vp = _rv(st["pursuer"])
    re, ve = _rv(st["evader"])
    return Game.from_snapshot(rules, rp, vp, re, ve, t=st.get("t_elapsed_sec", 0.0), t_max=st["t_max_sec"],
                              used=st.get("fuel_used_mps"), mover=st.get("mover"))


def state_from_game(g, role):
    return {
        "rules": g.rules.to_dict(), "role": role, "mover": g.mover, "t_elapsed_sec": g.t, "t_max_sec": g.t_max,
        "fuel_used_mps": dict(g.used),
        "pursuer": {"r_km": g.r("pursuer").tolist(), "v_kms": g.v("pursuer").tolist()},
        "evader": {"r_km": g.r("evader").tolist(), "v_kms": g.v("evader").tolist()},
    }


# ------------------------------------------------------------------ 分析
def _perigee_alt(r, v, mu=EARTH_MU):
    """近地點高度 km。用 r_p = h²/(μ(1+e))：橢圓、雙曲線（飛掠）、拋物線都成立（舊版 sma <= 0 回傳 nan）。"""
    r = np.asarray(r, dtype=float)
    v = np.asarray(v, dtype=float)
    h = np.cross(r, v)
    h2 = float(h @ h)
    energy = float(v @ v) / 2.0 - mu / float(np.linalg.norm(r))
    e = math.sqrt(max(0.0, 1.0 + 2.0 * energy * h2 / mu ** 2))
    return h2 / (mu * (1.0 + e)) - RE_VAL


def _orbit_type(r, v, mu=EARTH_MU):
    """'elliptic' 或 'hyperbolic (v∞ x.xx km/s)'（飛掠方）。"""
    energy = float(np.dot(v, v)) / 2.0 - mu / float(np.linalg.norm(r))
    return f"hyperbolic (v_inf {math.sqrt(2.0 * energy):.2f} km/s)" if energy > 0 else "elliptic"


def situation(g):
    R = g.rules
    horizon = min(g.time_left, 2 * g.period("pursuer"))
    ca_d, ca_t, _ = closest_approach(g.r("pursuer"), g.v("pursuer"), g.r("evader"), g.v("evader"), horizon,
                                     60.0, g.mu, R.gravity_degree)
    need_s, tof_s = pursuer_need(g, horizon=need_horizon(g))
    need_f, tof_f = pursuer_need(g)
    B = rsw_basis(g.r("pursuer"), g.v("pursuer"))
    return {
        "t": g.t, "time_left": g.time_left, "mover": g.mover,
        "distance_km": g.distance(),
        "rel_pos_rsw_km (evader wrt pursuer)": (B @ (g.r("evader") - g.r("pursuer"))).round(3).tolist(),
        "coast_closest_approach_km": ca_d, "coast_closest_approach_in_sec": ca_t,
        "capture_radius_km": R.capture_radius_km,
        "pursuer_need_short_mps": need_s, "pursuer_need_short_tof": tof_s,
        "pursuer_need_full_mps": need_f, "pursuer_need_full_tof": tof_f,
        "fuel_left": {s: g.fuel_left(s) for s in ("pursuer", "evader")},
        "burn_cap": {s: g.burn_cap(s) for s in ("pursuer", "evader")},
        "perigee_alt_km": {s: _perigee_alt(g.r(s), g.v(s)) for s in ("pursuer", "evader")},
        "orbit_type": {s: _orbit_type(g.r(s), g.v(s)) for s in ("pursuer", "evader")},
        "coast_is_safe": {s: orbit_survives(g, s, np.zeros(3)) for s in ("pursuer", "evader")},
    }


def rollout(g, side, plan, my_agent, opp_agent, stop=None):
    """我方先照 plan（[(偏移秒數, Δv)]）下完這回合，之後我方交給 my_agent、對手交給 opp_agent 下到比賽結束。

    stop（可選，快速模式用）：每回合開始前呼叫 stop(h)，回傳 True 就中止推演、回傳 None。"""
    h = g.clone()
    if h.rules.burns_per_turn <= 1:
        h.play_turn(plan[0][1])
    else:
        h.play_plan(plan)
    while not h.done:
        if stop is not None and stop(h):
            return None
        take_turn(h, my_agent if h.mover == side else opp_agent)
    s = h.summary()
    s["we_win"] = h.winner == side
    return s


def burn_formats(g, side, dv_eci_mps):
    return burn_formats_rv(g.r(side), g.v(side), dv_eci_mps)


def plan_formats(g, side, plan):
    """多發計畫的每一發（偏移秒數 + 各座標系 Δv）；VNB/RSW 用推那一刻的軌道狀態換算。"""
    if len(plan) == 1 and plan[0][0] == 0.0:
        return [{"offset_sec": 0.0, **burn_formats(g, side, plan[0][1])}]
    h = g.clone()
    h.history = []
    rec = h.play_plan(plan) if plan else None
    out = []
    for b in (rec["burns"] if rec else []):
        if b["dv_mps"] > 0.0:
            out.append({"offset_sec": b["t"] - rec["t"], **burn_formats_rv(b["r_before"], b["v_before"], b["dv_eci_mps"])})
    return out


def burn_formats_rv(r, v, dv_eci_mps):
    return {
        "eci_mps": np.asarray(dv_eci_mps).round(4).tolist(),
        "eci_kms (EarthMJ2000Eq, like official Burn Table)": (np.asarray(dv_eci_mps) / 1000).round(7).tolist(),
        "vnb_kms (GMAT ImpulsiveBurn Axes=VNB)": (vnb_basis(r, v) @ dv_eci_mps / 1000).round(7).tolist(),
        "rsw_mps (radial, along-track, cross-track)": (rsw_basis(r, v) @ dv_eci_mps).round(3).tolist(),
        "magnitude_mps": float(np.linalg.norm(dv_eci_mps)),
    }


def _with_workers(b, workers):
    """rollout 大腦加上平行推演的 worker 數（字串或 dict 規格都可以）。"""
    if b in ("rollout_pursuer", "rollout_evader"):
        return {"name": b, "workers": workers}
    if isinstance(b, dict) and b.get("name") in ("rollout_pursuer", "rollout_evader") and "workers" not in b:
        return {**b, "workers": workers}
    return b


def _default_workers():
    return int(os.environ.get("COPILOT_WORKERS", max(1, min(8, (os.cpu_count() or 2) - 2))))


def default_brains(side, workers=None):
    """advise 預設的大腦清單：DEFAULT_BRAINS（rollout 大腦帶 worker 數）+ 部署的 RL 策略。"""
    workers = _default_workers() if workers is None else int(workers)
    brains = [_with_workers(b, workers) for b in DEFAULT_BRAINS[side]]
    deployed = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", f"{side}.zip")
    if os.path.exists(deployed):              # tools/promote_model.py 部署的 RL 策略自動加入
        brains.append("sb3:" + deployed)
    return brains


def _advice_scan_scope(func):
    @wraps(func)
    def scoped(st, *args, **kwargs):
        if not scan_reuse_enabled():
            return func(st, *args, **kwargs)
        # 根局勢的大腦共用；各條推演遇到其他狀態時由 act / _candidates 另開範圍。
        with decision_scope(game_from_state(st)):
            return func(st, *args, **kwargs)
    return scoped


@_advice_scan_scope
def advise(st, brains=None, opp_models=None, rollouts=True, log=print, *, prune=False, budget_sec=None,
           workers=None, with_situation=True, rank="worst"):
    """預設（prune=False、budget_sec=None）：每個大腦的建議 × 每個對手模型推演到終局，全部做完再排序。

    可選（任一個有設就走 _advise_staged，大腦一個一個做「決策 → 推演表」）：
      prune=True      推演中途就確定某大腦不可能成為 ★ 時停掉它的推演表；★ 與不剪枝完全相同
      budget_sec=S    超過 S 秒就停：還沒開始的大腦跳過、推到一半的推演表作廢，★ 只在推演表完整的大腦裡選
      with_situation=False  不算戰況（agent 用）
      rank="wins"     ★ 改成先比贏幾個對手模型（rank_advice 的 order；預設 "worst" = 先比最壞）
    workers：rollout 大腦的平行 worker 數（None = 環境變數 COPILOT_WORKERS 或預設）。"""
    if prune or budget_sec is not None or not with_situation or rank != "worst":
        return _advise_staged(st, brains, opp_models, rollouts, prune, budget_sec, workers, with_situation, rank)
    g = game_from_state(st)
    side = st["role"]
    if not brains:
        brains = default_brains(side, workers)
    opp_models = opp_models or DEFAULT_OPP_MODELS[side]
    out = {"situation": situation(g), "advice": []}
    if g.done:
        out["note"] = f"比賽已結束：{g.outcome}"
        return out
    if g.mover != side:
        out["note"] = f"現在輪到 {g.mover}，不是我方（{side}）——以下建議是假設我方現在行動"
        g.mover = side
    opps = [(o, make_agent(o)) for o in opp_models]
    for b in brains:
        table_cont = b.get("_table_cont") if isinstance(b, dict) else None
        if table_cont is not None:
            b = {k: v for k, v in b.items() if k != "_table_cont"}
        agent = make_agent(b)
        table_agent = make_agent(table_cont) if table_cont is not None else agent   # 推演表的後續步
        t0 = time.perf_counter()
        if g.rules.burns_per_turn <= 1:
            dv = g.clip_dv(side, agent.act(g, side))
            plan = [(0.0, dv)]
        else:                                     # 一回合多發（HAP-107）：整個窗口的計畫
            plan = plan_turn(g, agent)
            dv = plan[0][1] if plan and plan[0][0] == 0.0 else np.zeros(3)
        entry = {"brain": b, "decide_sec": time.perf_counter() - t0, "burn": burn_formats(g, side, dv),
                 "plan": plan_formats(g, side, plan),
                 "safe_after_burn": orbit_survives(g, side, dv), "rollouts": []}
        if rollouts:
            for name, oa in opps:
                oa.reset(seed=0)
                entry["rollouts"].append({"opponent": name, **rollout(g, side, plan, table_agent, oa)})
        out["advice"].append(entry)
    if rollouts and out["advice"]:
        out["ranking"] = rank_advice(out["advice"], side)
    return out


def _rollout_value(r, side):
    """推演結果的分數（我方視角，越大越好）：贏 > 輸；贏時早抓到/剩油多，輸時追者看距離、躲者看撐多久。"""
    if r["we_win"]:
        fuel_used = r["used_pursuer_mps"] if side == "pursuer" else r["used_evader_mps"]
        return 1000.0 - 1e-3 * fuel_used - (1e-3 * r["t_end"] if side == "pursuer" else 0.0)
    if side == "pursuer":
        return -min(r["min_dist_km"], 1e5)
    return r["t_end"] / 100.0


def rank_advice(advice, side, order="worst"):
    """依推演表排序大腦：先看「對所有對手模型的最壞結果」，再看平均（HAP-108 教訓：預設大腦
    自己用的對手模型較弱，第一建議不一定是推演表上最好的）。

    order="wins"（可選，見 docs/notes/copilot_eval.md）：先比贏幾個對手模型，再比最壞、平均。"""
    rows = []
    for a in advice:
        vals = [_rollout_value(r, side) for r in a["rollouts"]]
        if not vals:
            continue
        rows.append({"brain": a["brain"], "worst": min(vals), "mean": float(np.mean(vals)),
                     "wins": sum(r["we_win"] for r in a["rollouts"]), "n": len(vals)})
    if order == "wins":
        rows.sort(key=lambda x: (x["wins"], x["worst"], x["mean"]), reverse=True)
    else:
        rows.sort(key=lambda x: (x["worst"], x["mean"]), reverse=True)
    return rows


# ------------------------------------------------------------------ 快速模式（advise 的 prune / budget_sec）
PRUNE_EPS = 1e-9


def _value_upper_bound(h, side):
    """推演還沒結束時，最後 _rollout_value 的上界：我方已用燃料、時間只增不減。
    贏：追者 1000 − 1e-3·(燃料 + t)、躲者 1000 − 1e-3·燃料；輸：追者 −最近距離 ≤ 0、躲者 t_end/100 ≤ t_max/100。"""
    if side == "pursuer":
        return max(1000.0 - 1e-3 * h.used["pursuer"] - 1e-3 * h.t, 0.0)
    return max(1000.0 - 1e-3 * h.used["evader"], h.t_max / 100.0)


def _rollout_stop(side, thr, deadline, why):
    def stop(h):
        if thr is not None and _value_upper_bound(h, side) < thr - PRUNE_EPS:
            why["status"] = "pruned"
            return True
        if deadline is not None and time.perf_counter() > deadline:
            why["status"] = "timeout"
            return True
        return False
    return stop


def _spec_key(spec):
    """續行 agent 規格的正規化（去掉 workers：平行與否結果相同）。"""
    if isinstance(spec, dict):
        kw = {k: v for k, v in spec.items() if k not in ("workers", "_table_cont")}
        return kw["name"] if len(kw) == 1 else json.dumps(kw, sort_keys=True, default=str)
    return str(spec)


def _prune_threshold(best, rank, cap):
    """推演中途的剪枝門檻：這個推演的分數上界低於它，這個大腦就不可能贏過目前最佳（cap = 最多還能贏幾個）。"""
    if best is None:
        return None
    if rank == "wins":
        return best[1] if cap <= best[0] else None
    return best[0]


def _beaten(best, rank, cap, worst_so_far):
    """已做完的推演就足以確定這個大腦的排序鍵輸給目前最佳。"""
    if rank == "wins":
        return cap < best[0] or (cap == best[0] and worst_so_far < best[1] - PRUNE_EPS)
    return worst_so_far < best[0] - PRUNE_EPS


def _advise_staged(st, brains, opp_models, rollouts, prune, budget_sec, workers, with_situation, rank="worst"):
    """大腦依序「決策 → 推演表」。★ 只在推演表完整（table_status == "complete"）的大腦裡選。

    剪枝（prune）：目前最佳大腦（推演表完整、排序鍵最大）的最壞分數 = 門檻；某大腦任一推演的分數
    （或推演中途的上界）低於門檻，它的排序鍵一定輸給目前最佳 → 不可能是 ★，停掉（rank="wins" 時再加上
    「最多還能贏幾個」的條件）。對手模型順序、同一個大腦物件連續推演（EscapeEvader 這類有狀態的大腦）都跟
    預設一樣，所以 ★ 與不剪枝相同。
    推演重用：續行是 RolloutPlanner（無狀態）、計畫逐位元相同、續行規格相同的推演直接沿用結果（強化版 rollout
    追者的推演表續行就是預設 rollout 追者，第一發常常一樣）。"""
    from agents.rollout import RolloutPlanner
    t_start = time.perf_counter()
    deadline = None if budget_sec is None else t_start + float(budget_sec)
    g = game_from_state(st)
    side = st["role"]
    if not brains:
        brains = default_brains(side, workers)
    opp_models = opp_models or DEFAULT_OPP_MODELS[side]
    out = {"situation": situation(g) if with_situation else None, "advice": []}
    if g.done:
        out["note"] = f"比賽已結束：{g.outcome}"
        return out
    if g.mover != side:
        out["note"] = f"現在輪到 {g.mover}，不是我方（{side}）——以下建議是假設我方現在行動"
        g.mover = side
    stats = {"prune": bool(prune), "budget_sec": budget_sec, "pruned": [], "timeout": [], "skipped": [],
             "rollouts_run": 0, "rollouts_reused": 0}
    opps = [(o, make_agent(o)) for o in opp_models]
    memo = {}                                     # (計畫, 續行規格, 對手模型序號) → 推演結果
    best = None                                   # 目前最佳大腦的 (最壞, 平均)
    for i, b in enumerate(brains):
        if deadline is not None and i > 0 and (stats["timeout"] or time.perf_counter() > deadline):
            stats["skipped"].append(b)
            continue
        table_cont = b.get("_table_cont") if isinstance(b, dict) else None
        if table_cont is not None:
            b = {k: v for k, v in b.items() if k != "_table_cont"}
        agent = make_agent(b)
        table_agent = make_agent(table_cont) if table_cont is not None else agent
        t0 = time.perf_counter()
        if g.rules.burns_per_turn <= 1:
            dv = g.clip_dv(side, agent.act(g, side))
            plan = [(0.0, dv)]
        else:
            plan = plan_turn(g, agent)
            dv = plan[0][1] if plan and plan[0][0] == 0.0 else np.zeros(3)
        entry = {"brain": b, "decide_sec": time.perf_counter() - t0, "burn": burn_formats(g, side, dv),
                 "plan": plan_formats(g, side, plan), "safe_after_burn": orbit_survives(g, side, dv),
                 "rollouts": [],
                 "plan_raw": [[float(o), np.asarray(d, dtype=np.float64).tolist()] for o, d in plan]}
        out["advice"].append(entry)
        if not rollouts:
            continue
        why = {"status": "complete"}
        tkey = None
        if isinstance(table_agent, RolloutPlanner):
            tkey = (tuple((float(o), tuple(np.asarray(d, dtype=np.float64).tolist())) for o, d in plan),
                    _spec_key(table_cont if table_cont is not None else b))
        vals, wins = [], 0
        for k, (name, oa) in enumerate(opps):
            if tkey is not None and (tkey, k) in memo:
                r = memo[(tkey, k)]
                stats["rollouts_reused"] += 1
            else:
                thr = _prune_threshold(best, rank, len(opps) - (len(vals) - wins)) if prune else None
                stop = _rollout_stop(side, thr, deadline, why) if (thr is not None or deadline is not None) else None
                oa.reset(seed=0)
                r = rollout(g, side, plan, table_agent, oa, stop=stop)
                if r is None:
                    break
                stats["rollouts_run"] += 1
                if tkey is not None:
                    memo[(tkey, k)] = r
            entry["rollouts"].append({"opponent": name, **r})
            vals.append(_rollout_value(r, side))
            wins += bool(r["we_win"])
            if prune and best is not None and _beaten(best, rank, len(opps) - (len(vals) - wins), min(vals)):
                why["status"] = "pruned"
                break
        entry["table_status"] = why["status"]
        if why["status"] == "complete":
            key = (min(vals), float(np.mean(vals)))
            if rank == "wins":
                key = (wins,) + key
            if best is None or key > best:
                best = key
        else:
            stats[why["status"]].append(b)
    if rollouts:
        done = [a for a in out["advice"] if a.get("table_status") == "complete"]
        if done:
            out["ranking"] = rank_advice(done, side, rank)
    out["rank"] = rank
    stats["elapsed_sec"] = time.perf_counter() - t_start
    out["staged"] = stats
    return out


def print_advice(out, side):
    s = out["situation"]
    print("=" * 78)
    print(f"戰況  t={s['t']:.0f}s  剩 {s['time_left']:.0f}s  輪到 {s['mover']}  我方={side}")
    print(f"  距離 {s['distance_km']:.2f} km   純滑行最近接近 {s['coast_closest_approach_km']:.2f} km "
          f"@ +{s['coast_closest_approach_in_sec']:.0f}s（捕獲半徑 {s['capture_radius_km']} km）")
    print(f"  追者攔截所需 Δv：短程 {s['pursuer_need_short_mps']:.1f} m/s (tof {s['pursuer_need_short_tof']:.0f}s)"
          f"   全程 {s['pursuer_need_full_mps']:.1f} m/s (tof {s['pursuer_need_full_tof']:.0f}s)")
    print(f"  剩餘燃料 P {s['fuel_left']['pursuer']:.0f} / E {s['fuel_left']['evader']:.0f} m/s   "
          f"單發上限 P {s['burn_cap']['pursuer']:.0f} / E {s['burn_cap']['evader']:.0f}")
    print(f"  近地點高度 P {s['perigee_alt_km']['pursuer']:.0f} / E {s['perigee_alt_km']['evader']:.0f} km   "
          f"不推也安全 P={s['coast_is_safe']['pursuer']} E={s['coast_is_safe']['evader']}")
    types = s.get("orbit_type", {})
    hyp = [f"{k} {types[k]}" for k in ("pursuer", "evader") if types.get(k, "elliptic") != "elliptic"]
    if hyp:
        print("  飛掠：" + "、".join(hyp))
    if out.get("note"):
        print("  ⚠️ " + out["note"])
    for a in out["advice"]:
        b = a["burn"]
        print("-" * 78)
        print(f"大腦 {a['brain']}（{a['decide_sec']:.2f}s）  |Δv| = {b['magnitude_mps']:.2f} m/s  推完安全={a['safe_after_burn']}")
        print(f"  ECI  km/s : {b['eci_kms (EarthMJ2000Eq, like official Burn Table)']}")
        print(f"  VNB  km/s : {b['vnb_kms (GMAT ImpulsiveBurn Axes=VNB)']}")
        print(f"  RSW  m/s  : {b['rsw_mps (radial, along-track, cross-track)']}")
        if len(a.get("plan", [])) > 1 or (a.get("plan") and a["plan"][0]["offset_sec"] > 0.0):
            print(f"  多發計畫（{len(a['plan'])} 發，總 {sum(p['magnitude_mps'] for p in a['plan']):.1f} m/s）：")
            for p in a["plan"]:
                print(f"    +{p['offset_sec']:6.1f}s  |Δv|={p['magnitude_mps']:7.2f}  "
                      f"ECI km/s {p['eci_kms (EarthMJ2000Eq, like official Burn Table)']}  "
                      f"VNB km/s {p['vnb_kms (GMAT ImpulsiveBurn Axes=VNB)']}")
        for r in a["rollouts"]:
            print(f"    vs {str(r['opponent']):<40} → {r['outcome']:<14} {'WIN ' if r['we_win'] else 'LOSE'} "
                  f"t={r['t_end']:.0f}s  最近 {r['min_dist_km']:.1f} km  燃料用 P {r['used_pursuer_mps']:.0f} / E {r['used_evader_mps']:.0f}")
        status = a.get("table_status")
        if status == "pruned":
            print("    （剪枝：推演已確定輸給目前最佳大腦的最壞情況，不可能是 ★，其餘推演略過）")
        elif status == "timeout":
            print("    （超過時間預算，推演表沒做完，不列入排序）")
    st = out.get("staged")
    if st:
        msg = f"快速模式：用時 {st['elapsed_sec']:.1f}s"
        if st.get("budget_sec") is not None:
            msg += f"（預算 {st['budget_sec']:g}s）"
        msg += f"；剪枝 {len(st['pruned'])} 個大腦、超時 {len(st['timeout'])} 個、跳過 {len(st['skipped'])} 個"
        print("-" * 78)
        print(msg)
        for b in st["skipped"]:
            print(f"  跳過（時間不夠）：{b}")
    if out.get("ranking"):
        print("=" * 78)
        if out.get("rank") == "wins":
            print("推演表排序（先比贏幾個對手模型、再比最壞情況、再比平均）：")
        else:
            print("推演表排序（先比最壞情況、再比平均）：")
        for i, row in enumerate(out["ranking"]):
            mark = "★ 推薦" if i == 0 else "      "
            print(f"  {mark} {str(row['brain']):<50} 贏 {row['wins']}/{row['n']} 個對手模型")


def _play_advice(g, entry):
    """照某個大腦的建議下完這個回合（單發用 burn、多發用 plan）。"""
    if g.rules.burns_per_turn <= 1:
        return g.play_turn(np.asarray(entry["burn"]["eci_mps"]))
    return g.play_plan([(p["offset_sec"], np.asarray(p["eci_mps"])) for p in entry["plan"]])


def _parse_specs(s):
    if not s:
        return None
    return [json.loads(t) if t.strip().startswith("{") else t.strip() for t in s.split(";" if ";" in s else ",")]


# ------------------------------------------------------------------ CLI
def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv and argv[0] == "final":
        # 金／銅牌賽（同時出手）流程在 final_copilot.py；舊指令照舊
        import final_copilot
        return final_copilot.main(argv[1:])
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="產生局勢檔範本")
    p.add_argument("path")

    p = sub.add_parser("import", help="讀 GMAT ReportFile 更新局勢檔（免手抄）")
    p.add_argument("path", help="局勢檔（會被更新）")
    p.add_argument("report", help="GMAT ReportFile")
    p.add_argument("--pursuer-ship", required=True, help="報表裡追者的 Spacecraft 名稱")
    p.add_argument("--evader-ship", required=True, help="報表裡躲者的 Spacecraft 名稱")
    p.add_argument("--row", type=int, default=-1, help="取第幾列（預設最後一列）")
    p.add_argument("--columns", default=None, help="報表沒有表頭時的欄名（空白分隔）")
    p.add_argument("--t-offset", type=float, default=0.0, help="報表 ElapsedSecs 與比賽時間的差")
    p.add_argument("--mover", default=None, help="現在輪到誰（pursuer/evader）")
    p.add_argument("--fuel-used", nargs=2, type=float, default=None, metavar=("P", "E"),
                   help="雙方已用燃料 m/s")

    p = sub.add_parser("advise", help="讀局勢檔，給建議")
    p.add_argument("path")
    p.add_argument("--brains", default=None, help="逗號分隔 agent 規格（可含 sb3:path）")
    p.add_argument("--opponents", default=None, help="推演用的對手模型")
    p.add_argument("--no-rollout", action="store_true")
    p.add_argument("--prune", action="store_true",
                   help="剪掉不可能成為 ★ 的推演（★ 與完整推演相同，只是更快；推演表只列做完的）")
    p.add_argument("--budget-sec", type=float, default=None,
                   help="時間預算（秒）：超過就停，★ 只在推演表做完的大腦裡選（建議配 --prune）")
    p.add_argument("--rank", default="worst", choices=["worst", "wins"],
                   help="★ 排序：worst = 先比最壞再比平均（預設）、wins = 先比贏幾個對手模型")
    p.add_argument("--gmat", default=None, help="把第一個大腦的建議輸出成 GMAT 腳本")
    p.add_argument("--verify", action="store_true", help="用本機 GmatConsole 跑腳本並比對")
    p.add_argument("--json", default=None, help="完整結果另存 JSON")

    p = sub.add_parser("drill", help="模擬整場演練")
    p.add_argument("--role", default="pursuer")
    p.add_argument("--opponent", default=None)
    p.add_argument("--rules", default="default", help="default / ranges / 規則 JSON 檔")
    p.add_argument("--scenario", default="near_coplanar")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--brains", default=None)
    p.add_argument("--interactive", action="store_true")
    p.add_argument("--no-rollout", action="store_true")

    args = ap.parse_args(argv)

    if args.cmd == "init":
        with open(args.path, "w") as f:
            json.dump(template_state(), f, indent=2, ensure_ascii=False)
        print(f"→ {args.path}")
        return 0

    if args.cmd == "import":
        from game.state_io import apply_report_to_state, read_gmat_report
        with open(args.path) as f:
            st = json.load(f)
        rec = read_gmat_report(args.report, args.columns.split() if args.columns else None, args.row)
        st = apply_report_to_state(st, rec, args.pursuer_ship, args.evader_ship, args.t_offset)
        if args.mover:
            st["mover"] = args.mover
        if args.fuel_used:
            st["fuel_used_mps"] = {"pursuer": args.fuel_used[0], "evader": args.fuel_used[1]}
        game_from_state(st)                       # 建得起來才寫回（再做一次整體檢查）
        with open(args.path, "w") as f:
            json.dump(st, f, indent=2, ensure_ascii=False)
        g = game_from_state(st)
        print(f"→ {args.path} 已更新：t={g.t:.1f}s  距離 {g.distance():.3f} km  輪到 {g.mover}")
        return 0

    if args.cmd == "advise":
        with open(args.path) as f:
            st = json.load(f)
        out = advise(st, _parse_specs(args.brains), _parse_specs(args.opponents), not args.no_rollout,
                     prune=args.prune, budget_sec=args.budget_sec, rank=args.rank)
        print_advice(out, st["role"])
        if args.json:
            with open(args.json, "w") as f:
                json.dump(out, f, indent=2, default=float, ensure_ascii=False)
        if args.gmat and out["advice"]:
            from tools.gmat_verify import earth_gate_lines, game_to_script, verify_game
            g = game_from_state(st)
            g.mover = st["role"]
            fresh = Game(g.rules.with_(t_max_sec=g.t + g.next_window() + 1.0), g.r("pursuer"), g.v("pursuer"),
                         g.r("evader"), g.v("evader"))
            fresh.mover = st["role"]
            fresh.used = dict(g.used)
            _play_advice(fresh, out["advice"][0])
            with open(args.gmat, "w") as f:
                f.write(game_to_script(fresh, os.path.abspath(os.path.splitext(args.gmat)[0] + "_report.txt")))
            print(f"→ GMAT 腳本 {args.gmat}（施加建議脈衝並滑行 {fresh.history[0]['coast_sec']:.0f}s）")
            if args.verify:
                v = verify_game(fresh)
                print(f"  GMAT 比對：位置差 {1000 * v['max_dpos_km']:.2f} m、窗口末距離 ours/GMAT = "
                      f"{v['final_dist_ours_km']:.4f} / {v['final_dist_gmat_km']:.4f} km")
                for line in earth_gate_lines(v):
                    print("  " + line)
        return 0

    if args.cmd == "drill":
        rng = np.random.default_rng(args.seed)
        from game.rules import RuleRanges
        if args.rules == "ranges":
            R = RuleRanges().sample(rng)
        elif args.rules == "default":
            R = Rules()
        else:
            R = Rules.from_dict(json.load(open(args.rules)))
        sc = sample_scenario(rng, args.scenario)
        g = Game.from_elements(R, sc.orbit_pursuer, sc.orbit_evader)
        side = args.role
        opp = make_agent(args.opponent or ("dv_evader" if side == "pursuer" else "lambert_pursuer"))
        brains = _parse_specs(args.brains) or DEFAULT_BRAINS[side]
        while not g.done:
            if g.mover != side:
                take_turn(g, opp)
                continue
            st = state_from_game(g, side)
            out = advise(st, brains, None, not args.no_rollout)
            print_advice(out, side)
            k = 0
            if out.get("ranking"):                    # 預設採用推演表排序第一的大腦
                top = out["ranking"][0]["brain"]
                k = next(i for i, a in enumerate(out["advice"]) if a["brain"] == top)
            if args.interactive:
                ans = input(f"採用第幾個大腦的建議？[0-{len(out['advice']) - 1}，或輸入 eci m/s 三個數字] ").strip()
                parts = ans.split()
                if len(parts) == 3:
                    g.play_turn(np.array([float(x) for x in parts]))
                    continue
                k = int(ans or 0)
            _play_advice(g, out["advice"][k])
        print("=" * 78)
        print("比賽結束：", g.summary(), "我方", "勝" if g.winner == side else "敗")
        return 0


if __name__ == "__main__":
    sys.exit(main())
