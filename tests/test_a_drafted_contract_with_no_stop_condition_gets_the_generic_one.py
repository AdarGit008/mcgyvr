"""A drafted contract with no stop condition gets the generic one, in code.

A contract whose kind runs on a model must name at least one condition that
sends the worker to BLOCKED (`contract.validate`). The fill proposer states the
generic one in code (`candidates.stop_condition`); a proposer that drafts its
fields, the one a re-decomposition asks, may leave them out. Emission fills the
same generic condition for such a proposal, so the product's own output is not
refused by its own validator. A proposal that states its own stop conditions,
and a deterministic operation, are emitted as they were.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

import pytest

from mcgyvr.cli.commands import delegate as command
from mcgyvr.config import Config
from mcgyvr.contract import Contract, dumps, generic_stop_condition, loads
from mcgyvr.decompose.decompose import Decomposition, Proposal, decompose
from mcgyvr.delegate import _drafting
from mcgyvr.ladder_map import Protocol
from mcgyvr.redecompose import Spent, request_for
from mcgyvr.repo.index import Index, build_index
from mcgyvr.runner import Completion, Request, StopReason
from mcgyvr.session import Session
from tests.decomposes import git
from tests.refines import repository
from tests.test_the_batch_redecomposes_a_spent_contract_and_frees_what_it_held import (
    CALLER,
    CODEC,
    EXPORT,
    RENAME,
    Policy,
    results,
    stand_in,
)


@pytest.fixture
def index(tmp_path: Path) -> Index:
    return repository(tmp_path / "drafted")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """The batch tests' repository: a codec, and an export that calls it."""
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "pkg" / "codec.py").write_text(CODEC)
    (root / "pkg" / "export.py").write_text(EXPORT)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "seed")
    return root


def reply_of(*entries: dict[str, Any]) -> str:
    """A proposer's reply: the JSON array a drafted proposer is answered with."""
    return json.dumps(list(entries))


def drafted(reply: str) -> Any:
    """The drafted proposer, its model answering `reply`."""

    def send(request: Request) -> Completion:
        return Completion(
            text=reply,
            stop_reason=StopReason.COMPLETE,
            raw_stop_reason="stop",
            model="drafter",
            source="test",
            protocol=Protocol.OPENAI,
            max_output_tokens=None,
            latency_s=0.0,
        )

    return _drafting(send, asked="proposer")


UNSTATED: dict[str, Any] = {
    "task_type": "code",
    "task": "Document listing.",
    "target": "listing.py",
}
FORMATTING: dict[str, Any] = {
    **UNSTATED,
    "task": "Format listing.",
    "operation": "format",
}


# -- emission -------------------------------------------------------------------


def test_a_drafted_proposal_with_no_stop_condition_is_emitted_with_the_generic_one(
    index: Index,
) -> None:
    result = decompose(index, "document listing", propose=drafted(reply_of(UNSTATED)))

    assert result.refusals == ()
    (built,) = result.contracts
    assert built.stop_conditions == (generic_stop_condition("code", "listing.py"),)
    (document,) = result.documents
    assert loads(document) == built
    assert json.loads(document)["stop_conditions"] == list(built.stop_conditions)


def test_a_proposal_that_states_its_own_stop_conditions_is_emitted_as_it_was(
    index: Index,
) -> None:
    own = ("the documented behaviour is ambiguous",)
    result = decompose(
        index,
        "document listing",
        propose=drafted(reply_of({**UNSTATED, "stop_conditions": list(own)})),
    )

    (built,) = result.contracts
    assert built.stop_conditions == own
    (document,) = result.documents
    assert json.loads(document)["stop_conditions"] == list(own)


def test_a_deterministic_operation_gets_no_stop_condition(index: Index) -> None:
    result = decompose(index, "format listing", propose=drafted(reply_of(FORMATTING)))

    (built,) = result.contracts
    assert built.operation == "format"
    assert built.stop_conditions == ()
    (document,) = result.documents
    assert json.loads(document)["stop_conditions"] == []


def test_what_needs_no_generic_stop_condition_is_returned_as_it_was() -> None:
    """Its own stop conditions, a deterministic operation, or an operation the
    catalog does not know (the contract refuses that by name): not rebuilt."""
    from mcgyvr.decompose.decompose import _stop_conditions_for

    for fields in (
        {**UNSTATED, "stop_conditions": ("the documented behaviour is ambiguous",)},
        FORMATTING,
        {**UNSTATED, "operation": "no-such-operation"},
    ):
        proposal = Proposal(**fields)
        assert _stop_conditions_for(proposal) is proposal


# -- re-decomposition -----------------------------------------------------------

#: The drafted model's reply in the spent rename's place: a narrower task on
#: the same target, and no stop condition.
NARROWER = {
    "task_type": "code",
    "task": "Rename the function rec_to_map to pairs_of; change nothing else.",
    "target": "pkg/codec.py",
    "interface": "def pairs_of(record) -> list",
}


class Redecompose:
    """Re-decomposes as `_redecomposer` does: `decompose` on the spent contract's
    own request, its failure notes on the evidence, the drafted proposer asked."""

    def __init__(self, root: Path, reply: str) -> None:
        self.root = root
        self.reply = reply

    def __call__(self, spent: Spent) -> Decomposition:
        return decompose(
            build_index(self.root),
            request_for(spent.contract),
            propose=drafted(self.reply),
            spent=spent,
        )


class CameTo(dict[str, tuple[str, bool]]):
    """Each contract's outcome; one the batch takes in a spent one's place lands."""

    def __missing__(self, key: str) -> tuple[str, bool]:
        return ("accepted", True)


def test_a_redecomposition_whose_reply_states_no_stop_condition_is_run(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = tmp_path / "journal"
    ran: list[Contract] = []
    came_to = CameTo({"code-rename": ("ladder_spent", False)})
    came_to["code-caller"] = ("accepted", False)
    monkeypatch.setattr(command, "_run", stand_in(repo, journal, came_to, ran))
    dec = Decomposition(
        contracts=(RENAME, CALLER), documents=(dumps(RENAME), dumps(CALLER))
    )
    args = argparse.Namespace(
        config=None,
        sandbox=None,
        commit=True,
        branch=None,
        record=None,
        session_id="test-session",
        session=Session("test-session"),
    )
    policy = Policy({"journal.dir": str(journal), "dependents": "hold"})

    code = command._run_delegated(
        args,
        repo,
        dec,
        [],
        cast(Config, policy),
        redecompose=Redecompose(repo, reply_of(NARROWER)),
    )

    (result,) = results(journal, "code-rename")
    assert "nothing new" not in result["redecomposed"]["detail"]
    (replacement,) = result["redecomposed"]["contracts"]
    assert [c.id for c in ran] == ["code-rename", replacement, "code-caller"]
    assert ran[1].stop_conditions == (generic_stop_condition("code", "pkg/codec.py"),)
    assert ran[1].lineage.replaces == "code-rename"
    assert code == 0
