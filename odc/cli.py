"""定義使用者子命令，將參數交給既有工具處理。
主要入口為 main；工具模組只在選定子命令後載入。
"""
import argparse
import importlib
from pathlib import Path
import sys

from odc.paths import ROOT


COMMANDS = {
    'new-config': ('odc.tools.new_config', None, False, '由共用情境建立本機設定檔'),
    'solve': ('odc.pipeline.stages', '--config', False, '搜尋任務並依序產出方案與腳本'),
    'resume': ('odc.pipeline.stages', '--from-winner', True, '讀取拆棒前贏家，接續合法化與輸出'),
    'export': ('odc.pipeline.stages', '--from-mission', True, '讀取任務方案，產出 GMAT 腳本'),
    'retarget': ('odc.pipeline.stages', '--from-mission', True, '在全攝動模型下重新瞄準已存方案'),
    'verify': ('odc.pipeline.stages', '--verify-script', True, '使用 GMAT 驗證既有腳本'),
    'check': ('odc.tools.check_problem', '--config', True, '檢查情境的軌道、規則與參數'),
    'feasibility': ('odc.tools.feasibility', '--config', False, '評估情境可行性與合法解稀有程度'),
    'sweep-burns': ('odc.tools.sweep_burns', '--config', False, '粗掃燃燒次數並精查候選範圍'),
    'sweep': ('odc.tools.sweep_params', None, False, '執行情境、種子與搜尋參數的批次實驗'),
    'test': ('odc.tools.regression', None, False, '執行獨立腳本形式的回歸測試'),
    'tmax': ('odc.tools.tmax_from_boundary', None, False, '由任務邊界計算可用時間'),
    'scoring': ('odc.tools.check_scoring_params', None, False, '換算與驗算官方計分參數'),
    'outputs': ('odc.tools.output_inventory', None, False, '索引、封存及還原本機執行成果'),
}


def _parser():
    parser = argparse.ArgumentParser(
        prog='odc', description='軌道攔截設計賽：任務規劃與驗證工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='常用範例：\n'
               '  uv run python odc.py solve configs/shared/ranking_round.json --no-gmat\n'
               '  uv run python odc.py resume winner_presplit_seed0.json --no-gmat\n'
               '  uv run python odc.py test --quick -q',
    )
    commands = parser.add_subparsers(dest='command', metavar='子命令')
    for command, (_, _, _, description) in COMMANDS.items():
        commands.add_parser(command, help=description, add_help=False)
    return parser


def _translate(command, argv, parser):
    _, flag, required, _ = COMMANDS[command]
    translated = list(argv)
    if flag:
        positional = translated.pop(0) if translated and not translated[0].startswith('-') else None
        supplied = any(arg == flag or arg.startswith(flag + '=') for arg in translated)
        if positional is not None and supplied:
            parser.error(f'{command} 的位置參數與 {flag} 不可同時指定')
        if positional is not None:
            translated = [flag, positional, *translated]
        elif required and not supplied and not any(arg in ('-h', '--help') for arg in translated):
            parser.error(f'{command} 需要指定輸入檔案')
    if command == 'retarget' and '--retarget-full-perturbation' not in translated:
        translated.append('--retarget-full-perturbation')
    return translated


def main(argv=None):
    if Path.cwd().resolve() != ROOT:
        print(f'請先 cd 到專案根目錄：{ROOT}', file=sys.stderr)
        return 2
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = _parser()
    if not argv:
        parser.print_help()
        return 0
    args = parser.parse_args(argv[:1])
    translated = _translate(args.command, argv[1:], parser)
    module = importlib.import_module(COMMANDS[args.command][0])
    if COMMANDS[args.command][0] == 'odc.pipeline.stages':
        try:
            result = module.main(translated)
        except module.NoLegalRouteError:
            return module.EXIT_NO_LEGAL_ROUTE
    else:
        result = module.main(translated)
    return 0 if result is None else result
