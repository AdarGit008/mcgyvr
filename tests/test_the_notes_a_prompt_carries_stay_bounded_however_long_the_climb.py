"""The failure notes a prompt carries are bounded, however long the climb.

A climb hands every record on, so a prompt would otherwise grow with every
failed attempt. :func:`mcgyvr.worker.prompt.render_notes` renders the latest
record in full up to :data:`~mcgyvr.worker.prompt.MAX_NOTES_SHOWN` notes and
the records before it one line each, at most
:data:`~mcgyvr.worker.prompt.MAX_RECORDS_SHOWN` in all. Asserted on the prompt
`build_prompt` assembles, the one a worker is sent.
"""

from __future__ import annotations

from mcgyvr.contract import loads as load_contract
from mcgyvr.notes import FailureNote, FailureNotes, NoteKind
from mcgyvr.worker.prompt import MAX_NOTES_SHOWN, MAX_RECORDS_SHOWN, build_prompt

CONTRACT = """
id: impl
task_type: code
task: Set VALUE to 1.
target: src/pkg/messy.py
stop_conditions: ["The value is not stated."]
acceptance: ["python -c 'import sys; sys.exit(0)'"]
limits:
  max_output_tokens: 256
scope:
  allow: ["src/**"]
"""


def _record(attempt: int, notes: int = 30) -> FailureNotes:
    return FailureNotes(
        rung="local_a",
        family="local",
        attempt=attempt,
        checks=("lint",),
        notes=tuple(
            FailureNote(
                check="lint",
                kind=NoteKind.FINDING,
                message=f"note {n} of attempt {attempt}",
                path="src/pkg/messy.py",
                line=n + 1,
                code="E501",
            )
            for n in range(notes)
        ),
    )


def _user(records: int) -> str:
    climb = tuple(_record(n) for n in range(1, records + 1))
    return build_prompt(load_contract(CONTRACT), retry=climb).user


def test_the_latest_record_shows_at_most_its_bound_and_counts_the_rest() -> None:
    user = _user(1)

    assert "note 19 of attempt 1" in user
    assert f"note {MAX_NOTES_SHOWN} of attempt 1" not in user
    assert f"- +{30 - MAX_NOTES_SHOWN} more" in user


def test_earlier_records_are_one_line_each_and_only_the_last_few() -> None:
    records = 12
    user = _user(records)

    assert "ATTEMPT 12 ON local_a WAS REJECTED BY THE GATE" in user
    earlier = [line for line in user.splitlines() if line.startswith("earlier: ")]
    shown = [f"earlier: local_a #{n} — lint (30)" for n in range(8, 12)]
    assert earlier == [
        f"earlier: {records - MAX_RECORDS_SHOWN} attempt(s) not shown",
        *shown,
    ]
    for hidden in range(1, 12):
        assert f"of attempt {hidden}\n" not in user, (
            "an earlier record was rendered whole"
        )


def test_the_prompt_stops_growing_once_the_bounds_are_reached() -> None:
    """Six records and fifty make prompts of one size, give or take their numbers.

    The difference left is the digits: attempt numbers in the banner, the
    shown notes and the earlier lines, and the count of records not shown.
    """
    at_bound = len(_user(MAX_RECORDS_SHOWN + 1))
    far_past = len(_user(50))

    assert far_past - at_bound < 64, (at_bound, far_past)
    assert len(_user(MAX_RECORDS_SHOWN)) < at_bound
