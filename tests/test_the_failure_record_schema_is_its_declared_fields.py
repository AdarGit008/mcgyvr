"""The failure record's fields are declared once, and the rest is drawn from them.

:data:`mcgyvr.notes.NOTE_FIELDS` and :data:`~mcgyvr.notes.NOTES_FIELDS` are the
schema: the dataclasses hold exactly those fields in that order, the JSON a
record writes is walked from them, and :func:`~mcgyvr.notes.json_schema` —
committed as ``skills/mcgyvr-direct/references/failure-notes.schema.json`` by `make
docs` — is rendered from them and validates the records the gate builds.
"""

from __future__ import annotations

import dataclasses
import json

from mcgyvr import docgen
from mcgyvr.gate.findings import Finding
from mcgyvr.gate.runner import GateResult
from mcgyvr.notes import (
    NOTE_FIELDS,
    NOTES_FIELDS,
    FailureNote,
    FailureNotes,
    json_schema,
)
from tests.rig_schema import SchemaError, validate

RECORD = "#/$defs/FailureNotes"


def _record() -> FailureNotes:
    gate = GateResult(
        findings=(
            Finding(check="lint", path="a.py", line=1, code="F401", message="unused"),
            Finding(
                check="semantic",
                path="a.py",
                line=2,
                code="unresolved",
                message="`os.nope` does not resolve",
                symbol="nope",
            ),
        )
    )
    record = FailureNotes.of_gate(gate, rung="local_a", family="local", attempt=1)
    assert record is not None
    return record


def test_the_dataclasses_hold_exactly_the_declared_fields() -> None:
    assert [f.name for f in dataclasses.fields(FailureNote)] == [
        f.name for f in NOTE_FIELDS
    ]
    held = [f.name for f in dataclasses.fields(FailureNotes)]
    assert sorted(held) == sorted(f.name for f in NOTES_FIELDS)
    assert list(_record().as_json()) == [f.name for f in NOTES_FIELDS]


def test_the_generated_schema_validates_a_record_the_gate_built() -> None:
    schema = json_schema()

    validate(_record().as_json(), schema, RECORD)
    validate(
        FailureNotes.unreadable(
            "no fenced block", rung="r", family="api", attempt=3
        ).as_json(),
        schema,
        RECORD,
    )


def test_the_generated_schema_refuses_what_is_not_a_record() -> None:
    schema = json_schema()
    data = _record().as_json()

    for broken in (
        {**data, "schema": "mcgyvr.failure_notes/2"},
        {**data, "extra": True},
        {**data, "attempt": 0},
        {**data, "notes": [{**data["notes"][0], "kind": "guess"}]},
    ):
        try:
            validate(broken, schema, RECORD)
        except SchemaError:
            continue
        raise AssertionError(f"the schema accepted {broken}")


def test_the_committed_schema_is_what_the_fields_render() -> None:
    committed = docgen.REPO_ROOT / docgen.NOTES_SCHEMA_PATH
    assert committed.read_text(encoding="utf-8") == docgen.render_notes_schema()
    assert json.loads(committed.read_text(encoding="utf-8")) == json_schema()


def test_the_skill_documents_every_field() -> None:
    skill = docgen.render_direct_skill()
    for spec in (*NOTES_FIELDS, *NOTE_FIELDS):
        assert f"**`{spec.name}`**" in skill, spec.name
    assert "references/failure-notes.schema.json" in skill
