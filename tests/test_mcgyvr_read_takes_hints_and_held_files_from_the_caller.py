"""`mcgyvr read` takes hints and held files from the caller.

`--hint PATH` names a path the caller believes is relevant: it re-ranks the
shortlist, and its candidate's evidence says supplied context named it, but it
can never add to the shortlist, so a hint the index does not know is dropped and
one the deterministic pass did not shortlist changes nothing; both are reported
as `! path: detail` lines, and neither fails the command. `--holds PATH` names a
file whose current content the caller already holds: it is read from the
working tree and checked against the index, and when it matches, its regions
are marked supplied and cost the budget nothing (`N saved`). A held file that
cannot be read is an error, exit 1. Both flags repeat.

The repository is an invented one, built in the test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests import livejournal as lj


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "listing.py").write_text(
        "def paginate(items, size):\n    return items[:size]\n", encoding="utf-8"
    )
    (root / "pkg" / "paging.py").write_text(
        "def paginate_all(items):\n    return [items]\n", encoding="utf-8"
    )
    (root / "pkg" / "other.py").write_text("x = 1\n", encoding="utf-8")
    (root / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    lj.git(root, "init", "-q")
    lj.git(root, "add", "-A")
    lj.git(root, "commit", "-q", "-m", "seed")
    return root


def _read(root: Path, *flags: str) -> int:
    return lj.main(["read", "paginate", "--repo", str(root), *flags])


def test_a_hint_on_the_shortlist_is_named_in_its_candidates_evidence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    assert _read(root, "--hint", "pkg/paging.py", "--json") == 0
    document = json.loads(capsys.readouterr().out)
    evidence = {c["path"]: c["evidence"] for c in document["resolution"]["candidates"]}
    assert "supplied context names this path" in evidence["pkg/paging.py"]
    assert "supplied context names this path" not in evidence["pkg/listing.py"]


def test_a_hint_the_index_does_not_know_is_dropped_and_said(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    assert _read(root, "--hint", "pkg/nowhere.py") == 0
    out = capsys.readouterr().out
    assert "  ! pkg/nowhere.py: not present in the index — the hint was dropped" in out


def test_a_hint_the_shortlist_does_not_hold_adds_nothing_and_is_said(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    assert _read(root, "--hint", "pkg/other.py", "--json") == 0
    document = json.loads(capsys.readouterr().out)
    shortlisted = [c["path"] for c in document["resolution"]["candidates"]]
    assert "pkg/other.py" not in shortlisted, "a hint never adds to the shortlist"

    assert _read(root, "--hint", "pkg/other.py") == 0
    out = capsys.readouterr().out
    assert "  ! pkg/other.py: the deterministic pass did not shortlist this path" in out


def test_a_held_file_that_matches_costs_the_budget_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    assert _read(root) == 0
    plain = capsys.readouterr().out
    assert "(supplied)" not in plain and "saved" not in plain

    assert _read(root, "--holds", "pkg/listing.py", "--holds", "pkg/paging.py") == 0
    held = capsys.readouterr().out
    assert " saved (" in held.splitlines()[0]
    assert "pkg/listing.py" in held and "(supplied)" in held


def test_a_held_file_that_cannot_be_read_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    assert _read(root, "--holds", "pkg/nowhere.py") == 1
    assert "error: cannot read --holds pkg/nowhere.py" in capsys.readouterr().err
