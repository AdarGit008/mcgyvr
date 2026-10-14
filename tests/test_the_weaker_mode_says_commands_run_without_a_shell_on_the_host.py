"""The weaker mode says what a contract's commands are, not "arbitrary shell".

A contract's acceptance commands are split like a shell would split them and
executed with no shell at all (``contract.py`` refuses shell syntax for that
reason). So "arbitrary shell" is false, and a user who knows it is false has
reason to doubt the rest of the warning. The rest is true and is the point:
each command runs whatever program it names, on the host, with only the host's
process, network and resource isolation, so Docker belongs on a machine that
runs contracts its user did not write.

Every place the weaker mode is explained says that: the notes ``setup`` and
``detect`` print, the note the sandbox prints when it opens in ``tempdir``, the
``sandbox.mode`` documentation and the sandbox package's own docstring.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

import mcgyvr.sandbox
from mcgyvr import detect as detect_module
from mcgyvr.config import field_at
from mcgyvr.initialize import initialize
from mcgyvr.sandbox.base import choose_mode
from tests.inits import KEYLESS_RIG


def _says_what_the_commands_are(text: str) -> None:
    """``text`` explains the weaker mode truthfully, and keeps its point."""
    flat = " ".join(text.split())
    assert "arbitrary shell" not in flat, flat
    assert "without a shell" in flat, flat
    assert "whatever program" in flat, flat
    assert "on the host" in flat, flat


def test_setup_says_the_commands_run_without_a_shell_and_to_install_docker(
    tmp_path: Path,
) -> None:
    found = dataclasses.replace(KEYLESS_RIG, docker=False)
    result = initialize(tmp_path / "setup", detection=found)
    note = next(limit for limit in result.limits if limit.startswith("sandbox.mode"))
    _says_what_the_commands_are(note)
    assert "install Docker before running contracts you did not write" in note


def test_detect_with_no_daemon_says_the_commands_run_without_a_shell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(detect_module, "_run", lambda cmd: None, raising=True)
    monkeypatch.setattr(
        detect_module, "_get_json", lambda url, timeout: None, raising=True
    )
    found = detect_module.detect()
    assert found.docker is False
    note = next(note for note in found.notes if note.startswith("Sandbox:"))
    _says_what_the_commands_are(note)


@pytest.mark.parametrize(
    ("configured", "docker", "fallback"),
    [("tempdir", True, False), ("docker", False, True)],
)
def test_the_sandbox_opening_in_tempdir_says_the_commands_run_without_a_shell(
    configured: str, docker: bool, fallback: bool
) -> None:
    choice = choose_mode(configured, docker, allow_fallback=fallback)
    assert choice.mode == "tempdir"
    _says_what_the_commands_are(" ".join(choice.notes))


def test_the_sandbox_mode_doc_says_the_commands_run_without_a_shell() -> None:
    mode = field_at("sandbox.mode")
    assert mode is not None
    _says_what_the_commands_are(mode.doc)


def test_the_sandbox_package_says_the_commands_run_without_a_shell() -> None:
    assert mcgyvr.sandbox.__doc__ is not None
    _says_what_the_commands_are(mcgyvr.sandbox.__doc__)
