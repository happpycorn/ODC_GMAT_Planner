"""以隔離子行程建立重構前後的數值、腳本及工具輸出基準。
主要入口為 main；每次執行固定執行緒並使用獨立的冷 Numba 快取。
"""
import argparse
import copy
import datetime
import difflib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[2]
# 同一列的兩個入口具有相同語意；後面的案例參數由 build_command 補上。
COMMANDS = {
    "solve": ("main.py",),
    "resume": ("main.py", "--from-winner"),
    "export": ("main.py", "--from-mission"),
    "feasibility": ("feasibility.py",),
    "check": ("check_problem.py",),
    "tmax": ("scripts", "tmax_from_boundary.py"),
    "scoring": ("scripts", "check_scoring_params.py"),
    "sweep": ("sweep_params.py",),
}
COMMAND_TABLE = {
    key: {"legacy": " ".join(value) if key in ("resume", "export")
          else str(Path(*value)), "odc": f"odc.py {key}"}
    for key, value in COMMANDS.items()
}
CASES = (
    "smoke_full", "prelim_split", "ranking_oracle", "hyperbolic",
    "from_winner", "from_mission", "tool_feasibility", "tool_check",
    "tool_tmax", "tool_scoring", "sweep_dry",
)
TEXT_CASES = {"tool_feasibility", "tool_check", "tool_tmax", "tool_scoring", "sweep_dry"}
ENVIRONMENT = {key: "1" for key in (
    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)}
ENVIRONMENT["PYTHONHASHSEED"] = "0"
IGNORED_KEYS = {
    "saved_at", "created_at", "updated_at", "timestamp", "run_dir", "provenance",
    "artifact_id", "mission_id", "wall_sec", "pipeline_wall_sec", "elapsed_sec",
    "execution_time", "execution_time_sec", "timings_sec",
    "SPLIT_WALL_BUDGET_SEC",
}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize(value, removed, location="$", in_source=False):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            child = f"{location}.{key}"
            if key in IGNORED_KEYS or (in_source and key == "sha256"):
                removed.append(child)
            elif isinstance(item, str) and (Path(item).is_absolute() or re.match(r"^[A-Za-z]:[\\/]", item)):
                removed.append(child)
            else:
                result[key] = normalize(item, removed, child, key == "source")
        return result
    if isinstance(value, list):
        return [normalize(item, removed, f"{location}[{index}]") for index, item in enumerate(value)]
    return value


def clean_stdout(value):
    lines = []
    for line in value.splitlines():
        if re.search(r"(?:[/\\].*\.(?:json|py|txt)|[A-Za-z]:[\\/]|\d{2}:\d{2}:\d{2}|耗時|elapsed|wall.clock)", line, re.I):
            continue
        lines.append(line.rstrip())
    return "\n".join(lines) + "\n"


def first_difference(left, right, location="$"):
    if type(left) is not type(right):
        return f"{location}: {left!r} → {right!r}"
    if isinstance(left, dict):
        if left.keys() != right.keys():
            return f"{location}: 鍵不同 {sorted(left.keys() ^ right.keys())}"
        for key in left:
            difference = first_difference(left[key], right[key], f"{location}.{key}")
            if difference:
                return difference
    elif isinstance(left, list):
        if len(left) != len(right):
            return f"{location}: 長度 {len(left)} → {len(right)}"
        for index, (a, b) in enumerate(zip(left, right)):
            difference = first_difference(a, b, f"{location}[{index}]")
            if difference:
                return difference
    elif left != right:
        return f"{location}: {left!r} → {right!r}"
    return None


def compare_runs(left, right):
    for key in ("returncode", "coverage"):
        difference = first_difference(left[key], right[key], key)
        if difference:
            return difference
    canonical = lambda names: sorted(re.sub(r"output_\d{8}_\d{6}\.txt$", "output_TIMESTAMP.txt", name) for name in names)
    difference = first_difference(canonical(left["artifacts"]), canonical(right["artifacts"]), "artifacts")
    if difference:
        return difference
    left = dict(left, scripts={canonical([key])[0]: value for key, value in left["scripts"].items()})
    right = dict(right, scripts={canonical([key])[0]: value for key, value in right["scripts"].items()})
    for name in left["scripts"]:
        a, b = bytes.fromhex(left["scripts"][name]), bytes.fromhex(right["scripts"][name])
        if a != b:
            index = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
            return f"{name}: byte {index}: {a[index:index+60]!r} → {b[index:index+60]!r}"
    difference = first_difference(normalize(left["json"], []), normalize(right["json"], []), "json")
    if difference:
        return difference
    if left.get("stdout_normalized") != right.get("stdout_normalized"):
        delta = list(difflib.unified_diff(left.get("stdout_normalized", "").splitlines(),
                                        right.get("stdout_normalized", "").splitlines()))
        return "stdout: " + " | ".join(delta[2:7])
    return None


