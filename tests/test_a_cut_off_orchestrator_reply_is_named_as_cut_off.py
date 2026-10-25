"""An orchestrator reply cut off at its cap is named as cut off, not as "not JSON".

A reply the backend stopped at a length limit is read by its stop reason before
its text: a proposal array cut off mid-entry opens as valid JSON, and calling it
malformed points the reader at the model's format rather than at the room the
unit gave it. The error says the reply was cut off, how many tokens it had spent
and the cap it was sent, names the unit, and says what to change. A reply that
finished on its own and is still not JSON keeps the "not JSON" error.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import mcgyvr.delegate as delegate
from mcgyvr.config import parse
from mcgyvr.delegate import (
    OrchestratorReplyCutOffError,
    UnreadableProposalError,
    proposer_for,
)
from mcgyvr.local_pool import Protocol, source_map
from mcgyvr.orchestrator.decompose import Evidence
from mcgyvr.orchestrator.index import Index, build_index
from mcgyvr.orchestrator.read import explore
from mcgyvr.orchestrator.resolve import resolve
from mcgyvr.runner import Completion, StopReason

CONFIG = """\
units:
  planner:
    address: http://localhost:11434
    model: planner-model
    rig: workstation
    width: 1
ladder:
- planner
orchestrator:
  unit: planner
  model: planner-model
"""

#: The opening of a proposal array, stopped mid-string the way a cap stops it.
CUT_OFF = json.dumps(
    [{"task_type": "code", "task": "Rename the helper and update its callers."}],
    indent=2,
)[:60]


@pytest.fixture
def evidence(tmp_path: Path) -> Evidence:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "listing.py").write_text("def listing(items):\n    return items\n")
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "seed"]):
        subprocess.run(
            ["git", "-c", "user.email=t@t.io", "-c", "user.name=t", *args],
            cwd=root,
            check=True,
            capture_output=True,
        )
    index: Index = build_index(root)
    resolution = resolve(index, "document listing")
    return Evidence(
        prompt="document listing",
        index=index,
        resolution=resolution,
        exploration=explore(index, resolution),
        vocabulary=(),
    )


def _propose(
    monkeypatch: pytest.MonkeyPatch, evidence: Evidence, answer: Completion
) -> None:
    def fake_dispatch_role(source_map, role, request, *, capacity=None):  # type: ignore[no-untyped-def]
        return answer

    monkeypatch.setattr(delegate, "dispatch_role", fake_dispatch_role)
    propose = proposer_for(source_map(parse(CONFIG)))
    assert propose is not None
    propose(evidence)


def _answer(text: str, stop: StopReason, raw: str, **extra: object) -> Completion:
    return Completion(
        text=text,
        stop_reason=stop,
        raw_stop_reason=raw,
        model="planner-model",
        source="planner",
        protocol=Protocol.OPENAI,
        max_output_tokens=2000,
        latency_s=0.0,
        **extra,  # type: ignore[arg-type]
    )


def test_a_truncated_orchestrator_reply_is_named_as_cut_off_not_as_not_json(
    monkeypatch: pytest.MonkeyPatch, evidence: Evidence
) -> None:
    answer = _answer(
        CUT_OFF,
        StopReason.TRUNCATED,
        "length",
        output_tokens=2000,
        reasoning_tokens=1500,
        cap_basis="the most unit 'planner' can give: its `output_tokens` is 2000",
    )

    with pytest.raises(OrchestratorReplyCutOffError) as raised:
        _propose(monkeypatch, evidence, answer)

    said = str(raised.value)
    assert "not JSON" not in said
    assert "cut off" in said
    assert "after 2000 output tokens" in said
    assert "1500 of them reported as reasoning" in said
    assert "unit 'planner'" in said
    assert "a cap of 2000 tokens" in said
    assert "its `output_tokens` is 2000" in said
    assert "`output_tokens`" in said and "`window`" in said
    assert "thinking budget" in said
    # Still one of the ways a reply cannot be read as proposals.
    assert isinstance(raised.value, UnreadableProposalError)


def test_a_truncated_reply_with_no_token_count_still_names_its_cap(
    monkeypatch: pytest.MonkeyPatch, evidence: Evidence
) -> None:
    answer = _answer(CUT_OFF, StopReason.TRUNCATED, "length")

    with pytest.raises(OrchestratorReplyCutOffError) as raised:
        _propose(monkeypatch, evidence, answer)

    said = str(raised.value)
    assert "cut off at its 2000-token cap" in said
    assert "unit 'planner'" in said


def test_a_complete_but_malformed_reply_still_gets_the_not_json_error(
    monkeypatch: pytest.MonkeyPatch, evidence: Evidence
) -> None:
    answer = _answer(CUT_OFF, StopReason.COMPLETE, "stop", output_tokens=40)

    with pytest.raises(UnreadableProposalError) as raised:
        _propose(monkeypatch, evidence, answer)

    assert not isinstance(raised.value, OrchestratorReplyCutOffError)
    assert "not JSON" in str(raised.value)
