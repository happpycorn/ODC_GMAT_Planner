"""找這台機器的 GmatConsole：GUI 和安裝腳本共用，只用標準函式庫。

順序：configs/local/config.json 的 local.gmat_console_path → 環境變數 GMAT_CONSOLE → 常見安裝位置。

    python gui/gmat_path.py                 # 印出找到的路徑；找不到結束碼 1
    python gui/gmat_path.py --write <路徑>  # 寫進 configs/local/config.json 的 local.gmat_console_path
"""
import argparse
import glob
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCAL_CONFIG = ROOT / "configs" / "local" / "config.json"
EXE = "GmatConsole.exe" if os.name == "nt" else "GmatConsole"


def configured():
    """config.json 裡寫的路徑（檔案不存在或沒寫就回 None）。"""
    try:
        with open(LOCAL_CONFIG, encoding="utf-8") as f:
            return json.load(f).get("local", {}).get("gmat_console_path") or None
    except (OSError, ValueError, AttributeError):
        return None


def candidates():
    """常見安裝位置，新版本排前面。"""
    home = Path.home()
    if sys.platform == "darwin":
        bases = [home / "Documents", Path("/Applications"), home / "Applications", home]
    elif os.name == "nt":
        bases = [Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
                 Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
                 Path("C:/"), home, home / "Documents"]
    else:
        bases = [home / "software" / "GMAT", home / "software", home, Path("/opt"), Path("/usr/local")]
    found = []
    for base in bases:
        for pattern in ("GMAT*", "GMAT*/GMAT*", "GMAT*/R*"):
            found += sorted(glob.glob(str(base / pattern / "bin" / EXE)), reverse=True)
    on_path = shutil.which(EXE)
    if on_path:
        found.append(on_path)
    return list(dict.fromkeys(found))


def resolve():
    """回傳 (路徑, 來源)；什麼都沒有時路徑是 None。設定或環境變數有寫就照用，存不存在由呼叫端檢查。"""
    path = configured()
    if path:
        return path, "configs/local/config.json"
    if os.environ.get("GMAT_CONSOLE"):
        return os.path.expanduser(os.environ["GMAT_CONSOLE"]), "環境變數 GMAT_CONSOLE"
    for path in candidates():
        if os.path.isfile(path):
            return path, "自動尋找"
    return None, None


def write(path):
    """把路徑寫進 config.json；config.json 要先存在（安裝腳本會先建好）。"""
    with open(LOCAL_CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    if cfg.get("local", {}).get("gmat_console_path") == path:
        return False
    cfg.setdefault("local", {})["gmat_console_path"] = path
    tmp = LOCAL_CONFIG.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)
        f.write("\n")
    os.replace(tmp, LOCAL_CONFIG)
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", metavar="PATH")
    args = ap.parse_args()
    if args.write:
        if not os.path.isfile(args.write):
            print(f"找不到檔案：{args.write}", file=sys.stderr)
            return 1
        print(("已寫入" if write(args.write) else "沒變") + f" {LOCAL_CONFIG}：{args.write}")
        return 0
    path, source = resolve()
    if not path:
        return 1
    print(path)
    print(f"（來源：{source}）", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
