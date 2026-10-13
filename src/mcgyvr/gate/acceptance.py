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
3. **The command rewrote the change** — a formatter listed as a check, say,
   that rewrites the very file the worker wrote. Its verdict is then about
   bytes the worker did not write, so it cannot accept them: the command fails
   **by name**, with the paths it rewrote.

What a command merely leaves behind is not a fourth outcome. A test runner
writes ``__pycache__`` and ``.pytest_cache``, a tool writes its cache, and none
of it is the change. The workspace is snapshotted before each command and
restored after it (:meth:`~mcgyvr.sandbox.base.Sandbox.restore`): what the
command created is removed, nested repositories first, and what it rewrote is
put back. Each command, and the first attempt after the preflight, starts on
the tree it was handed, and what was cleaned is said in a note naming the
paths (e2e run 1, F4).

Two command lists with opposite baseline expectations (#183):

- ``commands`` is the regression suite: it must **pass** on the unchanged tree
  and pass after the change.
- ``demonstrations`` is the ``failing_test_first`` evidence: each command must
  **fail** on the unchanged tree — a demonstration that passes at baseline
  demonstrates nothing, and is refused exactly as loudly as a regression suite
  that is already red — and pass after the change. They are separate fields
  because membership in one flat list cannot carry an expectation; the
  contract's ``acceptance`` / ``demonstration`` split maps here one to one.

Two entry points, one classifier:

- :meth:`Acceptance.precondition` runs both lists once against the *unchanged*
  tree, before the first worker attempt. A regression suite that is already
  red, a demonstration that already passes, a command that cannot run: none
  is a usable acceptance signal — and catching that
  here, as a :class:`~mcgyvr.gate.preflight.PreflightIssue`, spends no attempt
  and names the fault as the orchestration error it is. It also earns the
  interpretation :meth:`run` relies on: once the baseline behaviour of both
  lists is known, a later failure or timeout is the worker's.
- :meth:`Acceptance.run` is the gate's last rung, over the applied change,
  where both lists must pass — the pair of runs is what makes
  ``failing_test_first`` mean what it claims.

Output handed back to a retry keeps the **tail** of a command's streams, never
a truncated head — a test runner prints its passes first and its failures and
summary last, so a head could be all green while the change is red.
"""

from __future__ import annotations

import shlex
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum, auto

from mcgyvr.gate.findings import Finding
from mcgyvr.gate.preflight import PreflightIssue
from mcgyvr.sandbox.base import CommandResult, Restored, Sandbox

# The check name every acceptance finding carries, so a caller can group by it.
CHECK = "acceptance"

#: Conventional shell exit codes for a command that never ran: 127 when the
#: binary is not found, 126 when it is found but cannot be executed. Both are
#: "could not run" — an environment fault — as opposed to a code a program
#: returns to say it ran and failed, which is the worker's.
#:
#: Public because :mod:`mcgyvr.drive` draws the same distinction over the
#: deterministic floor's programs, and two definitions of "did not run" is a
#: defect waiting to happen: the rule is stated here, where the gate's
#: environment-issue channel is defined, and read there.
DID_NOT_RUN = frozenset({126, 127})

# Of the two, the one that says the program was not found — which is also what
# a ``VAR=x cmd`` prefix or a shell keyword comes to when executed directly.
_NOT_FOUND = 127

# How much of a failing command's output to carry. Kept from the tail, so the
# failing part survives even when the passes before it are voluminous.
_MAX_EXCERPT_LINES = 40
_MAX_EXCERPT_CHARS = 4000


class _Outcome(Enum):
    """How one acceptance command turned out. The five cases #38 must separate."""

    PASSED = auto()
    FAILED = auto()  # ran and returned non-zero — the worker's change is red
    DID_NOT_RUN = auto()  # 126/127 — an environment fault, not a rejection
    TIMED_OUT = auto()  # killed at the wall-clock ceiling
    ALTERED_TREE = auto()  # rewrote a file of the change — the run is invalidated


@dataclass(frozen=True)
class _Ran:
    """One command's outcome, its result, and what it rewrote of the change."""

    outcome: _Outcome
    result: CommandResult
    altered: tuple[str, ...] = ()


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
    #: What the commands left behind and the rung cleaned up, one sentence per
    #: command that left anything. Never a verdict: none of it was the change,
    #: which is also why the gate does not fold it into its result.
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Baseline:
    """What :meth:`Acceptance.baseline` found on the unchanged tree.

    ``issue`` is the reason the run should not start, or ``None``; ``notes``
    name what the baseline commands left behind and the preflight removed, so
    the first attempt starts on a clean copy.
    """

    issue: PreflightIssue | None = None
    notes: tuple[str, ...] = ()


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
    demonstrations: tuple[tuple[str, ...], ...] = ()

    def baseline(self) -> Baseline:
        """Verify both lists are a usable signal on the unchanged tree.

        Runs each command against the base, before any worker change. The
        demonstrations go first — one command settling whether the defect is
        real at all is cheaper than a whole suite, and a demonstration that
        passes at baseline means no fix could ever be evidenced, whatever the
        suite says. Each must *fail*; anything else — passing, not running,
        timing out — is reported. Then the regression commands, each of which
        must pass. The first problem either way is a
        :class:`~mcgyvr.gate.preflight.PreflightIssue` — an orchestration
        error distinct from a rejected change — and stops the check: a suite
        that cannot establish a clean baseline tells us nothing about a
        worker's diff. No issue is what lets :meth:`run` read a later failure
        as the worker's.

        What a command writes is never an issue here (owner ruling, e2e run 1
        F4). There is no change yet for it to have rewritten, so all of it —
        caches, files it rewrote, a nested repository — is cleaned up after the
        command, and each command that left anything gets a note naming it.
        """
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
        """:meth:`baseline`'s issue alone, for a caller with no use for its notes."""
        return self.baseline().issue

    def run(self) -> AcceptanceReport:
        """Run both lists over the applied change and judge them — all must pass.

        The demonstrations run first, in the same order as
        :meth:`precondition`: they failed at baseline, so one still failing is
        the headline — the defect the contract names is not fixed. A command
        that could not run becomes an environment issue, never a finding. A
        command that rewrote a file of the change fails by name and stops the
        run: the change is already rejected, and a suite is the dearest thing
        the gate runs. Other failures and timeouts accumulate as findings
        carrying the tail of the command's output. What a command only left
        behind is cleaned up and noted, never charged.
        """
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
        """Run one command, put the workspace back, and classify the run.

        Classified by deterministic signals only. A rewrite of the change is
        checked first, because it invalidates the run whatever the exit code;
        then the wall-clock kill, then the shell's did-not-run codes, then any
        other non-zero exit. At the baseline there is no change to rewrite.
        ``demonstrates`` says which list the command came from, so a note
        labels it by its role (e2e run 2, R6).
        """
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


#: When a command ran, for the note on what it left: on the unchanged tree
#: before the first attempt, or over a change at the gate.
_AT_BASELINE = "baseline"
_AT_GATE = "gate"


def _role(demonstrates: bool) -> str:
    """The contract field a command came from, which is how a note labels it.

    The contract splits its checks into ``acceptance`` and ``demonstration``;
    a note about a demonstration that says ``acceptance:`` names a list the
    command is not in (e2e run 2, R6).
    """
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
    """The sentence naming what one command left behind and what became of it."""
    after = (
        "so the first attempt starts on a clean copy"
        if when == _AT_BASELINE
        else "none of it is part of the change"
    )
    return (
        f"{role}: {_label(command)} left {restored.named()} in the workspace; "
        f"cleaned up after it ran, {after}"
    )


# --- outcome → report mapping --------------------------------------------


def _as_finding(command: Sequence[str], ran: _Ran, demonstrates: bool) -> Finding:
    """Turn a rejecting outcome into a finding that names the command.

    ``demonstrates`` marks a command from the demonstration list, whose
    baseline behaviour was the opposite — it changes what a failure and a
    timeout can honestly be blamed on, so their wording differs.
    """
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
    """Why a command never ran, noting the missing shell where it may be why.

    Commands are executed with no shell, so a ``VAR=x`` prefix is run as a
    program of that name, and ``&&`` or a pipe reaches the first program as an
    argument; both read as a missing dependency unless something says so.
    The loader refuses that syntax in a contract, so this is for argv that
    reached the gate another way, and for a program that really is missing.

    "Not found" is read from the exit code *or* from a bare program name:
    a name looked up on ``PATH`` that never ran is a not-found in practice
    even when it surfaces as 126, because Python's lookup reports an
    unreadable ``PATH`` entry's ``EACCES`` in preference to ``ENOENT``. Only a
    program named by its path and refused (126) is certainly not about the
    shell.
    """
    detail = result.stderr.strip() or f"exit {result.exit_code}"
    program = command[0] if command else ""
    if result.exit_code == _NOT_FOUND or "=" in program or "/" not in program:
        detail += " (commands run without a shell)"
    return detail


def _did_not_run_note(command: Sequence[str], result: CommandResult, role: str) -> str:
    """The environment-issue line for a command that never ran."""
    detail = _not_run_detail(command, result)
    return (
        f"{role}: {_label(command)} could not run — {detail}; this is a "
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
    """Map a demonstration's baseline outcome to a preflight issue.

    The expectation is inverted — only a command that *failed* demonstrated
    the defect — but the environment faults are the same faults, so they keep
    the same reasons as the regression list. A kill is not a verdict: a
    demonstration that times out at baseline has not failed, it has been
    stopped, so it too is refused rather than counted as demonstrating.
    """
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
