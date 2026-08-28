"""Delivery (E8) — an accepted change becomes a commit, or nothing at all.

Everything upstream of this module produces an opinion: the ladder picks a rung,
the worker writes a file, the gate judges it. Nothing writes that judgement into
the repository the run was pointed at. This is where a library of seams becomes
something that finishes a task, and it is the one place in mcgyvr that mutates a
tree a human owns — so most of what follows is about the mutations it refuses to
make.

**Acceptance and commit are two different moments.** local-ai learned this as its
merge gate (``merge.py``): between the verdict and the commit, another task
committed, a reset ran, or a person saved a file. So the verdict is not replayed
here, it is re-established against the tree as it is *now* — the change is still
present against the base, the path is still in scope, the bytes still parse. A
drift since acceptance fails at the commit point instead of shipping.

Four refusals, each with a named reason, because a caller handed a falsy result
with no reason cannot tell "refused" from "nothing to do":

* **Not accepted.** The gate said no; nothing is written and nothing is reset,
  because nothing was touched.
* **A dirty tree (M2).** Uncommitted work in the tree means a commit here would
  mix the worker's change with a person's unfinished edits, and the write would
  destroy them on the way. mcgyvr reports a dirty tree and stops — the same
  stance :func:`mcgyvr.gate.preflight.check_clean_tree` takes before a run, taken
  again at its end. Untracked *siblings* are not dirt: another contract's
  in-flight work in the same workspace is exactly what M3 keeps out of this
  commit, so it does not need to block it too.
* **The change vanished.** Content identical to what the base already holds is
  not a delivery; committing an empty change would report success for work that
  is no longer there.
* **Scope, and bytes that no longer parse.** The contract's own scope is
  re-confirmed, and the delivered file is re-parsed with the gate's language
  adapters. The gate's *style* rungs (lint, format) are deliberately not re-run:
  they already gave their verdict on these exact bytes, and re-litigating it here
  would drop an accepted change at the commit point over a trailing space. The
  expensive rungs (acceptance commands, semantic resolution) need a sandbox
  delivery is not given; re-running those is the caller's move, not this seam's.

**What ships is one path (M3).** The diff is taken against the *sandbox base
commit* the caller passes, not against the attach revision and not against
whatever is lying in the tree, and the commit names the contract's single target
explicitly. A delivery that staged everything would sweep a sibling contract's
half-finished work into this contract's commit — which is precisely the state the
M3 test puts the tree in.

**Every path that does not commit puts the tree back.** local-ai reset the whole
workspace in a ``finally`` so no failed attempt could poison the next one; that
invariant is kept, narrowed to the bytes delivery itself wrote. mcgyvr's tree is
not exclusively delivery's — a ``git clean`` here would delete the very sibling
work M3 protects — so the undo is a byte-exact snapshot taken before the write
and restored after any non-committing exit, including a raised one.

**No process-global state (§9).** Every fact a call needs is an argument or a
local; nothing is cached at module scope and no lock is held. Two orchestrators
delivering into two repositories at once is a supported case today, so the v2
queue does not have to be built on a seam that cannot be driven twice.

Extraction is not done here: a worker's reply becomes file content in
:mod:`mcgyvr.worker.reply`, and delivery is handed the content the gate actually
judged. Adding a trailing newline, re-encoding or reformatting on the way to disk
would ship bytes nobody gated, so the content is written verbatim.
"""

from __future__ import annotations

import subprocess
import textwrap
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from mcgyvr.config import Config
from mcgyvr.contract import Contract
from mcgyvr.gate.adapter import LanguageAdapter
from mcgyvr.gate.adapters import JavaScriptAdapter, PythonAdapter
from mcgyvr.gate.changeset import ChangeSet, ChangeSetError, FileChange
from mcgyvr.gate.findings import Finding
from mcgyvr.orchestrator.repo import AttachedRepo

# The well-known SHA-1 of git's empty tree, and the same sentinel
# :mod:`mcgyvr.gate.changeset` and :mod:`mcgyvr.orchestrator.repo` use: a
# repository with no commit yet has no base to diff against, and the empty tree
# makes a first-ever delivery one code path with every other.
_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