def config_for(case, folder):
    source = {"prelim_split": "contest", "ranking_oracle": "e1_r4", "hyperbolic": "hyperbolic_smoke"}[case]
    cfg = copy.deepcopy(read_json(ROOT / "configs" / "shared" / f"{source}.json"))
    cfg["optimization"].update(SEED=0, NUM_THREADS=1, MAXITER=5, POPSIZE=5, MAX_BURNS=[1, 2])
    cfg.setdefault("strategy", {}).update(
        REVS_ENSEMBLE=False, PRIMER_GUIDED_RESEARCH=False,
        SPLIT_NLP_MAXITER=20, SPLIT_N_SPAN=0, SPLIT_WORKERS=1,
        SPLIT_MULTISTART=[0], SPLIT_PRUNE_REOPT_MPS=0, SPLIT_WALL_BUDGET_SEC=3600,
    )
    if case == "ranking_oracle":
        cfg["strategy"].update(
            SPLIT_LEADING=True, ORACLE_TWOBURN=True, ORACLE_TWOBURN_K=1,
            ORACLE_TWOBURN_GRID_DIV=10, ORACLE_TWOBURN_WALL_SEC=3600,
            SPLIT_WORKERS=2, SPLIT_MULTISTART=[0, 0.75], SPLIT_NLP_MAXITER=2,
        )
    target = folder / "config.json"
    write_json(target, cfg)
    return target


def build_command(entry, case, folder, smoke_mission):
    run_dir = folder / "run"
    common = ["--no-gmat", "--stop-after", "export", "--run-dir", str(run_dir)]
    if case in ("smoke_full", "prelim_split", "ranking_oracle", "hyperbolic"):
        command = "solve"
        config = ROOT / "tests" / "fixtures" / "pipeline_smoke.json" if case == "smoke_full" else config_for(case, folder)
        args = (["--config", str(config)] if entry == "legacy" else [str(config)]) + common
    elif case == "from_winner":
        command = "resume"
        args = [str(ROOT / "docs" / "solutions" / "checkpoints" / "contest_route4_seed7_presplit.json")] + common
    elif case == "from_mission":
        command = "export"
        args = [str(smoke_mission)] + common
    elif case == "tool_feasibility":
        command, args = "feasibility", ["--config", str(ROOT / "configs" / "shared" / "official_sample.json"), "--grid", "3"]
    elif case == "tool_check":
        command, args = "check", ["--config", str(ROOT / "configs" / "shared" / "official_sample.json")]
    elif case == "tool_tmax":
        command, args = "tmax", ["--config", str(ROOT / "configs" / "shared" / "ranking_round.json"), "--boundary-km", "100000"]
    elif case == "tool_scoring":
        command, args = "scoring", ["--demo-prelim"]
    else:
        command, args = "sweep", [str(ROOT / "sweeps" / "ranking_mc_v1.json"), "--dry-run", "--out", str(folder / "sweep")]
    if entry == "odc":
        return [sys.executable, str(ROOT / "odc.py"), command, *args]
    parts = COMMANDS[command]
    prefix = [str(ROOT / parts[0]), *parts[1:]] if command in ("resume", "export") else [str(ROOT.joinpath(*parts))]
    return [sys.executable, *prefix, *args]


def fork_observer(folder):
    observer = folder / "observer"
    observer.mkdir()
    (observer / "sitecustomize.py").write_text(
        '"""記錄拆棒行程實際建立的 fork 事件。\n由 Python 自動載入，僅觀察，不改寫求解函式。\n"""\n'
        'import os\nimport sys\nfrom pathlib import Path\n'
        'def observe(event, args):\n'
        '    if event == "os.fork":\n'
        '        path = Path(os.environ["ODC_EQ_OBSERVER"]) / f"fork_{os.getpid()}.txt"\n'
        '        with path.open("a", encoding="utf-8") as stream:\n'
        '            stream.write("fork\\n")\n'
        'sys.addaudithook(observe)\n', encoding="utf-8")
    return observer


