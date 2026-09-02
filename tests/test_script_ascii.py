"""GMAT 腳本的 ASCII fail-fast 防呆（HAP-34）。

GMAT 的腳本語言是純 ASCII。非 ASCII 字元（設定名稱帶中文、貼進來的智慧引號/全形
符號/長破折號）寫成 UTF-8 檔 GMAT 不一定解析得了，而且是**比賽當天 GMAT 實際跑下去
才炸**的那種無聲失敗。_require_ascii 在產生階段就擋，指出哪一行哪個字元。

這份測試驗兩個方向：正常（純 ASCII，含官方範例真的走一遍 script_generator）不受影響、
非 ASCII 一定被擋且訊息可用。

跑法：uv run python tests/test_script_ascii.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import warnings
warnings.filterwarnings("ignore")

from src.script_generator import script_generator, _require_ascii

FAILS = []


def check(name, cond):
    print(("  ✅ " if cond else "  ❌ ") + name)
    if not cond:
        FAILS.append(name)


def main():
    print("=== GMAT 腳本 ASCII 防呆（HAP-34）===")

    # ── 純 ASCII 一律放行 ──
    check("純 ASCII 內容原樣放行", _require_ascii("Create Spacecraft ShipA;\nx = 1.0;") is not None)

    # ── 官方範例真的走一遍 script_generator，必須無錯且寫出的檔是 ASCII ──
    path = script_generator(
        6978.0, 0.0, 45.0, 0.0, 0.0, 0.0,
        6878.0, 0.0, 135.0, 30.0, 0.0, 60.0,
        burns=[(0.1, 0.0, 0.0)], times=[3000.0], aim_point=(6978.0, 0.0, 0.0),
        max_dv=1.5, gravity_degree=4, output_filename="_test_ascii_official.txt",
    )
    raw = open(path, "rb").read()
    is_ascii = True
    try:
        raw.decode("ascii")
    except UnicodeDecodeError:
        is_ascii = False
    check("官方範例照常產生、且寫出的檔是純 ASCII", is_ascii and len(raw) > 0)
    # 收尾：這是測試產物，不留在 outputs/
    try:
        os.remove(path)
    except OSError:
        pass

    # ── 各類非 ASCII 都要被擋，且訊息指出正確行號 ──
    for label, text, want_line in [
        ("中文字元", "line1\nName = '目標';\nline3", 2),
        ("智慧引號", "a = “hi”;", 1),
        ("全形符號", "b = 1／2;", 1),
        ("長破折號", "c = 1 — 2;", 1),
    ]:
        blocked = False
        line_ok = False
        try:
            _require_ascii(text)
        except ValueError as exc:
            blocked = True
            line_ok = f"第 {want_line} 行" in str(exc)
        check(f"{label}被擋下且指出第 {want_line} 行", blocked and line_ok)

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} 項失敗：" + "、".join(FAILS))
        sys.exit(1)
    print("✅ 全部通過")


if __name__ == "__main__":
    main()
