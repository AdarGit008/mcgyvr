"""A contract a model executes may leave ``limits.max_output_tokens`` out.

It used to be refused by ``mcgyvr contract`` and ``mcgyvr run`` (owner ruling:
"fail loud when no budget is declared"): a cap the loader derived from the
task type alone was a number nobody chose. The e2e run of 2026-10-13 showed
the stated number was the trap — DeepSeek's reasoning models spent a 1024 cap
on hidden reasoning and replied with nothing — and the owner's direction is a
cap that is a function of the file being changed. So a contract that states
none is accepted, and each attempt sizes its cap from the target
(``tests/test_an_unpinned_reply_cap_is_sized_from_the_target.py``), recording
how. A stated cap still wins, and a deterministic contract is not asked.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests import livejournal as lj

UNCAPPED = """
id: impl
task_type: code
task: Set VALUE to 1.
target: src/pkg/messy.py
stop_conditions: ["The value is not stated."]
demonstration: ["sh -c 'grep -q VALUE src/pkg/messy.py'"]
acceptance: ["python -c 'import sys; sys.exit(0)'"]
scope:
  allow: ["src/**"]
"""
CAPPED = UNCAPPED + "limits:\n  max_output_tokens: 256\n"
FORMAT = """
id: tidy
task_type: code
operation: format
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


def test_contract_accepts_a_model_contract_with_no_cap_and_says_how_it_is_sized(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = lj.make_contract(tmp_path / "impl.yaml", UNCAPPED)
    assert lj.main(["contract", str(path)]) == 0
    out = capsys.readouterr().out
    assert "output cap sized from the target each attempt" in out, out
    assert "from 1024 for the type" in out, "the type's floor is still printed"


def test_contract_admits_a_model_contract_that_declares_its_cap(tmp_path: Path) -> None:
    path = lj.make_contract(tmp_path / "impl.yaml", CAPPED)
    assert lj.main(["contract", str(path)]) == 0


@pytest.mark.parametrize("schema", ["prose", "media_artifact"])
def test_contract_admits_a_raw_text_reply_with_no_declared_cap(
    tmp_path: Path, schema: str
) -> None:
    """A raw-text reply carries no cap, so there is nothing to declare."""
    text = UNCAPPED + f"output_schema: {schema}\n"
    path = lj.make_contract(tmp_path / f"{schema}.yaml", text)
    assert lj.main(["contract", str(path)]) == 0


def test_contract_does_not_ask_a_deterministic_contract_for_a_cap(
    tmp_path: Path,
) -> None:
    path = lj.make_contract(tmp_path / "tidy.yaml", FORMAT)
    assert lj.main(["contract", str(path)]) == 0


def test_run_dispatches_a_model_contract_with_no_cap(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sent = lj.scripted(monkeypatch, lj.GOOD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=tmp_path / "journal")
    contract = lj.make_contract(tmp_path / "impl.yaml", UNCAPPED)
    code = lj.main(lj.run_args(contract, repo, config))
    out = capsys.readouterr()
    assert code == 0, out
    assert len(sent) == 1
