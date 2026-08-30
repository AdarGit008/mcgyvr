"""The correctness rung: declared types, and the hazards a type checker cannot see.

Two capabilities live here because they answer the same question — *is this
change wrong*, as opposed to *is it untidy* — and because the answer has to be
split along that line before either is worth having.

**The type checker the repository declared.**
:meth:`~mcgyvr.gate.adapter.LanguageAdapter.locate_type_check_command` has
existed since #114 and nothing in the gate has ever called it, so a worker can
annotate a function with a return type it does not return and the gate accepts.
:class:`TypeCheck` is the missing caller. It runs **only** what the repository
configured, in whichever file that checker reads its own configuration from,
and it runs nothing at all where the repository configured nothing — no default
checker, no synthesised strictness, and no environment issue for the absence.
ADR-0006 put the choice of type checker outside this project; a gate that ran
one anyway would apply a bar the repository never agreed to, and one that
recorded "no type checker" as degraded coverage would say every install that
never wanted one is broken.

*Why this names the changed files when ``locate_type_check_command`` refuses
to.* That method emits the **contract's own acceptance command**, so appending
a target there would substitute mcgyvr's idea of the repository's scope for the
one the project wrote down (#142) — and mypy does not apply ``exclude`` to a
file named on the command line, so the substitution would be silent. This rung
is the other kind of thing: a per-change rung, sibling to lint and format,
whose input set is the worker's own diff and whose cost must stay flat in the
size of the repository rather than growing with it. Both of those rungs name
the changed files for exactly that reason. The ``exclude`` asymmetry is real
and is the price: a file the repository excludes *and the worker changed* is
checked here. That is the safe direction — the change is what the gate is for,
and a worker cannot be told a file was too excluded to be judged after it was
edited.

**The hazards a type checker cannot see, split by severity.**
``_HazardVisitor`` in the Python adapter collects three language hazards and
every one of them rejects. That is fine while the list is mutable defaults,
bare excepts and wildcard imports — all three are faults. It stops being fine
the moment the list grows a member that is a house-style preference, because
then a *correct* change is rejected for a fashion, and the cheapest possible
fix (a deterministic rewrite at zero model spend, :mod:`mcgyvr.repair`) is
unreachable from a verdict that only says "no".

So the two families ported here carry the split with them:

* ``param-mutation`` is **correctness**. A function that mutates the object its
  caller passed in changes state the caller still owns; the caller's next read
  is wrong, and no amount of reformatting makes it right. It rejects, so it is
  reported on the ``structure`` axis the adapter's existing hazards already use.
* ``type-form`` — ``from typing import List`` where ``list[int]`` is the pinned
  form — is **style**. The code is correct. Rejecting it spends a model call, a
  gate run and a rung of the ladder to change six characters that a tool
  changes for nothing. It is reported on the ``style`` axis, which the gate
  folds into :attr:`~mcgyvr.gate.GateResult.observations`: said out loud,
  never fatal.

The style axis has to reach the **lint** rung as well, which is why
:data:`STYLE_LINT_CODES` is here and not only the AST family. ruff already
reports the deprecated typing form by default, as UP035 and UP006, and every
lint finding rejects — so on a machine with ruff the change costs an attempt
over six characters, and on a machine without it nothing reports the form at
all. Those are one missing behaviour seen from two sides: there is no axis on
which a finding can be said out loud without also being fatal. Both sides are
answered here, so the verdict does not depend on which tools the operator
happens to have.

**A demotion is per fault, not per lint code.** UP035 is one code over two
unrelated faults. ``from typing import Mapping`` is the deprecated spelling
above: the module imports, the code runs, and demoting it is the whole point.
``from collections import Mapping`` is not a spelling — ``collections``
re-exported the abstract base classes as a compatibility shim through 3.9 and
stopped in 3.10, so the line raises ``ImportError`` on every interpreter this
project supports and nothing in the module runs at all. Demoting *that* is a
gate accepting a module it could have proven unimportable, and telling the
reviewer, in :func:`~mcgyvr.verify.gate_summary`'s own words, that no check is
asking for it to be fixed. So ``unimportable`` is a family of its own here —
not ported, found — and it carries the same two-sided answer as the two that
were: it is an AST family so a machine without ruff still rejects it, and it
withdraws the UP035 demotion on the lines it found so a machine *with* ruff
does not say the same fault twice with opposite verdicts.

*Why the AST and not ruff's message.* Ruff's words for the two halves are
identical — "Import from ``collections.abc`` instead: ``Mapping``" — as are
the rule name, the severity, the documentation url and the fix it offers; the
two diagnostics differ in the filename and the end column and in nothing else
(pinned in ``tests/test_unimportable_is_not_style.py``). A message rule could
not separate them even in principle, and one keyed on the imported *name*
would reject ``from typing import Mapping`` too. The module an import names is
the fault, it is one field on one node, and it does not move when a linter
rewords itself.

local-ai's third family, ``forbidden-construct`` (bare except, mutable default,
unasked-for IO), is deliberately **not** ported. Its first two members already
exist in ``_HazardVisitor`` as rejecting findings, and demoting them to style
would weaken a bar mcgyvr already holds — a port may not quietly regress the
thing it is porting into. A **formatting** violation stays rejecting for the
same reason from the other direction: it is what makes the repair rung worth
running at all (D21), and demoting it would accept a change no one had tidied
rather than tidying it for free.
"""

