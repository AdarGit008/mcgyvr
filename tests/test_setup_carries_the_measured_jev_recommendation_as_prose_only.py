"""SETUP.md carries the measured Jev recommendation as prose, and nowhere else.

Owner ruling, 2026-10-04: the default Jev model is Qwen3.5-4B — "docs + lab
record only, attached to the run results; prose, for now". So the
recommendation is a paragraph under SETUP.md's `jev` section, after its key
table, citing the run it comes from. It is not a schema field, not a default
the loader fills, not a row of the capability table, and it does not reach the
config reference or the /mcgyvr skill, which are rendered from the schema
alone.
"""

from __future__ import annotations

from mcgyvr import config, docgen

MODEL = "Qwen3.5-4B"
EVIDENCE = "2026-10-04-jev-mcorch"


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    end = text.find("\n## ", start + len(heading))
    return text[start : end if end != -1 else len(text)]


def test_the_jev_section_of_setup_names_the_measured_model_and_its_evidence() -> None:
    setup = docgen.render_setup()
    jev = _section(setup, "## `jev`")
    table_end = jev.index("| `jev.model` |")
    note = jev[table_end:]
    assert MODEL in note
    assert EVIDENCE in note
    assert "Qwen3.5-9B" in note  # the higher-scoring option on judging code
    assert setup.count(MODEL) == 1  # said once, under the key it advises


def test_the_recommendation_is_prose_not_schema() -> None:
    jev = next(field for field in config.SCHEMA if field.name == "jev")
    assert MODEL not in jev.doc
    for inner in jev.block:
        assert MODEL not in inner.doc
        assert inner.default is None  # no default follows from the ruling
    assert MODEL not in docgen.render_reference()
    assert MODEL not in docgen.render_skill()
