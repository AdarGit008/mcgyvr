"""Deterministic repair of a rejected change (D21).

The gate is read-only on purpose: ``ruff format --diff`` reports what the
formatter *would* change, ``ruff check`` runs without ``--fix``, and a
formatting violation becomes a :class:`~mcgyvr.gate.Finding` rather than a
rewrite. A checker that edits what it is checking cannot be trusted to have
checked it, so that separation stays.

What it leaves behind is a bill. Every rejection a *tool* could have fixed for
nothing — an unused import, an unsorted block, a line the formatter would
reflow — is instead paid for with a model call, and on a weak local model the
call is the scarce thing. A 7B that produced correct logic with a blank line in
the wrong place is asked to try again, and it is at least as likely to produce
different logic as the same logic formatted.

So this module is the other half of the separation. The gate judges and never
writes; :func:`repair` writes and never judges. The caller's loop is::

    result = gate.run(changeset, contract.scope)
    if not result.accepted and repair(repo=repo, contract=contract, base=base).changed:
        result = gate.run(ChangeSet.detect(repo, base), contract.scope)

and the point of it is the rung that does *not* appear: on a repaired file the
gate is re-run **on the same rung, with no model retry**. A failed attempt
becomes a free pass.

Four constraints hold the lever honest, and each is a way it could otherwise
buy nothing, cost something, or write somewhere it was not asked to:

* **It reports what it did, by the bytes.** ``changed`` is computed by
  comparing each file before and after, not by trusting a tool's exit code. A
  caller told "repaired" re-runs the gate; told that on a file nothing touched,
  it re-runs a gate whose answer it already has, and on a failing attempt that
  is a loop that ends at the attempt ceiling rather than a recovery.
* **It stays inside the contract's scope — the file's, not the name's.** The
  tools are pointed at an explicit file list drawn from the change set and
  filtered through :class:`~mcgyvr.scope.Scope`, never at a directory. A
  formatter run across a tree is exactly how a tidy-up escapes its contract: it
  rewrites a human's unrelated file, and the gate never notices because the gate
  only looks at the change. Checking the *path* is not enough for the same
  reason: a symlink the worker left inside the scope is an in-scope name for an
  out-of-scope file, and ``ruff format`` writes through it. Resolving the path
  is not enough either, because a hard link has nothing to resolve — it *is*
  the file, under a second name, and the formatter writing through the name the
  scope allows rewrites the one it forbids (see :func:`_repairable`).
* **It says what it left behind.** ``repair`` mutates the working tree while its
  caller holds the worker's reply as a string, so :attr:`RepairOutcome.content`
  carries the bytes now on disk. Without it the caller has no way to learn what
  the gate is about to be re-run on, and the bytes it carries forward to
  :func:`mcgyvr.deliver.deliver` are the ones the gate *rejected*.
* **The one step that adds code may only transcribe.** Auto-import insertion
  writes ``from <module> import <name>`` for an undefined name **only** when
  some ``deps`` entry in the contract already declares that name. The repair is
  writing down something the contract said, not inventing a dependency.

Everything here is best effort. A missing ruff, a ruff that dies, a file that
will not decode: all are recorded as environment issues and none of them
raises. The verdict on the change belongs to the gate, and a tidy-up that could
not run has no standing to overturn one — it just reports that it changed
nothing, and the caller escalates exactly as it would have without this module.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from mcgyvr.contract import Contract, Dependency
from mcgyvr.gate.adapter import ToolUnavailableError, plain_env, require_tool
from mcgyvr.gate.adapters import PythonAdapter
from mcgyvr.gate.adapters.python import RUFF
from mcgyvr.gate.changeset import ChangeSet, ChangeSetError, FileChange
from mcgyvr.lines import LINE_END, parser_lines

#: ruff reports on 0 (clean) and 1 (diagnostics, or fixes applied with some
#: left); anything else is ruff telling us it did not do the job. Same split
#: the adapters make (:func:`mcgyvr.gate.adapter.trusted_stdout`) — read here
#: rather than reused, because an untrustworthy repair is an environment issue
#: and not, as it is for a gate rung, a reason to refuse the change.
_REPORTING = frozenset({0, 1})

#: Directory prefixes that are a packaging root rather than a package. ``src``
#: carries no ``__init__.py`` and is never importable, so ``src/pkg/x.py`` is
#: the module ``pkg.x``; keeping the prefix would emit an import that does not
#: resolve, which replaces one failure with another.
_SOURCE_ROOTS = ("src/",)

#: The name ruff quotes in ``Undefined name `foo```. Read from the message
#: rather than from the source span, because the span is a byte range and the
#: message already carries the identifier ruff resolved.
_UNDEFINED_NAME = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")


@dataclass(frozen=True)
class RepairOutcome:
    """What a repair pass actually did.

    ``repaired`` holds the paths whose bytes differ from what the worker left,
    which is the only claim a caller can act on: it is what makes re-running
    the gate worth a second subprocess rather than a guaranteed repeat of the
    verdict already in hand.

    ``content`` is what is on disk when the pass finishes, per repairable path
    and whether or not this pass changed it. It is here because a repair mutates
    the tree and its caller does not: the caller holds the worker's reply as a
    string, the gate is re-run against the file, and nothing connected the two —
    so the bytes carried on to delivery were the bytes the gate had rejected.
    That is the ``repair`` half of the port's "nothing owns the bytes"; the
    delivery half is :class:`mcgyvr.deliver.Accepted`, which binds these bytes to
    the verdict the re-run gate reaches on them.

    ``environment_issues`` mirror
    :class:`~mcgyvr.gate.acceptance.AcceptanceReport`'s — a step that could not
    run, phrased so an operator knows what to install. They never imply
    anything about the change.
    """

    repaired: tuple[str, ...] = ()
    content: Mapping[str, str] = field(default_factory=dict)
    environment_issues: tuple[str, ...] = ()

    @property
    def changed(self) -> bool:
        """Whether any file on disk is different from what the worker wrote."""
        return bool(self.repaired)


def repair(*, repo: Path, contract: Contract, base: str = "HEAD") -> RepairOutcome:
    """Apply every fix a tool can make to the worker's change, in place.

    ``base`` is the pre-worker tree, the same one the gate measured the change
    against, so the files touched here are exactly the files the gate judged.
    Nothing outside ``contract.scope`` is opened, and no model is reached at any
    point — this module imports nothing from :mod:`mcgyvr.runner` and calls no
    dispatcher, which is the whole economic argument for the lever.

    The order is deliberate: imports are inserted **first**, then the fixer,
    then the formatter. The insertion is the only step that writes new code, so
    running the tools after it means they see the file the re-run gate will see
    and the repair never leaves behind a line it added but did not tidy.

    The outcome carries the bytes left on disk as well as the paths, because the
    caller's next move is to re-run the gate on this tree and then hand *content*
    to :func:`mcgyvr.deliver.deliver` — and the content it was holding when it
    called this is no longer the content the gate is about to judge.
    """
    issues: list[str] = []
    try:
        changeset = ChangeSet.detect(repo, base)
    except ChangeSetError as exc:
        # No change set, no file list: repairing a tree we cannot describe is
        # exactly the unscoped tidy-up this module refuses to be.
        return RepairOutcome(environment_issues=(f"repair: {exc}",))

    targets = _repairable(changeset, contract)
    if not targets:
        return RepairOutcome()

    paths = [change.path for change in targets]
    before = {path: _read_bytes(repo / path) for path in paths}

    ruff = _locate_ruff(issues)
    if ruff is not None:
        _insert_declared_imports(repo, ruff, paths, contract.deps, issues)
        _run_ruff(repo, ruff, ["check", "--fix", "--force-exclude"], paths, issues)
        _run_ruff(repo, ruff, ["format", "--force-exclude"], paths, issues)

    after = {path: _read_bytes(repo / path) for path in paths}
    return RepairOutcome(
        repaired=tuple(path for path in paths if after[path] != before[path]),
        content={
            path: raw.decode("utf-8", "surrogateescape")
            for path, raw in after.items()
            if raw is not None
        },
        environment_issues=tuple(issues),
    )


def _repairable(changeset: ChangeSet, contract: Contract) -> list[FileChange]:
    """The changed files a repair may open: Python, in scope, still a real file.

    ``owned`` is the adapter's own answer to "is this a Python file the gate
    scans", already excluding deletions and binaries — asking it rather than
    re-deriving the suffix list keeps the repair pointed at precisely the files
    the gate's Python rungs rejected on.

    Scope is asked about the name, and then about the file, because those were
    not the same question and the gap was a way out of the contract. ``is_file()``
    follows symlinks: a link the worker left at an allowed path is an in-scope
    *name* for whatever it points at, and ``ruff format`` writes through it —
    rewriting a file the contract explicitly forbids, reporting the repair
    against the in-scope name, and leaving the gate none the wiser because the
    gate only ever looks at the change. So the answer is taken about the bytes
    that would actually be rewritten: still inside the repository, permitted
    where the name really lands, and — because a file may have more than one
    name and resolving finds only the first kind — permitted under *every* name
    it has (:func:`_writes_where_it_says`).
    """
    return [
        change
        for change in PythonAdapter().owned(changeset.files)
        if contract.scope.permits(change.path)
        and _writes_where_it_says(changeset.repo, change.path, contract)
    ]


def _writes_where_it_says(repo: Path, path: str, contract: Contract) -> bool:
    """Whether opening ``path`` for writing rewrites only bytes the contract allows.

    ``False`` for a path that is not a regular file, that resolves outside the
    repository, that resolves onto a file the scope does not permit, or that is
    one of several names for a file whose other names the scope does not permit —
    one check rather than four because the answer to all of them is the same:
    this is not ours to rewrite. A path with no link in it resolves to itself and
    has one name, and the scope has already said yes to that, so the ordinary
    case costs two ``stat`` calls and answers exactly as before.
    """
    target = repo / path
    if not target.is_file():
        return False
    anchor = repo.resolve()
    resolved = target.resolve()
    if anchor not in resolved.parents:
        return False
    if not contract.scope.permits(resolved.relative_to(anchor).as_posix()):
        return False
    return _every_name_is_in_scope(anchor, resolved, contract)


def _every_name_is_in_scope(anchor: Path, resolved: Path, contract: Contract) -> bool:
    """Whether every name this file has is one the contract permits.

    ``resolve()`` answers for symlinks and cannot answer for hard links, because
    a hard link is not a reference to a file — it *is* the file, under a second
    directory entry, with nothing to see through and nothing to resolve. The
    formatter writes to the inode, so what it writes through the name the scope
    allows appears under the name the scope forbids: in a directory the contract
    excluded, or in a tree the repository does not contain.

    An inode cannot be asked for its names, and the names that matter most are
    the ones outside the repository, where there is nowhere to look. So the
    question is asked the other way round. ``st_nlink`` is how many names the
    file has; count the ones inside the repository that the scope permits, and if
    that is fewer, at least one name exists that this repair may not write to —
    without ever having to find it. Two in-scope names for one inode is a file
    the contract permits, written twice, and is repaired as normal: the refusal
    is about where the other names are, not about there being more than one.
    """
    try:
        inode = resolved.stat()
    except OSError:
        return False
    if inode.st_nlink <= 1:
        return True
    return _in_scope_names(anchor, inode, contract) >= inode.st_nlink


def _in_scope_names(anchor: Path, inode: os.stat_result, contract: Contract) -> int:
    """How many names inside the repository, and inside scope, this inode has.

    The walk is paid for only by a file that has more than one name, which in a
    source tree is rare enough to cost nothing in the ordinary case, and it stops
    as soon as the count can no longer change the answer.

    ``lstat`` rather than ``stat`` so that a symlink counts as the separate file
    it is rather than as a second name for its target: counted the other way, a
    symlink and a hard link both aimed at one forbidden file would look like two
    permitted names and let the pair through. ``.git`` is not walked — nothing in
    it is a repair's to rewrite, and leaving a name found there out of the count
    can only refuse a file, never admit one.
    """
    device, number = inode.st_dev, inode.st_ino
    found = 0
    for directory, subdirectories, names in os.walk(anchor):
        subdirectories[:] = [name for name in subdirectories if name != ".git"]
        for name in names:
            candidate = Path(directory) / name
            if not contract.scope.permits(candidate.relative_to(anchor).as_posix()):
                continue
            try:
                entry = candidate.lstat()
            except OSError:
                continue
            if (entry.st_dev, entry.st_ino) == (device, number):
                found += 1
                if found >= inode.st_nlink:
                    return found
    return found


# --- the tools ------------------------------------------------------------


def _locate_ruff(issues: list[str]) -> str | None:
    """ruff's path, or ``None`` with the absence recorded for the operator."""
    try:
        return require_tool(RUFF)
    except ToolUnavailableError as exc:
        issues.append(f"repair: {exc.tool} not installed — no fix could be applied")
        return None


