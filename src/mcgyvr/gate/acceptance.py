"""Acceptance command execution: the gate's strongest, last rung (#38).

Running the contract's declared checks — its test suite, its type-checker — is
the most decisive acceptance signal there is, and the reason the per-task
sandbox (E4) exists. It is also the most expensive, so it runs last and inside
the sandbox, never on the host.

The hard part is not running a command; it is telling apart three outcomes
that look alike from the outside — all of them "the command did not simply
pass":

1. **The command failed** — tests are red. That is the worker's change being
   rejected, and it is the only one of the three that is.
2. **The command could not run** — a dependency is missing, the binary is not
   on ``PATH``. That is an *environment* fault; charging the worker for it
   would reject a good change for a reason it could never fix. We read the
   shell's own verdict: exit ``127`` (not found) or ``126`` (not executable)
   is "did not run", distinct from any exit code a program chooses for itself.
3. **The command changed the working tree** — a formatter listed as a check,
   say, that rewrites files. That *invalidates the run*: the gate must judge
   the worker's diff, not the diff plus the command's opinion. We snapshot the
   tree (a git ``write-tree`` that honours ``.gitignore``, so it sees exactly
   what the gate judges) before and after each command and fail the offending
   command **by name** when the two differ.

Two entry points, one classifier:

- :meth:`Acceptance.precondition` runs the suite once against the *unchanged*
  tree, before the first worker attempt. A suite that is already red, that
  cannot run, or that mutates the tree is not a usable acceptance signal — and
  catching that here, as a :class:`~mcgyvr.gate.preflight.PreflightIssue`,
  spends no attempt and names the fault as the orchestration error it is. It
  also earns the interpretation :meth:`run` relies on: once the suite is known
  green and read-only on the base, a later failure or timeout is the worker's.
- :meth:`Acceptance.run` is the gate's last rung, over the applied change.

Output handed back to a retry keeps the **tail** of a command's streams, never
a truncated head — a test runner prints its passes first and its failures and
summary last, so a head could be all green while the change is red.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from mcgyvr.gate.findings import Finding
from mcgyvr.gate.preflight import PreflightIssue
from mcgyvr.sandbox.base import CommandResult, Sandbox

# The check name every acceptance finding carries, so a caller can group by it.
CHECK = "acceptance"

# Conventional shell exit codes for a command that never ran: 127 when the
# binary is not found, 126 when it is found but cannot be executed. Both are
# "could not run" — an environment fault — as opposed to a code a program
# returns to say it ran and failed, which is the worker's.
_DID_NOT_RUN = frozenset({126, 127})

# How much of a failing command's output to carry. Kept from the tail, so the
# failing part survives even when the passes before it are voluminous.
_MAX_EXCERPT_LINES = 40
_MAX_EXCERPT_CHARS = 4000


class AcceptanceError(Exception):
    """The acceptance rung could not read the sandbox tree it needs to judge."""


class _Outcome(Enum):
    """How one acceptance command turned out. The five cases #38 must separate."""

    PASSED = auto()
    FAILED = auto()  # ran and returned non-zero — the worker's change is red
    DID_NOT_RUN = auto()  # 126/127 — an environment fault, not a rejection
    TIMED_OUT = auto()  # killed at the wall-clock ceiling
    ALTERED_TREE = auto()  # mutated the change-set — the run is invalidated


