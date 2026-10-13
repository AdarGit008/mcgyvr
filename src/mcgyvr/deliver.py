"""Delivery — an accepted change becomes a commit, or nothing at all.

Everything upstream of this module produces an opinion: the ladder picks a rung,
the worker writes a file, the gate judges it. Nothing writes that judgement into
the repository the run was pointed at. This is where a library of seams becomes
something that finishes a task, and it is the one place in mcgyvr that mutates a
tree a human owns — so most of what follows is about the mutations it refuses to
make.

**Acceptance and commit are two different moments.** Between the verdict and the
commit, another task may commit, a reset may run, or a person may save a file.
So the verdict is not replayed here, it is re-established against the tree as it
is *now* — the change is still present against the base, the path is still in
scope, the bytes still parse, and the bytes are still the ones the verdict was
reached on. A drift since acceptance fails at the commit point instead of
shipping.

**A verdict is something delivery reaches, never something it is told.** The
floor here is not a check on a claim, it is a gate run: before anything is
staged, the change delivery is about to commit is judged by
:class:`~mcgyvr.gate.Gate` over the rungs that need no sandbox — scope, secrets,
structured data, syntax, structural hazards, lint and format — in the repository
it is landing in, over the bytes that are on disk at that moment. Nothing a
caller says can make un-judged bytes into a commit.

An :class:`Accepted` still travels, and it is still minted where the verdict was
reached (:meth:`Accepted.read`, which reads the bytes off the tree the gate
judged rather than taking them from a caller). What it carries that delivery
cannot re-establish is the *expensive* half of the verdict — the contract's
acceptance commands and semantic resolution, which need a sandbox this seam is
not given — and the identity of the bytes across a store. It is a strictly
additional refusal, never a licence to skip the gate run: a rejected verdict
refuses, and a self-consistent forged one still has to survive the rungs
delivery runs for itself.

The refusals, each with a named reason, because a caller handed a falsy result
with no reason cannot tell "refused" from "nothing to do":

* **A checkout a commit would be lost in.** A detached ``HEAD``, or a rebase,
  merge, cherry-pick or bisect left partway through (:func:`_checkout_hazard`).
* **Not accepted, or a verdict that is not about these bytes.** The gate said no;
  nothing is written and nothing is reset, because nothing was touched. An
  :class:`Accepted` whose content no longer answers for its digest is refused in
  the same breath and for the same reason: a verdict that has come apart from its
  bytes is not a verdict about the change in hand — which is what happens when
  a store hands back bytes that are not the ones it was given.
* **A target committed to since the base.** The verdict is about the copy of
  the file at the base; a commit to it while the run climbed is work the
  accepted bytes were never judged against, and writing them would revert it.
* **A dirty tree.** Uncommitted work in the tree means a commit here would
  mix the worker's change with a person's unfinished edits, and the write would
  destroy them on the way. mcgyvr reports a dirty tree and stops — the same
  stance :func:`mcgyvr.gate.preflight.check_clean_tree` takes before a run, taken
  again at its end. Untracked *siblings* are not dirt: another contract's
  in-flight work in the same workspace is kept out of this commit by the
  named-paths rule below, so it does not need to block it too.
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
  wrote. The style rungs are deliberately *included*: the gate rejects on
  ``lint`` and ``format``, so bytes that passed a gate pass these too, and
  bytes that do not never passed one. With one carve-out that is the
  gate's and not delivery's: a diagnostic an adapter stamps ``style`` is
  routed to ``observations`` and blocks nothing, here or anywhere. That is the
  demotion :mod:`mcgyvr.gate.typecheck` argues for, and delivery inherits it
  rather than re-deciding it — which is also why that demotion is withdrawn per
  *line* and not per code, so a line that cannot be imported rejects at both
  ends. The expensive rungs (acceptance commands, semantic resolution)
  need a sandbox delivery is not given, which is exactly the part an
  :class:`Accepted` carries in from where it could be run. What re-runs cheaply
  and catches what no rung could is *identity*: a substitution parses and lints,
  and only a comparison against the bytes just written can see it.
* **A rung of that gate run that could not say what bar it applied.** A tool
  that is *absent* leaves a hole an operator can see and does not reject, and a
  tool that is present and then *fails* leaves a hole shaped exactly like a
  pass. So the commit-time gate run is read through
  :attr:`~mcgyvr.gate.GateResult.accepted`'s whole definition — no findings
  *and* no inconclusive rung — rather than through its findings alone, so a
  repository with an unloadable ruff config cannot commit a change lint and
  format never looked at. Nothing is claimed about the worker: the refusal names
  the rung, the tool and its exit code, and :attr:`Delivery.inconclusive`
  carries them structurally.

**Where the commit lands is the caller's ``branch``.** Empty, the commit goes
onto the branch the operator has checked out. Named, it goes onto that branch
and leaves ``HEAD``, the index and the working tree exactly as it found them,
and hands back the ``git push`` that moves the work off this machine — the
honest form of "give it to me rather than land it" in a repository this
codebase reaches only through ``subprocess``. A named branch that does not
exist is created from ``HEAD``; one that does takes the commit on its tip, when
its copy of every delivered file is still the one the change was judged against
(:func:`_branch_refusal`). *Whether* to commit at all is not decided here: the
run's policy (``delivery.commit``) and its flags answer that before delivery is
called, and :func:`place` is what a run that does not commit calls instead.

*The rejected alternative is a client.* Delivery could push and open the pull
request — a remote, a forge token, an HTTP call. It is rejected because the seam
that must be certain about what it writes would become the seam that also owns
network transport, credential handling and one forge's API shape, all of it
unreachable from any test that does not either mock the forge or hold a real
token. A branch and a printed command are checkable from a temporary directory,
and they leave the operator holding exactly the same decision a pull request
would have put in front of them.

**What ships is the paths the verdict names, and nothing else.** The diff is
taken against the base the caller passes — a revision of *this* repository, the
one the task's worker started from — not against the attach revision and not
against whatever is lying in the tree, and the commit names its paths
explicitly. For a model's change that is the contract's single target. For the
deterministic floor it is every file the program changed in the sandbox — a
``rename_symbol`` fans across the files that reference the symbol — carried as
one :class:`Accepted` and delivered all at once: every file inside the
contract's scope, every file clean, one commit, or nothing written. A delivery
that staged everything would sweep a sibling contract's half-finished work into
this contract's commit.

**Every path that does not commit puts the tree back.** No failed attempt may
poison the next one, and the undo is narrowed to the bytes delivery itself
wrote. mcgyvr's tree is not exclusively delivery's — a ``git clean`` here would
delete the very sibling work the named-paths rule protects — so the undo is a
byte-exact snapshot taken before the write and restored after any
non-committing exit, including a raised one.

**No process-global state, and one exclusion that is not process state.**
Every fact a call needs is an argument or a local, and nothing is cached at
module scope. Two orchestrators delivering into two repositories at once is a
supported case. Two delivering into *one* repository is a different
question with a different answer: the index and ``HEAD`` are one shared, locked
resource per work tree, and none of write-check-stage-commit-undo is atomic
against another call's. So a delivery holds an exclusive ``flock`` on a file in the
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
import tempfile
import textwrap
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from mcgyvr.contract import Contract, is_pattern
from mcgyvr.gate.adapter import LanguageAdapter
from mcgyvr.gate.adapters import JavaScriptAdapter, PythonAdapter
from mcgyvr.gate.changeset import ChangeSet, ChangeSetError, FileChange
from mcgyvr.gate.findings import Finding
from mcgyvr.gate.runner import Gate, GateResult, InconclusiveRung
from mcgyvr.orchestrator.repo import AttachedRepo
from mcgyvr.scope import OutsideTreeError, inside

# The well-known SHA-1 of git's empty tree, and the same sentinel
# :mod:`mcgyvr.gate.changeset` and :mod:`mcgyvr.orchestrator.repo` use: a
# repository with no commit yet has no base to diff against, and the empty tree
# makes a first-ever delivery one code path with every other.
_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

#: The exclusion one delivery holds against another into the same repository,
#: kept inside the git directory rather than beside the target. The working
#: tree is the thing being protected: a lock file lying in it is untracked dirt
#: that a person's ``git clean`` would sweep up, and that every ``git status``
#: would show them.
_LOCK_NAME = "mcgyvr-delivery.lock"


#: Where delivery tells git to look for hooks: a path that does not exist, so it
#: finds none. Absolute and obviously-named — a relative path would resolve
#: inside the repository being delivered to, where something could one day be.
_NO_HOOKS = "/nonexistent/mcgyvr-delivery-runs-no-hooks"


@dataclass(frozen=True)
class Identity:
    """Who a delivery commit is authored by.

    Injected on the command line (``git -c user.name=…``) rather than written
    into the repository's config: a workspace with no
    ``user.name``/``user.email`` bound would otherwise fail the commit, and
    delivery must not fall over on a machine's git settings — nor quietly change
    them.
    """

    name: str
    email: str


#: The default author. A ``.invalid`` domain (RFC 2606) is deliberate: the commit
#: was made by a program, and no mailbox should be implied for it.
IDENTITY = Identity("mcgyvr", "delivery@mcgyvr.invalid")


@dataclass(frozen=True)
class Accepted:
    """The bytes a gate read, and the verdict it reached on them, as one value.

    Carried apart — a ``str`` of content beside a ``bool`` — the two stop being
    about each other whenever a step between them mutates the *tree* instead
    of the string: :func:`mcgyvr.repair.repair` rewrites the worker's file in
    place, the gate is re-run on what is now on disk, and a caller still holding
    the reply it was handed would deliver bytes the gate rejected under a verdict
    reached on bytes it never saw.

    The mint has to happen where the verdict does, from what the
    gate read — which is a *tree*, not a string a caller is holding. Hence
    :meth:`read`, which is handed the workspace the gate judged and takes the
    bytes from it; there is deliberately no constructor that accepts content and
    a verdict as two arguments, because that pair is the substitution itself.

    Even so, this value is a claim about somewhere else, and Python has no way
    to make a frozen dataclass unforgeable. It is therefore an *additional*
    refusal and never a licence: :func:`deliver` judges the bytes it is about to
    write whatever arrives here. What an :class:`Accepted` adds is the half of
    the verdict delivery cannot re-establish — the sandboxed rungs — and an
    identity that survives a round trip through the ``surrogateescape``
    convention, which is the one place ``intact`` can actually come out false.
    """

    content: str
    accepted: bool
    digest: str

    findings: tuple[Finding, ...] = field(default=())
    """Why the gate refused, when it did — carried so a caller reporting a
    stranded attempt has the offending line rather than a bare ``False``."""

    observations: tuple[Finding, ...] = field(default=())
    """What the gate said without refusing, carried so the caller that delivers
    the change can say it too."""

    path: str = ""
    """Where ``content`` goes, when that is not the contract's ``target``.

    Empty on every value a model's attempt mints: a worker writes the one file
    its contract names, and that file is the target. Set by :meth:`read` when it
    is handed the paths a program changed — a ``rename_symbol`` fans across the
    files that reference the symbol, and the target need not be one of them."""

    companions: tuple[Companion, ...] = field(default=())
    """The other files the same verdict covers, bound the way ``content`` is.

    One verdict over several files is what the deterministic floor reaches:
    the gate judges the sandbox's whole change, and a rename that changed two
    files was accepted as two files. Delivering one of them leaves the user's
    tree half-renamed — an import of a name that no longer exists — under a
    result that says ``accepted``. So the files travel together and land
    together: :func:`deliver` and :func:`place` write, check and commit all of
    them or none."""

    @classmethod
    def read(
        cls,
        *,
        repo: Path | str | AttachedRepo,
        contract: Contract,
        result: GateResult,
        paths: Sequence[str] | None = None,
    ) -> Accepted:
        """Bind ``result`` to the bytes on disk in the tree it was reached over.

        Called immediately after the gate run, in the workspace the gate ran in,
        and handed no content at all: the bytes come out of the tree the verdict
        is about. A caller cannot offer the string it happens to be holding,
        because there is no parameter to offer it through.

        ``paths`` are the files the verdict is about when that is not the
        contract's target alone — the change set a program left in the
        workspace. Every one is bound; the target comes first when it is among
        them, so a single-file change binds exactly as it does without
        ``paths``. Omitted, the target is the one file bound.
        """
        root = _root(repo)
        if not paths:
            text = _bound_text(root, contract, _target(root, contract))
            return cls(
                content=text,
                accepted=result.accepted,
                digest=digest_of(text),
                findings=tuple(result.findings),
                observations=tuple(result.observations),
            )
        first, *rest = sorted(
            dict.fromkeys(_inside(root, contract, path) for path in paths),
            key=lambda rel: (rel != contract.target.strip(), rel),
        )
        companions: list[Companion] = []
        for rel in rest:
            other = _bound_text(root, contract, rel)
            companions.append(
                Companion(path=rel, content=other, digest=digest_of(other))
            )
        text = _bound_text(root, contract, first)
        return cls(
            content=text,
            accepted=result.accepted,
            digest=digest_of(text),
            findings=tuple(result.findings),
            observations=tuple(result.observations),
            path=first,
            companions=tuple(companions),
        )

    @property
    def intact(self) -> bool:
        """Whether ``content`` is still what ``digest`` was taken from.

        Always true of a freshly :meth:`read` value, and that is not what it is
        for: it answers after the pair has been *carried* — stored, restored,
        rebuilt from a record — which is where the two can come apart without
        anybody rewriting either field. Every companion is held to the same
        question: a verdict over three files is not intact when one of them is
        not.
        """
        return self.digest == digest_of(self.content) and all(
            companion.intact for companion in self.companions
        )

    def files(self, contract: Contract) -> tuple[tuple[str, str], ...]:
        """Every ``(path, content)`` this verdict covers, the primary file first.

        The primary file's path is :attr:`path`, or the contract's target when
        that is empty — the target as written, for :func:`_target` to resolve
        and refuse exactly as it always has.
        """
        return (
            (self.path or contract.target, self.content),
            *((companion.path, companion.content) for companion in self.companions),
        )


@dataclass(frozen=True)
class Companion:
    """One more file an :class:`Accepted` verdict covers, bound the same way."""

    path: str
    content: str
    digest: str

    @property
    def intact(self) -> bool:
        """Whether ``content`` is still what ``digest`` was taken from."""
        return self.digest == digest_of(self.content)


def _bound_text(root: Path, contract: Contract, rel: str) -> str:
    """The bytes of ``rel`` in the judged tree, refused when they are not there."""
    try:
        return (root / rel).read_bytes().decode("utf-8", "surrogateescape")
    except OSError as exc:
        raise DeliveryError(
            f"{contract.id} was judged in {root} but {rel} is not there to bind "
            f"the verdict to: {exc}"
        ) from exc


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


class DeliveryRefusedError(DeliveryError):
    """The change was judged where it would land, and refused.

    :func:`place` has no :class:`Delivery` to hand a refusal back in, so it
    raises this, carrying the same two structured channels a refusing
    :class:`Delivery` does. A caller catching :class:`DeliveryError` still
    catches it; one that wants to say *which* checks refused, and not only the
    sentence, reads ``findings`` and ``inconclusive``.
    """

    def __init__(
        self,
        reason: str,
        *,
        findings: Sequence[Finding] = (),
        inconclusive: Sequence[InconclusiveRung] = (),
    ) -> None:
        super().__init__(reason)
        self.findings: tuple[Finding, ...] = tuple(findings)
        self.inconclusive: tuple[InconclusiveRung, ...] = tuple(inconclusive)


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
    """The repository-relative path this delivery shipped — the primary one,
    when it shipped several (:attr:`paths`)."""

    paths: tuple[str, ...] = field(default=())
    """Every repository-relative path this delivery shipped, :attr:`path`
    first. One path for a model's change; every file a program changed for the
    deterministic floor's, committed together in the one commit."""

    base: str = ""
    """The tree-ish the change was diffed against — a revision of *this*
    repository, the one the task's worker started from.

    Not a sandbox's :meth:`~mcgyvr.sandbox.Sandbox.base_changeset_ref`: that is
    the single commit of the fresh repository ``git init`` made inside that
    workspace, and resolves nowhere else, so supplying it here raises. The value
    a caller wants is :meth:`~mcgyvr.sandbox.Sandbox.source_base_commit` — the
    revision in the source repository that workspace was populated from, which
    is a revision delivery can diff against."""

    branch: str = ""
    """The branch the commit landed on, when it is not the one checked out.

    Empty for a commit onto the checked-out branch, where naming it would be
    telling the operator something they can see. Populated for a named branch,
    and it is the *structural* half of the handback: a caller wanting to push,
    diff, or name the work in a report has a ref to resolve rather than a
    sentence to parse."""

    handoff: str = ""
    """The next step the commit needs from a person, or empty when it needs none.

    One command line: for a named branch, the ``git push`` that moves the work
    off this machine, with the repository's own remote in it so it can be
    pasted. For the checked-out branch it is empty, and so it is on every
    refusal — nothing was committed, so nothing is owed."""

    findings: tuple[Finding, ...] = field(default=())
    """Why a re-check refused, when one did — carried structurally so a caller
    can report the offending line rather than re-derive it from ``reason``."""

    inconclusive: tuple[InconclusiveRung, ...] = field(default=())
    """Which rungs of the commit-time gate run ran and could not say what bar
    they applied.

    A separate field from :attr:`findings` because the two mean opposite things
    to the caller holding them. A finding is a claim about the change and is
    what a retry note is built from; an inconclusive rung claims nothing about
    the change at all — it is a fact about the machine, and the operator's next
    move is to fix a config rather than to ask a worker for a different file.
    Folding them together would put "ruff could not load your pyproject.toml"
    into the next prompt as something a model was expected to correct.

    Structured rather than left to :attr:`reason`: a run manifest has to answer
    *which rung was inconclusive* per row, and a rate quoted from rows where
    lint could not run is not the rate it claims to be. A caller re-deriving
    that by parsing a sentence is the coupling the field exists to prevent."""

    def __str__(self) -> str:
        if self.committed:
            where = f" on {self.branch}" if self.branch else ""
            step = f"; next: {self.handoff}" if self.handoff else ""
            shipped = ", ".join(self.paths) or self.path
            return f"delivered {shipped} as {self.commit[:12]}{where}{step}"
        return f"not delivered: {self.reason}"


