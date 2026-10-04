"""A delegated contract carries the reply cap its task type derives, so `run` takes it.

`mcgyvr run` refuses a whole-file model contract that declares no
`limits.max_output_tokens` (exit 2): a reply cut at a cap nobody chose is spent
silently. The decomposer emitted every such contract without one, so every
prose (P) contract in the campaign validated and then was refused by `run`
(the lab's 2026-10-04 jev-mcorch evidence, the orch-modes RUN rows). The cap is now
written on the document from the one derivation the loader and `mcgyvr
contract` already use — :func:`mcgyvr.contract.output_cap`, the type's own
evidence — so nothing invents a number, and `run`'s refusal no longer fires. A
proposal that states its own cap wins; a deterministic type carries none,
having no reply to cap; a raw-text type (prose) carries none either.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcgyvr import cli, contract
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


WHOLE_FILE_MODEL_TYPES: dict[str, dict[str, object]] = {
    "docstring": {},
    "type_annotation": {},  # the checker arrives through `located`
    "function_implementation": {"acceptance": ("python -c 'import listing'",)},
    "test_scaffold": {"acceptance": ("python -c 'import listing'",)},
    "bug_fix": {"demonstration": ("python -c 'import sys; sys.exit(1)'",)},
}


@pytest.mark.parametrize("task_type", sorted(WHOLE_FILE_MODEL_TYPES))
def test_every_whole_file_model_type_is_emitted_with_the_cap_its_evidence_derives(
    tmp_path: Path, task_type: str
) -> None:
    result = decompose(
        _repo(tmp_path),
        "do the thing",
        propose=RecordedProposer(
            (_proposal(task_type, **WHOLE_FILE_MODEL_TYPES[task_type]),)
        ),
        located={"python": ["mypy"]},
    )
    assert result.refusals == (), result.refusals
    (built,) = result.contracts
    assert built.max_output_tokens_declared is True
    assert built.limits.max_output_tokens == contract.output_cap(task_type)
    assert cli._cap_undeclared(built) is None
    (document,) = result.documents
    assert json.loads(document)["limits"]["max_output_tokens"] == contract.output_cap(
        task_type
    )


def test_a_proposal_stating_its_own_cap_wins(tmp_path: Path) -> None:
    (built,) = decompose(
        _repo(tmp_path),
        "document",
        propose=RecordedProposer((_proposal("docstring", max_output_tokens=777),)),
    ).contracts
    assert built.limits.max_output_tokens == 777
    assert built.max_output_tokens_declared is True


def test_a_deterministic_type_carries_no_cap_and_is_not_asked_for_one(
    tmp_path: Path,
) -> None:
    (built,) = decompose(
        _repo(tmp_path),
        "format",
        propose=RecordedProposer(
            (Proposal(task_type="format", task="Format.", target="listing.py"),)
        ),
    ).contracts
    assert built.max_output_tokens_declared is False
    assert cli._cap_undeclared(built) is None


def test_the_prose_proposer_reads_a_stated_cap_from_the_reply() -> None:
    reply = json.dumps(
        [
            {
                "task_type": "docstring",
                "task": "Document listing.",
                "target": "listing.py",
                "stop_conditions": ["x"],
                "max_output_tokens": 512,
            },
            {
                "task_type": "docstring",
                "task": "Document more.",
                "target": "listing.py",
                "stop_conditions": ["x"],
            },
        ]
    )
    first, second = proposals_from_reply(reply)
    assert first.max_output_tokens == 512
    assert second.max_output_tokens is None


def test_the_mcorch_digest_hands_the_rung_a_contract_run_accepts() -> None:
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
                "task_type": "docstring",
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
    assert written.max_output_tokens_declared is True
    assert cli._cap_undeclared(written) is None
