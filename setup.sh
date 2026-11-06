#!/usr/bin/env bash
# 新電腦一鍵安裝（Mac／Linux）：排位賽工具（根目錄）＋金／銅牌賽工具（medal/）＋GUI。
#
#   ./setup.sh                    # 裝套件、找 GMAT、跑體檢
#   ./setup.sh --gmat <路徑>      # 直接指定 GmatConsole
#   ./setup.sh --yes              # 不問問題（找不到 GMAT 就跳過）
#   ./setup.sh --no-check         # 只安裝，不跑體檢
#   ./setup.sh --full-check       # 金牌賽跑完整 pytest（預設只跑快速子集）
#
# 兩邊是各自獨立的 uv 專案（各自的 uv.lock、.venv），版本照 lock 檔裝、不升級。
# 第一次要網路（約 2 GB）。說明在 docs/SETUP.md。
set -u
cd "$(dirname "$0")" || exit 1
ROOT="$(pwd)"
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

GMAT_ARG="" ASSUME_YES=0 CHECK=1 FULL=0
while [ $# -gt 0 ]; do
  case "$1" in
    --gmat) GMAT_ARG="${2:-}"; shift ;;
    --yes|-y) ASSUME_YES=1 ;;
    --no-check) CHECK=0 ;;
    --full-check) FULL=1 ;;
    -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
    *) echo "不認得的參數：$1（看 ./setup.sh --help）"; exit 2 ;;
  esac
  shift
done
[ -t 0 ] || ASSUME_YES=1

RESULTS=()
ok()   { RESULTS+=("✓ $1"); echo "✓ $1"; }
bad()  { RESULTS+=("✕ $1"); echo "✕ $1"; }
step() { echo; echo "── $1"; }

# ---------------------------------------------------------------- uv
step "uv"
if ! command -v uv >/dev/null 2>&1; then
  echo "找不到 uv。官方安裝指令：curl -LsSf https://astral.sh/uv/install.sh | sh"
  if [ $ASSUME_YES -eq 0 ]; then
    read -r -p "現在幫你跑這行嗎？[y/N] " ans
    case "$ans" in y|Y) curl -LsSf https://astral.sh/uv/install.sh | sh ;; esac
  fi
  command -v uv >/dev/null 2>&1 || { echo "沒有 uv 沒辦法繼續；裝好後重跑 ./setup.sh"; exit 1; }
fi
echo "$(uv --version)"

# ---------------------------------------------------------------- 套件
step "排位賽工具（根目錄）uv sync"
if uv sync --frozen --python 3.12; then ok "排位賽 venv（.venv）"; else bad "排位賽 uv sync 失敗"; fi

step "金／銅牌賽工具（medal/）uv sync"
if (cd medal && uv sync --frozen --python 3.12); then ok "金牌賽 venv（medal/.venv）"; else bad "金牌賽 uv sync 失敗"; fi

# ---------------------------------------------------------------- GMAT
step "GMAT"
if [ ! -f configs/local/config.json ] && [ -x .venv/bin/python ]; then
  .venv/bin/python -c "from odc.config.defaults import load_or_create_config; load_or_create_config()" >/dev/null 2>&1 \
    && echo "已建立 configs/local/config.json（預設情境）"
fi
PY=.venv/bin/python
[ -x "$PY" ] || PY=python3
GMAT="$GMAT_ARG"
[ -n "$GMAT" ] || GMAT="$("$PY" gui/gmat_path.py 2>/dev/null)"
if [ -n "$GMAT" ] && [ ! -f "$GMAT" ]; then
  echo "設定裡的 GMAT 路徑不存在：$GMAT"
  GMAT=""
fi
if [ -z "$GMAT" ] && [ $ASSUME_YES -eq 0 ]; then
  echo "找不到 GmatConsole。貼上完整路徑（例如 ~/Documents/GMAT R2026a/bin/GmatConsole），直接按 Enter 跳過："
  read -r GMAT
  GMAT="${GMAT/#\~/$HOME}"
  GMAT="${GMAT%\"}"; GMAT="${GMAT#\"}"
