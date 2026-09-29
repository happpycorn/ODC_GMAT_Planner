#!/usr/bin/env bash
# 可續跑的 ablation_v1 批次。規格與輸出路徑以本腳本所在的 repo 為基準。
set -euo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
slots=5
out_root="$repo_root/outputs/sweeps"
dry_run=false

usage() {
  cat <<'EOF'
Usage: scripts/run_ablation_v1.sh [--slots N] [--out-root PATH] [--dry-run]

Run the ablation_v1 sweep with resumable results. Relative output paths are
resolved from the caller's working directory.
EOF
}

while (($#)); do
  case "$1" in
    --slots|--out-root)
      if (($# < 2)); then printf 'Missing value for %s\n' "$1" >&2; exit 2; fi
      if [[ "$1" == --slots ]]; then slots=$2; else out_root=$2; fi
      shift 2
      ;;
    --dry-run) dry_run=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done
if [[ ! "$slots" =~ ^[1-9][0-9]*$ ]]; then
  printf 'Slots must be a positive integer: %s\n' "$slots" >&2
  exit 2
fi
if [[ "$out_root" != /* ]]; then out_root="$PWD/$out_root"; fi

cmd=(uv run python sweep_params.py sweeps/ablation_v1.json --slots "$slots" --out "$out_root/ablation_v1")
if "$dry_run"; then printf '%q ' "${cmd[@]}"; printf '\n'; exit 0; fi
cd -- "$repo_root"
"${cmd[@]}"
printf 'BATCH_DONE %s\n' "$(date -Iseconds)"
