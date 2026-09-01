"""The gate: order the checks, judge the change, return one result.

This is E5's aggregator (#32). It takes a change set (computed once, #33) and
runs every check against it in a deliberate order, cheapest and most decisive
first:

1. **scope** — did the worker touch only what its contract allowed? (#34)
2. **secrets** — did it add a credential? (#37)

Both are hard, safety-critical failures, so if either fires the run stops
there: there is no value in linting a change that leaks a key or escaped its
scope, and stopping saves the expensive subprocesses.

3. **structured data** — do changed JSON/YAML files still parse? (#39)
4. per language adapter (#35): **syntax** fast-fail, then **structural**
   hazards on added lines, then batched **lint** and **format** — a file that
   fails to parse is not linted, and lint/format run once per adapter over all
   its files, so the subprocess count stays flat as the change grows.

5. **semantic resolution** — do the names the worker called exist in the
   environment this repository declares? (#123) This one needs the per-task
   sandbox, because answering it means importing the target's own packages.
6. **acceptance commands** — the contract's own suite (#38), also in the
   sandbox.

Both sandboxed rungs are injected rather than constructed, and the cheaper of
the two goes first: a sub-second resolution pass has no business queueing
behind a test suite (ADR-0010).

Every finding is attributed to a worker-added line wherever the check can know
one. A tool that is not installed is recorded as an *environment* issue, not a
worker rejection — a keyless or minimal install still reaches a verdict on the
checks it could run. A tool that is installed and then *fails* is a different
thing and ADR-0034 gives it a different answer: the rung is recorded as
inconclusive and the change is not accepted, because a rung that cannot say
what bar it applied reported clean while applying none.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from mcgyvr.gate.acceptance import Acceptance
from mcgyvr.gate.adapter import (
    LanguageAdapter,
    ToolFailedError,
    ToolUnavailableError,
)
from mcgyvr.gate.adapters import JavaScriptAdapter, PythonAdapter
from mcgyvr.gate.changeset import ChangeSet, FileChange
from mcgyvr.gate.findings import Finding
from mcgyvr.gate.secrets import scan_secrets
from mcgyvr.gate.semantic import SemanticCheck
from mcgyvr.gate.structured import validate_structured_data
from mcgyvr.gate.typecheck import STYLE, TypeCheck, TypeCheckTimeoutError
from mcgyvr.scope import Scope


@dataclass(frozen=True)
class InconclusiveRung:
    """A rung that ran, and cannot say what bar it applied.

    Not a finding: it makes no claim about the worker's change. Not merely an
    environment issue either, because an absent tool leaves a legible hole and
    this leaves none — the tool was there, it exited, and the rung reported
    clean over a bar that never ran (#261, ADR-0034).

    Carried structured rather than as a sentence because a run manifest has to
    be able to answer *which rung was inconclusive* per row, and a rate quoted
    from rows where lint could not run is not the rate it claims to be.
    """

    adapter: str
    rung: str
    tool: str
    exit_code: int
    detail: str = ""

    def __str__(self) -> str:
        suffix = f" ({self.detail})" if self.detail else ""
        return (
            f"{self.adapter}: {self.rung} is inconclusive — {self.tool} exited "
            f"{self.exit_code}{suffix}"
        )


@dataclass(frozen=True)
class GateResult:
    """The gate's verdict on one change.

    ``accepted`` requires two things: no findings, and no rung that could not
    say whether it ran. ``environment_issues`` are things that stopped a check
    from running (a missing tool) — they do not by themselves reject the worker,
    but they are surfaced so a degraded run is never mistaken for a
    fully-checked one.

    ``inconclusive`` is the stronger case and it *does* reject (ADR-0034). A
    missing linter is a hole the operator can see; a linter that crashed is a
    hole that looks like a pass, and this project has hit that three times.
    Every inconclusive rung is also rendered into ``environment_issues``, so a
    reader that only knows about the older field still sees it.

    ``observations`` are findings a rung reported without rejecting on: real,
    line-attributed, and deliberately not part of the verdict. The semantic
    rung (#123) starts there, because the sample behind its false-positive
    rate is thin (#129) and a check that argues with correct code costs every
    change while catching few. Promoting a rung from observation to rejection
    is a policy flip, not a rewrite.
    """

    findings: tuple[Finding, ...] = ()
    environment_issues: tuple[str, ...] = field(default=())
    observations: tuple[Finding, ...] = field(default=())
    inconclusive: tuple[InconclusiveRung, ...] = field(default=())

    @property
    def accepted(self) -> bool:
        return not self.findings and not self.inconclusive

    def by_check(self) -> dict[str, list[Finding]]:
        grouped: dict[str, list[Finding]] = {}
        for finding in self.findings:
            grouped.setdefault(finding.check, []).append(finding)
        return grouped


class Gate:
    """The deterministic acceptance gate over a set of language adapters."""

    def __init__(self, adapters: Sequence[LanguageAdapter] | None = None) -> None:
        self.adapters: tuple[LanguageAdapter, ...] = (
            tuple(adapters)
            if adapters is not None
            else (PythonAdapter(), JavaScriptAdapter())
        )

    def run(
        self,
        changeset: ChangeSet,
        scope: Scope | None = None,
        *,
        semantic: SemanticCheck | None = None,
        acceptance: Acceptance | None = None,
        typecheck: TypeCheck | None = None,
        contract_text: str = "",
    ) -> GateResult:
        """Judge one change set. ``contract_text`` is the contract's own prose.

        Only one rung reads it — ``param-mutation``, which a contract can
        order and therefore has to be able to stand down (see
        :meth:`~mcgyvr.gate.adapter.LanguageAdapter.structural_checks`). It is
        a plain string with an empty default because the gate must still reach
        a verdict for a caller holding no contract, and that verdict is the
        strict one: a rung that read an absent contract as permission would
        stand down hardest exactly where the least is known.
        """
        findings: list[Finding] = []
        observations: list[Finding] = []

        # 1 & 2 — hard, decisive checks first. A failure here stops the run.
        if scope is not None:
            findings.extend(
                Finding(
                    check="scope",
                    path=path,
                    message=(
                        "path is explicitly forbidden by the contract"
                        if scope.forbidden(path)
                        else "path is outside the contract's allowed scope"
                    ),
                )
                for path in scope.violations(changeset.paths())
            )
        findings.extend(scan_secrets(changeset))
        if findings:
            return GateResult(findings=tuple(findings))

        # 3 — cheap structural correctness of data files.
        findings.extend(validate_structured_data(changeset))

        # 4 — per-adapter language checks.
        env_issues: list[str] = []
        inconclusive: list[InconclusiveRung] = []
        for adapter in self.adapters:
            for item in self._run_adapter(
                adapter, changeset, env_issues, inconclusive, contract_text
            ):
                (observations if item.check == STYLE else findings).append(item)

        if typecheck is not None and not findings:
            try:
                # The same split as the adapter branch above: a style finding
                # is said out loud and never fatal, whatever rung produced it.
                for item in typecheck.run(changeset):
                    (observations if item.check == STYLE else findings).append(item)
            except TypeCheckTimeoutError as exc:
                # A timeout is a load fault, not a verdict: reported as a skip
                # rather than an inconclusive rejection, so the same change is
                # not accepted on a quiet machine and rejected on a loaded one.
                env_issues.append(f"python: typecheck {exc.detail} — skipped")
            except ToolFailedError as exc:
                rung = InconclusiveRung(
                    adapter="python",
                    rung="typecheck",
                    tool=exc.tool,
                    exit_code=exc.exit_code,
                    detail=exc.detail,
                )
                inconclusive.append(rung)
                env_issues.append(str(rung))
            except ToolUnavailableError as exc:
                env_issues.append(
                    f"python: {exc.tool} not installed — typecheck skipped"
                )

        # 5 — semantic resolution (#123): the first rung that needs the
        # sandbox, and much the cheaper of the two that do. It resolves the
        # names on added lines against the packages the repository actually
        # installs — the coverage `tests_pass` cannot give, since a suite is a
        # verdict on itself and not on a diff (ADR-0010).
        if semantic is not None and not findings:
            semantic_report = semantic.run(changeset)
            findings.extend(semantic_report.findings)
            observations.extend(semantic_report.observations)
            env_issues.extend(semantic_report.environment_issues)

        # 6 — acceptance commands (#38): the strongest signal but the most
        # expensive, needing the sandbox (E4). It runs last and only when
        # nothing cheaper already rejected the change — there is no value in
        # spinning a suite for a diff that already fails lint or leaks a key.
        # A missing tool (an env issue, not a finding) does not hold it back.
        if acceptance is not None and not findings:
            report = acceptance.run()
            findings.extend(report.findings)
            env_issues.extend(report.environment_issues)

        return GateResult(
            findings=tuple(findings),
            environment_issues=tuple(env_issues),
            observations=tuple(observations),
            inconclusive=tuple(inconclusive),
        )

    def _run_adapter(
        self,
        adapter: LanguageAdapter,
        changeset: ChangeSet,
        env_issues: list[str],
        inconclusive: list[InconclusiveRung],
        contract_text: str = "",
    ) -> list[Finding]:
        repo = changeset.repo
        findings: list[Finding] = []
        syntax_clean: list[FileChange] = []
        for change in adapter.owned(changeset.files):
            syntax = adapter.check_syntax(change, repo)
            if syntax:
                findings.extend(syntax)  # a file that can't parse is not linted
                continue
            syntax_clean.append(change)
            findings.extend(
                adapter.structural_checks(change, repo, contract_text=contract_text)
            )

        if not syntax_clean:
            return findings

        # Batched, so the subprocess count is per-adapter, not per-file. Each
        # rung is tried even when the one before it faulted: an operator fixing
        # a broken environment wants both complaints, not one per run.
        for label, check in (("lint", adapter.lint), ("format", adapter.format_check)):
            try:
                findings.extend(check(syntax_clean, repo))
            except ToolFailedError as exc:
                # The tool was there and its answer is unreadable. Recorded in
                # both channels: `inconclusive` decides the verdict, and the
                # rendered sentence keeps every existing reader of
                # `environment_issues` seeing it (ADR-0034).
                rung = InconclusiveRung(
                    adapter=adapter.name,
                    rung=label,
                    tool=exc.tool,
                    exit_code=exc.exit_code,
                    detail=exc.detail,
                )
                inconclusive.append(rung)
                env_issues.append(str(rung))
            except ToolUnavailableError as exc:
                env_issues.append(
                    f"{adapter.name}: {exc.tool} not installed — {label} skipped"
                )
        return findings