@dataclass(frozen=True)
class AcceptanceReport:
    """The acceptance rung's verdict, in the gate's own currency.

    ``findings`` reject the worker's change; ``environment_issues`` record a
    command that could not run, so a degraded run is never mistaken for a
    passing one. Mirrors :class:`~mcgyvr.gate.runner.GateResult`'s two lists so
    the gate folds one straight into the other.
    """

    findings: tuple[Finding, ...] = ()
    environment_issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class Acceptance:
    """The contract's acceptance commands, bound to an open sandbox.

    Construct from an *entered* sandbox (E4) and the contract's declared
    checks, each an argv list. :meth:`precondition` is called once before the
    first worker attempt, on the unchanged tree; :meth:`run` is the gate's last
    rung, after a change has been applied to the sandbox workspace. Neither
    resets the sandbox — the caller owns :meth:`~mcgyvr.sandbox.base.Sandbox.reset`
    between attempts.
    """

    sandbox: Sandbox
    commands: tuple[tuple[str, ...], ...]
    timeout: float | None = None

    def precondition(self) -> PreflightIssue | None:
        """Verify the suite is a usable signal on the unchanged tree.

        Runs each command against the base, before any worker change. The first
        that fails, cannot run, times out, or mutates the tree is reported as a
        :class:`~mcgyvr.gate.preflight.PreflightIssue` — an orchestration error
        distinct from a rejected change — and stops the check: a suite that
        cannot establish a clean baseline tells us nothing about a worker's
        diff. ``None`` means every command passed cleanly and read-only, which
        is what lets :meth:`run` read a later failure as the worker's.
        """
        for command in self.commands:
            outcome, result = self._run_one(command)
            issue = _as_preflight(command, outcome, result)
            if issue is not None:
                return issue
        return None

    def run(self) -> AcceptanceReport:
        """Run the acceptance commands over the applied change and judge them.

        A command that could not run becomes an environment issue, never a
        finding. A command that altered the working tree fails by name and
        stops the run — everything after it would judge a contaminated tree.
        Other failures and timeouts accumulate as findings carrying the tail of
        the command's output.
        """
        findings: list[Finding] = []
        env_issues: list[str] = []
        for command in self.commands:
            outcome, result = self._run_one(command)
            if outcome is _Outcome.PASSED:
                continue
            if outcome is _Outcome.DID_NOT_RUN:
                env_issues.append(_did_not_run_note(command, result))
                continue
            findings.append(_as_finding(command, outcome, result))
            if outcome is _Outcome.ALTERED_TREE:
                # The tree is no longer the worker's; nothing run after this
                # would be judging the change under test.
                break
        return AcceptanceReport(tuple(findings), tuple(env_issues))

    def _run_one(self, command: Sequence[str]) -> tuple[_Outcome, CommandResult]:
        """Run one command and classify it by deterministic signals only.

        Tree alteration is checked first because it invalidates the run whatever
        the exit code; then the wall-clock kill, then the shell's did-not-run
        codes, then any other non-zero exit.
        """
        workspace = self.sandbox.workspace
        before = _worktree_tree(workspace)
        result = self.sandbox.run(command, timeout=self.timeout)
        after = _worktree_tree(workspace)
        if after != before:
            return _Outcome.ALTERED_TREE, result
        if result.timed_out:
            return _Outcome.TIMED_OUT, result
        if result.exit_code in _DID_NOT_RUN:
            return _Outcome.DID_NOT_RUN, result
        if result.exit_code != 0:
            return _Outcome.FAILED, result
        return _Outcome.PASSED, result


# --- outcome → report mapping --------------------------------------------


def _as_finding(
    command: Sequence[str], outcome: _Outcome, result: CommandResult
) -> Finding:
    """Turn a rejecting outcome into a finding that names the command."""
    label = _label(command)
    if outcome is _Outcome.ALTERED_TREE:
        return Finding(
            check=CHECK,
            path=label,
            code="tree-altering",
            message=(
                "acceptance command modified the working tree — an acceptance "
                "command must judge the change, not add to it; the gate can only "
                "score the worker's diff if the command leaves it untouched"
            ),
        )
    if outcome is _Outcome.TIMED_OUT:
        return Finding(
            check=CHECK,
            path=label,
            code="timeout",
            message=(
                "acceptance command exceeded the task's time limit; it passed on "
                "the unchanged tree, so the change is what made it hang or slow\n"
                + _excerpt(result)
            ),
        )
    return Finding(
        check=CHECK,
        path=label,
        code="failed",
        message=f"acceptance command failed (exit {result.exit_code})\n"
        + _excerpt(result),
    )


