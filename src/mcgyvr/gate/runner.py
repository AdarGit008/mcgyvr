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

Acceptance-command execution (#38) is the last rung and needs the per-task
sandbox (E4) to run in; the gate accepts a runner for it when one is wired.

Every finding is attributed to a worker-added line wherever the check can know
one. A tool that is not installed is recorded as an *environment* issue, not a
worker rejection — a keyless or minimal install still reaches a verdict on the
checks it could run.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from mcgyvr.gate.adapter import LanguageAdapter, ToolUnavailableError
from mcgyvr.gate.adapters import PythonAdapter
from mcgyvr.gate.changeset import ChangeSet, FileChange
from mcgyvr.gate.findings import Finding
from mcgyvr.gate.secrets import scan_secrets
from mcgyvr.gate.structured import validate_structured_data
from mcgyvr.scope import Scope


@dataclass(frozen=True)
class GateResult:
    """The gate's verdict on one change.

    ``accepted`` is simply the absence of findings. ``environment_issues`` are
    things that stopped a check from running (a missing tool) — they do not by
    themselves reject the worker, but they are surfaced so a degraded run is
    never mistaken for a fully-checked one.
    """

    findings: tuple[Finding, ...] = ()
    environment_issues: tuple[str, ...] = field(default=())

    @property
    def accepted(self) -> bool:
        return not self.findings

    def by_check(self) -> dict[str, list[Finding]]:
        grouped: dict[str, list[Finding]] = {}
        for finding in self.findings:
            grouped.setdefault(finding.check, []).append(finding)
        return grouped


class Gate:
    """The deterministic acceptance gate over a set of language adapters."""

    def __init__(self, adapters: Sequence[LanguageAdapter] | None = None) -> None:
        self.adapters: tuple[LanguageAdapter, ...] = (
            tuple(adapters) if adapters is not None else (PythonAdapter(),)
        )

    def run(self, changeset: ChangeSet, scope: Scope | None = None) -> GateResult:
        findings: list[Finding] = []

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
        for adapter in self.adapters:
            findings.extend(self._run_adapter(adapter, changeset, env_issues))

        return GateResult(
            findings=tuple(findings),
            environment_issues=tuple(env_issues),
        )

    def _run_adapter(
        self,
        adapter: LanguageAdapter,
        changeset: ChangeSet,
        env_issues: list[str],
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
            findings.extend(adapter.structural_checks(change, repo))

        if not syntax_clean:
            return findings

        # Batched, so the subprocess count is per-adapter, not per-file.
        for label, check in (("lint", adapter.lint), ("format", adapter.format_check)):
            try:
                findings.extend(check(syntax_clean, repo))
            except ToolUnavailableError as exc:
                env_issues.append(
                    f"{adapter.name}: {exc.tool} not installed — {label} skipped"
                )
        return findings
