"""B4/X3 — the pending store must not destroy the entry it is replacing before the
replacement exists.

``stash`` replaces a task's older entry wholesale: one task, one entry. The swap
used to be ``rmtree(entry)`` then ``staging.rename(entry)``, which left a window
where a crash — or a rename that failed for any other reason — destroyed the only
copy of the stranded work. The store exists to protect that work, so the
superseded entry has to survive until its replacement has actually landed.

This is asserted by crashing the swap at the moment the replacement would move
into place: the first stash's bytes must still be in the store afterwards, not
merely recoverable in principle.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mcgyvr.pending import PendingError
from tests.red_port.conftest import required

STASH = (
    "stash gate-passed work that could not be verified, in a form that can resume it"
)
LIST = "list the work it is holding, so an operator can see what is owed"

GOOD = 'def fetch(url):\n    return "café " + url\n'
NEWER = 'def fetch(url):\n    return "café " + url.strip()\n'


def _stash() -> Any:
    return required(
        STASH, lambda: __import__("mcgyvr.pending", fromlist=["stash"]).stash
    )


def _listing() -> Any:
    return required(
        LIST, lambda: __import__("mcgyvr.pending", fromlist=["listing"]).listing
    )


def _holds_exactly(root: Path, content: str) -> bool:
    """True when some file under the store is byte-for-byte the given content."""
    return any(
        path.is_file() and path.read_bytes() == content.encode("utf-8")
        for path in sorted(root.rglob("*"))
    )


def test_a_failed_swap_leaves_the_superseded_entry_in_place(
    repo: Path,
    contract: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first stash survives a crash while its replacement is being installed.

    The crash is injected at the one operation that used to follow the
    ``rmtree(entry)``: the rename that moves the staged replacement into place.
    If the superseded entry is destroyed first, the work is gone; if the swap is
    ordered safely, the first stash is still there, listing and all.
    """
    store = tmp_path / "pending"
    _stash()(store=store, repo=repo, contract=contract, content=GOOD)

    real_rename = Path.rename

    def crash_on_staging(self: Path, target: Path) -> Path:
        if self.name.startswith(".staging-"):
            raise OSError("simulated crash while the replacement was being installed")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", crash_on_staging)

    with pytest.raises(PendingError):
        _stash()(store=store, repo=repo, contract=contract, content=NEWER)

    assert _holds_exactly(store, GOOD), (
        "the superseded entry was destroyed before its replacement existed; the "
        "work the store exists to protect is gone"
    )
    assert any(contract.id in str(e) for e in _listing()(store=store)), (
        "the superseded entry is no longer listed after a failed replacement"
    )
