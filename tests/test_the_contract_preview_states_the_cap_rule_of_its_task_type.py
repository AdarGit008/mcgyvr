"""`mcgyvr contract` states the cap rule of the contract's task type.

Owner decision (2026-10-14, e2e run 3 T1) decides the cap model by task type,
and the preview is where an author reads which rule their contract is under
before anything is spent:

* model-written `code` that states a cap: ``<=N output tokens``;
* model-written `code` that states none: valid, and ``mcgyvr run`` refuses it
  until ``limits.max_output_tokens`` is stated;
* `chat` and `agent`: a raw connection — no output cap, no prompt checks;
* a deterministic operation calls no model: no output cap and no attempts.
  It used to print ``<=256 output tokens ... 2 attempt(s)``, a cap and a retry
  budget for a model that is never called;
* `media` is under development and unchanged.
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

CHAT = "id: sky\ntask_type: chat\ntask: Why is the sky blue?\n"

AGENT = 'id: brief\ntask_type: agent\ntask: Summarise.\nsources: ["src/r.txt"]\n'

MEDIA = """\
id: square
task_type: media
task: Draw a red square.
target: out/square.png
stop_conditions: ["The size is not stated."]
output_schema: media_artifact
media_kind: image
scope:
  allow: ["out/**"]
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


@pytest.mark.parametrize("text", [CHAT, AGENT], ids=["chat", "agent"])
def test_a_session_is_a_raw_connection(
    text: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    said = limits(tmp_path, text, capsys)
    assert "raw connection: no output cap, no prompt checks" in said, said
    assert "output tokens" not in said and "prompt tokens" not in said, said


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


def test_media_is_unchanged(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    said = limits(tmp_path, MEDIA, capsys)
    assert said.startswith("limits:  uncapped (raw text)"), said
