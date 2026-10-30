"""由共用情境建立不覆蓋既有檔案的本機設定。
主要入口為 main，建立後使用既有設定驗證函式檢查內容。
"""
import argparse
import json
from pathlib import Path
import sys

from odc.paths import ROOT
from odc.config.validator import validate_config, ConfigValidationError


def main(argv=None):
    parser = argparse.ArgumentParser(description='從共用情境建立本機設定檔')
    parser.add_argument('name', help='本機設定名稱，存入 configs/local/<名稱>.json')
    parser.add_argument('--from', dest='source', default='ranking_round', help='共用情境名稱（預設 ranking_round）')
    parser.add_argument('--gmat-console', help='寫入本機的 GmatConsole 執行檔路徑')
    args = parser.parse_args(argv)
    for name in (args.name, args.source):
        if not name or Path(name).name != name or name in ('.', '..'):
            parser.error('設定名稱必須是不含目錄的檔名')
    source = ROOT / 'configs' / 'shared' / (args.source if args.source.endswith('.json') else args.source + '.json')
    target = ROOT / 'configs' / 'local' / (args.name if args.name.endswith('.json') else args.name + '.json')
    created = False
    try:
        data = source.read_bytes()
        config = json.loads(data)
        if args.gmat_console is not None:
            config.setdefault('local', {})['gmat_console_path'] = args.gmat_console
            data = (json.dumps(config, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            created = True
            stream.write(data)
        validate_config(config)
    except (OSError, ValueError, ConfigValidationError) as error:
        if created:
            target.unlink()
        print(f'建立設定失敗：{error}', file=sys.stderr)
        return 1
    print(f'已建立本機設定：{target}')
    return 0
