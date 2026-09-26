"""sweep_params.py 純邏輯部分的驗證（不需要 pytest，直接 `uv run python tests/test_sweep_params.py`）。

為什麼要獨立測：掃描工具一跑就是整晚，規格展開或覆寫順序錯了，要到隔天看彙整才發現
「原來那 60 次都沒套到參數」。這裡只測不用跑求解的部分：
  * grid/具名參數組展開、名稱重複要擋
  * SEED 在最外層（跑到一半停掉時每個組合都已經有前幾顆 SEED）
  * 覆寫順序：情境 config → base → 情境 overrides → 參數組 → SEED
  * run.log 解析：各案例代數、搜尋/拆棒分段秒數（含跨午夜）
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sweep_params as sp

FAILS = []


def check(name, cond):
    print(("  ✅ " if cond else "  ❌ ") + name)
    if not cond:
        FAILS.append(name)


# ── 參數組展開 ──
spec = {
    "name": "t",
    "scenarios": [{"name": "A", "config": "a.json"},
                  {"name": "B", "config": "b.json", "overrides": {"rules.k_t": 0.5, "optimization.POPSIZE": 7}}],
    "seeds": [0, 1],
    "base": {"optimization.POPSIZE": 3, "optimization.MAX_BURNS": [1, 2]},
    "grid": {"optimization.MAXITER": [10, 20], "strategy.REVS_ENSEMBLE": [True, False]},
    "variants": {"big": {"optimization.MAXITER": 999, "optimization.POPSIZE": 50}},
}
vs = sp.expand_variants(spec)
check("grid 2×2 + 1 具名 = 5 組", len(vs) == 5)
check("grid 名稱帶短鍵與值", vs[0][0] == "MAXITER=10,REVS_ENSEMBLE=true")
check("具名參數組排在 grid 後面", vs[-1][0] == "big")
check("沒有 grid/variants 時只有 base 一組", sp.expand_variants({"scenarios": [], "seeds": []}) == [("base", {})])
try:
    sp.plan_jobs({**spec, "scenarios": [{"name": "A", "config": "a"}, {"name": "A", "config": "b"}]})
    check("情境名稱重複要擋", False)
except ValueError:
    check("情境名稱重複要擋", True)

# ── 執行順序 ──
jobs = sp.plan_jobs(spec)
check("總數 = 2 SEED × 2 情境 × 5 組", len(jobs) == 20)
check("SEED 在最外層：前 10 個全是 seed 0", all(j["seed"] == 0 for j in jobs[:10]))
check("key 唯一", len({sp.job_key(j) for j in jobs}) == 20)

# ── 覆寫順序 ──
with tempfile.TemporaryDirectory() as d:
    base_cfg = {"rules": {"k_t": 0.1}, "optimization": {"POPSIZE": 1, "MAXITER": 1, "SEED": None},
                "strategy": {}}
    for name in ("a.json", "b.json"):
        with open(os.path.join(d, name), "w") as f:
            json.dump(base_cfg, f)
    js = sp.plan_jobs({**spec, "scenarios": [{**s, "config": os.path.join(d, s["config"])}
                                            for s in spec["scenarios"]]})
    by = {sp.job_key(j): j for j in js}
    ca = sp.build_config(by["A|MAXITER=10,REVS_ENSEMBLE=true|1"])
    cb = sp.build_config(by["B|MAXITER=10,REVS_ENSEMBLE=true|1"])
    cbig = sp.build_config(by["B|big|0"])
    check("base 蓋過情境 config（A 的 POPSIZE=3）", ca["optimization"]["POPSIZE"] == 3)
    check("情境 overrides 蓋過 base（B 的 POPSIZE=7）", cb["optimization"]["POPSIZE"] == 7)
    check("參數組蓋過情境 overrides（B|big 的 POPSIZE=50）", cbig["optimization"]["POPSIZE"] == 50)
    check("情境 overrides 套到 rules", cb["rules"]["k_t"] == 0.5 and ca["rules"]["k_t"] == 0.1)
    check("grid 值套到了", ca["optimization"]["MAXITER"] == 10 and ca["strategy"]["REVS_ENSEMBLE"] is True)
    check("SEED 最後設定", ca["optimization"]["SEED"] == 1 and cbig["optimization"]["SEED"] == 0)
    check("list 值是複本（改一份不影響別份）",
          ca["optimization"]["MAX_BURNS"] is not sp.build_config(by["A|big|0"])["optimization"]["MAX_BURNS"])

    # ── run.log 解析 ──
    rd = os.path.join(d, "run")
    os.makedirs(rd)
    with open(os.path.join(rd, "run.log"), "w", encoding="utf-8") as f:
        f.write("23:59:50 INFO  📂 本次輸出：x\n"
                "23:59:55 INFO  ✅ 推進 1 次完成：目標值 -79.1469，跑了 10/10 代，單執行緒\n"
                "00:00:05 INFO  ✅ 推進 2 次完成：目標值 -80.3904，跑了 7/10 代，單執行緒\n"
                "00:00:10 DEBUG 💾 拆棒前贏家已存檔：x\n"
                "🔧 HAP-67 自動拆分：沒有時間戳的行\n"
                "00:01:40 INFO  💾 求解結果已保存：x\n")
    r = sp.collect_result(rd)
    check("解析兩個案例與代數", [(c["burns"], c["gens"]) for c in r["cases"]] == [(1, 10), (2, 7)])
    check("搜尋秒數跨午夜 = 20", r["search_sec"] == 20)
    check("拆棒秒數 = 90", r["split_sec"] == 90)
    check("沒有 mission.json 時 final 為 None（呼叫端判 no_result）", r["final"] is None)

print()
if FAILS:
    print(f"❌ {len(FAILS)} 項失敗：" + "、".join(FAILS))
    sys.exit(1)
print("✅ 全部通過")
