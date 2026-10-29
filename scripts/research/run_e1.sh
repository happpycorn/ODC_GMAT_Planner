#!/usr/bin/env bash
# E1（2026-10-29）批次：等錨點 sweep 跑完 → 錨點兩棒 oracle → 隨機題 sweep（3 顆並行）→ 隨機題 oracle。
# oracle 跟管線不同時跑（牆鐘、拆棒 600 s 預算都會被搶核心）。網格步長 h = T_max/100，K = 10。
set -u
cd "$(dirname "$0")/../.."
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
PY=${PY:-python}
LOG=outputs/research/e1; mkdir -p "$LOG"
# 只看 comm=python 的行程：pgrep -f 也會比對到命令列含這串字的外層 shell
while pgrep -f "sweep_params.py sweeps/e1_anchors" | xargs -r ps -o comm= -p | grep -qx python; do sleep 30; done
oracle() {  # $1 = 情境名
  local h; h=$($PY -c "import sys;sys.path.insert(0,'scripts/research');from oracle_common import load_scenario;print(load_scenario('$1')[1].T_max/100)")
  echo "== oracle $1 h=$h $(date)" >> "$LOG/e1.log"
  timeout 7200 $PY scripts/research/oracle_twoburn.py "$1" --h "$h" --K 10 > "$LOG/oracle_$1.log" 2>&1
  echo "   rc=$? $(date)" >> "$LOG/e1.log"
}
for s in ${ANCHORS:-hyper_far hyperbolic_smoke}; do oracle "$s"; done
echo "== random sweep $(date)" >> "$LOG/e1.log"
$PY sweep_params.py sweeps/e1_random.json --slots 3 --timeout 3600 > "$LOG/random_sweep.log" 2>&1
for s in $($PY -c "import json;print(' '.join(s['name'] for s in json.load(open('sweeps/e1_random.json'))['scenarios']))"); do oracle "$s"; done
echo "all done $(date)" >> "$LOG/e1.log"
