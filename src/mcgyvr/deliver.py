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
present against the base, the path is still in scope, the bytes still parse, and
the bytes are still the ones the verdict was reached on. A drift since acceptance
fails at the commit point instead of shipping.

**A verdict is something delivery reaches, never something it is told.** The
first attempt at this bound the bytes and the verdict into one value and trusted
it — and the binding was minted from whatever the caller happened to be holding,
so a caller could assert an acceptance about bytes no gate had ever read and the
check agreed with it every time. So the floor here is not a check on a claim, it
is a gate run: before anything is staged, the change delivery is about to commit
is judged by :class:`~mcgyvr.gate.Gate` over the rungs that need no sandbox —
scope, secrets, structured data, syntax, structural hazards, lint and format —
in the repository it is landing in, over the bytes that are on disk at that
moment. Nothing a caller says can make un-judged bytes into a commit.

An :class:`Accepted` still travels, and it is still minted where the verdict was
reached (:meth:`Accepted.read`, which reads the bytes off the tree the gate
judged rather than taking them from a caller). What it carries that delivery
cannot re-establish is the *expensive* half of the verdict — the contract's
acceptance commands and semantic resolution, which need a sandbox this seam is
not given — and, through :mod:`mcgyvr.pending`, the identity of the bytes across
a store. It is a strictly additional refusal, never a licence to skip the gate
run: a rejected verdict refuses, and a self-consistent forged one still has to
survive the rungs delivery runs for itself.

Six refusals, each with a named reason, because a caller handed a falsy result
with no reason cannot tell "refused" from "nothing to do":

* **Not accepted, or a verdict that is not about these bytes.** The gate said no;
  nothing is written and nothing is reset, because nothing was touched. An
  :class:`Accepted` whose content no longer answers for its digest is refused in
  the same breath and for the same reason: a verdict that has come apart from its
  bytes is not a verdict about the change in hand — which is what happens when
  a store hands back bytes that are not the ones it was given.
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
* **Content that cannot be written.** A lone surrogate denotes no byte sequence,
  so there is nothing to commit; see :func:`_encoded` for why that is distinct
  from the surrogate *escapes* the rest of mcgyvr depends on.
* **Scope, a change the gate rejects, and bytes that are no longer the ones
  just judged.** The contract's own scope is re-confirmed, the change is put
  through the gate's sandbox-free rungs, and — last, immediately before git
  reads the file — the bytes on disk are checked to still be the bytes this call
  wrote. The style rungs are deliberately *included*: the earlier draft left
  them out on the grounds that re-litigating them would drop an accepted change
  over a trailing space, which is only true if an accepted change is what
  arrived. It is not checkable from here, and the premise is false anyway — the
  gate rejects on ``lint`` and ``format`` (they are findings, not observations),
  so bytes that passed a gate pass these too, and bytes that do not never
  passed one. The expensive rungs (acceptance commands, semantic resolution)
  need a sandbox delivery is not given, which is exactly the part an
  :class:`Accepted` carries in from where it could be run. What re-runs cheaply
  and catches what no rung could is *identity*: a substitution parses and lints,
  and only a comparison against the bytes just written can see it.

**What ships is one path (M3).** The diff is taken against the base the caller
passes — a revision of *this* repository, the one the task's worker started from
— not against the attach revision and not against whatever is lying in the tree,
and the commit names the contract's single target explicitly. A delivery that
staged everything would sweep a sibling contract's half-finished work into this
contract's commit — which is precisely the state the M3 test puts the tree in.

**Every path that does not commit puts the tree back.** local-ai reset the whole
workspace in a ``finally`` so no failed attempt could poison the next one; that
invariant is kept, narrowed to the bytes delivery itself wrote. mcgyvr's tree is
not exclusively delivery's — a ``git clean`` here would delete the very sibling
work M3 protects — so the undo is a byte-exact snapshot taken before the write
and restored after any non-committing exit, including a raised one.

