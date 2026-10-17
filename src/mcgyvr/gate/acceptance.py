"""Acceptance and demonstration commands, run inside the sandbox as the gate.

``commands`` must pass. ``demonstrations`` are the other way round: they must
fail on the unchanged tree, to show the defect is real, and pass once it is
fixed. Each command is tried on the untouched tree — ``baseline()``, and
``precondition()`` for its issue alone — to decide whether the contract names a
usable signal at all, and again against the worker's tree in ``run()``; either
pass stops at the first command that settles the question.

Every run is bracketed by a snapshot and a restore: what a command leaves
behind is put back and noted, and a command that rewrites part of the worker's
own change is a finding (``tree-altering``) rather than a pass over bytes the
worker did not write. A command that never ran (exit 126/127) is an
environment issue, never a rejected change.
"""

from __future__ import annotations

import shlex
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum, auto

from mcgyvr.gate.findings import Finding
from mcgyvr.gate.preflight import PreflightIssue
from mcgyvr.sandbox.base import CommandResult, Restored, Sandbox

# The check name stamped on the findings this rung raises.
CHECK = "acceptance"

# Exit codes that mean the command never ran at all: 126 is "found but not
# executable", 127 is "no such program".
# The sandbox runs argv directly, with no shell, so a `VAR=value cmd` spelling
# is looked up as the program name and lands on 127 as well, and either code
# makes the outcome an environment issue: the command produced no result, so
# nothing about the change is judged and the worker is not charged with a
# failure.
# A timeout is classified before the exit code is consulted, and a command
# that ran and exited non-zero on its own is a plain failure.
DID_NOT_RUN = frozenset({126, 127})

# 127 on its own, checked by name where a report explains that the command
# never ran at all.
_NOT_FOUND = 127

# Caps on the excerpt a finding quotes: the failing part of a suite's output is
# at its end, so the tail is kept — the last 40 lines, at most 4000 characters.
_MAX_EXCERPT_LINES = 40
_MAX_EXCERPT_CHARS = 4000


class _Outcome(Enum):
    """How one run of one acceptance command is judged."""

    PASSED = auto()
    FAILED = auto()  # exited non-zero, and it did run
    DID_NOT_RUN = auto()  # exit 126/127: no such program, or not executable
    TIMED_OUT = auto()  # killed at the limit: no verdict either way
    ALTERED_TREE = auto()  # put back, and its files are part of the change


@dataclass(frozen=True)
class _Ran:
    """One executed command: its outcome, the raw result, and the paths of the
    change it rewrote when the outcome is ``ALTERED_TREE``."""

    outcome: _Outcome
    result: CommandResult
    altered: tuple[str, ...] = ()