from __future__ import annotations

import ast
import re
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from mcgyvr.gate.adapter import (
    ToolFailedError,
    plain_env,
    require_tool,
    trusted_stdout,
)
from mcgyvr.gate.changeset import ChangeSet, FileChange
from mcgyvr.gate.findings import Finding

if TYPE_CHECKING:  # see _python_adapter — a runtime import here closes a cycle
    from mcgyvr.gate.adapters.python import PythonAdapter

#: The check name every type-check finding carries, so a caller can group by it.
CHECK = "typecheck"

#: The axis a correctness hazard reports on — the same one the adapter's
#: existing structural hazards use, because they mean the same thing and a
#: second rejecting name would only make a manifest harder to read.
CORRECTNESS = "structure"

#: The axis a style hazard reports on: real, line-attributed, and outside the
#: verdict. Findings carrying this check belong in
#: :attr:`~mcgyvr.gate.GateResult.observations`.
STYLE = "style"

#: Lint rule codes that report the ``type-form`` family under another name, and
#: therefore belong on :data:`STYLE` rather than on the rejecting ``lint`` axis.
#: ruff's default rule set already flags ``from typing import List`` (UP035) and
#: ``List[int]`` in an annotation (UP006) — measured against ruff 0.16.4 with no
#: configuration discoverable, so this is what a bare install reports. Left where
#: they are, a correct change costs a model call, a gate run and a rung of the
#: ladder over six characters, which is the exact spend the split exists to stop.
#: Kept deliberately narrow: it is the family ported below, named in the other
#: vocabulary, and nothing else. A gate that says one thing twice must not mean
#: something different each time.
#:
#: The demotion is withdrawn per *line* by :func:`unimportable_lines`: UP035
#: covers a second fault that is not style at all, and a code in this set is
#: only demoted where the line it sits on is not one of those. Membership here
#: says "this code can carry a style fault", never "every report of this code
#: is one".
STYLE_LINT_CODES = frozenset({"UP006", "UP035"})

#: Wall-clock ceiling for one type-check pass. A checker reads a repository's
#: whole import graph and can be slow on a cold cache, so the bound is generous;
#: exceeding it is an inconclusive rung, never a verdict on the worker.
TYPECHECK_TIMEOUT_S = 300.0

#: A checker is *reporting* on 0 (clean) and 1 (diagnostics). Both mypy and
#: pyright reserve 2 and above for "I did not do the job", which must never be
#: read as a clean pass — the same rule, for the same reason, as the lint rung
#: (ADR-0034, #261).
_REPORTING = (0, 1)

#: ``path:line[:col[:end_line:end_col]]: severity: message``. The trailing
#: positions appear under ``--show-column-numbers`` / ``--show-error-end``,
#: which a repository may well have configured, so they are tolerated rather
#: than assumed absent.
_DIAGNOSTIC = re.compile(
    r"^(?P<path>[^:]+):(?P<line>\d+)(?::\d+){0,3}: "
    r"(?P<severity>error|warning|note): (?P<message>.*)$"
)

#: The rule identifier a checker appends in brackets, e.g. ``[return-value]``.
_CODE = re.compile(r"\s+\[([a-z0-9-]+)\]$")

#: Only outright errors reject. A ``note`` is elaboration attached to the error
#: above it and carries no independent verdict; reporting it as its own finding
#: would charge a worker twice for one fault.
_REJECTING = frozenset({"error"})


