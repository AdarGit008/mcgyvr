"""Structured-data validation and pre-flight: the cheap checks that save spend.

Structured-data findings must behave like any gate finding; pre-flight issues
must behave like the opposite — orchestration errors that never touch the
worker's ledger and, for the dirty-tree case, never touch the tree.
"""

from __future__ import annotations

import math
import subprocess
from pathlib import Path

import pytest

from mcgyvr.gate.changeset import ChangeSet, FileChange
from mcgyvr.gate.preflight import (
    ESTIMATE_RESERVE,
    PreflightIssue,
    TokenCount,
    check_clean_tree,
    check_prompt_fits,
)
from mcgyvr.gate.structured import validate_structured_data


def one_file(repo: Path, path: str, text: str) -> ChangeSet:
    dest = repo / path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    added = frozenset(range(1, len(text.split("\n")) + 1))
    change = FileChange(path=path, status="A", added_lines=added, is_binary=False)
    return ChangeSet(repo=repo, base="HEAD", files=(change,))


# --- structured data -------------------------------------------------------


def test_valid_json_passes(tmp_path: Path) -> None:
    cs = one_file(tmp_path, "config.json", '{"a": 1, "b": [2, 3]}\n')
    assert validate_structured_data(cs) == []


def test_invalid_json_is_flagged_with_a_line(tmp_path: Path) -> None:
    cs = one_file(tmp_path, "config.json", '{\n  "a": 1,\n  "b": ,\n}\n')
    findings = validate_structured_data(cs)
    assert len(findings) == 1
    assert findings[0].code == "invalid-json"
    assert findings[0].line is not None


def test_non_structured_files_are_ignored(tmp_path: Path) -> None:
    cs = one_file(tmp_path, "app.py", "def f(: this is not valid python\n")
    assert validate_structured_data(cs) == []


def test_binary_and_deleted_are_skipped(tmp_path: Path) -> None:
    changes = (
        FileChange("a.json", "D", frozenset(), False),
        FileChange("b.json", "M", frozenset({1}), True),
    )
    cs = ChangeSet(repo=tmp_path, base="HEAD", files=changes)
    assert validate_structured_data(cs) == []


def test_yaml_validation_when_parser_present(tmp_path: Path) -> None:
    yaml = pytest.importorskip("yaml")
    assert yaml is not None
    cs = one_file(tmp_path, "c.yaml", "a: 1\n b: 2\n  bad: indent\n")
    findings = validate_structured_data(cs)
    assert [f.code for f in findings] == ["invalid-yaml"]


# --- pre-flight ------------------------------------------------------------


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t.io", "-c", "user.name=t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def test_clean_tree_passes(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "f.py").write_text("x = 1\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    assert check_clean_tree(tmp_path) is None


def test_dirty_tree_is_reported_and_not_destroyed(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "f.py").write_text("x = 1\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    (tmp_path / "f.py").write_text("x = 999  # uncommitted local work\n")

    issue = check_clean_tree(tmp_path)
    assert isinstance(issue, PreflightIssue)
    assert issue.reason == "dirty-tree"
    assert "f.py" in issue.message
    # The user's uncommitted work must still be exactly where it was.
    assert (tmp_path / "f.py").read_text() == "x = 999  # uncommitted local work\n"


def test_untracked_file_makes_the_tree_dirty(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "seed.py").write_text("x = 1\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    (tmp_path / "stray.txt").write_text("left behind\n")

    issue = check_clean_tree(tmp_path)
    assert issue is not None and issue.reason == "dirty-tree"
    assert "stray.txt" in issue.message


def test_prompt_that_fits_passes() -> None:
    assert check_prompt_fits(1000, context_window=8192) is None
    # 4000 estimated against a 4192 budget used to pass. It no longer does: the
    # same text could really be 5280 tokens, which CLM-0011 measured rather than
    # supposed, and admitting it is how a prompt reaches a backend that refuses
    # it. Counted exactly, the same numbers still fit.
    assert check_prompt_fits(3000, context_window=8192, output_reserve=4000) is None
    assert (
        check_prompt_fits(
            4000,
            context_window=8192,
            output_reserve=4000,
            counted_by=TokenCount.TOKENIZER,
        )
        is None
    )


def test_prompt_too_large_is_rejected_before_spend() -> None:
    issue = check_prompt_fits(9000, context_window=8192)
    assert issue is not None and issue.reason == "prompt-too-large"


def test_output_reserve_counts_against_the_budget() -> None:
    # 5000 prompt + 4000 reserve = 9000 > 8192 window.
    issue = check_prompt_fits(5000, context_window=8192, output_reserve=4000)
    assert issue is not None and issue.reason == "prompt-too-large"


# --- #117: the check says which count it enforced with -----------------------


def test_an_estimated_count_is_charged_the_measured_reserve() -> None:
    """The reserve is the measured band, not a constant nobody can source."""
    window = 10_000
    # Just inside the window on its face; over it once the estimator's own
    # error is reserved against.
    estimated = 8000
    assert estimated < window
    assert math.ceil(estimated * (1 + ESTIMATE_RESERVE)) > window

    issue = check_prompt_fits(estimated, context_window=window)
    assert issue is not None and issue.reason == "prompt-too-large"


def test_a_rejection_is_attributable_to_the_proxy_or_to_the_prompt() -> None:
    """Which count was enforced with is the difference between two diagnoses."""
    estimated = check_prompt_fits(9000, context_window=8192)
    exact = check_prompt_fits(
        9000, context_window=8192, counted_by=TokenCount.TOKENIZER
    )

    assert estimated is not None and exact is not None
    assert "estimated tokens" in estimated.message
    assert "CLM-0011" in estimated.message
    assert "counted exactly" in exact.message
    assert "CLM-0011" not in exact.message


def test_an_exact_count_reserves_nothing() -> None:
    """A real tokenizer needs no protection against the proxy's error."""
    window = 10_000
    assert check_prompt_fits(9500, window, counted_by=TokenCount.TOKENIZER) is None
    assert check_prompt_fits(9500, window) is not None


def test_the_reserve_is_the_measured_undercount_not_a_round_number() -> None:
    """A margin that drifted to a tidy 0.25 or 0.5 would have stopped being measured."""
    assert 0.30 <= ESTIMATE_RESERVE <= 0.35
    assert ESTIMATE_RESERVE not in (0.25, 0.5)


def test_preflight_issue_is_not_a_finding() -> None:
    """An orchestration error must be a distinct type from a worker finding."""
    from mcgyvr.gate.findings import Finding

    issue = check_prompt_fits(9000, 8192)
    assert not isinstance(issue, Finding)
