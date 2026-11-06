"""當天流程彩排（tools/final_rehearsal.py）：GMAT 二體當真實世界、我方走 copilot.py final CLI。沒有 GmatConsole 時略過。"""
import os
from types import SimpleNamespace

import numpy as np
import pytest

from tools.final_rehearsal import parse_submission, write_official
from tools.gmat_verify import GMAT_CONSOLE


def test_parse_submission_reads_last_line():
    out = "建議 ...\n提交：逃方, 2, 1.0000, -2.5000, 3.1250\n"
    dv, line = parse_submission(out)
    np.testing.assert_allclose(dv, [1.0, -2.5, 3.125])
    assert line.startswith("提交：")


def test_written_official_files_parse_back(tmp_path):
    from game.official_io import read_official_state
    from physics import get_r0_v0
    state = {"pursuer": get_r0_v0(sma=7000.0, ecc=0.001, inc=30.0, raan=0.0, aop=0.0, ta=0.0),
             "evader": get_r0_v0(sma=7050.0, ecc=0.001, inc=30.0, raan=0.0, aop=0.0, ta=2.0)}
    for fmt in ("gmat", "csv", "text", "json"):
        got = read_official_state(write_official(tmp_path / f"s.{fmt}", state, fmt, 1200.0))
        for side in ("pursuer", "evader"):
            np.testing.assert_allclose(got[side][0], state[side][0], atol=1e-9)
            np.testing.assert_allclose(got[side][1], state[side][1], atol=1e-12)


@pytest.mark.skipif(not os.path.exists(GMAT_CONSOLE), reason="GmatConsole 不在這台機器上")
def test_rehearsal_end_to_end(tmp_path):
    from tools.final_rehearsal import rehearse
    args = SimpleNamespace(role="evader", opponent="capture_pursuer_fast", rules="configs/rulesets/final_official.json",
                           scenario="final", seed=0, fast=True, workdir=str(tmp_path / "reh"),
                           gmat_console=GMAT_CONSOLE)
    out = rehearse(args, log=lambda *a: None)
    assert out["outcome_gmat"] == out["outcome_engine"]
    assert out["we_won"]
    assert len(out["rounds"]) == 6
    assert all(r["consistency"].startswith("一致性檢查：通過") for r in out["rounds"][1:])
    assert os.path.exists(tmp_path / "reh" / "session.json")
