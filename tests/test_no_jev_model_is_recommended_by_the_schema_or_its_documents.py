"""No Jev model is recommended by the schema or by any document rendered from it.

Which model serves the `jev` unit is the user's choice: the measurements that
compare candidate models are the lab's, and the product ships only what
describes its code. So no model is a schema field's default, none is named in
a `jev` key's doc, and none reaches SETUP.md, the config reference or the
/mcgyvr skill. MODEL, the one an earlier SETUP.md recommended, is the probe.
"""

from __future__ import annotations

from mcgyvr import config, docgen

MODEL = "Qwen3.5-4B"


def test_the_jev_keys_name_no_model_and_default_to_none() -> None:
    jev = next(field for field in config.SCHEMA if field.name == "jev")
    assert MODEL not in jev.doc
    for inner in jev.block:
        assert MODEL not in inner.doc
        # `enabled` is the on/off switch, not a model, and is on by default.
        assert inner.default is (True if inner.name == "enabled" else None)


def test_no_rendered_document_names_a_jev_model() -> None:
    assert MODEL not in docgen.render_setup()
    assert MODEL not in docgen.render_reference()
    assert MODEL not in docgen.render_skill()


def test_the_jev_section_of_setup_ends_at_its_key_table() -> None:
    setup = docgen.render_setup()
    start = setup.index("## `jev`")
    end = setup.index("\n## ", start + 1)
    after = setup[setup.index("| `jev.model` |", start) : end]
    assert after.rstrip("\n").count("\n") == 0, after
