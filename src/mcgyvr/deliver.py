"""Land a judged change in the user's repository, or refuse to and say why.

:func:`deliver` is how a change reaches the user's tree. It takes the bytes an
attempt produced — or the :class:`Accepted` the gate minted for them — and
resolves which files they land in, takes a lock on the repository, checks that
writing them cannot destroy work (a detached HEAD, a merge or rebase in
progress, uncommitted edits, a file that moved in HEAD since the base, a path
outside the contract's scope, a named branch that is checked out in another
worktree or holds a different copy of the file), writes the files, re-runs the
gate over the change they make, and commits — onto the checked-out branch, or
onto a named branch through ``commit-tree`` and ``update-ref`` with the
checkout left as it was. :func:`place` walks the same path without the commit.

A verdict is never taken on faith. :class:`Accepted` carries the digest of the
content it was reached on, and content that no longer hashes to that digest is
refused rather than shipped, because "accepted" would then describe bytes
nothing judged; ``accepted=True`` handed in from outside is refused for the same
reason, since this module can check a digest but not a claim.

Every write is bracketed by the lock of :func:`_exclusive` and by a snapshot of
the paths about to change, so a refusal after the write restores the previous
bytes and removes the directories the call created. A verdict covering several
files (:attr:`Accepted.companions`) lands all of them or none.
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

# git's empty tree: the object every empty tree hashes to, and the only
# tree-ish that can stand for a base when there is no commit yet.
# `_resolve` substitutes it for an unborn HEAD, so a diff against it reads
# every file as added.
_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

# The lock file `_exclusive` flocks inside the git directory. It sits in
# `.git` rather than the work tree so it is never picked up as a file the
# delivery itself made, and it is one name for the whole repository so two
# deliveries cannot interleave their dirty-tree check, their writes and
# their commit.
_LOCK_NAME = "mcgyvr-delivery.lock"


# A path that does not exist, used as `core.hooksPath` for every commit this
# module makes. With it (and `--no-verify` where hooks run) the repository's
# commit hooks cannot rewrite the index or the message, so what lands is what
# the gate judged.
_NO_HOOKS = "/nonexistent/mcgyvr-delivery-runs-no-hooks"


@dataclass(frozen=True)
class Identity:
    """The name and email git records on a delivery commit."""

    name: str
    email: str


# The identity every delivery commit is attributed to, so a commit does not
# depend on the machine having a git identity configured.
IDENTITY = Identity("mcgyvr", "delivery@mcgyvr.invalid")


@dataclass(frozen=True)
class Accepted:
    """A gate verdict bound to the exact bytes it was reached on.

    `content` is what the gate judged, `accepted` whether it passed, and `digest`
    ties the two together: :attr:`intact` re-hashes the content, which catches a
    caller that edited the string after the verdict was minted. `path` and
    `companions` extend one verdict over the several files a program-driven change
    can touch.
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
        """Bind a gate result to the files in `repo` it was reached on.

        Without `paths` this reads the contract's target. With `paths` it reads each
        one, drops duplicates, and puts the contract's target first when it is among
        them; the rest become companions. A file that is not in the tree to be read
        raises :class:`DeliveryError`, because a verdict cannot be bound to content that
        is not there.
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
        """Whether `content` and every companion still hash to the stored digest."""
        return self.digest == digest_of(self.content) and all(
            companion.intact for companion in self.companions
        )

    def files(self, contract: Contract) -> tuple[tuple[str, str], ...]:
        """The ``(path, content)`` pairs this verdict covers, primary file first.

        The primary path falls back to the contract's target when :attr:`path` is
        empty.
        """
        return (
            (self.path or contract.target, self.content),
            *((companion.path, companion.content) for companion in self.companions),
        )


@dataclass(frozen=True)
class Companion:
    """One of the further files a single verdict covers, bound by digest."""

    path: str
    content: str
    digest: str

    @property
    def intact(self) -> bool:
        """Whether `content` still hashes to `digest`."""
        return self.digest == digest_of(self.content)


def _bound_text(root: Path, contract: Contract, rel: str) -> str:
    """Read `rel` from `root` as text, or raise when it is not there.

    Bytes are decoded with ``surrogateescape`` so content that git stores as
    bytes survives the round trip. A file that cannot be read is fatal: a verdict
    cannot be bound to content the tree does not hold.
    """
    try:
        return (root / rel).read_bytes().decode("utf-8", "surrogateescape")
    except OSError as exc:
        raise DeliveryError(
            f"{contract.id} was judged in {root} but {rel} is not there to bind "
            f"the verdict to: {exc}"
        ) from exc


def digest_of(content: str) -> str:
    """The sha256 of `content`: how a verdict is tied to the bytes it judged.

    Encoded with ``surrogatepass``, so the digest is defined even for text
    holding a lone surrogate — the same text :func:`_encoded` refuses to write.
    """
    return hashlib.sha256(content.encode("utf-8", "surrogatepass")).hexdigest()


class DeliveryError(Exception):
    """A delivery could not be attempted: bad arguments, or git failed."""


class DeliveryRefusedError(DeliveryError):
    """A delivery was attempted and refused, with the reasons carried.

    Raised by :func:`place`, which has no :class:`Delivery` to return; the same
    refusals come back from :func:`deliver` as an uncommitted :class:`Delivery`.
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
    """The outcome of a delivery: whether it committed, and what a person owes next.

    A refusal and a success are both one of these, so a caller reads
    :attr:`committed` rather than catching an exception. `reason` explains a
    refusal; `commit`, `path`, `paths`, `base`, `branch` and `handoff` describe a
    commit.
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
    """Write `content` into `repo`, re-check it, and commit it.

    The steps, in order: resolve `content` to text and to an optional bound verdict
    (:func:`_verdict`); work out which files land (:func:`_files`); take the
    delivery lock; resolve `base`; refuse a detached HEAD or a rebase, merge,
    cherry-pick or bisect in progress, and refuse a named `branch` that is checked
    out elsewhere or holds a different copy of a delivered path; run the checks that
    come before any write (:func:`_unwritable`); refuse a dirty working tree; write
    the files, re-run the gate over the change they make (:func:`_refusal`), and
    commit — through ``commit-tree``/``update-ref`` onto `branch` when one is named,
    otherwise through ``git add`` and ``git commit`` on the checked-out branch.

    A refusal after the write leaves nothing behind: every path goes back to the
    bytes it held, the directories the call created are removed, and anything staged
    is unstaged. The returned :class:`Delivery` says which of the two happened.
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
        # Two flags for the `finally` below. `staged` records that the paths went into
        # the repository's real index, so a rollback owes it a `git reset`.
        # `landed_here` records that the commit landed on the checked-out branch, where
        # the delivered bytes are meant to stay in the working tree. A commit onto a
        # named branch leaves it false on purpose: that commit lives only in the branch
        # ref, so the work tree is put back the way it was found.
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
            # Rollback, for every way out of the block above short of a commit on the
            # checked-out branch: each delivered path goes back to the bytes read into
            # `before` and is deleted when there was no file before, the directories
            # in `created` are removed once empty, and paths that reached the real
            # index are unstaged. It runs on the refusal returns as well as on an
            # exception, so a change that fails its re-check leaves the tree as it was
            # found rather than half-written, and the restore happens before the caller
            # sees the result. `git reset` touches only the index, which is what makes
            # that order safe.
            if not landed_here:
                for rel, held in before.items():
                    _restore(root / rel, held)
                _remove_created(created)
                if staged:
                    _git(root, "reset", "--quiet", "--", *call.paths)