def deliver(
    *,
    repo: Path | str | AttachedRepo,
    contract: Contract,
    content: str | Accepted,
    base: str = "HEAD",
    accepted: bool | None = None,
    branch: str = "",
    identity: Identity = IDENTITY,
    adapters: Sequence[LanguageAdapter] | None = None,
) -> Delivery:
    """Commit ``content`` as ``contract.target``, or refuse and say why.

    ``base`` is the revision of *this* repository the task's worker started from
    — not the attach revision and not the current tree. A sandbox names it
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
    wants committed. ``accepted=True`` raises: it is an acceptance nothing here
    can check — a caller asserting a verdict about bytes no gate ever read.
    Contradicting a bound verdict raises for the same reason.

    ``branch`` decides *where* the commit lands. Empty — or the name of the
    branch checked out — commits onto the branch in hand. Any other name
    commits onto that branch, leaving the checkout untouched and returning the
    push to run: created from ``HEAD`` when absent, onto its tip when present
    and its copy of every delivered file is the one at ``base``, refused when
    one moved or the branch is checked out in another worktree. A name git will
    not take as a branch raises before anything is written.

    ``adapters`` are the language adapters the commit-time gate run uses; the
    gate's own pair is the default. Nothing is shared between calls; the one
    exclusion is per repository and held in the repository, so two deliveries
    into two repositories still run concurrently and two into one queue.

    The checks made after the write are :func:`_refusal`, the same ones
    :func:`place` makes when the change is left uncommitted. The commit stays
    one atomic step: it lands whole, or the target, any directory the write
    created and the index are put back as they were.

    **Every file the verdict covers, in one commit.** An :class:`Accepted` that
    carries companions — the deterministic floor's, when a program changed more
    than one file — is delivered as one change: every file is held to every
    check above (scope, a commit since ``base``, uncommitted edits, the gate),
    and one refusal refuses them all with nothing written. A rename committed
    one file at a time, or half-written, is a tree that does not import.

    Raises :class:`DeliveryError` when delivery cannot be attempted — a path that
    is not a repository, a base that is empty or does not resolve, a target that
    escapes the tree, a verdict asserted or contradicted at the call site. A
    change that is merely unacceptable comes back as a refusal instead.
    """
    root = _root(repo)
    text, refused, bound = _verdict(content, accepted)
    files = _files(root, contract, text, bound)
    branch = _branch_named(root, branch)
    _named_base(base)

    with _exclusive(root):
        resolved = _resolve(root, base)
        call = _Call(
            root=root,
            path=files[0][0],
            base=resolved,
            paths=tuple(rel for rel, _ in files),
        )
        onto = _elsewhere(root, branch)

        hazard = _checkout_hazard(root, detached_ok=bool(onto))
        if hazard is None and onto:
            hazard = _branch_refusal(root, onto, resolved, call.paths)
        if hazard is not None:
            return call.refuse(hazard)

        refusal = _unwritable(call, contract, files, refused, bound)
        if refusal is not None:
            return refusal
        payloads = {rel: _encoded(body) for rel, body in files}

        dirty = _uncommitted(root, call.paths)
        if dirty:
            return call.refuse(
                f"the working tree is dirty ({_listed(dirty)}): delivering here "
                f"would commit the worker's change on top of unfinished edits, and "
                f"overwrite them on the way"
            )

        before = {rel: _snapshot(root / rel) for rel in call.paths}
        created = _all_missing_dirs(root, call.paths)
        staged = False
        # Not "did it commit" — "is the tree where the commit landed". Onto the
        # checked-out branch the two are the same thing. Onto a named branch the
        # commit is in a ref and the checkout is left as it was found, so the
        # undo below runs over a successful delivery, which is exactly right:
        # the work is durable somewhere else and a copy of it in the operator's
        # tree would be uncommitted edits they did not make.
        landed_here = False
        try:
            for rel, payload in payloads.items():
                _write(root / rel, payload)

            refusal = _refusal(call, contract, resolved, payloads, adapters)
            if refusal is not None:
                return refusal

            message = _message(contract, resolved, call.paths)
            if onto:
                return call.delivered(
                    _commit_onto(root, call.paths, message, identity, onto), onto
                )

            _git(root, "add", "--", *call.paths)
            staged = True
            sha = _commit(root, call.paths, message, identity)
            landed_here = True
            return call.delivered(sha)
        finally:
            # No attempt may poison the next one, so every exit that did not
            # leave the change in this tree — a refusal, a raised error, or a
            # delivery that put it on a named branch instead — leaves the tree
            # byte-for-byte as it was found. Narrowed to what this call wrote,
            # because a workspace-wide reset would delete work delivery was
            # never given. An undo that itself fails raises out of here, over
            # whatever was in flight: a tree we could not put back is the one
            # thing a caller must not be allowed to miss. It runs inside the
            # repository lock for the same reason the commit does — an undo
            # racing another call's staging leaves the index holding bytes the
            # tree does not.
            if not landed_here:
                for rel, held in before.items():
                    _restore(root / rel, held)
                _remove_created(created)
                if staged:
                    _git(root, "reset", "--quiet", "--", *call.paths)


