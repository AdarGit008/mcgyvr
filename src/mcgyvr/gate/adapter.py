"""The language adapter interface.

A language adapter is everything the gate needs to know that is specific to one
language, and nothing else. The interface is deliberately language-neutral —
adding a language is implementing this interface and registering it, with no
change anywhere else in the gate (#35). If a Python concept leaks into a method
signature here, the JS/TS adapter (#36) will not be able to satisfy it, so the
interface is the contract that keeps the second language affordable.

An adapter supplies five capabilities:

* **syntax** — a cheap parse that fails fast, so a file that does not even
  parse never reaches an expensive linter or a command execution;
* **structural checks** — language hazards, reported only on worker-added
  lines;
* **lint** and **format** — the project's own tools, with findings attributed
  to added lines so pre-existing style can never fail a worker's change;
* **test-command location** — the conventional way this stack names its tests,
  a fallback for when a contract does not declare one.

Lint and format shell out to real tools, and a tool can fail the adapter in two
distinct ways. Neither is the worker's fault, and ADR-0034 turns on telling them
apart:

* **absent** — not on PATH at all. The reduction in the bar is legible from the
  outside: the operator knows which rung did not run, and a keyless or minimal
  install is expected to reach a verdict on the rungs it has. The adapter raises
  :class:`ToolUnavailableError` and the gate records it and carries on.
* **present and untrustworthy** — the tool ran and its result cannot be read: a
  fatal exit, or output that is not the format it promised. Here the rung
  reports *clean* while having applied no bar at all, which is the one failure
  mode a gate must not have. The adapter raises :class:`ToolFailedError` and the
  gate refuses the change.

Both derive from :class:`EnvironmentFaultError`, so a caller that only wants
"a check could not run" can catch the base.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path

from mcgyvr.gate.changeset import FileChange
from mcgyvr.gate.findings import Finding


class EnvironmentFaultError(Exception):
    """A check could not be run, or its result cannot be trusted.

    Never a verdict on the worker's change: the base of both faults an adapter
    raises, so the gate can separate "the environment let us down" from "the
    change is bad" without knowing which tool was involved.
    """


class ToolUnavailableError(EnvironmentFaultError):
    """A required external tool is not on PATH — an environment fault.

    Carries the tool name so the gate can tell the operator exactly what to
    install, and can score the check as inconclusive rather than failed.
    """

    def __init__(self, tool: str) -> None:
        super().__init__(f"required tool not found on PATH: {tool}")
        self.tool = tool


class ToolFailedError(EnvironmentFaultError):
    """A tool ran and its result cannot be trusted — the rung is inconclusive.

    Distinct from :class:`ToolUnavailableError` in the one way that matters: the
    tool was *there*, so nothing about the run looks degraded from the outside.
    A ruff or eslint that dies on a malformed config exits 2 and writes **an
    empty stdout**, which every JSON reader here turns into zero diagnostics —
    a clean pass over a bar that never ran (#261).

    Carries the exit code and the tool's own first line of complaint, because
    the operator's next action is fixing the tool, and a bare "lint was
    inconclusive" does not say what to fix.
    """

    def __init__(self, tool: str, exit_code: int, detail: str = "") -> None:
        suffix = f": {detail}" if detail else ""
        super().__init__(
            f"{tool} exited {exit_code} and its output cannot be read{suffix}"
        )
        self.tool = tool
        self.exit_code = exit_code
        self.detail = detail


class LanguageAdapter(ABC):
    """One language's view of a change. Implement it; register it; done."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier, e.g. ``python`` or ``javascript``."""

    @abstractmethod
    def owns(self, path: str) -> bool:
        """Whether this adapter is responsible for the file at ``path``.

        Ownership is by filename convention (usually extension). A file no
        adapter owns is carried by the language-agnostic checks only.
        """

    @abstractmethod
    def check_syntax(self, change: FileChange, repo: Path) -> list[Finding]:
        """Parse the file cheaply. A non-empty result fails the file fast.

        Must not run a subprocess or any expensive analysis: this exists to
        cut off lint and command execution for a file that cannot parse.
        """

    @abstractmethod
    def structural_checks(
        self, change: FileChange, repo: Path, *, contract_text: str = ""
    ) -> list[Finding]:
        """Language hazards on worker-added lines only.

        Called only after :meth:`check_syntax` passes for the file. Findings
        must be attributed to lines in ``change.added_lines``; a hazard the
        worker did not introduce is out of scope by construction.

        ``contract_text`` is the contract's own prose
        (:attr:`~mcgyvr.contract.Contract.prose`), and it is here because this
        is the only rung whose hazards a contract can *order*. ``param-mutation``
        rejects a function that mutates the object its caller passed in, and a
        contract that says "sort the rows in place" has told the worker to do
        exactly that; without the prose the rung rejects the worker for obeying
        and the contract cannot be satisfied by any change at all.

        It is passed as text rather than as a :class:`~mcgyvr.contract.Contract`
        so an adapter cannot reach past what the worker was told and start
        judging by ``risk`` or ``verification`` — orchestrator fields #94 keeps
        off every worker-facing surface. It defaults to empty because a caller
        with no contract to hand must get the *strict* reading: silence is not
        permission, and delivery and every bench harness gate without one.
        """

    @abstractmethod
    def lint(self, changes: Sequence[FileChange], repo: Path) -> list[Finding]:
        """Lint every owned file in one invocation; attribute to added lines.

        Batched, not per-file, so the subprocess count stays flat as the
        change grows. Raises :class:`ToolUnavailableError` if the linter is
        absent, and :class:`ToolFailedError` if it ran but its output cannot be
        trusted — an empty list means *this change is clean*, and must never be
        the answer to *we could not tell*.
        """

    @abstractmethod
    def format_check(self, changes: Sequence[FileChange], repo: Path) -> list[Finding]:
        """Report formatting that would alter a worker-added line.

        A formatter wanting to reflow a pre-existing line is not the worker's
        fault and is ignored; only reformatting that touches an added line is
        a finding. Raises :class:`ToolUnavailableError` if the formatter is
        absent, and :class:`ToolFailedError` if it ran untrustworthily — the
        same distinction, for the same reason, as :meth:`lint`.
        """

    @abstractmethod
    def locate_test_command(self, repo: Path) -> list[str] | None:
        """The conventional test command for this stack, or ``None``.

        A fallback for when the contract declares no acceptance command; the
        contract always wins when it does.
        """

    @abstractmethod
    def locate_type_check_command(self, repo: Path) -> list[str] | None:
        """The type checker **this repository declares**, or ``None`` (#114).

        Sibling of :meth:`locate_test_command` and a fallback in exactly the
        same sense: the contract always wins when it declares its own commands,
        so a sniff can never overrule a caller who has said what to run.

        ADR-0006 is the whole of the policy, and it is a policy about restraint:
        mcgyvr never chooses a type checker and never synthesises its flags. It
        finds what the repository already configured and returns that
        invocation. **Strictness is whatever the repository set** — imposing
        ``--strict`` on a repository that carries no annotations is not a
        stricter version of this check, it is a different check that always
        fails, and one no rung can clear because clearing it means annotating
        files outside the contract's scope.

        ``None`` is an ordinary answer meaning *this repository runs no type
        checker*, and it is load-bearing rather than a shrug: where it is
        returned, a ``type_annotation`` contract is not emitted for that
        repository, because its guarantee needs evidence only a command can
        produce.

        Implementations must not import, execute or otherwise evaluate the
        target's code to answer — reading configuration is the whole of the
        permitted method. Running anything at all belongs in the sandbox
        (ADR-0005), and this is called on the host.
        """

    def owned(self, changes: Sequence[FileChange]) -> list[FileChange]:
        """The subset of ``changes`` this adapter owns and can scan.

        Deletions and binaries are dropped — there is no text to check.
        """
        return [
            c
            for c in changes
            if self.owns(c.path) and not c.is_deletion and not c.is_binary
        ]


def require_tool(tool: str) -> str:
    """Resolve ``tool`` on PATH or raise :class:`ToolUnavailableError`."""
    found = shutil.which(tool)
    if found is None:
        raise ToolUnavailableError(tool)
    return found


def trusted_stdout(
    tool: str,
    proc: subprocess.CompletedProcess[str],
    *,
    expected: Sequence[int],
) -> str:
    """``proc.stdout``, or raise :class:`ToolFailedError` if the run means nothing.

    ``expected`` is the set of exit codes under which the tool is *reporting*
    rather than *failing* — for every checker the adapters drive that is
    ``(0, 1)``: nothing to say, and something to say. Anything else is the tool
    telling us it did not do the job.

    The exit code has to be the test, and a format check on the output cannot
    replace it. Measured 2026-08-16 against ruff 0.16.1, eslint 9 and prettier
    3: all four invocations here answer a fatal config error with **exit 2 and
    an empty stdout**, which ``json.loads(stdout or "[]")`` reads as zero
    diagnostics and ``if not stdout.strip()`` reads as nothing to reformat.
    Both are a clean pass. The bad output never arrives to be caught.
    """
    if proc.returncode in expected:
        return proc.stdout
    raise ToolFailedError(tool, proc.returncode, _first_complaint(proc.stderr))


#: Enough of the tool's own words to act on, without pasting a stack trace into
#: every row of a manifest.
_DETAIL_LIMIT = 200


def _first_complaint(stderr: str) -> str:
    """The tool's first non-empty line of stderr, clipped; ``""`` if it said nothing."""
    for line in stderr.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:_DETAIL_LIMIT]
    return ""


#: Variables by which a surrounding shell tells a tool to colourise even when
#: its output is a pipe. `NO_COLOR` is the conventional opt-out and every tool
#: the adapters shell out to honours it.
_COLOUR_FORCING = ("FORCE_COLOR", "CLICOLOR_FORCE")


def plain_env() -> dict[str, str]:
    """The environment to run a checking tool in, with colour forced off.

    Every adapter reads its tool's output as structured text — a unified diff
    by its leading ``-`` and ``+``, or a JSON document by its first character.
    A tool that colourises writes ANSI escapes ahead of exactly those
    characters, so a `FORCE_COLOR` in the developer's shell does not make a
    gate fail: it makes the gate **stop reporting**. That is a silent false
    negative, which is the one failure mode a gate must not have, and it is
    invisible because the tool still exits with the right status.

    Passing this to every :func:`subprocess.run` in an adapter costs nothing
    and removes the whole class.
    """
    env = {k: v for k, v in os.environ.items() if k not in _COLOUR_FORCING}
    env["NO_COLOR"] = "1"
    return env