def run_case(entry, case, folder, smoke_mission):
    folder.mkdir(parents=True)
    command = build_command(entry, case, folder, smoke_mission)
    env = dict(os.environ, **ENVIRONMENT)
    if case == "ranking_oracle":
        observer = fork_observer(folder)
        env["PYTHONPATH"] = str(observer) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        env["ODC_EQ_OBSERVER"] = str(observer)
    with tempfile.TemporaryDirectory(prefix="odc-equivalence-numba-") as cache:
        env["NUMBA_CACHE_DIR"] = cache
        started = time.perf_counter()
        proc = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        wall = time.perf_counter() - started
    (folder / "stdout.txt").write_text(proc.stdout, encoding="utf-8")
    (folder / "stderr.txt").write_text(proc.stderr, encoding="utf-8")
    run_dir = folder / "run"
    artifacts = sorted(str(path.relative_to(run_dir)) for path in run_dir.rglob("*") if path.is_file()) if run_dir.exists() else []
    scripts = {str(path.relative_to(run_dir)): path.read_bytes().hex() for path in sorted(run_dir.rglob("*.txt"))} if run_dir.exists() else {}
    removed, snapshots = [], {}
    if run_dir.exists():
        for path in sorted(run_dir.glob("*.json")):
            if path.name.startswith(("mission", "winner_presplit", "oracle_candidates")):
                snapshots[path.name] = normalize(read_json(path), removed, path.name)
    coverage = {"ok": proc.returncode == 0}
    if case not in TEXT_CASES:
        coverage["mission_and_script"] = (run_dir / "mission.json").is_file() and (run_dir / "output.txt").is_file()
    if case == "prelim_split":
        coverage["split_executed"] = "HAP-67 自動拆分：超標解" in proc.stdout
    if case == "ranking_oracle":
        oracle = run_dir / "oracle_candidates_seed0.json"
        candidates = read_json(oracle).get("candidates", []) if oracle.is_file() else []
        coverage["spawn_completed"] = bool(candidates)
        coverage["fork_started"] = bool(list((folder / "observer").glob("fork_*.txt"))) if os.name != "nt" else True
        coverage["no_deadline"] = not any(word in proc.stdout for word in ("deadline exceeded", "牆鐘預算 3600 s 到期"))
    result = dict(command=command, returncode=proc.returncode, wall_sec=wall, artifacts=artifacts,
                  scripts=scripts, json=snapshots, removed_keys=sorted(set(removed)), coverage=coverage)
    if case in TEXT_CASES:
        result["stdout_normalized"] = clean_stdout(proc.stdout)
        (folder / "stdout_normalized.txt").write_text(result["stdout_normalized"], encoding="utf-8")
    write_json(folder / "result.json", result)
    return result


