"""D23 — work that passed the gate but could not be verified survives the process that
made it.

mcgyvr persists nothing about a task. The only artefact that outlives a run is the
index cache, which is a speed-up and not a record, so a task that reaches the last
step and cannot finish it — the verifier is unreachable, the key is missing, the API
is down — loses everything: the tokens spent, the gate that passed, and the file the
worker actually got right. The next run starts from the unchanged tree and pays for
the same answer again, and the operator has no way to see that this happened.

The store these tests describe is working state, not history. X02's telemetry says
what was attempted; this says what is still owed. The two are not interchangeable: a
record of a stranded attempt does not let you finish it.

Five statements, and the last three are the ones that make the store safe to rely on.

*Enough to resume it* is asserted as the exact bytes plus the contract, and the bytes
are compared for equality rather than for containing the change. A stash that
strips trailing whitespace, re-encodes, or appends a newline hands back something the
gate never saw, and re-verifying bytes nobody gated is worse than not stashing at
all — the verdict would be about a file that never existed. The contract has to be
there for the same reason: resuming re-runs the gate, and the gate is defined by the
contract's acceptance, target and scope.

*Resuming re-runs the gate* is asserted by resuming twice from the same store — once
from bytes that hold up and once from bytes that do not — with a verifier that
approves in both cases. A resume that trusted the earlier gate result would complete
both, and the broken file would land under an approval that was given for the
earlier, valid bytes. Time has passed since the stash was written; nothing about the
tree it lands on is still guaranteed.

**``GOOD`` had to change, and the reason is a defect this file was carrying.** It
was ``'def fetch(url):\n    return "café " + url  \n'`` — trailing spaces and a
non-ASCII byte, both of which a careless stash normalises away. The non-ASCII byte
stays, because it makes the statement. The trailing spaces had to go: the gate
rejects them (``format``: "formatter would reflow a worker-added line"), so no gate
run can produce that verdict about those bytes, and a test that resumed them to a
commit was pinning a state the system cannot reach — the pressure test's pattern D,
in the file whose own headline is that the bytes are the bytes. Byte-exactness is
still asserted, on the statement where it belongs: what the *store* holds is
compared for equality, including for content the gate would refuse, which is
:func:`test_the_store_keeps_bytes_the_gate_would_refuse` below.

*Still unverifiable leaves the stash intact* is the failure path, and it is where a
store like this normally leaks: clearing on the way out is one line and it is on the
path nobody exercises. If a failed re-verification consumed the entry, an outage that
lasted through one recovery run would destroy the work the store exists to protect.

*A newer attempt replaces the older stash* is asserted on the old bytes being gone
from the store entirely, not merely on the new bytes being findable. Two stashes for
one task means a later resume picks one by accident, and the one it picks is
whichever the filesystem happened to list first.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.red_port.conftest import git, required

STASH = (
    "stash gate-passed work that could not be verified, in a form that can resume it"
)
LIST = "list the work it is holding, so an operator can see what is owed"
RESUME = "resume stashed work once verification is reachable again"

# A non-ASCII byte a careless stash re-encodes away, in bytes a gate can accept —
# which the version with trailing whitespace could not be, see the module docstring.
GOOD = 'def fetch(url):\n    return "café " + url\n'
BROKEN = "def fetch(url:\n    return url\n"

# Byte-exactly what a careless stash would normalise, and byte-exactly what the
# gate's format rung refuses. It is stored, listed and restored; what it is not is
# committed, because nothing ever accepted it.
UNGATEABLE = 'def fetch(url):\n    return "café " + url  \n'


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


def _all_text(root: Path) -> str:
    """Everything the store holds, as one blob — the store's layout is its own "
    "business."""
    return "\n".join(
        path.read_bytes().decode("utf-8", "replace")
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )


def _holds_exactly(root: Path, content: str) -> bool:
    """True when some file under the store is byte-for-byte the given content."""
    return any(
        path.is_file() and path.read_bytes() == content.encode("utf-8")
        for path in sorted(root.rglob("*"))
    )


def test_unverifiable_work_is_stashed_with_the_bytes_and_the_contract(
    repo: Path, contract: Any, tmp_path: Path
) -> None:
    """What is stored is the file the gate saw, and the contract that defined the gate.

    Equality on the bytes, because "the change is in there somewhere" is satisfied by
    a reformatted copy, and a reformatted copy is a different file than the one that
    passed.
    """
    store = tmp_path / "pending"

    _stash()(store=store, repo=repo, contract=contract, content=GOOD)

    assert _holds_exactly(store, GOOD), (
        "the stash does not hold the accepted bytes exactly; what was gated and what "
        "would be resumed are not the same file"
    )
    held = _all_text(store)
    for needed in (contract.id, contract.target, contract.acceptance[0]):
        assert needed in held, (
            f"the stash does not carry {needed!r}, so a resume cannot re-run the gate "
            f"this work already passed"
        )


def test_the_stash_can_be_listed_and_names_the_task(
    repo: Path, contract: Any, tmp_path: Path
) -> None:
    """An operator has to be able to see what is owed without reading the store's files.

    Named by the task, not counted: "one item pending" tells nobody which run to
    re-drive or which contract to re-plan.
    """
    store = tmp_path / "pending"
    _stash()(store=store, repo=repo, contract=contract, content=GOOD)

    entries = list(_listing()(store=store))

    assert entries, "the stash reports nothing pending after work was stashed"
    assert any(contract.id in str(entry) for entry in entries), (
        f"nothing in the listing names {contract.id!r}: {entries}"
    )