#: The ``config.delivery.mode`` value a commit alone completes — and the
#: assumption when no config is supplied, since a delivery with nothing to hand
#: back to is a local commit.
COMMIT_ONLY = "none"

#: The modes whose handback is *not* finished by a commit. All three modes begin
#: with the commit this module makes; ``branch`` then pushes it and
#: ``pull_request`` also proposes it, both of which need a forge and the
#: credential named by ``delivery.token_env``. Delivery never pushes as a side
#: effect of committing, so those two are recorded on the result as still owed.
_FORGE_MODES = frozenset({"branch", "pull_request"})


@dataclass(frozen=True)
class Identity:
    """Who a delivery commit is authored by.

    Injected on the command line (``git -c user.name=…``) rather than written
    into the repository's config, for the reason local-ai found the hard way: a
    workspace with no ``user.name``/``user.email`` bound would otherwise fail the
    commit, and delivery must not fall over on a machine's git settings — nor
    quietly change them.
    """

    name: str
    email: str


#: The default author. A ``.invalid`` domain (RFC 2606) is deliberate: the commit
#: was made by a program, and no mailbox should be implied for it.
IDENTITY = Identity("mcgyvr", "delivery@mcgyvr.invalid")


class DeliveryError(Exception):
    """Delivery could not be attempted at all.

    Distinct from a refusal on purpose. A :class:`Delivery` with
    ``committed=False`` is an answer — the change was judged and declined. This
    is raised when there is no question to answer: the path is not a repository,
    the base does not resolve, the target escapes the tree, git itself failed.
    """


@dataclass(frozen=True)
class Delivery:
    """What delivery did, and — when it did nothing — why.

    ``reason`` is always populated on a refusal and always empty on a commit, so
    a caller can log one field either way without branching first.
    """

    committed: bool
    reason: str = ""

    commit: str = ""
    """The delivered commit's SHA, empty when nothing was committed."""

    path: str = ""
    """The single repository-relative path this delivery shipped (M3)."""

    base: str = ""
    """The tree-ish the change was diffed against — the sandbox base commit."""

    mode: str = COMMIT_ONLY
    """The ``config.delivery.mode`` this ran under."""

    handoff: str = ""
    """What the mode still owes this commit: empty when a local commit is the
    whole handback, otherwise the mode's name. ``branch`` has to be pushed and
    ``pull_request`` pushed and proposed; both need a forge and the credential
    named by ``delivery.token_env``, and delivery does not push silently."""

    findings: tuple[Finding, ...] = field(default=())
    """Why a re-check refused, when one did — carried structurally so a caller
    can report the offending line rather than re-derive it from ``reason``."""

    def __str__(self) -> str:
        if self.committed:
            owed = f", {self.handoff} still owed" if self.handoff else ""
            return f"delivered {self.path} as {self.commit[:12]}{owed}"
        return f"not delivered: {self.reason}"


