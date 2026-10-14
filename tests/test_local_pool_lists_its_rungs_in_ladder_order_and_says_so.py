"""``mcgyvr local_pool`` lists its rungs in ladder order, and its header says so.

The rungs are printed in the order the ladder names them, which is the order
work climbs them. The header said "cheapest first", which is only what a ladder
is usually written as: a policy that names the dear rung first, ``[pro,
flash]``, was printed pro first under a header claiming the opposite. The
header now names the order the list is actually in.
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


def test_the_header_names_ladder_order_and_the_rungs_follow_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = write_setup(tmp_path / "setup", DEAR_FIRST)

    assert main(["local_pool", str(folder)]) == 0
    out = capsys.readouterr().out

    header = out.splitlines()[0]
    assert header.endswith("2 usable rung(s), in ladder order:"), header
    assert "cheapest" not in header, header
    assert out.index("  pro ") < out.index("  flash "), out
