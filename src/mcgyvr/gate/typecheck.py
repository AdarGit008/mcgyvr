""

from __future__ import annotations

import ast
import io
import re
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

if TYPE_CHECKING:  #le
    from mcgyvr.gate.adapters.python import PythonAdapter

#
CHECK = "typecheck"

#'s
#
#
CORRECTNESS = "structure"

#
#
#
#
#
#
STYLE = "style"

#
PARAM_MUTATION = "PARAM-MUTATION"


class ParamMutation(StrEnum):
    ""

    REFUSE = "refuse"
    REPORT = "report"
    SKIP = "skip"


#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
STYLE_LINT_CODES = frozenset({"UP006", "UP035"})

#
#
#
TYPECHECK_TIMEOUT_S = 300.0

#
#
#ng
#
_REPORTING = (0, 1)

#
#
#
#
_DIAGNOSTIC = re.compile(
    r"^(?P<path>[^:]+):(?P<line>\d+)(?::\d+){0,3}: "
    r"(?P<severity>error|warning|note): (?P<message>.*)$"
)

#
#
#
_PYRIGHT_DIAGNOSTIC = re.compile(
    r"^\s*(?P<path>[^:]+):(?P<line>\d+):\d+ - "
    r"(?P<severity>error|warning|information): (?P<message>.*)$"
)

#
#
_CODE = re.compile(r"\s+(?:\[([a-z0-9-]+)\]|\((report[A-Za-z]+)\))$")

#
#
#
_REJECTING = frozenset({"error"})


def _python_adapter() -> PythonAdapter:
    ""
    from mcgyvr.gate.adapters.python import PythonAdapter

    return PythonAdapter()


class TypeCheckTimeoutError(ToolFailedError):
    ""


@dataclass(frozen=True)
class TypeCheck:
    ""

    repo: Path
    timeout: float | None = TYPECHECK_TIMEOUT_S
    runner: ToolRunner = field(default_factory=HostRunner)

    def declared_command(self) -> list[str] | None:
        ""
        return _python_adapter().locate_type_check_command(self.repo)

    def run(self, changeset: ChangeSet) -> list[Finding]:
        ""
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
        stdout = self._check(command, tool, self.repo, paths)
        reported = _diagnostics(stdout, paths, self.repo, self.runner.host_path)

        added = {change.path: change.added_lines for change in targets}

        def worker_line(d: _Diagnostic) -> bool:
            return d.line in added.get(d.path, frozenset())

        on_added = [d for d in reported if worker_line(d)]
        elsewhere = [d for d in reported if not worker_line(d)]
        if elsewhere:
            on_added.extend(self._new_since_base(elsewhere, changeset, command, tool))
        return [_finding(d) for d in sorted(on_added, key=lambda d: (d.path, d.line))]

    def _check(
        self, command: Sequence[str], tool: str, repo: Path, paths: Sequence[str]
    ) -> str:
        ""
        try:
            proc = self.runner.run(
                tool, [*command[1:], *paths], repo, timeout=self.timeout
            )
        except subprocess.TimeoutExpired as exc:
            #
            #
            #
            #
            raise TypeCheckTimeoutError(
                tool, -1, f"timed out after {self.timeout:g}s"
            ) from exc
        #
        # a
        #
        #
        stdout = trusted_stdout(tool, proc, expected=_REPORTING)
        #
        #
        #
        #
        if proc.returncode == 1 and not any(
            _rejecting(raw) for raw in stdout.splitlines()
        ):
            raise ToolFailedError(
                tool,
                proc.returncode,
                "it reported errors in a form this rung cannot read",
            )
        return stdout

    def _new_since_base(
        self,
        elsewhere: Sequence[_Diagnostic],
        changeset: ChangeSet,
        command: Sequence[str],
        tool: str,
    ) -> list[_Diagnostic]:
        ""
        with _base_tree(changeset, self.runner) as root:
            present = sorted({d.path for d in elsewhere if (root / d.path).is_file()})
            was: Counter[tuple[str, str | None, str]] = Counter()
            if present:
                was.update(
                    d.key
                    for d in _diagnostics(
                        self._check(command, tool, root, present),
                        present,
                        root,
                        self.runner.host_path,
                    )
                )
            seen: Counter[tuple[str, str | None, str]] = Counter()
            caused: list[_Diagnostic] = []
            for diagnostic in elsewhere:
                if not (root / diagnostic.path).is_file():
                    #
                    #
                    caused.append(diagnostic)
                    continue
                seen[diagnostic.key] += 1
                if seen[diagnostic.key] > was[diagnostic.key]:
                    caused.append(diagnostic)
            return caused