def report(out, entry, runs, baseline=None):
    lines = ["# 等價比對報告", "", f"入口：`{entry}`；每案例重複 {max(map(len, runs.values()))} 次。", "",
             "| 案例 | 結果 | 結束碼 | 中位秒數 | 相對基準 | 第一個差異或說明 |", "|---|---|---|---|---|---|"]
    failures = 0
    unstable = []
    for case, results in runs.items():
        differences = [compare_runs(results[0], result) for result in results[1:]]
        instability = next((item for item in differences if item), None)
        status, detail, percent = "相同", "", "—"
        if instability:
            status, detail = "基準本身不穩定", instability
            unstable.append(case)
        if not all(all(result["coverage"].values()) for result in results):
            status, detail = "不同", "執行或必要路徑覆蓋失敗：" + repr([result["coverage"] for result in results])
            failures += 1
        if baseline:
            other = baseline["runs"].get(case)
            if not other:
                status, detail = "不同", "基準缺少此案例"
                failures += 1
            else:
                reference_unstable = any(compare_runs(other[0], result) for result in other[1:])
                if reference_unstable:
                    status = "基準本身不穩定"
                    detail = detail or next(compare_runs(other[0], result) for result in other[1:] if compare_runs(other[0], result))
                else:
                    mismatch = next((compare_runs(other[0], result) for result in results if compare_runs(other[0], result)), None)
                    if mismatch:
                        status, detail = "不同", mismatch
                        failures += 1
                old = statistics.median(result["wall_sec"] for result in other)
                change = (statistics.median(result["wall_sec"] for result in results) / old - 1) * 100 if old else 0
                percent = f"{change:+.1f}%" + ("（超過 30%）" if abs(change) > 30 else "")
        seconds = statistics.median(result["wall_sec"] for result in results)
        lines.append(f"| {case} | {status} | {results[0]['returncode']} | {seconds:.3f} | {percent} | {detail.replace('|', '/')} |")
    lines += ["", "## 正規化時排除的鍵", "", "只排除環境衍生資料；source.sha256 取決於來源存檔的時間與來源雜湊。其餘數值完全相等比對。", ""]
    removed = sorted({key for results in runs.values() for result in results for key in result["removed_keys"]})
    lines += [f"- `{key}`" for key in removed]
    lines += ["", "SPLIT_WALL_BUDGET_SEC 是 oracle worker 依剩餘牆鐘時間縮短後寫入贏家設定的預算；排除此時間衍生值，仍檢查未觸發期限及全部物理數值。",
              "", "history/output_YYYYMMDD_HHMMSS.txt 的時間戳僅在產物名稱比對時正規化，檔案內容仍逐位元比較。",
              "", "stdout 排除含檔案路徑、絕對路徑、時鐘時間或耗時的整行；原文均保存於各案例 stdout.txt。",
              "", "每次子行程均使用全新的空 NUMBA_CACHE_DIR；固定環境：`" + " ".join(f"{key}={value}" for key, value in ENVIRONMENT.items()) + "`。",
              "", "ranking_oracle 以 oracle 候選產物證明 spawn 完成，並以唯讀 audit hook 記錄 fork 建立事件。",
              "", "基準不穩定案例不自動放寬容忍度；需先回報欄位與原因，再處理後續驗收。" if unstable else "所有重複案例均以完全相等與腳本逐位元比對。"]
    (out / "equivalence_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return failures, unstable


def main(argv=None):
    parser = argparse.ArgumentParser(description="固定執行緒與冷快取的重構等價比對")
    parser.add_argument("--entry", choices=("legacy", "odc"), required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--cases", nargs="+", choices=CASES, default=list(CASES))
    parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args(argv)
    if args.repeat < 1:
        parser.error("--repeat 必須至少為 1")
    out = (args.out or ROOT / "outputs" / "equivalence" / f"{args.entry}_{datetime.datetime.now():%Y%m%d_%H%M%S_%f}").resolve()
    baseline = read_json(args.compare / "equivalence_results.json") if args.compare else None
    runs = {}
    if out.exists():
        if args.compare and out == args.compare.resolve():
            saved = read_json(out / "equivalence_results.json")
            selected = {case: saved["runs"][case] for case in args.cases if case in saved["runs"]}
            if len(selected) != len(args.cases):
                parser.error("自我比對的基準缺少指定案例")
            failures, unstable = report(out, args.entry, selected, baseline)
            print(f"自我比對完成：{len(selected)} 案例，{failures} 不同，{len(unstable)} 不穩定；{out / 'equivalence_report.md'}")
            return int(bool(failures))
        parser.error(f"輸出目錄已存在，拒絕覆寫：{out}")
    out.mkdir(parents=True)
    selected = list(dict.fromkeys(args.cases))
    if "from_mission" in selected and "smoke_full" not in selected:
        selected.insert(0, "smoke_full")
    elif "from_mission" in selected:
        selected.remove("smoke_full")
        selected.insert(0, "smoke_full")
    for case in selected:
        runs[case] = []
        for index in range(args.repeat):
            print(f"執行 {case} [{index + 1}/{args.repeat}]", flush=True)
            smoke = out / "smoke_full" / f"repeat_{index+1}" / "run" / "mission.json"
            result = run_case(args.entry, case, out / case / f"repeat_{index+1}", smoke)
            runs[case].append(result)
            write_json(out / "equivalence_results.json", dict(entry=args.entry, environment=ENVIRONMENT, runs=runs))
            print(f"  結束碼 {result['returncode']}，{result['wall_sec']:.2f}s，覆蓋 {result['coverage']}", flush=True)
    failures, unstable = report(out, args.entry, runs, baseline)
    print(f"完成：{len(runs)} 案例，{failures} 不同，{len(unstable)} 不穩定；{out / 'equivalence_report.md'}")
    return int(bool(failures or unstable))


if __name__ == "__main__":
    sys.exit(main())
