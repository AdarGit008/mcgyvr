"""``mcgyvr config`` lists the ladder in ladder order, and its header says so.

The same claim ``local_pool`` made: the header read "cheapest first", which is
only how a ladder is usually written. A policy that names the dear rung first,
``[pro, flash]``, was printed pro first under a header claiming the opposite.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.cli import main
from tests._helpers import write_setup

#: Two units, the dearer model named first on the ladder.
DEAR_FIRST = """\
units:
  pro:
    address: http://localhost:11435
    model: qwen2.5-coder:7b
    rig: workstation
  flash:
    address: http://localhost:11434
    model: qwen2.5-coder:3b
    rig: workstation
ladder:
- pro
- flash
"""


def test_the_ladder_header_names_ladder_order_and_the_rungs_follow_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = write_setup(tmp_path / "setup", DEAR_FIRST)

    assert main(["config", str(folder)]) == 0
    out = capsys.readouterr().out

    ladder = out[out.index("\nLadder") :]
    header = ladder.splitlines()[1]
    assert header == "Ladder, in ladder order:", header
    assert ladder.index("  pro ") < ladder.index("  flash "), ladder
