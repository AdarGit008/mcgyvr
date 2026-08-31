"""The pending store (D23) — gate-passed work that could not be verified, kept.

A task can reach the last step and fail to take it: the verifier is unreachable,
the key is missing, the API is down. Everything upstream of that moment was real
— the tokens were spent, the gate passed, the file is right — and mcgyvr persists
none of it. The next run starts from the unchanged tree and buys the same answer
again, and nobody can see that this happened.

So this is **working state, not history**. X02's telemetry records what was
attempted; this records what is still *owed*, which is a different question: a
record of a stranded attempt does not let you finish it. What makes an entry
finishable is what it carries — the exact bytes the gate saw, and the contract
that defined the gate — and four properties this module exists to hold:

* **The bytes are the bytes.** Stored and restored through
  ``bytes``/``surrogateescape``, never through a text round-trip that could strip
  a trailing space, re-encode, or add a final newline. Re-verifying bytes nobody
  gated is worse than not stashing at all: the verdict would be about a file that
  never existed. The contract is stored as :func:`mcgyvr.contract.dumps` JSON,
  which is the emitted form the loader round-trips — an entry that cannot be
  re-loaded into a contract is not resumable, and it is better to find that out
  when stashing than when recovering.
* **Resuming re-runs the gate.** :func:`resume` restores the bytes and hands the
  whole apply-check-commit decision to :func:`mcgyvr.deliver.deliver`, which
  judges them again against the tree they are landing in. The earlier gate pass
  belonged to different bytes and to a tree that has since moved; a verifier
  approving today does not make yesterday's tree true. This was the claim the
  module made and the code did not: ``resume`` handed over a bare ``str``, which
  delivery took as an acceptance, so a stub verifier was enough to commit bytes
  the gate had rejected. Delivery reaches its own verdict now, and what the store
  contributes is the half delivery cannot reach — the verdict from the sandboxed
  rungs, and the identity of the bytes it was reached on.
* **The verdict is stored with the bytes, or not at all.** :func:`stash` takes an
  :class:`mcgyvr.deliver.Accepted` from the caller that gated, records its digest
  and its verdict in ``meta.json``, and :func:`resume` rebuilds the pair from the
  entry. That is the one place ``Accepted.intact`` can come out false and mean
  something: the digest was minted in the workspace the gate ran in, the bytes
  come back off a directory anybody with a shell can edit, and a mismatch says
  the work that is about to be committed is not the work that was judged.
* **A failed recovery changes nothing.** The entry is removed only after a commit
  exists. Clearing on the way out is one line and it sits on the path nobody
  exercises, which is exactly how a store like this leaks: an outage lasting
  through one recovery run would destroy the work the store exists to protect.
* **One task, one entry.** A newer attempt replaces the older entry wholesale
  rather than sitting beside it, because two stashes for one task means a later
  resume picks its bytes by directory order.

The layout under ``<store>/<slug>/`` is deliberately readable by a person with
``cat``, since the operator reading it is usually mid-incident: ``contract.json``
(what defined the gate), ``files/<target>`` (the exact bytes), ``change.patch``
(what a reviewer or a verifier prompt wants to see), and ``meta.json`` (what is
owed, and when it was stranded). ``meta.json`` is written **last** and is what
:func:`listing` keys on, so a stash interrupted halfway is invisible rather than
half-resumable, and the new entry is built beside the old one and renamed over
it, so nothing is lost in the window between them.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import shutil
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from mcgyvr.config import Config
from mcgyvr.contract import Contract, ContractError
from mcgyvr.contract import dumps as dump_contract
from mcgyvr.contract import loads as load_contract
from mcgyvr.deliver import Accepted, Delivery, deliver

#: The contract, as the JSON the direct-mode API emits and the loader accepts.
CONTRACT_FILE = "contract.json"

#: Byte-exact copies of what was stashed, under their repository-relative paths.
#: Copies rather than a patch, for the reason local-ai gives: re-applying a
#: composite diff to a tree that has moved is a merge, and a merge is a new file
#: that no gate has seen. A copy either restores or it does not.
FILES = "files"

#: The change as a unified diff — for the operator, and for the verifier prompt a
#: recovery run rebuilds. Never the thing that is restored.
PATCH = "change.patch"

#: What is owed, and when. Written last: its presence is what makes an entry real.
META_FILE = "meta.json"

#: Characters an entry directory may carry. A *loaded* contract's id is already
#: this alphabet — :mod:`mcgyvr.contract` validates it — but :func:`resume` is
#: handed a task id as a bare string, from a CLI argument or a recovery script,
#: and ``store / task`` would then be a path an operator's typo (or an id read
#: out of an untrusted file) could steer. The id of record lives in
#: ``meta.json``, so the directory is free to be a slug.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")

#: Left by an interrupted stash and never listed. The new entry is assembled here
#: and renamed into place, so the superseded one survives until its replacement
#: is complete.
_STAGING = ".staging-"

#: Where the superseded entry waits while its replacement is renamed into place.
#: Dot-prefixed so :func:`listing` never mistakes it for a live entry. A crash
#: between the two renames leaves the old work here rather than destroying it.
_TOMBSTONE = ".tombstone-"


class PendingError(Exception):
    """The store could not be read or written.

    Raised rather than returned, and deliberately not used for "this task is not
    pending" — that is an answer :func:`resume` gives as a result. This is a
    store that is broken: an entry whose contract will not load, bytes that are
    gone, a directory that cannot be written.
    """


@dataclass(frozen=True)
class Pending:
    """One task's stranded work, as an operator sees it.

    Named by the task rather than counted, because "one item pending" tells
    nobody which run to re-drive or which contract to re-plan.
    """

    task: str
    target: str
    entry: Path
    repo: str
    stashed_at: str
    size: int
    reason: str = ""

    accepted: bool | None = None
    """The gate's verdict on the stashed bytes, when the caller carried one.

    ``None`` means the stash was handed a bare ``str`` and no verdict came with
    it — which is not the same as a rejection, and is why this is not a plain
    ``bool``: a resume that read ``False`` out of "nothing was recorded" would
    strand recoverable work forever."""

    digest: str = ""
    """The digest of the bytes the verdict was reached on, minted where it was
    reached. Empty for the same reason ``accepted`` is ``None``."""

    def __str__(self) -> str:
        why = f" — {self.reason}" if self.reason else ""
        return (
            f"{self.task}: {self.target} ({self.size} bytes) "
            f"stashed {self.stashed_at} from {self.repo}{why}"
        )


@dataclass(frozen=True)
class Resumed:
    """What a recovery run did with one stashed task.

    ``completed`` means, and only means, that a commit now exists: every other
    outcome leaves the entry exactly where it was found.
    """

    completed: bool
    task: str
    reason: str = ""
    delivery: Delivery | None = None

    def __str__(self) -> str:
        if self.completed:
            return f"resumed {self.task}: {self.delivery}"
        return f"{self.task} is still pending: {self.reason}"


def stash(
    *,
    store: Path | str,
    repo: Path | str,
    contract: Contract,
    content: str | Accepted,
    reason: str = "",
) -> Pending:
    """Snapshot gate-passed work that could not be verified, and return the entry.

    ``content`` is the accepted file exactly as the gate saw it — either the
    :class:`mcgyvr.deliver.Accepted` the gating caller minted, which carries the
    verdict and the digest of the bytes it was reached on, or a bare ``str``,
    which carries neither. Prefer the former: it is the only form that lets a
    recovery run tell "these are the bytes that were judged" from "these are the
    bytes that are in the directory now", and the store is a directory an
    operator is expected to read with ``cat`` mid-incident. ``reason`` is why
    verification could not happen — it is what the operator reads in
    :func:`listing`, so "verifier unreachable: connection refused" is worth more
    there than a bare timestamp.

    A newer attempt for the same task replaces the older entry outright; the
    replacement is assembled beside it and renamed over it, so an interrupted
    stash cannot leave the task with two sets of bytes or none.

    Raises :class:`PendingError` when the entry cannot be written, which
    includes content that has no byte form: ``surrogateescape`` round-trips the
    bytes a decode produced, and a lone ``\\ud800`` that only ever existed as a
    JSON escape is not one of them. That has to arrive as this module's error
    rather than as a codec exception, because a caller catching
    :class:`PendingError` is a caller that has decided what to do about work it
    cannot stash.
    """
    root = Path(store)
    rel = _relative(contract.target)
    entry = root / _slug(contract.id)
    staging = root / f"{_STAGING}{entry.name}"
    tombstone = root / f"{_TOMBSTONE}{entry.name}"
    bound = content if isinstance(content, Accepted) else None
    text = bound.content if bound is not None else str(content)

    try:
        # Inside the try, and the record is built here for one reason: `size`
        # is an encoded length, so building the record is already one of the
        # ways this function can fail on the bytes it was handed. Computing it
        # above the try put the first encode of the content outside the only
        # handler the module has.
        record = Pending(
            task=contract.id,
            target=rel,
            entry=entry,
            repo=str(Path(repo)),
            stashed_at=datetime.now(UTC).isoformat(timespec="seconds"),
            size=len(text.encode("utf-8", "surrogateescape")),
            reason=reason,
            accepted=bound.accepted if bound is not None else None,
            digest=bound.digest if bound is not None else "",
        )
        shutil.rmtree(staging, ignore_errors=True)
        (staging / FILES).mkdir(parents=True, exist_ok=True)
        # The contract is dumped through the loader's own emitted form and read
        # back immediately: a contract that will not round-trip cannot be
        # re-gated, and a recovery run is the wrong place to discover that.
        serialized = dump_contract(contract)
        _check_round_trip(serialized, contract.id)
        (staging / CONTRACT_FILE).write_text(serialized, encoding="utf-8")
        _write_exact(staging / FILES / rel, text)
        # The diff carries the same bytes the file does, so it is written the
        # same way. A strict text write here would refuse an entry whose stored
        # file was written without complaint — the store would hold resumable
        # bytes and raise on its way to the operator-facing copy of them.
        _write_exact(staging / PATCH, _patch(Path(repo) / rel, rel, text))
        # Last, always: meta.json is what listing keys on, so until it lands the
        # entry does not exist as far as any reader is concerned.
        (staging / META_FILE).write_text(_meta_json(record), encoding="utf-8")

        # The superseded entry is never destroyed before its replacement exists.
        # Park it at a tombstone, rename the new entry into place, and only then
        # clear the tombstone. A crash between the two renames strands the old
        # work under the tombstone path rather than deleting it.
        shutil.rmtree(tombstone, ignore_errors=True)
        if entry.exists():
            entry.rename(tombstone)
        staging.rename(entry)
        shutil.rmtree(tombstone, ignore_errors=True)
    except (OSError, UnicodeEncodeError) as exc:
        shutil.rmtree(staging, ignore_errors=True)
        # If the old entry was parked and the replacement never landed, put it
        # back: a stash that fails must not lose what it found there.
        if not entry.exists() and tombstone.exists():
            with suppress(OSError):
                tombstone.rename(entry)
        raise PendingError(f"cannot stash {contract.id} under {root}: {exc}") from exc
    return record


def listing(*, store: Path | str) -> tuple[Pending, ...]:
    """Everything the store is holding, ordered by task.

    Ordered so two runs of ``mcgyvr`` show the same list in the same order:
    directory order is whatever the filesystem happened to return, and an
    operator comparing today's list to yesterday's should not have to sort it
    themselves. A store that does not exist yet is holding nothing, which is not
    an error — it is the answer.
    """
    root = Path(store)
    if not root.is_dir():
        return ()
    entries: list[Pending] = []
    for child in root.iterdir():
        if not child.is_dir() or child.name.startswith("."):
            continue  # a staging directory is a stash still being written
        record = _read(child)
        if record is not None:
            entries.append(record)
    return tuple(sorted(entries, key=lambda record: record.task))


def resume(
    *,
    store: Path | str,
    repo: Path | str,
    task: str,
    verify: Callable[[str], bool],
    base: str = "HEAD",
    config: Config | None = None,
) -> Resumed:
    """Re-verify one stashed task and, if it holds up, finish it.

    ``verify`` is handed the stashed bytes verbatim — the same string the gate
    judged — and says whether verification approves them now. Approval is not the
    end of it, and this is the half that was missing: a verifier is a reviewer,
    not a gate, and ``resume`` used to turn its "yes" into delivery's *acceptance*
    by handing over a bare ``str``. Measured, that let a stub verifier commit
    bytes the gate had rejected. What goes to :func:`mcgyvr.deliver.deliver` now
    is the verdict the store recorded, bound to the bytes it was reached on, and
    delivery judges the restored bytes for itself besides. An approving verifier
    cannot commit a file that does not pass the gate, no longer parses, is out of
    scope, or would land on a dirty tree.

    Every outcome but a commit leaves the entry untouched, including a ``verify``
    that raises: an unreachable verifier is this store's *expected* failure, not
    an anomaly, and a recovery run that destroyed the work on its way out would
    defeat the store entirely.

    Raises :class:`PendingError` when the entry exists but cannot be read.
    """
    entry = Path(store) / _slug(task)
    record = _read(entry)
    if record is None:
        return Resumed(False, task=task, reason=f"nothing is pending for {task!r}")

    contract = _contract(entry, task)
    # ``record.target`` came out of meta.json, a plain file an operator can edit
    # or an entry can arrive carrying. Re-validate it before it becomes a path,
    # so a tampered target refuses the read instead of steering it out of the
    # entry.
    target = _relative(record.target)
    content = _read_exact(entry / FILES / target, task)

    try:
        approved = bool(verify(content))
    except Exception as exc:  # the verifier is a network call; failing is normal
        return Resumed(
            False, task=task, reason=f"verification is still unreachable: {exc}"
        )
    if not approved:
        return Resumed(
            False,
            task=task,
            reason="verification declined the stashed work; it stays pending",
        )

    result = deliver(
        repo=repo,
        contract=contract,
        content=_restored(record, content),
        base=base,
        config=config,
    )
    if not result.committed:
        return Resumed(False, task=task, reason=result.reason, delivery=result)

    # Only now: the work exists somewhere more durable than this directory.
    shutil.rmtree(entry, ignore_errors=True)
    return Resumed(True, task=task, delivery=result)


def _restored(record: Pending, content: str) -> str | Accepted:
    """The stashed bytes, rebound to the verdict the entry recorded.

    The rebuild is the point: the digest was minted in the workspace the gate ran
    in and written into ``meta.json``, and the content comes back off
    ``files/<target>`` — a plain file in a plain directory. Putting the two back
    together *without recomputing the digest* is what makes
    :attr:`~mcgyvr.deliver.Accepted.intact` answer a real question here, and the
    only place in the codebase where it can come out false: an entry whose bytes
    were edited after they were judged is refused at the commit point instead of
    being delivered as though the gate had seen them.

    An entry with no recorded verdict is handed over as the bare string it always
    was. That is not a downgrade — delivery gates what it commits either way —
    it just carries nothing extra.
    """
    if not record.digest:
        return content
    return Accepted(
        content=content,
        accepted=bool(record.accepted),
        digest=record.digest,
    )


def _slug(task: str) -> str:
    """A directory name for a task id, one-to-one with the id.

    A contract's own id is already a safe filename and is used as-is, so the
    store reads as the task list it is. Anything else — which is to say, whatever
    :func:`resume` was handed — keeps a recognisable stem and carries a digest of
    the original: that is what stops two different ids from colliding on one
    entry, and what makes the same id map to the same entry every time, so a
    newer attempt replaces its predecessor instead of joining it.
    """
    cleaned = _UNSAFE.sub("-", task.strip()).strip("-.")
    if cleaned == task and cleaned not in ("", ".", ".."):
        return cleaned
    digest = hashlib.sha256(task.encode("utf-8", "surrogateescape")).hexdigest()[:8]
    return f"{cleaned or 'task'}-{digest}"


def _relative(target: str) -> str:
    """The contract's target as a path that cannot escape the store or the repo."""
    named = target.strip()
    path = PurePosixPath(named)
    if not named or path.is_absolute() or ".." in path.parts:
        raise PendingError(f"{target!r} is not a repository-relative target path")
    return path.as_posix()