**No process-global state (§9), and one exclusion that is not process state.**
Every fact a call needs is an argument or a local, and nothing is cached at
module scope. Two orchestrators delivering into two repositories at once is a
supported case today, so the v2 queue does not have to be built on a seam that
cannot be driven twice. Two delivering into *one* repository is a different
question with a different answer: the index and ``HEAD`` are one shared, locked
resource per work tree, and none of write-check-stage-commit-undo is atomic
against another call's — concurrent deliveries lost accepted changes outright,
and the ``finally`` that puts the tree back raised on the same contention while
it was undoing. So a delivery holds an exclusive ``flock`` on a file in the
repository's own git directory for the length of the call. That is state in the
repository rather than in the process, which is what keeps both properties: two
repositories still run at once, and two *processes* on one repository queue,
which a module-level lock could not have covered.

Extraction is not done here: a worker's reply becomes file content in
:mod:`mcgyvr.worker.reply`, and delivery is handed the content the gate actually
judged. Adding a trailing newline, re-encoding or reformatting on the way to disk
would ship bytes nobody gated, so the content is written verbatim.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import os
import subprocess
import textwrap
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from mcgyvr.config import Config
from mcgyvr.contract import Contract
from mcgyvr.gate.adapter import LanguageAdapter
from mcgyvr.gate.adapters import JavaScriptAdapter, PythonAdapter
from mcgyvr.gate.changeset import ChangeSet, ChangeSetError, FileChange
from mcgyvr.gate.findings import Finding
from mcgyvr.gate.runner import Gate, GateResult
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

#: The exclusion one delivery holds against another into the same repository,
#: kept inside the git directory rather than beside the target. The working
#: tree is the thing being protected: a lock file lying in it is untracked dirt
#: that a person's ``git clean`` would sweep up, and that every ``git status``
#: would show them.
_LOCK_NAME = "mcgyvr-delivery.lock"


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


@dataclass(frozen=True)
class Accepted:
    """The bytes a gate read, and the verdict it reached on them, as one value.

    The two used to travel apart — a ``str`` of content beside a ``bool`` — and
    nothing could tell whether they were still about each other. They stop being
    about each other whenever a step between the two mutates the *tree* instead
    of the string: :func:`mcgyvr.repair.repair` rewrites the worker's file in
    place, the gate is re-run on what is now on disk, and a caller still holding
    the reply it was handed then delivers bytes the gate rejected under a verdict
    reached on bytes it never saw. That is not hypothetical; it is the port's own
    documented repair loop, run as written.

    **The first fix for that bound the wrong two things.** Its constructor took
    the content from the caller and minted the digest from it, so every value
    the system could build answered for its own digest and the check was true by
    construction. The mint has to happen where the verdict does, from what the
    gate read — which is a *tree*, not a string a caller is holding. Hence
    :meth:`read`, which is handed the workspace the gate judged and takes the
    bytes from it; there is deliberately no constructor that accepts content and
    a verdict as two arguments, because that pair is the substitution itself.

    Even so, this value is a claim about somewhere else, and Python has no way
    to make a frozen dataclass unforgeable. It is therefore an *additional*
    refusal and never a licence: :func:`deliver` judges the bytes it is about to
    write whatever arrives here. What an :class:`Accepted` adds is the half of
    the verdict delivery cannot re-establish — the sandboxed rungs — and an
    identity that survives a round trip through :mod:`mcgyvr.pending`, which is
    the one place ``intact`` can actually come out false.
    """

    content: str
    accepted: bool
    digest: str

    findings: tuple[Finding, ...] = field(default=())
    """Why the gate refused, when it did — carried so a caller reporting a
    stranded attempt has the offending line rather than a bare ``False``."""

    @classmethod
    def read(
        cls,
        *,
        repo: Path | str | AttachedRepo,
        contract: Contract,
        result: GateResult,
    ) -> Accepted:
        """Bind ``result`` to the bytes on disk in the tree it was reached over.

        Called immediately after the gate run, in the workspace the gate ran in,
        and handed no content at all: the bytes come out of the tree the verdict
        is about. That is the whole difference from the version this replaces —
        a caller cannot offer the string it happens to be holding, because there
        is no parameter to offer it through.
        """
        root = _root(repo)
        rel = _target(root, contract)
        try:
            text = (root / rel).read_bytes().decode("utf-8", "surrogateescape")
        except OSError as exc:
            raise DeliveryError(
                f"{contract.id} was judged in {root} but {rel} is not there to bind "
                f"the verdict to: {exc}"
            ) from exc
        return cls(
            content=text,
            accepted=result.accepted,
            digest=digest_of(text),
            findings=tuple(result.findings),
        )

    @property
    def intact(self) -> bool:
        """Whether ``content`` is still what ``digest`` was taken from.

        Always true of a freshly :meth:`read` value, and that is not what it is
        for: it answers after the pair has been *carried* — stored, restored,
        rebuilt from a record — which is where the two can come apart without
        anybody rewriting either field.
        """
        return self.digest == digest_of(self.content)


