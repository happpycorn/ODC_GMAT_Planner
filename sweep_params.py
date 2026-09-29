"""
sweep_params.py —— 參數正式實驗的掃描工具：情境 × SEED × 參數組，每組跑一次完整求解，結果寫成 jsonl。

為什麼要有這支（見 STATUS 待辦 B）：MAXITER/POPSIZE 這些搜尋預算原本是憑感覺設的，REVS 集成、種子精修
這些開關也沒有數據撐。要下結論得同時滿足幾件事，手動一次次跑很難做到：
  * 多情境、多組計分權重——計分參數是佔位值，只在 contest.json 上調到最好對真題沒意義。
  * 多顆 SEED——SEED 雜訊（換盆地）常比參數效果大，要看中位數與最差值，不是單次分數。
  * 記時間——目標是「限時內的分數」，所以每筆都記牆鐘與 CPU 秒。
  * 固定 numba 快取狀態——evaluator 冷編譯 vs 讀快取差 1 ulp 就會讓 DE 分岔（STATUS 待辦 A），
    所以開跑前先暖快取，每次 run 也檢查快取檔有沒有被改寫（有 = 這次有冷編譯，彙整時警告）。

每次 run 用子行程跑 `main.py --stop-after solve`（與實際使用同一條管線，含 C2 與拆棒合法化；
不跑 GMAT，要驗證加 --gmat），跑完讀本次目錄的 mission.json（拆後）、winner_presplit（拆前）、
run.log（各棒數案例跑了幾代），整理成一行寫進 results.jsonl。可以隨時中斷，重跑同一份規格會跳過
已完成的組合。執行順序是 SEED 在最外層，跑到一半停掉時每個組合都已經有前幾顆 SEED。

規格檔（JSON，放 sweeps/ 底下）：
    {
      "name": "budget_v1",                       # 輸出到 outputs/sweeps/<name>/
      "scenarios": [
        {"name": "contest", "config": "configs/shared/contest.json"},
        {"name": "contest_w2", "config": "configs/shared/contest.json",
         "overrides": {"rules.k_t": 0.001, "rules.C_t": 8000}}     # 同幾何換權重
      ],
      "seeds": [0, 1, 2, 3, 4],
      "base": {"optimization.MAX_BURNS": [1, 2, 3]},              # 所有 run 共用的覆寫
      "grid": {"optimization.MAXITER": [300, 600, 1200],          # 笛卡兒積展開成參數組
               "optimization.POPSIZE": [10, 20, 40]},
      "variants": {"revs_off": {"strategy.REVS_ENSEMBLE": false}} # 或/且：具名參數組
    }
覆寫的套用順序：情境 config → base → 情境 overrides → 參數組 → optimization.SEED。

用法：
    uv run python sweep_params.py sweeps/budget_v1.json --dry-run    # 列出要跑哪些、共幾次
    uv run python sweep_params.py sweeps/budget_v1.json              # 開跑（可中斷、可續跑）
    uv run python sweep_params.py sweeps/budget_v1.json --slots 3    # 同時跑 3 個 (牆鐘會互相干擾)
    uv run python sweep_params.py sweeps/budget_v1.json --summary    # 彙整已有結果
    uv run python sweep_params.py sweeps/budget_v1.json --gmat --gmat-console /path/to/GmatConsole
"""
import argparse
import copy
import datetime
import fcntl
import glob
import itertools
import json
import os
import re
import shutil
import signal
import statistics
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from src.config_validator import validate_config, ConfigValidationError  # noqa: E402

# numba cache=True 的快取檔 (.nbi 索引 / .nbc 機器碼) 都落在各模組旁的 __pycache__/
NUMBA_CACHE_GLOBS = [os.path.join(ROOT, "src", "__pycache__", "*.nb[ic]"),
                     os.path.join(ROOT, "__pycache__", "*.nb[ic]")]
CASE_LINE_RE = re.compile(r"推進 (\d+) 次完成：目標值 (-?[\d.]+)，跑了 (\d+)/(\d+) 代")
TS_RE = re.compile(r"^(\d\d):(\d\d):(\d\d) ")
# run.log 的階段分界：開頭 → 拆棒前贏家存檔 = 搜尋（含種子、C2 重搜、NLP 微調）；存檔 → 求解結果已保存 = 拆棒合法化。
# 預算小時拆棒可能比搜尋還久（contest MAXITER=10：搜尋 29s、拆棒 262s），「限時內分數」要分開看。
STAGE_MARKS = {"presplit": "拆棒前贏家已存檔", "saved": "求解結果已保存"}