@dataclass(frozen=True)
class AcceptanceReport:
    """What the gate gets from the worker's tree: a finding for each command
    that did not pass, an environment issue for each one that could not run,
    and the cleanup notes gathered on the way."""

    findings: tuple[Finding, ...] = ()
    environment_issues: tuple[str, ...] = ()
    # Cleanup remarks in the order the commands ran: what a command left
    # behind, which was put back, and why that is not charged. They are
    # reported beside the verdict, not as part of it.
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Baseline:
    """The commands' state on the unchanged tree: the first reason the contract
    names no usable signal, or ``None``, plus the cleanup notes gathered."""

    issue: PreflightIssue | None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Acceptance:
    """The contract's commands, run in a sandbox: ``commands`` must pass, and
    ``demonstrations`` must fail on the unchanged tree and pass after the
    change."""

    sandbox: Sandbox
    commands: tuple[tuple[str, ...], ...]
    timeout: float | None = None
    demonstrations: tuple[tuple[str, ...], ...] = ()

    def baseline(self) -> Baseline:
        """Try every command once on the unchanged tree and report the first
        reason the resulting signal is unusable. Demonstrations go first, so the
        one command settling whether the defect is real is tried before the
        whole regression suite."""
        notes: list[str] = []
        for command in self.demonstrations:
            ran = self._run_one(command, notes, when=_AT_BASELINE, demonstrates=True)
            issue = _demonstration_preflight(command, ran.outcome, ran.result)
            if issue is not None:
                return Baseline(issue, tuple(notes))
        for command in self.commands:
            ran = self._run_one(command, notes, when=_AT_BASELINE, demonstrates=False)
            issue = _as_preflight(command, ran.outcome, ran.result)
            if issue is not None:
                return Baseline(issue, tuple(notes))
        return Baseline(None, tuple(notes))

    def precondition(self) -> PreflightIssue | None:
        """The baseline's issue alone: ``None`` when the commands are a usable
        signal on the tree as it stands."""
        return self.baseline().issue

    def run(self) -> AcceptanceReport:
        """Run every command against the worker's tree. A passing command adds
        nothing; one that could not run is an environment issue; anything else
        is a finding, and a rewritten change ends the run because the change is
        already rejected."""
        findings: list[Finding] = []
        env_issues: list[str] = []
        notes: list[str] = []
        judged = [(c, True) for c in self.demonstrations]
        judged += [(c, False) for c in self.commands]
        for command, demonstrates in judged:
            ran = self._run_one(
                command, notes, when=_AT_GATE, demonstrates=demonstrates
            )
            if ran.outcome is _Outcome.PASSED:
                continue
            if ran.outcome is _Outcome.DID_NOT_RUN:
                env_issues.append(
                    _did_not_run_note(command, ran.result, _role(demonstrates))
                )
                continue
            findings.append(_as_finding(command, ran, demonstrates))
            if ran.outcome is _Outcome.ALTERED_TREE:
                break
        return AcceptanceReport(tuple(findings), tuple(env_issues), tuple(notes))

    def _run_one(
        self,
        command: Sequence[str],
        notes: list[str],
        *,
        when: str,
        demonstrates: bool,
    ) -> _Ran:
        """Snapshot, run one command, then restore the tree: whatever the
        command left behind is put back and noted under its role. At the gate
        only, a file the command rewrote that is also part of the worker's
        change makes the outcome ``ALTERED_TREE`` — on the unchanged tree there
        is no change for it to rewrite."""
        before = self.sandbox.snapshot()
        result = self.sandbox.run(command, timeout=self.timeout)
        restored = self.sandbox.restore(before)
        if not restored:
            return _Ran(_classify(result), result)
        notes.append(_cleanup_note(command, restored, when, _role(demonstrates)))
        if when == _AT_GATE and restored.reverted:
            change = self.sandbox.changed_since_base(before)
            altered = tuple(path for path in restored.reverted if path in change)
            if altered:
                return _Ran(_Outcome.ALTERED_TREE, result, altered)
        return _Ran(_classify(result), result)


# The two moments a command is run, quoted in cleanup notes and compared to
# decide whether a restored file counts as an alteration.
_AT_BASELINE = "baseline"
_AT_GATE = "gate"


def _role(demonstrates: bool) -> str:
    """The word a note uses for the list the command came from."""
    return "demonstration" if demonstrates else CHECK


def _classify(result: CommandResult) -> _Outcome:
    if result.timed_out:
        return _Outcome.TIMED_OUT
    if result.exit_code in DID_NOT_RUN:
        return _Outcome.DID_NOT_RUN
    if result.exit_code != 0:
        return _Outcome.FAILED
    return _Outcome.PASSED


def _cleanup_note(
    command: Sequence[str], restored: Restored, when: str, role: str
) -> str:
    """Say what a command left behind and that it was cleaned up, worded for
    the moment it ran: a baseline leftover is cleared so the first attempt
    starts on a clean copy, a gate leftover is not part of the change."""
    after = (
        "so the first attempt starts on a clean copy"
        if when == _AT_BASELINE
        else "none of it is part of the change"
    )
    return (
        f"{role}: {_label(command)} left {restored.named()} in the workspace; "
        f"cleaned up after it ran, {after}"
    )


# --- from a judged run to the finding or issue that reports it --------------


def _as_finding(command: Sequence[str], ran: _Ran, demonstrates: bool) -> Finding:
    """The finding for a run that did not pass, keyed by its outcome: a rewrite
    of the change, a timeout, a demonstration that still fails, or a plain
    failure."""
    label = _label(command)
    outcome, result = ran.outcome, ran.result
    if outcome is _Outcome.ALTERED_TREE:
        rewrote = Restored(reverted=ran.altered).named()
        return Finding(
            check=CHECK,
            path=label,
            names_a_file=False,
            code="tree-altering",
            message=(
                f"acceptance command rewrote {rewrote}, part of the change — its "
                "verdict is about bytes the worker did not write, so it cannot "
                "accept them. The files are put back; an acceptance command "
                "must check the change, not edit it (`--check`, `--diff`)"
            ),
        )
    if outcome is _Outcome.TIMED_OUT:
        baseline = (
            "it failed promptly on the unchanged tree"
            if demonstrates
            else "it passed on the unchanged tree"
        )
        return Finding(
            check=CHECK,
            path=label,
            names_a_file=False,
            code="timeout",
            message=(
                f"acceptance command exceeded the task's time limit; {baseline}, "
                "so the change is what made it hang or slow\n" + _excerpt(result)
            ),
        )
    if demonstrates:
        return Finding(
            check=CHECK,
            path=label,
            names_a_file=False,
            code="demonstration-failed",
            message=(
                f"demonstrating command still fails after the change "
                f"(exit {result.exit_code}) — it failed on the unchanged tree to "
                f"demonstrate the defect, and it was to pass once the defect was "
                f"fixed; the defect the contract names is not fixed\n"
                + _excerpt(result)
            ),
        )
    return Finding(
        check=CHECK,
        path=label,
        names_a_file=False,
        code="failed",
        message=f"acceptance command failed (exit {result.exit_code})\n"
        + _excerpt(result),
    )


