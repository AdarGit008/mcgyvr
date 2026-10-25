"""A decomposed `code` contract states no reply cap: its unit's maximum is sent.

Every generating request is sent the most its unit can give, clamped to the
room the window leaves the prompt (``tests/test_every_generating_request_is_
sent_its_units_maximum.py``), so the cap is not a property of the work and no
contract has to state one. The decomposer used to require it — refusing a
`code` proposal without one, and stating twice the target's size from the typed
and no-jev paths — which held a reasoning model to a fraction of what its unit
serves. Now no path asks for or writes a cap, and a contract that still states
one loads.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

import mcgyvr.decision as decision
from mcgyvr.catalog import catalog
from mcgyvr.config import parse
from mcgyvr.contract import dumps as dump_contract
from mcgyvr.contract import loads as load_contract
from mcgyvr.decision import Choice, ChoiceAnswer, Decision, Question
from mcgyvr.delegate import (
    ClassifierProposer,
    _reply_format,
    classifier_proposer_for,
    proposals_from_reply,
    proposer_by_authoring,
)
from mcgyvr.local_pool import source_map
from mcgyvr.orchestrator.decompose import (
    Evidence,
    Proposal,
    RecordedProposer,
    decompose,
)
from mcgyvr.orchestrator.index import Index, build_index
from tests.livejournal import git

LISTING = "def listing(items):\n    return list(items)\n"

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


def _repo(tmp_path: Path, text: str = LISTING) -> Index:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "listing.py").write_text(text, encoding="utf-8")
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "seed")
    return build_index(root)


def _proposal(**extra: object) -> Proposal:
    base: dict[str, object] = {
        "task_type": "code",
        "task": "Do the thing.",
        "target": "listing.py",
        "stop_conditions": ("the intent is ambiguous",),
    }
    return Proposal(**{**base, **extra})  # type: ignore[arg-type]


def _chooses_code(state: Any, questions: Mapping[str, Question]) -> Decision:
    """Pick `code`, then rank 0 for every other field."""
    ((field, question),) = questions.items()
    assert isinstance(question, Choice)
    key = next(iter(question.options))
    if field == "task_type":
        doc = catalog().require("code").doc
        (key,) = (k for k, line in question.options.items() if line == doc)
    answer = ChoiceAnswer(choice=key, probabilities={key: 1.0}, confidence=0.9)
    return Decision(answers={field: answer})


def _no_prose(evidence: Evidence) -> Sequence[Proposal]:
    raise AssertionError("the typed path proposed, so prose is not asked")


def test_a_code_proposal_with_no_cap_is_emitted(tmp_path: Path) -> None:
    result = decompose(
        _repo(tmp_path), "do the thing", propose=RecordedProposer((_proposal(),))
    )

    assert result.refusals == (), result.refusals
    (built,) = result.contracts
    assert built.task_type == "code"
    assert built.limits.max_output_tokens is None
    (document,) = result.documents
    assert json.loads(document)["limits"]["max_output_tokens"] is None


def test_a_resized_contract_still_states_no_cap(tmp_path: Path) -> None:
    # A target large enough that the view outgrows the schema's 4096-token
    # input ceiling, so the contract is rebuilt at the size it needs.
    big = LISTING + "".join(f"VALUE_{n} = {n}\n" for n in range(1800))
    result = decompose(
        _repo(tmp_path, big),
        "do the thing",
        propose=RecordedProposer((_proposal(),)),
        max_input_tokens=64000,
    )

    assert result.refusals == (), result.refusals
    (built,) = result.contracts
    assert built.max_input_tokens > 4096, "the fixture no longer forces a resize"
    assert built.limits.max_output_tokens is None


def test_the_prose_proposer_is_not_asked_for_a_cap() -> None:
    assert "max_output_tokens" not in _reply_format()


def test_a_prose_reply_that_still_states_a_cap_is_read_without_it() -> None:
    reply = json.dumps(
        [
            {
                "task_type": "code",
                "task": "Do the thing.",
                "target": "listing.py",
                "max_output_tokens": 1024,
            }
        ]
    )

    assert proposals_from_reply(reply) == (
        Proposal(task_type="code", task="Do the thing.", target="listing.py"),
    )


def test_the_typed_proposer_states_no_cap(tmp_path: Path) -> None:
    propose = proposer_by_authoring(
        "classifier", typed=ClassifierProposer(classify=_chooses_code), prose=_no_prose
    )
    assert propose is not None

    result = decompose(_repo(tmp_path), "document listing", propose=propose)

    assert result.refusals == (), result.refusals
    (contract,) = result.contracts
    assert contract.task_type == "code"
    assert contract.limits.max_output_tokens is None


def test_the_no_jev_collapse_states_no_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_model(*args: object, **kwargs: object) -> object:
        raise AssertionError("no model is asked without a jev unit")

    monkeypatch.setattr(decision, "_post_json", no_model)
    typed = classifier_proposer_for(source_map(parse(LADDER)))
    propose = proposer_by_authoring("classifier", typed=typed, prose=_no_prose)
    assert propose is not None

    result = decompose(_repo(tmp_path), "document listing", propose=propose)

    (contract,) = result.contracts
    assert contract.limits.max_output_tokens is None


def test_a_contract_that_states_a_cap_still_loads(tmp_path: Path) -> None:
    result = decompose(
        _repo(tmp_path), "do the thing", propose=RecordedProposer((_proposal(),))
    )
    (built,) = result.contracts
    document = json.loads(dump_contract(built))
    document["limits"]["max_output_tokens"] = 777

    assert load_contract(json.dumps(document)).limits.max_output_tokens == 777


def test_the_prose_proposer_is_told_to_omit_deps_it_cannot_ground() -> None:
    # The model is shown only the resolution and read regions, not the index's
    # symbol table, so it must not guess a dependency name it has not seen. The
    # prompt says to name only symbols shown there and to omit the field rather
    # than invent one, which is what turned `proxyaddr` / `STRICT` into refusals.
    said = _reply_format()
    line = said[said.index('"deps"') :].split("\n- ", 1)[0]
    assert "RESOLUTION or READ REGIONS" in line, line
    assert "omit" in line.lower(), line


def test_the_prose_proposer_is_told_a_dependency_is_an_existing_symbol() -> None:
    # An "extract a helper `compileTrust`" request names the symbol the change
    # creates, and the target will call it — which the deps field's "may call"
    # framing reads as a dependency. The prompt must say a dependency is an
    # existing symbol and the to-be-created symbol is never a dependency, or the
    # proposer names it and decompose refuses it for having no signature yet.
    said = _reply_format()
    line = said[said.index('"deps"') :].split("\n- ", 1)[0]
    assert "existing symbol" in line, line
    assert "Never name the symbol this proposal's own target creates" in line, line


def test_the_prose_proposer_is_told_commands_run_without_a_shell() -> None:
    # The contract schema refuses `|`, `&&`, `||`, `;`, `<`, `>` and a leading
    # `VAR=` because commands run shell-less, but the proposer is never told, so
    # it invents a `| grep` pipeline for its demonstration. The prompt must list
    # the forbidden operators, or the model keeps producing them.
    said = _reply_format()
    acceptance = said[said.index('"acceptance"') :].split("\n- ", 1)[0]
    assert "no shell" in acceptance, acceptance
    assert "`|`" in acceptance and "`&&`" in acceptance and "`VAR=`" in acceptance
