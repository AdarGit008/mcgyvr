"""The typecheck rung, plus the AST compliance rules that ride with it.

:class:`TypeCheck` runs the type checker a repo declares over the Python files a
changeset touches, keeps only the diagnostics this diff is responsible for — the
lines the worker added, and faults absent from the same file at the base commit —
and turns them into findings. :func:`compliance_findings` covers what no checker
reports as an error: mutation of a caller-owned parameter, imports that cannot
import, and deprecated ``typing`` spellings, each sorted onto the rejecting
``structure`` axis or the observational ``style`` one.
"""

from __future__ import annotations

import ast
import io
import re
import shlex
import subprocess
import tarfile
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from mcgyvr.gate.adapter import (
    HostRunner,
    ToolFailedError,
    ToolRunner,
    plain_env,
    trusted_stdout,
)
from mcgyvr.gate.changeset import ChangeSet
from mcgyvr.gate.findings import Finding

if TYPE_CHECKING:  # type-only: the adapter imports this module at runtime
    from mcgyvr.gate.adapters.python import PythonAdapter

#: The check name attached to every finding this rung produces.
CHECK = "typecheck"

#: Findings land on one of two axes: ``structure`` faults reject the work and
#: send it back, ``style`` faults are printed as observations and leave the
#: verdict alone.
CORRECTNESS = "structure"

#: The observational axis. A finding filed here is real and line-attributed but
#: never rejects the work, so a worker is not charged a rung of the ladder for a
#: prose-level preference.
STYLE = "style"

#: Code shared by every parameter-mutation finding, whichever axis it lands on.
PARAM_MUTATION = "PARAM-MUTATION"


class ParamMutation(StrEnum):
    """What to do when a function mutates an object its caller owns.

    ``REFUSE`` reports the mutation on the rejecting ``structure`` axis, ``REPORT``
    keeps those findings on ``style`` instead, and ``SKIP`` turns the rule off.
    """

    REFUSE = "refuse"
    REPORT = "report"
    SKIP = "skip"


#: Ruff codes demoted from the rejecting ``lint`` axis to ``style`` under the
#: product's default rule selection — a repo that states no ruff config of its
#: own. Both are default rules there: ``UP006``
#: (``List`` where ``list`` would do) and ``UP035`` (import from a deprecated
#: location). They describe code that runs, in a dialect the project has moved
#: away from, which is an observation rather than a defect. ``UP035`` also covers
#: a fault that is not a spelling: ``from collections import Mapping`` stops
#: importing on 3.10, where the re-export shim was removed. That line is a
#: compliance finding (see :func:`unimportable_lines`), and the lint path
#: re-promotes it rather than demoting it with the rest of the code.
STYLE_LINT_CODES = frozenset({"UP006", "UP035"})

#: Wall-clock budget for a single checker invocation. Exceeding it is an
#: environment fault, not a finding against the worker's code.
TYPECHECK_TIMEOUT_S = 300.0

#: Exit codes that mean "the checker ran and this is its report": 0 for a clean
#: pass, 1 for diagnostics found. Any other code is a broken tool, and
#: :func:`trusted_stdout` raises instead of reading a verdict out of it.
_REPORTING = (0, 1)

#: ``path:line[:col[:end]]: severity: message`` — the format mypy and other
#: compiler-style tools print. The line is what a finding is attributed to; up to
#: three extra numeric segments (column, end line, end column) may follow it.
_DIAGNOSTIC = re.compile(
    r"^(?P<path>[^:]+):(?P<line>\d+)(?::\d+){0,3}: "
    r"(?P<severity>error|warning|note): (?P<message>.*)$"
)

#: pyright's format: ``path:line:col - severity: message``. It needs its own
#: pattern because the column is mandatory, a spaced hyphen separates location from
#: severity, and pyright says ``information`` where the others say ``note``.
_PYRIGHT_DIAGNOSTIC = re.compile(
    r"^\s*(?P<path>[^:]+):(?P<line>\d+):\d+ - "
    r"(?P<severity>error|warning|information): (?P<message>.*)$"
)

#: The code a checker appends to its message: ruff and mypy use ``[code]``,
#: pyright uses ``(reportRule)``.
_CODE = re.compile(r"\s+(?:\[([a-z0-9-]+)\]|\((report[A-Za-z]+)\))$")

#: Only ``error`` rejects. ``warning``, ``note`` and ``information`` come out of
#: the same parsers but describe code that still runs, so they are never collected.
_REJECTING = frozenset({"error"})