def _run_ruff(
    repo: Path, ruff: str, args: Sequence[str], paths: Sequence[str], issues: list[str]
) -> None:
    """Run one ruff rung over ``paths``, noting a fault instead of raising.

    ``--force-exclude`` because the paths are named explicitly: without it ruff
    edits a file its own configuration excludes, and a repository that excluded
    a path has said not to rewrite it. ``--`` because a worker-created filename
    may begin with a dash.
    """
    proc = subprocess.run(
        [ruff, *args, "--", *paths],
        cwd=repo,
        capture_output=True,
        text=True,
        env=plain_env(),
        check=False,
    )
    if proc.returncode not in _REPORTING:
        issues.append(
            f"repair: {RUFF} {args[0]} exited {proc.returncode} — "
            f"{_first_line(proc.stderr)}"
        )


# --- auto-import insertion ------------------------------------------------


def _insert_declared_imports(
    repo: Path,
    ruff: str,
    paths: Sequence[str],
    deps: Sequence[Dependency],
    issues: list[str],
) -> None:
    """Give every undefined name the contract already declared its import.

    The index is built from the contract's ``deps`` — their *signatures*, which
    are the contract's own statement of what each dependency exposes, and the
    only thing this step is permitted to write down. A name ruff cannot resolve
    and the contract never mentioned is a real failure and stays one: guessing
    a module for it would turn a legible rejection into an import that does not
    resolve.
    """
    index = _declared_modules(deps)
    if not index:
        return
    for path, names in _undefined_names(repo, ruff, paths, issues).items():
        wanted = sorted(
            f"from {index[name]} import {name}" for name in names if name in index
        )
        if wanted:
            _insert_imports(repo / path, wanted, issues)