@dataclass(frozen=True)
class _Diagnostic:
    ""

    path: str
    line: int
    code: str | None
    message: str

    @property
    def key(self) -> tuple[str, str | None, str]:
        ""
        return (self.path, self.code, self.message)


def _finding(diagnostic: _Diagnostic) -> Finding:
    return Finding(
        check=CHECK,
        path=diagnostic.path,
        line=diagnostic.line,
        code=diagnostic.code,
        message=diagnostic.message,
    )


def _diagnostics(
    stdout: str,
    paths: Sequence[str],
    repo: Path,
    host_path: Callable[[str], Path] = Path,
) -> list[_Diagnostic]:
    ""
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
    ""
    match = _DIAGNOSTIC.match(raw) or _PYRIGHT_DIAGNOSTIC.match(raw)
    if match is None or match["severity"] not in _REJECTING:
        return None
    return match


@contextmanager
def _base_tree(changeset: ChangeSet, runner: ToolRunner) -> Iterator[Path]:
    ""
    with runner.scratch() as root:
        archive = subprocess.run(
            ["git", "archive", "--format=tar", changeset.base],
            cwd=changeset.repo,
            capture_output=True,
            env=plain_env(),
            check=False,
        )
        if archive.returncode != 0:
            yield root  #
            return
        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
            tar.extractall(root, filter="data")
        yield root


def _relative_to_repo(path: str, repo: Path) -> str:
    ""
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            return candidate.relative_to(repo).as_posix()
        except ValueError:
            return candidate.as_posix()
    return candidate.as_posix().removeprefix("./")


#
#
#
#
#
#

#
#
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

#
#
#
#
#
#
#
#
#
#
#
#ns
#
#
_INPLACE_ASK = re.compile(r"\bin[- ]place\b|\bmutat(?:e|es|ion|ing)\b", re.IGNORECASE)

#
#
#
#
_NEGATION = frozenset(
    {"not", "no", "never", "without", "don't", "dont", "cannot", "can't", "cant"}
)

#
#
#
_NOT_CALLER_OWNED = frozenset({"self", "cls"})

#
#as
#
#
#
#
#
#
#
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

