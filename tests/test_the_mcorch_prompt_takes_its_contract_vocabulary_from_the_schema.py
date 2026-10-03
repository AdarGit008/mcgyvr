"""The mcorch prompt takes its contract vocabulary from the schema, never by hand.

``prompts/mcorch.md`` says who the rung is and how it works — the loop, the
rule that every bounded question is Jev's, the harness tools it drives — and
leaves the contract vocabulary to be rendered from ``contract.SCHEMA`` the way
``skills/mcgyvr/SKILL.md`` is, so a key added to the schema reaches the rung
without anyone editing a prompt. The rendered prompt also names the writer id
the rung must pass as ``--orchestrator`` and the authoring strategy in force,
and holds the slot the loop fills with Jev's notes.
"""

from __future__ import annotations

from mcgyvr import contract
from mcgyvr.mcorch import prompt


def test_the_prompt_names_every_contract_key_from_the_schema() -> None:
    rendered = prompt.render(writer="mcorch-2026", authoring="direct")
    for field in contract.SCHEMA:
        assert f"`{field.name}`" in rendered, field.name


def test_the_prompt_carries_the_writer_the_strategy_and_the_notes_slot() -> None:
    rendered = prompt.render(writer="mcorch-2026", authoring="direct")
    assert "--orchestrator mcorch-2026" in rendered
    assert "direct" in rendered
    assert prompt.NOTES_SLOT in rendered
    assert "mcgyvr run" in rendered
    assert "mcgyvr contract" in rendered


def test_the_prompt_file_is_the_source_and_carries_no_hand_kept_table() -> None:
    source = prompt.source()
    assert "| Key |" not in source
    assert prompt.VOCABULARY_SLOT in source
    assert "Jev" in source


def test_the_prompt_explains_preflight_refusals_and_forbids_target_edits() -> None:
    """The pilot rung read a refusal as a broken tool and edited the target itself."""
    rendered = prompt.render(writer="mcorch-2026", authoring="direct")
    assert "acceptance-mutates-tree" in rendered
    assert "acceptance-baseline-failing" in rendered
    assert "demonstration" in rendered
    assert "__pycache__" in rendered
    assert "never edit" in rendered.lower() or "do not edit" in rendered.lower()
