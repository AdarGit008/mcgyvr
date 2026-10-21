"""The per-field instruction rendering and its constraints slot (W6).

`instructions` renders the CONSTRAINTS section that W6's retry loop fills; W3
left it empty. When no constraints are given the rendered text must stay
byte-identical to what W3 shipped, and a non-empty directive must land under
the CONSTRAINTS heading in place of the blank line.
"""

from __future__ import annotations

from mcgyvr.orchestrator.candidates import CandidateSet, FieldCandidate
from mcgyvr.orchestrator.fields import instructions, render_choice


def test_instructions_without_constraints_are_unchanged() -> None:
    """The empty-constraints output is the exact W3 text."""
    assert instructions("target", "Which file?", abstain_line="") == (
        "FIELD target: Which file?\n"
        "\n"
        "CONSTRAINTS (ignore this section if empty):\n"
        "\n"
        "Pick the candidate that best satisfies the criterion above."
    )


def test_instructions_render_constraints_under_the_heading() -> None:
    """A non-empty directive replaces the blank line after the heading."""
    assert instructions(
        "target", "Which file?", constraints="only a path the index holds"
    ) == (
        "FIELD target: Which file?\n"
        "\n"
        "CONSTRAINTS (ignore this section if empty):\n"
        "only a path the index holds\n"
        "Pick the candidate that best satisfies the criterion above."
    )


def test_instructions_keep_the_abstain_line_below_the_prompt() -> None:
    """Constraints and the abstain instruction both render, in order."""
    rendered = instructions(
        "symbol",
        "Which symbol?",
        abstain_line="Choose the no-symbol option when the whole file is the work.",
        constraints="keep the same symbol",
    )
    assert rendered.endswith(
        "Pick the candidate that best satisfies the criterion above.\n"
        "Choose the no-symbol option when the whole file is the work."
    )
    assert "keep the same symbol" in rendered


def test_render_choice_passes_constraints_through() -> None:
    """`render_choice` threads its new `constraints` into `instructions`."""
    set_ = CandidateSet(
        field="target",
        candidates=(FieldCandidate(id="target:0", value="listing.py", rank=0),),
    )
    choice = render_choice(
        set_,
        criterion="Which file?",
        abstain_line="",
        constraints="only a path the index holds",
    )
    assert "only a path the index holds" in choice.instructions
