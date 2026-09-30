"""A caller's gate that exits 130 or dies by a signal is a refusal by that gate.

130 is how the door says it was interrupted. A caller's gate that exits
with it, or is killed by a signal, has refused: the door stops with its own
refusal status, 2, and says the gate's exit status or the signal.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.serving import run
from tests import callergates as cg

ENDINGS = {
    "exit 130": ("sys.exit(130)", "exit 130"),
    "killed": ("os.kill(os.getpid(), signal.SIGKILL)", "signal 9"),
}


@pytest.mark.parametrize("ending", sorted(ENDINGS))
@pytest.mark.parametrize("verb", ["serve", "read"])
def test_a_callers_gate_ending_so_stops_the_door_with_its_refusal_status(
    verb: str,
    ending: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    root = tmp_path / "caller"
    code, words = ENDINGS[ending]
    cg.executable(
        root / "end.py",
        f"#!/usr/bin/env python3\nimport os, signal, sys\n{code}\n",
    )
    listed = cg.write_list(
        tmp_path / "gates.json", str(root), [cg.entry("end.py", "before")]
    )
    if verb == "serve":
        argv = cg.serve_argv(
            cg.compose_file(tmp_path / "c.yaml"), "--gates", str(listed)
        )
    else:
        argv = cg.read_argv("--gates", str(listed))

    status = run.main(argv)

    said = capsys.readouterr().err
    assert status == 2, said
    assert "end.py" in said and words in said, said
