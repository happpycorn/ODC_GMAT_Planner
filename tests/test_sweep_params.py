"""sweep_params.py 純邏輯部分的驗證（不需要 pytest，直接 `uv run python tests/test_sweep_params.py`）。

為什麼要獨立測：掃描工具一跑就是整晚，規格展開或覆寫順序錯了，要到隔天看彙整才發現
「原來那 60 次都沒套到參數」。這裡只測不用跑求解的部分：
  * grid/具名參數組展開、名稱重複要擋
  * SEED 在最外層（跑到一半停掉時每個組合都已經有前幾顆 SEED）
  * 覆寫順序：情境 config → base → 情境 overrides → 參數組 → SEED
  * run.log 解析：各案例代數、搜尋/拆棒分段秒數（含跨午夜）
"""

import json
import fcntl
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sweep_params as sp
from scripts.generate_c4_configs import build_configs

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

# ── 版控中的 sweep 規格應能直接讀取共用情境 ──
sweep_dir = Path(sp.ROOT) / "sweeps"
specs = sorted(sweep_dir.glob("*.json"))
broken = []
checked = 0
for spec_path in specs:
    with spec_path.open(encoding="utf-8") as f:
        sweep_spec = json.load(f)
    if "scenarios" not in sweep_spec:
        continue  # C4 uses generated groups, checked below.
    checked += 1
    for scenario in sweep_spec["scenarios"]:
        relative = scenario["config"]
        config_path = Path(sp.ROOT) / relative
        if not relative.startswith("configs/shared/") or not config_path.is_file():
            broken.append(f"{spec_path.name}: {relative} 未納入共用情境")
            continue
        with config_path.open(encoding="utf-8") as f:
            shared_config = json.load(f)
        if "local" in shared_config:
            broken.append(f"{relative}: 含本機設定 local")
        try:
            sp.validate_config(shared_config)
        except sp.ConfigValidationError as exc:
            broken.append(f"{relative}: {exc}")
check(f"{checked} 份 sweep 規格的情境都可從版控讀取且有效", checked > 0 and not broken)
for problem in broken:
    print("  ❌ " + problem)

c4_jobs = build_configs()
c4_broken = []
for name, config in c4_jobs.items():
    if "local" in config:
        c4_broken.append(f"{name}: 含本機設定 local")
    try:
        sp.validate_config(config)
    except sp.ConfigValidationError as exc:
        c4_broken.append(f"{name}: {exc}")
check("C4 規格可從共用情境產生 33 份有效設定", len(c4_jobs) == 33 and not c4_broken)
for problem in c4_broken:
    print("  ❌ " + problem)

# ── GMAT 路徑與封存鎖 ──
with tempfile.TemporaryDirectory() as d:
    name = "retry_case"
    run_dir = Path(d) / "runs" / name
    config_dir = Path(d) / "configs"
    run_dir.mkdir(parents=True)
    config_dir.mkdir()
    (run_dir / "run.json").write_text("old run", encoding="utf-8")
    (config_dir / f"{name}.json").write_text("old config", encoding="utf-8")
    (config_dir / f"{name}.console.log").write_text("old failure", encoding="utf-8")
    stale = Path(sp.preserve_previous_job(d, name))
    check("重跑時舊 run、設定與 console 一起保存在 stale 目錄",
          (stale / "run.json").read_text() == "old run"
          and (stale / "config.json").read_text() == "old config"
          and (stale / "console.log").read_text() == "old failure"
          and not run_dir.exists())
    (config_dir / f"{name}.console.log").write_text("failure before run dir", encoding="utf-8")
    stale_only = Path(sp.preserve_previous_job(d, name))
    check("只有 console、尚未建立 run 目錄時也保存錯誤訊息",
          stale_only != stale and (stale_only / "console.log").read_text() == "failure before run dir")

with tempfile.TemporaryDirectory() as d:
    job = {"scenario": "official_sample", "variant": "base", "seed": 0,
           "config": "configs/shared/official_sample.json", "overrides": {}}
    with patch.object(sp.subprocess, "Popen") as popen:
        running = sp.start_job(job, d, gmat=True, gmat_console="/tmp/GmatConsole")
        gmat_command = popen.call_args.args[0]
        running.console.close()
        running = sp.start_job(job, d, gmat=False, gmat_console="/tmp/GmatConsole")
        solve_command = popen.call_args.args[0]
        running.console.close()
    check("GMAT sweep 將指定的 GmatConsole 路徑交給 main.py",
          gmat_command[-2:] == ["--gmat-console", "/tmp/GmatConsole"]
          and "--stop-after" not in gmat_command)
    check("只求解的 sweep 保留原本模式，不傳 GMAT 路徑",
          solve_command[-2:] == ["--stop-after", "solve"]
          and "--gmat-console" not in solve_command)

lock_path = Path(sp.ROOT) / "outputs/sweeps/.archive.lock"
def inspect_sweep_lock(*_args):
    with lock_path.open("a+") as other:
        try:
            fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        finally:
            fcntl.flock(other, fcntl.LOCK_UN)
    return False

with patch.object(sp, "_run_sweep", side_effect=inspect_sweep_lock):
    lock_held = sp.run_sweep({}, "unused", 1, 0, False, False, False)
with lock_path.open("a+") as after:
    try:
        fcntl.flock(after, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_released = True
    except BlockingIOError:
        lock_released = False
    finally:
        if lock_released:
            fcntl.flock(after, fcntl.LOCK_UN)
check("執行 sweep 時禁止封存，結束後釋放鎖", lock_held and lock_released)

print()
if FAILS:
    print(f"❌ {len(FAILS)} 項失敗：" + "、".join(FAILS))
    sys.exit(1)
print("✅ 全部通過")
