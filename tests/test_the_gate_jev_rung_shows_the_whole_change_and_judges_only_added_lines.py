"""The gate's Jev rung shows the whole change and judges only the added lines.

Owner ruling after the pilot: with added lines alone the rung scored AUROC
0.44-0.65 across 1.5B-14B, while the reviewer's verdict — shown the original
file and the change (:func:`mcgyvr.verify.verdict_state`) — scored 0.73-0.75.
So the state a question is asked over now carries ``original`` (the file at
the change's base, empty where there was none) and ``change`` (the file as
the worker left it) beside ``added_lines``. What is judged has not moved: a
finding is attributed to an added line, and a pre-existing line is never one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcgyvr.decision import BoolAnswer, Decision, ScoreAnswer
from mcgyvr.gate.changeset import ChangeSet, FileChange
from mcgyvr.gate.jev import JevCheck, build_state
from tests.livejournal import git

BEFORE = "a = 1\nb = 2\n"
AFTER = "a = 1\nimport os\nb = 2\n"


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "m.py").write_text(BEFORE, encoding="utf-8")
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    (root / "m.py").write_text(AFTER, encoding="utf-8")
    return root


def test_the_state_carries_the_original_the_change_and_the_added_lines(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    changeset = ChangeSet.detect(root)
    (change,) = changeset.files
    state = build_state(changeset, change, "Import os.")
    assert state["original"] == BEFORE
    assert state["change"] == AFTER
    assert state["added_lines"] == [{"line": 2, "text": "import os"}]
    assert state["task"] == "Import os."
    assert state["path"] == "m.py"


def test_a_file_with_no_base_version_has_an_empty_original(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "new.py").write_text("x = 1\n", encoding="utf-8")
    changeset = ChangeSet.detect(root)
    new = next(change for change in changeset.files if change.path == "new.py")
    state = build_state(changeset, new, "Add x.")
    assert state["original"] == ""
    assert state["change"] == "x = 1\n"


def test_a_change_set_outside_git_still_builds_its_state(tmp_path: Path) -> None:
    (tmp_path / "f.py").write_text("y = 2\n", encoding="utf-8")
    changeset = ChangeSet(
        repo=tmp_path,
        base="HEAD",
        files=(
            FileChange(
                path="f.py", status="A", added_lines=frozenset({1}), is_binary=False
            ),
        ),
    )
    state = build_state(changeset, changeset.files[0], "Add y.")
    assert state["original"] == ""
    assert state["change"] == "y = 2\n"


def test_a_finding_is_attributed_to_an_added_line_never_a_pre_existing_one(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    changeset = ChangeSet.detect(root)

    def no(state: Any) -> Decision:
        assert "original" in state and "change" in state
        return Decision(
            answers={
                "satisfies_task": BoolAnswer(
                    value=False, probability_true=0.1, confidence=0.8
                ),
                "in_scope": BoolAnswer(
                    value=True, probability_true=0.9, confidence=0.8
                ),
                "regression_risk": ScoreAnswer(
                    level=0.0,
                    probabilities={"low": 0.9, "medium": 0.1, "high": 0.0},
                    confidence=0.8,
                ),
            }
        )

    report = JevCheck(decide=no).run(changeset, "Import os.")
    (finding,) = report.observations
    assert finding.path == "m.py"
    assert finding.line == 2  # the added line, not line 1 or 3 of the original