#
#
#
#
#
#
#
#
#ot
#
_DEPRECATED_TYPING: dict[str, str] = {
    #
    #
    #
    #
    #nd
    #
    #
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
    ""
    if source is None:
        return {}
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return {}
    return _unimportable(tree)


def _unimportable(tree: ast.Module) -> dict[int, str]:
    ""
    hits: dict[int, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module != "collections":
            continue
        moved = [a.name for a in node.names if a.name in _MOVED_TO_COLLECTIONS_ABC]
        if moved:
            hits[node.lineno] = _unimportable_verdict(moved)
    return hits


def _unimportable_verdict(names: Sequence[str]) -> str:
    ""
    return (
        f"'from collections import {', '.join(names)}' raises ImportError on "
        f"Python 3.10 and later — collections re-exported the collections.abc "
        f"names as a shim until 3.9 and stopped; import them from "
        f"collections.abc"
    )


def deprecated_typing_import_lines(source: str | None) -> frozenset[int]:
    ""
    if source is None:
        return frozenset()
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return frozenset()
    return _deprecated_typing_imports(tree)


def _deprecated_typing_imports(tree: ast.Module) -> frozenset[int]:
    ""
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
    ""
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
    ""
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
    ""
    for match in _INPLACE_ASK.finditer(contract_text):
        before = contract_text[: match.start()].lower()
        preceding = re.findall(r"[a-z']+", before)[-3:]
        if not any(word in _NEGATION for word in preceding):
            return True
    return False


def _param_mutation(tree: ast.Module, contract_text: str) -> list[tuple[int, str]]:
    ""
    if _asks_for_mutation(contract_text):
        return []
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            hits += _mutations_in(node)
    #
    #
    #
    #
    return sorted(set(hits))


def _mutations_in(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[tuple[int, str]]:
    ""
    owned = _parameters(func)
    if not owned:
        return []
    hits: list[tuple[int, str]] = []
    _scan(func.body, owned, hits)
    return hits


def _parameters(func: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    ""
    args = func.args
    return {
        arg.arg
        for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs)
        if arg.arg not in _NOT_CALLER_OWNED
    }


def _scan(
    body: Sequence[ast.stmt], owned: set[str], hits: list[tuple[int, str]]
) -> set[str]:
    ""
    for statement in body:
        owned = _scan_statement(statement, owned, hits)
    return owned


def _scan_statement(
    node: ast.stmt, owned: set[str], hits: list[tuple[int, str]]
) -> set[str]:
    ""
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
        _scan(node.body, owned, hits)  #
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
        if node.value is None:  #
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
    ""
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
    ""
    if test is not None:
        _report(test, owned, hits)
    reached: list[set[str]] = []
    for arm in arms:
        if not arm:  #
            reached.append(owned)
            continue
        after = _scan(arm, owned, hits)
        if _falls_through(arm):
            reached.append(after)
    return set().union(*reached, set()) if reached else owned


def _scan_for(
    node: ast.For | ast.AsyncFor, owned: set[str], hits: list[tuple[int, str]]
) -> set[str]:
    ""
    _report(node.iter, owned, hits)
    names = _target_names(node.target)
    after = owned | names if _root_name(node.iter) in owned else owned - names
    _scan(node.body, after, hits)
    _scan(node.orelse, after, hits)
    return after


def _scan_with(
    node: ast.With | ast.AsyncWith, owned: set[str], hits: list[tuple[int, str]]
) -> set[str]:
    ""
    bound: set[str] = set()
    for item in node.items:
        _report(item.context_expr, owned, hits)
        if item.optional_vars is not None:
            bound |= _target_names(item.optional_vars)
    return _scan(node.body, owned - bound, hits)


def _scan_try(
    node: ast.Try | ast.TryStar, owned: set[str], hits: list[tuple[int, str]]
) -> set[str]:
    ""
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
    #
    #
    return _scan(node.finalbody, after | owned, hits) if node.finalbody else after


def _scan_match(
    node: ast.Match, owned: set[str], hits: list[tuple[int, str]]
) -> set[str]:
    ""
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
    ""
    return (
        case.guard is None
        and isinstance(case.pattern, ast.MatchAs)
        and case.pattern.pattern is None
    )


def _pattern_names(pattern: ast.pattern) -> set[str]:
    ""
    names: set[str] = set()
    for node in ast.walk(pattern):
        for attribute in ("name", "rest"):
            bound = getattr(node, attribute, None)
            if isinstance(bound, str):
                names.add(bound)
    return names


def _falls_through(body: Sequence[ast.stmt]) -> bool:
    ""
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
    ""
    _report_in_scope(node, owned, hits)


def _report_in_scope(
    node: ast.AST, owned: set[str], hits: list[tuple[int, str]]
) -> None:
    ""
    if isinstance(node, ast.Lambda):
        bound = _lambda_bound_names(node)
        #
        #
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
    ""
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
    ""
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
    ""
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
    ""
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, ast.Starred):
        return _target_names(target.value)
    if isinstance(target, ast.Tuple | ast.List):
        return set().union(*(_target_names(elt) for elt in target.elts), set())
    return set()


def _root_name(node: ast.expr) -> str | None:
    ""
    while isinstance(node, ast.Subscript | ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None
