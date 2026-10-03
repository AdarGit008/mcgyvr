"""The rung's system prompt: ``prompts/mcorch.md`` with the schema rendered in.

The prompt file says who the rung is and how a turn goes; it does not carry
the contract vocabulary, because a hand-kept key table is a second copy of
``contract.SCHEMA`` that drifts the moment a key is added. The vocabulary is
rendered here from the schema, the way ``skills/mcgyvr/SKILL.md`` is rendered
by :mod:`mcgyvr.docgen`, so the rung and the API-tier agent read one source.

The leading HTML-comment marker is provenance, stripped before the prompt is
sent (:func:`mcgyvr.worker.bundle.strip_provenance`): a note to a reader of the
repository, not instructions to a model.
"""

from __future__ import annotations

from importlib import resources

from mcgyvr import contract
from mcgyvr.docgen import _contract_section, _contract_table
from mcgyvr.worker.bundle import strip_provenance

#: The slot the loop fills with Jev's notes for this turn.
NOTES_SLOT = "{jev_notes}"
#: The slot the schema's key tables are rendered into.
VOCABULARY_SLOT = "{vocabulary}"
#: The slot the writer id and the authoring strategy fill.
_WRITER_SLOT = "{writer}"
_AUTHORING_SLOT = "{authoring}"

_FILENAME = "mcorch.md"


def source() -> str:
    """The prompt file as shipped, marker and slots included."""
    resource = resources.files("mcgyvr") / "prompts" / _FILENAME
    return resource.read_text(encoding="utf-8")


def vocabulary() -> str:
    """The contract schema as the key tables the skill renders."""
    lines = _contract_table(contract.SCHEMA, "")
    for field in contract.SCHEMA:
        if field.block:
            lines += _contract_section(field, field.name)
    return "\n".join(lines).rstrip("\n")


def render(*, writer: str, authoring: str) -> str:
    """The system prompt for one server: writer and strategy filled, notes slot kept.

    The notes slot stays a slot so the loop can fill it per turn without
    re-reading the file; :func:`with_notes` does that.
    """
    text = strip_provenance(source())
    return (
        text.replace(_WRITER_SLOT, writer)
        .replace(_AUTHORING_SLOT, authoring)
        .replace(VOCABULARY_SLOT, vocabulary())
    )


def with_notes(rendered: str, notes: str) -> str:
    """``rendered`` with this turn's Jev notes in their slot."""
    return rendered.replace(NOTES_SLOT, notes)
