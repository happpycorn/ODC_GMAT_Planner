"""集中提供專案根目錄與本機預設設定檔位置。
主要入口為 default_config_path，舊路徑仍存在時提示搬移。
"""
import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def default_config_path():
    local = Path("configs") / "local" / "config.json"
    legacy = Path("configs") / "config.json"
    if not local.is_file() and legacy.is_file():
        logging.getLogger("odc").warning("請把本機設定搬到 configs/local/")
        return legacy
    return local
