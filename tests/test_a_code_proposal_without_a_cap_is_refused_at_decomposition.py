"""A proposal that would be a `code` contract with no cap is refused where it is made.

Every model-written `code` contract
states ``limits.max_output_tokens``, and one that does not is refused at
dispatch. A decomposition that emitted one would hand ``mcgyvr run`` a contract
certain to be refused, so the decomposer refuses it first, naming the field,
before anything is dispatched. A proposal that states its cap is written with
it, and keeps it when the contract is resized to its worker view.
"""

from __future__ import annotations

import json
from pathlib import Path

from mcgyvr.delegate import _reply_format
from mcgyvr.orchestrator.decompose import Proposal, RecordedProposer, decompose
from mcgyvr.orchestrator.index import Index, build_index
from tests.livejournal import git

LISTING = "def listing(items):\n    return list(items)\n"


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


def test_a_code_proposal_with_no_cap_is_refused_by_name(tmp_path: Path) -> None:
    result = decompose(
        _repo(tmp_path), "do the thing", propose=RecordedProposer((_proposal(),))
    )

    assert result.contracts == ()
    (refused,) = result.refusals
    assert refused.subject == "listing.py"
    assert "max_output_tokens" in refused.reason, refused.reason


def test_a_code_proposal_that_states_its_cap_is_written_with_it(
    tmp_path: Path,
) -> None:
    result = decompose(
        _repo(tmp_path),
        "do the thing",
        propose=RecordedProposer((_proposal(max_output_tokens=777),)),
    )

    assert result.refusals == (), result.refusals
    (built,) = result.contracts
    assert built.limits.max_output_tokens == 777
    (document,) = result.documents
    assert json.loads(document)["limits"]["max_output_tokens"] == 777


def test_the_cap_survives_the_resize_to_the_worker_view(tmp_path: Path) -> None:
    # A target large enough that the view outgrows the schema's 4096-token
    # input ceiling, so the contract is rebuilt at the size it needs.
    big = LISTING + "".join(f"VALUE_{n} = {n}\n" for n in range(1800))
    result = decompose(
        _repo(tmp_path, big),
        "do the thing",
        propose=RecordedProposer((_proposal(max_output_tokens=777),)),
        max_input_tokens=64000,
    )

    assert result.refusals == (), result.refusals
    (built,) = result.contracts
    assert built.max_input_tokens > 4096, "the fixture no longer forces a resize"
    assert built.limits.max_output_tokens == 777


def test_the_prose_proposer_is_told_a_code_proposal_states_its_cap() -> None:
    said = _reply_format()
    line = said[said.index('"max_output_tokens"') :].split("\n- ", 1)[0]
    assert "required for task_type code" in line, line