def digest_of(content: str) -> str:
    """The identity of some content, as one hex digest.

    Public because a module minting an :class:`Accepted` and this one must not
    drift apart on how it is computed; a second, subtly different digest would
    make every verdict look substituted.

    ``surrogatepass`` here and ``surrogateescape`` in :func:`_encoded` are not an
    inconsistency: this names *the string*, and that names *the file*. The
    encoding is chosen because it is the one total over ``str`` — a verdict has
    to be expressible about content that delivery will go on to refuse to write,
    or the refusal could never be reported against a bound value.
    """
    return hashlib.sha256(content.encode("utf-8", "surrogatepass")).hexdigest()


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
    """The tree-ish the change was diffed against — a revision of *this*
    repository, the one the task's worker started from.

    Not a sandbox's :meth:`~mcgyvr.sandbox.Sandbox.base_changeset_ref`, which
    this field named until the pressure test tried it: that is the single commit
    of the fresh repository ``git init`` made inside that workspace, and resolves
    nowhere else, so supplying it here raised every time. The value a caller
    wants is :meth:`~mcgyvr.sandbox.Sandbox.source_base_commit` — the revision in
    the source repository that workspace was populated from, which is a revision
    delivery can diff against."""

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
    content: str | Accepted,
    base: str = "HEAD",
    accepted: bool | None = None,
    config: Config | None = None,
    identity: Identity = IDENTITY,
    adapters: Sequence[LanguageAdapter] | None = None,
) -> Delivery:
    """Commit ``content`` as ``contract.target``, or refuse and say why.

    ``base`` is the revision of *this* repository the task's worker started from
    — not the attach revision and not the current tree (M3). A sandbox names it
    :meth:`~mcgyvr.sandbox.Sandbox.source_base_commit`; its workspace's own base
    commit exists only inside that workspace and resolves nowhere here. What
    ships is the difference this task made, isolated from every other contract
    working in the same workspace.

    ``content`` is either an :class:`Accepted` — the bytes and the verdict bound
    together where the verdict was reached, which is what a caller that gated in
    a sandbox should carry back — or a bare ``str``, which carries no verdict at
    all. Neither is trusted on its own: delivery judges the change it is about to
    commit with the gate's sandbox-free rungs either way, in the repository the
    commit lands in. An :class:`Accepted` adds to that; it does not stand in for
    it.

    ``accepted`` may only say **no**. ``accepted=False`` is a caller that already
    knows the gate refused, and it saves delivery a gate run over bytes nobody
    wants committed. ``accepted=True`` raises: an acceptance nothing here can
    check is exactly the claim B6 was — a caller asserting a verdict about bytes
    no gate ever read. Contradicting a bound verdict raises for the same reason.

    ``adapters`` are the language adapters the commit-time gate run uses; the
    gate's own pair is the default. Nothing is shared between calls (§9); the one
    exclusion is per repository and held in the repository, so two deliveries
    into two repositories still run concurrently and two into one queue.

    Raises :class:`DeliveryError` when delivery cannot be attempted — a path that
    is not a repository, a base that is empty or does not resolve, a target that
    escapes the tree, a verdict asserted or contradicted at the call site. A
    change that is merely unacceptable comes back as a refusal instead.
    """
    root = _root(repo)
    rel = _target(root, contract)
    mode = _mode(config)
    text, refused, bound = _verdict(content, accepted)
    _named_base(base)

    with _exclusive(root):
        resolved = _resolve(root, base)
        call = _Call(path=rel, base=resolved, mode=mode)

        if refused:
            # Cheapest first, and nothing has been touched yet: a rejected change
            # never reaches the working tree at all, so there is nothing to undo.
            return call.refuse(
                f"the gate did not accept {contract.id}; nothing was written",
                bound.findings if bound is not None else (),
            )

        if bound is not None and not bound.intact:
            return call.refuse(
                f"the content handed to {contract.id} is not the content its "
                f"verdict was reached on: the accepted bytes digest to "
                f"{bound.digest[:12]} and these digest to "
                f"{digest_of(bound.content)[:12]}. Nothing is written, because "
                f"a verdict that has come apart from its bytes covers neither."
            )

        try:
            payload = _encoded(text)
        except UnicodeEncodeError as exc:
            return call.refuse(
                f"{rel} cannot be written: the character at position {exc.start} "
                f"is the lone surrogate U+{ord(text[exc.start]):04X}, which has no "
                f"UTF-8 encoding and stands for no byte. Writing it as anything "
                f"would ship bytes nobody gated."
            )

        dirty = _uncommitted(root, rel)
        if dirty:
            return call.refuse(
                f"the working tree is dirty ({_listed(dirty)}): delivering here "
                f"would commit the worker's change on top of unfinished edits, and "
                f"overwrite them on the way"
            )

        target = root / rel
        before = _snapshot(target)
        staged = False
        delivered = False
        try:
            _write(target, payload)

            change = _delivered_change(root, resolved, rel)
            if change is None:
                # Freshness, in local-ai's merge-gate sense: the accepted change
                # is no longer a change. Either the tree already holds it or the
                # base moved under the run, and committing now would report
                # success for work that is not in this commit.
                return call.refuse(
                    f"{rel} is identical to {_shown(resolved)}: the accepted change "
                    f"is no longer present, so there is nothing to commit"
                )

            if contract.scope.violations((rel,)):
                # Contract loading already rejects a target its own scope forbids;
                # this re-confirms it at the commit point, where the answer is
                # about a file that now exists rather than about a declaration.
                return call.refuse(
                    f"{rel} is outside the scope {contract.id} declares, so it may "
                    f"not be committed under it"
                )

            findings = _judged(change, root, resolved, adapters)
            if findings:
                return call.refuse(
                    f"{rel} does not pass the gate in {root.name}: {findings[0]}",
                    findings,
                )

            if _snapshot(target) != payload:
                # Identity, checked as late as this seam can check it. Between the
                # write above and git reading the file back sit several subprocess
                # round-trips, and a writer landing in that window substitutes
                # content no verdict covers — invisibly, because a substitution
                # parses and the style rungs are not re-run. The repository lock
                # excludes another delivery; this is what catches everything else.
                return call.refuse(
                    f"{rel} changed between the write and the commit: what is on "
                    f"disk is no longer the accepted content, and committing it "
                    f"would ship bytes no verdict covers"
                )

            _git(root, "add", "--", rel)
            staged = True
            sha = _commit(root, rel, _message(contract, resolved), identity)
            delivered = True
            return call.delivered(sha)
        finally:
            # The invariant ported from local-ai's apply: no attempt may poison
            # the next one, so every exit that is not a commit — a refusal or a
            # raised error — leaves the tree byte-for-byte as it was found.
            # Narrowed to what this call wrote, because a workspace-wide reset
            # would delete work delivery was never given. An undo that itself
            # fails raises out of here, over whatever was in flight: a tree we
            # could not put back is the one thing a caller must not be allowed to
            # miss. It runs inside the repository lock for the same reason the
            # commit does — an undo racing another call's staging is how the
            # concurrent case left the index holding bytes the tree did not.
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