# ─── 規格展開 ────────────────────────────────────────────────────────────────

def set_dotted(cfg, key, value):
    """cfg["a"]["b"] = value，用 "a.b" 指定。中間層不存在就建。"""
    parts = key.split(".")
    node = cfg
    for p in parts[:-1]:
        node = node.setdefault(p, {})
        if not isinstance(node, dict):
            raise ValueError(f"覆寫 {key}：{p} 不是物件，不能往下設")
    node[parts[-1]] = copy.deepcopy(value)


def _short(key):
    return key.split(".")[-1]


def expand_variants(spec):
    """回傳 [(參數組名稱, 覆寫 dict)]，順序固定（grid 在前、具名在後）。"""
    out = []
    grid = spec.get("grid") or {}
    if grid:
        keys = list(grid)
        for combo in itertools.product(*(grid[k] for k in keys)):
            name = ",".join(f"{_short(k)}={json.dumps(v, separators=(',', ':'))}"
                            for k, v in zip(keys, combo))
            out.append((name, dict(zip(keys, combo))))
    for name, ov in (spec.get("variants") or {}).items():
        out.append((name, dict(ov)))
    if not out:
        out.append(("base", {}))
    names = [n for n, _ in out]
    if len(set(names)) != len(names):
        raise ValueError(f"參數組名稱重複：{names}")
    return out


def plan_jobs(spec):
    """展開成 job 清單，SEED 在最外層（跑到一半停掉時每個組合都已有前幾顆 SEED）。"""
    scenarios = spec["scenarios"]
    names = [s["name"] for s in scenarios]
    if len(set(names)) != len(names):
        raise ValueError(f"情境名稱重複：{names}")
    variants = expand_variants(spec)
    jobs = []
    for seed in spec["seeds"]:
        for sc in scenarios:
            for vname, vov in variants:
                jobs.append({"scenario": sc["name"], "variant": vname, "seed": int(seed),
                             "config": sc["config"],
                             "overrides": {**(spec.get("base") or {}),
                                           **(sc.get("overrides") or {}), **vov}})
    return jobs


def job_key(job):
    return f"{job['scenario']}|{job['variant']}|{job['seed']}"


def job_dirname(job):
    return re.sub(r"[^\w.=,+-]", "_", f"{job['scenario']}__{job['variant']}__s{job['seed']}")


def build_config(job):
    path = job["config"] if os.path.isabs(job["config"]) else os.path.join(ROOT, job["config"])
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    for k, v in job["overrides"].items():
        set_dotted(cfg, k, v)
    set_dotted(cfg, "optimization.SEED", job["seed"])
    return cfg


# ─── 執行 ────────────────────────────────────────────────────────────────────

def git_state():
    def _git(*a):
        try:
            return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        except OSError:
            return ""
    return {"commit": _git("rev-parse", "HEAD"),
            "dirty": bool(_git("status", "--porcelain", "--untracked-files=no"))}


def numba_cache_snapshot():
    snap = {}
    for pat in NUMBA_CACHE_GLOBS:
        for p in glob.glob(pat):
            try:
                snap[p] = os.stat(p).st_mtime_ns
            except OSError:
                pass
    return snap


