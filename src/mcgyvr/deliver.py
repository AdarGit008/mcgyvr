""

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

#
#
#
#
_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

#
#
#
#
#
_LOCK_NAME = "mcgyvr-delivery.lock"


#
#ve
#
_NO_HOOKS = "/nonexistent/mcgyvr-delivery-runs-no-hooks"


@dataclass(frozen=True)
class Identity:
    ""

    name: str
    email: str


#
#
IDENTITY = Identity("mcgyvr", "delivery@mcgyvr.invalid")


@dataclass(frozen=True)
class Accepted:
    ""

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
        ""
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
        ""
        return self.digest == digest_of(self.content) and all(
            companion.intact for companion in self.companions
        )

    def files(self, contract: Contract) -> tuple[tuple[str, str], ...]:
        ""
        return (
            (self.path or contract.target, self.content),
            *((companion.path, companion.content) for companion in self.companions),
        )


@dataclass(frozen=True)
class Companion:
    ""

    path: str
    content: str
    digest: str

    @property
    def intact(self) -> bool:
        ""
        return self.digest == digest_of(self.content)


def _bound_text(root: Path, contract: Contract, rel: str) -> str:
    ""
    try:
        return (root / rel).read_bytes().decode("utf-8", "surrogateescape")
    except OSError as exc:
        raise DeliveryError(
            f"{contract.id} was judged in {root} but {rel} is not there to bind "
            f"the verdict to: {exc}"
        ) from exc


def digest_of(content: str) -> str:
    ""
    return hashlib.sha256(content.encode("utf-8", "surrogatepass")).hexdigest()


class DeliveryError(Exception):
    ""


class DeliveryRefusedError(DeliveryError):
    ""

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
    ""

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
    ""
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
        #he
        #
        #
        #
        #
        #
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
            #
            # a
            #ee
            #
            #
            #
            #
            #
            #do
            #
            #
            if not landed_here:
                for rel, held in before.items():
                    _restore(root / rel, held)
                _remove_created(created)
                if staged:
                    _git(root, "reset", "--quiet", "--", *call.paths)


@dataclass(frozen=True)
class _Call:
    ""

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
        ""
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
    ""
    root = repo.root if isinstance(repo, AttachedRepo) else Path(repo)
    if not (root / ".git").exists():
        raise DeliveryError(f"{root} is not a git repository; nothing can be delivered")
    return root


def _refuse_pattern_target(contract: Contract) -> None:
    ""
    if is_pattern(contract.target):
        raise DeliveryError(
            f"{contract.id} targets {contract.target!r}, which is a pattern. "
            f"A single-file delivery cannot take a pattern target; name one "
            f"literal path."
        )


def _verdict(
    content: str | Accepted, accepted: bool | None
) -> tuple[str, bool, Accepted | None]:
    ""
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
    ""
    try:
        fd = os.open(_git_dir(root) / _LOCK_NAME, os.O_RDWR | os.O_CREAT, 0o600)
    except OSError as exc:
        raise DeliveryError(f"cannot take the delivery lock in {root}: {exc}") from exc
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)  #


def _git_dir(root: Path) -> Path:
    ""
    return Path(_git(root, "rev-parse", "--absolute-git-dir").strip())


def _branch_named(root: Path, branch: str) -> str:
    ""
    named = branch.strip()
    if named and _refuses_ref(root, named):
        raise DeliveryError(
            f"{named!r} is not a name git takes for a branch, so nothing can be "
            f"committed onto it. Name another branch, or none to commit onto "
            f"the branch you have checked out"
        )
    return named


def _elsewhere(root: Path, branch: str) -> str:
    ""
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
    ""
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
    ""
    done = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}^{{commit}}"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip() if done.returncode == 0 else ""


def _blob(root: Path, rev: str, rel: str) -> str:
    ""
    done = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{rev}:{rel}"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip() if done.returncode == 0 else ""


def _refuses_ref(root: Path, branch: str) -> bool:
    ""
    done = subprocess.run(
        ["git", "check-ref-format", "--branch", branch],
        cwd=root,
        capture_output=True,
    )
    return done.returncode != 0


def _commit_onto(
    root: Path, rels: Sequence[str], message: str, identity: Identity, branch: str
) -> str:
    ""
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
        #
        #
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
    ""
    with tempfile.TemporaryDirectory(prefix="mcgyvr-delivery-") as where:
        yield {"GIT_INDEX_FILE": str(Path(where) / "index")}


def _head(root: Path) -> str:
    ""
    done = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "HEAD^{commit}"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip() if done.returncode == 0 else ""


def _push_step(root: Path, branch: str) -> str:
    ""
    remotes = _git(root, "remote").split()
    if not remotes:
        return (
            f"git push -u <remote> {branch} — {root.name} has no remote "
            f"configured, so add one first"
        )
    return f"git push -u {remotes[0]} {branch}"


def _target(root: Path, contract: Contract) -> str:
    ""
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
    ""
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
    ""
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
    ""
    if not base.strip():
        raise DeliveryError(
            "delivery was given an empty base. A base is the revision the "
            "worker started from, and an empty one is not a request to diff "
            "against HEAD — HEAD is a moving name, and diffing against it "
            "ships whatever the branch has got to rather than this task's "
            "change. Pass Sandbox.source_base_commit(), or 'HEAD' explicitly"
        )


