"""The deterministic floor: what runs on it, and what a missing tool costs (#81).

mcgyvr's cheapest family is not weak — it is empty, and it says so in its own
words. :func:`mcgyvr.route.plan` for the deterministic family returns nothing
because that family "binds no rung: it is tools, not a model on a source"
(``route._why_empty``). The premise is right — a rung's family is derived from
whether its *source* needs a credential
(:meth:`~mcgyvr.catalog.Catalog.family_of`) and a program has no source — but
the consequence is not. All four ``starts_on: deterministic`` types in the
catalog (``format``, ``import_sort``, ``lint_fix``, ``rename_symbol``) plan an
empty family, :func:`~mcgyvr.escalate.escalate` steps over it on its way to a
model, and work a tool does perfectly, for free, in one attempt becomes a model
call. The floor the catalog wrote down is not being enforced downward; it is
being skipped.

This module supplies the half the ladder is missing — **which program owns a
type on a target** — and the rule for the day that program is absent.

**A rung is a source, a tool is a program, so the floor needs its own table.**
:func:`tool_for` answers from two facts and no config: the contract's type, and
the language of its target as the gate's own adapters define it. The language
comes from :meth:`~mcgyvr.gate.adapter.LanguageAdapter.owns` rather than from a
second table of file extensions for the reason :mod:`mcgyvr.scope` gives for
having one matcher — the gate already decides which program is "the project's
own formatter" for a path, and a second answer to that question is how the two
drift apart.

**A missing tool degrades rather than halts.** ``ruff`` not being installed is
an ordinary state of an ordinary machine, and it must not turn a ``format``
contract into work that cannot run: the work is still doable, just dearly, so
it goes to the cheapest family above the floor that offers a rung — exactly
where :func:`~mcgyvr.escalate.ascent` would have taken it. Ported from local-ai
(``mvp/orchestrator/router.py:938-955``), which degrades its tool tier to the
local pool on the same argument.

**The degradation is recorded, because a silent fallback is what makes a
missing dependency invisible**: the contract still completes, the operator sees
no error, and the only evidence is a model bill quietly larger than it should
be. A :class:`Degradation` names four things — the contract, its type, the
family it left and the family now paying for it — because a fixed sentence can
satisfy any one of them and not all four.

**A planned step names the whole command, because a step nothing can run is
not a floor.** :attr:`ToolStep.argv` is the executable, its subcommand and
flags, and the contract's target — everything a caller needs to run it and
nothing it would have to re-derive. The alternative was tried and is the defect
this replaces: a step carrying a program's *name* determined nothing, because
``ruff`` owns three of the four deterministic types with three different
invocations and the target was never on the step at all. A caller holding such
a step had to rebuild the command from the task type, which is the second table
this module exists to prevent — and, until it did, the floor was bound in the
plan and unbound in every direction downstream of it.

**What is deliberately not here.** Running the tool is the caller's: nothing in
this file executes a program, which is what lets every rule in it be asserted on
a machine with no ruff and no sandbox, and what keeps a routing decision from
writing to a working tree. The command is data here and a subprocess there, for
the same reason :meth:`Degradation.as_record` renders a record rather than
appending one. Climbing past the family a degradation lands on is #43's — this
decides where work starts, never how far it goes. And the write to telemetry is
the caller's too, because a routing decision has no attempt to hang a record on,
and a planning function that opened a file would stop being the thing a caller
can inspect before anything is spent.
"""

from __future__ import annotations

import shutil
from collections.abc import Collection
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mcgyvr.catalog import Family, catalog
from mcgyvr.route import Plan, Planned, Step, attempts_for, plan

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.config import Config
    from mcgyvr.contract import Contract
    from mcgyvr.pool import SourceMap


