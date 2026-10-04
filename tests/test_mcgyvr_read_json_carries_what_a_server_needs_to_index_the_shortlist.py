"""`mcgyvr read --json` carries what a server needs to index the shortlist itself.

mcorch holds no path to the user's repository; evidence rides the harness. The
rung has the harness run `mcgyvr read "<request>" --json` in the working
directory, and the tool result is this document: the request, the resolver's
shortlist, the regions read, and — the part a server cannot get any other way
— the whole text of every shortlisted and read file, so the server can build
the same index the command built and run the deterministic decomposer over it.
stdout is the document and nothing else, so a reader parses it whole.
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
    (root / "pkg" / "other.py").write_text("x = 1\n", encoding="utf-8")
    (root / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    lj.git(root, "init", "-q")
    lj.git(root, "add", "-A")
    lj.git(root, "commit", "-q", "-m", "seed")
    return root


def test_the_document_holds_the_shortlist_the_reads_and_every_files_text(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    code = lj.main(["read", "document paginate", str(root), "--json"])
    assert code == 0
    out = capsys.readouterr().out
    document = json.loads(out)  # the whole of stdout is one JSON object
    assert document["prompt"] == "document paginate"
    assert document["root"] == str(root)
    assert document["resolution"]["verdict"] in ("resolved", "ambiguous")
    candidates = [c["path"] for c in document["resolution"]["candidates"]]
    assert "pkg/listing.py" in candidates
    assert all(
        {"path", "score", "evidence"} <= set(c)
        for c in document["resolution"]["candidates"]
    )
    reads = document["reads"]
    assert reads and {"path", "start", "end", "reason", "text"} <= set(reads[0])
    files = {entry["path"]: entry["text"] for entry in document["files"]}
    assert files["pkg/listing.py"].startswith("def paginate")
    for path in candidates + [read["path"] for read in reads]:
        assert path in files


def test_the_text_form_is_unchanged_without_the_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    assert lj.main(["read", "document paginate", str(root)]) == 0
    out = capsys.readouterr().out
    assert out.startswith('"document paginate" — read')
    with pytest.raises(ValueError):
        json.loads(out)
