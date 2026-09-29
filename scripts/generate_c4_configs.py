#!/usr/bin/env python3
"""Expand sweeps/c4_v1.json into local C4 configs without replacing existing files.

Usage: uv run python scripts/generate_c4_configs.py [--out configs/c4]
       uv run python scripts/generate_c4_configs.py --check
"""
import argparse
import copy
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "sweeps/c4_v1.json"
DEFAULT_OUT = ROOT / "configs/c4"
NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


def set_dotted(config, key, value):
    parts = key.split(".")
    node = config
    for part in parts[:-1]:
        node = node.setdefault(part, {})
        if not isinstance(node, dict):
            raise ValueError(f"Cannot set {key}: {part} is not an object")
    node[parts[-1]] = copy.deepcopy(value)


def build_configs(spec_path=SPEC_PATH):
    """Return the exact 33 configs keyed by job name; each config has no local settings."""
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    presets = spec.get("presets", {})
    jobs = {}
    for group in spec["groups"]:
        stem = group["stem"]
        if not NAME_RE.fullmatch(stem):
            raise ValueError(f"Invalid C4 job stem: {stem}")
        source = Path(group["config"])
        if source.is_absolute() or source.parts[:2] != ("configs", "shared"):
            raise ValueError(f"C4 base must be a shared config: {source}")
        base = json.loads((ROOT / source).read_text(encoding="utf-8"))
        if "local" in base:
            raise ValueError(f"Shared config contains machine settings: {source}")
        preset_name = group.get("preset")
        if preset_name and preset_name not in presets:
            raise ValueError(f"Unknown C4 preset: {preset_name}")
        preset = presets.get(preset_name, {})
        for seed in group.get("seeds", [0]):
            if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
                raise ValueError(f"Invalid C4 seed: {seed}")
            prefix = f"{stem}_s{seed}" if group.get("seed_in_name", False) else stem
            for variant, variant_overrides in group["variants"].items():
                if not NAME_RE.fullmatch(variant):
                    raise ValueError(f"Invalid C4 variant: {variant}")
                name = f"{prefix}_{variant}"
                if name in jobs:
                    raise ValueError(f"Duplicate C4 job name: {name}")
                config = copy.deepcopy(base)
                for overrides in (preset, group.get("overrides", {}), variant_overrides):
                    for key, value in overrides.items():
                        set_dotted(config, key, value)
                set_dotted(config, "optimization.SEED", seed)
                jobs[name] = config
    return jobs


def ensure_configs(out_dir=DEFAULT_OUT, *, check=False):
    """Write missing files only; ignore local paths, but reject changed experiment inputs."""
    out_dir = Path(out_dir)
    jobs = build_configs()
    expected = {f"{name}.json" for name in jobs}
    actual = {path.name for path in out_dir.glob("*.json")} if out_dir.is_dir() else set()
    extra = sorted(actual - expected)
    if extra:
        raise ValueError(f"Unexpected configs in {out_dir}: {', '.join(extra)}")
    missing = []
    changed = []
    for name, config in jobs.items():
        path = out_dir / f"{name}.json"
        if not path.exists():
            missing.append((path, config))
            continue
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = None
        if isinstance(existing, dict):
            existing.pop("local", None)
        if existing != config:
            changed.append(path.name)
    if changed:
        raise ValueError(f"Existing C4 configs differ in {out_dir}: {', '.join(changed)}")
    if check and missing:
        raise ValueError(f"Missing {len(missing)} C4 configs in {out_dir}")
    if not check:
        out_dir.mkdir(parents=True, exist_ok=True)
        for path, config in missing:
            with path.open("x", encoding="utf-8") as output:
                json.dump(config, output, ensure_ascii=False, indent=2)
                output.write("\n")
    return len(jobs), len(missing)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Generated config directory")
    parser.add_argument("--check", action="store_true", help="Verify all configs exist and match; write nothing")
    args = parser.parse_args()
    try:
        total, missing = ensure_configs(args.out, check=args.check)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"C4 configs: {total} valid; {'missing' if args.check else 'created'} {missing}")


if __name__ == "__main__":
    main()