def deliver(
    *,
    repo: Path | str | AttachedRepo,
    contract: Contract,
    content: str,
    base: str = "HEAD",
    accepted: bool = True,
    config: Config | None = None,
    identity: Identity = IDENTITY,
    adapters: Sequence[LanguageAdapter] | None = None,
) -> Delivery:
    """Commit ``content`` as ``contract.target``, or refuse and say why.

    ``base`` is the *sandbox base commit* — the revision this task's worker
    started from — not the attach revision and not the current tree (M3). What
    ships is the difference this task made, isolated from every other contract
    working in the same workspace.

    ``accepted`` is the gate's verdict, re-asked here rather than assumed:
    delivery is the one caller that can turn a verdict into a permanent change,
    so it does not take "it must have passed, or you would not have called me".

    ``adapters`` supply the parse that re-confirms the delivered bytes; the
    gate's own pair is the default. Nothing here is shared between calls, so two
    deliveries into two repositories may run concurrently (§9).

    Raises :class:`DeliveryError` when delivery cannot be attempted — a path that
    is not a repository, a base that does not resolve, a target that escapes the
    tree. A change that is merely unacceptable comes back as a refusal instead.
    """
    root = _root(repo)
    rel = _target(root, contract)
    resolved = _resolve(root, base)
    mode = _mode(config)
    call = _Call(path=rel, base=resolved, mode=mode)

    if not accepted:
        # Cheapest first, and nothing has been touched yet: a rejected change
        # never reaches the working tree at all, so there is nothing to undo.
        return call.refuse(
            f"the gate did not accept {contract.id}; nothing was written"
        )

    dirty = _uncommitted(root, rel)
    if dirty:
        return call.refuse(
            f"the working tree is dirty ({_listed(dirty)}): delivering here would "
            f"commit the worker's change on top of unfinished edits, and overwrite "
            f"them on the way"
        )

    target = root / rel
    before = _snapshot(target)
    staged = False
    delivered = False
    try:
        _write(target, content)

        change = _delivered_change(root, resolved, rel)
        if change is None:
            # Freshness, in local-ai's merge-gate sense: the accepted change is
            # no longer a change. Either the tree already holds it or the base
            # moved under the run, and committing now would report success for
            # work that is not in this commit.
            return call.refuse(
                f"{rel} is identical to {_shown(resolved)}: the accepted change is "
                f"no longer present, so there is nothing to commit"
            )

        if contract.scope.violations((rel,)):
            # Contract loading already rejects a target its own scope forbids;
            # this re-confirms it at the commit point, where the answer is about
            # a file that now exists rather than about a declaration.
            return call.refuse(
                f"{rel} is outside the scope {contract.id} declares, so it may not "
                f"be committed under it"
            )

        findings = _parses(change, root, adapters)
        if findings:
            return call.refuse(f"{rel} no longer parses: {findings[0]}", findings)

        _git(root, "add", "--", rel)
        staged = True
        sha = _commit(root, rel, _message(contract, resolved), identity)
        delivered = True
        return call.delivered(sha)
    finally:
        # The invariant ported from local-ai's apply: no attempt may poison the
        # next one, so every exit that is not a commit — a refusal or a raised
        # error — leaves the tree byte-for-byte as it was found. Narrowed to what
        # this call wrote, because a workspace-wide reset would delete work
        # delivery was never given. An undo that itself fails raises out of here,
        # over whatever was in flight: a tree we could not put back is the one
        # thing a caller must not be allowed to miss.
        if not delivered:
            _restore(target, before)
            if staged:
                _git(root, "reset", "--quiet", "--", rel)


@dataclass(frozen=True)
class _Call:
    """The facts every outcome of one delivery carries, whichever way it ends.

    A per-call value rather than a module-level context: two deliveries running
    at once (§9) each hold their own, and a refusal is then one line at the point
    the decision is made instead of a six-field constructor repeated five times.
    """

    path: str
    base: str
    mode: str

    @property
    def handoff(self) -> str:
        return self.mode if self.mode in _FORGE_MODES else ""

    def refuse(self, reason: str, findings: Sequence[Finding] = ()) -> Delivery:
        return Delivery(
            committed=False,
            reason=reason,
            path=self.path,
            base=self.base,
            mode=self.mode,
            handoff=self.handoff,
            findings=tuple(findings),
        )

    def delivered(self, sha: str) -> Delivery:
        return Delivery(
            committed=True,
            commit=sha,
            path=self.path,
            base=self.base,
            mode=self.mode,
            handoff=self.handoff,
        )


def _root(repo: Path | str | AttachedRepo) -> Path:
    """The repository root, whether attach's result or a bare path was passed.

    Accepting :class:`~mcgyvr.orchestrator.repo.AttachedRepo` means the caller
    that attached does not have to unwrap it. The tree's *state*, though, is read
    fresh below rather than taken from attach's snapshot: attach happened before
    the run, and this decision is about the tree the commit lands in.
    """
    root = repo.root if isinstance(repo, AttachedRepo) else Path(repo)
    if not (root / ".git").exists():
        raise DeliveryError(f"{root} is not a git repository; nothing can be delivered")
    return root


