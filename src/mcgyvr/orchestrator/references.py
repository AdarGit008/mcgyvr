"""Which spellings of a name are the symbol being renamed, and which are not.

A rename may rewrite only the occurrences that denote one symbol, and the index
records names rather than bindings. So this module reads the sources again: it
binds every name to the scope it is bound in, follows plain imports, `import *`
and re-export barrels back to the file that defines the symbol, and gives each
occurrence of the old name a verdict — `RENAME` where it is the symbol, `OTHER`
where it is a same-named method, attribute, key, parameter or local. Where the
two cannot be told apart, or the new name would collide with or be captured by
another, `UnsafeRenameError` is raised and nothing is renamed.

Python is walked with `ast`, JavaScript and TypeScript with tree-sitter. A
column is a byte offset into its line, as both parsers report it, because that
is where the rename splices.
"""

from __future__ import annotations

import ast
import bisect
import posixpath
import re
from collections.abc import Collection, Iterable, Iterator, Mapping
from dataclasses import dataclass
from enum import StrEnum

from tree_sitter import Node, Parser

from mcgyvr.lines import parser_lines
from mcgyvr.orchestrator.symbols import _grammar_for, _node_text, _walk, language_of

# One verdict per occurrence, the shapes they come back in, and the refusal.


class Verdict(StrEnum):
    """What one spelling of the name means for the rename at hand."""

    #: it is the symbol being renamed: safe to rewrite
    RENAME = "rename"
    #: same spelling, another symbol or undecidable: left exactly as it is
    OTHER = "other"


@dataclass(frozen=True)
class Occurrence:
    """One place the old name is spelled, and what it is there.

    `column` is a byte offset into the line, and `text` is a short rendering of the
    occurrence for a report.
    """

    path: str
    line: int
    column: int
    verdict: Verdict
    text: str


@dataclass(frozen=True)
class Definition:
    """A definition of the name that the parser found, at `line` of `path`.

    `module_level` is true when it sits at module scope rather than nested in a
    function, class or method: a rename starts from a module-level definition, because
    which `x.old` reaches a method depends on the type of `x`.
    """

    path: str
    line: int
    module_level: bool


@dataclass(frozen=True)
class Resolution:
    """The verdict for each occurrence the resolver could place, and the rest.

    `occurrences` holds one `Occurrence` per place it was placed; `unresolved` describes
    in `path:line` form the places that spell the name but could not be read — a file
    that does not parse, a string that may name it.
    """

    occurrences: tuple[Occurrence, ...]
    unresolved: tuple[str, ...]


class UnsafeRenameError(Exception):
    """The occurrences cannot be told apart, so nothing may be renamed.

    Raised before any verdict is returned and before any file is written: an ambiguous
    binding, a collision with the new name, or a shorthand property whose key the rename
    would change.
    """


def definitions(path: str, source: bytes, name: str) -> tuple[Definition, ...] | None:
    """Every definition of `name` the parser finds in `source`.

    `None` when the language is neither Python nor JS/TS, or when a Python file does not
    parse: a file the parser could not read is not a file that has no definition.
    """
    language = language_of(path)
    if language == "python":
        tree = _parse_python(source)
        return None if tree is None else _python_definitions(path, tree, name)
    if language == "js/ts":
        root = Parser(_grammar_for(path)).parse(source).root_node
        return _js_definitions(path, root, name)
    return None


def resolve(
    sources: Mapping[str, bytes],
    held: Collection[str],
    defining: str,
    old: str,
    new: str,
) -> Resolution:
    """Judge every occurrence of `old` in `sources`, or refuse to.

    `defining` is the file that holds the symbol's module-level definition and seeds the
    set of files whose binding of the name is the symbol; `held` is every path the tree
    holds, which is what imports are resolved against. Raises `UnsafeRenameError` when
    an occurrence could mean either symbol, or when the new name would collide with or
    be captured by another.
    """
    if language_of(defining) == "python":
        return _PythonResolver(sources, held, defining, old, new).run()
    return _JsResolver(sources, held, defining, old, new).run()


# Bytes that may continue an identifier: letters, digits, underscore, and non-ASCII.

#: `_token` wraps the escaped name in these lookarounds, so `foo` is not part of
#: `foobar`.
_IDENT_BYTE = rb"A-Za-z0-9_\x80-\xff"


def _token(name: str) -> re.Pattern[bytes]:
    raw = re.escape(name.encode("utf-8"))
    return re.compile(
        rb"(?<![" + _IDENT_BYTE + rb"])" + raw + rb"(?![" + _IDENT_BYTE + rb"])"
    )


def _byte_lines(source: bytes) -> list[bytes]:
    """The source as bytes, one entry per line, with the terminators kept.

    Lines are split exactly as the parsers count them, so a byte column from either
    parser indexes straight into `lines[lineno - 1]`; decoding first lets `parser_lines`
    see the real line breaks while undecodable bytes survive the round trip.
    """
    text = source.decode("utf-8", "surrogateescape")
    return [line.encode("utf-8", "surrogateescape") for line in parser_lines(text)]


def _short(text: str, limit: int = 60) -> str:
    """The first line of `text`, trimmed and cut to `limit` with an ellipsis.

    A report entry holds one line, so everything after the first is dropped.
    """
    first = text.strip().splitlines()[0] if text.strip() else ""
    return first if len(first) <= limit else first[: limit - 1] + "…"


# Python's own parser: the module, or `None` when the file does not parse.


def _parse_python(source: bytes) -> ast.Module | None:
    try:
        return ast.parse(source.decode("utf-8", "surrogateescape"))
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        # Nothing can be judged here; the caller reports the file as unresolved.
        return None


#: Blocks that open no scope: a def inside one of them is still module level.
_MODULE_BLOCKS = (
    ast.If,
    ast.Try,
    ast.TryStar,
    ast.With,
    ast.AsyncWith,
    ast.For,
    ast.AsyncFor,
    ast.While,
)

_FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef
_DefNode = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef


def _module_statements(body: Iterable[ast.stmt]) -> Iterator[ast.stmt]:
    """Every statement in `body`, descending into blocks that open no scope.

    `if`, `try`, `with`, `for`, `while` and `match` keep their bodies in the scope they
    appear in, so a definition inside one of them still binds there.
    """
    for statement in body:
        yield statement
        if isinstance(statement, _MODULE_BLOCKS):
            for part in ("body", "orelse", "finalbody"):
                yield from _module_statements(getattr(statement, part, ()))
            for handler in getattr(statement, "handlers", ()):
                yield from _module_statements(handler.body)
        elif isinstance(statement, ast.Match):
            for case in statement.cases:
                yield from _module_statements(case.body)