def _declared_modules(deps: Sequence[Dependency]) -> dict[str, str]:
    """Name → module, over every dependency the contract states.

    First declaration wins, matching the order the contract lists them in: two
    dependencies exporting one name is the contract's ambiguity to resolve, and
    picking the later one would make the repair depend on iteration order.
    """
    index: dict[str, str] = {}
    for dep in deps:
        module = _module_of(dep.path)
        if module is None:
            continue
        for name in _declared_names(dep.signature):
            index.setdefault(name, module)
    return index


def _declared_names(signature: str) -> tuple[str, ...]:
    """The names a declared signature defines, parsed rather than matched.

    A signature is a header without a body, so it is completed with a
    placeholder until it parses — ``def f(x) -> None`` and ``class C(B):`` need
    different endings, and a signature that is already whole needs none. A
    signature that parses under none of them is not a declaration of a name and
    contributes nothing: the contract said something this step cannot read, and
    inventing a name from it is the one thing it must not do.
    """
    for completion in ("", ": ...", " ..."):
        try:
            tree = ast.parse(signature + completion)
        except SyntaxError:
            continue
        names = tuple(
            node.name
            for node in tree.body
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        )
        if names:
            return names
    return ()


def _module_of(path: str) -> str | None:
    """The dotted module a repo-relative ``.py`` path is imported as.

    ``None`` where the path cannot name a module — a suffix that is not
    ``.py``, or a directory segment that is not an identifier (``my-pkg/x.py``).
    An import line that does not resolve is a new failure rather than a repair,
    so an unnameable path is skipped instead of guessed at.
    """
    if not path.endswith(".py"):
        return None
    relative = path
    for root in _SOURCE_ROOTS:
        if relative.startswith(root):
            relative = relative[len(root) :]
            break
    parts = relative.removesuffix(".py").split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]  # a package is imported by its directory
    if not parts or not all(part.isidentifier() for part in parts):
        return None
    return ".".join(parts)