def _python_adapter() -> PythonAdapter:
    """Return a Python adapter with the default configuration.

    The import is local because ``mcgyvr.gate.adapters.python`` imports this module
    for its compliance helpers, so a module-level import would be circular.
    """
    from mcgyvr.gate.adapters.python import PythonAdapter

    return PythonAdapter()


class TypeCheckTimeoutError(ToolFailedError):
    """The declared checker did not finish inside the configured timeout."""


@dataclass(frozen=True)
class TypeCheck:
    """One repository's typecheck rung.

    ``repo`` is the tree the checker reads, ``timeout`` bounds each invocation, and
    ``runner`` is where those invocations and the base-tree extraction happen: the
    host, or a sandbox whose reported paths come back through ``host_path``.
    """

    repo: Path
    timeout: float | None = TYPECHECK_TIMEOUT_S
    runner: ToolRunner = field(default_factory=HostRunner)

    def declared_command(self) -> list[str] | None:
        """Return the command the repo declares for type checking, or None.

        No declaration means the rung has nothing to run and stays silent.
        """
        return _python_adapter().locate_type_check_command(self.repo)

    def run(self, changeset: ChangeSet) -> list[Finding]:
        """Return the findings the checker reports against this changeset.

        Only Python files the changeset touches and that still exist on disk are
        checked. Diagnostics attributed to lines the worker added become findings
        directly; diagnostics anywhere else in those files are compared against the
        same file at the base commit, so a fault that was already there is not
        charged to this diff. The result is sorted by path, then line.
        """
        command = self.declared_command()
        if command is None:
            return []
        targets = [
            change
            for change in _python_adapter().owned(changeset.files)
            if (self.repo / change.path).is_file()
        ]
        if not targets:
            return []

        tool = command[0]
        paths = [change.path for change in targets]
        stdout, exit_code = self._check(command, tool, self.repo, paths)
        reported = _diagnostics(stdout, paths, self.repo, self.runner.host_path)
        # What ran over the worker's tree, as data each finding carries: the
        # command line — the declared checker and the repo-relative files — and
        # the exit it reported with.
        ran = shlex.join([*command, *paths])

        added = {change.path: change.added_lines for change in targets}

        def worker_line(d: _Diagnostic) -> bool:
            return d.line in added.get(d.path, frozenset())

        on_added = [d for d in reported if worker_line(d)]
        elsewhere = [d for d in reported if not worker_line(d)]
        if elsewhere:
            on_added.extend(self._new_since_base(elsewhere, changeset, command, tool))
        return [
            _finding(d, command=ran, exit_code=exit_code)
            for d in sorted(on_added, key=lambda d: (d.path, d.line))
        ]

    def _check(
        self, command: Sequence[str], tool: str, repo: Path, paths: Sequence[str]
    ) -> tuple[str, int]:
        """Run the checker over ``paths`` and return its stdout and exit code.

        A timeout is an environment fault, as is an exit code outside
        ``_REPORTING``. Exit 1 with no readable diagnostic in the output is treated
        the same way: the tool did complain, in a shape this rung cannot parse.
        """
        try:
            proc = self.runner.run(
                tool, [*command[1:], *paths], repo, timeout=self.timeout
            )
        except subprocess.TimeoutExpired as exc:
            # Out of time. Raised as an environment fault that names the tool and
            # the budget, because nothing about the worker's code was learned; -1
            # stands in for the exit code that was never produced.
            raise TypeCheckTimeoutError(
                tool, -1, f"timed out after {self.timeout:g}s"
            ) from exc
        # Anything outside the reporting exits — a crash, a bad config, a missing
        # dependency — raises here, with the tool's first stderr line as the detail.
        stdout = trusted_stdout(tool, proc, expected=_REPORTING)
        # The tool exited 1 but printed nothing this module can read: a traceback on
        # stderr, a config complaint, an unknown flag. Reported as a broken tool,
        # since otherwise an unparsed report would look exactly like a clean pass.
        if proc.returncode == 1 and not any(
            _rejecting(raw) for raw in stdout.splitlines()
        ):
            raise ToolFailedError(
                tool,
                proc.returncode,
                "it reported errors in a form this rung cannot read",
            )
        return stdout, proc.returncode

    def _new_since_base(
        self,
        elsewhere: Sequence[_Diagnostic],
        changeset: ChangeSet,
        command: Sequence[str],
        tool: str,
    ) -> list[_Diagnostic]:
        """Return the off-diff diagnostics this changeset actually introduced.

        The touched files are materialised at the changeset's base commit and checked
        again. A diagnostic survives when the base tree has no such file at all, or
        when it occurs more times now than it did there — a count rather than a set
        comparison, so a fault the diff added a second copy of is still caught.
        """
        with _base_tree(changeset, self.runner) as root:
            present = sorted({d.path for d in elsewhere if (root / d.path).is_file()})
            was: Counter[tuple[str, str | None, str]] = Counter()
            if present:
                was.update(
                    d.key
                    for d in _diagnostics(
                        self._check(command, tool, root, present)[0],
                        present,
                        root,
                        self.runner.host_path,
                    )
                )
            seen: Counter[tuple[str, str | None, str]] = Counter()
            caused: list[_Diagnostic] = []
            for diagnostic in elsewhere:
                if not (root / diagnostic.path).is_file():
                    # The file does not exist at the base commit, so nothing in it
                    # can predate this changeset.
                    caused.append(diagnostic)
                    continue
                seen[diagnostic.key] += 1
                if seen[diagnostic.key] > was[diagnostic.key]:
                    caused.append(diagnostic)
            return caused