def _python_definitions(
    path: str, tree: ast.Module, name: str
) -> tuple[Definition, ...]:
    module_level = {
        id(node)
        for node in _module_statements(tree.body)
        if isinstance(node, _DefNode) and node.name == name
    }
    return tuple(
        Definition(path, node.lineno, id(node) in module_level)
        for node in ast.walk(tree)
        if isinstance(node, _DefNode) and node.name == name
    )


class _Bind(StrEnum):
    """How a scope came to bind a name, which decides whose symbol the name is."""

    DEFINE = "define"  # a def or class statement written in this scope
    IMPORT_FROM = "import_from"  # a plain `from m import old`, no alias
    STAR = "star"  # `from m import *`: it may bring the name in
    IMPORT_OTHER = "import_other"  # a module, or an aliased import
    ASSIGN = "assign"  # an assignment, annotated or augmented, or a delete
    OTHER = "other"  # a parameter, `except` or `match` target, a local


@dataclass(frozen=True)
class _Binding:
    kind: _Bind
    line: int
    module: ast.ImportFrom | None = None


class _Scope:
    """One Python scope: the names it binds and how it bound the old one.

    `globals` and `nonlocals` hold the declarations that send a lookup elsewhere;
    `events` records each binding of the old name with its line and kind, and
    `new_lines` the lines that bind the new one, so a collision can say where it would
    land.
    """

    __slots__ = (
        "bindings",
        "events",
        "globals",
        "kind",
        "label",
        "new_lines",
        "nonlocals",
        "parent",
    )

    def __init__(self, kind: str, parent: _Scope | None, label: str) -> None:
        self.kind = kind  # module, function, class or comprehension
        self.parent = parent
        self.label = label
        self.bindings: set[str] = set()
        self.globals: set[str] = set()
        self.nonlocals: set[str] = set()
        self.events: list[_Binding] = []
        self.new_lines: list[int] = []  # lines binding the new name, for a message


def _lookup(scope: _Scope, name: str) -> _Scope:
    """The scope a read of `name` from `scope` resolves to.

    A `global` sends it to the module and a `nonlocal` to the enclosing function that
    binds it; a class body is skipped for anything nested inside it, since a method does
    not see its class's names.
    """
    current = scope
    own = True
    while current.parent is not None:
        if own or current.kind != "class":
            if name in current.globals:
                return _root(current)
            if name in current.nonlocals:
                return _lookup_enclosing(current, name)
            if name in current.bindings:
                return current
        own = False
        current = current.parent
    return current


def _lookup_enclosing(scope: _Scope, name: str) -> _Scope:
    """The enclosing function scope that a `nonlocal name` in `scope` reaches.

    Class scopes are skipped and the module is not a `nonlocal` target, so the walk
    stops before the root; `scope` itself comes back when nothing encloses it and binds
    the name.
    """
    current = scope.parent
    while current is not None and current.parent is not None:
        if current.kind != "class" and name in current.bindings:
            return current
        current = current.parent
    return scope  # nothing enclosing binds it: leave the name where it was


def _root(scope: _Scope) -> _Scope:
    while scope.parent is not None:
        scope = scope.parent
    return scope


@dataclass
class _PyFile:
    """One Python file, parsed and walked: what the resolver reads from it.

    The lists hold what the walk found — name uses with the scope they sit in, def
    nodes, declarations, attribute accesses, imports, and strings that spell the old
    name — each judged later, once the file's origin is known.
    """

    path: str
    tree: ast.Module
    lines: list[bytes]
    module: _Scope
    names: list[tuple[ast.Name, _Scope]]
    defs: list[tuple[_DefNode, _Scope]]
    declarations: list[tuple[ast.Global | ast.Nonlocal, _Scope]]
    attributes: list[ast.Attribute]
    imports: list[tuple[ast.Import | ast.ImportFrom, _Scope]]
    strings: list[ast.Constant]


