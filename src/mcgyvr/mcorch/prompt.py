""

from __future__ import annotations

from importlib import resources

from mcgyvr import contract
from mcgyvr.docgen import _contract_section, _contract_table
from mcgyvr.worker.bundle import strip_provenance

#
NOTES_SLOT = "{jev_notes}"
#
VOCABULARY_SLOT = "{vocabulary}"
#
_WRITER_SLOT = "{writer}"
_AUTHORING_SLOT = "{authoring}"

_FILENAME = "mcorch.md"


def source() -> str:
    ""
    resource = resources.files("mcgyvr") / "prompts" / _FILENAME
    return resource.read_text(encoding="utf-8")


def vocabulary() -> str:
    ""
    lines = _contract_table(contract.SCHEMA, "")
    for field in contract.SCHEMA:
        if field.block:
            lines += _contract_section(field, field.name)
    return "\n".join(lines).rstrip("\n")


def render(*, writer: str, authoring: str) -> str:
    ""
    text = strip_provenance(source())
    return (
        text.replace(_WRITER_SLOT, writer)
        .replace(_AUTHORING_SLOT, authoring)
        .replace(VOCABULARY_SLOT, vocabulary())
    )