def _verdict(
    content: str | Accepted, accepted: bool | None
) -> tuple[str, bool, Accepted | None]:
    """The bytes, whether a caller already refused them, and any bound verdict.

    The middle value is deliberately a *refusal* rather than an acceptance.
    Delivery reaches its own acceptance a few lines further down, over the bytes
    on disk; what it cannot reach on its own is "do not bother", and that is the
    only thing a caller is allowed to state here. ``accepted=True`` is the shape
    B6 travelled in — a verdict asserted about bytes nothing here can check —
    and it raises rather than being quietly ignored, because a call site that
    believes it is stating a verdict should find out that it is not.
    """
    if accepted is True:
        raise DeliveryError(
            "accepted=True asserts a verdict delivery cannot check: it says these "
            "bytes passed a gate, and nothing about this call can establish that "
            "any gate ever read them. Hand over the mcgyvr.deliver.Accepted the "
            "gate minted, or hand over the bytes and let delivery reach its own "
            "verdict on them"
        )
    if isinstance(content, Accepted):
        if accepted is not None and accepted != content.accepted:
            raise DeliveryError(
                f"the content carries a verdict of accepted={content.accepted} and "
                f"the call asserts accepted={accepted}; delivery does not choose "
                f"between two answers to one question"
            )
        return content.content, not content.accepted, content
    return content, accepted is False, None


