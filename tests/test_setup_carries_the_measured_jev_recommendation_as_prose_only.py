"""SETUP.md cites the measured Jev recommendation as prose, and nowhere else.

Owner ruling, 2026-10-04: the default Jev model is Qwen3.5-4B — "docs + lab
record only, attached to the run results; prose, for now". Approved by the owner
on 2026-10-20: the product ships only what describes its code, so the figures stay
in the lab record and SETUP.md's `jev` section, after its key table, cites that
record in one line. The recommendation is not a schema field, not a default
the loader fills, not a row of the capability table, and it does not reach the
config reference or the /mcgyvr skill, which are rendered from the schema
alone.
"""

from __future__ import annotations

from mcgyvr import config, docgen

MODEL = "Qwen3.5-4B"
EVIDENCE = "records/evidence/2026-10-04-jev-mcorch"


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    end = text.find("\n## ", start + len(heading))
    return text[start : end if end != -1 else len(text)]


def test_the_jev_section_of_setup_cites_the_lab_record_of_the_measured_model() -> None:
    setup = docgen.render_setup()
    jev = _section(setup, "## `jev`")
    table_end = jev.index("| `jev.model` |")
    note = jev[table_end:]
    assert EVIDENCE in note
    assert setup.count(EVIDENCE) == 1  # cited once, under the key it advises
    assert MODEL not in setup  # the figures are the lab record's, not the doc's


def test_the_recommendation_is_prose_not_schema() -> None:
    jev = next(field for field in config.SCHEMA if field.name == "jev")
    assert MODEL not in jev.doc
    for inner in jev.block:
        assert MODEL not in inner.doc
        assert inner.default is None  # no default follows from the ruling
    assert MODEL not in docgen.render_reference()
    assert MODEL not in docgen.render_skill()
