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
#: and rejecting it anyway would make the contract unsatisfiable. Not
#: hypothetical: ``tools/bundle/python/tasks/t11`` says "keep appending to it in
#: place and returning that same list", and its own reference solution is the
#: ``if tags is None: tags = []`` shape this family now flags. Whether that task
#: can be solved at all rests on the prose reaching here.
#:
#: Word-boundary rather than substring, because the opposite wording must not
#: stand the rung down: "do not mutate the caller's list" *forbids* the very
#: thing this family flags, and a substring match would read it as an ask.
#: ``permutation`` is the same trap from the other side — it contains
#: "mutation" and has nothing to do with it. :func:`_asks_for_mutation` does the
#: matching, so the negation lives beside the ask it cancels.
_INPLACE_ASK = re.compile(r"\bin[- ]place\b|\bmutat(?:e|es|ion|ing)\b", re.IGNORECASE)

#: A negation within the three words before an ask turns it into a prohibition.
#: "Three words" is the window because the negation and the ask are never far
#: apart in prose worth trusting: "do not mutate", "never mutate", "without
#: mutation", "no mutation".
_NEGATION = frozenset(
    {"not", "no", "never", "without", "don't", "dont", "cannot", "can't"}
)

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

#: ``typing`` aliases mapped to the form the codebase pins, so the AST half of
#: the rung can report them on a machine without ruff. The six builtin
#: generics are joined by the ``collections`` and ``collections.abc`` aliases
#: and a few from ``re`` and ``contextlib``, because the gate's verdict must
#: not depend on which tools the operator happens to have: without this, a
#: ``from typing import Mapping`` was reported by nothing, and a module
#: importing a 3.10-removed name sailed past the AST half of the rung. It is a
#: mapping rather than a set because the pinned form is not always
#: ``name.lower()`` — ``Mapping`` pins to ``collections.abc.Mapping``, not
#: ``mapping``.
_DEPRECATED_TYPING: dict[str, str] = {
    # The ``collections.abc`` names map to themselves, and the explicit
    # entries override where the two lists disagree. ``Set`` is the one name
    # in both: ``typing.Set`` is the builtin ``set`` (``typing.Set[int]``
    # is ``set[int]``), while ``collections.Set`` is the 3.9 shim for
    # ``collections.abc.Set`` — the first is this family's ``typing`` pin and
    # the second is :func:`_unimportable`'s, so the ``**`` spread must not
    # win. Ordering the spread first makes every explicit entry authoritative.
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

    ``contract_text`` is the contract's own prose —
    :attr:`~mcgyvr.contract.Contract.prose`, which is ``task`` and
    ``interface`` joined. It stands the mutation family down when the contract
    asked for in-place behaviour, which is the difference between a correctness
    check and a house rule, and a caller that has no contract to hand gets the
    strict reading. It does *not* stand ``unimportable`` down, and there is no
    wording that could: a contract cannot ask for a module that will not load.

    It reaches here from :meth:`~mcgyvr.gate.Gate.run` through
    :meth:`~mcgyvr.gate.adapter.LanguageAdapter.structural_checks`. It did not
    used to: the parameter existed and the adapter had nowhere to take one
    from, so the stand-down was unreachable from every call site in the tree
    and a contract ordering in-place work was unsatisfiable. Threaded rather
    than deleted because the alternative is a gate that can be given a contract
    it will then reject the worker for obeying.
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
    return f"typing.{alias} — the pinned form is {_DEPRECATED_TYPING[alias]}[...]"


def _asks_for_mutation(contract_text: str) -> bool:
    """Whether the prose asks for in-place mutation, rather than forbids it.

    Word-boundary rather than substring, and negation-aware. "Sort the rows in
    place" stands the rung down; "do not mutate the caller's list" does not —
    it orders the worker to keep its hands off the caller's object, which is
    the exact behaviour the rung exists to check, and standing down for it
    would remove the backstop from the one contract that needs it. A negation
    within the three words before the ask cancels it.
    """
    for match in _INPLACE_ASK.finditer(contract_text):
        before = contract_text[: match.start()].lower()
        preceding = re.findall(r"[a-z']+", before)[-3:]
        if not any(word in _NEGATION for word in preceding):
            return True
    return False


def _param_mutation(tree: ast.Module, contract_text: str) -> list[tuple[int, str]]:
    """Mutation of an object the caller still owns, per function.

    A heuristic by design, and local-ai's note on why is worth keeping: it
    tracks direct mutation of parameters, of their elements, and of ``for``
    aliases into them, and stands down for a parameter rebound to a new object
    **before** the mutation — ``items = list(items)`` is the sanctioned
    defensive copy, and after it the name is no longer the caller's object.
    *Before* is the load-bearing word and :func:`_mutations_in` is where it is
    enforced; asking only whether the name was rebound somewhere accepted the
    canonical ``if x is None: x = []`` and accepted a copy written after the
    line it was meant to protect. Aliasing through other locals is still not
    tracked. The contract's acceptance suite remains the real catch; this is
    the backstop for contracts whose tests do not look.
    """
    if _asks_for_mutation(contract_text):
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
    """Every mutation some path reaches while the object is still the caller's.

    The body is walked in **execution order** rather than with
    :func:`ast.walk`, and that is the whole of this family. The rebind is the
    sanctioned defence — after ``items = list(items)`` the rest of the function
    is working on a list the caller does not hold — but a rebind defends only
    what it runs *before*. Asking instead whether the name is rebound anywhere
    in the body accepted three shapes that leave the caller's object exposed:
    the copy written after the mutation, the copy in a branch that does not
    reach it, and

    .. code-block:: python

        if target is None:
            target = []
        target.append(extra)

    which is the most common way the fault is written and the one that reads
    most like its own fix. The rebind runs only for the caller that passed
    nothing; every caller that passed a list has it appended to.

    So the state threaded through the walk is *which names may still be the
    caller's object on some path to here*, and the merge at a branch is a
    **union**: a name is still owned after an ``if`` if it is owned after
    either arm. A rebind on a path that cannot fall through — a branch that
    returns or raises — is not merged in, because nothing leaves it. Rebinds
    inside a loop or an ``except`` handler do not survive the block: a loop can
    run zero times and a handler runs only when something raised.

    Every approximation points the same way. Where the walk cannot tell, the
    name stays owned and the mutation is reported, because the alternative is a
    rung certifying a function it did not follow. What is still not tracked is
    aliasing through another local — ``other = items`` then ``other.append(x)``
    passes — which is the heuristic local-ai shipped, and the reason the
    contract's own acceptance suite remains the real catch rather than this.
    """
    owned = _parameters(func)
    if not owned:
        return []
    hits: list[tuple[int, str]] = []
    _scan(func.body, owned, hits)
    return hits


def _parameters(func: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """The declared parameters that are the caller's objects to begin with.

    A receiver (``self``/``cls``) and the packed ``*args``/``**kwargs`` never
    are: the tuple and the dict are built fresh at every call site, so
    ``kwargs.pop(...)`` is a local edit and rejecting it would fail a correct
    and idiomatic function.
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
    """Run a block statement by statement; return what is still the caller's."""
    for statement in body:
        owned = _scan_statement(statement, owned, hits)
    return owned


def _scan_statement(
    node: ast.stmt, owned: set[str], hits: list[tuple[int, str]]
) -> set[str]:
    """One statement: report what it mutates, then say what it rebound.

    Dispatch is explicit per statement type rather than generic, because the
    two questions a statement answers here are different for each of them —
    *which of its parts run now* and *which of its parts run on every path out*
    — and a generic walk cannot tell them apart. That is the bug this replaces.
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
        _scan(node.body, owned, hits)  # zero iterations is a path; discard it
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
        if node.value is None:  # a bare `x: int` declares; it does not bind
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
    """A nested ``def``: decorators and defaults now, the body against today's state.

    The body is scanned rather than skipped because a closure that mutates the
    parameter it closed over is the same hazard reached one level down, and it
    is scanned with the enclosing state at the point of definition because that
    is the only state this walk can know. Names the inner function binds itself
    are dropped first: an inner parameter that shadows an outer one is a
    different object, and it is judged when :func:`_param_mutation` reaches
    that function on its own.
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
    """Scan every arm from the same state, and union what reaches the far side.

    Union, not intersection, is the direction that makes a rebind a defence
    only where it is unavoidable: a name that is still the caller's on *any*
    arm is still the caller's after the branch. An arm that cannot fall through
    contributes nothing, which is what lets ``else: return ...`` leave a
    single-armed rebind standing.
    """
    if test is not None:
        _report(test, owned, hits)
    reached: list[set[str]] = []
    for arm in arms:
        if not arm:  # an absent `else` is the path that changes nothing
            reached.append(owned)
            continue
        after = _scan(arm, owned, hits)
        if _falls_through(arm):
            reached.append(after)
    return set().union(*reached, set()) if reached else owned


def _scan_for(
    node: ast.For | ast.AsyncFor, owned: set[str], hits: list[tuple[int, str]]
) -> set[str]:
    """A ``for``: the target aliases into what is iterated, or rebinds away from it.

    Iterating a tracked object hands the body the caller's own elements, so the
    target joins the set; iterating anything else rebinds the target away from
    whatever it named. Nothing the body rebinds survives the loop, because a
    loop that runs zero times reaches the code after it with the state it
    started in.
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
    """A ``with``: its body always runs, so a rebind in it does survive."""
    bound: set[str] = set()
    for item in node.items:
        _report(item.context_expr, owned, hits)
        if item.optional_vars is not None:
            bound |= _target_names(item.optional_vars)
    return _scan(node.body, owned - bound, hits)


def _scan_try(
    node: ast.Try | ast.TryStar, owned: set[str], hits: list[tuple[int, str]]
) -> set[str]:
    """A ``try``: every handler starts from the state the ``try`` was entered in.

    An exception can be raised at any point in the body, including before a
    rebind the body was going to perform, so a handler may not assume the body
    got that far. That is why ``except ...: items = list(items)`` alone does
    not defend a mutation after the block: the path where nothing raised did
    not copy anything.
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
    # `finally` runs on the way out of every one of those paths and on the way
    # out of the ones that raised again, so it is read against all of them.
    return _scan(node.finalbody, after | owned, hits) if node.finalbody else after


def _scan_match(
    node: ast.Match, owned: set[str], hits: list[tuple[int, str]]
) -> set[str]:
    """A ``match``: one arm per case, plus the path where nothing matched.

    That last path is dropped only for a final unguarded ``case _``, which
    cannot fail to match — otherwise a ``match`` whose every case rebinds would
    still be reached, unchanged, by a subject none of them accepted.
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
    """Whether this case is the irrefutable ``case _`` with no guard."""
    return (
        case.guard is None
        and isinstance(case.pattern, ast.MatchAs)
        and case.pattern.pattern is None
    )


def _pattern_names(pattern: ast.pattern) -> set[str]:
    """Every name a ``match`` pattern binds — captures, stars and mapping rests."""
    names: set[str] = set()
    for node in ast.walk(pattern):
        for attribute in ("name", "rest"):
            bound = getattr(node, attribute, None)
            if isinstance(bound, str):
                names.add(bound)
    return names


def _falls_through(body: Sequence[ast.stmt]) -> bool:
    """Whether control can reach the statement after this block.

    Deliberately shallow: ``return``, ``raise``, ``break`` and ``continue`` at
    the end, and an ``if`` whose arms all end that way. Answering *false* where
    the truth is *true* would drop a real path from the merge and stand the
    rung down on it, so the unknown answer is *true* — the mutation is
    reported, and a conservative read of a block this walk did not follow costs
    a finding rather than a silent pass.
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
    """Record every mutating method call this expression makes on an owned name."""
    for sub in ast.walk(node):
        if (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and sub.func.attr in _MUTATING_METHODS
            and _root_name(sub.func.value) in owned
        ):
            hits.append(
                (sub.lineno, _verdict(f".{sub.func.attr}() on", sub.func.value))
            )


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
