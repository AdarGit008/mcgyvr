"""`mcgyvr read --json` carries the checker the repository declares, located on disk.

The command runs where the repository is, so it is the one place the
adapters' lookup — the same one :func:`decompose._acceptance_for` performs
for `mcgyvr delegate` — can read the repository's configuration. The document
carries the result under ``located``: adapter name → the command's argv,
exactly as located, for every adapter that located one; an adapter that found
none is absent, never filled in. A server assembling an index from the
document uses this in place of any read of its own.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests import livejournal as lj


def _repo(tmp_path: Path, *, mypy: bool) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "listing.py").write_text("def listing(items):\n    return items\n")
    if mypy:
        (root / "pyproject.toml").write_text('[tool.mypy]\nfiles = ["."]\n')
    lj.git(root, "init", "-q")
    lj.git(root, "add", "-A")
    lj.git(root, "commit", "-q", "-m", "seed")
    return root


def test_a_declared_checker_is_carried_as_the_adapters_argv(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path, mypy=True)
    assert lj.main(["read", "annotate listing", str(root), "--json"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["located"] == {"python": ["mypy"]}


def test_an_undeclared_checker_is_absent_never_guessed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path, mypy=False)
    assert lj.main(["read", "annotate listing", str(root), "--json"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["located"] == {}
