# 多發規則間隔存活放寬 A/B（ODC_GAP_SURVIVAL 0 / 1 / 2）

- **規則**：`configs/rulesets/ranking_like_2burn.json`（250/3000、2 發、間隔 100 s）、`symmetric_2burn.json`（1500/3000、2 發）、`ranking_like_3burn.json`
- **幾何**：mixed；seed 1（調參批）、seed 2（確認批）；同一 seed 各 arm 是同一批幾何，逐局配對
- **arm**：off = 0（舊行為，嚴格檢查）、on1 = 1（撐過間隔 + 救得回來）、on2 = 2（再加「間隔後一發補得完同一個攔截」）
- **欄位**：追者勝率 [Wilson 95%]；配對 = 只有 off 抓到 / 只有 on 抓到 的局數與雙尾符號檢定 p；撞地 P = crash_pursuer 局數（各 arm）；
  燃料 P = 追者平均用油 m/s（各 arm）；決策層放寬次數 = 真實決策（Lambert 追者本身、rollout 追者的候選）中「嚴格檢查不過、放寬後通過」的次數 / 窗口第一發決策數
- 指令：`ODC_GAP_SURVIVAL={0,1,2} uv run python evaluate.py --rules <規則> --scenario mixed --games 24 --seed 1 --workers 5 --pursuers "lambert_pursuer;rollout_pursuer" --evaders "dv_evader;rollout_evader"`
  （這批是用下面的診斷腳本跑的：同一個 `evaluation.tournament.play`，只多了計數，局面與 evaluate.py 相同）

## ranking_like_2burn，seed 1，24 局/配對

| 追者 | 躲者 | n | off | on1 | on2 | 配對 off→on1 | 配對 off→on2 | 撞地 P | 燃料 P | 決策層放寬次數 on1 ; on2 |
|---|---|---|---|---|---|---|---|---|---|---|
| lambert_pursuer | dv_evader | 24 | 50% [31–69] | 50% [31–69] | 50% [31–69] | 0/0, p=1 | 0/0, p=1 | 0/0/0 | 2627/2632/2629 | 4/859 ; 1/859 |
| lambert_pursuer | rollout_evader | 24 | 50% [31–69] | 50% [31–69] | 50% [31–69] | 0/0, p=1 | 0/0, p=1 | 0/0/0 | 2462/2462/2462 | 2/831 ; 1/831 |
| rollout_pursuer | dv_evader | 24 | 83% [64–93] | 83% [64–93] | 83% [64–93] | 0/0, p=1 | 0/0, p=1 | 0/0/0 | 1983/2058/1963 | 0/2996 ; 0/3040 |
| rollout_pursuer | rollout_evader | 24 | 83% [64–93] | 79% [60–91] | 83% [64–93] | 2/1, p=1 | 0/0, p=1 | 0/0/0 | 2104/2050/2116 | 4/3144 ; 4/3248 |

## symmetric_2burn，seed 1，24 局/配對

| 追者 | 躲者 | n | off | on1 | on2 | 配對 off→on1 | 配對 off→on2 | 撞地 P | 燃料 P | 決策層放寬次數 on1 ; on2 |
|---|---|---|---|---|---|---|---|---|---|---|
| lambert_pursuer | dv_evader | 24 | 8% [2–26] | 8% [2–26] | 8% [2–26] | 0/0, p=1 | 0/0, p=1 | 0/0/0 | 2997/2997/2997 | 99/1017 ; 0/1017 |
| lambert_pursuer | rollout_evader | 24 | 12% [4–31] | 12% [4–31] | 12% [4–31] | 0/0, p=1 | 0/0, p=1 | 0/0/0 | 2872/2872/2872 | 68/980 ; 0/980 |
| rollout_pursuer | dv_evader | 24 | 50% [31–69] | 50% [31–69] | 50% [31–69] | 1/1, p=1 | 0/0, p=1 | 0/1/0 | 2076/1920/2076 | 1374/3604 ; 4/3788 |
| rollout_pursuer | rollout_evader | 24 | 71% [51–85] | 62% [43–79] | 71% [51–85] | 3/1, p=0.62 | 0/0, p=1 | 0/0/0 | 2376/2407/2376 | 857/3460 ; 4/3428 |

Lambert 追者本身的救命推力次數（兩個躲者合計 48 局；窗口第 1 發 / 第 2 發）：off 133 / 137、on1 68 / 230——放寬把第 1 發的減半/救命換成大推力，
結果第 2 發多半只能救命。ranking_like_2burn 的 on1：放寬 6 次，其中 5 次下一發是救命推力。

## 撞地局重播（symmetric_2burn seed 1 第 21 局，wild 幾何，rollout 追者 vs dv_evader，on1）

| t (s) | 追者這個窗口的推力（偏移 s, m/s） | 窗口結束時嚴格安全？ |
|---|---|---|
| 600 | (0, 1500)——放寬候選；第 2 問選了零 | 否 |
| 1200 | 不推（選零候選） | 否 |
| 1800 | 不推（選零候選） | 否 |
| 2408 | 撞地 | — |

最近距離 11,335 km，所有候選推演都輸 → 分數都是 −(歷史最近距離)/10，平手時 `RolloutPlanner` 取第一個候選（零向量），
所以從來沒有救命。off 時同一局是超時輸（追者軌道一直嚴格安全，選零無害）。

## symmetric_2burn，seed 2（沒調過參的確認批），24 局/配對，off vs on1

