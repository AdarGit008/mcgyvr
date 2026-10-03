"""``mcgyvr init`` writes ``sandbox.allow_fallback`` and ``sandbox.network``.

Both have a default the loader fills in, and a default left out reads in the
file as ``# allow_fallback:  # unset`` — true of the file, false of the run.
So init writes each at the value the loader would use, as a live key, with
the schema's comment above it saying what it does and what the other choice
is: refuse or fall back to ``tempdir`` when no Docker daemon answers, and a
network the container reaches or ``none``. It writes them with a daemon and
without one, and the no-daemon comment stays beside ``mode`` alone.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from mcgyvr import detect
from mcgyvr.config import POLICY_FILENAME, SANDBOX_FIELDS
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

_DEFAULTS = {field.name: field.default for field in SANDBOX_FIELDS}


def _sandbox_lines(path: Path) -> list[str]:
    """The ``sandbox:`` block of the written policy, one line each."""
    text = (path / POLICY_FILENAME).read_text(encoding="utf-8")
    start = text.index("\nsandbox:\n")
    return text[start : text.find("\n\n# ", start + 1)].splitlines()


def _comment_above(lines: list[str], key_line: str) -> str:
    """The comment lines right above ``key_line``, joined into one text."""
    at = lines.index(key_line)
    above: list[str] = []
    for line in reversed(lines[:at]):
        if not line.strip().startswith("#"):
            break
        above.insert(0, line.strip().lstrip("#").strip())
    return " ".join(above)


@pytest.mark.parametrize("docker", [True, False], ids=["daemon", "no-daemon"])
def test_both_keys_are_written_live_at_the_value_the_loader_uses(
    tmp_path: Path, docker: bool
) -> None:
    setup = tmp_path / "setup"
    initialize(setup, detection=dataclasses.replace(SERVING, docker=docker))

    lines = _sandbox_lines(setup)
    assert "  allow_fallback: false" in lines
    assert f"  network: {_DEFAULTS['network']}" in lines
    assert not any(line.strip().startswith("# allow_fallback:") for line in lines)
    assert not any(line.strip().startswith("# network:") for line in lines)

    config = load_config(setup)
    assert config.get("sandbox.allow_fallback") is _DEFAULTS["allow_fallback"]
    assert config.get("sandbox.network") == _DEFAULTS["network"]


def test_each_comment_says_what_the_key_does_and_the_other_choice(
    tmp_path: Path,
) -> None:
    setup = tmp_path / "setup"
    initialize(setup, detection=dataclasses.replace(SERVING, docker=True))

    lines = _sandbox_lines(setup)
    fallback = _comment_above(lines, "  allow_fallback: false")
    assert "refused" in fallback
    assert "`tempdir`" in fallback
    network = _comment_above(lines, f"  network: {_DEFAULTS['network']}")
    assert "`none`" in network
    assert "`bridge`" in network


def test_the_no_daemon_comment_stays_beside_mode_alone(tmp_path: Path) -> None:
    setup = tmp_path / "setup"
    initialize(setup, detection=dataclasses.replace(SERVING, docker=False))

    lines = _sandbox_lines(setup)
    assert "No Docker daemon answered" in _comment_above(lines, "  mode: tempdir")
    assert "No Docker daemon answered" not in _comment_above(
        lines, "  allow_fallback: false"
    )
    assert "No Docker daemon answered" not in _comment_above(
        lines, f"  network: {_DEFAULTS['network']}"
    )