def _did_not_run_note(command: Sequence[str], result: CommandResult) -> str:
    """The environment-issue line for a command that never ran."""
    detail = result.stderr.strip() or f"exit {result.exit_code}"
    return (
        f"acceptance: {_label(command)} could not run — {detail}; this is a "
        "missing dependency, an environment fault, not a rejected change"
    )


def _as_preflight(
    command: Sequence[str], outcome: _Outcome, result: CommandResult
) -> PreflightIssue | None:
    """Map a baseline command outcome to a preflight issue (``None`` if clean)."""
    if outcome is _Outcome.PASSED:
        return None
    label = _label(command)
    if outcome is _Outcome.DID_NOT_RUN:
        detail = result.stderr.strip() or f"exit {result.exit_code}"
        return PreflightIssue(
            "acceptance-unavailable",
            f"acceptance command cannot run on this machine: {label} — {detail}. "
            "A missing dependency is an environment fault, not a worker failure.",
        )
    if outcome is _Outcome.TIMED_OUT:
        return PreflightIssue(
            "acceptance-baseline-timeout",
            f"acceptance command did not finish within the time limit on the "
            f"unchanged tree: {label}. Raise the limit or fix the suite before "
            "spending an attempt against it.",
        )
    if outcome is _Outcome.ALTERED_TREE:
        return PreflightIssue(
            "acceptance-mutates-tree",
            f"acceptance command modifies the working tree with no change applied: "
            f"{label}. An acceptance command must be read-only, or the gate would "
            "judge the worker's diff plus the command's edits.",
        )
    return PreflightIssue(
        "acceptance-baseline-failing",
        f"acceptance command already fails before any change is made: {label}. "
        "The suite is not a usable acceptance signal until it is green.\n"
        + _excerpt(result),
    )


# --- helpers -------------------------------------------------------------


def _label(command: Sequence[str]) -> str:
    """A shell-readable rendering of a command, for a finding or an issue."""
    return shlex.join(command)


def _excerpt(result: CommandResult) -> str:
    """The failing part of a command's output — the tail of its two streams.

    Combines stdout and stderr and keeps the end, because a test runner prints
    its passes first and its failures, tracebacks and summary last: a truncated
    head could be all green while the change is red (the exact failure #38's
    acceptance criteria call out).
    """
    parts = [
        stream.rstrip("\n")
        for stream in (result.stdout, result.stderr)
        if stream.strip()
    ]
    combined = "\n".join(parts)
    return _tail(combined) if combined else "(command produced no output)"


def _tail(text: str) -> str:
    """Keep the last lines and characters of ``text``, marking any elision."""
    truncated = False
    lines = text.split("\n")
    if len(lines) > _MAX_EXCERPT_LINES:
        lines = lines[-_MAX_EXCERPT_LINES:]
        truncated = True
    tail = "\n".join(lines)
    if len(tail) > _MAX_EXCERPT_CHARS:
        tail = tail[-_MAX_EXCERPT_CHARS:]
        truncated = True
    return f"…(earlier output omitted)…\n{tail}" if truncated else tail


def _worktree_tree(workspace: Path) -> str:
    """A content hash of the workspace tree, honouring ``.gitignore``.

    Written into a *throwaway* index so the sandbox's own index and working
    tree are never touched. ``add -A`` then ``write-tree`` yields the SHA of
    exactly the content the gate's change-set sees — ignored paths (a test
    runner's caches) are excluded, so a run that only writes those is correctly
    not counted as altering the tree. Comparing the SHA before and after a
    command is how tree alteration is detected.
    """
    with tempfile.TemporaryDirectory(prefix="mcgyvr-accept-") as tmp:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(tmp) / "index")}
        _git(workspace, "add", "-A", env=env)
        return _git(workspace, "write-tree", env=env).decode("ascii").strip()


def _git(root: Path, *args: str, env: dict[str, str]) -> bytes:
    """Run git in ``root`` with the throwaway index; raise on failure."""
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        env=env,
    )
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise AcceptanceError(f"git {args[0]} failed in {root}: {detail}")
    return proc.stdout