def _resolve(root: Path, base: str) -> str:
    ""
    if base != "HEAD":
        return base
    return _head(root) or _EMPTY_TREE


def _checkout_hazard(root: Path, *, detached_ok: bool = False) -> str | None:
    ""
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
    ""
    unsafe = list(_modified(root))
    for rel in rels:
        if (root / rel).exists() and not _tracked(root, rel):
            unsafe.append(rel)
    return tuple(dict.fromkeys(unsafe))


def _modified(root: Path) -> tuple[str, ...]:
    ""
    tokens = _git_bytes(
        root, "status", "--porcelain", "-z", "--untracked-files=no"
    ).split(b"\x00")
    paths: list[str] = []
    i = 0
    while i < len(tokens):
        record = tokens[i]
        if not record:  #
            break
        paths.append(record[3:].decode("utf-8", "surrogateescape"))
        i += 2 if record[:1] in (b"R", b"C") else 1
    return tuple(paths)


def _tracked(root: Path, rel: str) -> bool:
    ""
    return bool(_git(root, "ls-files", "--", rel).strip())


def _ignored(root: Path, rel: str) -> bool:
    ""
    done = subprocess.run(
        ["git", "check-ignore", "--quiet", "--", rel],
        cwd=root,
        capture_output=True,
    )
    return done.returncode == 0


def _delivered_changes(
    root: Path, base: str, rels: Sequence[str]
) -> dict[str, FileChange | None]:
    ""
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
    ""
    owners = tuple(adapters) if adapters is not None else _ADAPTERS()
    #
    #
    #
    #
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
    ""
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
    ""

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
    ""
    return "; ".join(str(rung) for rung in rungs)


def _ADAPTERS() -> tuple[LanguageAdapter, ...]:  #ss
    ""
    return (PythonAdapter(), JavaScriptAdapter())


def _snapshot(path: Path) -> bytes | None:
    ""
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _encoded(content: str) -> bytes:
    ""
    return content.encode("utf-8", "surrogateescape")


def _refusal(
    call: _Call,
    contract: Contract,
    resolved: str,
    payloads: Mapping[str, bytes],
    adapters: Sequence[LanguageAdapter] | None,
) -> Delivery | None:
    ""
    root = call.root
    rels = tuple(payloads)
    #
    #
    shown = rels[0] if len(rels) == 1 else _listed(rels)
    changes = _delivered_changes(root, resolved, rels)
    for rel, change in changes.items():
        if change is not None:
            continue
        if _ignored(root, rel):
            #
            #
            #
            #he
            #
            #
            #
            return call.refuse(
                f"{rel} is ignored by {root.name}'s .gitignore, so it was "
                f"not in the change set the gate judged and is not in the "
                f"one delivery can commit. Un-ignore the path or point the "
                f"contract at one the repository tracks."
            )
        #
        #
        #
        #
        return call.refuse(
            f"{rel} is identical to {_shown(resolved)}: the accepted change "
            f"is no longer present, so there is nothing to commit"
        )

    outside = contract.scope.violations(rels)
    if outside:
        #
        #
        #
        #
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
        #
        #
        #
        #
        #
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
            #
            #
            #
            # a
            #
            #
            #
            return call.refuse(
                f"{rel} changed between the write and the commit: what is on "
                f"disk is no longer the accepted content, and committing it "
                f"would ship bytes no verdict covers"
            )
    return None


def _outside(contract: Contract, outside: Sequence[str]) -> str:
    ""
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
    ""
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
            #
            #s.
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
    ""
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
    ""
    head = _head(root)
    if not head:
        return ""
    try:
        changed = _git(root, "diff", "--name-only", base, head, "--", rel)
    except DeliveryError as exc:
        raise DeliveryError(f"cannot diff against {_shown(base)}: {exc}") from exc
    return head if changed.strip() else ""


def _write(path: Path, payload: bytes) -> None:
    ""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _missing_dirs(path: Path) -> tuple[Path, ...]:
    ""
    missing: list[Path] = []
    parent = path.parent
    while not parent.exists():
        missing.append(parent)
        if parent == parent.parent:
            break
        parent = parent.parent
    return tuple(missing)


def _all_missing_dirs(root: Path, paths: Sequence[str]) -> tuple[Path, ...]:
    ""
    missing = {d for rel in paths for d in _missing_dirs(root / rel)}
    return tuple(sorted(missing, key=lambda d: len(d.parts), reverse=True))


def _remove_created(dirs: Sequence[Path]) -> None:
    ""
    for directory in dirs:
        with contextlib.suppress(OSError):
            directory.rmdir()


def _restore(path: Path, before: bytes | None) -> None:
    ""
    if before is None:
        path.unlink(missing_ok=True)
    else:
        path.write_bytes(before)


def _commit(root: Path, rels: Sequence[str], message: str, identity: Identity) -> str:
    ""
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
    ""
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
    ""
    return "the empty tree" if base == _EMPTY_TREE else base


def _listed(paths: Sequence[str]) -> str:
    ""
    shown = ", ".join(paths[:5])
    return shown if len(paths) <= 5 else f"{shown} (+{len(paths) - 5} more)"


def _git(root: Path, *args: str, env: Mapping[str, str] | None = None) -> str:
    ""
    return _git_bytes(root, *args, env=env).decode("utf-8", "surrogateescape")


def _git_bytes(root: Path, *args: str, env: Mapping[str, str] | None = None) -> bytes:
    ""
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