def _python_adapter() -> PythonAdapter:
    """The Python adapter, imported at call time rather than at module scope.

    This module has to reach the adapter for two things it must not answer
    twice — which files are Python, and which checker the repository declared —
    while the adapter reaches *this* module for :func:`compliance_findings`. A
    module-level import would close that cycle and break
    ``import mcgyvr.gate`` outright, so the direction that runs once per gate
    rung is the one deferred. Nothing is cached: ``sys.modules`` already is the
    cache, and an adapter is stateless.
    """
    from mcgyvr.gate.adapters.python import PythonAdapter

    return PythonAdapter()


@dataclass(frozen=True)
class TypeCheck:
    """The declared type checker, run over the lines a worker added.

    ``repo`` is where the declaration lives, so it is constructor state; the
    files to check come from the change set handed to :meth:`run`. Instances
    are immutable and cheap — the declaration is re-read per run rather than
    cached, because a contract may add the config file it is being judged by.
    """

    repo: Path
    timeout: float | None = TYPECHECK_TIMEOUT_S

    def declared_command(self) -> list[str] | None:
        """The checker this repository configured, or ``None`` for none.

        Delegated rather than re-derived: the adapter already knows the four
        places mypy reads its configuration from and parses rather than greps
        for them, and a second detector that disagreed would fabricate a
        type-check for a repository that runs none.
        """
        return _python_adapter().locate_type_check_command(self.repo)

    def run(self, changeset: ChangeSet) -> list[Finding]:
        """Type-check the worker's Python files; report only on added lines.

        Returns an empty list where there is nothing to say **and** where there
        is nobody to ask: a repository that declared no checker is not failed
        for the absence and is not reported as degraded either.

        Raises :class:`~mcgyvr.gate.ToolUnavailableError` when a *declared*
        checker is not installed, and :class:`~mcgyvr.gate.ToolFailedError`
        when it ran and its answer cannot be read — the same two faults, with
        the same meanings, as :meth:`~mcgyvr.gate.LanguageAdapter.lint`, so the
        gate records the rung as skipped or inconclusive without needing to
        know a type checker was involved.
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
        checker = require_tool(tool)
        try:
            proc = subprocess.run(
                [checker, *command[1:], *[change.path for change in targets]],
                cwd=self.repo,
                capture_output=True,
                text=True,
                env=plain_env(),
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            # The rung ran and cannot say what bar it applied, which is the
            # inconclusive case rather than the absent one: nothing about a
            # timeout looks degraded from the outside.
            raise ToolFailedError(
                tool, -1, f"timed out after {self.timeout:g}s"
            ) from exc
        # A checker that exits 2 writes its complaint to stderr and leaves
        # stdout empty, which reads as "no diagnostics" — a clean pass over a
        # bar that never ran. The exit code is the only thing that separates
        # the two, so it is checked before the output is parsed.
        stdout = trusted_stdout(tool, proc, expected=_REPORTING)
        return _diagnostics(stdout, targets)


def _diagnostics(stdout: str, targets: Sequence[FileChange]) -> list[Finding]:
    """Parse a checker's report, keeping errors on worker-added lines only.

    A checker follows imports, so it reports on files the worker never touched
    and on lines that were already there. Both are dropped here: the gate's
    core promise is that pre-existing state in the repository can never fail a
    change.
    """
    added = {change.path: change.added_lines for change in targets}
    findings: list[Finding] = []
    for raw in stdout.splitlines():
        match = _DIAGNOSTIC.match(raw)
        if match is None or match["severity"] not in _REJECTING:
            continue
        path = match["path"]
        line = int(match["line"])
        if line not in added.get(path, frozenset()):
            continue
        message = match["message"].strip()
        code = _CODE.search(message)
        findings.append(
            Finding(
                check=CHECK,
                path=path,
                line=line,
                code=code.group(1) if code else None,
                message=_CODE.sub("", message),
            )
        )
    return findings


# --- the AST families -----------------------------------------------------
#
# Ported from local-ai's `compliance.py`, which found them by looking at the
# failures no context bundle rescued: input mutation through an aliased inner
# list, and deprecated typing aliases against the pinned modern form. Both are
# AST-detectable in milliseconds, which is what makes them worth a rung.

#: Methods that change the receiver rather than returning a new object. A call
#: to one of these on something the caller still owns is the whole hazard.
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

#: Wording in a contract that *asks* for mutation. A contract that says "sort
#: the list in place" has told the worker to do the thing this family rejects,
#: and rejecting it anyway would make the contract unsatisfiable.
_INPLACE_WORDS = ("in place", "in-place", "mutate", "mutation")

#: PEP 585 aliases whose builtin-generic form is the pinned one.
_DEPRECATED_TYPING = frozenset({"List", "Dict", "Set", "Tuple", "FrozenSet", "Type"})

#: Bound by the language rather than by the caller, so mutating them is not the
#: caller's problem: a method's receiver is the object the method exists to
#: change, and ``*args``/``**kwargs`` are built fresh at every call site.
_NOT_CALLER_OWNED = frozenset({"self", "cls"})

#: The abstract base classes ``collections`` re-exported for compatibility
#: until 3.9 and stopped re-exporting in 3.10 — ``_collections_abc.__all__`` as
#: it stood in 3.9, the list the shim was keyed on. Written out rather than
#: read from the running interpreter, and it is a closed list either way: the
#: removal has already happened, so nothing will ever join it, and introspecting
#: ``collections`` here would make the gate's verdict a fact about whichever
#: Python mcgyvr happens to run under instead of a fact about the worker's
#: file. ``Buffer`` is *not* here: it arrived in ``collections.abc`` in 3.12 and
#: was never in ``collections`` to lose.
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


def unimportable_lines(source: str | None) -> dict[int, str]:
    """Lines in ``source`` holding an import that cannot resolve, and why.

    Keyed by the line ruff and :mod:`ast` both attribute the statement to — the
    ``from`` line, including where the import spans several lines — so the lint
    rung can look a diagnostic's row up here and withdraw its demotion without
    re-deriving anything.

    Takes source rather than a parsed tree, unlike :func:`compliance_findings`,
    because the one caller that is not :meth:`~PythonAdapter.structural_checks`
    is the lint rung, which works from a linter's JSON and has no tree to hand.
    Tolerating ``None`` and unparseable text here rather than at each call site
    keeps that single answer in one place: **nothing found**, deliberately, and
    not "nothing is wrong". A file that will not parse has already been
    rejected by the syntax rung, and a second finding for one fault would
    charge the worker twice — the same rule the ``note`` severity follows in
    :func:`_diagnostics`.
    """
    if source is None:
        return {}
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return {}
    return _unimportable(tree)


def _unimportable(tree: ast.Module) -> dict[int, str]:
    """``from collections import <an ABC>``, by line.

    Only the ``from`` form. ``import collections`` followed by
    ``collections.Mapping`` is an ``AttributeError`` when the attribute is
    read, not an ``ImportError`` when the module is loaded, and this family
    claims the second — a check whose message named the wrong exception would
    be worse than one that stayed narrow.
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
    """Every moved name on the statement, because the import fails on the first.

    A worker told about one of two bad names fixes one of them and comes back
    to the same rejection, which costs a whole attempt to learn what the gate
    already knew.
    """
    return (
        f"'from collections import {', '.join(names)}' raises ImportError on "
        f"Python 3.10 and later — collections re-exported the collections.abc "
        f"names as a shim until 3.9 and stopped; import them from "
        f"collections.abc"
    )


