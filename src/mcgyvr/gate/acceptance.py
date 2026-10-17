""

from __future__ import annotations

import shlex
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum, auto

from mcgyvr.gate.findings import Finding
from mcgyvr.gate.preflight import PreflightIssue
from mcgyvr.sandbox.base import CommandResult, Restored, Sandbox

#
CHECK = "acceptance"

#
#
#gram
#
#
#
#
#
#
DID_NOT_RUN = frozenset({126, 127})

#at
#
_NOT_FOUND = 127

#
#
_MAX_EXCERPT_LINES = 40
_MAX_EXCERPT_CHARS = 4000


class _Outcome(Enum):
    ""

    PASSED = auto()
    FAILED = auto()  #ed
    DID_NOT_RUN = auto()  #on
    TIMED_OUT = auto()  #
    ALTERED_TREE = auto()  #ed


@dataclass(frozen=True)
class _Ran:
    ""

    outcome: _Outcome
    result: CommandResult
    altered: tuple[str, ...] = ()


@dataclass(frozen=True)
class AcceptanceReport:
    ""

    findings: tuple[Finding, ...] = ()
    environment_issues: tuple[str, ...] = ()
    #
    #
    #
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Baseline:
    ""

    issue: PreflightIssue | None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Acceptance:
    ""

    sandbox: Sandbox
    commands: tuple[tuple[str, ...], ...]
    timeout: float | None = None
    demonstrations: tuple[tuple[str, ...], ...] = ()

    def baseline(self) -> Baseline:
        ""
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
        ""
        return self.baseline().issue

    def run(self) -> AcceptanceReport:
        ""
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
        ""
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


#
#
_AT_BASELINE = "baseline"
_AT_GATE = "gate"


def _role(demonstrates: bool) -> str:
    ""
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
    ""
    after = (
        "so the first attempt starts on a clean copy"
        if when == _AT_BASELINE
        else "none of it is part of the change"
    )
    return (
        f"{role}: {_label(command)} left {restored.named()} in the workspace; "
        f"cleaned up after it ran, {after}"
    )


#--


def _as_finding(command: Sequence[str], ran: _Ran, demonstrates: bool) -> Finding:
    ""
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
    ""
    detail = result.stderr.strip() or f"exit {result.exit_code}"
    program = command[0] if command else ""
    if result.exit_code == _NOT_FOUND or "=" in program or "/" not in program:
        detail += " (commands run without a shell)"
    return detail


def _did_not_run_note(command: Sequence[str], result: CommandResult, role: str) -> str:
    ""
    detail = _not_run_detail(command, result)
    return (
        f"{role}: {_label(command)} could not run — {detail}; this is a "
        "missing dependency, an environment fault, not a rejected change"
    )


def _as_preflight(
    command: Sequence[str], outcome: _Outcome, result: CommandResult
) -> PreflightIssue | None:
    ""
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
    ""
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


#


def _label(command: Sequence[str]) -> str:
    ""
    return shlex.join(command)


def _excerpt(result: CommandResult) -> str:
    ""
    parts = [
        stream.rstrip("\n")
        for stream in (result.stdout, result.stderr)
        if stream.strip()
    ]
    combined = "\n".join(parts)
    return _tail(combined) if combined else "(command produced no output)"


def _tail(text: str) -> str:
    ""
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