def _walk_python(
    path: str, tree: ast.Module, source: bytes, old: str, new: str
) -> _PyFile:
    """Walk the tree once, binding names to scopes and recording the old name.

    A scope is opened for each function, lambda, class and comprehension. Every binding
    of the old name is kept with its line and kind, and every binding of the new one
    with its line, so a collision can name the line it would land on.
    """
    module = _Scope("module", None, "<module>")
    found = _PyFile(path, tree, _byte_lines(source), module, [], [], [], [], [], [])
    stack: list[tuple[ast.AST, _Scope]] = [
        (statement, module) for statement in tree.body
    ]

    def bind(
        scope: _Scope, name: str, kind: _Bind, line: int, **extra: ast.ImportFrom
    ) -> None:
        scope.bindings.add(name)
        if name == new:
            scope.new_lines.append(line)
        if name == old:
            scope.events.append(_Binding(kind, line, extra.get("module")))

    def arguments_outside(args: ast.arguments, scope: _Scope) -> None:
        # defaults and annotations are evaluated where the def is written, not inside
        for default in (*args.defaults, *args.kw_defaults):
            if default is not None:
                stack.append((default, scope))
        for arg in (
            *args.posonlyargs,
            *args.args,
            *args.kwonlyargs,
            args.vararg,
            args.kwarg,
        ):
            if arg is not None and arg.annotation is not None:
                stack.append((arg.annotation, scope))

    def arguments_inside(args: ast.arguments, scope: _Scope) -> None:
        for arg in (
            *args.posonlyargs,
            *args.args,
            *args.kwonlyargs,
            args.vararg,
            args.kwarg,
        ):
            if arg is not None:
                bind(scope, arg.arg, _Bind.OTHER, arg.lineno)

    while stack:
        node, scope = stack.pop()
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            bind(scope, node.name, _Bind.DEFINE, node.lineno)
            if node.name == old:
                found.defs.append((node, scope))
            stack.extend((decorator, scope) for decorator in node.decorator_list)
            arguments_outside(node.args, scope)
            if node.returns is not None:
                stack.append((node.returns, scope))
            inner = _Scope("function", scope, node.name)
            arguments_inside(node.args, inner)
            stack.extend((statement, inner) for statement in node.body)
        elif isinstance(node, ast.Lambda):
            arguments_outside(node.args, scope)
            inner = _Scope("function", scope, "<lambda>")
            arguments_inside(node.args, inner)
            stack.append((node.body, inner))
        elif isinstance(node, ast.ClassDef):
            bind(scope, node.name, _Bind.DEFINE, node.lineno)
            if node.name == old:
                found.defs.append((node, scope))
            stack.extend((d, scope) for d in (*node.decorator_list, *node.bases))
            stack.extend((keyword.value, scope) for keyword in node.keywords)
            inner = _Scope("class", scope, node.name)
            stack.extend((statement, inner) for statement in node.body)
        elif isinstance(
            node, ast.ListComp | ast.SetComp | ast.GeneratorExp | ast.DictComp
        ):
            # the first iterable runs outside the comprehension; the rest runs inside
            stack.append((node.generators[0].iter, scope))
            inner = _Scope("comprehension", scope, "<comprehension>")
            for position, generator in enumerate(node.generators):
                if position:
                    stack.append((generator.iter, inner))
                stack.append((generator.target, inner))
                stack.extend((condition, inner) for condition in generator.ifs)
            if isinstance(node, ast.DictComp):
                stack.extend(((node.key, inner), (node.value, inner)))
            else:
                stack.append((node.elt, inner))
        elif isinstance(node, ast.NamedExpr):
            # `x := ...` binds in the nearest enclosing non-comprehension scope
            target_scope = scope
            while (
                target_scope.kind == "comprehension" and target_scope.parent is not None
            ):
                target_scope = target_scope.parent
            stack.append((node.target, target_scope))
            stack.append((node.value, scope))
        elif isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Store | ast.Del):
                bind(scope, node.id, _Bind.ASSIGN, node.lineno)
            if node.id == old:
                found.names.append((node, scope))
        elif isinstance(node, ast.Global | ast.Nonlocal):
            (scope.globals if isinstance(node, ast.Global) else scope.nonlocals).update(
                node.names
            )
            if old in node.names:
                found.declarations.append((node, scope))
        elif isinstance(node, ast.Import):
            found.imports.append((node, scope))
            for alias in node.names:
                bound = alias.asname or alias.name.split(".")[0]
                bind(scope, bound, _Bind.IMPORT_OTHER, node.lineno)
        elif isinstance(node, ast.ImportFrom):
            found.imports.append((node, scope))
            for alias in node.names:
                if alias.name == "*":
                    if scope.kind == "module":
                        scope.events.append(_Binding(_Bind.STAR, node.lineno, node))
                    continue
                kind = (
                    _Bind.IMPORT_FROM
                    if alias.asname is None and alias.name == old
                    else _Bind.IMPORT_OTHER
                )
                bind(scope, alias.asname or alias.name, kind, node.lineno, module=node)
        else:
            if (
                isinstance(node, ast.ExceptHandler | ast.MatchAs | ast.MatchStar)
                and node.name
            ):
                bind(scope, node.name, _Bind.OTHER, node.lineno)
            elif isinstance(node, ast.MatchMapping) and node.rest:
                bind(scope, node.rest, _Bind.OTHER, node.lineno)
            elif isinstance(node, ast.Attribute) and node.attr == old:
                found.attributes.append(node)
            elif (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and (node.value == old or node.value.endswith("." + old))
            ):
                found.strings.append(node)
            stack.extend((child, scope) for child in ast.iter_child_nodes(node))
    return found