@dataclass(frozen=True)
class _Call:
    """The arguments a decision needs, and the two ways to answer it.

    `path` is the primary file and `paths` every file the call delivers, the primary
    one first (empty means just `path`, which :meth:`refuse` and
    :meth:`delivered` normalise). `base` is the resolved revision the change is
    diffed against.
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
        """An uncommitted :class:`Delivery` for `reason`, carrying path and paths."""
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
    """The root of `repo`, refusing a directory that is not a git repository.

    An :class:`~mcgyvr.orchestrator.repo.AttachedRepo` contributes its `root`; a
    path is taken as given. A root with no ``.git`` entry (a directory, or the file
    a worktree has instead) cannot hold a commit.
    """
    root = repo.root if isinstance(repo, AttachedRepo) else Path(repo)
    if not (root / ".git").exists():
        raise DeliveryError(f"{root} is not a git repository; nothing can be delivered")
    return root


def _refuse_pattern_target(contract: Contract) -> None:
    """Reject a pattern target: one delivery needs one literal path."""
    if is_pattern(contract.target):
        raise DeliveryError(
            f"{contract.id} targets {contract.target!r}, which is a pattern. "
            f"A single-file delivery cannot take a pattern target; name one "
            f"literal path."
        )


def _verdict(
    content: str | Accepted, accepted: bool | None
) -> tuple[str, bool, Accepted | None]:
    """Split the caller's content into ``(text, refused, bound)``.

    `accepted=True` is refused outright: it asserts a verdict this call cannot
    check, and acting on it would ship bytes no gate is known to have read. An
    :class:`Accepted` supplies its own verdict — and raises when `accepted`
    contradicts it — while a bare string is marked refused only when the caller
    passes ``accepted=False``.
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
    """Hold an exclusive ``flock`` on the delivery lock file for the block.

    This is what serialises deliveries into one repository: the checks that read
    the working tree and the commit that changes it happen under one lock. The lock
    is released when the descriptor is closed, including on an exception.
    """
    try:
        fd = os.open(_git_dir(root) / _LOCK_NAME, os.O_RDWR | os.O_CREAT, 0o600)
    except OSError as exc:
        raise DeliveryError(f"cannot take the delivery lock in {root}: {exc}") from exc
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)  # closing the descriptor releases the lock


