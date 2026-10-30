# 此入口把專案根目錄加入模組搜尋路徑，再交由 CLI 分派子命令。
# 主要入口為 odc.cli.main，其回傳值直接作為行程結束碼。
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from odc.cli import main

if __name__ == "__main__":
    sys.exit(main())