def test_resuming_restores_the_exact_bytes_re_gates_them_and_finishes(
    repo: Path, contract: Any, tmp_path: Path
) -> None:
    """A resume is a fresh gate run over restored bytes, not a replay of an old verdict.

    Both halves use a verifier that approves. The good bytes must land; the broken
    ones must not, even though the verifier said yes — the earlier gate pass belonged
    to different bytes and to a tree that has since moved.
    """
    store = tmp_path / "pending"
    stash, resume = _stash(), _resume()
    target = repo / "src" / "pkg" / "fetch.py"
    shown: list[str] = []

    def approve(content: str) -> bool:
        shown.append(content)
        return True

    stash(store=store, repo=repo, contract=contract, content=GOOD)
    result = resume(store=store, repo=repo, task=contract.id, verify=approve)

    assert shown == [GOOD], (
        f"the verifier was not shown the stashed bytes, but {shown!r}"
    )
    assert target.read_text() == GOOD, (
        "the resumed file is not the file that was stashed"
    )
    assert getattr(result, "completed", False), (
        f"a verified resume did not complete: {result}"
    )
    assert not any(contract.id in str(e) for e in _listing()(store=store)), (
        "a completed task is still listed as pending"
    )

    git(repo, "checkout", "--", "src/pkg/fetch.py")
    before = target.read_text()
    stash(store=store, repo=repo, contract=contract, content=BROKEN)
    broken = resume(store=store, repo=repo, task=contract.id, verify=approve)

    assert not getattr(broken, "completed", False), (
        "an approving verifier completed a resume of bytes that do not parse: the gate "
        "was not re-run"
    )
    assert target.read_text() == before, (
        "bytes that failed the re-gate were left in the tree"
    )


def test_the_store_keeps_bytes_the_gate_would_refuse(
    repo: Path, contract: Any, tmp_path: Path
) -> None:
    """The bytes are the bytes — asserted where it is the store's own promise.

    ``UNGATEABLE`` carries the trailing whitespace the gate's ``format`` rung
    rejects. A stash that stripped it, re-encoded it or appended a newline would
    hand a recovery run a file that never existed, and the operator reading
    ``files/`` with ``cat`` would be reading a different change than the one that
    was stranded. So the store keeps it byte-for-byte.

    What the store does *not* do is turn keeping it into committing it: the same
    bytes, offered to an approving verifier, still do not reach the repository,
    because nothing ever accepted them. Both halves are asserted here, since it
    is the pair that is the property — a store that refused these bytes and a
    store that committed them are both wrong, in opposite directions.
    """
    store = tmp_path / "pending"
    head = git(repo, "rev-parse", "HEAD").strip()
    before = (repo / "src" / "pkg" / "fetch.py").read_text()

    _stash()(store=store, repo=repo, contract=contract, content=UNGATEABLE)

    assert _holds_exactly(store, UNGATEABLE), (
        "the store normalised the bytes it was given; a resume would restore a "
        "file the gate never saw"
    )

    result = _resume()(
        store=store, repo=repo, task=contract.id, verify=lambda _text: True
    )

    assert not getattr(result, "completed", False), (
        f"an approving verifier committed bytes the gate rejects: {result}"
    )
    assert git(repo, "rev-parse", "HEAD").strip() == head
    assert (repo / "src" / "pkg" / "fetch.py").read_text() == before
    assert _holds_exactly(store, UNGATEABLE), (
        "a refused resume consumed the work the store exists to protect"
    )


def test_work_that_still_cannot_be_verified_keeps_its_stash(
    repo: Path, contract: Any, tmp_path: Path
) -> None:
    """A recovery run that fails again must leave the work exactly where it found it.

    Asserted on both the listing and the bytes, because an entry that survives as an
    empty directory is a listing that lies.
    """
    store = tmp_path / "pending"
    _stash()(store=store, repo=repo, contract=contract, content=GOOD)

    def unreachable(content: str) -> bool:
        return False

    result = _resume()(store=store, repo=repo, task=contract.id, verify=unreachable)

    assert not getattr(result, "completed", False), (
        f"an unverified resume completed: {result}"
    )
    assert any(contract.id in str(e) for e in _listing()(store=store)), (
        "the stash was cleared by a resume that did not finish the work"
    )
    assert _holds_exactly(store, GOOD), (
        "the stashed bytes did not survive a failed resume"
    )


def test_a_newer_attempt_replaces_the_stash_it_supersedes(
    repo: Path, contract: Any, tmp_path: Path
) -> None:
    """One task, one pending entry — otherwise a resume picks its bytes by accident.

    The old bytes are asserted absent from the whole store, not just absent from the
    listing: a superseded copy left on disk is a second answer waiting to be resumed.
    """
    store = tmp_path / "pending"
    stash = _stash()
    # Never delivered, only stored and compared: trailing whitespace is exactly
    # what a careless stash normalises, which is what this asserts against.
    newer = 'def fetch(url):\n    return "café " + url.strip()  \n'

    stash(store=store, repo=repo, contract=contract, content=GOOD)
    stash(store=store, repo=repo, contract=contract, content=newer)

    named = [e for e in _listing()(store=store) if contract.id in str(e)]
    assert len(named) == 1, f"one task is listed {len(named)} times: {named}"
    assert _holds_exactly(store, newer), (
        "the newer attempt's bytes are not what is held"
    )
    assert not _holds_exactly(store, GOOD), (
        "the superseded attempt's bytes are still in the store, so which bytes "
        "a resume "
        ""
        ""
        ""
        ""
        ""
        ""
        "uses is decided by directory order"
    )