def _git_dir(root: Path) -> Path:
    """The repository's absolute git directory (a worktree's own, not the main one)."""
    return Path(_git(root, "rev-parse", "--absolute-git-dir").strip())


def _branch_named(root: Path, branch: str) -> str:
    """`branch` without surrounding whitespace, or ``""`` when none was named.

    A name git would not accept as a branch is an error rather than a silent
    fall-back to the checked-out branch.
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
    """`branch` when it is not the one checked out in `root`, else ``""``.

    ``""`` means "commit onto the checked-out branch"; a value means the commit has
    to be built without touching the checkout.
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
    """Why committing onto `branch` is unsafe, or ``None`` when it is safe.

    Refuses when the branch is checked out in any worktree, because the commit
    would change the files under that checkout, and when the branch's tip holds a
    different version of a delivered path than `base` does, because the commit would
    overwrite a copy nothing judged. A branch that does not exist yet has no copy to
    clash with.
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
    """The commit `branch` points at, or ``""`` for a branch that does not exist."""
    done = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}^{{commit}}"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip() if done.returncode == 0 else ""


def _blob(root: Path, rev: str, rel: str) -> str:
    """The blob id `rel` has at `rev`, or ``""`` when it has none."""
    done = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{rev}:{rel}"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip() if done.returncode == 0 else ""


def _refuses_ref(root: Path, branch: str) -> bool:
    """Whether git rejects `branch` as a branch name."""
    done = subprocess.run(
        ["git", "check-ref-format", "--branch", branch],
        cwd=root,
        capture_output=True,
    )
    return done.returncode != 0


def _commit_onto(
    root: Path, rels: Sequence[str], message: str, identity: Identity, branch: str
) -> str:
    """Commit `rels` onto `branch` and move the ref, without touching the checkout.

    The tree is built in a scratch index (``GIT_INDEX_FILE`` in a temporary
    directory), so the repository's own index and work tree are untouched: the
    parent tree is read into it, the delivered paths are added, and the result is
    written. ``commit-tree`` mints the commit with `identity` and signing off, and
    ``update-ref`` moves ``refs/heads/<branch>`` to it with the old tip as the
    expected value, so a branch that moved in the meantime fails the update instead
    of losing the commit that moved it. Returns the new commit's sha.
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
        # The message goes in as one argv element, so no byte of the contract's task
        # text is ever read by a shell.
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
    """Yield an environment pointing git at a temporary, empty index."""
    with tempfile.TemporaryDirectory(prefix="mcgyvr-delivery-") as where:
        yield {"GIT_INDEX_FILE": str(Path(where) / "index")}


def _head(root: Path) -> str:
    """The current HEAD commit, or ``""`` when the repository has no commit yet."""
    done = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "HEAD^{commit}"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip() if done.returncode == 0 else ""


