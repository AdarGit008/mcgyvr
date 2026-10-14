"""A glob target reaches the tool as the files it names, not as the pattern.

A pattern target is legal for a deterministic operation precisely so the change
can fan across files, and delivery lands every file the floor changed in one
commit. The step itself handed the pattern to the program verbatim, with no
shell between: a program that expands its own arguments (prettier, eslint)
coped, and ruff — which does not — exited "No such file or directory" on every
`format`, `import_sort` and `lint_fix` over Python. mcgyvr now expands the
pattern itself, over the files the sandbox holds and by the same glob rules as
`scope`, so every program is handed literal paths.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests import livejournal as lj

GLOB_FORMAT = """
id: tidy-all
task_type: code
operation: format
task: Reformat the package with the project's formatter.
target: "src/pkg/*.py"
scope:
  allow: ["src/**"]
"""

MESSY = {
    "src/pkg/a.py": "x=1\ny  =  2\n",
    "src/pkg/b.py": "def f( a ):\n    return a\n",
}

TIDY = {
    "src/pkg/a.py": "x = 1\ny = 2\n",
    "src/pkg/b.py": "def f(a):\n    return a\n",
}


def test_a_glob_target_reaches_the_tool_as_the_files_it_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    lj.clean_env(monkeypatch, home)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    lj.claude_transcript(home, "s1")
    repo = lj.make_repo(tmp_path / "repo")
    for rel, text in MESSY.items():
        (repo / rel).write_text(text, encoding="utf-8")
    lj.git(repo, "add", "-A")
    lj.git(repo, "commit", "-q", "-m", "messy")
    config = lj.make_config(tmp_path / "setup", journal_dir=tmp_path / "journal")
    contract = lj.make_contract(tmp_path / "tidy.yaml", GLOB_FORMAT)

    code = lj.main(lj.run_args(contract, repo, config))

    out = capsys.readouterr().out
    result = json.loads(lj.result_path(out).read_text(encoding="utf-8"))
    assert result["outcome"] == "accepted", result
    assert code == 0, out
    for rel, text in TIDY.items():
        assert (repo / rel).read_text(encoding="utf-8") == text, rel