@contextlib.contextmanager
def _exclusive(root: Path) -> Iterator[None]:
    """Hold this repository's delivery lock for the length of one call.

    Why it exists is in the module docstring; what it is, is a ``flock`` on a
    file in the repository's own git directory. Per repository rather than per
    process is the whole point — a module-level lock would serialise two
    orchestrators working on two different trees, which §9 says must not happen,
    and would still not serialise two *processes* on one tree, which is the case
    that corrupted it.

    Blocking rather than polling with a deadline, because there is nothing to
    time out against: the kernel drops a ``flock`` when the holding descriptor
    closes, so a crashed or killed delivery cannot strand the next one (the
    property :mod:`mcgyvr.capacity` leans on for its host-wide slots), and the
    only thing a waiter can be waiting for is a live delivery, which is bounded
    by its own work.
    """
    try:
        fd = os.open(_git_dir(root) / _LOCK_NAME, os.O_RDWR | os.O_CREAT, 0o600)
    except OSError as exc:
        raise DeliveryError(f"cannot take the delivery lock in {root}: {exc}") from exc
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)  # closing the descriptor is what releases the flock


def _git_dir(root: Path) -> Path:
    """The repository's git directory, asked of git rather than assumed.

    ``.git`` is a directory in a primary checkout and a *file* pointing
    elsewhere in a linked worktree. Asking gives the right answer for both, and
    the right granularity with it: the index and ``HEAD`` this call serialises
    against are per work tree, so two worktrees of one repository are two lock
    domains and may deliver at the same time.
    """
    return Path(_git(root, "rev-parse", "--absolute-git-dir").strip())


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