def compliance_findings(
    tree: ast.Module,
    path: str,
    added_lines: frozenset[int],
    *,
    contract_text: str = "",
) -> list[Finding]:
    """The three AST families, attributed to worker-added lines.

    Takes the parsed tree rather than the source because the caller
    (:meth:`~mcgyvr.gate.adapters.PythonAdapter.structural_checks`) has already
    parsed it, and a third parse of the same file per gate run buys nothing.

    ``contract_text`` is the contract's own prose. It stands the mutation
    family down when the contract asked for in-place behaviour, which is the
    difference between a correctness check and a house rule: the caller is
    expected to pass ``contract.task`` and ``contract.interface`` joined, and
    a caller that has no contract to hand gets the strict reading. It does
    *not* stand ``unimportable`` down, and there is no wording that could: a
    contract cannot ask for a module that will not load.
    """
    style = [
        Finding(check=STYLE, path=path, line=line, code="TYPE-FORM", message=message)
        for line, message in _type_form(tree)
    ]
    correctness = [
        Finding(
            check=CORRECTNESS,
            path=path,
            line=line,
            code="PARAM-MUTATION",
            message=message,
        )
        for line, message in _param_mutation(tree, contract_text)
    ]
    correctness += [
        Finding(
            check=CORRECTNESS,
            path=path,
            line=line,
            code="UNIMPORTABLE",
            message=message,
        )
        for line, message in sorted(_unimportable(tree).items())
    ]
    return [f for f in (*correctness, *style) if f.line in added_lines]


