"""Mac advise 牆鐘量測；每次都是新行程，保留原始文字及完整精度 JSON。

例：
  .venv/bin/python tools/bench_advise.py --label before --output /tmp/mac_advise \
      --states docs/notes/mac_timing_states/*.json --workers 1 4 perf
  .venv/bin/python tools/bench_advise.py --compare /tmp/mac_advise/before.jsonl /tmp/mac_advise/after.jsonl

首次樣本各用空的 NUMBA_CACHE_DIR；暖機樣本沿用最後一次首次樣本的磁碟快取。
每次仍含 Python 啟動、未提供磁碟快取的 JIT、worker 啟動及完整 CLI 輸出。
本腳本只使用標準函式庫，不會替受測行程設定 BLAS 執行緒或改決策參數。
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import statistics
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
THREAD_ENV = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
              "VECLIB_MAXIMUM_THREADS", "ACCELERATE_MAX_THREADS", "BLIS_NUM_THREADS",
              "NUMBA_NUM_THREADS", "ODC_SCAN_REUSE", "ODC_STRICT_SURVIVAL", "ODC_GAP_SURVIVAL")


def exact_result(value):
    """只去除耗時與 worker 設定；浮點數用 hex 比較，連正負零也不會隱藏。"""
    if isinstance(value, dict):
        return {k: exact_result(v) for k, v in value.items()
                if k not in ("decide_sec", "elapsed_sec", "workers")}
    if isinstance(value, list):
        return [exact_result(v) for v in value]
    if isinstance(value, float):
        return {"float64_hex": value.hex()}
    return value


def exact_text(value):
    value = re.sub(r"（[0-9.]+s）", "（<耗時>s）", value)
    value = re.sub(r"快速模式：用時 [0-9.]+s", "快速模式：用時 <耗時>s", value)
    return re.sub(r"'workers': [0-9]+", "'workers': <數量>", value)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def first_difference(a, b, path="$"):
    if type(a) is not type(b):
        return path
    if isinstance(a, dict):
        if a.keys() != b.keys():
            return path + ".<keys>"
        for key in a:
            if a[key] != b[key]:
                return first_difference(a[key], b[key], path + "." + key)
    elif isinstance(a, list):
        if len(a) != len(b):
            return path + ".<length>"
        for i, (x, y) in enumerate(zip(a, b)):
            if x != y:
                return first_difference(x, y, f"{path}[{i}]")
    elif a != b:
        return path
    return None


def read_runs(path):
    with Path(path).open() as f:
        return [json.loads(line) for line in f if line.strip()]


def compare(paths):
    reference = {}
    checked = 0
    for path in paths:
        for run in read_runs(path):
            key = (run["state"], run["state_sha256"])
            current = (exact_result(run["result"]), exact_text(run["stdout"]))
            if key not in reference:
                reference[key] = current
            if current != reference[key]:
                where = first_difference(reference[key][0], current[0]) or "CLI 文字"
                raise AssertionError(f"{path}: {key[0]} w={run['workers']} {run['phase']} "
                                     f"#{run['repeat']} 不同：{where}")
            checked += 1
    return {"runs_equal": checked, "states": len(reference),
            "comparison": "float.hex() ==，原始 CLI 文字只移除耗時及 workers 設定",
            "sha256": {key[0]: digest(value[0]) for key, value in reference.items()}}


def command_output(command):
    proc = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    return proc.stdout if proc.returncode == 0 else proc.stderr.strip()


def hardware():
    # 只保留機型資訊，避免把 system_profiler 的序號及 UUID 寫入報告。
    text = command_output(["/usr/sbin/system_profiler", "SPHardwareDataType"]) if sys.platform == "darwin" else ""
    fields = ("Model Name:", "Model Identifier:", "Chip:", "Total Number of Cores:", "Memory:")
    selected = [line.strip() for line in text.splitlines() if any(line.strip().startswith(x) for x in fields)]
    perf_text = command_output(["/usr/sbin/sysctl", "-n", "hw.perflevel0.physicalcpu"]) if sys.platform == "darwin" else ""
    perf = int(perf_text.strip()) if perf_text.strip().isdigit() else None
    if perf is None:
        match = re.search(r"\((\d+) Performance", text)
        perf = int(match[1]) if match else None
    return {"platform": platform.platform(), "python": sys.version, "cpu_count": os.cpu_count(),
            "hardware": selected, "performance_cores": perf, "sysctl": perf_text.strip(),
            "environment": {k: os.environ.get(k) for k in THREAD_ENV},
            "numpy_config": command_output([sys.executable, "-c", "import numpy; numpy.show_config()"]),
            "versions": command_output([sys.executable, "-c",
                                         "import importlib.metadata as m; print({k:m.version(k) for k in "
                                         "['numpy','numba','scipy','stable-baselines3']})"])}


def summarize(runs):
    rows = []
    for state, workers in sorted({(r["state"], r["workers"]) for r in runs}):
        row = {"state": state, "workers": workers}
        for phase in ("first", "warm"):
            samples = [r["wall_sec"] for r in runs
                       if (r["state"], r["workers"], r["phase"]) == (state, workers, phase)]
            if samples:
                row[phase + "_sec"] = samples
                row[phase + "_median_sec"] = statistics.median(samples)
        rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--states", nargs="+", type=Path)
    ap.add_argument("--workers", nargs="+", default=["1", "4", "perf"])
    ap.add_argument("--label", default="timing")
    ap.add_argument("--output", type=Path, default=Path("/tmp/mac_advise"))
    ap.add_argument("--first-runs", type=int, default=3)
    ap.add_argument("--warm-runs", type=int, default=3)
    ap.add_argument("--compare", nargs="+", type=Path)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()
    if args.compare:
        print(json.dumps(compare(args.compare), indent=2, ensure_ascii=False))
        return
    if not args.states or min(args.first_runs, args.warm_runs) < 0 or args.first_runs + args.warm_runs < 1:
        ap.error("請指定 --states，且首次／暖機次數合計至少 1")
    hw = hardware()
    workers = []
    for token in args.workers:
        n = hw["performance_cores"] if token == "perf" else int(token)
        if n is None or n < 1:
            ap.error("無法取得效能核心數；請用 --workers 指定")
        if n not in workers:
            workers.append(n)
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    raw_path = args.output / f"{args.label}.jsonl"
    if raw_path.exists() and not args.resume:
        ap.error(f"{raw_path} 已存在；另取 --label 或使用 --resume")
    sources = ["copilot.py", "agents/analytic.py", "agents/rollout.py", "evaluation/tournament.py",
               "evaluate.py", "tools/bench_advise.py"]
    meta = {**hw, "workers_requested": args.workers, "workers_measured": workers,
            "source_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources},
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    meta_path = args.output / f"{args.label}_meta.json"
    if args.resume and meta_path.exists():
        old = json.loads(meta_path.read_text())
        if old["source_sha256"] != meta["source_sha256"] or old["environment"] != meta["environment"]:
            ap.error("續跑的程式或環境已變，請另取 --label")
    else:
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    existing = read_runs(raw_path) if raw_path.exists() else []
    done = {(r["state"], r["state_sha256"], r["workers"], r["phase"], r["repeat"]) for r in existing}
    with tempfile.TemporaryDirectory(prefix=f"odc_advise_{args.label}_") as cache_root:
        with raw_path.open("a") as raw:
            for state in args.states:
                state = state.resolve()
                name = state.name
                state_sha = hashlib.sha256(state.read_bytes()).hexdigest()
                for n in workers:
                    for phase, count in (("first", args.first_runs), ("warm", args.warm_runs)):
                        for repeat in range(1, count + 1):
                            if (name, state_sha, n, phase, repeat) in done:
                                continue
                            cache_id = repeat if phase == "first" else max(1, args.first_runs)
                            cache = Path(cache_root) / f"{name}_w{n}_{cache_id}"
                            cache.mkdir(exist_ok=True)
                            # 續跑時暫存快取消失，暖機樣本前先補一次不計入統計的 CLI 執行。
                            env = {**os.environ, "COPILOT_WORKERS": str(n), "NUMBA_CACHE_DIR": str(cache)}
                            result_path = Path(cache_root) / "result.json"
                            cmd = [sys.executable, str(ROOT / "copilot.py"), "advise", str(state),
                                   "--prune", "--json", str(result_path)]
                            if phase == "warm" and not any(cache.iterdir()):
                                subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, check=True)
                            print(f"{args.label} {name} w={n} {phase} {repeat}/{count}…", flush=True)
                            t0 = time.perf_counter()
                            proc = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
                            wall = time.perf_counter() - t0
                            if proc.returncode:
                                raise RuntimeError(f"{cmd}: exit={proc.returncode}\n{proc.stderr}\n{proc.stdout}")
                            result = json.loads(result_path.read_text())
                            record = {"state": name, "state_sha256": state_sha, "workers": n,
                                      "phase": phase, "repeat": repeat, "wall_sec": wall,
                                      "result": result, "stdout": proc.stdout, "stderr": proc.stderr,
                                      "command": [".venv/bin/python", "copilot.py", "advise", str(state.relative_to(ROOT)),
                                                  "--prune", "--json", "<暫存檔>"],
                                      "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
                            raw.write(json.dumps(record, ensure_ascii=False) + "\n")
                            raw.flush()
                            print(f"  {wall:.3f} s；★ {result.get('ranking', [{}])[0].get('brain')}", flush=True)
    runs = read_runs(raw_path)
    summary = {"timings": summarize(runs), "exact": compare([raw_path])}
    (args.output / f"{args.label}_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