def _mode(config: Config | None) -> str:
    """``config.delivery.mode``, or a local commit when there is no config."""
    if config is None:
        return COMMIT_ONLY
    return str(config.get("delivery.mode", COMMIT_ONLY) or COMMIT_ONLY)


def _target(root: Path, contract: Contract) -> str:
    """The contract's single target as a repository-relative path.

    A target that escapes the repository is refused loudly rather than written:
    the contract's single-target discipline says where the worker's output goes,
    and "anywhere on this machine" is not one of the answers.
    """
    named = contract.target.strip()
    if not named:
        raise DeliveryError(f"{contract.id} names no target to deliver")
    anchor = root.resolve()
    resolved = (anchor / named).resolve()
    if anchor not in resolved.parents:
        raise DeliveryError(
            f"{contract.id} targets {named!r}, which is outside the repository"
        )
    return resolved.relative_to(anchor).as_posix()


def _resolve(root: Path, base: str) -> str:
    """The base as a concrete tree-ish, softening only ``HEAD``.

    ``HEAD`` on a repository with no commit yet becomes the empty tree, so a
    first-ever delivery is diffed like any other. An explicit base that does not
    resolve is a caller error and fails loud where it is used — silently diffing
    against something else would ship a different change than the accepted one.
    """
    if base and base != "HEAD":
        return base
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "HEAD^{commit}"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    revision = proc.stdout.strip()
    return revision if proc.returncode == 0 and revision else _EMPTY_TREE


def _uncommitted(root: Path, rel: str) -> tuple[str, ...]:
    """Paths that make this tree unsafe to commit into (M2).

    Two kinds, and the line between them is the one M2 and M3 draw together:

    * a **tracked** file with uncommitted changes — a person's unfinished edit,
      which a delivery would mix into its commit or overwrite outright;
    * the **target itself when it is untracked** — unversioned content the write
      would destroy with no way back.

    An untracked file that is not the target is neither: it is what M3 calls
    another contract's work in the same workspace, and since delivery commits
    exactly one named path it cannot ride along.
    """
    unsafe = list(_modified(root))
    if (root / rel).exists() and not _tracked(root, rel):
        unsafe.append(rel)
    return tuple(dict.fromkeys(unsafe))


def _modified(root: Path) -> tuple[str, ...]:
    """Tracked paths differing from HEAD or the index, in git's report order.

    ``-z`` keeps a filename with spaces or non-ASCII bytes verbatim instead of
    quoted, the same hazard :mod:`mcgyvr.gate.changeset` guards against; a rename
    record carries its origin path as an extra token, which is skipped.
    """
    tokens = _git_bytes(
        root, "status", "--porcelain", "-z", "--untracked-files=no"
    ).split(b"\x00")
    paths: list[str] = []
    i = 0
    while i < len(tokens):
        record = tokens[i]
        if not record:  # the trailing NUL leaves an empty final token
            break
        paths.append(record[3:].decode("utf-8", "surrogateescape"))
        i += 2 if record[:1] in (b"R", b"C") else 1
    return tuple(paths)


def _tracked(root: Path, rel: str) -> bool:
    """Whether git knows this path at all."""
    return bool(_git(root, "ls-files", "--", rel).strip())


def _delivered_change(root: Path, base: str, rel: str) -> FileChange | None:
    """This delivery's own file within the whole change against ``base``.

    Reusing :class:`~mcgyvr.gate.changeset.ChangeSet` is not only economy: it is
    what makes "delivered" and "gated" the same notion of a change. It stages
    into a throwaway index, so an untracked new target is seen as added and the
    repository's real index is never touched — and everything else it finds is
    the sibling work M3 says must not ride along, which is why only one path is
    picked out of it.
    """
    try:
        changed = ChangeSet.detect(root, base)
    except ChangeSetError as exc:
        raise DeliveryError(f"cannot diff against {_shown(base)}: {exc}") from exc
    return next((change for change in changed if change.path == rel), None)


