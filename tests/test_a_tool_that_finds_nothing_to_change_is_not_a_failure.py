"""A program that finds nothing to change has done its job; a model that does has not.

Owner ruling: a delivery check runs whether or not the work is committed, so a
reply identical to its target — a model echoing the file it was asked to
change — is refused either way. The same check would turn a ``format`` run over
an already-formatted file into ``delivery_refused``, exit 1. That is a
different fact: the contract asked for a formatted file and there is one. The
floor's no-op ends as its own word, ``nothing_to_change``, exit 0, with or
without ``--commit``; a model's no-op stays refused.

A refusal also says why in the result file: the gate's findings behind a
no-commit refusal reach ``findings``, as they do for a gate rejection.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.contract import load
from mcgyvr.deliver import Accepted, place
from mcgyvr.gate import GateResult
from mcgyvr.gate.findings import Finding
from tests import livejournal as lj

FORMAT = """
id: tidy
task_type: format
task: Reformat the module.
target: src/pkg/messy.py
scope:
  allow: ["src/**"]
"""

#: A model contract with no demonstration, so an unchanged reply reaches
#: delivery rather than failing a "must fail before" command in the sandbox.
NO_DEMO_CONTRACT = """
id: impl
task_type: function_implementation
task: Set VALUE to 1.
target: src/pkg/messy.py
stop_conditions: ["The value is not stated."]
acceptance: ["python -c 'import sys; sys.exit(0)'"]
limits:
  max_output_tokens: 256
scope:
  allow: ["src/**"]
"""


def _result(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    return dict(json.loads(lj.result_path(capsys.readouterr().out).read_text()))


def _untouched(repo: Path, head: str) -> None:
    assert (repo / "src/pkg/messy.py").read_text() == "x = 0\n"
    assert lj.git(repo, "status", "--porcelain") == ""
    assert lj.git(repo, "rev-parse", "HEAD").strip() == head, "a commit was made"


@pytest.mark.parametrize("commit", [False, True], ids=["left", "commit"])
def test_a_floor_run_on_a_clean_target_is_nothing_to_change(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    commit: bool,
) -> None:
    from mcgyvr import cli

    lj.scripted(monkeypatch)  # nothing scripted: the floor dispatches nothing
    repo = lj.make_repo(tmp_path / "repo")  # `x = 0` is already formatted
    head = lj.git(repo, "rev-parse", "HEAD").strip()
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    contract = lj.make_contract(tmp_path / "tidy.yaml", FORMAT)
    extra = ("--commit",) if commit else ()

    code = lj.main(lj.run_args(contract, repo, config, *extra))

    result = _result(capsys)
    assert result["outcome"] == "nothing_to_change", result
    assert code == 0
    assert cli.NOTHING_TO_CHANGE == "nothing_to_change"
    assert result["exit_code"] == 0
    assert result["committed"] is False
    (row,) = lj.rows(journal)
    assert row["outcome"] == cli.NOTHING_TO_CHANGE
    assert row["tier"] == "deterministic"
    _untouched(repo, head)


@pytest.mark.parametrize("commit", [False, True], ids=["left", "commit"])
def test_a_model_reply_that_changes_nothing_is_still_refused(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    commit: bool,
) -> None:
    repo = lj.make_repo(tmp_path / "repo")
    head = lj.git(repo, "rev-parse", "HEAD").strip()
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=tmp_path / "j")
    contract = lj.make_contract(tmp_path / "impl.yaml", NO_DEMO_CONTRACT)
    scripted = lj.scripted(monkeypatch, "```python\nx = 0\n```")
    extra = ("--commit",) if commit else ()

    code = lj.main(lj.run_args(contract, repo, config, *extra))

    assert scripted, "the model was asked"
    result = _result(capsys)
    assert result["outcome"] == "delivery_refused", result
    assert code == 1
    _untouched(repo, head)


def test_place_refusal_carries_the_gate_findings(tmp_path: Path) -> None:
    from mcgyvr.deliver import DeliveryRefusedError

    repo = lj.make_repo(tmp_path / "repo")
    contract = load(lj.make_contract(tmp_path / "impl.yaml"))
    base = lj.git(repo, "rev-parse", "HEAD").strip()
    (repo / contract.target).write_text("def broken(:\n", encoding="utf-8")
    bound = Accepted.read(repo=repo, contract=contract, result=GateResult())
    lj.git(repo, "checkout", "--", contract.target)

    with pytest.raises(DeliveryRefusedError) as refused:
        place(repo=repo, contract=contract, content=bound, base=base)

    assert refused.value.findings, "the refusal dropped the gate's findings"
    assert "does not pass the gate" in str(refused.value)


def test_a_no_commit_refusal_puts_its_findings_in_the_result_file(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import mcgyvr.deliver as deliver

    finding = Finding(
        check="lint",
        path="src/pkg/messy.py",
        line=1,
        code="E999",
        message="refused at delivery",
    )

    def refusing_place(**_: Any) -> Path:
        raise deliver.DeliveryRefusedError(
            "src/pkg/messy.py does not pass the gate", findings=(finding,)
        )

    monkeypatch.setattr(deliver, "place", refusing_place)
    repo = lj.make_repo(tmp_path / "repo")
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=tmp_path / "j")
    contract = lj.make_contract(tmp_path / "impl.yaml")
    lj.scripted(monkeypatch, lj.GOOD_REPLY)

    code = lj.main(lj.run_args(contract, repo, config))

    result = _result(capsys)
    assert result["outcome"] == "delivery_refused", result
    assert code == 1
    assert result["findings"] == [str(finding)]