@dataclass(frozen=True)
class _Diagnostic:
    """One error-severity diagnostic parsed out of a checker's output."""

    path: str
    line: int
    code: str | None
    message: str

    @property
    def key(self) -> tuple[str, str | None, str]:
        """Identity used to match a diagnostic against the same fault at the base.

        The line number is left out on purpose: code the diff inserted above a
        pre-existing fault moves it without making it new.
        """
        return (self.path, self.code, self.message)


def _finding(
    diagnostic: _Diagnostic, *, command: str | None = None, exit_code: int | None = None
) -> Finding:
    return Finding(
        check=CHECK,
        path=diagnostic.path,
        line=diagnostic.line,
        code=diagnostic.code,
        message=diagnostic.message,
        command=command,
        exit_code=exit_code,
    )


def _diagnostics(
    stdout: str,
    paths: Sequence[str],
    repo: Path,
    host_path: Callable[[str], Path] = Path,
) -> list[_Diagnostic]:
    """Return the error diagnostics in ``stdout`` that belong to ``paths``.

    An absolute path goes through ``host_path`` first (a sandbox reports paths from
    its own view of the filesystem) and is then made repo-relative; a line whose
    path falls outside ``paths`` is dropped. A trailing ``[code]`` or
    ``(reportRule)`` is split off the message and kept as the finding's code.
    """
    wanted = set(paths)
    diagnostics: list[_Diagnostic] = []
    for raw in stdout.splitlines():
        match = _rejecting(raw)
        if match is None:
            continue
        printed = match["path"]
        if Path(printed).is_absolute():
            printed = str(host_path(printed))
        path = _relative_to_repo(printed, repo)
        if path not in wanted:
            continue
        message = match["message"].strip()
        code = _CODE.search(message)
        diagnostics.append(
            _Diagnostic(
                path=path,
                line=int(match["line"]),
                code=(code.group(1) or code.group(2)) if code else None,
                message=_CODE.sub("", message),
            )
        )
    return diagnostics


def _rejecting(raw: str) -> re.Match[str] | None:
    """Return the match when this line is an error-severity diagnostic.

    Both supported formats are tried here. Warnings, notes and pyright's
    ``information`` are dropped at this point, so nothing downstream has to check
    severity again.
    """
    match = _DIAGNOSTIC.match(raw) or _PYRIGHT_DIAGNOSTIC.match(raw)
    if match is None or match["severity"] not in _REJECTING:
        return None
    return match


@contextmanager
def _base_tree(changeset: ChangeSet, runner: ToolRunner) -> Iterator[Path]:
    """Yield a scratch directory holding the changeset's base tree.

    The tree is unpacked from ``git archive`` of the base commit. When the archive
    fails — an unborn base, a missing ref — the directory is yielded empty, and
    every diagnostic in a touched file then counts as new.
    """
    with runner.scratch() as root:
        archive = subprocess.run(
            ["git", "archive", "--format=tar", changeset.base],
            cwd=changeset.repo,
            capture_output=True,
            env=plain_env(),
            check=False,
        )
        if archive.returncode != 0:
            yield root  # empty: no base copy for a fault to be inherited from
            return
        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
            tar.extractall(root, filter="data")
        yield root


def _relative_to_repo(path: str, repo: Path) -> str:
    """Return ``path`` as a repo-relative POSIX path.

    An absolute path inside ``repo`` is made relative; one outside it stays
    absolute, so it cannot silently match a repo file that happens to end the same
    way. A leading ``./`` on a relative path is stripped.
    """
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            return candidate.relative_to(repo).as_posix()
        except ValueError:
            return candidate.as_posix()
    return candidate.as_posix().removeprefix("./")


