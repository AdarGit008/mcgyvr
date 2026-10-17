"""The deterministic floor: work a program does, and the bill when it cannot.

A contract whose kind starts on the cheapest family is not sent to a model. The
catalog's deterministic operations name work a program performs in place, and
:func:`tool_for` binds each one to what performs it — `_PROGRAMS` for the
operations a program runs, `IN_PROCESS` for the one mcgyvr applies itself. A
bound operation becomes a single :class:`ToolStep`: the program, its flags, and
the contract's target after a `--` separator, which is the whole of what
:func:`mcgyvr.drive.run_tool_step` needs to run it in a sandbox.

:func:`route` decides between that step and the ladder. When the tool is bound
and available the contract runs on its own family; when it is not, the work is
planned on the cheapest family above the floor that has a rung to offer, and the
:class:`Degradation` carried on the :class:`Routed` says which contract left
which family, what was missing, and what is paying for it instead — a fallback
nobody can read is a model bill nobody can explain. A contract that does not
start on the floor is planned for its own family and carries no degradation.
"""

from __future__ import annotations

import shutil
from collections.abc import Collection
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mcgyvr.catalog import Family, catalog
from mcgyvr.contract import Rename
from mcgyvr.route import Plan, Planned, Step, attempts_for, plan

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.config import Config
    from mcgyvr.contract import Contract
    from mcgyvr.local_pool import SourceMap


# The floor's programs, keyed by the language the target is written in and the
# operation the contract asks for, each value being the program and the flags
# that perform that operation in place. The table holds no path: `ToolStep.argv`
# and `ToolStep.argv_over` append the target after a `--` separator, so a target
# that spells an option is still handed to the program as a path. A
# (language, operation) pair the table does not list has no program, and a
# contract asking for one has nowhere on the floor to run.
_PROGRAMS: dict[tuple[str, str], tuple[str, ...]] = {
    ("python", "format"): ("ruff", "format"),
    ("python", "import_sort"): ("ruff", "check", "--select", "I", "--fix"),
    ("python", "lint_fix"): ("ruff", "check", "--fix"),
    ("js/ts", "format"): ("prettier", "--write"),
    ("js/ts", "lint_fix"): ("eslint", "--fix"),
}

# Operations mcgyvr performs itself, on the tree, without starting a program.
# None of them is given a command, so a step naming one has no argv, and
# `mcgyvr.drive.exec` applies it through mcgyvr's own executor rather than a
# sandbox run. `rename_symbol` is the only entry, applied by `mcgyvr.rename`.
IN_PROCESS: frozenset[str] = frozenset({"rename_symbol"})

# The operations for which an exit code of 1 is the operation reporting what it
# did rather than failing. A fixer that applied every fix it could still exits 1
# while problems it cannot fix remain, and that residue is the contract's stated
# shape and not a rejection of it; `Tool.reporting` widens the codes a step
# counts as performed to include 1 for these, and a step exiting 1 outside this
# set did fail. Formatting is not here: both formatters exit 0 when they format
# and non-zero only when they could not.
_RESIDUE_IS_EXPECTED: frozenset[str] = frozenset({"lint_fix", "import_sort"})


@dataclass(frozen=True)
class Tool:
    """One operation and, when a program performs it, the command that does.

    An empty `command` is an operation mcgyvr runs in process, so the step
    carries no argv and no program has to be found for it.
    """

    operation: str
    command: tuple[str, ...] = ()

    @property
    def program(self) -> str | None:
        """The program to find and run — the command's first word — or `None`
        for an operation run in process.
        """
        return self.command[0] if self.command else None

    @property
    def reporting(self) -> tuple[int, ...]:
        """The exit codes under which this operation did its work: 0 always,
        and 1 as well for the fixers whose residue is expected.
        """
        return (0, 1) if self.operation in _RESIDUE_IS_EXPECTED else (0,)