| 追者 | 躲者 | n | off | on1 | 配對 off→on1 | 撞地 P | 燃料 P | 決策層放寬次數 |
|---|---|---|---|---|---|---|---|---|
| lambert_pursuer | dv_evader | 24 | 8% [2–26] | 8% [2–26] | 0/0, p=1 | 0/0 | 2980/2980 | 69/975 |
| lambert_pursuer | rollout_evader | 24 | 4% [1–20] | 8% [2–26] | 0/1, p=1 | 0/0 | 2977/2978 | 20/1010 |
| rollout_pursuer | dv_evader | 24 | 33% [18–53] | 33% [18–53] | 0/0, p=1 | 0/0 | 1649/1645 | 1605/3760 |
| rollout_pursuer | rollout_evader | 24 | 42% [24–61] | 46% [28–65] | 1/2, p=1 | 0/0 | 2237/2268 | 798/3536 |

## ranking_like_3burn，seed 1，12 局/配對（n 小，只看觸發頻率與方向），off vs on1

| 追者 | 躲者 | n | off | on1 | 配對 off→on1 | 撞地 P | 燃料 P | 決策層放寬次數 |
|---|---|---|---|---|---|---|---|---|
| lambert_pursuer | dv_evader | 12 | 50% [25–75] | 50% [25–75] | 0/0, p=1 | 0/0 | 2691/2665 | 1/412 |
| lambert_pursuer | rollout_evader | 12 | 42% [19–68] | 42% [19–68] | 0/0, p=1 | 0/0 | 2551/2551 | 0/405 |
| rollout_pursuer | dv_evader | 12 | 100% [76–100] | 100% [76–100] | 0/0, p=1 | 0/0 | 2016/2046 | 4/1244 |
| rollout_pursuer | rollout_evader | 12 | 100% [76–100] | 92% [65–99] | 1/0, p=1 | 0/0 | 2017/2122 | 0/1468 |

## 合計（off → on1，所有規則/seed/配對）

只有 off 抓到 8 局、只有 on1 抓到 6 局，符號檢定 p = 0.79；只看 rollout 追者 vs rollout 躲者：7 對 4，p = 0.55。

## 診斷腳本（勝負可用 evaluate.py 重跑；決策層計數要用這個）

`ODC_GAP_SURVIVAL=1 uv run python gap_diag.py configs/rulesets/symmetric_2burn.json 24 1 out.jsonl "lambert_pursuer;rollout_pursuer" "dv_evader;rollout_evader"`

<details><summary>gap_diag.py</summary>

```python
import json, math, sys
from collections import Counter
from multiprocessing import Pool
import agents.analytic as A
import agents.rollout as RO
from evaluation.tournament import Task, make_games, play

C = Counter()
CTX = {"rollout": 0, "cand": 0, "act": None}
ctx = lambda: "sim" if CTX["rollout"] else ("cand" if CTX["cand"] else "direct")

def ask_index(game):
    gap = game.rules.min_burn_gap_sec
    off, _, _ = game._window_used()
    return int(math.floor(off / gap + 1e-6)) if gap > 0 else 0

_act, _gap, _rescue = A.LambertPursuer.act, A.gap_burn_survives, A.rescue_burn
_play_out, _cands = RO.play_out, RO.RolloutPlanner._candidates

def act(self, game, side):
    k = f"{ctx()}|ask{ask_index(game)}"
    rec = {"gap_calls": 0, "gap_true": 0, "rescue": 0}
    prev, CTX["act"] = CTX["act"], rec
    try:
        dv = _act(self, game, side)
    finally:
        CTX["act"] = prev
    C[k + "|acts"] += 1
    C[k + "|strict_fail_more_burns"] += bool(rec["gap_calls"])   # 嚴格不過且窗口內還會再推
    C[k + "|relaxed_changed"] += bool(rec["gap_true"])           # 放寬後通過 = 決策跟嚴格版不同
    C[k + "|rescue"] += bool(rec["rescue"])
    return dv

def gap(game, side, dv, g, **kw):
    rec, CTX["act"] = CTX["act"], None      # 裡面的 rescue_burn 是可救判定，不算救命推力
    try:
        ok = _gap(game, side, dv, g, **kw)
    finally:
        CTX["act"] = rec
    if rec is not None:
        rec["gap_calls"] += 1; rec["gap_true"] += int(ok)
    return ok

def rescue(game, side):
    if CTX["act"] is not None:
        CTX["act"]["rescue"] += 1
    return _rescue(game, side)

def play_out(*a, **kw):
    CTX["rollout"] += 1
    try: return _play_out(*a, **kw)
    finally: CTX["rollout"] -= 1

def cands(self, game):
    CTX["cand"] += 1
    try: return _cands(self, game)
    finally: CTX["cand"] -= 1

A.LambertPursuer.act, A.gap_burn_survives, A.rescue_burn = act, gap, rescue
RO.play_out, RO.RolloutPlanner._candidates = play_out, cands

def run(task):
    C.clear(); r = play(task); r["diag"] = dict(C); return r

if __name__ == "__main__":
    rules_path, n, seed, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    ps, es = sys.argv[5].split(";"), sys.argv[6].split(";")
    rules = json.load(open(rules_path))
    tasks = [Task(p, e, R, op, oe, fam, gi, seed * 100003 + gi)
             for gi, (R, op, oe, fam) in enumerate(make_games(n, rules, "mixed", seed)) for p in ps for e in es]
    with Pool(5) as pool, open(out, "w") as f:
        for r in pool.imap_unordered(run, tasks):
            f.write(json.dumps(r, default=float) + "\n")
```
</details>