def _type_form(tree: ast.Module) -> list[tuple[int, str]]:
    """Deprecated typing aliases, by import and by attribute access."""
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
    return f"typing.{alias} — the pinned form is {alias.lower()}[...]"


def _param_mutation(tree: ast.Module, contract_text: str) -> list[tuple[int, str]]:
    """Mutation of an object the caller still owns, per function.

    A heuristic by design, and local-ai's note on why is worth keeping: it
    tracks direct mutation of parameters, of their elements, and of ``for``
    aliases into them, and stands down for a parameter rebound to a new object
    first — ``items = list(items)`` is the sanctioned defensive copy, and a
    parameter that has been rebound is no longer the caller's object. Aliasing
    through other locals is not tracked. The contract's acceptance suite
    remains the real catch; this is the backstop for contracts whose tests do
    not look.
    """
    if any(word in contract_text.lower() for word in _INPLACE_WORDS):
        return []
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            hits += _mutations_in(node)
    # `ast.walk` descends into nested functions, so an inner mutation is seen
    # once from its own definition and again from every definition enclosing
    # it. Deduplicating is cheaper than restricting the walk, and restricting
    # it would lose the closure that mutates the parameter it closed over.
    return sorted(set(hits))


def _mutations_in(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[tuple[int, str]]:
    tracked = _caller_owned(func)
    if not tracked:
        return []
    hits: list[tuple[int, str]] = []
    for node in ast.walk(func):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _MUTATING_METHODS
            and _root_name(node.func.value) in tracked
        ):
            hits.append(
                (node.lineno, _verdict(f".{node.func.attr}() on", node.func.value))
            )
        elif isinstance(node, ast.Assign | ast.AugAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            hits += _writes_into(node.lineno, targets, tracked, "assignment into")
        elif isinstance(node, ast.Delete):
            hits += _writes_into(node.lineno, node.targets, tracked, "del on")
    return hits


def _writes_into(
    lineno: int, targets: Iterable[ast.expr], tracked: set[str], what: str
) -> list[tuple[int, str]]:
    """Targets that write *through* a tracked name rather than rebinding it.

    ``items[0] = x`` and ``items.field = x`` reach the caller's object;
    ``items = x`` only moves a local name and is what makes a defensive copy
    work, so a bare :class:`ast.Name` target is not a hazard here.
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


def _caller_owned(func: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Parameter names that still refer to the caller's own objects.

    Three things take a name out of the set. A receiver (``self``/``cls``) and
    the packed ``*args``/``**kwargs`` are never the caller's object to begin
    with — the tuple and dict are built fresh per call, so ``kwargs.pop(...)``
    is a local edit and rejecting it would fail a correct and idiomatic
    function. A name rebound anywhere in the body (assignment, ``with ... as``,
    tuple unpacking, augmented assignment) has stopped pointing at the input.
    And a ``for`` target cuts both ways: iterating a tracked object aliases the
    target *into* it, while iterating anything else rebinds the target away.
    """
    args = func.args
    tracked = {
        arg.arg
        for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs)
        if arg.arg not in _NOT_CALLER_OWNED
    }
    if not tracked:
        return tracked

    rebound: set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                rebound |= _target_names(target)
        elif isinstance(node, ast.AnnAssign | ast.AugAssign) and isinstance(
            node.target, ast.Name
        ):
            rebound.add(node.target.id)
        elif isinstance(node, ast.With | ast.AsyncWith):
            for item in node.items:
                if item.optional_vars is not None:
                    rebound |= _target_names(item.optional_vars)
    tracked -= rebound

    for node in ast.walk(func):
        if isinstance(node, ast.For | ast.AsyncFor):
            names = _target_names(node.target)
            if _root_name(node.iter) in tracked:
                tracked |= names - rebound
            else:
                tracked -= names
    return tracked


def _target_names(target: ast.expr) -> set[str]:
    """Every plain name an assignment target binds, through nesting and stars."""
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, ast.Starred):
        return _target_names(target.value)
    if isinstance(target, ast.Tuple | ast.List):
        return set().union(*(_target_names(elt) for elt in target.elts), set())
    return set()


def _root_name(node: ast.expr) -> str | None:
    """Unwrap a subscript/attribute chain to the name underneath it."""
    while isinstance(node, ast.Subscript | ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None