fi
if [ -n "$GMAT" ] && [ -f "$GMAT" ]; then
  if [ -f configs/local/config.json ]; then
    "$PY" gui/gmat_path.py --write "$GMAT"
  fi
  ok "GMAT 路徑：$GMAT"
else
  GMAT=""
  bad "沒有 GMAT 路徑（排位賽步驟 6 與經緯高轉檔會失敗；之後重跑 ./setup.sh --gmat <路徑>）"
fi

[ $CHECK -eq 1 ] || { echo; printf '%s\n' "${RESULTS[@]}"; exit 0; }

# ---------------------------------------------------------------- 體檢
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1

step "體檢：GMAT 能不能開"
if [ -n "$GMAT" ]; then
  T="$(mktemp -d)"
  printf "Create Spacecraft Probe;\nCreate ReportFile Rep;\nRep.Filename = '%s';\nBeginMissionSequence;\nReport Rep Probe.SMA;\n" \
    "$T/probe.txt" > "$T/probe.script"
  (cd "$(dirname "$GMAT")" && "./$(basename "$GMAT")" --exit --run "$T/probe.script" > "$T/gmat.log" 2>&1)
  if grep -q "^[0-9]" "$T/probe.txt" 2>/dev/null; then ok "GMAT 跑得起來"; else bad "GMAT 跑不起來（輸出在 $T/gmat.log）"; fi
else
  bad "GMAT 沒設定，跳過"
fi

step "體檢：排位賽 quick test（約 3 分鐘）"
if uv run python odc.py test --quick -q; then ok "排位賽 quick test"; else bad "排位賽 quick test 失敗"; fi

if [ $FULL -eq 1 ]; then
  step "體檢：金牌賽完整 pytest（約 6 分鐘）"
  MEDAL_TESTS=()
else
  step "體檢：金牌賽 quick test"
  MEDAL_TESTS=(tests/test_final_rules.py tests/test_final_copilot.py tests/test_official_io.py tests/test_state_io.py tests/test_simultaneous.py)
fi
if [ -n "$GMAT" ]; then export GMAT_CONSOLE="$GMAT"; fi
if (cd medal && .venv/bin/python -m pytest -q -p no:cacheprovider ${MEDAL_TESTS[@]+"${MEDAL_TESTS[@]}"}); then
  ok "金牌賽 pytest"
else
  bad "金牌賽 pytest 有失敗（完整跑時 test_rule_map::test_rule_ranges_sample_unchanged 是已知的浮點假失敗）"
fi

step "體檢：GUI 能不能啟動"
PORT=8799
uv run python gui/app.py --no-browser --port $PORT > /dev/null 2>&1 &
GUI_PID=$!
GUI_OK=0
for _ in $(seq 1 30); do
  sleep 1
  if .venv/bin/python - "$PORT" <<'EOF' 2>/dev/null
import json, sys, urllib.request
base = f"http://127.0.0.1:{sys.argv[1]}"
assert urllib.request.urlopen(base + "/", timeout=2).status == 200
m = json.load(urllib.request.urlopen(base + "/api/medal/overview", timeout=5))
r = json.load(urllib.request.urlopen(base + "/api/ranking/overview?name=config", timeout=5))
assert m["ok"] and r["ok"] and m["drl_ok"], (m, r)
EOF
  then GUI_OK=1; break; fi
done
kill $GUI_PID 2>/dev/null; wait $GUI_PID 2>/dev/null
if [ $GUI_OK -eq 1 ]; then ok "GUI 啟動（http://127.0.0.1:8765，雙擊 gui/start.command 開）"; else bad "GUI 啟動失敗（手動跑 uv run python gui/app.py 看錯誤）"; fi

echo
echo "================ 結果 ================"
printf '%s\n' "${RESULTS[@]}"
case "${RESULTS[*]}" in *✕*) exit 1 ;; esac
exit 0
