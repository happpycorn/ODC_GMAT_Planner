"""Index local run results and reversibly archive sweep console logs.

All generated files stay under the gitignored outputs/ directory. From repo root:

    uv run python scripts/output_inventory.py index
    uv run python scripts/output_inventory.py archive-logs
    uv run python scripts/output_inventory.py verify-archive outputs/archive/<name>.tar.gz
    uv run python scripts/output_inventory.py restore-archive outputs/archive/<name>.tar.gz
"""

import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import uuid

try:
    import fcntl
except ImportError:  # Index and archive verification remain usable on Windows.
    fcntl = None


ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
ARCHIVE = OUTPUTS / "archive"
SWEEP_LOCK = OUTPUTS / "sweeps" / ".archive.lock"


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def relative(path):
    return path.relative_to(ROOT).as_posix()


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_record(run_file):
    run = read_json(run_file) or {}
    mission = read_json(run_file.parent / "mission.json") or {}
    info = mission.get("mission_info") or {}
    fixed = (run.get("verification") or {}).get("fixed") or {}
    config = (run.get("arguments") or {}).get("config")
    if config:
        try:
            config = relative(Path(config).resolve())
        except ValueError:
            pass
    return {
        "path": relative(run_file.parent),
        "status": run.get("status"),
        "score": info.get("score"),
        "config": config,
        "verification_status": run.get("verification_status"),
        "fixed_intercept": fixed.get("intercept_success"),
        "fixed_burn_legal": fixed.get("final_burn_legal"),
    }


def sweep_record(directory):
    results = directory / "results.jsonl"
    rows = []
    if results.exists():
        for line in results.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    best = max(
        (row for row in rows if row.get("status") == "ok"
         and isinstance((row.get("final") or {}).get("score"), (int, float))),
        key=lambda row: row["final"]["score"], default=None,
    )
    return {
        "name": directory.name,
        "results": relative(results) if results.exists() else None,
        "rows": len(rows),
        "status": dict(Counter(row.get("status", "unknown") for row in rows)),
        "config_snapshots": len(list((directory / "configs").glob("*.json"))),
        "best_score": (best.get("final") or {}).get("score") if best else None,
        "best_run": best.get("run_dir") if best else None,
    }