@dataclass(frozen=True)
class _Call:
    """The facts every outcome of one delivery carries, whichever way it ends.

    A per-call value rather than a module-level context: two deliveries running
    at once each hold their own, and a refusal is then one line at the point
    the decision is made instead of a six-field constructor repeated five times.
    """

    root: Path
    path: str
    base: str
    paths: tuple[str, ...] = ()
    """Every path this call delivers, :attr:`path` first."""

    def refuse(
        self,
        reason: str,
        findings: Sequence[Finding] = (),
        inconclusive: Sequence[InconclusiveRung] = (),
    ) -> Delivery:
        """A refusal owes nothing.

        Nothing was committed, so there is no commit to hand anywhere and
        ``handoff`` stays empty.

        The two structured channels are separate parameters rather than one,
        and every refusal but the gate's passes neither: a refusal about a dirty
        tree or a lone surrogate is not a verdict on the change, and inventing
        an empty finding list for it would conflate a fact about the machine
        with a verdict on the change.
        """
        return Delivery(
            committed=False,
            reason=reason,
            path=self.path,
            paths=self.paths or (self.path,),
            base=self.base,
            findings=tuple(findings),
            inconclusive=tuple(inconclusive),
        )

    def delivered(self, sha: str, branch: str = "") -> Delivery:
        return Delivery(
            committed=True,
            commit=sha,
            path=self.path,
            paths=self.paths or (self.path,),
            base=self.base,
            branch=branch,
            handoff=_push_step(self.root, branch) if branch else "",
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


def _refuse_pattern_target(contract: Contract) -> None:
    """Refuse a target that names a set of files, not one file.

    Contract loading already rejects a glob target for a model-run task type;
    this is the same refusal at the delivery seam, by the same test
    (:func:`mcgyvr.contract.is_pattern`), for a contract assembled in code or
    read back from a record. A single-file delivery has no answer to a
    pattern, and writing it as a literal filename would commit a path nobody
    named.
    """
    if is_pattern(contract.target):
        raise DeliveryError(
            f"{contract.id} targets {contract.target!r}, which is a pattern. "
            f"A single-file delivery cannot take a pattern target; name one "
            f"literal path."
        )


def _verdict(
    content: str | Accepted, accepted: bool | None
) -> tuple[str, bool, Accepted | None]:
    """The bytes, whether a caller already refused them, and any bound verdict.

    The middle value is deliberately a *refusal* rather than an acceptance.
    Delivery reaches its own acceptance a few lines further down, over the bytes
    on disk; what it cannot reach on its own is "do not bother", and that is the
    only thing a caller is allowed to state here. ``accepted=True`` is a verdict
    asserted about bytes nothing here can check, and it raises rather than being
    quietly ignored, because a call site that believes it is stating a verdict
    should find out that it is not.
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
    orchestrators working on two different trees, and would still not serialise
    two *processes* on one tree.

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


def _branch_named(root: Path, branch: str) -> str:
    """``branch`` stripped, refused before anything is written when git will not
    take it as a branch name.

    Git is asked rather than its rules restated: ``a..b`` and ``a.lock`` look
    like names and are not refs.
    """
    named = branch.strip()
    if named and _refuses_ref(root, named):
        raise DeliveryError(
            f"{named!r} is not a name git takes for a branch, so nothing can be "
            f"committed onto it. Name another branch, or none to commit onto "
            f"the branch you have checked out"
        )
    return named


def _elsewhere(root: Path, branch: str) -> str:
    """``branch``, or empty when it is the branch checked out here.

    Naming the branch in hand is the same request as naming none, and has to
    be carried out as one: moving the checked-out ref without the index and
    tree would leave the operator's checkout reading as a revert of the commit
    just made.
    """
    if not branch:
        return ""
    current = subprocess.run(
        ["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return "" if branch == current else branch


def _branch_refusal(
    root: Path, branch: str, base: str, rels: Sequence[str]
) -> str | None:
    """Why a commit onto ``branch`` (not the checked-out one) is refused, or ``None``.

    **Checked out in another worktree.** Moving that ref would change the files
    under somebody else's checkout without touching them — the clobber a named
    branch exists to avoid.

    **Its copy of a delivered path moved.** The change was judged against each
    of ``rels`` at ``base``. A branch that holds a different copy of any of them
    holds work the accepted bytes were never judged against, and committing them
    onto its tip would revert it — the refusal :func:`_moved_since` makes for the
    checked-out branch, made for this one, and for every file the change spans:
    a rename lands on the branch whole or not at all. A branch that does not
    exist has no copy and is created from ``HEAD``, which that refusal already
    covers.
    """
    where = ""
    for line in _git(root, "worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            where = line.removeprefix("worktree ")
        elif line == f"branch refs/heads/{branch}":
            return (
                f"{branch} is checked out in the worktree at {where}: committing "
                f"onto it would change the files under that checkout. Name "
                f"another branch, or deliver from that worktree"
            )
    tip = _branch_tip(root, branch)
    if not tip:
        return None
    for rel in rels:
        if _blob(root, tip, rel) != _blob(root, base, rel):
            return (
                f"{branch} holds a different {rel} from the one at {_shown(base)} "
                f"the change was judged against: committing it onto {branch} "
                f"would overwrite that copy unjudged. Name another branch, or "
                f"bring {branch}'s {rel} level with the base first"
            )
    return None


def _branch_tip(root: Path, branch: str) -> str:
    """The commit ``refs/heads/<branch>`` names, or empty when there is none."""
    done = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}^{{commit}}"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip() if done.returncode == 0 else ""


def _blob(root: Path, rev: str, rel: str) -> str:
    """The object ``rel`` names at ``rev``, or empty when it is not there."""
    done = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{rev}:{rel}"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip() if done.returncode == 0 else ""


def _refuses_ref(root: Path, branch: str) -> bool:
    """Whether git rejects this as a branch name — asked of git, not restated."""
    done = subprocess.run(
        ["git", "check-ref-format", "--branch", branch],
        cwd=root,
        capture_output=True,
    )
    return done.returncode != 0


def _commit_onto(
    root: Path, rels: Sequence[str], message: str, identity: Identity, branch: str
) -> str:
    """Commit ``rels`` onto ``branch``, touching neither HEAD nor the index.

    This is what makes a named branch a different place rather than a different
    word for the checked-out one. ``git checkout`` then ``git commit`` then
    ``git checkout -`` would also produce the ref, and would do it by moving the
    operator's HEAD twice through states they never asked to be in — with their
    unfinished work in the tree the whole time, and no way back if the second
    checkout fails. Instead the commit is built as objects: a scratch index
    (``GIT_INDEX_FILE``, outside the repository) seeded from the parent, the
    delivered paths added into it, a tree written, a commit written over that
    tree, and the ref pointed at it. The repository's own index, ``HEAD`` and
    working tree are read and never written; :func:`deliver`'s undo then puts
    the files back.

    **The parent is the branch's tip, or ``HEAD`` for a branch not yet made —
    never the base.** The tree being committed is the parent's tree with the
    delivered paths replaced, so the parent is the only commit under which the
    commit's diff is this task's change; the branch's own history and its other
    files are kept. :func:`_branch_refusal` has already refused a tip whose copy
    of any delivered path is not the one the change was judged against.

    ``update-ref`` is given the tip it read as the expected old value — ``""``
    for a branch that must not exist yet — which makes the move atomic: the lock
    excludes another delivery, and this excludes everything else. ``core.hooksPath``
    is still pointed at nothing for the reason :func:`_commit` gives:
    ``update-ref`` fires ``reference-transaction``, which is the repository's
    code and not ours to run. ``commit-tree`` runs no hooks at all, which is a
    second reason to prefer it, and it does honour ``commit.gpgsign`` — so that
    is turned off here for the same reason it is there.
    """
    tip = _branch_tip(root, branch)
    parent = tip or _head(root)
    with _scratch_index() as index:
        if parent:
            _git(root, "read-tree", parent, env=index)
        _git(root, "update-index", "--add", "--", *rels, env=index)
        tree = _git(root, "write-tree", env=index).strip()
    parents = ["-p", parent] if parent else []
    sha = _git(
        root,
        "-c",
        f"user.name={identity.name}",
        "-c",
        f"user.email={identity.email}",
        "-c",
        "commit.gpgsign=false",
        "commit-tree",
        tree,
        *parents,
        # `-m`, because `commit-tree` is plumbing and does not take git-commit's
        # `--message`; it is the same string either way.
        "-m",
        message,
    ).strip()
    _git(
        root,
        "-c",
        f"core.hooksPath={_NO_HOOKS}",
        "update-ref",
        f"refs/heads/{branch}",
        sha,
        tip,
    )
    return sha


@contextlib.contextmanager
def _scratch_index() -> Iterator[dict[str, str]]:
    """A ``GIT_INDEX_FILE`` environment for staging that must not be seen.

    Outside the repository on purpose. An index file dropped inside ``.git``
    would be a name the operator's tooling can trip over, and one dropped in the
    work tree would be untracked dirt of exactly the kind the delivery lock is
    kept out of the tree to avoid.
    """
    with tempfile.TemporaryDirectory(prefix="mcgyvr-delivery-") as where:
        yield {"GIT_INDEX_FILE": str(Path(where) / "index")}


def _head(root: Path) -> str:
    """The commit ``HEAD`` names, or empty in a repository with none yet."""
    done = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "HEAD^{commit}"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip() if done.returncode == 0 else ""


def _push_step(root: Path, branch: str) -> str:
    """The one command that moves a ``branch`` delivery off this machine.

    A command rather than a description, and with the repository's own remote in
    it rather than a guessed ``origin``, so the obligation it records is one the
    operator can act on. A repository with no remote gets the shape of the
    command and the reason it cannot be run yet, which is still more than a mode
    name.
    """
    remotes = _git(root, "remote").split()
    if not remotes:
        return (
            f"git push -u <remote> {branch} — {root.name} has no remote "
            f"configured, so add one first"
        )
    return f"git push -u {remotes[0]} {branch}"


def _target(root: Path, contract: Contract) -> str:
    """The contract's single target as a repository-relative path.

    A target that escapes the repository, crosses a symlink or enters ``.git``
    is refused loudly rather than written (:func:`mcgyvr.scope.inside`): the
    contract's single-target discipline says where the worker's output goes,
    and "anywhere on this machine" is not one of the answers.
    """
    named = contract.target.strip()
    if not named:
        raise DeliveryError(f"{contract.id} names no target to deliver")
    try:
        resolved = inside(root, named)
    except OutsideTreeError as refusal:
        raise DeliveryError(
            f"{contract.id} targets {refusal}; delivery refuses it"
        ) from refusal
    return resolved.relative_to(root.resolve()).as_posix()


def _inside(root: Path, contract: Contract, named: str) -> str:
    """``named`` as a repository-relative path, refused as :func:`_target` is.

    For the paths an :class:`Accepted` carries besides the target: they came
    out of a change set rather than out of the contract, and are held to the
    same three refusals before anything reads or writes them.
    """
    try:
        resolved = inside(root, named.strip())
    except OutsideTreeError as refusal:
        raise DeliveryError(
            f"{contract.id} would deliver {refusal}; delivery refuses it"
        ) from refusal
    return resolved.relative_to(root.resolve()).as_posix()


def _files(
    root: Path, contract: Contract, text: str, bound: Accepted | None
) -> tuple[tuple[str, str], ...]:
    """Every ``(path, content)`` this call delivers, the primary file first.

    A model's change is one file, the contract's target, refused when it is a
    pattern (:func:`_refuse_pattern_target`) — today's single-target delivery
    exactly. A verdict that names its own paths (:attr:`Accepted.path`, the
    deterministic floor's) delivers those, each a literal path out of the change
    set, so a pattern target that let a formatter or a rename fan out is not the
    question. A path named twice is refused: two contents for one file is two
    answers to one question.
    """
    if bound is None or not bound.path:
        _refuse_pattern_target(contract)
        primary = _target(root, contract)
    else:
        primary = _inside(root, contract, bound.path)
    files = [(primary, text)]
    for companion in bound.companions if bound is not None else ():
        files.append((_inside(root, contract, companion.path), companion.content))
    paths = [rel for rel, _ in files]
    twice = sorted({rel for rel in paths if paths.count(rel) > 1})
    if twice:
        raise DeliveryError(
            f"{contract.id}'s verdict names {_listed(twice)} more than once; "
            f"delivery does not choose between two contents for one file"
        )
    return tuple(files)


def _named_base(base: str) -> None:
    """Refuse a base that names nothing, before anything is touched.

    An empty base is the one value that means *there is no base*, and reading
    it as ``HEAD`` would select the one base that is a moving name.
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
    return _head(root) or _EMPTY_TREE


def _checkout_hazard(root: Path, *, detached_ok: bool = False) -> str | None:
    """A checkout state a commit would be silently lost in, or ``None``.

    A commit onto the checked-out branch lands on whatever ``HEAD`` names. A
    detached ``HEAD`` names a commit no branch ref points at — unless the commit
    goes onto a named branch instead (``detached_ok``), which then starts from
    it. A rebase, merge, cherry-pick or bisect left partway through means the
    commit would start from a half-built or moving state, whichever branch it
    goes onto. Both are states the operator can fix — check out a branch, or
    finish the operation — so this returns a reason to refuse rather than
    raising.
    """
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    if branch == "HEAD" and not detached_ok:
        return (
            "HEAD is detached in "
            f"{root.name}: a commit here would have no branch to hold it. "
            "Check out a branch before delivering, or name one to commit onto "
            "(`--branch NAME`, or `delivery.branch`) and leave the checkout "
            "alone."
        )
    git_dir = _git_dir(root)
    labels = {
        "rebase-merge": "rebase",
        "rebase-apply": "rebase",
        "MERGE_HEAD": "merge",
        "CHERRY_PICK_HEAD": "cherry-pick",
        "BISECT_LOG": "bisect",
    }
    for name, label in labels.items():
        if (git_dir / name).exists():
            return (
                f"{name} is present in {root.name}'s git directory, so a "
                f"{label} is in progress. Finish or abort it before "
                f"delivering."
            )
    return None


def _uncommitted(root: Path, rels: Sequence[str]) -> tuple[str, ...]:
    """Paths that make this tree unsafe to commit into.

    Two kinds:

    * a **tracked** file with uncommitted changes — a person's unfinished edit,
      which a delivery would mix into its commit or overwrite outright;
    * a **delivered path that is untracked** — unversioned content the write
      would destroy with no way back.

    An untracked file that is not delivered is neither: it is another
    contract's work in the same workspace, and since delivery commits exactly
    the paths it names it cannot ride along.
    """
    unsafe = list(_modified(root))
    for rel in rels:
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


def _ignored(root: Path, rel: str) -> bool:
    """Whether ``.gitignore`` excludes this path, so a change to it is invisible.

    ``check-ignore`` exits 1 for a path that is *not* ignored, which is an answer
    rather than a failure — hence :func:`subprocess.run` here instead of
    :func:`_git`, which turns a non-zero exit into a :class:`DeliveryError`.

    Deliberately **without** ``--no-index``, which asks the wrong question: it
    reports on the ignore rules alone, so a file force-added with ``git add -f``
    while matching ``.gitignore`` comes back ignored — and delivery would then
    tell an operator their tracked, gated, perfectly deliverable file "was not
    in the change set the gate judged", when the real reason is that its content
    equals the base. Without the flag git answers about the path as it actually
    stands, which is what the caller is trying to explain.

    Only exit 0 is read as ignored. Anything else — 1 for not-ignored, 128 for a
    pathspec git will not take — leaves the caller on its original refusal, which
    is the safe direction: this function chooses between two ways of saying no.
    """
    done = subprocess.run(
        ["git", "check-ignore", "--quiet", "--", rel],
        cwd=root,
        capture_output=True,
    )
    return done.returncode == 0


def _delivered_changes(
    root: Path, base: str, rels: Sequence[str]
) -> dict[str, FileChange | None]:
    """This delivery's own files within the whole change against ``base``.

    Reusing :class:`~mcgyvr.gate.changeset.ChangeSet` is not only economy: it is
    what makes "delivered" and "gated" the same notion of a change. It stages
    into a throwaway index, so an untracked new target is seen as added and the
    repository's real index is never touched — and everything else it finds is
    the sibling work that must not ride along, which is why only the delivered
    paths are picked out of it. A delivered path the diff does not hold maps to
    ``None``.
    """
    try:
        changed = ChangeSet.detect(root, base)
    except ChangeSetError as exc:
        raise DeliveryError(f"cannot diff against {_shown(base)}: {exc}") from exc
    found = {change.path: change for change in changed}
    return {rel: found.get(rel) for rel in rels}


def _judged(
    changes: Sequence[FileChange],
    root: Path,
    base: str,
    adapters: Sequence[LanguageAdapter] | None,
    contract: Contract,
) -> GateResult:
    """Run the gate over this delivery's own change, here, now.

    This is the floor the whole module rests on: whatever a caller claims, these
    are the bytes about to become a commit, and this is a verdict on them rather
    than a verdict about them reported from elsewhere. Everything the gate can
    do without a sandbox runs — secrets and structured data from the aggregator,
    then syntax, structural hazards, lint and format from the adapters that own
    the path. A file no adapter owns is delivered unlinted, the same latitude
    the gate gives it.

    **The whole result comes back, not its findings.**
    :attr:`GateResult.accepted` is ``not findings and not inconclusive``, and
    the second half exists because a rung which crashed reports clean. Handing
    over the result lets the call site refuse for the right reason and say which
    rung it was.

    The change set handed over is narrowed to the delivered paths on purpose.
    The whole diff against ``base`` is also holding whatever sibling contracts
    have left in the workspace, and a delivery must not be refused because
    somebody else's half-finished file does not lint. The delivered files are
    judged together, in one run, as the sandbox's gate judged them.

    ``Scope`` is not passed: the contract's scope is re-confirmed a few lines
    above, where the refusal can name the contract that forbids the path rather
    than arriving as one finding among several.

    The contract's *prose* is passed, and for the opposite reason. It is the
    one input that changes what a rung means rather than which files it reads:
    ``param-mutation`` rejects a function for mutating its caller's object, and
    a contract that ordered in-place work has told the worker to write exactly
    that. Withholding it here would make delivery a stricter bar than the gate
    the change already passed in the sandbox — a change accepted where it was
    written and refused where it lands, for obeying its contract.
    """
    owners = tuple(adapters) if adapters is not None else _ADAPTERS()
    # A rung whose tool would import a delivered file as its configuration is
    # not run here, in the user's checkout: that would run the task's code on
    # the host (`not_rerun_here` says so to the user). One run judges every
    # delivered file, so the rung stands down for all of them together.
    kept = tuple(
        _Without(owner, loads)
        if (
            loads := frozenset(
                rung for change in changes for rung in owner.loads_as_code(change.path)
            )
        )
        else owner
        for owner in owners
    )
    narrowed = ChangeSet(repo=root, base=base, files=tuple(changes))
    return Gate(kept).run(narrowed, contract_text=contract.prose)


def not_rerun_here(adapters: Sequence[LanguageAdapter] | None, path: str) -> str:
    """The sentence saying which checker delivery left out for ``path``, or "".

    A checker that imports ``path`` as its own configuration is not run over it
    in the user's checkout, where it would run the task's code on the host. It
    runs on it only where the task's commands ran, in the task's sandbox.
    """
    owners = tuple(adapters) if adapters is not None else _ADAPTERS()
    tools = sorted(
        {tool for owner in owners for tool in owner.loads_as_code(path).values()}
    )
    if not tools:
        return ""
    names = " and ".join(tools)
    loads = "loads" if len(tools) == 1 else "load"
    return (
        f"not re-run here: {names} {loads} {path} as code, so it is checked by "
        f"{names} only in the task's sandbox, never on this machine"
    )


class _Without(LanguageAdapter):
    """``adapter`` with the named rungs (``lint``, ``format``) answering clean.

    Only for delivery's re-judge of a file a rung's tool would load as code;
    every other rung is the adapter's own.
    """

    def __init__(self, adapter: LanguageAdapter, rungs: frozenset[str]) -> None:
        self._adapter = adapter
        self._rungs = rungs

    @property
    def name(self) -> str:
        return self._adapter.name

    def owns(self, path: str) -> bool:
        return self._adapter.owns(path)

    def check_syntax(self, change: FileChange, repo: Path) -> list[Finding]:
        return self._adapter.check_syntax(change, repo)

    def structural_checks(
        self, change: FileChange, repo: Path, *, contract_text: str = ""
    ) -> list[Finding]:
        return self._adapter.structural_checks(
            change, repo, contract_text=contract_text
        )

    def lint(
        self, changes: Sequence[FileChange], repo: Path, *, base: str | None = None
    ) -> list[Finding]:
        if "lint" in self._rungs:
            return []
        return self._adapter.lint(changes, repo, base=base)

    def format_check(self, changes: Sequence[FileChange], repo: Path) -> list[Finding]:
        if "format" in self._rungs:
            return []
        return self._adapter.format_check(changes, repo)

    def locate_test_command(self, repo: Path) -> list[str] | None:
        return self._adapter.locate_test_command(repo)

    def locate_type_check_command(self, repo: Path) -> list[str] | None:
        return self._adapter.locate_type_check_command(repo)


def _unjudged(rungs: Sequence[InconclusiveRung]) -> str:
    """Every rung that could not say what bar it applied, in its own words.

    All of them, not the first: an operator fixing a broken environment gets
    every complaint from one run, not one per run.
    :meth:`InconclusiveRung.__str__` already names the adapter, the rung, the
    tool, the exit code and the tool's own first line, which is the whole of
    what the operator has to act on.
    """
    return "; ".join(str(rung) for rung in rungs)


def _ADAPTERS() -> tuple[LanguageAdapter, ...]:  # noqa: N802 — a default, not a class
    """The gate's own adapter pair, built per call.

    Constructed rather than shared at module scope so delivery holds no global
    state; adapters are cheap and hold nothing but the settings they were built
    with, so this costs nothing. These are the strict reading; a caller whose
    setup relaxed a check hands its own in as ``adapters``.
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

    ``surrogateescape`` is the repository's convention, and it is a convention
    about *bytes*: U+DC80..U+DCFF are how a byte that is not valid UTF-8
    survives a decode, and they have to keep round-tripping — the convention's
    entire claim is that the bytes a string carries are the bytes it resumes.

    A *lone* surrogate is a different animal and does not round-trip anything.
    ``\\ud800`` is a legal JSON escape, so it survives ``json.loads`` into a
    completion and passes ``parse_reply`` as ordinary content, and it denotes no
    byte sequence at all. The caller answers the
    :class:`UnicodeEncodeError` with a refusal, because inventing bytes for it
    would ship a file nobody gated and no encoding of it is the accepted one.
    """
    return content.encode("utf-8", "surrogateescape")


def _refusal(
    call: _Call,
    contract: Contract,
    resolved: str,
    payloads: Mapping[str, bytes],
    adapters: Sequence[LanguageAdapter] | None,
) -> Delivery | None:
    """Why the bytes just written may not stay, or ``None``.

    The one set of checks both ways out of a run take — :func:`deliver`
    before it commits and :func:`place` before it leaves the files in the tree —
    so what is left uncommitted and what would be committed cannot be judged
    by two different bars. Called inside the repository lock, after the write
    and before anything else touches the tree; the caller owns the undo.
    ``payloads`` maps every delivered path to the bytes written there, and one
    refusal of any of them is a refusal of all.

    In order: each file is still a change against ``resolved`` (and not
    ignored), each is inside the contract's scope, the gate's sandbox-free rungs
    find nothing over them together and none of them faulted, and the bytes on
    disk are still the bytes that were written.
    """
    root = call.root
    rels = tuple(payloads)
    # Named as one path when there is one, so a single-file refusal reads as it
    # always has; a set is listed.
    shown = rels[0] if len(rels) == 1 else _listed(rels)
    changes = _delivered_changes(root, resolved, rels)
    for rel, change in changes.items():
        if change is not None:
            continue
        if _ignored(root, rel):
            # A different fact with the same symptom, and worth its own
            # sentence: `ChangeSet.detect` stages with `add -A`, which
            # honours `.gitignore`, so an ignored target is not in the
            # change set — here *or* in the sandbox the gate ran in. The
            # bytes were therefore never judged, and "identical to base"
            # would send the reader looking for a diff that is not the
            # problem.
            return call.refuse(
                f"{rel} is ignored by {root.name}'s .gitignore, so it was "
                f"not in the change set the gate judged and is not in the "
                f"one delivery can commit. Un-ignore the path or point the "
                f"contract at one the repository tracks."
            )
        # Freshness: the accepted change is no longer a change. Either
        # the tree already holds it or the base moved under the run, and
        # committing now would report success for work that is not in
        # this commit.
        return call.refuse(
            f"{rel} is identical to {_shown(resolved)}: the accepted change "
            f"is no longer present, so there is nothing to commit"
        )

    outside = contract.scope.violations(rels)
    if outside:
        # Contract loading already rejects a target its own scope forbids,
        # and :func:`_unwritable` every delivered path before the write;
        # this re-confirms it at the commit point, where the answer is
        # about a file that now exists rather than about a declaration.
        return call.refuse(_outside(contract, outside))

    verdict = _judged(
        tuple(change for change in changes.values() if change is not None),
        root,
        resolved,
        adapters,
        contract,
    )
    if verdict.findings:
        return call.refuse(
            f"{shown} does not pass the gate in {root.name}: {verdict.findings[0]}",
            verdict.findings,
        )
    if verdict.inconclusive:
        # Findings first, and this second, because the two refusals are
        # about different things and the reader needs the one that is
        # about their change. A rung that faulted claims nothing about
        # the worker; if something else already rejected, that is the
        # sentence worth having.
        return call.refuse(
            f"{shown} could not be judged in {root.name}: "
            f"{_unjudged(verdict.inconclusive)}. Nothing is committed: a "
            f"rung that ran and cannot say what bar it applied did not "
            f"pass it, and a linter that reported clean while applying "
            f"no bar is a hole shaped exactly like a pass. "
            f"Fix what the tool is complaining about and deliver again.",
            inconclusive=verdict.inconclusive,
        )

    for rel, payload in payloads.items():
        if _snapshot(root / rel) != payload:
            # Identity, checked as late as this seam can check it. Between
            # the write above and git reading the file back sit several
            # subprocess round-trips, and a writer landing in that window
            # substitutes content no verdict covers — invisibly, because a
            # substitution made after the gate run above is judged by
            # nothing. The repository lock excludes another delivery; this
            # is what catches everything else.
            return call.refuse(
                f"{rel} changed between the write and the commit: what is on "
                f"disk is no longer the accepted content, and committing it "
                f"would ship bytes no verdict covers"
            )
    return None


def _outside(contract: Contract, outside: Sequence[str]) -> str:
    """The refusal for delivered paths the contract's scope does not allow."""
    if len(outside) == 1:
        return (
            f"{outside[0]} is outside the scope {contract.id} declares, so it may "
            f"not be committed under it"
        )
    return (
        f"{_listed(outside)} are outside the scope {contract.id} declares, so "
        f"they may not be committed under it"
    )


def place(
    *,
    repo: Path | str,
    contract: Contract,
    content: Accepted,
    base: str,
    adapters: Sequence[LanguageAdapter] | None = None,
) -> Path:
    """Leave the accepted content in the working tree as ``contract.target``.

    What a run does by default: no commit, no branch, no receipt — the output
    file, where the contract said it goes. The bytes are the ones the gate
    judged, written the way :func:`deliver` writes them, and refused before the
    write by the same :func:`_unwritable` checks — a verdict that is not an
    acceptance, bytes that are not the ones it was reached on, a target
    committed to since ``base``, content with no encoding.

    Git is consulted for one question: whether the target is safe to overwrite,
    which has two halves. ``base`` is the revision the worker started from —
    :meth:`~mcgyvr.sandbox.Sandbox.source_base_commit`, the same value
    :func:`deliver` takes and for the same reason. The sandbox judged *that*
    copy of the file. A target the user has committed to since the sandbox was
    opened — a climb takes minutes — holds work the accepted bytes were never
    judged against, and a clean tree says nothing about it; it is refused here
    rather than overwritten with exit 0. And a target the user has edited or
    never committed holds work the write would destroy with no way back, refused
    the way :func:`deliver` refuses it. The rest of the tree is theirs: other
    files that moved are not this write's business.

    **Checked exactly as a commit would be.** Once the bytes are written, the
    :func:`_refusal` that :func:`deliver` runs judges them where they landed: a
    change identical to ``base`` or an ignored target, a target outside the
    contract's scope, bytes the commit-time gate rejects or cannot judge, and
    bytes that changed after the write. A refusal restores the target, and
    removes any directory the write created, before
    :class:`DeliveryRefusedError` is raised carrying the refusal's findings: the
    tree is left as it was found.
    ``adapters`` are the language adapters those gate rungs use, as for
    :func:`deliver`.

    Under the repository's delivery lock, as :func:`deliver` is: a concurrent
    ``--commit`` delivery's undo restores the target to what it snapshotted,
    and a write that landed between its snapshot and its undo would be lost.
    """
    root = Path(repo)
    files = _files(root, contract, content.content, content)
    _named_base(base)
    with _exclusive(root):
        resolved = _resolve(root, base)
        call = _Call(
            root=root,
            path=files[0][0],
            base=resolved,
            paths=tuple(rel for rel, _ in files),
        )
        unwritable = _unwritable(call, contract, files, not content.accepted, content)
        if unwritable is not None:
            raise DeliveryRefusedError(unwritable.reason, findings=unwritable.findings)
        edited = [rel for rel in _uncommitted(root, call.paths) if rel in call.paths]
        if len(edited) == 1:
            (rel,) = edited
            raise DeliveryError(
                f"{rel} has uncommitted changes in the working tree, and the "
                f"accepted change was judged against the committed copy; writing "
                f"it would overwrite work no one has kept. Commit or restore "
                f"{rel} and run again."
            )
        if edited:
            raise DeliveryError(
                f"{_listed(edited)} have uncommitted changes in the working tree, "
                f"and the accepted change was judged against the committed "
                f"copies; writing them would overwrite work no one has kept. "
                f"Nothing was written: the change lands in every file it made or "
                f"in none. Commit or restore them and run again."
            )
        payloads = {rel: _encoded(body) for rel, body in files}
        before = {rel: _snapshot(root / rel) for rel in call.paths}
        created = _all_missing_dirs(root, call.paths)
        kept = False
        try:
            for rel, payload in payloads.items():
                _write(root / rel, payload)
            refusal = _refusal(call, contract, resolved, payloads, adapters)
            if refusal is not None:
                raise DeliveryRefusedError(
                    refusal.reason,
                    findings=refusal.findings,
                    inconclusive=refusal.inconclusive,
                )
            kept = True
            return root / call.path
        finally:
            # A refusal, or anything raised past the write, leaves every file
            # exactly as it was found — the invariant :func:`deliver` holds.
            if not kept:
                for rel, held in before.items():
                    _restore(root / rel, held)
                _remove_created(created)


def _unwritable(
    call: _Call,
    contract: Contract,
    files: Sequence[tuple[str, str]],
    refused: bool,
    bound: Accepted | None,
) -> Delivery | None:
    """Why nothing may be written for this call, or ``None``.

    The checks both ways out of a run make before the write, as
    :func:`_refusal` is the ones they make after it — so a change left in the
    tree and a change committed are held to one bar. Called inside the
    repository lock, before anything is touched, so a refusal has nothing to
    undo. ``files`` is every ``(path, content)`` the call delivers, and each is
    held to every check: one that fails refuses them all.

    In order: the gate did not accept the change; the bytes are not the ones
    the verdict was reached on; a path is outside the contract's scope — the
    whole set is named, because a rename that reached a file the contract does
    not allow is refused before any of it is written rather than delivered in
    part; a path was committed to after ``base``, so the verdict is about a
    copy of the file ``HEAD`` no longer holds and writing would revert that
    commit; and a content has no encoding.
    """
    if refused:
        return call.refuse(
            f"the gate did not accept {contract.id}; nothing was written",
            bound.findings if bound is not None else (),
        )

    if bound is not None and not bound.intact:
        if bound.digest != digest_of(bound.content):
            return call.refuse(
                f"the content handed to {contract.id} is not the content its "
                f"verdict was reached on: the accepted bytes digest to "
                f"{bound.digest[:12]} and these digest to "
                f"{digest_of(bound.content)[:12]}. Nothing is written, because "
                f"a verdict that has come apart from its bytes covers neither."
            )
        broken = next(c for c in bound.companions if not c.intact)
        return call.refuse(
            f"the content handed to {contract.id} for {broken.path} is not the "
            f"content its verdict was reached on: the accepted bytes digest to "
            f"{broken.digest[:12]} and these digest to "
            f"{digest_of(broken.content)[:12]}. Nothing is written, because "
            f"a verdict that has come apart from its bytes covers neither."
        )

    outside = contract.scope.violations(call.paths)
    if outside:
        return call.refuse(f"{_outside(contract, outside)}; nothing was written")

    for rel in call.paths:
        moved = _moved_since(call.root, call.base, rel)
        if moved:
            return call.refuse(
                f"{rel} was committed to after the run started: the accepted "
                f"change was judged against {_shown(call.base)}, and HEAD "
                f"({moved[:12]}) holds a different {rel}. Writing it would "
                f"overwrite work that was committed while the ladder was "
                f"climbing. Review the accepted change against the new copy, "
                f"or run again from the current HEAD."
            )

    for rel, text in files:
        try:
            _encoded(text)
        except UnicodeEncodeError as exc:
            return call.refuse(
                f"{rel} cannot be written: the character at position {exc.start} "
                f"is the lone surrogate U+{ord(text[exc.start]):04X}, which has no "
                f"UTF-8 encoding and stands for no byte. Writing it as anything "
                f"would ship bytes nobody gated."
            )
    return None


def _moved_since(root: Path, base: str, rel: str) -> str:
    """``HEAD`` when ``rel`` differs between ``base`` and ``HEAD``, else ``""``.

    A repository with no commit yet has no ``HEAD`` to have moved, and a base
    that does not resolve is the caller's error: git's own complaint is
    re-raised as a refusal rather than read as "nothing moved".
    """
    head = _head(root)
    if not head:
        return ""
    try:
        changed = _git(root, "diff", "--name-only", base, head, "--", rel)
    except DeliveryError as exc:
        raise DeliveryError(f"cannot diff against {_shown(base)}: {exc}") from exc
    return head if changed.strip() else ""


def _write(path: Path, payload: bytes) -> None:
    """Write ``payload`` to ``path`` verbatim, creating parents as needed.

    Bytes, and no newline translation or trailing-newline fixup: the gate judged
    exactly these characters, and a delivery that normalised them would ship a
    file the gate never saw. Already encoded by the caller, so that content with
    no encoding at all is refused before anything on disk has been touched.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _missing_dirs(path: Path) -> tuple[Path, ...]:
    """The path's missing parent directories, deepest first.

    Walked from ``path.parent`` upward and collected until an existing
    directory is reached. Returned deepest-first so the caller can remove them
    bottom-up: a child must be empty before its parent can be removed.
    """
    missing: list[Path] = []
    parent = path.parent
    while not parent.exists():
        missing.append(parent)
        if parent == parent.parent:
            break
        parent = parent.parent
    return tuple(missing)


def _all_missing_dirs(root: Path, paths: Sequence[str]) -> tuple[Path, ...]:
    """Every missing parent directory of every path, deepest first.

    Taken before the first write: once one file is written, a directory it
    created no longer counts as missing for the next, and the undo would leave
    it behind.
    """
    missing = {d for rel in paths for d in _missing_dirs(root / rel)}
    return tuple(sorted(missing, key=lambda d: len(d.parts), reverse=True))


def _remove_created(dirs: Sequence[Path]) -> None:
    """Remove directories a write created, empty ones only, best-effort.

    ``rmdir`` refuses a non-empty directory, which is the safety wanted here:
    a directory that gained content since the write must not be swept away.
    Failure is swallowed — the undo is best-effort and must not mask the reason
    the delivery is refusing.
    """
    for directory in dirs:
        with contextlib.suppress(OSError):
            directory.rmdir()


def _restore(path: Path, before: bytes | None) -> None:
    """Put the file back exactly as it was found, or remove one we created."""
    if before is None:
        path.unlink(missing_ok=True)
    else:
        path.write_bytes(before)


def _commit(root: Path, rels: Sequence[str], message: str, identity: Identity) -> str:
    """Commit exactly ``rels`` — in one commit — and return the new SHA.

    The pathspec is what keeps the commit to the delivered paths: a bare
    ``git commit`` would take whatever else the caller had staged and ``-a``
    would take the whole tree, while naming the paths commits this contract's
    files and leaves everyone else's work — staged, unstaged or untracked —
    exactly where it was.

    **No hooks run, because the repository is not ours.** ``repo`` is whatever
    tree the run was pointed at, and a mission points it at a detached worktree
    of a *cloned* repository whose hooks live in the shared git directory. A hook
    there is code the operator never agreed to run: it executes with the runner's
    environment, on the runner's machine, at the one moment mcgyvr is holding a
    repository lock. Nothing upstream of here gates a hook — the gate reads the
    worker's diff, not the repository's configuration — so the only place to
    decline is the invocation.

    ``--no-verify`` is **not** how that is done. It suppresses ``pre-commit``
    and ``commit-msg`` and nothing else: ``prepare-commit-msg`` still runs,
    before the object is written and with the message file to rewrite, and
    ``post-commit`` still runs after. Both satisfy the paragraph above word for
    word. ``core.hooksPath`` pointed at a path that does not exist is what
    actually holds — git finds no hook directory and runs none of the four — and
    it is set on the command line rather than in the repository's config so that
    nothing about the operator's checkout is changed. ``--no-verify`` is kept
    beside it as a statement of intent for a reader who greps for it, and
    carries no load.

    A delivery that wanted hooks to run would be asking the corpus to have an
    opinion about the change, which is the reviewer's job and not a shell
    script's.

    **``commit.gpgsign=false``, because this commit is scaffolding.** It is
    written by a runner under a synthetic identity, not authored, so a signature
    would attest to something that did not happen. The sharper reason is the
    failure mode: on a host with ``commit.gpgsign=true`` and no usable key, git
    exits non-zero, :func:`_git` raises :class:`DeliveryError`, and it raises
    from inside the ``try`` whose ``finally`` is mid-restore — out of a seam
    whose callers are written to receive a refusal. A delivery that cannot
    commit must say so as a :class:`Delivery`, never as an exception thrown
    through a caller that has already committed earlier contracts.
    """
    _git(
        root,
        "-c",
        f"user.name={identity.name}",
        "-c",
        f"user.email={identity.email}",
        "-c",
        "commit.gpgsign=false",
        "-c",
        f"core.hooksPath={_NO_HOOKS}",
        "commit",
        "--quiet",
        "--no-verify",
        "--message",
        message,
        "--",
        *rels,
    )
    return _git(root, "rev-parse", "HEAD").strip()


def _message(contract: Contract, base: str, paths: Sequence[str] = ()) -> str:
    """A commit message naming the contract, its target and its base.

    The base is in the trailer because a delivery is only meaningful against one:
    a reader asking "what did this task actually change" needs the revision the
    diff was taken from, and the branch it landed on may have moved since. The
    delivered files are listed too when they are not exactly the target — a
    rename's commit holds every file it renamed in, and ``Target`` alone would
    name one of them, or none.
    """
    files = (
        f"Files: {', '.join(paths)}\n"
        if paths and tuple(paths) != (contract.target.strip(),)
        else ""
    )
    subject = textwrap.shorten(
        f"{contract.id}: {' '.join(contract.task.split())}",
        width=72,
        placeholder="...",
    )
    return (
        f"{subject}\n\n"
        f"Contract: {contract.id}\n"
        f"Target: {contract.target}\n"
        f"{files}"
        f"Base: {_shown(base)}\n"
    )


def _shown(base: str) -> str:
    """A base rendered for a human: the empty tree said in words."""
    return "the empty tree" if base == _EMPTY_TREE else base


def _listed(paths: Sequence[str]) -> str:
    """The first few offending paths, with a count standing in for the rest."""
    shown = ", ".join(paths[:5])
    return shown if len(paths) <= 5 else f"{shown} (+{len(paths) - 5} more)"


def _git(root: Path, *args: str, env: Mapping[str, str] | None = None) -> str:
    """Run git in ``root``, returning stdout, raising with git's own complaint."""
    return _git_bytes(root, *args, env=env).decode("utf-8", "surrogateescape")


def _git_bytes(root: Path, *args: str, env: Mapping[str, str] | None = None) -> bytes:
    """The bytes form: path output is only safely decoded after splitting on NUL.

    ``env`` is *added to* the inherited environment rather than replacing it:
    the only caller uses it for ``GIT_INDEX_FILE``, and a git run with
    ``PATH``, ``HOME`` and the operator's ``GIT_*`` settings stripped out is a
    different git from the one every other call here gets.
    """
    proc = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        env={**os.environ, **env} if env else None,
    )
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise DeliveryError(f"git {args[0]} failed in {root}: {detail}")
    return proc.stdout
