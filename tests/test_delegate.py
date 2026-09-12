"""Delegated mode: the orchestrator role turns a reply into proposals.

These hold the three things the feature's acceptance names — a proposer built
on the orchestrator role reads a model reply as proposals, ``decompose`` emits
validated contracts through that proposer end-to-end, and a keyless install
answers with the documented "no orchestrator role" instead of a traceback.

The only thing substituted is the model: ``dispatch_role`` is patched at the
same seam the verifier's tests patch, so the role lookup, the prompt builder
and the proposal parser all run for real while no backend is required.
"""

from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

import pytest

from mcgyvr.config import parse
from mcgyvr.delegate import (
    NO_ORCHESTRATOR_ROLE,
    UnreadableProposalError,
    proposals_from_reply,
    proposer_for,
)
from mcgyvr.exits import Exit
from mcgyvr.orchestrator.decompose import (
    DepRef,
    Evidence,
    Proposal,
    decompose,
)
from mcgyvr.orchestrator.index import Index, build_index
from mcgyvr.orchestrator.read import explore
from mcgyvr.orchestrator.resolve import resolve
from mcgyvr.pool import Protocol, source_map
from mcgyvr.runner import Completion, StopReason

#: A keyless local ladder with no orchestrator block — the ordinary install
#: that must answer "no orchestrator role" rather than fail.
LADDER = """
version: 1
sources:
  workstation:
    base_url: http://localhost:11434
    api: openai
    max_parallel: 2
ladder:
  tiers:
    - name: local_qwen-7b
      source: workstation
      model: qwen2.5-coder:7b
"""

#: The same install with the orchestrator role bound to a usable source.
ORCHESTRATOR = (
    LADDER
    + """
orchestrator:
  source: workstation
  model: qwen2.5-coder:14b
"""
)

#: A reply the orchestrator role might send: one well-formed proposal.
DOCSTRING_REPLY = json.dumps(
    [
        {
            "task_type": "docstring",
            "task": "document listing()",
            "target": "listing.py",
            "stop_conditions": ["the function's behaviour is ambiguous"],
        }
    ]
)


def cfg(body: str) -> str:
    return textwrap.dedent(body).strip() + "\n"


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t.io", "-c", "user.name=t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Index:
    """A small repository with a target worth proposing work against."""
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "listing.py").write_text("def listing(items):\n    return items\n")
    (root / "pagination.py").write_text(
        "def paginate(items, size=10):\n    return items[:size]\n"
    )
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "seed")
    return build_index(root)


def evidence_for(repo: Index, prompt: str) -> Evidence:
    """The deterministic pass ``decompose`` would hand a proposer."""
    resolution = resolve(repo, prompt)
    return Evidence(
        prompt=prompt,
        index=repo,
        resolution=resolution,
        exploration=explore(repo, resolution),
        vocabulary=(),
    )


def completion(text: str) -> Completion:
    return Completion(
        text=text,
        stop_reason=StopReason.COMPLETE,
        raw_stop_reason="stop",
        model="qwen2.5-coder:14b",
        source="workstation",
        protocol=Protocol.OPENAI,
        max_output_tokens=4096,
        latency_s=0.0,
    )


# --- (a) a proposer builds proposals from a model reply --------------------


def test_proposals_from_reply_reads_a_json_array() -> None:
    proposals = proposals_from_reply(DOCSTRING_REPLY)

    assert proposals == (
        Proposal(
            task_type="docstring",
            task="document listing()",
            target="listing.py",
            stop_conditions=("the function's behaviour is ambiguous",),
        ),
    )


def test_proposals_from_reply_reads_a_fenced_reply() -> None:
    fenced = f"```json\n{DOCSTRING_REPLY}\n```\n"

    assert proposals_from_reply(fenced)[0].target == "listing.py"