# The rules below read the worker's syntax tree for faults no checker reports as
# an error. They share one idea of ownership: ``owned`` holds the parameter names
# that still alias an object the caller passed in, and it shrinks at every
# rebinding, shadowing and scope boundary. A mutation is only a fault while the
# name really does reach the caller's object.

#: Methods that change their receiver in place. Called on an ``owned`` name, they
#: mutate data the caller is still holding.
_MUTATING_METHODS = frozenset(
    {
        "append",
        "extend",
        "insert",
        "remove",
        "pop",
        "clear",
        "sort",
        "reverse",
        "update",
        "setdefault",
        "add",
        "discard",
        "popitem",
    }
)

#: The contract is the escape hatch. When the task asks for a parameter to be
#: changed in place, mutating it is what was requested, and the rule stands down for
#: the whole file: prose is the only statement of intent available, and it routinely
#: says "mutate the list you are given" for exactly the case this rule would
#: otherwise reject. The ask is read from that prose rather than a marker because the
#: contract is written by a model; the pattern is narrow, and a negation among the
#: few words before the match ("do not mutate") turns it off.
_INPLACE_ASK = re.compile(r"\bin[- ]place\b|\bmutat(?:e|es|ion|ing)\b", re.IGNORECASE)

#: Words that turn an in-place request into a prohibition. Only the words just
#: before the match are inspected, which is where English puts the negation.
_NEGATION = frozenset(
    {"not", "no", "never", "without", "don't", "dont", "cannot", "can't", "cant"}
)

#: ``self`` and ``cls`` are not caller-owned: mutating them is how a method does
#: its work.
_NOT_CALLER_OWNED = frozenset({"self", "cls"})

#: The abstract base classes ``collections`` re-exported from ``collections.abc`` as
#: a compatibility shim through 3.9, plus the deprecated ``ByteString``. Importing
#: any of them from ``collections`` raises ImportError on every interpreter this
#: project supports — on 3.10 and later because the shim is gone — so a line that
#: does it cannot run.
_MOVED_TO_COLLECTIONS_ABC = frozenset(
    {
        "AsyncGenerator",
        "AsyncIterable",
        "AsyncIterator",
        "Awaitable",
        "ByteString",
        "Callable",
        "Collection",
        "Container",
        "Coroutine",
        "Generator",
        "Hashable",
        "ItemsView",
        "Iterable",
        "Iterator",
        "KeysView",
        "Mapping",
        "MappingView",
        "MutableMapping",
        "MutableSequence",
        "MutableSet",
        "Reversible",
        "Sequence",
        "Set",
        "Sized",
        "ValuesView",
    }
)

#: Deprecated spellings and the form to use instead: the abstract base classes that
#: live in ``collections.abc``, the builtin containers, and the stdlib types that
#: replaced the rest. A deprecated spelling still runs, so a hit here is style. The
#: same names imported from ``collections`` do not run at all, and
#: :func:`unimportable_lines` reports those on the structure axis.
_DEPRECATED_TYPING: dict[str, str] = {
    # The abstract base classes live in collections.abc; the collections module
    # only re-exported them, and stopped doing so in 3.10.
    **{name: f"collections.abc.{name}" for name in _MOVED_TO_COLLECTIONS_ABC},
    "List": "list",
    "Dict": "dict",
    "Set": "set",
    "Tuple": "tuple",
    "FrozenSet": "frozenset",
    "Type": "type",
    "DefaultDict": "collections.defaultdict",
    "Deque": "collections.deque",
    "OrderedDict": "collections.OrderedDict",
    "Counter": "collections.Counter",
    "ChainMap": "collections.ChainMap",
    "ContextManager": "contextlib.AbstractContextManager",
    "AsyncContextManager": "contextlib.AbstractAsyncContextManager",
    "Pattern": "re.Pattern",
    "Match": "re.Match",
}


def unimportable_lines(source: str | None) -> dict[int, str]:
    """Return ``{line: message}`` for imports that cannot import.

    Only ``from collections import ...`` lines naming a member of
    :data:`_MOVED_TO_COLLECTIONS_ABC` are reported. Source that does not parse
    yields no hits; the parse error itself is the syntax check's finding.
    """
    if source is None:
        return {}
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return {}
    return _unimportable(tree)


