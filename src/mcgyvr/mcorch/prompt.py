"""Assemble the system prompt the mcorch rung runs on.

``prompts/mcorch.md`` ships inside the package and holds the hand-written
instructions plus slots. Rendering strips that file's provenance comment and
fills the slots: the writer id (the value the rung passes to ``mcgyvr run`` as
``--orchestrator``), the authoring strategy in force, and the contract
vocabulary, which is rebuilt from ``contract.SCHEMA`` with the same docgen
helpers that render ``SKILL.md`` so a key added to the schema reaches the rung
without anyone editing a prompt. The ``{jev_notes}`` slot is not filled here:
it survives rendering for the loop to fill.
"""

from __future__ import annotations

from importlib import resources

from mcgyvr import contract
from mcgyvr.docgen import _contract_section, _contract_table
from mcgyvr.worker.bundle import strip_provenance

#: Slot the loop fills with Jev's notes after rendering; render leaves it intact.
NOTES_SLOT = "{jev_notes}"
#: Slot render fills with the vocabulary table built from contract.SCHEMA.
VOCABULARY_SLOT = "{vocabulary}"
#: Slots render fills with the writer id and the authoring strategy in force.
_WRITER_SLOT = "{writer}"
_AUTHORING_SLOT = "{authoring}"

_FILENAME = "mcorch.md"


def source() -> str:
    """Return the packaged ``prompts/mcorch.md`` text as shipped, slots and
    provenance comment included."""
    resource = resources.files("mcgyvr") / "prompts" / _FILENAME
    return resource.read_text(encoding="utf-8")


def vocabulary() -> str:
    """Return the contract vocabulary as markdown: one table row per top-level
    ``contract.SCHEMA`` field, followed by a ``####`` section per block field
    restating its nested keys. Trailing blank lines are trimmed."""
    lines = _contract_table(contract.SCHEMA, "")
    for field in contract.SCHEMA:
        if field.block:
            lines += _contract_section(field, field.name)
    return "\n".join(lines).rstrip("\n")


def render(*, writer: str, authoring: str) -> str:
    """Return the source prompt with its provenance comment stripped and the
    writer, authoring and vocabulary slots replaced. ``NOTES_SLOT`` is left for
    the loop."""
    text = strip_provenance(source())
    return (
        text.replace(_WRITER_SLOT, writer)
        .replace(_AUTHORING_SLOT, authoring)
        .replace(VOCABULARY_SLOT, vocabulary())
    )
