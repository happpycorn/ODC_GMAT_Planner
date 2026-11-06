"""copilot「★ 推薦」當 agent（清單第 5 項；研究筆記 docs/notes/copilot_eval.md）。

當天每回合照 `copilot.py advise` 的 ★ 推薦下：各大腦的建議 × 對手模型推演到終局，先比最壞再比平均
（copilot.rank_advice）。這個 agent 把同一套流程搬進對打評測：

    make_agent("py:agents.copilot_agent:CopilotAgent")
    evaluate.py --evaders "py:agents.copilot_agent:CopilotAgent;lazy_evader" ...

* 每次 act：copilot.state_from_game → copilot.advise（預設大腦、預設對手模型）→ ★ 大腦的這一發，
  用原始 Δv（advise 印出的 ECI m/s 四捨五入到 1e-4 m/s，差別可忽略）。
* prune=True（預設）：推演表只做到能確定 ★ 為止（copilot.advise 的 prune），★ 與完整 advise 相同；
  prune=False 就是完整推演（一樣的 ★，只是慢）。budget_sec：copilot 的時間預算模式（★ 可能不同）。
  rank="wins"：★ 改成先比贏幾個對手模型（copilot.rank_advice 的 order；評測用的候選修正）。
* 多發規則（burns_per_turn > 1）：窗口開始時跑一次 advise、記住 ★ 大腦整個窗口的計畫；take_turn 在窗口
  中途再問時照計畫回傳那個時刻的那一發——等同當天「每回合跑一次 copilot、照 ★ 的多發計畫輸入」。
* 評測時設 COPILOT_WORKERS=1（或 workers=1）：每局在單一行程裡跑，總行程數 = evaluate.py --workers。
* log_dir（或環境變數 COPILOT_AGENT_LOG）：每次決策寫一行 JSON（★、各大腦推演表狀態、用時），供事後分析。
"""
import json
import os
import time

import numpy as np

import copilot
from agents.base import Agent

_STRONG = {k: v for k, v in copilot.STRONG_ROLLOUT_PURSUER.items() if k != "_table_cont"}


def brain_label(spec):
    """大腦規格的短名稱（去掉 workers；強化版 rollout 追者 → strong_rollout_pursuer）。"""
    if isinstance(spec, str):
        return "sb3:" + os.path.basename(spec[4:]) if spec.startswith("sb3:") else spec
    if isinstance(spec, dict):
        kw = {k: v for k, v in spec.items() if k not in ("workers", "_table_cont")}
        if kw == _STRONG:
            return "strong_rollout_pursuer"
        name = kw.pop("name")
        return name + ("(" + ",".join(f"{k}={v}" for k, v in sorted(kw.items())) + ")" if kw else "")
    return str(spec)


class CopilotAgent(Agent):
    name = "copilot"

    def __init__(self, brains=None, opponents=None, prune=True, budget_sec=None, workers=None, log_dir=None,
                 rank="worst", name="copilot"):
        self.brains = brains
        self.opponents = opponents
        self.prune = bool(prune)
        self.budget_sec = budget_sec
        self.rank = rank
        self.workers = workers
        self.log_dir = log_dir if log_dir is not None else os.environ.get("COPILOT_AGENT_LOG")
        self.name = name
        self.seed = None
        self._plan = None              # (窗口 key, [(偏移秒數, Δv)])：★ 大腦這個窗口的計畫
        self.decisions = []            # 這一局每次 advise 的紀錄

    def reset(self, seed=None):
        self.seed = seed
        self._plan = None
        self.decisions = []

    @staticmethod
    def _window_key(game, side):
        t0 = game._pending["t"] if game.mid_window else game.t
        return (side, game.turn, float(t0))

    def act(self, game, side):
        key = self._window_key(game, side)
        if game.mid_window and self._plan is not None and self._plan[0] == key:
            off = game._window_used()[0]
            for o, dv in self._plan[1]:
                if abs(o - off) < 1e-6:
                    return dv.copy()
            return np.zeros(3)
        st = copilot.state_from_game(game, side)
        t0 = time.perf_counter()
        out = copilot.advise(st, self.brains, self.opponents, True, prune=self.prune, budget_sec=self.budget_sec,
                             workers=self.workers, with_situation=False, rank=self.rank)
        sec = time.perf_counter() - t0
        advice = out["advice"]
        k = 0                                      # 沒有排序（預算不夠）時用第一個大腦
        if out.get("ranking"):
            top = out["ranking"][0]["brain"]
            k = next(i for i, a in enumerate(advice) if a["brain"] == top)
        plan = [(float(o), np.asarray(d, dtype=np.float64)) for o, d in advice[k]["plan_raw"]]
        self._record(game, side, out, k, plan, sec)
        if game.mid_window:                        # 窗口中途、沒有這個窗口的計畫：快照當新窗口算，只取現在這一發
            return next((dv.copy() for o, dv in plan if o == 0.0), np.zeros(3))
        self._plan = (key, plan)
        return next((dv.copy() for o, dv in plan if abs(o) < 1e-6), np.zeros(3))

    def _record(self, game, side, out, k, plan, sec):
        rank = [[brain_label(r["brain"]), r["worst"], r["mean"], r["wins"], r["n"]] for r in out.get("ranking", [])]
        st = out.get("staged") or {}
        rec = {
            "seed": self.seed, "side": side, "rank_order": self.rank, "turn": game.turn, "t": game.t,
            "t_max": game.t_max,
            "star": brain_label(out["advice"][k]["brain"]), "star_idx": k, "ranked": bool(rank),
            "dv_mps": float(sum(np.linalg.norm(d) for _, d in plan)), "sec": sec,
            "status": {brain_label(a["brain"]): a.get("table_status", "complete") for a in out["advice"]},
            "skipped": [brain_label(b) for b in st.get("skipped", [])], "rank": rank,
            "used": dict(game.used), "dist_km": game.distance(),
        }
        self.decisions.append(rec)
        if self.log_dir:
            os.makedirs(self.log_dir, exist_ok=True)
            path = os.path.join(self.log_dir, f"copilot_{side}_{os.getpid()}.jsonl")
            with open(path, "a") as f:
                f.write(json.dumps(rec, default=float, ensure_ascii=False) + "\n")
