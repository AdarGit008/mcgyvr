"""A ``--gates`` that was given is a gate list, even when its name is empty.

A launcher that passes ``--gates "$LIST"`` with the variable unset hands the
door an empty name. The door refuses it before any gate runs, rather than
running without the caller's gates.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.serving import run
from tests import callergates as cg


@pytest.mark.parametrize("spelling", [["--gates", ""], ["--gates="]])
@pytest.mark.parametrize("verb", ["serve", "read"])
def test_an_empty_gate_list_name_is_refused_before_any_gate(
    verb: str,
    spelling: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    if verb == "serve":
        argv = cg.serve_argv(cg.compose_file(tmp_path / "compose.yaml"), *spelling)
    else:
        argv = cg.read_argv(*spelling)

    assert run.main(argv) == 2

    assert cg.log_lines(log) == []
    assert "--gates" in capsys.readouterr().err