def _push_step(root: Path, branch: str) -> str:
    """The ``git push`` a person needs to move `branch` off this machine.

    The repository's first configured remote is named when there is one; with no
    remote the line says so, because no push can work until one is added.
    """
    remotes = _git(root, "remote").split()
    if not remotes:
        return (
            f"git push -u <remote> {branch} — {root.name} has no remote "
            f"configured, so add one first"
        )
    return f"git push -u {remotes[0]} {branch}"


def _target(root: Path, contract: Contract) -> str:
    """The contract's target as a repository-relative POSIX path.

    Raises :class:`DeliveryError` when the contract names no target, or one that
    resolves outside `root`.
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
    """`named` as a repository-relative POSIX path, refusing anything outside `root`."""
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
    """The ``(path, content)`` pairs this delivery writes, primary file first.

    A bound verdict that names a path supplies its own file set, companions
    included, and each is re-resolved inside `root`; otherwise the contract's target
    is used, which must then be a literal path rather than a pattern. Raises when
    the same path appears twice, since delivery does not choose between two contents
    for one file.
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
    """Reject an empty base, which is not shorthand for HEAD.

    HEAD is a moving name: diffing against it would ship whatever the branch has
    reached by the time delivery runs rather than the change this task made.
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
    """The revision to diff against: `base` as given, or the empty tree for no HEAD.

    ``"HEAD"`` is the only value resolved here. An unborn repository has no HEAD
    commit, so the empty-tree sentinel stands in and every file reads as added.
    """
    if base != "HEAD":
        return base
    return _head(root) or _EMPTY_TREE


def _checkout_hazard(root: Path, *, detached_ok: bool = False) -> str | None:
    """Why committing in `root` right now would be unsafe, or ``None``.

    Refuses a detached HEAD unless `detached_ok` — a named branch gives the commit
    a ref to live on, so the detached checkout does not matter — and refuses while a
    rebase, merge, cherry-pick or bisect is in progress, since the commit would land
    in the middle of one.
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
    """Working-tree paths a delivery here would put at risk.

    That is every modified tracked path git reports anywhere in the repository,
    plus a delivered path that exists on disk without being tracked: writing and
    staging the delivery would overwrite either. Order is kept and duplicates
    dropped.
    """
    unsafe = list(_modified(root))
    for rel in rels:
        if (root / rel).exists() and not _tracked(root, rel):
            unsafe.append(rel)
    return tuple(dict.fromkeys(unsafe))


def _modified(root: Path) -> tuple[str, ...]:
    """Tracked paths git reports as changed, read from NUL-separated porcelain output.

    Each record is ``XY <path>``, so the path starts at byte 3. A rename or copy
    record carries the original path as a second NUL-terminated field, and that one
    is skipped; the trailing empty token ends the scan.
    """
    tokens = _git_bytes(
        root, "status", "--porcelain", "-z", "--untracked-files=no"
    ).split(b"\x00")
    paths: list[str] = []
    i = 0
    while i < len(tokens):
        record = tokens[i]
        if not record:  # the trailing empty token of the split
            break
        paths.append(record[3:].decode("utf-8", "surrogateescape"))
        i += 2 if record[:1] in (b"R", b"C") else 1
    return tuple(paths)


def _tracked(root: Path, rel: str) -> bool:
    """Whether git knows `rel` as a tracked path."""
    return bool(_git(root, "ls-files", "--", rel).strip())


def _ignored(root: Path, rel: str) -> bool:
    """Whether an ignore rule matches `rel`."""
    done = subprocess.run(
        ["git", "check-ignore", "--quiet", "--", rel],
        cwd=root,
        capture_output=True,
    )
    return done.returncode == 0


