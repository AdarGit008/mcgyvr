"""Two knobs the config validates, `init` writes, and the run never reads.

``budgets.task_timeout_s`` is declared as the "wall-clock ceiling for one task,
including acceptance commands", defaults to 900, is written into every config
`mcgyvr init` creates, and is set to 900 in the owner's live config. The only
reader in the repository is ``tools/missions/run.py``. ``drive.gate_workspace``
builds its ``Acceptance`` without a timeout, so the field stays ``None`` and a
contract's arbitrary shell reaches ``sandbox.run(command, timeout=None)``. A
contract whose acceptance command hangs hangs the run, with a ceiling declared,
validated and ignored. ``consensus`` states the opposite in its own docstring:
"wall clock against ``budgets.task_timeout_s``".

``sandbox.mode`` is declared with the same weight — ``sandbox/base.py`` says
"``mode`` comes from ``sandbox.mode`` in config", and ``mcgyvr init`` reports
"sandbox.mode is `tempdir`" to the operator as a limit it detected. No
``config.get("sandbox.mode")`` exists. Both call sites pass the argparse default,
which is ``docker``. On a machine with Docker, an operator who wrote ``tempdir``
gets Docker and is told nothing.

These are stated together because they are one failure: a key whose value is
never consulted is a lie the config tells with a straight face, and the config is
the one surface a user is asked to edit.

What must be observably true: the value in the file is the value the run uses.
"""

from __future__ import annotations

from typing import Any

from tests.red_port.conftest import required

CONFIG = """
version: 1
sources:
  local:
    base_url: "http://localhost:11434"
    api: openai
    max_parallel: 1
ladder:
  tiers:
    - name: only
      source: local
      model: "a-model"
sandbox:
  mode: tempdir
budgets:
  task_timeout_s: 7
"""


def _config() -> Any:
    from mcgyvr.config import parse

    return parse(CONFIG)


def test_the_acceptance_ceiling_is_the_one_the_config_declares() -> None:
    """A command that outlives the declared ceiling must be stopped by it."""
    config = _config()
    bind = required(
        "bound an acceptance command by budgets.task_timeout_s, so a hung "
        "command ends the task instead of the run",
        lambda: __import__("mcgyvr.drive", fromlist=["acceptance_for"]).acceptance_for,
    )
    acceptance = bind(config, sandbox=None, commands=())
    assert acceptance.timeout == 7, (
        f"the config declares 7s and the gate carries {acceptance.timeout!r}; "
        "a contract's acceptance command runs with no wall clock"
    )


def test_the_sandbox_mode_is_the_one_the_config_declares() -> None:
    """`tempdir` in the file must mean tempdir on a machine that has Docker."""
    config = _config()
    chosen = required(
        "take the sandbox mode from the config when the command line does not "
        "override it",
        lambda: __import__("mcgyvr.cli", fromlist=["sandbox_mode"]).sandbox_mode,
    )
    assert chosen(config, requested=None) == "tempdir", (
        "the config says tempdir and the run opens docker; the operator is told nothing"
    )


def test_the_command_line_still_wins_over_the_file() -> None:
    """The precedence that must not invert.

    A flag typed at the terminal is a person overriding their own file, and it
    outranks it. What must change is only what happens when nobody typed one.
    """
    config = _config()
    chosen = required(
        "take the sandbox mode from the config when the command line does not "
        "override it",
        lambda: __import__("mcgyvr.cli", fromlist=["sandbox_mode"]).sandbox_mode,
    )
    assert chosen(config, requested="docker") == "docker"