def _unimportable(tree: ast.Module) -> dict[int, str]:
    """Return ``{lineno: message}`` for each unimportable ``from collections`` line.

    One entry per importing statement, covering every moved name it names.
    """
    hits: dict[int, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module != "collections":
            continue
        moved = [a.name for a in node.names if a.name in _MOVED_TO_COLLECTIONS_ABC]
        if moved:
            hits[node.lineno] = _unimportable_verdict(moved)
    return hits


def _unimportable_verdict(names: Sequence[str]) -> str:
    """Return the finding message for a ``from collections`` line naming ``names``."""
    return (
        f"'from collections import {', '.join(names)}' raises ImportError on "
        f"Python 3.10 and later — collections re-exported the collections.abc "
        f"names as a shim until 3.9 and stopped; import them from "
        f"collections.abc"
    )


def deprecated_typing_import_lines(source: str | None) -> frozenset[int]:
    """Return the line numbers importing a deprecated spelling from ``typing``.

    Unparseable source yields an empty set, as in :func:`unimportable_lines`.
    """
    if source is None:
        return frozenset()
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return frozenset()
    return _deprecated_typing_imports(tree)


def _deprecated_typing_imports(tree: ast.Module) -> frozenset[int]:
    """Return the lines of ``from typing import ...`` naming a deprecated spelling.

    ``import typing`` followed by ``typing.List`` is caught by :func:`_type_form`,
    not here.
    """
    return frozenset(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "typing"
        and any(alias.name in _DEPRECATED_TYPING for alias in node.names)
    )


def compliance_findings(
    tree: ast.Module,
    path: str,
    added_lines: frozenset[int],
    *,
    contract_text: str = "",
    param_mutation: ParamMutation = ParamMutation.REFUSE,
) -> list[Finding]:
    """Return the AST compliance findings that fall on the worker's added lines.

    Three rules run. Deprecated ``typing`` spellings are always ``style``.
    Parameter mutation is ``structure`` unless the mode is ``REPORT``, absent under
    ``SKIP``, and suppressed when the contract asks for in-place change. Imports
    that cannot import are always ``structure``. Only findings whose line is in
    ``added_lines`` survive, so the worker is never charged for code it did not
    touch.
    """
    style = [
        Finding(check=STYLE, path=path, line=line, code="TYPE-FORM", message=message)
        for line, message in _type_form(tree)
    ]
    mutation_axis = STYLE if param_mutation == ParamMutation.REPORT else CORRECTNESS
    mutations = [
        Finding(
            check=mutation_axis,
            path=path,
            line=line,
            code=PARAM_MUTATION,
            message=message,
        )
        for line, message in (
            []
            if param_mutation == ParamMutation.SKIP
            else _param_mutation(tree, contract_text)
        )
    ]
    unimportable = [
        Finding(
            check=CORRECTNESS,
            path=path,
            line=line,
            code="UNIMPORTABLE",
            message=message,
        )
        for line, message in sorted(_unimportable(tree).items())
    ]
    return [f for f in (*mutations, *unimportable, *style) if f.line in added_lines]


def _type_form(tree: ast.Module) -> list[tuple[int, str]]:
    """Return ``(line, message)`` for every deprecated ``typing`` spelling.

    Both spellings are found: ``from typing import List`` and ``typing.List``.
    """
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "typing":
            hits += [
                (node.lineno, _pinned_form(alias.name))
                for alias in node.names
                if alias.name in _DEPRECATED_TYPING
            ]
        elif (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "typing"
            and node.attr in _DEPRECATED_TYPING
        ):
            hits.append((node.lineno, _pinned_form(node.attr)))
    return hits


def _pinned_form(alias: str) -> str:
    return f"typing.{alias} — the pinned form is {_DEPRECATED_TYPING[alias]}[...]"


def _asks_for_mutation(contract_text: str) -> bool:
    """Return True when the contract asks, without a negation, for in-place change.

    A request anywhere in the prose suppresses the rule for the whole file.
    """
    for match in _INPLACE_ASK.finditer(contract_text):
        before = contract_text[: match.start()].lower()
        preceding = re.findall(r"[a-z']+", before)[-3:]
        if not any(word in _NEGATION for word in preceding):
            return True
    return False


def _param_mutation(tree: ast.Module, contract_text: str) -> list[tuple[int, str]]:
    """Return ``(line, message)`` for each mutation of a caller-owned parameter.

    Empty when the contract asked for the mutation, because the code then does what
    it was told, and empty when no function has a caller-owned parameter to mutate.
    """
    if _asks_for_mutation(contract_text):
        return []
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            hits += _mutations_in(node)
    # A line can be recorded more than once — ``a[k] = b[k] = 1`` yields one hit
    # per target — so duplicates are collapsed, and sorting keeps the report order
    # stable across runs.
    return sorted(set(hits))


def _mutations_in(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[tuple[int, str]]:
    """Return the mutation hits inside one function, seeded with its parameters."""
    owned = _parameters(func)
    if not owned:
        return []
    hits: list[tuple[int, str]] = []
    _scan(func.body, owned, hits)
    return hits


def _parameters(func: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Return the parameter names a caller could have handed an object to.

    Positional-only, positional-or-keyword and keyword-only parameters count.
    ``self`` and ``cls`` do not, and neither do ``*args`` and ``**kwargs``, whose
    names bind a tuple and a dict built from the call.
    """
    args = func.args
    return {
        arg.arg
        for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs)
        if arg.arg not in _NOT_CALLER_OWNED
    }


def _scan(
    body: Sequence[ast.stmt], owned: set[str], hits: list[tuple[int, str]]
) -> set[str]:
    """Scan ``body`` in order and return the names still owned after it."""
    for statement in body:
        owned = _scan_statement(statement, owned, hits)
    return owned


def _scan_statement(
    node: ast.stmt, owned: set[str], hits: list[tuple[int, str]]
) -> set[str]:
    """Scan one statement and return the owned names after it.

    Expressions report their mutation hits into ``hits``; statements that bind
    names drop those names, because the name no longer refers to what the caller
    passed. Branches, loops and ``try`` return the union of the states they can
    reach, and an unhandled statement kind is walked for the expressions among its
    children.
    """
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        return _scan_nested_function(node, owned, hits)
    if isinstance(node, ast.ClassDef):
        for expr in (
            *node.decorator_list,
            *node.bases,
            *(keyword.value for keyword in node.keywords),
        ):
            _report(expr, owned, hits)
        _scan(node.body, owned, hits)
        return owned - {node.name}
    if isinstance(node, ast.If):
        return _scan_branches(node.test, [node.body, node.orelse], owned, hits)
    if isinstance(node, ast.For | ast.AsyncFor):
        return _scan_for(node, owned, hits)
    if isinstance(node, ast.While):
        _report(node.test, owned, hits)
        _scan(node.body, owned, hits)  # a while body may run zero times
        _scan(node.orelse, owned, hits)
        return owned
    if isinstance(node, ast.With | ast.AsyncWith):
        return _scan_with(node, owned, hits)
    if isinstance(node, ast.Try | ast.TryStar):
        return _scan_try(node, owned, hits)
    if isinstance(node, ast.Match):
        return _scan_match(node, owned, hits)
    if isinstance(node, ast.Assign):
        for expr in (node.value, *node.targets):
            _report(expr, owned, hits)
        hits += _writes_into(node.lineno, node.targets, owned, "assignment into")
        return owned - set().union(*map(_target_names, node.targets), set())
    if isinstance(node, ast.AnnAssign):
        if node.value is None:  # annotation only: nothing is bound or written
            return owned
        for expr in (node.value, node.target):
            _report(expr, owned, hits)
        hits += _writes_into(node.lineno, [node.target], owned, "assignment into")
        return owned - _target_names(node.target)
    if isinstance(node, ast.AugAssign):
        for expr in (node.value, node.target):
            _report(expr, owned, hits)
        hits += _writes_into(node.lineno, [node.target], owned, "assignment into")
        return owned - _target_names(node.target)
    if isinstance(node, ast.Delete):
        for expr in node.targets:
            _report(expr, owned, hits)
        hits += _writes_into(node.lineno, node.targets, owned, "del on")
        return owned - set().union(*map(_target_names, node.targets), set())
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.expr):
            _report(child, owned, hits)
    return owned


def _scan_nested_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    owned: set[str],
    hits: list[tuple[int, str]],
) -> set[str]:
    """Scan a nested ``def`` and return the owned names after the statement.

    The def's arguments shadow outer names inside its body, its decorators and
    defaults still evaluate in the enclosing scope and are scanned there, and the
    function's own name stops aliasing anything once it is bound.
    """
    args = node.args
    shadowed = {
        arg.arg
        for arg in (
            *args.posonlyargs,
            *args.args,
            *args.kwonlyargs,
            *(extra for extra in (args.vararg, args.kwarg) if extra is not None),
        )
    }
    for expr in (
        *node.decorator_list,
        *args.defaults,
        *(default for default in args.kw_defaults if default is not None),
    ):
        _report(expr, owned, hits)
    _scan(node.body, owned - shadowed, hits)
    return owned - {node.name}


def _scan_branches(
    test: ast.expr | None,
    arms: Sequence[Sequence[ast.stmt]],
    owned: set[str],
    hits: list[tuple[int, str]],
) -> set[str]:
    """Scan every arm from the same starting state and return the states reached.

    An arm that always returns, raises, breaks or continues contributes nothing: no
    code after the statement runs with its bindings. Arms that fall through are
    unioned, so a name stays owned while any live path still owns it, and an empty
    arm passes the state through unchanged.
    """
    if test is not None:
        _report(test, owned, hits)
    reached: list[set[str]] = []
    for arm in arms:
        if not arm:  # no else body: the state passes through unchanged
            reached.append(owned)
            continue
        after = _scan(arm, owned, hits)
        if _falls_through(arm):
            reached.append(after)
    return set().union(*reached, set()) if reached else owned


def _scan_for(
    node: ast.For | ast.AsyncFor, owned: set[str], hits: list[tuple[int, str]]
) -> set[str]:
    """Scan a ``for`` loop and return the owned names after it.

    When the loop iterates an owned object, its targets hand back pieces of that
    object and are owned too; otherwise they shadow. The body and the ``else`` are
    scanned with that state, and it is also the state after the loop, since the
    loop may run zero times.
    """
    _report(node.iter, owned, hits)
    names = _target_names(node.target)
    after = owned | names if _root_name(node.iter) in owned else owned - names
    _scan(node.body, after, hits)
    _scan(node.orelse, after, hits)
    return after


def _scan_with(
    node: ast.With | ast.AsyncWith, owned: set[str], hits: list[tuple[int, str]]
) -> set[str]:
    """Scan a ``with`` block, treating each ``as`` target as a new binding.

    Context expressions run in the enclosing scope; the targets shadow owned names
    for the length of the block.
    """
    bound: set[str] = set()
    for item in node.items:
        _report(item.context_expr, owned, hits)
        if item.optional_vars is not None:
            bound |= _target_names(item.optional_vars)
    return _scan(node.body, owned - bound, hits)


def _scan_try(
    node: ast.Try | ast.TryStar, owned: set[str], hits: list[tuple[int, str]]
) -> set[str]:
    """Scan a ``try`` statement and return the states that reach the code after.

    The body's state counts when the ``else`` (or, without one, the body) can fall
    through; each handler starts from the state before the ``try`` minus its ``as``
    name and counts when it can fall through. With no reachable path the entry state
    is kept rather than guessed away.
    """
    after_body = _scan(node.body, owned, hits)
    after_body = _scan(node.orelse, after_body, hits)
    reached: list[set[str]] = []
    if _falls_through(node.orelse or node.body):
        reached.append(after_body)
    for handler in node.handlers:
        if handler.type is not None:
            _report(handler.type, owned, hits)
        caught = owned - ({handler.name} if handler.name else set())
        after_handler = _scan(handler.body, caught, hits)
        if _falls_through(handler.body):
            reached.append(after_handler)
    after = set().union(*reached, set()) if reached else owned
    # ``finally`` runs from every path, so it is scanned with the state on entry
    # unioned with the states the body and handlers reached.
    return _scan(node.finalbody, after | owned, hits) if node.finalbody else after


def _scan_match(
    node: ast.Match, owned: set[str], hits: list[tuple[int, str]]
) -> set[str]:
    """Scan a ``match`` statement and return the states that reach past it.

    Each case removes the names its pattern binds. The state before the match is
    also a reached state unless the last case cannot fail to match — a bare
    ``case _`` with no guard — so an unmatched subject is accounted for.
    """
    _report(node.subject, owned, hits)
    reached: list[set[str]] = []
    for case in node.cases:
        inside = owned - _pattern_names(case.pattern)
        if case.guard is not None:
            _report(case.guard, inside, hits)
        after = _scan(case.body, inside, hits)
        if _falls_through(case.body):
            reached.append(after)
    if not node.cases or not _always_matches(node.cases[-1]):
        reached.append(owned)
    return set().union(*reached, set()) if reached else owned


def _always_matches(case: ast.match_case) -> bool:
    """Return True when this case is an unguarded bare ``case _:``."""
    return (
        case.guard is None
        and isinstance(case.pattern, ast.MatchAs)
        and case.pattern.pattern is None
    )


def _pattern_names(pattern: ast.pattern) -> set[str]:
    """Return every name a pattern binds, including ``as`` and ``*rest`` names."""
    names: set[str] = set()
    for node in ast.walk(pattern):
        for attribute in ("name", "rest"):
            bound = getattr(node, attribute, None)
            if isinstance(bound, str):
                names.add(bound)
    return names


def _falls_through(body: Sequence[ast.stmt]) -> bool:
    """Return True when execution can continue past ``body``.

    Only a final ``return``, ``raise``, ``break`` or ``continue`` stops it; a final
    ``if`` or ``with`` is judged by its own bodies, and anything else — including an
    empty body — falls through.
    """
    if not body:
        return True
    last = body[-1]
    if isinstance(last, ast.Return | ast.Raise | ast.Break | ast.Continue):
        return False
    if isinstance(last, ast.If):
        return _falls_through(last.body) or _falls_through(last.orelse)
    if isinstance(last, ast.With | ast.AsyncWith):
        return _falls_through(last.body)
    return True


def _report(node: ast.expr, owned: set[str], hits: list[tuple[int, str]]) -> None:
    """Record mutation hits found anywhere inside the expression ``node``."""
    _report_in_scope(node, owned, hits)


def _report_in_scope(
    node: ast.AST, owned: set[str], hits: list[tuple[int, str]]
) -> None:
    """Walk an expression and record mutations of ``owned`` names into ``hits``.

    Scopes are honoured: a lambda's parameters and the targets of a comprehension's
    generators shadow outer names inside their bodies, while defaults and the
    outermost iterable still evaluate in the enclosing scope. A call to a mutating
    method on an owned name is the hit this exists to find.
    """
    if isinstance(node, ast.Lambda):
        bound = _lambda_bound_names(node)
        # A lambda's defaults are evaluated where the lambda is written, so they
        # are scanned in the enclosing scope; only its body sees the parameters.
        for default in (*node.args.defaults, *node.args.kw_defaults):
            if default is not None:
                _report_in_scope(default, owned, hits)
        _report_in_scope(node.body, owned - bound, hits)
        return
    if isinstance(node, ast.ListComp | ast.SetComp | ast.GeneratorExp | ast.DictComp):
        _report_comprehension(node, owned, hits)
        return
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _MUTATING_METHODS
        and _root_name(node.func.value) in owned
    ):
        hits.append((node.lineno, _verdict(f".{node.func.attr}() on", node.func.value)))
    for child in ast.iter_child_nodes(node):
        _report_in_scope(child, owned, hits)


def _report_comprehension(
    node: ast.ListComp | ast.SetComp | ast.GeneratorExp | ast.DictComp,
    owned: set[str],
    hits: list[tuple[int, str]],
) -> None:
    """Walk a comprehension with its generator targets treated as new bindings.

    The first iterable evaluates in the enclosing scope; every later iterable, the
    ``if`` clauses and the element (or key and value) are inside the
    comprehension's own scope.
    """
    generators = node.generators
    _report_in_scope(generators[0].iter, owned, hits)
    scoped = owned
    for generator in generators:
        scoped = scoped - _target_names(generator.target)
    if isinstance(node, ast.DictComp):
        _report_in_scope(node.key, scoped, hits)
        _report_in_scope(node.value, scoped, hits)
    else:
        _report_in_scope(node.elt, scoped, hits)
    for index, generator in enumerate(generators):
        for condition in generator.ifs:
            _report_in_scope(condition, scoped, hits)
        if index != 0:
            _report_in_scope(generator.iter, scoped, hits)


def _lambda_bound_names(node: ast.Lambda) -> set[str]:
    """Return the names a lambda's argument list binds."""
    args = node.args
    names = {arg.arg for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs)}
    if args.vararg is not None:
        names.add(args.vararg.arg)
    if args.kwarg is not None:
        names.add(args.kwarg.arg)
    return names


def _writes_into(
    lineno: int, targets: Iterable[ast.expr], tracked: set[str], what: str
) -> list[tuple[int, str]]:
    """Return hits for targets that write into an owned object.

    Only subscript and attribute targets count — ``params["k"] = v``,
    ``item.field = v`` — because a plain name target only rebinds, and the name is
    dropped by the caller instead.
    """
    return [
        (lineno, _verdict(what, target))
        for target in targets
        if isinstance(target, ast.Subscript | ast.Attribute)
        and _root_name(target) in tracked
    ]


def _verdict(what: str, node: ast.expr) -> str:
    return (
        f"{what} parameter '{_root_name(node)}' — the caller still owns that "
        f"object and its next read is wrong"
    )


def _target_names(target: ast.expr) -> set[str]:
    """Return the names a target binds, looking through tuples, lists and stars."""
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, ast.Starred):
        return _target_names(target.value)
    if isinstance(target, ast.Tuple | ast.List):
        return set().union(*(_target_names(elt) for elt in target.elts), set())
    return set()


def _root_name(node: ast.expr) -> str | None:
    """Return the innermost name of an attribute or subscript chain, else None."""
    while isinstance(node, ast.Subscript | ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None
