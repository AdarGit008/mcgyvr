"""``mcgyvr setup`` with no Docker daemon writes the weaker mode, and says so.

A setup that names ``docker`` on a machine with no daemon is refused at its
first run. So init, which already asked whether a daemon answers, makes the
choice at setup: ``sandbox.mode: tempdir``, with a comment beside it saying it
is the weaker mode and how to move to ``docker``. With a daemon, init writes
``docker`` as before and says nothing of the kind.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from mcgyvr import detect
from mcgyvr.config import POLICY_FILENAME
from mcgyvr.config import load as load_config
from mcgyvr.initialize import initialize
from tests.machine_shapes import detection, shape, with_server

_MACHINE = shape("one-card")
_FREE = next(
    kind
    for kind, _, _ in detect.PORT_CONVENTIONS
    if kind not in {server.kind for server in _MACHINE.servers}
)

#: A machine with a server that lists a model, so init has a unit to bind.
SERVING = detection(with_server(_MACHINE, kind=_FREE, models=("example-model",)))


def _sandbox_block(path: Path) -> str:
    """The ``sandbox:`` block of the written policy, its comments included.

    It runs to the next top-level key's comment: the block's own keys and
    their comments are indented.
    """
    text = (path / POLICY_FILENAME).read_text(encoding="utf-8")
    start = text.index("\nsandbox:\n")
    return text[start : text.find("\n\n# ", start + 1)]


def test_no_daemon_writes_tempdir_with_how_to_move_to_docker(tmp_path: Path) -> None:
    setup = tmp_path / "setup"
    initialize(setup, detection=dataclasses.replace(SERVING, docker=False))

    config = load_config(setup)
    assert config.get("sandbox.mode") == "tempdir"
    assert config.get("sandbox.allow_fallback") is False
    block = " ".join(_sandbox_block(setup).split())
    assert "mode: tempdir" in block
    assert "No Docker daemon answered" in block
    assert "weaker mode" in block
    assert "`mode: docker`" in block


def test_a_daemon_writes_docker_and_no_such_comment(tmp_path: Path) -> None:
    setup = tmp_path / "setup"
    initialize(setup, detection=dataclasses.replace(SERVING, docker=True))

    assert load_config(setup).get("sandbox.mode") == "docker"
    block = " ".join(_sandbox_block(setup).split())
    assert "mode: docker" in block
    assert "No Docker daemon answered" not in block