# Which program owns which type, per language, and how it is invoked. Both
# halves of every entry are already written down elsewhere: the catalog states
# the guarantee in terms of "the project's own formatter/linter/tool"
# (``data/task-catalog.json``), and the gate's adapters name which program that
# is — ruff for Python (``gate/adapters/python.py``), eslint and prettier for
# JS/TS (``gate/adapters/javascript.py``). Nothing is chosen here; this records
# the choice the gate already made, so a change cannot be produced by one
# program and judged by another.
#
# **The invocation is part of the binding, not a detail a caller supplies.**
# Three Python types map to one program, and ``ruff`` is not a command: the
# subcommand and flags are what make it ``format``'s tool rather than
# ``lint_fix``'s. Each is forced by the type's guarantee rather than chosen
# here — "byte-identical to what the project's own formatter produces" is
# ``ruff format``; "every autofix the project's linter applies … and nothing
# else" is ``ruff check --fix``; "imports are ordered as the project's own tool
# orders them, with no other change to the file" is ruff's import rule alone,
# which is ``--select I``. A step that carried only the name would be the same
# step three times over, and running one type's invocation for another's
# contract makes a change that type's guarantee does not describe.
#
# The target is not here: it is the contract's, and it is appended by
# :attr:`ToolStep.argv`. Every program in this table takes the path last, after
# a ``--`` that argv supplies — an entry for a program that could not be told
# where its flags end would not belong here, because a target it read as an
# option is a target it never acted on.
#
# ``("js/ts", "import_sort")`` is absent on purpose. ADR-0025 holds this
# project's eslint config at `recommended`, which carries no import-order rule,
# so no program on this machine would sort a TypeScript file's imports. Binding
# one anyway would claim ``import_sort``'s guarantee — "imports are ordered as
# the project's own tool orders them" — for a tool that orders nothing. The
# absence routes such a contract onward and says why, which is the honest
# answer and the same one a missing ruff gets.
_PROGRAMS: dict[tuple[str, str], tuple[str, ...]] = {
    ("python", "format"): ("ruff", "format"),
    ("python", "import_sort"): ("ruff", "check", "--select", "I", "--fix"),
    ("python", "lint_fix"): ("ruff", "check", "--fix"),
    ("js/ts", "format"): ("prettier", "--write"),
    ("js/ts", "lint_fix"): ("eslint", "--fix"),
}

# The types mcgyvr executes itself, with nothing to install. ``rename_symbol``'s
# warrant in the catalog is that "the index (#47) already resolved the
# references", so its executor is mcgyvr's own index rather than a program on
# PATH — which is why it is the one deterministic type a bare machine can
# always run, and why it is keyed by type alone: an index that resolved the
# references did so whatever language they were written in.
_IN_PROCESS: frozenset[str] = frozenset({"rename_symbol"})


@dataclass(frozen=True)
class Tool:
    """What executes one task type on one target, and what it needs installed.

    ``command`` is how the program is invoked, without the target — the whole
    invocation rather than the program's name, because one program owns three
    of the four deterministic types and the subcommand is what tells them
    apart. It is empty for a type mcgyvr executes in-process.

    :attr:`program` is the first word of that, or ``None``. ``None`` is not "no
    tool" — it is a tool with nothing to install, and that distinction is the
    whole of what :func:`route` asks about: a tool with nothing to install
    cannot be missing, so the one deterministic type that needs no program is
    the one a bare machine can always run on its own floor. It is derived
    rather than stored so that the name and the command cannot disagree.
    """

    task_type: str
    command: tuple[str, ...] = ()

    @property
    def program(self) -> str | None:
        """The executable this tool needs on PATH, or ``None`` for in-process."""
        return self.command[0] if self.command else None


@dataclass(frozen=True)
class ToolStep:
    """One step of a deterministic plan: a program, not a rung.

    The sibling of :class:`~mcgyvr.route.Step`, and deliberately not the same
    type. A :class:`~mcgyvr.route.Step` carries a :class:`~mcgyvr.pool.Rung`,
    which resolves to an endpoint a runner dispatches against; a tool has no
    endpoint and never will, so fitting one into that shape would mean
    inventing a rung name :meth:`~mcgyvr.pool.SourceMap.bind` cannot honour.

    ``attempts`` is one and comes from :func:`~mcgyvr.route.attempts_for`
    rather than from a literal here, so the rule that a tool fails identically
    on retry keeps being stated in exactly one place.

    ``target`` is the contract's, carried on the step rather than left for the
    caller to fetch back, because a step that named a program and not the file
    it acts on determined nothing that could be run. With it, :attr:`argv` is
    the whole command and executing this step is handing that to a runner —
    which is what "the floor binds a program" has to mean for it to be worth
    more than the empty family it replaced.
    """

    tool: Tool
    target: str
    attempts: int = 1

    @property
    def argv(self) -> tuple[str, ...]:
        """The exact command line that performs this step, or ``()``.

        Empty for an in-process tool, and deliberately not a plausible-looking
        command built from the task type: there is no program to run, and an
        argv that named one would send a caller to a process that cannot exist.
        An empty tuple is the honest answer and is the answer a caller can
        distinguish, which a guessed command is not.

        ``--`` before the target, for the same reason the gate's own ruff
        invocation has always carried one (``gate/adapters/python.py``). A target
        is a contract's field, a contract is what a decomposer emitted, and
        ``target: -h.py`` is a legal string in one: without the separator ``ruff
        format -h.py`` prints help, **exits 0** and formats nothing, so an
        executor reading the exit code records a ``format`` contract completed
        over a file it never touched. ``--config=…`` is the same defect with a
        worse ending — the program loads a file the contract named as its
        configuration. Both were reproduced against ruff, prettier and eslint,
        and all three read the path as a path once ``--`` is there.
        """
        if not self.tool.command:
            return ()
        return (*self.tool.command, "--", self.target)


