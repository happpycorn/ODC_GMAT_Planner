#!/usr/bin/env python3
"""C4 驗證排程器（可續跑）：已完成的 job 跳過，未完成的舊目錄改名 .stale<ts> 後重跑。

依記憶體與槽位（每個 job 的槽位 = MAX_BURNS 案例數）決定何時開下一個 job。
用法：uv run python scripts/c4_runner.py [--slots N] [--config-dir PATH] [--out PATH] [--gmat-console PATH] [job 名稱前綴 ...]
已有 main.py 行程在跑的 job（例如排程器重啟前留下的）會被接手等待，不會被當成未完成重跑。
乾淨 clone 若沒有 configs/c4/*.json，會從 sweeps/c4_v1.json 產生；舊的本機設定不會覆寫。
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

if __package__:
    from .generate_c4_configs import build_configs, ensure_configs
else:
    from generate_c4_configs import build_configs, ensure_configs

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CFG_DIR = ROOT / "configs/c4"
CFG_DIR = DEFAULT_CFG_DIR
OUT_DIR = Path(os.environ.get("C4_OUT", ROOT / "outputs/c4"))
PY = Path(sys.executable)
MAX_SLOTS = 8
MIN_AVAIL_GB = 3.5
POLL_SEC = 20

# 大的先跑（E3 是 4 案例 × 2000 代），小的填空檔
ORDER = ["E3_", "E4_", "E5_", "E2_"]


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(OUT_DIR / "runner.log", "a") as f:
        f.write(line + "\n")


def mem_avail_gb():
    for line in open("/proc/meminfo"):
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) / 1024 / 1024
    return 0.0


def is_done(name):
    rj = OUT_DIR / name / "run.json"
    if not rj.exists():
        return False
    try:
        return json.loads(rj.read_text()).get("status") == "completed"
    except (OSError, ValueError):
        return False


def live_pid(name):
    """找出正在跑這個 job 的 main.py 主行程（--run-dir 指向它），沒有就回 None。"""
    target = str(OUT_DIR / name)
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            argv = (proc / "cmdline").read_bytes().split(b"\0")
            ppid_argv = (Path("/proc") / (proc / "stat").read_text().split()[3] / "cmdline").read_bytes()
        except (OSError, ValueError):
            continue
        # 只認主行程：子 worker 的父行程也是同一個 main.py
        if b"main.py" in argv and target.encode() in argv and target.encode() not in ppid_argv:
            return int(proc.name)
    return None


class External:
    """排程器重啟前就在跑的 job：不是我們的子行程，只能輪詢 pid 是否還活著。"""
    def __init__(self, pid):
        self.pid = pid

    def poll(self):
        return None if Path(f"/proc/{self.pid}").exists() else 0


def load_jobs(prefixes, generated=None):
    jobs = []
    if generated is None:
        source = ((cfg, json.loads(cfg.read_text())) for cfg in sorted(CFG_DIR.glob("*.json")))
    else:
        source = ((CFG_DIR / f"{name}.json", config) for name, config in sorted(generated.items()))
    for cfg, config in source:
        name = cfg.stem
        if prefixes and not any(name.startswith(p) for p in prefixes):
            continue
        w = len(config["optimization"]["MAX_BURNS"])
        jobs.append((name, cfg, w))
    rank = lambda j: next((i for i, p in enumerate(ORDER) if j[0].startswith(p)), len(ORDER))
    return sorted(jobs, key=lambda j: (rank(j), j[0]))


def update_status(name, **fields):
    path = OUT_DIR / "jobs.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    data.setdefault(name, {}).update(fields)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False))


def stale_destination(path):
    """Choose a readable, unused name without replacing an earlier stale artifact."""
    stamp = int(time.time())
    candidate = path.with_name(f"{path.name}.stale{stamp}")
    suffix = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.stale{stamp}.{suffix}")
        suffix += 1
    return candidate


def preserve_incomplete_run(name):
    """Move old run files and console output before the next console log is opened."""
    run_dir = OUT_DIR / name
    stale_dir = None
    if run_dir.exists():
        stale_dir = stale_destination(run_dir)
        run_dir.rename(stale_dir)
        log(f"moved incomplete {name} -> {stale_dir.name}")

    console_path = OUT_DIR / f"{name}.console.log"
    if console_path.exists():
        destination = stale_dir / "console.log" if stale_dir else stale_destination(console_path)
        if destination.exists():
            destination = stale_destination(destination)
        console_path.rename(destination)
        log(f"preserved {console_path.name} -> {destination.relative_to(OUT_DIR)}")


def main():
    global CFG_DIR, OUT_DIR, PY, MAX_SLOTS, MIN_AVAIL_GB, POLL_SEC
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("prefixes", nargs="*", help="只執行名稱以指定字串開頭的 job")
    parser.add_argument("--slots", type=int, default=MAX_SLOTS, help="可同時使用的案例槽位（預設 8）")
    parser.add_argument("--config-dir", type=Path, default=CFG_DIR, help="C4 設定檔目錄")
    parser.add_argument("--out", type=Path, default=OUT_DIR, help="結果目錄（也可用 C4_OUT）")
    parser.add_argument("--python", type=Path, default=PY, help="執行 main.py 的 Python（預設為目前解譯器）")
    parser.add_argument("--gmat-console", help="這台機器的 GmatConsole 路徑；共用設定不含本機路徑")
    parser.add_argument("--min-avail-gb", type=float, default=MIN_AVAIL_GB, help="已有工作時最低可用記憶體 GB")
    parser.add_argument("--poll-seconds", type=float, default=POLL_SEC, help="檢查工作狀態的間隔秒數")
    parser.add_argument("--dry-run", action="store_true", help="只列出預定動作，不啟動或修改任何工作")
    args = parser.parse_args()
    if args.slots < 1 or args.min_avail_gb < 0 or args.poll_seconds <= 0:
        parser.error("--slots 必須大於 0，--min-avail-gb 不可為負數，--poll-seconds 必須大於 0")
    CFG_DIR = args.config_dir.resolve()
    OUT_DIR = args.out.resolve()
    PY = args.python.resolve()
    MAX_SLOTS = args.slots
    MIN_AVAIL_GB = args.min_avail_gb
    POLL_SEC = args.poll_seconds
    # Keep existing local C4 configs intact. A clean clone has no configs/c4 files:
    # preview its tracked spec in memory, then materialize only for a real run.
    generate_default = CFG_DIR == DEFAULT_CFG_DIR and not any(CFG_DIR.glob("*.json"))
    generated = None
    if generate_default:
        try:
            generated = build_configs()
            if not args.dry_run:
                ensure_configs(CFG_DIR)
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
    elif not CFG_DIR.is_dir():
        parser.error(f"設定檔目錄不存在：{CFG_DIR}")
    jobs = load_jobs(args.prefixes, generated=generated if args.dry_run else None)
    if not jobs:
        parser.error(f"沒有符合的 C4 設定檔：{CFG_DIR}")
    if args.dry_run:
        for name, _cfg, w in jobs:
            run_dir = OUT_DIR / name
            if is_done(name):
                action = "skip (completed)"
            elif live_pid(name):
                action = "adopt (running)"
            elif run_dir.exists() or (OUT_DIR / f"{name}.console.log").exists():
                action = "rerun (preserve incomplete artifacts first)"
            else:
                action = "run"
            print(f"{name}: {action}; slots={w}")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pending = []
    running = {}  # name -> (Popen|External, w, t0)
    for name, cfg, w in jobs:
        if is_done(name):
            log(f"skip {name} (already completed)")
            continue
        run_dir = OUT_DIR / name
        pid = live_pid(name)
        if pid:
            running[name] = (External(pid), w, time.time())
            log(f"adopt running {name} (pid={pid}, w={w})")
            continue
        preserve_incomplete_run(name)
        pending.append((name, cfg, w))

    log(f"MAX_SLOTS={MAX_SLOTS}")
    while pending or running:
        for name, (p, w, t0) in list(running.items()):
            rc = p.poll()
            if rc is None:
                continue
            wall = round(time.time() - t0, 1)
            status = "done" if rc == 0 and is_done(name) else f"failed(rc={rc})"
            update_status(name, status=status, wall_sec=wall)
            log(f"finish {name} {status} wall={wall}s")
            del running[name]

        used = sum(w for _, w, _ in running.values())
        while pending:
            name, cfg, w = pending[0]
            avail = mem_avail_gb()
            # 沒有任何 job 在跑時一律放行，避免大 job 永遠等不到
            if running and (used + w > MAX_SLOTS or avail < MIN_AVAIL_GB):
                break
            pending.pop(0)
            console = open(OUT_DIR / f"{name}.console.log", "w")
            command = [str(PY), "main.py", "--config", str(cfg), "--run-dir", str(OUT_DIR / name), "--quiet"]
            if args.gmat_console:
                command.extend(["--gmat-console", args.gmat_console])
            p = subprocess.Popen(
                command,
                cwd=ROOT, stdout=console, stderr=subprocess.STDOUT,
            )
            running[name] = (p, w, time.time())
            used += w
            update_status(name, status="running")
            log(f"start {name} (w={w}, used={used}, mem={avail:.1f}G)")
            time.sleep(5)  # 讓新 job 先把記憶體吃起來再評估下一個
        time.sleep(POLL_SEC)
    log("all jobs finished")


if __name__ == "__main__":
    main()
