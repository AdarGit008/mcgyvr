"""E6 — an attempt that raises must not destroy the waves that already ran.

:func:`mcgyvr.waves.run_waves` calls the attempt function unguarded, so a
contract whose attempt raises propagates straight out of the run — and with it
the record of every wave that already completed. A plan that committed two
steps and crashed on the third reports nothing: the commits are real and the
report is gone, which is the worst possible combination.

The fix catches the raise and records that contract as failed with the
exception named, so the run ends as a :class:`WaveRun` naming everything that
happened rather than as a traceback.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from mcgyvr.contract import loads
from tests.red_port.conftest import required

DRIVER = "run a set of contracts in dependency order and re-plan the work that failed"

CONTRACT = """
id: {id}
task_type: docstring
task: Document the {id} helper.
target: src/pkg/fetch.py
stop_conditions:
  - The helper's behaviour is not stated anywhere in the repo.
acceptance: ["python -c 'import sys; sys.exit(0)'"]
scope:
  allow: ["src/**/*.py"]
"""


def _driver() -> Any:
    return required(
        DRIVER, lambda: __import__("mcgyvr.waves", fromlist=["run_waves"]).run_waves
    )


def test_an_attempt_that_raises_does_not_destroy_the_run() -> None:
    """The earlier wave is still reported; the raise is recorded as a failure."""
    safe = loads(CONTRACT.format(id="safe"))
    exploding = loads(CONTRACT.format(id="explodes"))

    def attempt(contract: Any) -> Any:
        if contract.id == "explodes":
            raise RuntimeError("the rung exploded")
        return SimpleNamespace(ok=True)

    result = _driver()(contracts=(safe, exploding), attempt=attempt)

    assert result.completed == ("safe",), (
        f"the wave that already landed was lost: {result.completed}"
    )
    failed = {task: reason for task, reason in result.failed}
    assert "explodes" in failed, f"the raise was not recorded as a failure: {result}"
    assert "RuntimeError" in failed["explodes"], (
        f"the raise was recorded without naming the exception: {failed['explodes']}"
    )