def _not_run_detail(command: Sequence[str], result: CommandResult) -> str:
    """Why the command never ran: its stderr, or the bare exit code, plus the
    reminder that no shell is involved when the program token could not have
    been a path (no separator, or a `VAR=value` assignment) and on exit 127."""
    detail = result.stderr.strip() or f"exit {result.exit_code}"
    program = command[0] if command else ""
    if result.exit_code == _NOT_FOUND or "=" in program or "/" not in program:
        detail += " (commands run without a shell)"
    return detail


def _did_not_run_note(command: Sequence[str], result: CommandResult, role: str) -> str:
    """The note reporting a command that could not run as an environment fault
    rather than a rejected change."""
    detail = _not_run_detail(command, result)
    return (
        f"{role}: {_label(command)} could not run — {detail}; this is a "
        "missing dependency, an environment fault, not a rejected change"
    )


def _as_preflight(
    command: Sequence[str], outcome: _Outcome, result: CommandResult
) -> PreflightIssue | None:
    """The baseline issue for an acceptance command, ``None`` when it passed: it
    cannot run, it timed out on the unchanged tree, or the suite is already
    red."""
    if outcome is _Outcome.PASSED:
        return None
    label = _label(command)
    if outcome is _Outcome.DID_NOT_RUN:
        detail = _not_run_detail(command, result)
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
    return PreflightIssue(
        "acceptance-baseline-failing",
        f"acceptance command already fails before any change is made: {label}. "
        "The suite is not a usable acceptance signal until it is green. If "
        "this command is meant to fail until the change lands, it belongs in "
        "`demonstration`, not `acceptance`.\n" + _excerpt(result),
    )


def _demonstration_preflight(
    command: Sequence[str], outcome: _Outcome, result: CommandResult
) -> PreflightIssue | None:
    """The baseline issue for a demonstrating command, ``None`` when it failed
    as intended: it cannot run, it timed out (a kill is no verdict on the
    defect), or it already passes on the unchanged tree."""
    if outcome is _Outcome.FAILED:
        return None
    label = _label(command)
    if outcome is _Outcome.DID_NOT_RUN:
        detail = _not_run_detail(command, result)
        return PreflightIssue(
            "acceptance-unavailable",
            f"demonstrating command cannot run on this machine: {label} — "
            f"{detail}. A missing dependency is an environment fault, not a "
            "worker failure.",
        )
    if outcome is _Outcome.TIMED_OUT:
        return PreflightIssue(
            "acceptance-baseline-timeout",
            f"demonstrating command did not finish within the time limit on "
            f"the unchanged tree: {label}. A kill is not a failure, so nothing "
            "was demonstrated — if the defect itself is a hang, the "
            "demonstrating test must bound the wait and fail by its own "
            "verdict rather than the runner's kill.",
        )
    return PreflightIssue(
        "demonstration-passes-at-baseline",
        f"demonstrating command already passes before any change is made: "
        f"{label}. It was to fail on the unchanged tree to demonstrate the "
        "defect — passing here means either the defect does not exist or the "
        "command does not exercise it, and no change could ever be evidenced "
        "against it.",
    )


# Turning a command into the text a finding, issue or note quotes.


def _label(command: Sequence[str]) -> str:
    """The command as one shell-quoted string, for quoting in a message."""
    return shlex.join(command)


def _excerpt(result: CommandResult) -> str:
    """The command's output for a message: whichever streams are non-empty, in
    order, tailed to the end where the failure is, or a placeholder when both
    are blank."""
    parts = [
        stream.rstrip("\n")
        for stream in (result.stdout, result.stderr)
        if stream.strip()
    ]
    combined = "\n".join(parts)
    return _tail(combined) if combined else "(command produced no output)"


def _tail(text: str) -> str:
    """Keep the last lines and characters of a text, marking the elision when
    earlier output was dropped."""
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