def _named_base(base: str) -> None:
    """Refuse a base that names nothing, before anything is touched.

    ``Sandbox.source_base_commit()`` used to answer ``""`` for a source with no
    revision to name, and ``_resolve`` treated any falsy base as ``HEAD`` — so
    the one value that means *there is no base* selected the one base that is a
    moving name. Measured: ``deliver(base="")`` committed against whatever the
    branch had got to, which is precisely what ``_source_commit``'s own
    docstring says it exists to prevent. The sandbox now refuses to hand back
    that value at all; this refuses it on arrival from anywhere else.
    """
    if not base.strip():
        raise DeliveryError(
            "delivery was given an empty base. A base is the revision the "
            "worker started from, and an empty one is not a request to diff "
            "against HEAD — HEAD is a moving name, and diffing against it "
            "ships whatever the branch has got to rather than this task's "
            "change. Pass Sandbox.source_base_commit(), or 'HEAD' explicitly"
        )


def _resolve(root: Path, base: str) -> str:
    """The base as a concrete tree-ish, softening only ``HEAD``.

    ``HEAD`` on a repository with no commit yet becomes the empty tree, so a
    first-ever delivery is diffed like any other. An explicit base that does not
    resolve is a caller error and fails loud where it is used — silently diffing
    against something else would ship a different change than the accepted one.
    An *empty* base is neither, and :func:`_named_base` has already refused it.
    """
    if base != "HEAD":
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


def _judged(
    change: FileChange,
    root: Path,
    base: str,
    adapters: Sequence[LanguageAdapter] | None,
) -> tuple[Finding, ...]:
    """Run the gate over this delivery's own change, here, now.

    This is the floor the whole module rests on: whatever a caller claims, these
    are the bytes about to become a commit, and this is a verdict on them rather
    than a verdict about them reported from elsewhere. Everything the gate can
    do without a sandbox runs — secrets and structured data from the aggregator,
    then syntax, structural hazards, lint and format from the adapters that own
    the path. A file no adapter owns is delivered unlinted, the same latitude
    the gate gives it.

    The change set handed over is narrowed to this one path on purpose. The
    whole diff against ``base`` is also holding whatever sibling contracts have
    left in the workspace (M3), and a delivery must not be refused because
    somebody else's half-finished file does not lint.

    ``Scope`` is not passed: the contract's scope is re-confirmed a few lines
    above, where the refusal can name the contract that forbids the path rather
    than arriving as one finding among several.
    """
    owners = tuple(adapters) if adapters is not None else _ADAPTERS()
    narrowed = ChangeSet(repo=root, base=base, files=(change,))
    return Gate(owners).run(narrowed).findings


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


def _encoded(content: str) -> bytes:
    """``content`` as the bytes that go on disk, raising if it has none.

    ``surrogateescape`` is the repository's convention (documented at
    :mod:`mcgyvr.pending`) and it is a convention about *bytes*: U+DC80..U+DCFF
    are how a byte that is not valid UTF-8 survives a decode, and they have to
    keep round-tripping — the pending store's entire claim is that the bytes it
    stashed are the bytes it resumes.

    A *lone* surrogate is a different animal and does not round-trip anything.
    ``\ud800`` is a legal JSON escape, so it survives ``json.loads`` into a
    completion and passes ``parse_reply`` as ordinary content, and it denotes no
    byte sequence at all. This raised straight out of delivery until the pressure
    test found it; the encoding is unchanged and the caller now answers the
    :class:`UnicodeEncodeError` with a refusal, because inventing bytes for it
    would ship a file nobody gated and no encoding of it is the accepted one.
    """
    return content.encode("utf-8", "surrogateescape")


def _write(path: Path, payload: bytes) -> None:
    """Write ``payload`` to ``path`` verbatim, creating parents as needed.

    Bytes, and no newline translation or trailing-newline fixup: the gate judged
    exactly these characters, and a delivery that normalised them would ship a
    file the gate never saw. (local-ai's apply appends a missing final newline;
    that is the one thing from it deliberately not ported.) Already encoded by
    the caller, so that content with no encoding at all is refused before
    anything on disk has been touched.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


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