def _chain(node: ast.expr) -> str | None:
    """The dotted text of a name/attribute chain, or `None` for anything else."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        head = _chain(node.value)
        return None if head is None else f"{head}.{node.attr}"
    return None


class _Origin(StrEnum):
    OURS = "ours"
    OTHER = "other"
    AMBIGUOUS = "ambiguous"


class _PythonResolver:
    """Resolves the old name across Python sources, then judges each use.

    The files that bind the symbol are found first — the defining file, then whatever
    imports it plainly, then `import *` of it, then whatever imports it from a file
    already ours — repeated to a fixpoint, so a chain of imports carries the rename to
    the files at the end of it.
    """

    def __init__(
        self,
        sources: Mapping[str, bytes],
        held: Collection[str],
        defining: str,
        old: str,
        new: str,
    ) -> None:
        self.old = old
        self.new = new
        self.defining = defining
        self.unresolved: list[str] = []
        self.files: dict[str, _PyFile] = {}
        word = _token(old)
        for path in sorted(sources):
            tree = _parse_python(sources[path])
            if tree is None:
                self.unresolved.extend(
                    f"{path}:{number} (the file does not parse)"
                    for number, line in enumerate(_byte_lines(sources[path]), start=1)
                    if word.search(line)
                )
                continue
            self.files[path] = _walk_python(path, tree, sources[path], old, new)
        # Every held module, indexed by each dotted suffix of its path.
        self.by_suffix: dict[tuple[str, ...], set[str]] = {}
        self.held_python = {path for path in held if language_of(path) == "python"}
        for path in self.held_python:
            parts = _module_parts(path)
            for start in range(len(parts)):
                self.by_suffix.setdefault(parts[start:], set()).add(path)
        self.ours: set[str] = {defining}

    # Import specifiers to held files: absolute names by suffix, relative by path.

    def _absolute(self, dotted: str) -> set[str]:
        return set(self.by_suffix.get(tuple(dotted.split(".")), ()))

    def _relative(self, importer: str, level: int, dotted: str | None) -> set[str]:
        base = posixpath.dirname(importer)
        for _ in range(level - 1):
            base = posixpath.dirname(base)
        parts = [part for part in base.split("/") if part]
        if dotted:
            parts.extend(dotted.split("."))
        stem = "/".join(parts)
        tried = (
            [f"{stem}.py", f"{stem}.pyi", f"{stem}/__init__.py", f"{stem}/__init__.pyi"]
            if stem
            else ["__init__.py", "__init__.pyi"]
        )
        return {path for path in tried if path in self.held_python}

    def _from_module(self, importer: str, node: ast.ImportFrom) -> set[str]:
        if node.level:
            return self._relative(importer, node.level, node.module)
        return self._absolute(node.module) if node.module else set()

    def _submodule(self, importer: str, node: ast.ImportFrom, name: str) -> set[str]:
        """The held files that a `from pkg import name` could mean as `pkg.name`."""
        if node.level:
            joined = f"{node.module}.{name}" if node.module else name
            return self._relative(importer, node.level, joined)
        return self._absolute(f"{node.module}.{name}") if node.module else set()

    def _is_ours(self, modules: set[str]) -> bool:
        return bool(modules & self.ours)

    def _star_brings(self, modules: set[str]) -> bool:
        """Whether `from m import *` of one of our modules brings the old name in.

        A module that declares `__all__` brings in only what is listed there; one that
        does not brings in everything whose name is not underscored.
        """
        for path in modules & self.ours:
            declared = (
                _python_dunder_all(self.files[path].tree)
                if path in self.files
                else None
            )
            if declared is not None:
                if self.old in declared:
                    return True
            elif not self.old.startswith("_"):
                return True
        return False

    # Which symbol a scope's binding of the old name comes from: ours, or another's.

    def _origin(self, found: _PyFile, scope: _Scope) -> _Origin:
        ours = other = False
        for event in scope.events:
            if event.kind is _Bind.DEFINE:
                if scope is found.module and found.path == self.defining:
                    ours = True
                else:
                    other = True
            elif event.kind is _Bind.IMPORT_FROM and event.module is not None:
                if self._is_ours(self._from_module(found.path, event.module)):
                    ours = True
                else:
                    other = True
            elif event.kind is _Bind.STAR and event.module is not None:
                if self._star_brings(self._from_module(found.path, event.module)):
                    ours = True
            elif event.kind in (_Bind.IMPORT_OTHER, _Bind.OTHER):
                other = True
        if ours and other:
            return _Origin.AMBIGUOUS
        return _Origin.OURS if ours else _Origin.OTHER

    def _fixpoint(self) -> None:
        changed = True
        while changed:
            changed = False
            for path, found in self.files.items():
                if path in self.ours:
                    continue
                if self._origin(found, found.module) is not _Origin.OTHER:
                    self.ours.add(path)
                    changed = True

    # The verdict over the whole tree: settle which files are ours, then judge each.

    def run(self) -> Resolution:
        self._fixpoint()
        occurrences: list[Occurrence] = []
        for found in self.files.values():
            occurrences.extend(self._judge(found))
        return Resolution(tuple(occurrences), tuple(self.unresolved))

    def _refuse_ambiguous(self, found: _PyFile, scope: _Scope) -> None:
        lines = ", ".join(str(event.line) for event in scope.events)
        where = "module scope" if scope.kind == "module" else f"{scope.label}"
        raise UnsafeRenameError(
            f"{found.path} binds {self.old!r} in {where} both to the symbol being "
            f"renamed and to something else (lines {lines}); which uses mean "
            f"which cannot be told apart, so nothing was renamed"
        )

    def _refuse_collision(self, found: _PyFile, line: int, why: str) -> None:
        raise UnsafeRenameError(
            f"renaming {self.old!r} to {self.new!r} at {found.path}:{line} would "
            f"{why}; nothing was renamed"
        )

    def _refuse_new_bound_at(self, found: _PyFile, scope: _Scope) -> None:
        """Refuse when the scope already binds the new name by itself.

        The line reported is the first binding of the new name in the scope, since that
        is where a rename would land.
        """
        if self.new not in scope.bindings:
            return
        where = "module scope" if scope.parent is None else scope.label
        line = min(scope.new_lines, default=1)
        self._refuse_collision(
            found, line, f"collide with the {self.new!r} already bound there ({where})"
        )

    def _judge(self, found: _PyFile) -> Iterator[Occurrence]:
        old, path = self.old, found.path
        module_origin = self._origin(found, found.module)
        if module_origin is _Origin.AMBIGUOUS:
            self._refuse_ambiguous(found, found.module)
        if module_origin is _Origin.OURS:
            self._refuse_new_bound_at(found, found.module)
        origins: dict[int, _Origin] = {id(found.module): module_origin}

        def origin_of(scope: _Scope) -> _Origin:
            key = id(scope)
            if key not in origins:
                origins[key] = self._origin(found, scope)
                if origins[key] is _Origin.AMBIGUOUS:
                    self._refuse_ambiguous(found, scope)
                if origins[key] is _Origin.OURS:
                    self._refuse_new_bound_at(found, scope)
            return origins[key]

        # Name uses: renamed where the scope they read resolves to our symbol.
        for name, scope in found.names:
            home = _lookup(scope, old)
            if (
                home is scope
                and scope.kind == "class"
                and isinstance(name.ctx, ast.Load)
                and module_origin is _Origin.OURS
            ):
                # The one case a scope cannot settle: a class body that binds the
                # name itself, read at load time, may mean the class attribute or
                # the module's name depending on how far the body has run.
                raise UnsafeRenameError(
                    f"{path}:{name.lineno} reads {old!r} in the body of class "
                    f"{scope.label}, which also binds it; whether that is the "
                    f"class attribute or the module's {old!r} depends on the "
                    f"order the body runs in, so nothing was renamed"
                )
            if origin_of(home) is _Origin.OURS:
                captor = _lookup(scope, self.new)
                if captor is not home and captor.parent is not None:
                    self._refuse_collision(
                        found,
                        name.lineno,
                        f"be captured by the {self.new!r} that {captor.label} binds",
                    )
                yield Occurrence(
                    path, name.lineno, name.col_offset, Verdict.RENAME, old
                )
            else:
                yield Occurrence(
                    path,
                    name.lineno,
                    name.col_offset,
                    Verdict.OTHER,
                    _described(old, home),
                )

        # Def and class statements: renamed only at this module's top level.
        for node, scope in found.defs:
            keyword = "class" if isinstance(node, ast.ClassDef) else "def"
            column = _def_name_column(found.lines, node)
            if scope is found.module and path == self.defining:
                yield Occurrence(
                    path, node.lineno, column, Verdict.RENAME, f"{keyword} {old}"
                )
            else:
                where = "" if scope.kind == "module" else f" (in {scope.label})"
                yield Occurrence(
                    path, node.lineno, column, Verdict.OTHER, f"{keyword} {old}{where}"
                )

        # `global`/`nonlocal`: the name follows the scope the keyword points at.
        for statement, scope in found.declarations:
            home = (
                found.module
                if isinstance(statement, ast.Global)
                else _lookup_enclosing(scope, old)
            )
            located = _statement_token(found.lines, statement, old)
            if located is None:
                self.unresolved.append(
                    f"{path}:{statement.lineno} (a declaration not found)"
                )
                continue
            verdict = (
                Verdict.RENAME if origin_of(home) is _Origin.OURS else Verdict.OTHER
            )
            keyword = "global" if isinstance(statement, ast.Global) else "nonlocal"
            yield Occurrence(path, located[0], located[1], verdict, f"{keyword} {old}")

        # Imports: the `from m import old` line itself, and receivers for attributes.
        receivers: set[str] = set()
        for importing, scope in found.imports:
            if isinstance(importing, ast.Import):
                for alias in importing.names:
                    if alias.asname is not None:
                        if self._is_ours(self._absolute(alias.name)):
                            receivers.add(alias.asname)
                    else:
                        parts = alias.name.split(".")
                        for end in range(1, len(parts) + 1):
                            dotted = ".".join(parts[:end])
                            if self._is_ours(self._absolute(dotted)):
                                receivers.add(dotted)
                continue
            source = self._from_module(path, importing)
            for alias in importing.names:
                if alias.name == old:
                    shown = _short(ast.unparse(importing))
                    if self._is_ours(source):
                        if alias.asname is None:
                            origin_of(scope)  # settles this scope, refusing a collision
                        yield Occurrence(
                            path, alias.lineno, alias.col_offset, Verdict.RENAME, shown
                        )
                    else:
                        yield Occurrence(
                            path, alias.lineno, alias.col_offset, Verdict.OTHER, shown
                        )
                elif alias.name != "*" and self._is_ours(
                    self._submodule(path, importing, alias.name)
                ):
                    receivers.add(alias.asname or alias.name)

        # `module.old` is renamed only off an import of ours that brings the package.
        for attribute in found.attributes:
            line = attribute.end_lineno or attribute.lineno
            stop = attribute.end_col_offset
            column = (stop if stop is not None else 0) - len(old.encode("utf-8"))
            receiver = _chain(attribute.value)
            shown = _short(ast.unparse(attribute))
            if receiver is not None and receiver in receivers:
                yield Occurrence(path, line, column, Verdict.RENAME, shown)
            else:
                yield Occurrence(path, line, column, Verdict.OTHER, shown)

        # `__all__` entries follow the rename; any other string naming it is reported.
        listed: set[int] = set()
        if module_origin is _Origin.OURS:
            for entry in _dunder_all_entries(found.tree, old):
                quoted = _quoted_name_column(found.lines, entry, old)
                if quoted is not None:
                    listed.add(id(entry))
                    yield Occurrence(
                        path, entry.lineno, quoted, Verdict.RENAME, f'"{old}"'
                    )
        for string in found.strings:
            if id(string) not in listed:
                self.unresolved.append(
                    f"{path}:{string.lineno} the string {string.value!r}"
                )


def _module_parts(path: str) -> tuple[str, ...]:
    stem = path.rsplit(".", 1)[0]
    parts = tuple(stem.split("/"))
    return parts[:-1] if parts and parts[-1] == "__init__" else parts


def _described(name: str, scope: _Scope) -> str:
    if scope.parent is None:
        return name
    return f"{name} (local to {scope.label})"


_DEF_KEYWORD = re.compile(rb"(?:async[ \t\x0c]+)?def[ \t\x0c]+|class[ \t\x0c]+")


def _def_name_column(lines: list[bytes], node: _DefNode) -> int:
    """The byte column where the name starts on a `def`/`class` statement's line.

    The AST points at the statement, so the keyword and an `async` before it are
    skipped; when the line's text does not answer, the statement's own column comes
    back.
    """
    if not 1 <= node.lineno <= len(lines):
        return node.col_offset
    found = _DEF_KEYWORD.match(lines[node.lineno - 1], node.col_offset)
    return found.end() if found else node.col_offset


def _statement_token(
    lines: list[bytes], statement: ast.Global | ast.Nonlocal, name: str
) -> tuple[int, int] | None:
    """The line and byte column of `name` in a `global`/`nonlocal` statement.

    The search starts past the keyword on the statement's first line and ends at the
    statement's end, so a same-named token elsewhere on the line is not taken for the
    declared one; `None` when nothing matches.
    """
    pattern = _token(name)
    last = statement.end_lineno or statement.lineno
    for number in range(statement.lineno, min(last, len(lines)) + 1):
        line = lines[number - 1]
        keyword = len("global" if isinstance(statement, ast.Global) else "nonlocal")
        start = statement.col_offset + keyword if number == statement.lineno else 0
        end = statement.end_col_offset if number == last else None
        found = pattern.search(line, start, len(line) if end is None else end)
        if found:
            return number, found.start()
    return None


def _python_dunder_all(tree: ast.Module) -> list[str] | None:
    entries = [
        node.value
        for node in _dunder_all_nodes(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    has_all = any(
        isinstance(target, ast.Name) and target.id == "__all__"
        for statement in _module_statements(tree.body)
        for target in _assigned(statement)
    )
    return entries if has_all else None


def _assigned(statement: ast.stmt) -> list[ast.expr]:
    if isinstance(statement, ast.Assign):
        return list(statement.targets)
    if isinstance(statement, ast.AugAssign | ast.AnnAssign):
        return [statement.target]
    return []


def _dunder_all_nodes(tree: ast.Module) -> Iterator[ast.expr]:
    for statement in _module_statements(tree.body):
        if not any(
            isinstance(target, ast.Name) and target.id == "__all__"
            for target in _assigned(statement)
        ):
            continue
        value = getattr(statement, "value", None)
        if isinstance(value, ast.List | ast.Tuple):
            yield from value.elts


def _dunder_all_entries(tree: ast.Module, name: str) -> Iterator[ast.Constant]:
    for node in _dunder_all_nodes(tree):
        if isinstance(node, ast.Constant) and node.value == name:
            yield node


def _quoted_name_column(
    lines: list[bytes], node: ast.Constant, name: str
) -> int | None:
    """The byte column of a `__all__` entry written as a plain `"name"` literal.

    An entry that is not a one-line string literal quoted one way comes back as `None`:
    it is reported as unresolved rather than spliced into.
    """
    if node.end_lineno != node.lineno or not 1 <= node.lineno <= len(lines):
        return None
    raw = lines[node.lineno - 1][node.col_offset : node.end_col_offset]
    encoded = name.encode("utf-8")
    if raw in (b'"' + encoded + b'"', b"'" + encoded + b"'"):
        return node.col_offset + 1
    return None


# JS/TS: the same question asked of tree-sitter nodes, whose columns are bytes.

_FUNCTION_TYPES = frozenset(
    {
        "function_declaration",
        "generator_function_declaration",
        "function_expression",
        "function",
        "generator_function",
        "arrow_function",
        "method_definition",
        "function_signature",
        "class_static_block",
    }
)
_BLOCK_TYPES = frozenset(
    {
        "program",
        "statement_block",
        "for_statement",
        "for_in_statement",
        "switch_body",
        "catch_clause",
        "class_static_block",
    }
)
_NAMED_DECLARATIONS = frozenset(
    {
        "function_declaration",
        "generator_function_declaration",
        "function_signature",
        "class_declaration",
        "abstract_class_declaration",
        "interface_declaration",
        "type_alias_declaration",
        "enum_declaration",
    }
)
_SELF_NAMED = frozenset(
    {"function_expression", "function", "generator_function", "class"}
)
_NAME_TYPES = frozenset({"identifier", "type_identifier"})
_JS_EXTENSIONS = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts")


def _nearest(node: Node, types: frozenset[str]) -> Node:
    """The closest ancestor of `node` whose type is in `types`.

    The root comes back when nothing matches, and `node` itself only when it has no
    parent at all.
    """
    current = node.parent
    while current is not None:
        if current.type in types:
            return current
        if current.parent is None:
            return current
        current = current.parent
    return node


def _pattern_names(node: Node | None) -> Iterator[Node]:
    """Every name a binding pattern introduces, at any depth of nesting."""
    if node is None:
        return
    if node.type in _NAME_TYPES or node.type == "shorthand_property_identifier_pattern":
        yield node
    elif node.type in ("object_pattern", "array_pattern", "rest_pattern"):
        for child in node.named_children:
            yield from _pattern_names(child)
    elif node.type == "pair_pattern":
        yield from _pattern_names(node.child_by_field_name("value"))
    elif node.type in ("assignment_pattern", "object_assignment_pattern"):
        yield from _pattern_names(node.child_by_field_name("left"))
    elif node.type in ("required_parameter", "optional_parameter"):
        yield from _pattern_names(node.child_by_field_name("pattern"))


def _declarations(root: Node) -> Iterator[tuple[Node, Node]]:
    """Every name a JS/TS file binds, paired with the node that scopes it.

    `var` belongs to the enclosing function and `let`/`const` to the block, so the walk
    looks for the one or the other; a parameter belongs to its function, and an import
    to the program.
    """
    for node in _walk(root):
        kind = node.type
        if kind == "variable_declarator":
            declaration = node.parent
            is_var = (
                declaration is not None and declaration.type == "variable_declaration"
            )
            scope = _nearest(node, _FUNCTION_TYPES if is_var else _BLOCK_TYPES)
            for name in _pattern_names(node.child_by_field_name("name")):
                yield name, scope
        elif kind == "for_in_statement":
            keyword = node.child_by_field_name("kind")
            if keyword is not None:
                is_var = keyword.type == "var"
                scope = _nearest(node, _FUNCTION_TYPES) if is_var else node
                for name in _pattern_names(node.child_by_field_name("left")):
                    yield name, scope
        elif kind in _NAMED_DECLARATIONS:
            declared = node.child_by_field_name("name")
            if declared is not None and declared.type in _NAME_TYPES:
                yield declared, _nearest(node, _BLOCK_TYPES)
        elif kind in _SELF_NAMED:
            declared = node.child_by_field_name("name")
            if declared is not None and declared.type in _NAME_TYPES:
                yield declared, node
        elif kind == "formal_parameters" and node.parent is not None:
            for parameter in node.named_children:
                yield from ((name, node.parent) for name in _pattern_names(parameter))
        elif kind == "arrow_function":
            single = node.child_by_field_name("parameter")
            if single is not None:
                yield single, node
        elif kind == "catch_clause":
            for name in _pattern_names(node.child_by_field_name("parameter")):
                yield name, node
        elif kind == "type_parameter" and node.parent is not None:
            declared = node.child_by_field_name("name")
            if declared is not None and node.parent.parent is not None:
                yield declared, node.parent.parent
        elif kind == "import_specifier":
            local = node.child_by_field_name("alias") or node.child_by_field_name(
                "name"
            )
            if local is not None:
                yield local, root
        elif kind in ("namespace_import", "import_clause"):
            for child in node.named_children:
                if child.type == "identifier":
                    yield child, root


def _js_definitions(path: str, root: Node, name: str) -> tuple[Definition, ...]:
    """Definitions of `name` in a JS/TS file, with whether they are module level.

    A function or class declared at the program is, as is a declaration there whose
    value is an arrow or function expression; a method, or a declaration inside a
    function, is not.
    """
    found: list[Definition] = []
    for node in _walk(root):
        if node.type in (
            "function_declaration",
            "generator_function_declaration",
            "class_declaration",
            "abstract_class_declaration",
        ):
            if _text(node.child_by_field_name("name")) == name:
                level = _nearest(node, _BLOCK_TYPES).type == "program"
                found.append(Definition(path, node.start_point[0] + 1, level))
        elif node.type == "method_definition":
            if _text(node.child_by_field_name("name")) == name:
                found.append(Definition(path, node.start_point[0] + 1, False))
        elif node.type == "variable_declarator":
            value = node.child_by_field_name("value")
            if value is None or value.type not in (
                "arrow_function",
                "function_expression",
            ):
                continue
            if _text(node.child_by_field_name("name")) != name:
                continue
            declaration = node.parent
            is_var = (
                declaration is not None and declaration.type == "variable_declaration"
            )
            scope = _nearest(node, _FUNCTION_TYPES if is_var else _BLOCK_TYPES)
            found.append(
                Definition(path, node.start_point[0] + 1, scope.type == "program")
            )
    return tuple(found)


def _text(node: Node | None) -> str | None:
    return None if node is None else _node_text(node)


def _key(node: Node) -> tuple[int, int, str]:
    return (node.start_byte, node.end_byte, node.type)


def _specifier(statement: Node) -> str:
    source = statement.child_by_field_name("source")
    if source is None:
        return ""
    for child in source.named_children:
        if child.type == "string_fragment":
            return _node_text(child) or ""
    return ""


#: The leaves whose text can spell a name: identifiers, type names, properties.
_LEAF_TYPES = frozenset(
    {
        "identifier",
        "type_identifier",
        "property_identifier",
        "shorthand_property_identifier",
        "shorthand_property_identifier_pattern",
    }
)
_SHORTHAND = frozenset(
    {"shorthand_property_identifier", "shorthand_property_identifier_pattern"}
)


@dataclass
class _JsFile:
    """One JS/TS file, parsed and walked: what the resolver reads from it.

    Byte offsets locate everything — `starts` turns an offset into a line and a column —
    and the indexes hold the watched names by where they are declared, so a leaf can be
    told from a shadowed local.
    """

    path: str
    root: Node
    starts: list[int]  # byte offset of each line's first byte, for a line number
    leaves: list[Node]  # leaves spelling the old name exactly, in source order
    scope_of: dict[tuple[int, int, str], Node]  # a declaration's name -> its scope
    inner: dict[str, list[Node]]  # the scopes declaring a watched name, by text
    program: dict[str, list[Node]]  # watched names declared at module scope, by text
    statements: list[Node]  # import and export statements
    namespaces: list[Node]  # `import * as ns` clauses


def _js_file(path: str, source: bytes, old: str, new: str) -> _JsFile:
    root = Parser(_grammar_for(path)).parse(source).root_node
    starts = [0]
    for line in _byte_lines(source):
        starts.append(starts[-1] + len(line))
    found = _JsFile(path, root, starts, [], {}, {}, {}, [], [])
    watched = (old, new)
    for name, scope in _declarations(root):
        text = _node_text(name)
        if text not in watched or text is None:
            continue
        found.scope_of[_key(name)] = scope
        if scope.parent is None:
            found.program.setdefault(text, []).append(name)
        else:
            found.inner.setdefault(text, []).append(scope)
    spelled = old.encode("utf-8")
    for node in _walk(root):
        if node.type in _LEAF_TYPES:
            if node.text == spelled:
                found.leaves.append(node)
        elif node.type in ("import_statement", "export_statement"):
            found.statements.append(node)
        elif node.type == "namespace_import":
            found.namespaces.append(node)
    found.leaves.sort(key=lambda leaf: leaf.start_byte)
    return found


def _ancestors(node: Node) -> set[tuple[int, int, str]]:
    keys: set[tuple[int, int, str]] = set()
    current: Node | None = node
    while current is not None:
        keys.add(_key(current))
        current = current.parent
    return keys


class _JsResolver:
    """Resolves the old name across JS/TS sources, then judges every leaf.

    A file is ours when its module scope binds the name to our symbol or re-exports it,
    repeated to a fixpoint, so a barrel that passes the name on carries the rename to
    whatever imports it.
    """

    def __init__(
        self,
        sources: Mapping[str, bytes],
        held: Collection[str],
        defining: str,
        old: str,
        new: str,
    ) -> None:
        self.old = old
        self.new = new
        self.defining = defining
        self.held = set(held)
        self.files = {
            path: _js_file(path, sources[path], old, new) for path in sorted(sources)
        }
        self.ours: set[str] = {defining}

    # A relative specifier to the held files it could name, extensions and index tried.

    def _resolve_specifier(self, importer: str, specifier: str) -> set[str]:
        """The held files that a relative import specifier could name.

        The path itself, its variants with an extension, and an `index` file inside it
        are tried; a bare specifier names a package rather than a file of this tree, so
        it resolves to nothing.
        """
        if not specifier.startswith(("./", "../")):
            return set()
        base = posixpath.normpath(
            posixpath.join(posixpath.dirname(importer), specifier)
        )
        tried = [base, *(base + ext for ext in _JS_EXTENSIONS)]
        tried.extend(f"{base}/index{ext}" for ext in _JS_EXTENSIONS)
        stem, dot, ext = base.rpartition(".")
        if dot and f".{ext}" in (".js", ".jsx", ".mjs", ".cjs"):
            # a `.js` specifier written in TS source means the `.ts` file: try those too
            tried.extend(stem + other for other in (".ts", ".tsx", ".mts", ".cts"))
        return {path for path in tried if path in self.held}

    def _from_ours(self, found: _JsFile, statement: Node | None) -> bool:
        if statement is None:
            return False
        named = self._resolve_specifier(found.path, _specifier(statement))
        return bool(named & self.ours)

    # What module scope says about the old name: ours, another's, or both, and where.

    def _program_binding(self, found: _JsFile) -> tuple[bool, bool, list[int]]:
        """Whether module scope binds the old name to our symbol, to another's, or both.

        A plain `import { old } from` a file of ours counts as ours, and so does the
        defining file; an aliased or namespace import, or a declaration elsewhere,
        counts as another's. The lines are where those bindings sit.
        """
        ours = other = False
        lines: list[int] = []
        for name in found.program.get(self.old, ()):
            lines.append(self._where(found, name)[0])
            parent = name.parent
            if parent is not None and parent.type == "import_specifier":
                plain = parent.child_by_field_name("alias") is None
                statement = _ancestor(parent, "import_statement")
                if plain and self._from_ours(found, statement):
                    ours = True
                else:
                    other = True
            elif parent is not None and parent.type in (
                "namespace_import",
                "import_clause",
            ):
                other = True
            elif found.path == self.defining:
                ours = True
            else:
                other = True
        return ours, other, lines

    def _reexports(self, found: _JsFile) -> bool:
        """Whether the file re-exports our symbol, which makes its importers ours too.

        `export * from` a file of ours and an unaliased `export { old }` from one both
        pass the name on; `export * as ns from` binds a namespace, so it does not.
        """
        for statement in found.statements:
            if statement.type != "export_statement":
                continue
            if not self._from_ours(found, statement):
                continue
            clause = _child_of_type(statement, "export_clause")
            if clause is None:
                if _child_of_type(statement, "namespace_export") is None:
                    return True  # `export *` of ours: it passes the name on
                continue
            for specifier in clause.named_children:
                if (
                    specifier.type == "export_specifier"
                    and _text(specifier.child_by_field_name("name")) == self.old
                    and specifier.child_by_field_name("alias") is None
                ):
                    return True
        return False

    def _fixpoint(self) -> None:
        changed = True
        while changed:
            changed = False
            for path, found in self.files.items():
                if path in self.ours:
                    continue
                ours, _, _ = self._program_binding(found)
                if ours or self._reexports(found):
                    self.ours.add(path)
                    changed = True

    # The verdict over the whole tree, once the re-export chains are followed.

    def run(self) -> Resolution:
        self._fixpoint()
        occurrences: list[Occurrence] = []
        for found in self.files.values():
            occurrences.extend(self._judge(found))
        return Resolution(tuple(occurrences), ())

    def _where(self, found: _JsFile, node: Node) -> tuple[int, int]:
        """The line number and byte column of `node`, found from its byte offset."""
        offset = node.start_byte
        index = bisect.bisect_right(found.starts, offset) - 1
        return index + 1, offset - found.starts[index]

    def _shadowed(self, found: _JsFile, node: Node, name: str) -> bool:
        """Whether `name` is declared in a scope enclosing `node`, shadowing ours."""
        scopes = found.inner.get(name)
        if not scopes:
            return False
        around = _ancestors(node)
        return any(_key(scope) in around for scope in scopes)

    def _judge(self, found: _JsFile) -> Iterator[Occurrence]:
        ours, other, lines = self._program_binding(found)
        if ours and other:
            raise UnsafeRenameError(
                f"{found.path} binds {self.old!r} at module scope both to the "
                f"symbol being renamed and to something else (lines "
                f"{', '.join(map(str, sorted(lines)))}); which uses mean which "
                f"cannot be told apart, so nothing was renamed"
            )
        if found.path in self.ours:
            self._refuse_new_at_program(found)
        namespaces = self._namespaces(found)
        for leaf in found.leaves:
            parent = leaf.parent
            kind = parent.type if parent is not None else ""
            if (
                parent is not None
                and leaf.type == "property_identifier"
                and (kind == "member_expression")
            ):
                yield self._member(found, leaf, parent, namespaces)
            elif parent is not None and kind in (
                "import_specifier",
                "export_specifier",
            ):
                yield self._specifier(found, leaf, parent, ours)
            elif kind in ("namespace_import", "import_clause"):
                statement = _ancestor(leaf, "import_statement")
                yield self._other(found, leaf, _short(_text(statement) or self.old))
            elif leaf.type == "property_identifier":
                what = {"pair": "an object key", "method_definition": "a method"}
                yield self._other(
                    found, leaf, f"{self.old} ({what.get(kind, 'a property')})"
                )
            else:
                yield from self._name(found, leaf, ours)

    def _other(self, found: _JsFile, node: Node, text: str) -> Occurrence:
        line, column = self._where(found, node)
        return Occurrence(found.path, line, column, Verdict.OTHER, text)

    def _rename(self, found: _JsFile, node: Node, text: str) -> Occurrence:
        line, column = self._where(found, node)
        return Occurrence(found.path, line, column, Verdict.RENAME, text)

    def _refuse_new_at_program(self, found: _JsFile) -> None:
        """Refuse when the file already binds or exports the new name at module scope.

        A rename landing on one of those would silently merge two symbols.
        """
        for name in found.program.get(self.new, ()):
            line, _ = self._where(found, name)
            raise UnsafeRenameError(
                f"renaming {self.old!r} to {self.new!r} would collide with the "
                f"{self.new!r} {found.path}:{line} already binds at module scope; "
                f"nothing was renamed"
            )
        for statement in found.statements:
            clause = _child_of_type(statement, "export_clause")
            if statement.type != "export_statement" or clause is None:
                continue
            for specifier in clause.named_children:
                exported = specifier.child_by_field_name(
                    "alias"
                ) or specifier.child_by_field_name("name")
                if _text(exported) == self.new:
                    line, _ = self._where(found, specifier)
                    raise UnsafeRenameError(
                        f"renaming {self.old!r} to {self.new!r} would collide with "
                        f"the {self.new!r} {found.path}:{line} already exports; "
                        f"nothing was renamed"
                    )

    def _namespaces(self, found: _JsFile) -> set[str]:
        """The local names of `import * as ns` clauses that bring in a file of ours.

        Only a member read off one of these receivers can be our symbol; `other.old` may
        be anything.
        """
        names: set[str] = set()
        for node in found.namespaces:
            if self._from_ours(found, _ancestor(node, "import_statement")):
                names.update(
                    _node_text(child) or ""
                    for child in node.named_children
                    if child.type == "identifier"
                )
        return names

    def _member(
        self, found: _JsFile, leaf: Node, member: Node, namespaces: set[str]
    ) -> Occurrence:
        shown = _short(_text(member) or self.old)
        receiver = member.child_by_field_name("object")
        spelled = _text(receiver) if receiver is not None else None
        if (
            receiver is not None
            and receiver.type == "identifier"
            and spelled in namespaces
            and not self._shadowed(found, receiver, spelled or "")
        ):
            return self._rename(found, leaf, shown)
        return self._other(found, leaf, shown)

    def _specifier(
        self, found: _JsFile, leaf: Node, specifier: Node, file_ours: bool
    ) -> Occurrence:
        alias = specifier.child_by_field_name("alias")
        if alias is not None and _key(alias) == _key(leaf):
            # the leaf is the `as` alias, which spells something else here
            return self._other(found, leaf, f"{self.old} (an alias)")
        statement = _ancestor(
            specifier, specifier.type.replace("specifier", "statement")
        )
        shown = _short(_text(statement) or self.old)
        if (
            statement is not None
            and statement.child_by_field_name("source") is not None
        ):
            if self._from_ours(found, statement):
                return self._rename(found, leaf, shown)
            return self._other(found, leaf, shown)
        # no source: a local `export { old }`, meaning this file's own binding
        if file_ours:
            return self._rename(found, leaf, shown)
        return self._other(found, leaf, shown)

    def _name(
        self, found: _JsFile, leaf: Node, file_ours: bool
    ) -> Iterator[Occurrence]:
        old, path = self.old, found.path
        line, _ = self._where(found, leaf)
        scope = found.scope_of.get(_key(leaf))
        if scope is not None and scope.parent is None:
            # declared at module scope: only the defining file may rewrite it
            if path != self.defining:
                yield self._other(found, leaf, old)
                return
            if leaf.type in _SHORTHAND:
                self._refuse_shorthand(path, line)
            yield self._rename(found, leaf, old)
            return
        if scope is not None or self._shadowed(found, leaf, old):
            yield self._other(found, leaf, f"{old} (local)")
            return
        if not file_ours:
            yield self._other(found, leaf, old)
            return
        if leaf.type in _SHORTHAND:
            self._refuse_shorthand(path, line)
        if self._shadowed(found, leaf, self.new):
            raise UnsafeRenameError(
                f"renaming {old!r} to {self.new!r} at {path}:{line} would be "
                f"captured by the {self.new!r} declared around it; nothing was "
                f"renamed"
            )
        yield self._rename(found, leaf, old)

    def _refuse_shorthand(self, path: str, line: int) -> None:
        old = self.old
        raise UnsafeRenameError(
            f"{path}:{line} uses {old!r} as a shorthand property `{{ {old} }}`; "
            f"renaming the variable would change the object's key, and which of "
            f"the two was meant cannot be decided. Spell it `{{ {old}: {old} }}` "
            f"first; nothing was renamed"
        )


def _ancestor(node: Node, type_: str) -> Node | None:
    current = node.parent
    while current is not None and current.type != type_:
        current = current.parent
    return current


def _child_of_type(node: Node, type_: str) -> Node | None:
    for child in node.children:
        if child.type == type_:
            return child
    return None
