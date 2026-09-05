"""A contract a model executes must declare ``limits.max_output_tokens``, or
``mcgyvr contract`` and ``mcgyvr run`` refuse it by name (owner, 2026-09-05:
"fail loud when no budget is declared").

The loader derived the cap from the task type's own evidence, silently. In the
first live e2e the top rung's reply was cut at that derived 1024 after a
41-second climb, and nobody had chosen the number. The loader still derives
one — the bench and the corpus need a number — but the two commands a person
runs refuse a model contract that leaves it out, print the derived figure as
the value to start from, and exit 2 before a sandbox is opened or a rung is
spent. A deterministic contract has no reply to cap and is not asked.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests import livejournal as lj

UNCAPPED = """
id: impl
task_type: function_implementation
task: Set VALUE to 1.
target: src/pkg/messy.py
stop_conditions: ["The value is not stated."]
acceptance: ["sh -c 'grep -q VALUE src/pkg/messy.py'"]
scope:
  allow: ["src/**"]
"""
CAPPED = UNCAPPED + "limits:\n  max_output_tokens: 256\n"
FORMAT = """
id: tidy
task_type: format
task: Reformat the module.
target: src/pkg/messy.py
scope:
  allow: ["src/**"]
"""


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    lj.clean_env(monkeypatch, home)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s-cap")
    lj.claude_transcript(home, "s-cap")
    return home


def test_contract_refuses_a_model_contract_with_no_cap_and_names_the_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = lj.make_contract(tmp_path / "impl.yaml", UNCAPPED)
    assert lj.main(["contract", str(path)]) == 2
    err = capsys.readouterr().err
    assert "limits.max_output_tokens" in err, err
    assert "1024" in err, "the derived figure is printed as the value to start from"


def test_contract_admits_a_model_contract_that_declares_its_cap(tmp_path: Path) -> None:
    path = lj.make_contract(tmp_path / "impl.yaml", CAPPED)
    assert lj.main(["contract", str(path)]) == 0


def test_contract_does_not_ask_a_deterministic_contract_for_a_cap(
    tmp_path: Path,
) -> None:
    path = lj.make_contract(tmp_path / "tidy.yaml", FORMAT)
    assert lj.main(["contract", str(path)]) == 0


def test_run_refuses_before_any_dispatch_and_before_a_sandbox(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sent = lj.scripted(monkeypatch)  # any dispatch is an unscripted one
    repo = lj.make_repo(tmp_path / "repo")
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=tmp_path / "journal")
    contract = lj.make_contract(tmp_path / "impl.yaml", UNCAPPED)
    code = lj.main(lj.run_args(contract, repo, config))
    err = capsys.readouterr().err
    assert code == 2, err
    assert "limits.max_output_tokens" in err, err
    assert sent == []
