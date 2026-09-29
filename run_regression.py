"""一鍵賽前回歸（HAP-37）：把 tests/ 底下所有 test_*.py 一次跑完，給一個乾淨的
PASS/FAIL 總結。平常用 --quick（約 60 秒），commit 前跑 full（約 6 分鐘）。

為什麼用子行程一支一支跑，而不是 import 進來呼叫 main()
──────────────────────────────────────────────────────
每支測試都是「跑到底、失敗就 sys.exit(1)」的獨立腳本，而且各自有模組級的 FAILS
狀態、還會觸發 numba JIT。用子行程跑天生隔離，一支炸掉不會污染別支，退出碼也直接
就是「有沒有失敗」——跟這些測試本來被設計的跑法（uv run python tests/test_x.py）
完全一致，不用為了湊成一個 runner 去改動任何一支測試。

跑法：
  uv run python run_regression.py            # 跑全部
  uv run python run_regression.py --quick    # 跳過檔頂標記 SLOW = True 的測試
  uv run python run_regression.py -q         # 只印每支的 PASS/FAIL 一行，不印內文
  uv run python run_regression.py test_rotation_invariance   # 只跑名字含這個字串的
"""

import argparse
import ast
import glob
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
TESTS_DIR = os.path.join(ROOT, "tests")


def is_slow(path):
    """只解析檔案頂層的 SLOW = True，不 import 或執行測試。"""
    with open(path, encoding="utf-8") as source:
        module = ast.parse(source.read(), filename=path)
    return any(
        isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "SLOW" for target in node.targets)
        and isinstance(node.value, ast.Constant)
        and node.value.value is True
        for node in module.body
    )


def discover(filters, quick=False):
    paths = sorted(glob.glob(os.path.join(TESTS_DIR, "test_*.py")))
    if filters:
        paths = [p for p in paths if any(f in os.path.basename(p) for f in filters)]
    if quick:
        paths = [p for p in paths if not is_slow(p)]
    return paths


def run_one(path, quiet):
    """跑一支測試，回傳 (通過?, 耗時秒, 輸出文字)。"""
    t0 = time.time()
    proc = subprocess.run(
        [sys.executable, path],
        cwd=ROOT, capture_output=True, text=True,
    )
    elapsed = time.time() - t0
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, elapsed, out


def main():
    parser = argparse.ArgumentParser(description="賽前回歸：預設 full，平常可用 --quick。")
    parser.add_argument("--quick", action="store_true", help="跳過標記 SLOW = True 的測試")
    parser.add_argument("-q", action="store_true", dest="quiet", help="只印每支 PASS/FAIL，失敗仍印輸出")
    parser.add_argument("filters", nargs="*", help="只跑檔名含任一字串的測試")
    args = parser.parse_args()
    quiet = args.quiet

    paths = discover(args.filters, quick=args.quick)
    if not paths:
        print("找不到符合的測試（tests/test_*.py；--quick 會排除 slow）。")
        sys.exit(2)

    mode = "quick" if args.quick else "full"
    print(f"=== 賽前回歸（{mode}）：{len(paths)} 支測試 ===\n")
    results = []
    for path in paths:
        name = os.path.basename(path)
        passed, elapsed, out = run_one(path, quiet)
        results.append((name, passed, elapsed))
        tag = "✅ PASS" if passed else "❌ FAIL"
        print(f"{tag}  {name}  ({elapsed:.1f}s)")
        # 失敗一定把內文印出來（不管 -q）；成功時只有非 -q 才印，方便看細節
        if not passed:
            print("  ── 輸出 ──")
            for line in out.rstrip().splitlines():
                print("  " + line)
            print()
        elif not quiet:
            # 只回顯 check() 印出來的通過行（固定是 "  ✅ " 開頭）。刻意不撈 ❌ 開頭的
            # 行：這支測試退出碼已經是 0（權威判定為通過），裡面若有 ❌ 字樣，那是被測
            # 程式**故意**印的內容（例如 test_tiebreak 的全違規案例會印「最佳化失敗」），
            # 撈進來只會在賽前虛驚一場。
            for line in out.splitlines():
                if line.startswith("  ✅"):
                    print("  " + line.strip())

    n_pass = sum(1 for _, p, _ in results if p)
    total_t = sum(t for _, _, t in results)
    print(f"\n=== {n_pass}/{len(results)} 支通過，總耗時 {total_t:.1f}s ===")
    if n_pass != len(results):
        failed = "、".join(n for n, p, _ in results if not p)
        print(f"❌ 失敗：{failed}")
        sys.exit(1)
    print("✅ 全部通過——地基乾淨。")


if __name__ == "__main__":
    main()
