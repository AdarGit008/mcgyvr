"""A failure record reads back as the record it was, from JSON and from a result file.

The record is what the calling agent replans from, so the copy in the result
file has to be the record and not a rendering of it: :meth:`FailureNotes.as_json`
writes it, :meth:`FailureNotes.from_json` reads it back equal, and a real
``mcgyvr direct`` writes it under ``attempts[].notes`` beside the `findings` lines
rendered from it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcgyvr.gate.findings import Finding
from mcgyvr.gate.runner import GateResult, InconclusiveRung
from mcgyvr.notes import SCHEMA_ID, FailureNotes, NotesError
from tests import livejournal as lj


def _record() -> FailureNotes:
    gate = GateResult(
        findings=(
            Finding(
                check="lint", path="src/a.py", line=3, code="F401", message="unused"
            ),
            Finding(
                check="acceptance",
                path="pytest -q",
                names_a_file=False,
                code="failed",
                message="acceptance command failed (exit 1)\nE assert 1 == 2",
                command="pytest -q",
                exit_code=1,
            ),
        ),
        inconclusive=(
            InconclusiveRung(adapter="python", rung="format", tool="ruff", exit_code=2),
        ),
    )
    record = FailureNotes.of_gate(gate, rung="local_a", family="local", attempt=2)
    assert record is not None
    return record


def test_a_record_round_trips_through_json() -> None:
    record = _record()

    data = json.loads(json.dumps(record.as_json()))

    assert data["schema"] == SCHEMA_ID
    assert data["checks"] == ["lint", "acceptance", "format"]
    assert data["notes"][1]["command"] == "pytest -q"
    assert data["notes"][1]["path"] is None
    assert FailureNotes.from_json(data) == record


@pytest.mark.parametrize(
    "broken",
    [
        {"schema": "mcgyvr.failure_notes/0"},
        {"surprise": 1},
        {"attempt": True},
        {"notes": [{"check": "lint", "kind": "guess", "message": "m"}]},
    ],
)
def test_a_record_that_is_not_one_is_refused_by_name(broken: dict[str, object]) -> None:
    data = {**_record().as_json(), **broken}

    with pytest.raises(NotesError):
        FailureNotes.from_json(data)


def test_a_run_writes_the_record_into_the_result_file(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The real run path: a rejected attempt's record, read back from the file."""
    lj.scripted(monkeypatch, lj.BAD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    config = lj.make_config(tmp_path / "setup", journal_dir=tmp_path / "journal")
    contract = lj.make_contract(tmp_path / "impl.yaml")

    assert lj.main(lj.run_args(contract, repo, config)) == 1

    result = json.loads(lj.result_of(contract).read_text())
    (attempt,) = result["attempts"]
    record = FailureNotes.from_json(attempt["notes"])
    assert (record.rung, record.family, record.attempt) == ("local_qwen-7b", "local", 1)
    assert attempt["findings"] == list(record.findings)
    (note,) = record.notes
    assert (note.check, note.code) == ("acceptance", "demonstration-failed")
    assert note.command == "sh -c 'grep -q VALUE src/pkg/messy.py'"
    assert note.exit_code == 1
