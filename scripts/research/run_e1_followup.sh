#!/usr/bin/env bash
# E1 補跑（2026-10-29）：run_e1.sh 的 hyperbolic_smoke oracle 卡在 vallado NaN 無窮迴圈（逾時 2 h），
# 修好 oracle_twoburn.kepler 後等 run_e1.sh 跑完再補：
#   hyper_far h=1626（上一輪 GLOBAL_ORACLE 的步長，確認重現 82.6473）→ 另存 _h1626
#   hyper_far h=T_max/100（用修正版重跑，確認跟第一次 82.6445 相同）
#   hyperbolic_smoke h=T_max/100
set -u
cd "$(dirname "$0")/../.."
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
PY=${PY:-python}
LOG=outputs/research/e1; OUTJ=outputs/research/global_oracle
while pgrep -f "run_e1.sh" | xargs -r ps -o comm= -p | grep -qx bash; do sleep 30; done
cp "$OUTJ/oracle_twoburn_hyper_far.json" "$OUTJ/oracle_twoburn_hyper_far_run1.json"
echo "== followup hyper_far h=1626 $(date)" >> "$LOG/e1.log"
timeout 7200 $PY scripts/research/oracle_twoburn.py hyper_far --h 1626 --K 10 > "$LOG/oracle_hyper_far_h1626.log" 2>&1
echo "   rc=$? $(date)" >> "$LOG/e1.log"
mv "$OUTJ/oracle_twoburn_hyper_far.json" "$OUTJ/oracle_twoburn_hyper_far_h1626.json"
for s in hyper_far hyperbolic_smoke; do
  h=$($PY -c "import sys;sys.path.insert(0,'scripts/research');from oracle_common import load_scenario;print(load_scenario('$s')[1].T_max/100)")
  echo "== followup oracle $s h=$h $(date)" >> "$LOG/e1.log"
  timeout 7200 $PY scripts/research/oracle_twoburn.py "$s" --h "$h" --K 10 > "$LOG/oracle_$s.log" 2>&1
  echo "   rc=$? $(date)" >> "$LOG/e1.log"
done
echo "followup done $(date)" >> "$LOG/e1.log"
