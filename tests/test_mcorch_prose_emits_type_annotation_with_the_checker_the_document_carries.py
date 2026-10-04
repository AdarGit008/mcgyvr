"""Under mcorch's prose path, `type_annotation` is emitted with the document's checker.

The read document carries the checker the repository declared, located where
the repository is; the server, which has no repository, hands it to the
decomposer in place of a read of its own. A `type_annotation` proposal then
becomes a contract whose acceptance is that command, exactly as located; a
document carrying none refuses the type by name, as `mcgyvr delegate` does on
a repository that declares no checker, and never guesses a command. The
document's ``root`` is a path that does not exist here: nothing on the server
opens one.
"""

from __future__ import annotations

import json
from pathlib import Path

from mcgyvr.config import parse
from mcgyvr.mcorch import authoring, evidence
from tests.mcorch_fakes import ScriptedJev, ScriptedRung, text

SETUP = """\
units:
  small:
    address: http://box.invalid:11434
    model: coder-7b
    rig: box
    width: 3
ladder:
- small
"""

LISTING = "def listing(items):\n    return list(items)\n"
PROPOSAL = json.dumps(
    [
        {
            "task_type": "type_annotation",
            "task": "Annotate listing() and its return.",
            "target": "listing.py",
            "stop_conditions": ["the element type is ambiguous"],
        }
    ]
)


def _document(located: dict[str, list[str]] | None) -> evidence.Document:
    raw: dict[str, object] = {
        "prompt": "annotate listing",
        "root": "/nowhere/that/exists/work",
        "resolution": {
            "verdict": "resolved",
            "candidates": [{"path": "listing.py", "score": 2.0, "evidence": ["name"]}],
        },
        "reads": [],
        "files": [{"path": "listing.py", "text": LISTING}],
    }
    if located is not None:
        raw["located"] = located
    document = evidence.parse_document(json.dumps(raw))
    assert document is not None
    return document


def _prose() -> tuple[authoring.Evidenced, ScriptedRung]:
    rung = ScriptedRung(text(PROPOSAL))
    chosen = authoring.authoring_for(
        "prose", jev=ScriptedJev(ready_to_run=True), rung=rung, config=parse(SETUP)
    )
    assert isinstance(chosen, authoring.Evidenced)
    return chosen, rung


def test_the_documents_checker_becomes_the_contracts_acceptance() -> None:
    chosen, _ = _prose()
    document = _document({"python": ["mypy"]})
    assert not Path(document.root).exists()
    digest = chosen.propose(document, max_output_tokens=400)
    assert digest.startswith("ready: contract ")
    assert '"task_type": "type_annotation"' in digest
    assert (
        '"acceptance": [\n    "mypy"\n  ]' in digest
        or '"acceptance": ["mypy"]' in digest
    )
    assert document.located == {"python": ("mypy",)}


def test_a_document_with_no_checker_refuses_the_type_by_name() -> None:
    chosen, _ = _prose()
    digest = chosen.propose(_document({}), max_output_tokens=400)
    assert digest.startswith("refused: listing.py")
    assert "declares no type checker" in digest
    assert "type_annotation" in digest
    assert "ready:" not in digest


def test_a_document_from_before_the_field_carries_no_checker() -> None:
    document = _document(None)
    assert document.located == {}
    chosen, _ = _prose()
    digest = chosen.propose(document, max_output_tokens=400)
    assert "declares no type checker" in digest
