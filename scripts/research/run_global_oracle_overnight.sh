#!/usr/bin/env bash
# GLOBAL_ORACLE 夜間批次（2026-10-28）：等手上的 global_oracle_* sweep 跑完（避免拆棒牆鐘預算被搶核心），
# 依序對每個情境跑 兩棒 oracle → 天花板 → 換求解器／free-ECI，最後才跑第 4 項（大預算參考解）。
# hyperbolic_smoke 套排位賽覆寫後與 ranking_round 設定完全相同（軌道、T_max、計分參數），只跑一次。
set -u
cd "$(dirname "$0")/../.."
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
LOG=outputs/research/global_oracle; mkdir -p "$LOG"
while pgrep -f "sweep_params.py sweeps/global_oracle" > /dev/null; do sleep 60; done
echo "sweeps done $(date)" >> "$LOG/overnight.log"
for spec in "hyperbolic_test_fuel 100" "hyperbolic_smoke 250" "hyper_far 1626"; do
  set -- $spec; s=$1; h=$2
  echo "== $s oracle $(date)" >> "$LOG/overnight.log"
  uv run python scripts/research/oracle_twoburn.py "$s" --h "$h" --K 10 > "$LOG/oracle_twoburn_$s.log" 2>&1
  uv run python scripts/research/oracle_ceiling.py "$s" > "$LOG/oracle_ceiling_$s.log" 2>&1
  echo "== $s solvers $(date)" >> "$LOG/overnight.log"
  uv run --with cma python scripts/research/oracle_solvers.py "$s" --seeds 3 --random-starts 8 > "$LOG/oracle_solvers_$s.log" 2>&1
done
# 第 4 項排最後（比賽設定基準可續跑、已完成的跳過；再跑大預算參考解）
echo "== item4 $(date) $(git rev-parse --short HEAD)" >> "$LOG/overnight.log"
uv run python sweep_params.py sweeps/global_oracle_contest.json --slots 2 > outputs/sweeps/global_oracle_contest.console2.log 2>&1
uv run python sweep_params.py sweeps/global_oracle_bigbudget.json --slots 2 > outputs/sweeps/global_oracle_bigbudget.console.log 2>&1
echo "all done $(date)" >> "$LOG/overnight.log"