def _delivered_changes(
    root: Path, base: str, rels: Sequence[str]
) -> dict[str, FileChange | None]:
    """Detect the change set against `base` and pick `rels` out of it.

    Returns one entry per requested path, ``None`` where the diff does not mention
    it — a path identical to the base, or one git ignores — which the caller has to
    refuse. A diff that cannot be produced is a :class:`DeliveryError`.
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
    """Run the gate over `changes`, leaving out the rungs that would execute them.

    An adapter reports through ``loads_as_code`` which of its rungs load a given path
    as code rather than reading it — a lint or format config module, say. Those rungs
    are dropped for this run, because running them here would execute the delivered
    file. :class:`_Without` stubs exactly those rungs out and delegates the rest.
    """
    owners = tuple(adapters) if adapters is not None else _ADAPTERS()
    # A changed config module is not data the linter reads but a module it imports,
    # so running that rung on this machine would execute the delivered bytes.
    # `loads_as_code` names those rungs per path; `_Without` reports nothing for
    # them and leaves the check to the sandbox.
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
    """A line naming the tools that would execute `path`, or ``""`` for none.

    The rungs delivery skips are not skipped silently: the tools that load `path`
    as code are named, so a report can say where the file was checked instead.
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
    """An adapter that answers for another adapter but stubs out named rungs.

    Every method is delegated unchanged except ``lint`` and ``format_check``, which
    report nothing when ``"lint"`` or ``"format"`` is in the rung set handed to the
    constructor.
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
    """The inconclusive rungs as one semicolon-separated line."""
    return "; ".join(str(rung) for rung in rungs)


def _ADAPTERS() -> tuple[LanguageAdapter, ...]:  # noqa: N802 — a default, not a class
    """The default adapters when a caller names none: Python, then JavaScript."""
    return (PythonAdapter(), JavaScriptAdapter())


def _snapshot(path: Path) -> bytes | None:
    """The current bytes of `path`, or ``None`` when there is no file there."""
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _encoded(content: str) -> bytes:
    """`content` as the bytes to write, or ``UnicodeEncodeError`` for a lone surrogate.

    ``surrogateescape`` round-trips the undecodable bytes a file may already hold
    and raises for a surrogate that stands for no byte at all — the case
    :func:`_unwritable` refuses up front.
    """
    return content.encode("utf-8", "surrogateescape")


def _refusal(
    call: _Call,
    contract: Contract,
    resolved: str,
    payloads: Mapping[str, bytes],
    adapters: Sequence[LanguageAdapter] | None,
) -> Delivery | None:
    """Why the written files must not be committed, or ``None`` when they may be.

    It runs after the write, so it judges what a commit would actually ship: every
    delivered path has to appear in the change set against `resolved` (an ignored
    path and one identical to the base do not), the paths have to be inside the
    contract's scope, a fresh gate run over the change set has to report no findings
    and no inconclusive rung, and the bytes on disk have to still equal the payloads
    written. The returned :class:`Delivery` names the first condition that failed.
    """
    root = call.root
    rels = tuple(payloads)
    # A message names the one path when there is one, and lists them when several
    # files were delivered.
    shown = rels[0] if len(rels) == 1 else _listed(rels)
    changes = _delivered_changes(root, resolved, rels)
    for rel, change in changes.items():
        if change is not None:
            continue
        if _ignored(root, rel):
            # An ignored path never reaches the change set, so the gate never saw it
            # and `git add` would not stage it: what would be delivered is not the
            # content that was judged and cannot be committed under the contract's
            # name. It is reported apart from the identical-to-base case below,
            # because the fix is to un-ignore the path rather than to change the file.
            return call.refuse(
                f"{rel} is ignored by {root.name}'s .gitignore, so it was "
                f"not in the change set the gate judged and is not in the "
                f"one delivery can commit. Un-ignore the path or point the "
                f"contract at one the repository tracks."
            )
        # ``None`` means the path is not in the diff against the base: what is on
        # disk is what the base holds. The accepted change is not there — the write
        # did not take, or the tree already had it — so there is nothing to commit
        # under the contract's name.
        return call.refuse(
            f"{rel} is identical to {_shown(resolved)}: the accepted change "
            f"is no longer present, so there is nothing to commit"
        )

    outside = contract.scope.violations(rels)
    if outside:
        # Checked again here rather than trusted from the pre-write check: the paths are
        # now resolved ones, and scope is re-asserted at the point where a commit is
        # about to happen.
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
        # An inconclusive rung blocks the commit. It reported no finding, but it
        # also did not apply the bar it was configured to apply, so there is no
        # verdict to ship. It is carried in ``inconclusive`` so the caller can tell
        # "the tool could not run" from "the change is wrong".
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
            # The gate run above reads the tree, and anything on this machine can write
            # to it in between. Re-reading each path and comparing it with the payload
            # catches a file that no longer holds the accepted bytes, so the commit
            # cannot ship content the verdict never covered.
            return call.refuse(
                f"{rel} changed between the write and the commit: what is on "
                f"disk is no longer the accepted content, and committing it "
                f"would ship bytes no verdict covers"
            )
    return None


def _outside(contract: Contract, outside: Sequence[str]) -> str:
    """The refusal text for paths the contract's scope does not allow."""
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
    """Write the accepted files into `repo` and leave them uncommitted.

    The pre-write checks of :func:`deliver` (:func:`_unwritable`), plus a refusal
    when any delivered path already has uncommitted edits, which the write would
    overwrite. Then the files are written, the change is re-judged by
    :func:`_refusal`, and the primary path is returned. A refusal after the write
    restores every path and removes the directories created, raising
    :class:`DeliveryRefusedError`.
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
            # On a refusal after the write, every path goes back to the bytes it held
            # and the directories the call made are removed: a refused placement leaves
            # no trace.
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
    """Why nothing may be written at all, or ``None`` when the write may go ahead.

    The checks that come before the first byte: a verdict that refused, a verdict
    whose digest no longer matches its content (primary file or companion), a path
    outside the contract's scope, a path that HEAD has moved since `base`, and
    content that will not encode. Each answer is a refused :class:`Delivery`, which
    :func:`deliver` returns and :func:`place` raises.
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
    """HEAD's sha when `rel` differs between `base` and HEAD, else ``""``.

    An unborn HEAD has nothing to have moved, so it answers ``""``; a ``git diff``
    that cannot run is an error rather than an answer.
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
    """Write `payload` to `path`, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _missing_dirs(path: Path) -> tuple[Path, ...]:
    """The directories above `path` that do not exist yet, deepest first."""
    missing: list[Path] = []
    parent = path.parent
    while not parent.exists():
        missing.append(parent)
        if parent == parent.parent:
            break
        parent = parent.parent
    return tuple(missing)


