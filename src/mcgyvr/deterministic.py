"""The deterministic floor: work a program does instead of a model.

A contract whose kind starts on the cheapest family is not sent to a model. The
catalog's deterministic operations name work a program performs in place, and
:func:`tool_for` binds each one to what performs it — `_PROGRAMS` for the
operations a program runs, `IN_PROCESS` for the one mcgyvr applies itself. A
bound operation becomes a single :class:`ToolStep`: the program, its flags, and
the contract's target after a `--` separator, which is the whole of what
:func:`mcgyvr.drive.run_tool_step` needs to run it in a sandbox.

:func:`mcgyvr.route.plan` fills the floor from :func:`tool_steps`. An operation
nothing binds has no step here, and the floor path of ``mcgyvr run`` stops on
it with exit 1, naming the dearer family it does not climb to.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mcgyvr.contract import Rename
from mcgyvr.route import attempts_for

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.contract import Contract


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
