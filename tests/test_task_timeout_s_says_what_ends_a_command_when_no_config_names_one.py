"""`task_timeout_s` says what ends a command when no config names a ceiling.

The key is the task's wall-clock ceiling and the queue wait for a busy unit's
slot. With no config at all, `task_ceiling` reads no ceiling, and each command
still ends at the sandbox's own `DEFAULT_COMMAND_TIMEOUT_S`: the key's text,
and SETUP.md rendered from it, name that number from the constant itself, so
the two cannot drift.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr import docgen
from mcgyvr.config import SCHEMA
from mcgyvr.drive import gate
from mcgyvr.sandbox.base import DEFAULT_COMMAND_TIMEOUT_S, command_timeout


def _text() -> str:
    (field,) = [f for f in SCHEMA if f.name == "task_timeout_s"]
    return " ".join(field.doc.split())


def test_the_text_names_the_queue_wait_and_the_sandboxs_own_default() -> None:
    text = _text()
    assert "wait for a busy unit's slot" in text
    assert f"the sandbox's own {DEFAULT_COMMAND_TIMEOUT_S:g} s default" in text
    assert f"the sandbox's own {DEFAULT_COMMAND_TIMEOUT_S:g} s default" in " ".join(
        docgen.render_setup().split()
    )


def test_with_no_config_a_command_still_ends_at_that_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from mcgyvr import config

    def missing() -> config.Config:
        raise config.ConfigMissingError(tmp_path / "nowhere")

    monkeypatch.setattr(config, "load", missing)
    assert gate.task_ceiling() is None
    assert command_timeout(gate.task_ceiling()) == DEFAULT_COMMAND_TIMEOUT_S