def write_index():
    OUTPUTS.mkdir(exist_ok=True)
    runs = [run_record(path) for path in OUTPUTS.rglob("run.json")]
    runs.sort(key=lambda row: row["path"])
    sweeps = [sweep_record(path) for path in sorted((OUTPUTS / "sweeps").glob("*")) if path.is_dir()]
    legacy_files = [relative(path) for path in sorted(OUTPUTS.iterdir())
                    if path.is_file() and path.name not in {"INDEX.md", "index.json"}]
    history_count = sum(path.is_file() for path in (OUTPUTS / "history").glob("*"))
    manifest = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "runs": runs,
        "sweeps": sweeps,
        "legacy_root_files": legacy_files,
        "legacy_history_files": history_count,
        "archives": [relative(path) for path in sorted(ARCHIVE.glob("*.tar.gz"))],
    }
    (OUTPUTS / "index.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = ["# 本機執行成果索引", "", "由 `scripts/output_inventory.py index` 產生。",
             "設定與執行資料留在 `outputs/`；精選、可分享的解見 `docs/solutions/`。", "",
             "## Sweep 結果", "",
             "最佳分數取自已完成搜尋的 Python 方案；是否通過 GMAT 須查該 run 的驗證資料。", "",
             "| 實驗 | 紀錄 | 成功 | 最佳分數 | 最佳執行 |",
             "|---|---:|---:|---:|---|"]
    for sweep in sweeps:
        score = f"{sweep['best_score']:.6f}" if sweep["best_score"] is not None else "—"
        link = sweep["results"]
        result = f"[{sweep['name']}]({link.removeprefix('outputs/')})" if link else sweep["name"]
        best_path = sweep["best_run"]
        best = (f"[run]({best_path.removeprefix('outputs/')})" if best_path else "—")
        lines.append(f"| {result} | {sweep['rows']} | {sweep['status'].get('ok', 0)} | {score} | {best} |")
    lines.extend(["", "## 其他執行目錄", "",
                  "`index.json` 列出每筆執行的設定來源、分數與驗證狀態。",
                  "以下摘要不含 `sweeps/` 的逐筆執行，避免重複。", "",
                  "| 目錄 | 執行數 | 完成數 | 固定燃燒驗證通過 |",
                  "|---|---:|---:|---:|"])
    groups = {}
    for run in runs:
        parent = run["path"].split("/")[1] if "/" in run["path"] else run["path"]
        if parent == "sweeps":
            continue
        groups.setdefault(parent, []).append(run)
    for name, rows in sorted(groups.items()):
        verified = sum(row["status"] == "completed"
                       and row["verification_status"] == "completed"
                       and row["fixed_intercept"] is True
                       and row["fixed_burn_legal"] is True for row in rows)
        completed = sum(row["status"] == "completed" for row in rows)
        lines.append(f"| `{name}/` | {len(rows)} | {completed} | {verified} |")
    lines.extend(["", "## 舊式根目錄檔案", "",
                  f"`history/` 有 {history_count} 份舊腳本副本；新執行使用獨立 run 目錄。", ""])
    for path in legacy_files:
        lines.append(f"- [{Path(path).name}]({path.removeprefix('outputs/')})")
    lines.extend(["", "## 壓縮封存", ""])
    archives = manifest["archives"]
    if archives:
        for archive in archives:
            lines.append(f"- `{archive}`：可用 `verify-archive` 驗證、`restore-archive` 還原。")
    else:
        lines.append("目前沒有壓縮封存。")
    lines.append("")
    (OUTPUTS / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Indexed {len(runs)} runs and {len(sweeps)} sweeps in {relative(OUTPUTS / 'INDEX.md')}")


def active_sweep_writers():
    """Catch jobs started by an older copy of the runner without the lock."""
    result = subprocess.run(["ps", "-eo", "pid=,args="], text=True,
                            capture_output=True, check=True)
    active = []
    for line in result.stdout.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2 or not parts[0].isdigit() or int(parts[0]) == os.getpid():
            continue
        command = parts[1]
        if (re.search(r"(?:^|[ /])sweep_params\.py(?:\s|$)", command)
                or (re.search(r"(?:^|[ /])main\.py(?:\s|$)", command)
                    and "outputs/sweeps/" in command)):
            active.append(int(parts[0]))
    return active


def archive_logs():
    if fcntl is None:
        raise RuntimeError("Archiving sweep logs requires Unix file locking")
    SWEEP_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with SWEEP_LOCK.open("a+b") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("A sweep is running; archive logs after it finishes") from exc
        _archive_logs_locked()


def _archive_logs_locked():
    active = active_sweep_writers()
    if active:
        raise RuntimeError(f"Sweep jobs are still running (PID {', '.join(map(str, active))})")
    logs = sorted((OUTPUTS / "sweeps").rglob("*.console.log"))
    if not logs:
        print("No sweep console logs to archive.")
        return
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    archive = ARCHIVE / f"sweep-console-logs-{stamp}.tar.gz"
    if archive.exists():
        raise FileExistsError(archive)
    temporary = ARCHIVE / f".{archive.name}.{uuid.uuid4().hex}.tmp"
    entries = {}
    try:
        with tarfile.open(temporary, "w:gz") as bundle:
            for path in logs:
                stat = path.stat()
                entries[relative(path)] = {"size": stat.st_size,
                                           "mtime_ns": stat.st_mtime_ns,
                                           "sha256": file_hash(path)}
                bundle.add(path, arcname=relative(path), recursive=False)
        verify_members(temporary, entries)
        temporary.replace(archive)
        manifest = {"archive": relative(archive), "sha256": file_hash(archive),
                    "files": entries}
        manifest_path = archive.with_suffix(archive.suffix + ".json")
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        active = active_sweep_writers()
        if active:
            raise RuntimeError(f"Sweep jobs started during archival (PID {', '.join(map(str, active))}); originals retained")
        removed = 0
        for path in logs:
            recorded = entries[relative(path)]
            stat = path.stat()
            if ((stat.st_size, stat.st_mtime_ns) != (recorded["size"], recorded["mtime_ns"])
                    or file_hash(path) != recorded["sha256"]):
                print(f"Changed during archival; retained {relative(path)}")
                continue
            path.unlink()
            removed += 1
        print(f"Archived and verified {len(entries)} logs in {relative(archive)}; removed {removed} originals")
    finally:
        temporary.unlink(missing_ok=True)


def checked_manifest(archive):
    archive = archive if archive.is_absolute() else ROOT / archive
    archive = archive.resolve()
    if not archive.is_relative_to(ARCHIVE.resolve()) or not archive.name.endswith(".tar.gz"):
        raise ValueError("Archive must be a .tar.gz inside outputs/archive/")
    manifest = read_json(archive.with_suffix(archive.suffix + ".json"))
    if not manifest or manifest.get("archive") != relative(archive):
        raise ValueError("Matching archive manifest is missing")
    if file_hash(archive) != manifest.get("sha256"):
        raise ValueError("Archive checksum mismatch")
    return manifest


def verify_members(archive, entries, restore=False):
    seen = set()
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle:
            name = member.name
            path = Path(name)
            if (not member.isfile() or path.is_absolute() or ".." in path.parts
                    or path.parts[:2] != ("outputs", "sweeps")
                    or not name.endswith(".console.log") or name not in entries
                    or name in seen):
                raise ValueError(f"Unexpected archive member: {name}")
            seen.add(name)
            data = bundle.extractfile(member)
            if data is None:
                raise ValueError(f"Unreadable archive member: {name}")
            digest = hashlib.sha256()
            size = 0
            target = ROOT / path
            if restore and not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
                try:
                    with temporary.open("wb") as out:
                        for chunk in iter(lambda: data.read(1024 * 1024), b""):
                            out.write(chunk)
                            digest.update(chunk)
                            size += len(chunk)
                    if (digest.hexdigest(), size) != (entries[name]["sha256"], entries[name]["size"]):
                        raise ValueError(f"Corrupt archive member: {name}")
                    temporary.replace(target)
                finally:
                    temporary.unlink(missing_ok=True)
            else:
                for chunk in iter(lambda: data.read(1024 * 1024), b""):
                    digest.update(chunk)
                    size += len(chunk)
                if restore and file_hash(target) != entries[name]["sha256"]:
                    raise ValueError(f"Existing file differs from archive: {name}")
            if (digest.hexdigest(), size) != (entries[name]["sha256"], entries[name]["size"]):
                raise ValueError(f"Corrupt archive member: {name}")
    if seen != set(entries):
        raise ValueError("Archive member list differs from manifest")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("index", help="refresh outputs/INDEX.md and outputs/index.json")
    sub.add_parser("archive-logs", help="archive, verify, then remove sweep console logs")
    for command in ("verify-archive", "restore-archive"):
        sub.add_parser(command).add_argument("archive", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "index":
            write_index()
        elif args.command == "archive-logs":
            archive_logs()
        else:
            archive = args.archive if args.archive.is_absolute() else ROOT / args.archive
            manifest = checked_manifest(archive)
            verify_members(archive, manifest["files"], restore=args.command == "restore-archive")
            print(f"Verified {len(manifest['files'])} files in {manifest['archive']}")
    except (OSError, ValueError, RuntimeError, tarfile.TarError,
            subprocess.CalledProcessError) as exc:
        parser.exit(2, f"{exc}\n")


if __name__ == "__main__":
    main()