def _all_missing_dirs(root: Path, paths: Sequence[str]) -> tuple[Path, ...]:
    """Every directory `paths` need and do not have, deepest first, deduplicated."""
    missing = {d for rel in paths for d in _missing_dirs(root / rel)}
    return tuple(sorted(missing, key=lambda d: len(d.parts), reverse=True))


def _remove_created(dirs: Sequence[Path]) -> None:
    """Remove `dirs`, ignoring any that is not empty or is already gone."""
    for directory in dirs:
        with contextlib.suppress(OSError):
            directory.rmdir()


def _restore(path: Path, before: bytes | None) -> None:
    """Put `path` back to `before`, deleting it when there was no file before."""
    if before is None:
        path.unlink(missing_ok=True)
    else:
        path.write_bytes(before)


def _commit(root: Path, rels: Sequence[str], message: str, identity: Identity) -> str:
    """Commit `rels` on the checked-out branch and return the new HEAD sha.

    `identity` supplies author and committer, signing is off so the commit cannot ask
    for a key, and hooks are disabled so no hook can change what lands. ``--`` keeps
    git from reading a path as a revision.
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
    """The commit message for a delivery.

    The subject is the contract id and its task, shortened to 72 columns, and the
    body names the contract, the target and the base. A ``Files:`` line is added
    only when the delivery covers paths beyond the contract's own target.
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
    """The empty-tree sentinel spelled out for a reader, and any other base as given."""
    return "the empty tree" if base == _EMPTY_TREE else base


def _listed(paths: Sequence[str]) -> str:
    """The first five paths comma-separated, with a count of the rest when longer."""
    shown = ", ".join(paths[:5])
    return shown if len(paths) <= 5 else f"{shown} (+{len(paths) - 5} more)"


def _git(root: Path, *args: str, env: Mapping[str, str] | None = None) -> str:
    """Run git in `root` and return its stdout as text.

    ``surrogateescape`` keeps paths that are not valid UTF-8 intact on the way back;
    :func:`_git_bytes` raises when the command fails.
    """
    return _git_bytes(root, *args, env=env).decode("utf-8", "surrogateescape")


def _git_bytes(root: Path, *args: str, env: Mapping[str, str] | None = None) -> bytes:
    """Run git in `root` and return its raw stdout, raising when it fails.

    `env` is merged over the current environment, which is how a scratch index
    (``GIT_INDEX_FILE``) reaches a command. A non-zero status becomes a
    :class:`DeliveryError` carrying git's stderr.
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
