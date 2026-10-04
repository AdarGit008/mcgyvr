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


def test_the_prompt_leaves_a_run_result_to_the_rung_with_no_jev_note_promised() -> None:
    """J3 is decommissioned (lab issue #61): the prompt must not tell the rung to
    wait for or obey a ``Jev:`` note about what comes after a result; the rung
    itself judges done / a different contract / ask the user from the result."""
    # Unwrapped, so a phrase the file breaks across lines still reads as one.
    rendered = " ".join(prompt.render(writer="mcorch-2026", authoring="direct").split())
    jev = rendered[rendered.index("## Jev") : rendered.index("## Replies")]
    assert "chat or work" in jev
    assert "ready to run" in jev
    assert "what to do after a result" not in rendered
    assert "yours to judge" in jev
    assert "no `Jev:` note" in jev
    assert "only the user" in rendered  # the ask-the-user branch is the rung's


def test_the_prompt_explains_preflight_refusals_and_forbids_target_edits() -> None:
    """The pilot rung read a refusal as a broken tool and edited the target itself."""
    rendered = prompt.render(writer="mcorch-2026", authoring="direct")
    assert "acceptance-mutates-tree" in rendered
    assert "acceptance-baseline-failing" in rendered
    assert "demonstration" in rendered
    assert "__pycache__" in rendered
    assert "never edit" in rendered.lower() or "do not edit" in rendered.lower()


def test_the_prompt_validates_then_fixes_before_it_runs_as_the_skill_does() -> None:
    """SKILL.md step 2: validate, fix what it names, never guess a field."""
    rendered = prompt.render(writer="mcorch-2026", authoring="direct")
    validate = rendered.index("mcgyvr contract ")
    run = rendered.index("mcgyvr run ")
    assert validate < run
    between = rendered[validate:run].lower()
    assert "fix" in between and "names" in between