@dataclass(frozen=True)
class ToolStep:
    """One program run on one target: what the floor plans and an executor runs.

    `attempts` is what `attempts_for` gives a step on the floor — one attempt,
    because a tool fails the same way on a retry and there is no rung below to
    climb — and `rename` is the one argument a step needs beside its target.
    """

    tool: Tool
    target: str
    attempts: int = 1
    rename: Rename = field(default_factory=Rename)
    """The pair a ``rename_symbol`` step renames, empty on every other operation.

    Carried on the step for the reason ``target`` is: an in-process step whose
    executor had to fetch the contract back to learn what it was renaming would
    determine nothing that could be run from the step alone, and
    :func:`~mcgyvr.drive.run_tool_step` is handed a step and a sandbox.
    """

    @property
    def argv(self) -> tuple[str, ...]:
        """The command that runs for this step's target, the target last.

        A step whose operation is run in process has no command and so no argv.
        The `--` before the target keeps a name such as `-h.py` from being read
        by the program as an option.
        """
        if not self.tool.command:
            return ()
        return (*self.tool.command, "--", self.target)

    def argv_over(self, paths: Collection[str]) -> tuple[str, ...]:
        """The same command over the given paths rather than over the target.

        Used when the target is a glob: every path it named in the workspace
        follows the separator, so each is read as a path and none as a flag.
        """
        if not self.tool.command:
            return ()
        return (*self.tool.command, "--", *paths)


@dataclass(frozen=True)
class Degradation:
    """One contract that left its own family, and what that costs.

    `missing` is why the floor could not run the work — the program is not
    installed, or nothing binds the operation for that target — and `reason` is
    why nothing above the floor can run it either, empty when a rung up there is
    going to. `str` is the sentence a run reports; `as_record` is the same fact
    shaped for the run's log.
    """

    contract: str
    operation: str
    left: str
    landed: str
    missing: str
    reason: str = ""

    def __str__(self) -> str:
        if self.reason:
            return (
                f"{self.operation} contract {self.contract!r} left the "
                f"{self.left!r} family: {self.missing}, and nothing above it "
                f"can run the work ({self.reason}); no model is paying for it."
            )
        return (
            f"{self.operation} contract {self.contract!r} left the "
            f"{self.left!r} family: {self.missing}, so the work is routed to "
            f"the {self.landed!r} family and paid for with a model."
        )

    def as_record(self) -> dict[str, str]:
        """The degradation as a log record: one key per field, tagged
        `degraded`, carrying `reason` only when there is one.
        """
        record = {
            "event": "degraded",
            "contract": self.contract,
            "operation": self.operation,
            "left": self.left,
            "landed": self.landed,
            "missing": self.missing,
        }
        if self.reason:
            record["reason"] = self.reason
        return record


