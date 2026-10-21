"""`mcgyvr contract` states the cap rule of the contract's task type.

The cap model is decided by task type,
and the preview is where an author reads which rule their contract is under
before anything is spent:

* model-written `code` that states a cap: ``<=N output tokens``;
* model-written `code` that states none: valid, and ``mcgyvr run`` refuses it
  until ``limits.max_output_tokens`` is stated;
* a deterministic operation calls no model: no output cap and no attempts.
  It used to print ``<=256 output tokens ... 2 attempt(s)``, a cap and a retry
  budget for a model that is never called.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.contract import loads
from tests import livejournal as lj

CODE = """\
id: impl
task_type: code
task: Set VALUE to 1.
target: src/pkg/value.py
stop_conditions: ["The value is not stated."]
scope:
  allow: ["src/**"]
"""

FORMAT = """\
id: format-pkg
task_type: code
operation: format
task: Reformat the module with the project's formatter.
target: src/pkg/messy.py
scope:
  allow: ["src/pkg/**"]
"""


def limits(tmp_path: Path, text: str, capsys: pytest.CaptureFixture[str]) -> str:
    """The preview's `limits:` line, or "" when it prints none."""
    path = lj.make_contract(tmp_path / "contract.yaml", text)
    assert lj.main(["contract", str(path)]) == 0
    out = capsys.readouterr().out
    assert "valid" in out, out
    return next((line.strip() for line in out.splitlines() if "limits:" in line), "")


def test_code_with_a_cap_states_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    said = limits(tmp_path, CODE + "limits:\n  max_output_tokens: 512\n", capsys)
    assert said.startswith("limits:  <=512 output tokens"), said


def test_code_without_a_cap_says_run_refuses_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    said = limits(tmp_path, CODE, capsys)
    assert "`mcgyvr run` refuses it until `limits.max_output_tokens` is stated" in said


def test_a_deterministic_operation_shows_no_cap_and_no_attempts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert loads(FORMAT).limits.max_output_tokens is None
    path = lj.make_contract(tmp_path / "format.yaml", FORMAT)
    assert lj.main(["contract", str(path)]) == 0
    out = capsys.readouterr().out
    assert "deterministic tier" in out, out
    assert "output tokens" not in out, out
    assert "attempt" not in out, out
