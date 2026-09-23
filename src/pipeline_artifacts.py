"""Versioned pipeline snapshots. Files are immutable inputs to later stages."""
import datetime
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import uuid

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
# Conservative invalidation: changing these files requires solving/replaying again.
PHYSICS_FILES = (
    "src/core_math.py", "src/propagator.py", "src/scorer.py",
    "src/optimizer.py", "src/burn_splitter.py", "src/config_validator.py", "uv.lock",
)


def jsonable(value):
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [jsonable(v) for v in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def digest(value):
    raw = json.dumps(jsonable(value), sort_keys=True, ensure_ascii=True,
                     allow_nan=False, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def provenance():
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
            stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    files = (*PHYSICS_FILES, "main.py", "src/script_generator.py", "src/pipeline_artifacts.py")
    return {"git_commit": commit, "python": platform.python_version(),
            "files": {p: file_digest(ROOT / p) for p in files}}


def write_json(path, payload):
    """Atomic write: interrupted stages never leave a half-written snapshot."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        tmp.write_text(json.dumps(jsonable(payload), ensure_ascii=False,
                                  allow_nan=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def create_run_dir(path=None):
    if path is None:
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = Path("outputs") / "runs" / (stamp + "_" + uuid.uuid4().hex[:8])
    path = Path(path).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=False)
    return path


def save_mission(path, config, burns, times, mission_info, source=None):
    payload = jsonable({
        "schema_version": SCHEMA_VERSION, "stage": "mission",
        "saved_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "provenance": provenance(), "source": source,
        "config": config, "burns": burns, "times": times, "mission_info": mission_info,
        # Post-solve evidence only; GMAT results belong to separate verification artifacts.
        "verification": "python_only",
    })
    payload["artifact_id"] = digest(payload)
    write_json(path, payload)
    return payload["artifact_id"]


def load_mission(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("stage") != "mission":
        raise ValueError("需要受支援的拆棒後 mission.json；拆棒前存檔請用 --from-winner。")
    recorded = payload.get("artifact_id")
    if recorded != digest({k: v for k, v in payload.items() if k != "artifact_id"}):
        raise ValueError("mission 存檔內容與雜湊不符，請由上游重新產生。")
    changed = [p for p in PHYSICS_FILES
               if payload["provenance"]["files"].get(p) != file_digest(ROOT / p)]
    if changed:
        raise ValueError("求解/物理程式版本已變更，請重新求解或用 --from-winner 重跑拆棒："
                         + ", ".join(changed))
    from src.config_validator import validate_config
    validate_config(payload["config"])
    burns, times, mi = payload["burns"], payload["times"], payload["mission_info"]
    n = mi["num_burns"]
    if not burns or len(burns) != n or len(times) != n + 1:
        raise ValueError("mission 的棒數與燃燒/滑行資料不一致。")
    if any(len(b) != 3 or not all(math.isfinite(v) for v in b) for b in burns):
        raise ValueError("mission 燃燒向量必須是有限的 VNB 三維向量。")
    if any(not math.isfinite(t) or t < 0 for t in times):
        raise ValueError("mission 時間必須是非負有限值。")
    if not isinstance(mi.get("earth_safe"), bool) or not isinstance(mi.get("dc_converged"), bool):
        raise ValueError("mission 缺少 Python 安全/收斂檢查結果。")
    return payload