@dataclass(frozen=True)
class Degradation:
    """One contract that could not run on the floor its own type declares.

    Four named facts and then the reason, because this is the record an
    operator reads when the bill is larger than it should be: *this* contract,
    of *this* type, was supposed to run on *that* family and is being paid for
    by *this* one instead. A single sentence could carry any one of the four
    and still leave the reader unable to act on it, which is why they are
    fields rather than prose.
    """

    contract: str
    task_type: str
    left: str
    landed: str
    missing: str

    def __str__(self) -> str:
        return (
            f"{self.task_type} contract {self.contract!r} left the "
            f"{self.left!r} family: {self.missing}, so the work is routed to "
            f"the {self.landed!r} family and paid for with a model."
        )

    def as_record(self) -> dict[str, str]:
        """The same fact as flat data, for whoever owns the telemetry sink.

        Rendered rather than written: :mod:`mcgyvr.telemetry` records attempts
        against a path its caller supplies, and a routing decision has neither.
        The caller that has both appends this.
        """
        return {
            "event": "degraded",
            "contract": self.contract,
            "task_type": self.task_type,
            "left": self.left,
            "landed": self.landed,
            "missing": self.missing,
        }


@dataclass(frozen=True)
class Routed(Planned):
    """Where a contract's work lands, and what it cost to put it there.

    The same shape as :class:`~mcgyvr.route.Plan` — a family, the steps in it,
    and a reason when there are none — plus what was given up on the way. A
    plan cannot carry that: it answers about one family, and a degradation is
    a fact about two.

    "The same shape" is inherited rather than restated. This carries the same
    ``ToolStep | Step`` union a plan does, so it holds the same trap: ``steps``
    and truthiness cannot tell a program from a rung, and a caller that read
    either as "there is something to climb here" would make the mistake #81 made
    one class over. :attr:`~mcgyvr.route.Planned.climbable`,
    :attr:`~mcgyvr.route.Planned.programs` and
    :attr:`~mcgyvr.route.Planned.climb_budget` come from
    :class:`~mcgyvr.route.Planned` for that reason — one answer to the question,
    for both of the types that raise it.

    Truthiness here does keep its own meaning, and it is not the ascent's. A
    route holding one program is a route that found something to run — that is
    the whole of what the floor is for — so ``bool`` and ``len`` both answer
    "was anything planned", and they agree. What may be *climbed* is a narrower
    question and it now has its own name.
    """

    family: Family
    steps: tuple[ToolStep | Step, ...]
    reason: str = ""
    degradations: tuple[Degradation, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.steps)

    def __len__(self) -> int:
        return len(self.steps)

    @property
    def degraded(self) -> bool:
        """Whether this contract is running somewhere dearer than its floor."""
        return bool(self.degradations)


def tool_for(contract: Contract) -> Tool | None:
    """The program that executes ``contract`` outright, or ``None``.

    ``None`` means no deterministic tool claims this work — the type is not on
    the floor, or nothing on this project's toolchain owns that language's
    version of it. It is an ordinary answer and the caller degrades on it; it
    is not an error, because a contract nothing can execute deterministically
    is still perfectly executable by a model.
    """
    if contract.task_type in _IN_PROCESS:
        return Tool(task_type=contract.task_type)
    language = _language_of(contract.target)
    if language is None:
        return None
    command = _PROGRAMS.get((language, contract.task_type))
    if command is None:
        return None
    return Tool(task_type=contract.task_type, command=command)


def tool_steps(contract: Contract) -> tuple[ToolStep, ...]:
    """The deterministic plan for ``contract``: one step, or none.

    One step, because a tool fails identically on retry. None only when
    nothing binds this type on this target — never because the program is not
    installed on the machine that happens to be asking. That separation is the
    reason this takes no ``installed``: a plan is the thing a caller can print,
    diff and assert on before anything is spent, and one that quietly consulted
    ``PATH`` would answer differently on two machines running the same config,
    which is exactly the reproducibility :mod:`mcgyvr.route` is shaped around.
    What is on this machine is :func:`route`'s question, and it is in that
    signature where a caller can see it.

    This is the seam :func:`~mcgyvr.route.plan` needs to stop returning an
    empty family for work that has a program to do it.
    """
    tool = tool_for(contract)
    if tool is None:
        return ()
    return (
        ToolStep(
            tool=tool,
            target=contract.target,
            attempts=attempts_for(contract.type.starts_on, 1, contract),
        ),
    )


