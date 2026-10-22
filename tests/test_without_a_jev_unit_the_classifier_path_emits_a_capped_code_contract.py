"""Without a jev unit, `authoring: classifier` still emits a capped `code` contract.

With no jev unit opted in, the classifier path asks no model: it collapses the
first candidate of every field. That collapse used to state no reply cap, so a
`code` proposal was refused at decomposition ("states no max_output_tokens")
and, since the typed proposer had proposed something, prose was never asked:
`mcgyvr delegate` emitted nothing. The collapse now states the cap the first
type and target need, as the typed path does.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

import mcgyvr.decision as decision
from mcgyvr.catalog import catalog
from mcgyvr.config import parse
from mcgyvr.delegate import classifier_proposer_for, proposer_by_authoring
from mcgyvr.gate.preflight import check_cap_stated
from mcgyvr.local_pool import source_map
from mcgyvr.orchestrator.candidates import reply_cap
from mcgyvr.orchestrator.decompose import Evidence, Proposal, decompose
from mcgyvr.orchestrator.index import Index, build_index

#: A keyless local ladder with no jev block: nothing to ask typed questions of.
LADDER = """\
units:
  local_qwen-7b:
    address: http://localhost:11434
    model: qwen2.5-coder:7b
    rig: workstation
    width: 2
ladder:
- local_qwen-7b
"""


@pytest.fixture
def repo(tmp_path: Path) -> Index:
    root = tmp_path / "repo"
    root.mkdir()

    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-c", "user.email=t@t.io", "-c", "user.name=t", *args],
            cwd=root,
            check=True,
            capture_output=True,
        )

    git("init", "-q", "-b", "main")
    (root / "listing.py").write_text("def listing(items):\n    return items\n")
    git("add", "-A")
    git("commit", "-q", "-m", "seed")
    return build_index(root)


def test_the_no_jev_collapse_emits_a_code_contract_with_a_cap(
    repo: Index, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_model(*args: object, **kwargs: object) -> object:
        raise AssertionError("no model is asked without a jev unit")

    def prose(evidence: Evidence) -> Sequence[Proposal]:
        raise AssertionError("the collapse proposed, so prose is not asked")

    monkeypatch.setattr(decision, "_post_json", no_model)
    typed = classifier_proposer_for(source_map(parse(LADDER)))
    propose = proposer_by_authoring("classifier", typed=typed, prose=prose)
    assert propose is not None

    result = decompose(repo, "document listing", propose=propose)

    assert result.refusals == ()
    (contract,) = result.contracts
    assert contract.task_type == "code"
    assert contract.task == "document listing"
    assert contract.limits.max_output_tokens is not None
    assert check_cap_stated(contract) is None


def test_the_collapse_states_the_cap_the_typed_path_would(repo: Index) -> None:
    typed = classifier_proposer_for(source_map(parse(LADDER)))
    assert typed is not None
    asked: list[Evidence] = []

    def watch(evidence: Evidence) -> Sequence[Proposal]:
        asked.append(evidence)
        return typed(evidence)

    result = decompose(repo, "document listing", propose=watch)

    (contract,) = result.contracts
    (evidence,) = asked
    assert contract.limits.max_output_tokens == reply_cap(
        evidence, catalog().require("code"), "listing.py"
    )
