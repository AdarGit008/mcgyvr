"""A delegated contract pins no reply cap unless its proposal did.

The decomposer used to write the type-derived cap onto every whole-file
contract, because `mcgyvr run` refused one that stated none. The refusal is
gone: a contract that states no cap is sized at each attempt from the target
it changes, with a reasoning allowance on top
(:func:`mcgyvr.contract.auto_reply_cap`), and the type-derived figure is only
that sizing's floor. A number written here would have been the 1024 a
reasoning model spent before it wrote a line (the e2e run of 2026-10-13). A
proposal that states its own cap still wins and is written.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcgyvr import contract
from mcgyvr.config import parse
from mcgyvr.delegate import proposals_from_reply
from mcgyvr.mcorch import authoring, evidence
from mcgyvr.orchestrator.decompose import Proposal, RecordedProposer, decompose
from mcgyvr.orchestrator.index import Index, build_index
from tests.livejournal import git
from tests.mcorch_fakes import ScriptedJev, ScriptedRung, text

LISTING = "def listing(items):\n    return list(items)\n"


def _repo(tmp_path: Path) -> Index:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "listing.py").write_text(LISTING, encoding="utf-8")
    (root / "test_listing.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "seed")
    return build_index(root)


def _proposal(task_type: str, **extra: object) -> Proposal:
    base: dict[str, object] = {
        "task_type": task_type,
        "task": "Do the thing.",
        "target": "listing.py",
        "stop_conditions": ("the intent is ambiguous",),
    }
    return Proposal(**{**base, **extra})  # type: ignore[arg-type]


CODE_VARIANTS: dict[str, dict[str, object]] = {
    "gate_only": {},
    "acceptance": {"acceptance": ("python -c 'import listing'",)},
    "demonstration": {"demonstration": ("python -c 'import sys; sys.exit(1)'",)},
    "no_semantic_change": {"no_semantic_change": True},
    "type_check": {"type_check": True},  # the checker arrives through `located`
}


@pytest.mark.parametrize("variant", sorted(CODE_VARIANTS))
def test_every_code_shape_is_emitted_with_its_cap_left_to_the_sizing(
    tmp_path: Path, variant: str
) -> None:
    result = decompose(
        _repo(tmp_path),
        "do the thing",
        propose=RecordedProposer((_proposal("code", **CODE_VARIANTS[variant]),)),
        located={"python": ["mypy"]},
    )
    assert result.refusals == (), result.refusals
    (built,) = result.contracts
    assert built.max_output_tokens_declared is False
    # The loader's floor for the type, which the attempt sizes up from.
    assert built.limits.max_output_tokens == contract.output_cap(
        "code", evidence=built.evidence
    )
    (document,) = result.documents
    # Emitted as `null`, the form `dumps` writes for a cap nobody stated.
    assert json.loads(document)["limits"]["max_output_tokens"] is None


def test_a_proposal_stating_its_own_cap_wins(tmp_path: Path) -> None:
    (built,) = decompose(
        _repo(tmp_path),
        "document",
        propose=RecordedProposer((_proposal("code", max_output_tokens=777),)),
    ).contracts
    assert built.limits.max_output_tokens == 777
    assert built.max_output_tokens_declared is True


def test_the_prose_proposer_reads_a_stated_cap_from_the_reply() -> None:
    reply = json.dumps(
        [
            {
                "task_type": "code",
                "task": "Document listing.",
                "target": "listing.py",
                "stop_conditions": ["x"],
                "max_output_tokens": 512,
            },
            {
                "task_type": "code",
                "task": "Document more.",
                "target": "listing.py",
                "stop_conditions": ["x"],
            },
        ]
    )
    first, second = proposals_from_reply(reply)
    assert first.max_output_tokens == 512
    assert second.max_output_tokens is None


def test_the_mcorch_digest_hands_the_rung_a_contract_sized_per_attempt() -> None:
    document = evidence.parse_document(
        json.dumps(
            {
                "prompt": "document listing",
                "root": "/nowhere/work",
                "resolution": {
                    "verdict": "resolved",
                    "candidates": [
                        {"path": "listing.py", "score": 2.0, "evidence": ["n"]}
                    ],
                },
                "reads": [],
                "files": [{"path": "listing.py", "text": LISTING}],
            }
        )
    )
    assert document is not None
    proposals = json.dumps(
        [
            {
                "task_type": "code",
                "task": "Document listing.",
                "target": "listing.py",
                "stop_conditions": ["the intent is ambiguous"],
            }
        ]
    )
    chosen = authoring.authoring_for(
        "prose",
        jev=ScriptedJev(ready_to_run=True),
        rung=ScriptedRung(text(proposals)),
        config=parse(
            "units:\n  small:\n    address: http://box.invalid:11434\n    model: m\n"
            "    rig: box\nladder:\n- small\n"
        ),
    )
    assert isinstance(chosen, authoring.Evidenced)
    digest = chosen.propose(document, max_output_tokens=400)
    assert digest.startswith("ready: contract ")
    written = contract.loads(digest.split("\n", 1)[1])
    assert written.max_output_tokens_declared is False
    assert written.limits.max_output_tokens is not None