def _write_exact(path: Path, content: str) -> None:
    """Write ``content`` with no translation of any kind.

    ``write_bytes`` rather than ``write_text``: a text write encodes with the
    platform's preferences and translates line endings, and either would hand a
    resume a file the gate never saw. It also encodes under ``strict``, which
    refuses the ``surrogateescape`` characters that are how every byte the tree
    could not decode got into a ``str`` in the first place.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8", "surrogateescape"))


def _read_exact(path: Path, task: str) -> str:
    """The stashed bytes back, decoded the way they were encoded.

    ``surrogateescape`` on both sides makes the round trip total: a file that is
    not valid UTF-8 still comes back byte-identical rather than raising or being
    silently repaired.
    """
    try:
        return path.read_bytes().decode("utf-8", "surrogateescape")
    except OSError as exc:
        raise PendingError(
            f"{task} is listed as pending but its bytes are gone ({path}): {exc}"
        ) from exc


def _patch(current: Path, rel: str, content: str) -> str:
    """The stashed change as a unified diff against what the tree holds now.

    For reading, never for applying — :data:`FILES` is what a resume restores.
    Generated in-process rather than by shelling out to git, because the file
    being diffed is not in any index and a stash must not touch the repository it
    is rescuing work from.
    """
    try:
        before = current.read_bytes().decode("utf-8", "surrogateescape")
    except OSError:
        before = ""  # a new file: the whole content is the diff
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            content.splitlines(keepends=True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
        )
    )


def _meta_json(record: Pending) -> str:
    """The operator-facing half of an entry, as JSON.

    JSON rather than YAML for the acceptance commands' sake: they are shell, full
    of quotes, and JSON escapes only the two characters that cannot appear raw. A
    YAML emitter may re-quote a command into something that no longer reads back
    as the command that was run.
    """
    return json.dumps(
        {
            "task": record.task,
            "target": record.target,
            "repo": record.repo,
            "stashed_at": record.stashed_at,
            "size": record.size,
            "reason": record.reason,
            # Both null when the stash was handed a bare string: an absent
            # verdict has to read as absent rather than as a rejection, or a
            # resume would strand work nobody ever refused.
            "accepted": record.accepted,
            "digest": record.digest,
        },
        indent=2,
        ensure_ascii=False,
    )


def _read(entry: Path) -> Pending | None:
    """One entry as a :class:`Pending`, or None when the directory is not one.

    None rather than an exception: a directory without ``meta.json`` is a stash
    that was interrupted before it became real, and a listing that raised on one
    would hide every entry beside it.
    """
    meta = entry / META_FILE
    try:
        raw: Any = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, Mapping):
        return None
    verdict = raw.get("accepted")
    return Pending(
        task=str(raw.get("task", entry.name)),
        target=str(raw.get("target", "")),
        entry=entry,
        repo=str(raw.get("repo", "")),
        stashed_at=str(raw.get("stashed_at", "")),
        size=int(raw.get("size", 0)),
        reason=str(raw.get("reason", "")),
        # An entry written before the verdict was recorded, or by a caller that
        # carried none, reads back as "no verdict" rather than as False.
        accepted=None if verdict is None else bool(verdict),
        digest=str(raw.get("digest", "") or ""),
    )


def _contract(entry: Path, task: str) -> Contract:
    """The contract that defined the gate this work already passed.

    Re-validated through the loader on the way out, not trusted as data: a resume
    re-runs the gate, and the gate is the contract's acceptance, target and scope.
    """
    try:
        return load_contract((entry / CONTRACT_FILE).read_text(encoding="utf-8"))
    except OSError as exc:
        raise PendingError(f"{task} is pending but carries no contract: {exc}") from exc
    except ContractError as exc:
        raise PendingError(
            f"{task}'s stashed contract no longer loads, so the gate it passed "
            f"cannot be re-run: {exc}"
        ) from exc


def _check_round_trip(serialized: str, task: str) -> None:
    """Refuse to stash a contract that will not come back."""
    try:
        load_contract(serialized)
    except ContractError as exc:
        raise PendingError(
            f"{task}'s contract does not round-trip, so a resume could not re-gate "
            f"its work: {exc}"
        ) from exc
