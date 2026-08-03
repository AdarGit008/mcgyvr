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

Lint and format shell out to real tools. When the tool is not installed, that
is an *environment* problem, not a worker problem — the adapter raises
:class:`ToolUnavailableError` and the gate records it as such rather than rejecting
the worker's change (the same distinction #38 draws for acceptance commands).
"""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path

from mcgyvr.gate.changeset import FileChange
from mcgyvr.gate.findings import Finding


class ToolUnavailableError(Exception):
    """A required external tool is not on PATH — an environment fault.

    Carries the tool name so the gate can tell the operator exactly what to
    install, and can score the check as inconclusive rather than failed.
    """

    def __init__(self, tool: str) -> None:
        super().__init__(f"required tool not found on PATH: {tool}")
        self.tool = tool


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
    def structural_checks(self, change: FileChange, repo: Path) -> list[Finding]:
        """Language hazards on worker-added lines only.

        Called only after :meth:`check_syntax` passes for the file. Findings
        must be attributed to lines in ``change.added_lines``; a hazard the
        worker did not introduce is out of scope by construction.
        """

    @abstractmethod
    def lint(self, changes: Sequence[FileChange], repo: Path) -> list[Finding]:
        """Lint every owned file in one invocation; attribute to added lines.

        Batched, not per-file, so the subprocess count stays flat as the
        change grows. Raises :class:`ToolUnavailableError` if the linter is absent.
        """

    @abstractmethod
    def format_check(self, changes: Sequence[FileChange], repo: Path) -> list[Finding]:
        """Report formatting that would alter a worker-added line.

        A formatter wanting to reflow a pre-existing line is not the worker's
        fault and is ignored; only reformatting that touches an added line is
        a finding. Raises :class:`ToolUnavailableError` if the formatter is absent.
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