@dataclass(frozen=True)
class Routed(Planned):
    """Where one contract was routed, the steps that route is made of, and the bill.

    `steps` holds both kinds a plan can carry — a `ToolStep` the floor runs and a
    `Step` to climb — and the readers inherited from :class:`~mcgyvr.route.Planned`
    (`climbable`, `programs`) tell them apart, so no caller matches on the union.
    `reason` is why there is nothing to run, and `degradations` records every
    family this contract left on the way here.
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
        """True when this route left a family rather than running where the
        contract started.
        """
        return bool(self.degradations)


def tool_for(contract: Contract) -> Tool | None:
    """The tool that performs this contract's operation, or `None` if nothing does.

    An operation in `IN_PROCESS` is bound whatever the target is, because
    mcgyvr performs it itself; one that needs a program is bound only when the
    target's language and the operation are both a pair `_PROGRAMS` lists. A
    contract with no operation, or a target in a language neither table names,
    has no tool and so no step on the floor.
    """
    if not contract.operation:
        return None
    if contract.operation in IN_PROCESS:
        return Tool(operation=contract.operation)
    language = _language_of(contract.target)
    if language is None:
        return None
    command = _PROGRAMS.get((language, contract.operation))
    if command is None:
        return None
    return Tool(operation=contract.operation, command=command)


def tool_steps(contract: Contract) -> tuple[ToolStep, ...]:
    """The floor's steps for this contract: one, or none when no tool binds it.

    One step and not a sequence of attempts, because a program is run once and
    what it produced is then the gate's to judge.
    """
    tool = tool_for(contract)
    if tool is None:
        return ()
    return (
        ToolStep(
            tool=tool,
            target=contract.target,
            attempts=attempts_for(contract.kind.starts_on, 1, contract),
            rename=contract.rename,
        ),
    )


def route(
    config: Config,
    pool: SourceMap,
    contract: Contract,
    *,
    installed: Collection[str] | None = None,
) -> Routed:
    """Route one contract: onto the floor's tool, or up to the family that can run it.

    A contract whose kind does not start on the floor is planned for its own
    family by :func:`mcgyvr.route.plan` and carries no degradation, since there
    is no floor for it to fall off. On the floor, a bound tool that is available
    becomes the route's single step; otherwise the work is planned on the
    cheapest family above the floor that has a rung to offer, and a
    :class:`Degradation` records what was missing, which family was left and
    which one pays instead — including the case where no family above has a
    step, where the degradation's `reason` says why nothing can run the work and
    it does not claim a model paid.

    `installed` names the programs a caller already knows to be present, and
    `None` asks the machine's PATH.
    """
    floor = contract.kind.starts_on
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
                operation=contract.kind.name,
                left=floor.name,
                landed=onward.family.name,
                missing=_why_missing(contract, tool),
                reason=onward.reason if not onward.steps else "",
            ),
        ),
    )


def _have(tool: Tool, installed: Collection[str] | None) -> bool:
    """Whether this tool can be run here.

    An operation run in process has no program to find and so is always
    available; a program is looked for by name in `installed` when the caller
    supplied one, and on the machine's PATH when it did not.
    """
    if tool.program is None:
        return True
    if installed is None:
        return shutil.which(tool.program) is not None
    return tool.program in installed


def _why_missing(contract: Contract, tool: Tool | None) -> str:
    """The sentence a degradation carries for why the floor could not run this.

    Either the program that was not installed, or the fact that no binding
    exists for this operation and this target. An in-process operation never
    reaches here, since `_have` answers for it without a program.
    """
    if tool is not None and tool.program is not None:
        return f"{tool.program} is not installed"
    return f"no deterministic tool binds {contract.kind.name!r} for {contract.target}"


def _cheapest_above(
    config: Config,
    pool: SourceMap,
    contract: Contract,
    floor: Family,
) -> Plan:
    """The cheapest family above the floor that has a step, and why not when none has.

    Every family dearer than the floor is planned and the first with steps wins;
    the catalog lists families cheapest to dearest, so that first one is the
    cheapest. When none has a step, the cheapest of those families is returned
    with no steps and a `reason` joining the reasons each family was planned
    empty, so a degradation can say why nothing above could run the work.
    """
    plans = tuple(
        plan(config, pool, contract, family=family)
        for family in catalog().families
        if family.rank > floor.rank
    )
    runnable = next((p for p in plans if p.steps), None)
    if runnable is not None:
        return runnable
    if not plans:  # The catalog declares no family above the floor.
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


# The suffixes each language on the floor owns. `_language_of` matches a target
# against these two tuples and nothing else, so which program runs a file is
# decided by its name rather than by parsing it.
_PY_EXTENSIONS = (".py", ".pyi")
_JS_EXTENSIONS = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts")


def _language_of(target: str) -> str | None:
    """The key `_PROGRAMS` uses for this target's language, read from its suffix.

    `python` for the Python suffixes and `js/ts` for the JavaScript and
    TypeScript ones; `None` for anything else, which no program in the table
    performs.
    """
    if target.endswith(_PY_EXTENSIONS):
        return "python"
    if target.endswith(_JS_EXTENSIONS):
        return "js/ts"
    return None