def test_proposals_from_reply_carries_deps_and_optional_fields() -> None:
    reply = json.dumps(
        [
            {
                "task_type": "bug_fix",
                "task": "page the items before returning",
                "target": "listing.py",
                "interface": "listing(items, size=10) -> list",
                "deps": [
                    {
                        "path": "pagination.py",
                        "symbol": "paginate",
                        "note": "page the items with this",
                    }
                ],
                "allow": ["listing.py", "pagination.py"],
                "forbid": ["docs/**"],
                "stop_conditions": ["the pager's contract is ambiguous"],
                "acceptance": ["pytest -q"],
                "demonstration": ["pytest -q tests/test_listing.py::test_page_size"],
                "risk": "low",
            }
        ]
    )

    (proposal,) = proposals_from_reply(reply)
    assert proposal.task_type == "bug_fix"
    assert proposal.deps == (
        DepRef("pagination.py", "paginate", "page the items with this"),
    )
    assert proposal.allow == ("listing.py", "pagination.py")
    assert proposal.forbid == ("docs/**",)
    assert proposal.acceptance == ("pytest -q",)
    assert proposal.demonstration == (
        "pytest -q tests/test_listing.py::test_page_size",
    )
    assert proposal.risk == "low"


def test_proposals_from_reply_refuses_prose() -> None:
    with pytest.raises(UnreadableProposalError):
        proposals_from_reply("sure, here is a proposal: listing.py")


def test_proposer_for_dispatches_to_the_role_and_parses_the_reply(
    repo: Index, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mcgyvr.delegate as delegate

    pool = source_map(parse(cfg(ORCHESTRATOR)))
    seen: list[str] = []

    def fake_dispatch_role(source_map, role, request, *, capacity=None):  # type: ignore[no-untyped-def]
        seen.append(request.prompt)
        return completion(DOCSTRING_REPLY)

    monkeypatch.setattr(delegate, "dispatch_role", fake_dispatch_role)

    propose = proposer_for(pool)
    assert propose is not None
    proposals = propose(evidence_for(repo, "document listing"))

    assert proposals == (
        Proposal(
            task_type="docstring",
            task="document listing()",
            target="listing.py",
            stop_conditions=("the function's behaviour is ambiguous",),
        ),
    )
    assert len(seen) == 1
    assert "document listing" in seen[0]
    assert "listing.py" in seen[0]


# --- (b) decompose emits validated contracts end-to-end --------------------


def test_decompose_emits_validated_contracts_through_the_role(
    repo: Index, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mcgyvr.contract as contract_module
    import mcgyvr.delegate as delegate

    config = parse(cfg(ORCHESTRATOR))
    pool = source_map(config)
    asked: list[str] = []

    def fake_dispatch_role(source_map, role, request, *, capacity=None):  # type: ignore[no-untyped-def]
        asked.append(request.prompt)
        return completion(DOCSTRING_REPLY)

    monkeypatch.setattr(delegate, "dispatch_role", fake_dispatch_role)

    propose = proposer_for(pool)
    assert propose is not None
    result = decompose(repo, "document listing", propose=propose, config=config)

    assert result.refusals == ()
    (contract,) = result.contracts
    assert contract.task_type == "docstring"
    assert contract.target == "listing.py"
    # The emitted document is exactly what direct mode accepts.
    assert contract_module.loads(result.documents[0]) == contract
    assert asked, "the orchestrator role was never asked"
    assert "document listing" in asked[0]


# --- (c) a keyless install returns the documented answer -------------------


def test_proposer_for_returns_none_without_an_orchestrator_role() -> None:
    pool = source_map(parse(cfg(LADDER)))

    assert proposer_for(pool) is None


def test_a_keyless_install_answers_the_documented_no_role(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mcgyvr.cli import main

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("MCGYVR_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)

    code = main(["delegate", "document the listing helper"])

    assert code == Exit.REFUSED
    assert NO_ORCHESTRATOR_ROLE in capsys.readouterr().err


def test_the_delegate_command_writes_contracts_from_the_role(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import mcgyvr.delegate as delegate
    from mcgyvr.cli import main

    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "listing.py").write_text("def listing(items):\n    return items\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "seed")

    config = tmp_path / "mcgyvr.yaml"
    config.write_text(cfg(ORCHESTRATOR), encoding="utf-8")
    out = tmp_path / "contracts"

    def fake_dispatch_role(source_map, role, request, *, capacity=None):  # type: ignore[no-untyped-def]
        return completion(DOCSTRING_REPLY)

    monkeypatch.setattr(delegate, "dispatch_role", fake_dispatch_role)

    code = main(
        [
            "delegate",
            "document listing",
            str(repo),
            "--config",
            str(config),
            "--output",
            str(out),
        ]
    )

    assert code == 0
    (written,) = out.iterdir()
    document = json.loads(written.read_text(encoding="utf-8"))
    assert document["task_type"] == "docstring"
    assert document["target"] == "listing.py"
    assert "contract(s) proposed" in capsys.readouterr().err