def _parses(
    change: FileChange, root: Path, adapters: Sequence[LanguageAdapter] | None
) -> list[Finding]:
    """Re-parse the delivered file with whichever adapter owns it.

    The cheapest and most decisive of the gate's rungs, and the only one worth
    repeating at the commit point: it costs no subprocess (that is the adapter
    interface's own rule for ``check_syntax``) and it catches the drift that
    makes a commit actively harmful — bytes that no longer compile. A file no
    adapter owns is delivered unparsed, the same latitude the gate gives it.
    """
    owners = adapters if adapters is not None else _ADAPTERS()
    findings: list[Finding] = []
    for adapter in owners:
        if adapter.owns(change.path):
            findings.extend(adapter.check_syntax(change, root))
    return findings


def _ADAPTERS() -> tuple[LanguageAdapter, ...]:  # noqa: N802 — a default, not a class
    """The gate's own adapter pair, built per call.

    Constructed rather than shared at module scope so delivery holds no global
    state (§9); adapters are cheap and stateless, so this costs nothing.
    """
    return (PythonAdapter(), JavaScriptAdapter())


def _snapshot(path: Path) -> bytes | None:
    """The file's exact bytes before delivery writes, or None if it is absent.

    Bytes rather than a git operation on purpose: the undo has to restore what
    was *in the tree*, which is not necessarily what any commit or index holds.
    """
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _write(path: Path, content: str) -> None:
    """Write ``content`` to ``path`` verbatim, creating parents as needed.

    Bytes, and no newline translation or trailing-newline fixup: the gate judged
    exactly these characters, and a delivery that normalised them would ship a
    file the gate never saw. (local-ai's apply appends a missing final newline;
    that is the one thing from it deliberately not ported.)
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8", "surrogateescape"))


def _restore(path: Path, before: bytes | None) -> None:
    """Put the file back exactly as it was found, or remove one we created."""
    if before is None:
        path.unlink(missing_ok=True)
    else:
        path.write_bytes(before)


def _commit(root: Path, rel: str, message: str, identity: Identity) -> str:
    """Commit exactly ``rel`` and return the new SHA.

    The pathspec is what keeps M3 true: a bare ``git commit`` would take whatever
    else the caller had staged and ``-a`` would take the whole tree, while naming
    the path commits this contract's file and leaves everyone else's work —
    staged, unstaged or untracked — exactly where it was.
    """
    _git(
        root,
        "-c",
        f"user.name={identity.name}",
        "-c",
        f"user.email={identity.email}",
        "commit",
        "--quiet",
        "--message",
        message,
        "--",
        rel,
    )
    return _git(root, "rev-parse", "HEAD").strip()


def _message(contract: Contract, base: str) -> str:
    """A commit message naming the contract, its target and its base.

    The base is in the trailer because a delivery is only meaningful against one:
    a reader asking "what did this task actually change" needs the revision the
    diff was taken from, and the branch it landed on may have moved since.
    """
    subject = textwrap.shorten(
        f"{contract.id}: {' '.join(contract.task.split())}",
        width=72,
        placeholder="...",
    )
    return (
        f"{subject}\n\n"
        f"Contract: {contract.id}\n"
        f"Target: {contract.target}\n"
        f"Base: {_shown(base)}\n"
    )


def _shown(base: str) -> str:
    """A base rendered for a human: the empty tree said in words."""
    return "the empty tree" if base == _EMPTY_TREE else base


def _listed(paths: Sequence[str]) -> str:
    """The first few offending paths, with a count standing in for the rest."""
    shown = ", ".join(paths[:5])
    return shown if len(paths) <= 5 else f"{shown} (+{len(paths) - 5} more)"


def _git(root: Path, *args: str) -> str:
    """Run git in ``root``, returning stdout, raising with git's own complaint."""
    return _git_bytes(root, *args).decode("utf-8", "surrogateescape")


def _git_bytes(root: Path, *args: str) -> bytes:
    """The bytes form: path output is only safely decoded after splitting on NUL."""
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True)
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise DeliveryError(f"git {args[0]} failed in {root}: {detail}")
    return proc.stdout