def _undefined_names(
    repo: Path, ruff: str, paths: Sequence[str], issues: list[str]
) -> dict[str, set[str]]:
    """Per file, the names ruff says are undefined.

    ``--select F821`` asks ruff one question rather than reading whatever the
    repository happens to have enabled: the repair needs the undefined names
    specifically, and a project that never selected ``F`` still has undefined
    names worth an import. JSON rather than the human format for the same
    reason the lint rung uses it — a message layout is not an interface.
    """
    proc = subprocess.run(
        [
            ruff,
            "check",
            "--select",
            "F821",
            "--output-format=json",
            "--force-exclude",
            "--",
            *paths,
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        env=plain_env(),
        check=False,
    )
    if proc.returncode not in _REPORTING:
        issues.append(
            f"repair: {RUFF} check --select F821 exited {proc.returncode} — "
            f"{_first_line(proc.stderr)}"
        )
        return {}
    try:
        diagnostics = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        # ruff promised JSON on a reporting exit code and did not deliver it.
        # Nothing here is trustworthy enough to write an import from.
        issues.append(f"repair: {RUFF} F821 output is not JSON")
        return {}

    # ruff prints absolute filenames; the change set carries repo-relative
    # ones. Resolving both sides is what maps a diagnostic back to its file.
    by_resolved = {(repo / path).resolve(): path for path in paths}
    undefined: dict[str, set[str]] = {}
    for diagnostic in diagnostics:
        path = by_resolved.get(Path(diagnostic["filename"]).resolve())
        match = _UNDEFINED_NAME.search(diagnostic.get("message", ""))
        if path is not None and match is not None:
            undefined.setdefault(path, set()).add(match.group(1))
    return undefined


def _insert_imports(path: Path, imports: Sequence[str], issues: list[str]) -> None:
    """Splice import lines into a file below whatever already imports there."""
    source = _read_text(path)
    if source is None:
        issues.append(f"repair: {path.name} could not be decoded — no import inserted")
        return
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # A file that does not parse is a syntax rejection, which is the
        # gate's to report and a model's to fix. Editing it blind would only
        # move the error.
        return
    lines = parser_lines(source)
    present = {line.strip() for line in lines}
    ending = _terminator(source)
    fresh = [f"{line}{ending}" for line in imports if line not in present]
    if not fresh:
        return
    anchor = _import_anchor(tree)
    lines[anchor:anchor] = fresh
    _write_text(path, "".join(lines))


def _terminator(source: str) -> str:
    """The line ending ``source`` already uses, or ``\\n`` for a file with none.

    An inserted line has to end the way the file's other lines end. A ``\\n``
    spliced into a CRLF file leaves a mixed-ending file behind, which the next
    formatter normalises — so a repair that added one import is recorded as
    having rewritten every line in the file.
    """
    found = LINE_END.search(source)
    return found.group(0) if found else "\n"


def _import_anchor(tree: ast.Module) -> int:
    """The line index to insert imports at: after the docstring and imports.

    Placing them at line 0 would push a module docstring down a line and demote
    it to a plain string expression — valid Python that has quietly deleted the
    module's documentation. Stopping at the first statement that is neither
    keeps the block where a reader expects it, and where ``__future__`` imports
    (which must come first) already are.
    """
    body = list(tree.body)
    anchor = 0
    if body and _is_docstring(body[0]):
        anchor = body[0].end_lineno or anchor
        body = body[1:]
    for node in body:
        if not isinstance(node, ast.Import | ast.ImportFrom):
            break
        anchor = node.end_lineno or anchor
    return anchor


def _is_docstring(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


# --- io -------------------------------------------------------------------


def _read_bytes(path: Path) -> bytes | None:
    """The file's exact bytes, or ``None`` if it cannot be read.

    Bytes, not text: "did the repair change this file" has to be answered on
    what is on disk, and a decode step could report two different files as the
    same one.
    """
    try:
        return path.read_bytes()
    except OSError:
        return None


def _read_text(path: Path) -> str | None:
    """The file as text with its line endings intact, or ``None`` if unreadable.

    ``newline=""`` turns off universal-newline translation, which is not a
    detail: with it on, a CRLF file arrives as LF, is written back as LF, and a
    repair asked to add one import has rewritten every line ending in the file —
    the whole file reported as repaired, and every line of it in the diff a
    reviewer reads. The parser is handed this same string and numbers its lines
    over ``\\r\\n`` and ``\\r`` exactly as it does over ``\\n``.
    """
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            return handle.read()
    except (OSError, UnicodeDecodeError):
        return None


def _write_text(path: Path, source: str) -> None:
    """Write ``source`` back as it is, line endings included.

    ``newline=""`` for the other half of :func:`_read_text`'s reason: the default
    translates every ``\\n`` written to ``os.linesep``, so on a platform whose
    linesep is not ``\\n`` even a file read without translation would come back
    with its endings changed.
    """
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(source)


def _first_line(stderr: str) -> str:
    for line in stderr.splitlines():
        if line.strip():
            return line.strip()
    return "no output"
