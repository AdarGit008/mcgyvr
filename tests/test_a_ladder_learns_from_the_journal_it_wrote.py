"""A ladder learns from the journal it wrote.

The journal now says, per attempt, which rung answered, what kind of work it
was and how it landed. What nothing does yet is read that back: a task type a
cheap rung fails every time still starts on that rung, and every run pays the
failed attempt before climbing. The compounding the live journal exists for is
this step — routing on what was measured here (ADR-0028), not on a guess.

The shape the owner decided on (2026-09-03, #406): a proposer over the folded
journal that, given a config, says which task types should start one rung up
because the rung the catalog starts them on has been failing them. This test
is that claim, red until #406 lands: a journal where the cheap rung passed
every ``bug_fix`` and failed every ``function_implementation`` yields exactly
one proposal, for ``function_implementation``, and none for the type that
passes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.telemetry import correct, observe


def _dispatch(
    journal: Path, *, contract: str, task_type: str, rung: str, landed: str
) -> None:
    attempt_id = f"agent:{contract}:{rung}:1"
    observe(
        lambda: "reply",
        path=journal / "agent.jsonl",
        attempt_id=attempt_id,
        orchestrator="agent",
        rung=rung,
        task_type=task_type,
    )
    correct(
        path=journal / "agent.jsonl",
        attempt_id=attempt_id,
        outcome=landed,
        orchestrator="agent",
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "2026-09-03: decided — the feedback loop is v2 (#406). Nothing reads "
        "the folded journal to move a floor: `mcgyvr.feedback.propose` does "
        "not exist, and the cheap rung starts every type the catalog starts "
        "there however often it has failed it."
    ),
)
def test_a_type_the_cheap_rung_keeps_failing_is_proposed_to_start_one_rung_up(
    tmp_path: Path,
) -> None:
    journal = tmp_path / "journal"
    journal.mkdir()
    for n in range(3):
        _dispatch(
            journal,
            contract=f"fix-{n}",
            task_type="bug_fix",
            rung="local_small",
            landed="committed",
        )
        _dispatch(
            journal,
            contract=f"impl-{n}",
            task_type="function_implementation",
            rung="local_small",
            landed="failed",
        )

    from mcgyvr.feedback import propose  # type: ignore[import-untyped]

    proposals = propose(journal)

    assert [(p.task_type, p.reason) for p in proposals] == [
        ("function_implementation", "local_small failed 3 of 3")
    ]
