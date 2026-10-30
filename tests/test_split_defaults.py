"""拆棒預設、明確關閉與 CPU 上限；直接執行，不需要 pytest。"""
import copy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import odc.config.defaults as ref_defaults
import odc.pipeline.legalize as ref_legalize
from odc.config.validator import validate_config, ConfigValidationError


class SplitDefaultsTests(unittest.TestCase):
    def options(self, strategy):
        config = copy.deepcopy(ref_defaults.DEFAULT_CONFIG)
        config["strategy"].update(strategy)
        validate_config(config)
        return ref_legalize.split_options(config)

    def test_missing_keys(self):
        with patch.object(os, "cpu_count", return_value=8):
            for config in ({}, {"strategy": {}}, ref_defaults.DEFAULT_CONFIG):
                self.assertEqual(ref_legalize.split_options(config), {
                    "n_span": 1, "maxiter": 1000, "fast_fd": False,
                    "jacobian": "stm", "workers": 3, "starts": [0, 0.75, 1],
                    "prune_reopt_tol": 0.001, "wall_budget": 600.0,
                })
            self.options({})

    def test_explicit_legacy_values(self):
        for starts in (None, []):
            for off in (0, None):
                with self.subTest(starts=starts, off=off):
                    options = self.options({
                        "SPLIT_JACOBIAN": "fd", "SPLIT_WORKERS": 1,
                        "SPLIT_MULTISTART": starts, "SPLIT_PRUNE_REOPT_MPS": off,
                        "SPLIT_WALL_BUDGET_SEC": off, "SPLIT_FAST_FD": False,
                    })
                    self.assertEqual(options, {
                        "n_span": 1, "maxiter": 1000, "fast_fd": False,
                        "jacobian": "fd", "workers": 1, "starts": None,
                        "prune_reopt_tol": None, "wall_budget": None,
                    })

    def test_individual_overrides(self):
        with patch.object(os, "cpu_count", return_value=8):
            for key, value, option, expected in (
                ("SPLIT_JACOBIAN", "fd", "jacobian", "fd"),
                ("SPLIT_WORKERS", 2, "workers", 2),
                ("SPLIT_MULTISTART", [0, 0.5], "starts", [0, 0.5]),
                ("SPLIT_PRUNE_REOPT_MPS", 2, "prune_reopt_tol", 0.002),
                ("SPLIT_WALL_BUDGET_SEC", 30, "wall_budget", 30.0),
                ("SPLIT_FAST_FD", True, "fast_fd", True),
            ):
                with self.subTest(key=key):
                    self.assertEqual(self.options({key: value})[option], expected)

    def test_workers_clamped_to_cpu_count(self):
        for cores, expected in ((1, 1), (2, 2), (3, 3), (8, 3), (None, 1), (0, 1)):
            with self.subTest(cores=cores), patch.object(os, "cpu_count", return_value=cores):
                self.assertEqual(self.options({})["workers"], expected)
                self.assertEqual(self.options({"SPLIT_WORKERS": 1})["workers"], 1)
                self.assertEqual(self.options({"SPLIT_WORKERS": 10})["workers"], max(1, cores or 1))

    def test_blas_lock_uses_default_jacobian(self):
        for strategy, locked in (({}, True), ({"SPLIT_JACOBIAN": "fd"}, False),
                                 ({"SPLIT_JACOBIAN": "fd", "SPLIT_FAST_FD": True}, True)):
            with self.subTest(strategy=strategy), \
                 patch.object(ref_legalize, "threadpool_limits") as limit, \
                 patch.object(ref_legalize, "legalize_violating_winner", return_value=None):
                result = ref_legalize._legalize_stage({"strategy": strategy}, [], [], {}, None)
                self.assertEqual(result, ([], [], {}))
                self.assertEqual(limit.called, locked)
                if locked:
                    limit.assert_called_once_with(limits=1, user_api="blas")

    def test_invalid_values_still_rejected(self):
        for key, value in (("SPLIT_JACOBIAN", None), ("SPLIT_WORKERS", 0),
                           ("SPLIT_MULTISTART", [3]), ("SPLIT_PRUNE_REOPT_MPS", -1),
                           ("SPLIT_WALL_BUDGET_SEC", -1), ("SPLIT_FAST_FD", None)):
            with self.subTest(key=key), self.assertRaises(ConfigValidationError):
                self.options({key: value})


if __name__ == "__main__":
    unittest.main()
