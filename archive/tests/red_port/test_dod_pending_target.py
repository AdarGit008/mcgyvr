"""B6 — ``meta.json``'s target is re-validated before it is used as a filesystem path.

``resume`` reads ``record.target`` out of ``meta.json`` and then does
``entry / FILES / record.target``. ``meta.json`` is a plain file in a plain
directory — an operator editing it mid-incident, or an entry that arrived
carrying an escaping target, could steer that read anywhere the process can
reach. The module already has ``_relative``, which refuses absolute and escaping
targets; ``resume`` just never ran it on the read side.

The statement is that a tampered target is refused as a ``PendingError`` *before*
any bytes outside the entry are read, not merely that the wrong content fails
the re-gate after the fact.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.pending import PendingError
from tests.red_port.conftest import required

STASH = (
    "stash gate-passed work that could not be verified, in a form that can resume it"
)
LIST = "list the work it is holding, so an operator can see what is owed"
RESUME = "resume stashed work once verification is reachable again"

GOOD = 'def fetch(url):\n    return "café " + url\n'


def _stash() -> Any:
    return required(
        STASH, lambda: __import__("mcgyvr.pending", fromlist=["stash"]).stash
    )


def _listing() -> Any:
    return required(
        LIST, lambda: __import__("mcgyvr.pending", fromlist=["listing"]).listing
    )


def _resume() -> Any:
    return required(
        RESUME, lambda: __import__("mcgyvr.pending", fromlist=["resume"]).resume
    )


def test_a_tampered_target_is_refused_before_it_becomes_a_path(
    repo: Path, contract: Any, tmp_path: Path
) -> None:
    """An escaping ``target`` in ``meta.json`` raises instead of being read.

    The tampered value points three levels up, out of the store entirely, at a
    file the test plants with distinctive content. The resume must refuse the
    target before the verifier sees any of that content; a read that succeeds
    and then fails the gate is the defect, not a fix.
    """
    store = tmp_path / "pending"
    _stash()(store=store, repo=repo, contract=contract, content=GOOD)

    entry = next(e for e in _listing()(store=store) if e.task == contract.id).entry
    meta = json.loads((entry / "meta.json").read_text(encoding="utf-8"))
    meta["target"] = "../../../stolen.txt"
    (entry / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    planted = tmp_path / "stolen.txt"
    planted.write_text("def stolen():\n    return 'read outside the entry'\n")
    shown: list[str] = []

    def approve(content: str) -> bool:
        shown.append(content)
        return False

    with pytest.raises(PendingError, match="repository-relative"):
        _resume()(store=store, repo=repo, task=contract.id, verify=approve)

    assert shown == [], f"the tampered target was read before it was refused: {shown!r}"