def route(
    config: Config,
    pool: SourceMap,
    contract: Contract,
    *,
    installed: Collection[str] | None = None,
) -> Routed:
    """Where this contract may start, with the deterministic floor honoured.

    A contract whose type starts above the floor is planned exactly as
    :func:`~mcgyvr.route.plan` plans it — this function adds a floor, it does
    not replace routing. A contract that starts *on* the floor runs there when
    its tool is installed, and is routed onward with a :class:`Degradation`
    when it is not.

    ``installed`` names the programs available, and defaults to asking PATH.
    Passing it explicitly is how a caller asks "what would this install do" —
    for a machine that is not this one, or for a test that must not depend on
    what the developer happens to have.
    """
    floor = contract.type.starts_on
    if floor.rank != 0:
        planned = plan(config, pool, contract)
        return Routed(family=planned.family, steps=planned.steps, reason=planned.reason)

    tool = tool_for(contract)
    if tool is not None and _have(tool, installed):
        return Routed(family=floor, steps=tool_steps(contract))

    onward = _cheapest_above(config, pool, contract, floor)
    return Routed(
        family=onward.family,
        steps=onward.steps,
        reason=onward.reason,
        degradations=(
            Degradation(
                contract=contract.id,
                task_type=contract.task_type,
                left=floor.name,
                landed=onward.family.name,
                missing=_why_missing(contract, tool),
            ),
        ),
    )


def _have(tool: Tool, installed: Collection[str] | None) -> bool:
    """Whether ``tool`` can actually run here.

    A tool with nothing to install is always available: the answer is about
    the machine, and there is nothing on the machine for it to depend on.
    """
    if tool.program is None:
        return True
    if installed is None:
        return shutil.which(tool.program) is not None
    return tool.program in installed


def _why_missing(contract: Contract, tool: Tool | None) -> str:
    """Why the floor could not run this, in the terms that make it actionable.

    Two different situations reach the same degradation and they want
    different sentences: a program the operator can install, and a type
    nothing on this toolchain claims — which is not something to install and
    should not read like it is.
    """
    if tool is not None and tool.program is not None:
        return f"{tool.program} is not installed"
    return f"no deterministic tool binds {contract.task_type!r} for {contract.target}"


def _cheapest_above(
    config: Config,
    pool: SourceMap,
    contract: Contract,
    floor: Family,
) -> Plan:
    """The cheapest family above ``floor`` that offers a rung.

    The same walk :func:`~mcgyvr.escalate.ascent` makes, so degraded work
    lands where escalation would have taken it rather than somewhere only this
    module knows about. When nothing above the floor offers a rung the answer
    is still a family and still names a reason — every reason, since an
    operator whose keyless install cannot run a ``format`` contract needs to
    know what each family said, not only the first.
    """
    plans = tuple(
        plan(config, pool, contract, family=family)
        for family in catalog().families
        if family.rank > floor.rank
    )
    runnable = next((p for p in plans if p.steps), None)
    if runnable is not None:
        return runnable
    if not plans:  # a catalog whose floor is also its ceiling
        return Plan(
            family=floor,
            steps=(),
            reason=f"no family is dearer than {floor.name!r} to degrade into.",
        )
    return Plan(
        family=plans[0].family,
        steps=(),
        reason=" ".join(f"{p.family.name}: {p.reason}" for p in plans if p.reason),
    )


def _language_of(target: str) -> str | None:
    """Which language's toolchain owns ``target``, by the gate's ownership rule.

    The adapters are constructed inside the call rather than at import, because
    a routing decision must not drag the gate's parsers into a process that is
    only planning — the same restraint :mod:`mcgyvr.escalate` shows by keeping
    :class:`~mcgyvr.gate.GateResult` under ``TYPE_CHECKING``. The pair is the
    gate's own default set (:class:`~mcgyvr.gate.Gate`), so a language the gate
    can judge is a language this can route.
    """
    from mcgyvr.gate.adapters import JavaScriptAdapter, PythonAdapter

    for adapter in (PythonAdapter(), JavaScriptAdapter()):
        if adapter.owns(target):
            return adapter.name
    return None
