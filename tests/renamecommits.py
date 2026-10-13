"""A rename delivered as one commit."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests import livejournal as lj

CONTRACT = """
id: rename-fetch
task_type: code
operation: rename_symbol
task: Rename fetch_page to fetch_document.
target: src/pkg/web.py
rename:
  from: fetch_page
  to: fetch_document
scope:
  allow: {allow}
"""


TREE = {
    "src/pkg/__init__.py": "",
    "src/pkg/web.py": "def fetch_page(url):\n    return url\n",
    "src/pkg/use.py": (
        "from pkg.web import fetch_page\n\n\ndef go():\n    return fetch_page(1)\n"
    ),
}


def _repo(root: Path) -> Path:
    lj.make_repo(root)
    for path, text in TREE.items():
        (root / path).write_text(text, encoding="utf-8")
    lj.git(root, "add", "-A")
    lj.git(root, "commit", "-q", "-m", "a symbol and a caller")
    return root


def _run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *extra: str,
    allow: str = '["src/pkg/**"]',
    before: dict[str, str] | None = None,
) -> tuple[Path, Path, int]:
    lj.scripted(monkeypatch)  # nothing scripted: the floor dispatches nothing
    repo = _repo(tmp_path / "repo")
    for path, text in (before or {}).items():
        (repo / path).write_text(text, encoding="utf-8")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "setup", journal_dir=journal)
    contract = lj.make_contract(tmp_path / "rename.yaml", CONTRACT.format(allow=allow))
    code = lj.main(lj.run_args(contract, repo, config, *extra))
    return repo, journal, code