def cache_changes(before, after):
    return sorted(os.path.relpath(p, ROOT) for p in after if before.get(p) != after[p])


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def collect_result(run_dir):
    """從本次目錄撈出彙整要的欄位；缺檔就留 None，由呼叫端判定狀態。"""
    res = {"final": None, "presplit": None, "cases": [], "solve_sec": None, "provenance_files": None}
    mission = _read_json(os.path.join(run_dir, "mission.json"))
    if mission:
        mi = mission.get("mission_info", {})
        res["final"] = {k: mi.get(k) for k in ("score", "penalty_count", "num_burns", "total_dv_mps",
                                              "T_team", "miss_km", "earth_safe")}
        res["provenance_files"] = (mission.get("provenance") or {}).get("files")
    pre = sorted(glob.glob(os.path.join(run_dir, "winner_presplit_seed*.json")))
    if pre:
        w = _read_json(pre[0]) or {}
        mi = w.get("mission_info", {})
        res["presplit"] = {k: mi.get(k) for k in ("score", "score_split_est", "num_burns",
                                                  "penalty_count", "total_dv_mps", "T_team")}
    run = _read_json(os.path.join(run_dir, "run.json"))
    if run:
        res["solve_sec"] = (run.get("timings_sec") or {}).get("solve")
        res["run_status"] = run.get("status")
    res["search_sec"] = res["split_sec"] = None
    try:
        t_first, t_last, marks = None, None, {}
        with open(os.path.join(run_dir, "run.log"), encoding="utf-8") as f:
            for line in f:
                m = CASE_LINE_RE.search(line)
                if m:
                    res["cases"].append({"burns": int(m[1]), "objective": float(m[2]),
                                         "gens": int(m[3]), "max_gens": int(m[4])})
                ts = TS_RE.match(line)
                if not ts:
                    continue
                t = int(ts[1]) * 3600 + int(ts[2]) * 60 + int(ts[3])
                if t_first is None:
                    t_first = t
                while t < (t_last if t_last is not None else t):   # 跨午夜
                    t += 86400
                t_last = t
                for name, text in STAGE_MARKS.items():
                    if text in line and name not in marks:
                        marks[name] = t
        if "presplit" in marks:
            res["search_sec"] = marks["presplit"] - t_first
            if "saved" in marks:
                res["split_sec"] = marks["saved"] - marks["presplit"]
    except OSError:
        pass
    return res


class Running:
    def __init__(self, job, proc, run_dir, t0, cache_before, console):
        self.job, self.proc, self.run_dir, self.t0 = job, proc, run_dir, t0
        self.cache_before, self.console = cache_before, console


