"""The floor checks its acceptance against the unchanged tree before the tool runs.

`_climb` runs a contract's `acceptance` and `demonstration` against the base
tree first (`Acceptance.baseline`): a suite already red there is refused as an
orchestration error, not charged to the change. The floor did not, so a red
suite reached the gate after the tool ran and read as the tool's change being
``rejected`` — the wrong thing to replan from. The same baseline now runs on
the floor, before the tool step, and nothing is written to the journal for a
run that never started its work.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests import livejournal as lj

RED_SUITE = """
id: tidy
task_type: code
operation: format
task: Reformat the module with the project's formatter.
target: src/pkg/messy.py
acceptance: ["python -c 'import sys; sys.exit(1)'"]
scope:
  allow: ["src/**"]
"""


def test_a_floor_run_refuses_an_acceptance_suite_that_is_already_red(
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
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "setup", journal_dir=journal)
    contract = lj.make_contract(tmp_path / "tidy.yaml", RED_SUITE)

    code = lj.main(lj.run_args(contract, repo, config))

    out = capsys.readouterr().out
    result = json.loads(lj.result_path(out).read_text(encoding="utf-8"))
    assert code == 1, out
    assert result["outcome"] == "error", result
    assert "ruff format" not in out, "the tool ran before the baseline was checked"
    assert lj.rows(journal) == [], "a run that never started its work left a row"
