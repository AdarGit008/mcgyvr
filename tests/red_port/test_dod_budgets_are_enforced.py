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

**Asserted as what the run does, not as what a new function returns.** The whole
finding is "the key exists and nothing reads it"; a test requiring a fresh
``acceptance_for`` or ``sandbox_mode`` would be satisfied by adding one that
nothing calls, which is the defect again with a better name. So the ceiling is
asserted by running a command that outlives it, and the mode by parsing the
command line the user actually types.

What must be observably true: the value in the file is the value the run uses.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.red_port.conftest import required

CONFIG = """
version: 1
sources:
  local:
    base_url: "http://localhost:8080"
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


SLOW = """
id: hangs
task_type: function_implementation
task: Anything; the acceptance command is the subject.
target: src/pkg/fetch.py
stop_conditions:
  - Nothing.
acceptance: ["python3 -c 'import time; time.sleep(25)'"]
limits:
  max_output_tokens: 64
scope:
  allow: ["src/pkg/**"]
"""


def test_an_acceptance_command_that_outlives_the_ceiling_is_stopped_by_it(
    repo: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The outcome, not the field.

    ``Acceptance.timeout`` being set to 7 and never handed to ``sandbox.run``
    would satisfy an assertion on the attribute and hang the run exactly as it
    hangs today. So the command sleeps well past a seven-second ceiling and the
    test is what happens. Twenty-five seconds rather than the two minutes a
    real hang would run for: long enough that no ceiling under fifteen could be
    mistaken for one, short enough that a RED run is not a coffee break.
    """
    import time

    from mcgyvr.contract import loads
    from mcgyvr.drive import gate_workspace
    from mcgyvr.sandbox.base import open_sandbox

    written = tmp_path / "mcgyvr.yaml"
    written.write_text(CONFIG, encoding="utf-8")
    monkeypatch.setenv("MCGYVR_CONFIG", str(written))

    started = time.monotonic()
    with open_sandbox(repo, mode="tempdir") as sandbox:
        result = gate_workspace(loads(SLOW), sandbox)
    elapsed = time.monotonic() - started

    assert elapsed < 15, (
        f"the config declares a 7s ceiling and the acceptance command ran for "
        f"{elapsed:.0f}s; a contract's shell has no wall clock"
    )
    assert not result.accepted, "a command stopped by the ceiling is not a pass"


def test_the_sandbox_mode_comes_from_the_file_when_no_flag_is_typed() -> None:
    """Asserted on the command line a person actually types.

    A helper that resolves config-then-flag correctly changes nothing while
    ``--sandbox`` carries an argparse default of ``docker``: the flag is never
    absent, so the config is never consulted. What must be true is that a run
    with no ``--sandbox`` on it leaves the mode unset for the config to supply.
    """
    parser = required(
        "leave the sandbox mode unset on the command line when nobody typed "
        "one, so the config can supply it",
        lambda: __import__("mcgyvr.cli", fromlist=["build_parser"]).build_parser,
    )()
    args = parser.parse_args(["run", "c.yaml", "--repo", "."])
    assert args.sandbox is None, (
        f"--sandbox defaults to {args.sandbox!r}, so a config that says "
        "tempdir is never reached on a machine with Docker"
    )


def test_a_typed_flag_still_wins_over_the_file() -> None:
    """The precedence that must not invert.

    A flag typed at the terminal is a person overriding their own file and
    outranks it. Only the no-flag case changes.
    """
    parser = required(
        "leave the sandbox mode unset on the command line when nobody typed "
        "one, so the config can supply it",
        lambda: __import__("mcgyvr.cli", fromlist=["build_parser"]).build_parser,
    )()
    args = parser.parse_args(["run", "c.yaml", "--repo", ".", "--sandbox", "docker"])
    assert args.sandbox == "docker"