def preserve_previous_job(out_dir, name):
    """Keep an incomplete run's inputs and console output before retrying."""
    run_dir = os.path.join(out_dir, "runs", name)
    cfg_path = os.path.join(out_dir, "configs", name + ".json")
    console_path = os.path.join(out_dir, "configs", name + ".console.log")
    if not any(os.path.lexists(path) for path in (run_dir, cfg_path, console_path)):
        return None
    stale_root = os.path.join(out_dir, "runs", "_stale")
    os.makedirs(stale_root, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    destination = os.path.join(stale_root, f"{name}__{stamp}")
    suffix = 1
    while os.path.lexists(destination):
        destination = os.path.join(stale_root, f"{name}__{stamp}.{suffix}")
        suffix += 1
    if os.path.lexists(run_dir):
        shutil.move(run_dir, destination)
    else:
        os.mkdir(destination)
    for source, target in ((cfg_path, "config.json"), (console_path, "console.log")):
        if os.path.lexists(source):
            saved = os.path.join(destination, target)
            suffix = 1
            while os.path.lexists(saved):
                saved = os.path.join(destination, f"{target}.{suffix}")
                suffix += 1
            shutil.move(source, saved)
    return destination


def start_job(job, out_dir, gmat, gmat_console=None):
    cfg = build_config(job)
    name = job_dirname(job)
    preserve_previous_job(out_dir, name)
    cfg_path = os.path.join(out_dir, "configs", name + ".json")
    os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
    with open(cfg_path, "x", encoding="utf-8") as f:
        json.dump(cfg, f, indent=1, ensure_ascii=False)
    run_dir = os.path.join(out_dir, "runs", name)
    cmd = [sys.executable, "main.py", "--config", cfg_path, "--run-dir", run_dir, "--quiet"]
    if not gmat:
        cmd += ["--stop-after", "solve"]
    elif gmat_console:
        cmd += ["--gmat-console", gmat_console]
    console = open(os.path.join(out_dir, "configs", name + ".console.log"), "x")
    cache_before = numba_cache_snapshot()
    try:
        proc = subprocess.Popen(cmd, cwd=ROOT, stdout=console, stderr=subprocess.STDOUT,
                                start_new_session=True)   # 自己一個 process group，逾時整組殺
    except Exception:
        console.close()
        raise
    return Running(job, proc, run_dir, time.time(), cache_before, console)


def finish_job(r, rusage, returncode, timed_out, git):
    r.console.close()
    wall = time.time() - r.t0
    res = collect_result(r.run_dir)
    if timed_out:
        status = "timeout"
    elif returncode != 0:
        status = "error"
    elif res["final"] is None:
        status = "no_result"
    else:
        status = "ok"
    return {
        "key": job_key(r.job), "scenario": r.job["scenario"], "variant": r.job["variant"],
        "seed": r.job["seed"], "status": status, "returncode": returncode,
        "overrides": r.job["overrides"],
        "wall_sec": round(wall, 2),
        # wait4 的 rusage 含子行程等到的孫行程 (搜尋 worker)——CPU 秒不受 --slots 干擾，牆鐘會
        "cpu_sec": round(rusage.ru_utime + rusage.ru_stime, 2) if rusage else None,
        "solve_sec": res["solve_sec"], "search_sec": res["search_sec"], "split_sec": res["split_sec"],
        "final": res["final"], "presplit": res["presplit"], "cases": res["cases"],
        "numba_cache_written": cache_changes(r.cache_before, numba_cache_snapshot()),
        "provenance_files": res["provenance_files"],
        "git": git, "run_dir": os.path.relpath(r.run_dir, ROOT),
        "finished_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }


def load_results(path):
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows


def warmup(spec, jobs, out_dir):
    """用第一個 job 的設定、極小預算跑一次完整求解，讓 numba 快取落地——之後每次 run 都是讀快取。"""
    job = dict(jobs[0], variant="_warmup", seed=0)
    job["overrides"] = {**job["overrides"], "optimization.MAXITER": 3, "optimization.POPSIZE": 2,
                        "optimization.MAX_BURNS": [1, 2], "strategy.REVS_ENSEMBLE": False,
                        "strategy.SEED_PORTFOLIO_N": 1}
    wdir = os.path.join(out_dir, "_warmup")
    shutil.rmtree(wdir, ignore_errors=True)
    print("🔥 暖 numba 快取（極小預算跑一次完整求解）…", flush=True)
    r = start_job(job, wdir, gmat=False)
    r.proc.wait()
    r.console.close()
    changed = cache_changes(r.cache_before, numba_cache_snapshot())
    print(f"   完成（{time.time() - r.t0:.0f}s，{'寫入 %d 個快取檔' % len(changed) if changed else '快取原本就是熱的'}）"
          + ("" if r.proc.returncode == 0 else f"  ⚠️ 暖身失敗 returncode={r.proc.returncode}，"
             f"見 {wdir}"), flush=True)


def run_sweep(spec, out_dir, slots, timeout, gmat, retry_failed, do_warmup,
              gmat_console=None):
    # archive-logs takes an exclusive lock before removing console logs. Keep a
    # shared lock for the entire sweep, including warmup, while jobs may write.
    lock_path = os.path.join(ROOT, "outputs", "sweeps", ".archive.lock")
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    with open(lock_path, "a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_SH)
        try:
            return _run_sweep(spec, out_dir, slots, timeout, gmat, retry_failed,
                              do_warmup, gmat_console)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _run_sweep(spec, out_dir, slots, timeout, gmat, retry_failed, do_warmup,
               gmat_console):
    os.makedirs(out_dir, exist_ok=True)
    res_path = os.path.join(out_dir, "results.jsonl")
    jobs = plan_jobs(spec)
    for job in jobs:   # 先全部驗證一遍，別跑了一整晚才發現第 80 組設定打錯
        try:
            validate_config(build_config(job))
        except ConfigValidationError as exc:
            sys.exit(f"❌ {job_key(job)} 設定不合法：{exc}")
    done = {}
    for row in load_results(res_path):
        done[row["key"]] = row["status"]
    pending = [j for j in jobs if job_key(j) not in done
               or (retry_failed and done[job_key(j)] != "ok")]
    print(f"📋 {spec['name']}：共 {len(jobs)} 次，已完成 {len(jobs) - len(pending)}，"
          f"待跑 {len(pending)}（slots={slots}）", flush=True)
    if not pending:
        return
    git = git_state()
    if git["dirty"]:
        print("⚠️ 工作目錄有未 commit 的改動——結果只記得到 commit，之後很難重現", flush=True)
    if do_warmup:
        warmup(spec, jobs, out_dir)

    running = []
    n_done = 0
    t_start = time.time()
    with open(res_path, "a", encoding="utf-8") as out:
        try:
            while pending or running:
                while pending and len(running) < slots:
                    running.append(start_job(pending.pop(0), out_dir, gmat, gmat_console))
                time.sleep(1.0)
                for r in list(running):
                    pid, status, rusage = os.wait4(r.proc.pid, os.WNOHANG)
                    timed_out = False
                    if pid == 0:
                        if timeout and time.time() - r.t0 > timeout:
                            os.killpg(r.proc.pid, signal.SIGKILL)
                            pid, status, rusage = os.wait4(r.proc.pid, 0)
                            timed_out = True
                        else:
                            continue
                    r.proc.returncode = os.waitstatus_to_exitcode(status)
                    row = finish_job(r, rusage, r.proc.returncode, timed_out, git)
                    out.write(json.dumps(row, ensure_ascii=False) + "\n")
                    out.flush()
                    running.remove(r)
                    n_done += 1
                    f = row["final"] or {}
                    warn = "  ⚠️ 有冷編譯" if row["numba_cache_written"] else ""
                    print(f"[{n_done}/{n_done + len(pending) + len(running)}] {row['key']:<50} "
                          f"{row['status']:<9} score={f.get('score', float('nan')):.4f} "
                          f"違規={f.get('penalty_count')} 牆鐘={row['wall_sec']:.0f}s "
                          f"(累計 {(time.time() - t_start) / 60:.0f} 分){warn}", flush=True)
        except KeyboardInterrupt:
            print("\n⏹ 中斷：終止執行中的 run（沒寫進 results 的下次會重跑）", flush=True)
            for r in running:
                try:
                    os.killpg(r.proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            raise


# ─── 彙整 ────────────────────────────────────────────────────────────────────

def summarize(spec, out_dir):
    rows = load_results(os.path.join(out_dir, "results.jsonl"))
    if not rows:
        print("還沒有結果。")
        return
    variants = [n for n, _ in expand_variants(spec)]
    scenarios = [s["name"] for s in spec["scenarios"]]
    by = {}
    for r in rows:
        by.setdefault((r["scenario"], r["variant"]), []).append(r)

    def score(r):
        return (r.get("final") or {}).get("score") if r["status"] == "ok" else None

    medians = {}   # (scenario, variant) -> 中位數
    for sc in scenarios:
        print(f"\n== {sc} ==")
        print(f"  {'參數組':<34}{'n':>3}{'中位數':>10}{'最差':>10}{'最佳':>10}{'有違規':>7}{'失敗':>5}"
              f"{'牆鐘中位':>9}{'搜尋':>7}{'拆棒':>7}{'CPU中位':>9}")
        for v in variants:
            rs = by.get((sc, v), [])
            if not rs:
                continue
            sc_list = [s for s in (score(r) for r in rs) if s is not None]
            n_fail = sum(r["status"] != "ok" for r in rs)
            n_pen = sum(((r.get("final") or {}).get("penalty_count") or 0) > 0 for r in rs if r["status"] == "ok")
            walls = [r["wall_sec"] for r in rs if r["status"] == "ok"]
            cpus = [r["cpu_sec"] for r in rs if r["status"] == "ok" and r.get("cpu_sec") is not None]
            srch = [r["search_sec"] for r in rs if r["status"] == "ok" and r.get("search_sec") is not None]
            spl = [r["split_sec"] for r in rs if r["status"] == "ok" and r.get("split_sec") is not None]
            med = statistics.median(sc_list) if sc_list else float("nan")
            if sc_list:
                medians[(sc, v)] = med
            print(f"  {v:<34}{len(rs):>3}{med:>10.4f}"
                  f"{(min(sc_list) if sc_list else float('nan')):>10.4f}"
                  f"{(max(sc_list) if sc_list else float('nan')):>10.4f}{n_pen:>7}{n_fail:>5}"
                  f"{(statistics.median(walls) if walls else float('nan')):>9.0f}"
                  f"{(statistics.median(srch) if srch else float('nan')):>7.0f}"
                  f"{(statistics.median(spl) if spl else float('nan')):>7.0f}"
                  f"{(statistics.median(cpus) if cpus else float('nan')):>9.0f}")

    # 跨情境：各情境內依中位數排名（1 = 最好），再看平均名次與「離該情境最佳差多少」的最壞值
    if len(scenarios) > 1 and len(variants) > 1:
        print("\n== 跨情境（依各情境中位數）==")
        print(f"  {'參數組':<34}{'平均名次':>9}{'最大落後':>10}{'涵蓋情境':>9}")
        ranks, gaps = {v: [] for v in variants}, {v: [] for v in variants}
        for sc in scenarios:
            meds = {v: medians[(sc, v)] for v in variants if (sc, v) in medians}
            if not meds:
                continue
            best = max(meds.values())
            order = sorted(meds, key=lambda v: -meds[v])
            for v in meds:
                ranks[v].append(order.index(v) + 1)
                gaps[v].append(best - meds[v])
        for v in sorted(variants, key=lambda v: statistics.mean(ranks[v]) if ranks[v] else 1e9):
            if ranks[v]:
                print(f"  {v:<34}{statistics.mean(ranks[v]):>9.2f}{max(gaps[v]):>10.4f}"
                      f"{len(ranks[v]):>6}/{len(scenarios)}")

    # 可信度警告
    cold = [r["key"] for r in rows if r.get("numba_cache_written")]
    if cold:
        print(f"\n⚠️ {len(cold)} 次 run 期間 numba 快取被改寫（= 有冷編譯，與其他 run 可能差 1 ulp 而分岔）："
              f"{cold[:5]}{' …' if len(cold) > 5 else ''}")
    prov = {json.dumps(r.get("provenance_files"), sort_keys=True) for r in rows if r.get("provenance_files")}
    if len(prov) > 1:
        print(f"⚠️ 結果來自 {len(prov)} 個不同版本的程式碼（跑到一半改過 code？）——跨版本比較要小心")
    fails = [f"{r['key']}({r['status']})" for r in rows if r["status"] != "ok"]
    if fails:
        print(f"⚠️ 失敗 {len(fails)} 次：{fails[:5]}{' …' if len(fails) > 5 else ''}")


def main():
    ap = argparse.ArgumentParser(description="參數正式實驗：情境 × SEED × 參數組 → jsonl")
    ap.add_argument("spec", help="規格檔（JSON），格式見檔頭說明")
    ap.add_argument("--dry-run", action="store_true", help="只列出要跑的組合")
    ap.add_argument("--summary", action="store_true", help="彙整已有結果，不跑")
    ap.add_argument("--slots", type=int, default=1,
                    help="同時跑幾個 run（預設 1。>1 省總時間但牆鐘互相干擾，CPU 秒不受影響）")
    ap.add_argument("--timeout", type=float, default=0, help="單次 run 上限秒數（0 = 不限）")
    ap.add_argument("--gmat", action="store_true", help="每次 run 也跑 GMAT 驗證（預設只求解）")
    ap.add_argument("--gmat-console", help="搭配 --gmat 時指定 GmatConsole 路徑")
    ap.add_argument("--retry-failed", action="store_true", help="重跑狀態不是 ok 的組合")
    ap.add_argument("--no-warmup", action="store_true", help="跳過開跑前的 numba 快取暖身")
    ap.add_argument("--out", help="輸出目錄（預設 outputs/sweeps/<name>）")
    args = ap.parse_args()

    with open(args.spec, encoding="utf-8") as f:
        spec = json.load(f)
    for k in ("name", "scenarios", "seeds"):
        if k not in spec:
            sys.exit(f"❌ 規格檔缺 {k}")
    out_dir = args.out or os.path.join(ROOT, "outputs", "sweeps", spec["name"])

    if args.summary:
        summarize(spec, out_dir)
        return
    if args.dry_run:
        jobs = plan_jobs(spec)
        done = {r["key"]: r["status"] for r in load_results(os.path.join(out_dir, "results.jsonl"))}
        for j in jobs:
            mark = {"ok": "✅"}.get(done.get(job_key(j)), "❌" if job_key(j) in done else "  ")
            print(f"{mark} {job_key(j)}")
        n_v = len(expand_variants(spec))
        print(f"\n{len(spec['scenarios'])} 情境 × {n_v} 參數組 × {len(spec['seeds'])} SEED = {len(jobs)} 次"
              f"（已完成 {sum(v == 'ok' for v in done.values())}）")
        return
    try:
        run_sweep(spec, out_dir, max(1, args.slots), args.timeout, args.gmat, args.retry_failed,
                  not args.no_warmup, args.gmat_console)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
