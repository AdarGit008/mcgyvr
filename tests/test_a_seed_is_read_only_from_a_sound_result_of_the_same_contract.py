"""A seed is read only from a sound result of the same contract.

`mcgyvr.notes.seeded` is the one way a run is handed an earlier run's failure
notes: it reads that run's result file (or its parsed JSON, or a bare list of
records), and hands back the records as :class:`~mcgyvr.notes.CarriedNotes`,
each stamped with the run it came from. What it reads is a file on disk, so it
is untrusted: a result of another contract, a record of another schema version,
a path that is absolute or climbs out of the repository, a secret in a message,
a file too large or not JSON at all are each refused, or scrubbed, by name —
never a crash, never a guess.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.notes import (
    MAX_SEED_BYTES,
    CarriedNotes,
    FailureNote,
    FailureNotes,
    NoteKind,
    NotesError,
    primed,
    seeded,
)
from mcgyvr.worker.prompt import MAX_RECORDS_SHOWN, render_notes


def _record(rung: str = "local_a", attempt: int = 1, **note: Any) -> dict[str, Any]:
    """A record as a result file holds it; `path` is written in as given, the
    way a file on disk can hold anything."""
    path = note.pop("path", None)
    fields = {
        "check": "acceptance",
        "kind": NoteKind.FINDING,
        "message": "the demonstration failed",
        **note,
    }
    record = FailureNotes(
        rung=rung,
        family="local",
        attempt=attempt,
        checks=(fields["check"],),
        notes=(FailureNote(**fields),),
    ).as_json()
    if path is not None:
        record["notes"][0]["path"] = path
    return record


def _result(*records: dict[str, Any] | None, contract: str = "impl") -> dict[str, Any]:
    return {
        "contract": contract,
        "run": "20261023T101010.000000Z",
        "outcome": "ladder_spent",
        "attempts": [
            {"rung": "local_a", "attempt": n, "verdict": "failed", "notes": record}
            for n, record in enumerate(records, start=1)
        ],
    }


def test_the_failed_attempts_of_a_result_come_back_stamped_with_its_run() -> None:
    got = seeded(_result(_record(attempt=1), None, _record(attempt=3)), contract="impl")

    assert [(r.rung, r.attempt) for r in got] == [("local_a", 1), ("local_a", 3)]
    assert all(isinstance(r, CarriedNotes) for r in got)
    assert {r.run for r in got} == {"20261023T101010.000000Z"}


def test_a_seeded_record_is_named_as_an_earlier_runs_never_as_this_ones() -> None:
    (record,) = seeded(_result(_record()), contract="impl")

    section = render_notes((record,))
    assert section is not None
    assert section.startswith(
        "IN AN EARLIER RUN (20261023T101010.000000Z), NOT THIS ONE: "
        "ATTEMPT 1 ON local_a WAS REJECTED BY THE GATE"
    )
    assert record.summary.startswith("earlier run 20261023T101010.000000Z: local_a #1")
    # The record itself is the schema's: the run travels beside it, not in it.
    assert "run" not in record.as_json()
    assert record.carried_json() == {
        "run": "20261023T101010.000000Z",
        "notes": record.as_json(),
    }


def test_a_result_of_another_contract_is_refused_by_name() -> None:
    with pytest.raises(NotesError, match=r"contract 'other'.*not 'impl'"):
        seeded(_result(_record(), contract="other"), contract="impl")


def test_records_an_earlier_seed_carried_come_first_with_their_own_run() -> None:
    earlier = CarriedNotes.of(FailureNotes.from_json(_record(rung="api_x")), "R0")
    result = _result(_record())
    result["seeded"] = {"handed": 1, "records": [earlier.carried_json()]}

    got = seeded(result, contract="impl")

    assert [(r.run, r.rung) for r in got] == [
        ("R0", "api_x"),
        ("20261023T101010.000000Z", "local_a"),
    ]


def test_a_bare_list_of_records_is_read_with_no_run_named() -> None:
    (record,) = seeded([_record()], contract="impl")

    assert record.run == ""
    assert record.headline.startswith("IN AN EARLIER RUN, NOT THIS ONE: ATTEMPT 1")


def test_no_more_records_are_kept_than_a_prompt_shows() -> None:
    many = [_record(attempt=n) for n in range(1, MAX_RECORDS_SHOWN + 4)]

    got = seeded(many, contract="impl")

    assert len(got) == MAX_RECORDS_SHOWN
    assert got[-1].attempt == MAX_RECORDS_SHOWN + 3


@pytest.mark.parametrize(
    ("record", "refused"),
    [
        ({**_record(), "schema": "mcgyvr.failure_notes/2"}, "failure_notes/2"),
        ({**_record(), "attempt": 0}, "below 1"),
        ({**_record(), "extra": 1}, "extra"),
        (_record(path="/abs/repo/src/x.py"), "absolute"),
        (_record(path="~/repo/src/x.py"), "absolute"),
        (_record(path="src/../../etc/passwd"), "outside the repository"),
        (_record(path=""), "empty"),
    ],
)
def test_an_unsound_record_is_refused(record: dict[str, Any], refused: str) -> None:
    with pytest.raises(NotesError, match=refused):
        seeded(_result(record), contract="impl")


def test_a_secret_in_a_seeded_message_is_scrubbed() -> None:
    record = _record(
        message="push to https://bob:hunter2@git.example/x failed",
        command="git push https://bob:hunter2@git.example/x",
    )
    (got,) = seeded(_result(record), contract="impl")

    assert "hunter2" not in got.notes[0].message
    assert "hunter2" not in (got.notes[0].command or "")


def test_an_unreadable_file_is_a_clear_error_not_a_crash(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    with pytest.raises(NotesError, match="cannot be read"):
        seeded(missing, contract="impl")

    garbled = tmp_path / "garbled.json"
    garbled.write_text("{not json", encoding="utf-8")
    with pytest.raises(NotesError, match="not JSON"):
        seeded(garbled, contract="impl")

    huge = tmp_path / "huge.json"
    huge.write_text(" " * (MAX_SEED_BYTES + 1), encoding="utf-8")
    with pytest.raises(NotesError, match="larger than"):
        seeded(huge, contract="impl")

    scalar = tmp_path / "scalar.json"
    scalar.write_text("3", encoding="utf-8")
    with pytest.raises(NotesError, match="neither a result nor a list"):
        seeded(scalar, contract="impl")


def test_a_result_file_on_disk_is_read_like_its_json(tmp_path: Path) -> None:
    path = tmp_path / "impl-20261023T101010.000000Z.json"
    path.write_text(json.dumps(_result(_record())), encoding="utf-8")

    assert seeded(path, contract="impl") == seeded(_result(_record()), contract="impl")


def test_only_retry_notes_climb_primes_the_climb_with_a_seed() -> None:
    seed = seeded(_result(_record()), contract="impl")

    assert primed(seed, "climb") == list(seed)
    assert primed(seed, "rung") == []
    assert primed(seed, "none") == []
    with pytest.raises(ValueError, match="retry_notes"):
        primed(seed, "all")
