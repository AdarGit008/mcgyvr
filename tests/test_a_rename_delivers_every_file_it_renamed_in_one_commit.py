"""``mcgyvr run`` on a ``rename_symbol`` delivers every file the rename changed.

e2e run 2, R3: the rename covered both files in the sandbox ("5 occurrence(s)
in 2 file(s)") and the gate accepted the whole change, then delivery wrote back
``contract.target`` alone. The user's ``use.py`` kept
``from pkg.web import fetch_page`` against a ``web.py`` that no longer defined
it — an ``ImportError`` — under a result that said ``accepted``,
``deterministic``, with no notes; ``--commit`` committed the one file.

Driven through the real entry point (:func:`mcgyvr.cli.main`), with nothing
scripted: the floor dispatches nothing.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests import livejournal as lj
from tests.renamecommits import TREE, _run

RENAMED = {
    "src/pkg/web.py": "def fetch_document(url):\n    return url\n",
    "src/pkg/use.py": (
        "from pkg.web import fetch_document\n\n\ndef go():\n"
        "    return fetch_document(1)\n"
    ),
}


def _result(stdout: str) -> dict[str, Any]:
    return dict(json.loads(lj.result_path(stdout).read_text()))


def _tree(repo: Path) -> dict[str, str]:
    return {path: (repo / path).read_text(encoding="utf-8") for path in RENAMED}


def _imports(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", "-c", "import pkg.use; print(pkg.use.go())"],
        cwd=repo,
        env={**os.environ, "PYTHONPATH": str(repo / "src")},
        capture_output=True,
        text=True,
    )


def test_without_commit_every_renamed_file_is_left_in_the_tree(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, _, code = _run(tmp_path, monkeypatch)
    head = lj.git(repo, "rev-parse", "HEAD").strip()

    out = capsys.readouterr().out
    result = _result(out)
    assert code == 0, out
    assert result["outcome"] == "accepted"
    assert _tree(repo) == RENAMED, "a renamed file was not delivered"
    imported = _imports(repo)
    assert imported.returncode == 0, imported.stderr
    assert lj.git(repo, "rev-parse", "HEAD").strip() == head, "a commit was made"
    assert "Left in src/pkg/web.py, src/pkg/use.py, not committed" in out
    assert result["delivery"] == (
        "not committed; change left in src/pkg/web.py, src/pkg/use.py"
    )


def test_commit_lands_every_renamed_file_in_one_commit(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, _, code = _run(tmp_path, monkeypatch, "--commit")

    out = capsys.readouterr().out
    result = _result(out)
    assert code == 0, out
    assert result["committed"] is True
    shipped = lj.git(repo, "show", "--name-only", "--format=", "HEAD").split()
    assert sorted(shipped) == ["src/pkg/use.py", "src/pkg/web.py"]
    assert lj.git(repo, "log", "-1", "--format=%s", "HEAD~1").strip() == (
        "a symbol and a caller"
    ), "the rename took more than one commit"
    assert lj.git(repo, "status", "--porcelain") == ""
    assert _tree(repo) == RENAMED
    imported = _imports(repo)
    assert imported.returncode == 0, imported.stderr


@pytest.mark.parametrize("commit", [False, True], ids=["left", "commit"])
def test_a_reference_outside_the_allowed_scope_refuses_and_writes_nothing(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    commit: bool,
) -> None:
    """``allow`` names the definition's file; the importer it must rename is out."""
    extra = ("--commit",) if commit else ()
    repo, _, code = _run(tmp_path, monkeypatch, *extra, allow='["src/pkg/web.py"]')
    head = lj.git(repo, "rev-parse", "HEAD").strip()

    out = capsys.readouterr().out
    result = _result(out)
    assert code == 1, out
    assert result["committed"] is False
    assert any("src/pkg/use.py" in finding for finding in result["findings"]), result
    assert _tree(repo) == {path: TREE[path] for path in RENAMED}
    assert lj.git(repo, "status", "--porcelain") == ""
    assert lj.git(repo, "rev-parse", "HEAD").strip() == head


@pytest.mark.parametrize("commit", [False, True], ids=["left", "commit"])
def test_an_uncommitted_edit_to_a_renamed_file_that_is_not_the_target_refuses(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    commit: bool,
) -> None:
    """The dirty-target refusal holds for every file the rename would write."""
    extra = ("--commit",) if commit else ()
    edited = TREE["src/pkg/use.py"] + "# a person's unfinished edit\n"
    repo, _, code = _run(
        tmp_path, monkeypatch, *extra, before={"src/pkg/use.py": edited}
    )
    head = lj.git(repo, "rev-parse", "HEAD").strip()

    out = capsys.readouterr().out
    result = _result(out)
    assert code == 1, out
    assert result["outcome"] == "delivery_refused"
    assert "src/pkg/use.py" in result["detail"]
    assert _tree(repo) == {
        "src/pkg/web.py": TREE["src/pkg/web.py"],
        "src/pkg/use.py": edited,
    }, "something was written over a person's edit, or beside it"
    assert lj.git(repo, "rev-parse", "HEAD").strip() == head


STORE = (
    "import json\n\n\ndef load(path):\n    with open(path) as f:\n"
    "        return json.load(f)\n"
)
APP = "from app.store import load\n\n\ndef main(path):\n    return load(path)\n"


def test_renaming_load_leaves_json_load_alone_and_the_tree_imports(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """e2e run 2, R3b: ``load`` -> ``load_json`` made ``json.load_json(f)``."""
    lj.scripted(monkeypatch)
    repo = lj.make_repo(tmp_path / "repo")
    (repo / "src/app").mkdir(parents=True)
    (repo / "src/app/__init__.py").write_text("", encoding="utf-8")
    (repo / "src/app/store.py").write_text(STORE, encoding="utf-8")
    (repo / "src/app/main.py").write_text(APP, encoding="utf-8")
    (repo / "data.json").write_text('{"ok": 1}\n', encoding="utf-8")
    lj.git(repo, "add", "-A")
    lj.git(repo, "commit", "-q", "-m", "a store")
    contract = lj.make_contract(
        tmp_path / "rename.yaml",
        "id: rename-load\ntask_type: code\noperation: rename_symbol\n"
        "task: Rename load to load_json.\ntarget: src/app/store.py\n"
        "rename:\n  from: load\n  to: load_json\n"
        'scope:\n  allow: ["src/app/**"]\n',
    )
    config = lj.make_config(tmp_path / "setup", journal_dir=tmp_path / "journal")

    code = lj.main(lj.run_args(contract, repo, config, "--commit"))

    out = capsys.readouterr().out
    assert code == 0, out
    store = (repo / "src/app/store.py").read_text(encoding="utf-8")
    assert "def load_json(path):" in store
    assert "return json.load(f)" in store, "an attribute of json was renamed"
    assert (repo / "src/app/main.py").read_text(encoding="utf-8") == APP.replace(
        "load", "load_json"
    )
    shipped = lj.git(repo, "show", "--name-only", "--format=", "HEAD").split()
    assert sorted(shipped) == ["src/app/main.py", "src/app/store.py"]
    ran = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            "import app.main as m; print(m.main('data.json'))",
        ],
        cwd=repo,
        env={**os.environ, "PYTHONPATH": str(repo / "src")},
        capture_output=True,
        text=True,
    )
    assert ran.returncode == 0, ran.stderr
    assert ran.stdout.strip() == "{'ok': 1}"
