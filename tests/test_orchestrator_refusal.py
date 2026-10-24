"""The machine-actionable half of a refusal.

W4 gives every `Refusal` a `{field, what_to_change}` pair beside its human
`{subject, reason}`: `field` names the proposal field to change (empty when the
request as a whole is at fault), and `what_to_change` is the directive a retry
loop can act on. These tests trigger each mapped refusal site and hold it to
the table, while leaving the human half — `str`, `.subject`, `.reason` and
`Decomposition.explain()` — untouched.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.orchestrator.decompose import (
    Decomposition,
    DepRef,
    Proposal,
    RecordedProposer,
    Refusal,
    decompose,
)
from mcgyvr.orchestrator.index import Index, build_index
from tests.decomposes import an_annotation, git


@pytest.fixture
def repo(tmp_path: Path) -> Index:
    """A repository with a Python target, a dependency, and an unowned target."""
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "pagination.py").write_text(
        "def paginate(items: list[int], size: int = 10) -> list[int]:\n"
        '    """Split into pages."""\n'
        "    return items[:size]\n"
    )
    (root / "listing.py").write_text(
        "from pagination import paginate\n\n\ndef listing(items):\n    return items\n"
    )
    (root / "notes.md").write_text("# notes\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "seed")
    return build_index(root)


def a_fix(**overrides: object) -> Proposal:
    """A well-formed `code` proposal, mirroring ``test_orchestrator_decompose``."""
    base = {
        "task_type": "code",
        "task": "listing() ignores the page size; page the items before returning.",
        "target": "listing.py",
        "interface": "listing(items, size=10) -> list",
        "deps": (DepRef("pagination.py", "paginate", "page the items with this"),),
        "stop_conditions": ("the pager's contract is ambiguous",),
        "acceptance": ("pytest -q",),
        "demonstration": ("pytest -q tests/test_listing.py::test_page_size",),
    }
    return Proposal(**{**base, **overrides})  # type: ignore[arg-type]


def one_refusal(result: Decomposition) -> Refusal:
    """The single refusal a decomposition produced."""
    assert result.contracts == ()
    (refusal,) = result.refusals
    return refusal


def test_a_refusal_string_is_subject_colon_reason(repo: Index) -> None:
    refusal = one_refusal(
        decompose(
            repo,
            "fix",
            propose=RecordedProposer((a_fix(target="nowhere.py", deps=()),)),
        )
    )

    assert str(refusal) == f"{refusal.subject}: {refusal.reason}"


def test_explain_keeps_subject_colon_reason_lines(repo: Index) -> None:
    result = decompose(
        repo,
        "fix",
        propose=RecordedProposer((a_fix(target="nowhere.py", deps=()),)),
    )
    (refusal,) = result.refusals

    assert f"{refusal.subject}: {refusal.reason}" in result.explain()


def test_a_clean_decomposition_has_no_refusals(repo: Index) -> None:
    result = decompose(repo, "fix", propose=RecordedProposer((a_fix(),)))

    assert result.contracts
    assert result.refusals == ()


# --- the mapped sites, each held to the field/what_to_change table ----------


def test_nothing_proposed_names_the_request_and_the_way_forward(repo: Index) -> None:
    refusal = one_refusal(
        decompose(repo, "make it better somehow", propose=RecordedProposer(()))
    )

    assert refusal.field == "request"
    assert refusal.what_to_change == (
        "name a target the index holds, or narrow the request to a servable type"
    )


def test_an_unservable_type_points_at_the_task_type(repo: Index) -> None:
    refusal = one_refusal(
        decompose(
            repo,
            "do it",
            propose=RecordedProposer((a_fix(task_type="teleport", deps=()),)),
        )
    )

    assert refusal.field == "task_type"
    assert refusal.what_to_change == "pick a servable type"


def test_an_unindexed_target_points_at_the_target(repo: Index) -> None:
    refusal = one_refusal(
        decompose(
            repo,
            "fix",
            propose=RecordedProposer((a_fix(target="nowhere.py", deps=()),)),
        )
    )

    assert refusal.field == "target"
    assert refusal.what_to_change == (
        "name a path the index holds (check spelling, or index the repo that has it)"
    )


def test_an_unknown_dependency_points_at_deps(repo: Index) -> None:
    refusal = one_refusal(
        decompose(
            repo,
            "fix",
            propose=RecordedProposer(
                (a_fix(deps=(DepRef("pagination.py", "conjured_helper"),)),)
            ),
        )
    )

    assert refusal.field == "deps"
    assert refusal.what_to_change == (
        "omit that symbol from deps, or name a symbol the parser defines"
    )


def test_a_duplicate_points_at_the_task(repo: Index) -> None:
    result = decompose(repo, "fix", propose=RecordedProposer((a_fix(), a_fix())))

    assert len(result.contracts) == 1
    (refusal,) = result.refusals
    assert refusal.field == "task"
    assert refusal.what_to_change == (
        "make the directive distinct (same type+target+task is one unit twice)"
    )


def test_a_schema_error_re_wrap_carries_the_bad_key(repo: Index) -> None:
    refusal = one_refusal(
        decompose(
            repo,
            "fix",
            propose=RecordedProposer((a_fix(stop_conditions=()),)),
        )
    )

    assert refusal.field == ""
    assert refusal.what_to_change
    assert "stop_conditions" in refusal.what_to_change


def test_a_target_too_large_points_at_the_target(repo: Index) -> None:
    refusal = one_refusal(
        decompose(
            repo,
            "fix",
            propose=RecordedProposer((a_fix(),)),
            max_input_tokens=20,
        )
    )

    assert refusal.field == "target"
    assert refusal.what_to_change == (
        "narrow the target to a smaller file/region, or raise the ceiling"
    )


def test_an_unowned_target_points_at_the_target(repo: Index) -> None:
    refusal = one_refusal(
        decompose(
            repo,
            "annotate",
            propose=RecordedProposer((an_annotation(target="notes.md"),)),
        )
    )

    assert refusal.field == "target"
    assert refusal.what_to_change == (
        "retarget a file in a carried language, or state the acceptance command"
    )


def test_a_missing_checker_points_at_type_check(repo: Index) -> None:
    refusal = one_refusal(
        decompose(repo, "annotate", propose=RecordedProposer((an_annotation(),)))
    )

    assert refusal.field == "type_check"
    assert refusal.what_to_change == (
        "configure a checker in the repo, or drop type_check / state acceptance"
    )
