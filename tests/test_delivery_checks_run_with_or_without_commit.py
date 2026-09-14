"""What a run leaves in the tree is checked exactly as what it would commit.

``place`` — the default, no ``--commit`` — wrote the accepted bytes after asking
git whether the target was safe to overwrite, and nothing else. ``deliver``
refuses a change identical to its base, a target outside the contract's scope
and bytes the commit-time gate rejects. Live run ``doc-structured-validators``
(2026-09-14T18:55:25Z) was reported ``accepted`` / "change left in
src/mcgyvr/gate/structured.py" while the reply was byte-identical to the file:
nothing had changed, and only the commit path would have said so.

Both paths now run one set of checks, and a refusal on either leaves the tree
exactly as it was found.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.contract import load
from mcgyvr.deliver import Accepted, DeliveryError, place
from mcgyvr.gate import GateResult
from mcgyvr.scope import Scope
from tests import livejournal as lj

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


def _accepted(repo: Path, contract: Any, text: str) -> Accepted:
    """An `Accepted` minted the only way one can be: read off a tree."""
    (repo / contract.target).write_text(text, encoding="utf-8")
    bound = Accepted.read(repo=repo, contract=contract, result=GateResult())
    lj.git(repo, "checkout", "--", contract.target)
    return bound


def _as_found(repo: Path) -> None:
    assert (repo / "src/pkg/messy.py").read_text() == "x = 0\n"
    assert lj.git(repo, "status", "--porcelain") == ""


def test_place_refuses_content_identical_to_its_base(tmp_path: Path) -> None:
    repo = lj.make_repo(tmp_path / "repo")
    contract = load(lj.make_contract(tmp_path / "impl.yaml"))
    base = lj.git(repo, "rev-parse", "HEAD").strip()
    bound = _accepted(repo, contract, "x = 0\n")

    with pytest.raises(DeliveryError, match="identical") as refused:
        place(repo=repo, contract=contract, content=bound, base=base)

    assert contract.target in str(refused.value)
    _as_found(repo)


def test_place_refuses_bytes_the_commit_time_gate_rejects(tmp_path: Path) -> None:
    repo = lj.make_repo(tmp_path / "repo")
    contract = load(lj.make_contract(tmp_path / "impl.yaml"))
    base = lj.git(repo, "rev-parse", "HEAD").strip()
    bound = _accepted(repo, contract, "def broken(:\n")

    with pytest.raises(DeliveryError, match="does not pass the gate"):
        place(repo=repo, contract=contract, content=bound, base=base)

    _as_found(repo)


def test_place_refuses_a_target_outside_the_contracts_scope(tmp_path: Path) -> None:
    repo = lj.make_repo(tmp_path / "repo")
    loaded = load(lj.make_contract(tmp_path / "impl.yaml"))
    base = lj.git(repo, "rev-parse", "HEAD").strip()
    bound = _accepted(repo, loaded, "VALUE = 1\n")
    narrowed = dataclasses.replace(
        loaded, scope=Scope.of(["src/**"], ["src/pkg/messy.py"])
    )

    with pytest.raises(DeliveryError, match="outside the scope"):
        place(repo=repo, contract=narrowed, content=bound, base=base)

    _as_found(repo)


def test_place_still_leaves_a_checked_change_in_the_tree(tmp_path: Path) -> None:
    repo = lj.make_repo(tmp_path / "repo")
    contract = load(lj.make_contract(tmp_path / "impl.yaml"))
    base = lj.git(repo, "rev-parse", "HEAD").strip()
    bound = _accepted(repo, contract, "VALUE = 1\n")

    written = place(repo=repo, contract=contract, content=bound, base=base)

    assert written.read_text() == "VALUE = 1\n"
    assert lj.git(repo, "rev-parse", "HEAD").strip() == base, "nothing committed"


def test_a_run_whose_reply_changes_nothing_is_delivery_refused_without_commit(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    contract = lj.make_contract(tmp_path / "impl.yaml", NO_DEMO_CONTRACT)
    scripted = lj.scripted(monkeypatch, "```python\nx = 0\n```")

    code = lj.main(lj.run_args(contract, repo, config))

    assert scripted, "the model was asked"
    result = json.loads(lj.result_path(capsys.readouterr().out).read_text())
    assert result["outcome"] == "delivery_refused", result
    assert code == 1
    _as_found(repo)
