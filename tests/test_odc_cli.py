"""檢查子命令參數翻譯、衝突、延遲載入及結束碼傳遞。
以獨立腳本執行 unittest，主要入口為 unittest.main。
"""
import argparse
import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from odc import cli


class CliTests(unittest.TestCase):
    def test_each_command_forwards_original_argv(self):
        examples = {
            'new-config': (['sample', '--from', 'ranking_round'], ['sample', '--from', 'ranking_round']),
            'solve': (['a.json', '--no-gmat'], ['--config', 'a.json', '--no-gmat']),
            'resume': (['winner.json', '--no-gmat'], ['--from-winner', 'winner.json', '--no-gmat']),
            'export': (['mission.json', '--stop-after', 'export'], ['--from-mission', 'mission.json', '--stop-after', 'export']),
            'retarget': (['mission.json', '--retarget-burn', '2'], ['--from-mission', 'mission.json', '--retarget-burn', '2', '--retarget-full-perturbation']),
            'verify': (['script.txt', '--quiet'], ['--verify-script', 'script.txt', '--quiet']),
            'check': (['a.json'], ['--config', 'a.json']),
            'feasibility': (['a.json', '--grid', '3'], ['--config', 'a.json', '--grid', '3']),
            'sweep-burns': (['a.json', '--burns', '2-3'], ['--config', 'a.json', '--burns', '2-3']),
            'sweep': (['spec.json', '--dry-run'], ['spec.json', '--dry-run']),
            'test': (['--quick', '-q'], ['--quick', '-q']),
            'tmax': (['--boundary-km', '100000'], ['--boundary-km', '100000']),
            'scoring': (['--demo-prelim'], ['--demo-prelim']),
            'outputs': (['index'], ['index']),
        }
        self.assertEqual(set(examples), set(cli.COMMANDS))
        for name, (argv, expected) in examples.items():
            seen = []
            module = SimpleNamespace(main=lambda argv: seen.append(argv), NoLegalRouteError=RuntimeError)
            with self.subTest(command=name), patch.object(cli.importlib, 'import_module', return_value=module) as imported:
                self.assertEqual(cli.main([name, *argv]), 0)
            self.assertEqual(seen, [expected])
            imported.assert_called_once_with(cli.COMMANDS[name][0])
        with patch.object(cli.importlib, 'import_module', return_value=SimpleNamespace(main=lambda argv: len(argv))):
            self.assertEqual(cli.main(['solve']), 0)
            self.assertEqual(cli.main(['feasibility']), 0)
            self.assertEqual(cli.main(['sweep-burns']), 0)

    def test_positional_and_flag_conflict(self):
        for name, (_, flag, _, _) in cli.COMMANDS.items():
            if flag is None:
                continue
            for option in ([flag, 'b.json'], [flag + '=b.json']):
                with self.subTest(command=name, option=option), contextlib.redirect_stderr(io.StringIO()), \
                     patch.object(cli.importlib, 'import_module') as imported, self.assertRaises(SystemExit) as error:
                    cli.main([name, 'a.json', *option])
                self.assertEqual(error.exception.code, 2)
                imported.assert_not_called()

    def test_help_is_forwarded_for_every_command(self):
        def original(argv):
            argparse.ArgumentParser().parse_args(argv)
        for command in cli.COMMANDS:
            module = SimpleNamespace(main=original, NoLegalRouteError=RuntimeError)
            with self.subTest(command=command), contextlib.redirect_stdout(io.StringIO()), \
                 patch.object(cli.importlib, 'import_module', return_value=module), self.assertRaises(SystemExit) as result:
                cli.main([command, '--help'])
            self.assertEqual(result.exception.code, 0)
        with contextlib.redirect_stdout(io.StringIO()), patch.object(cli.importlib, 'import_module') as imported, \
             self.assertRaises(SystemExit) as result:
            cli.main(['--help'])
        self.assertEqual(result.exception.code, 0)
        imported.assert_not_called()

    def test_bootstrap_passes_system_exit_and_no_legal_route(self):
        code = '''from pathlib import Path
import runpy, sys
from types import SimpleNamespace
from odc import cli
class NoLegalRouteError(RuntimeError): pass
def stop(argv):
    if sys.argv[-1] == 'system': raise SystemExit(3)
    raise NoLegalRouteError()
cli.importlib.import_module = lambda name: SimpleNamespace(main=stop, NoLegalRouteError=NoLegalRouteError, EXIT_NO_LEGAL_ROUTE=3)
runpy.run_path(str(Path.cwd() / 'odc.py'), run_name='__main__')
'''
        for mode in ('system', 'no_legal'):
            result = subprocess.run([sys.executable, '-c', code, 'solve', mode], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 3, result.stdout + result.stderr)

    def test_wrong_working_directory_returns_two(self):
        with patch.object(cli.Path, 'cwd', return_value=ROOT.parent), contextlib.redirect_stderr(io.StringIO()) as output:
            self.assertEqual(cli.main(['--help']), 2)
        self.assertIn(str(ROOT), output.getvalue())

    def test_tmax_help_does_not_import_numba(self):
        code = '''import sys
from odc import cli
try: cli.main(['tmax', '--help'])
except SystemExit as error: assert error.code == 0
assert 'numba' not in sys.modules
'''
        result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_new_config_copy_override_existing_and_validation_cleanup(self):
        from odc.tools import new_config
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shared = root / 'configs' / 'shared'
            shared.mkdir(parents=True)
            source = shared / 'ranking_round.json'
            shutil.copyfile(ROOT / 'configs' / 'shared' / 'ranking_round.json', source)
            with patch.object(new_config, 'ROOT', root), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(new_config.main(['sample']), 0)
                target = root / 'configs' / 'local' / 'sample.json'
                self.assertEqual(target.read_bytes(), source.read_bytes())
                self.assertNotIn('local', json.loads(target.read_bytes()))
                self.assertEqual(new_config.main(['sample']), 1)
                self.assertEqual(target.read_bytes(), source.read_bytes())
                self.assertEqual(new_config.main(['with-console', '--from', 'ranking_round', '--gmat-console', 'GmatConsole.exe']), 0)
                with_console = json.loads((target.parent / 'with-console.json').read_bytes())
                self.assertEqual(with_console['local']['gmat_console_path'], 'GmatConsole.exe')
                invalid = json.loads(source.read_bytes())
                invalid['rules']['MAX_DV_MPS'] = -1
                (shared / 'invalid.json').write_text(json.dumps(invalid))
                self.assertEqual(new_config.main(['invalid-copy', '--from', 'invalid']), 1)
                self.assertFalse((target.parent / 'invalid-copy.json').exists())
                self.assertEqual(new_config.main(['missing', '--from', 'missing']), 1)
                self.assertFalse((target.parent / 'missing.json').exists())


if __name__ == '__main__':
    unittest.main()
