""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import partial

from mcgyvr.gate.acceptance import Acceptance
from mcgyvr.gate.adapter import (
    LanguageAdapter,
    ToolFailedError,
    ToolUnavailableError,
)
from mcgyvr.gate.adapters import JavaScriptAdapter, PythonAdapter
from mcgyvr.gate.changeset import ChangeSet, FileChange
from mcgyvr.gate.findings import Finding
from mcgyvr.gate.jev import JevCheck, JevReport
from mcgyvr.gate.output import OutputChecks
from mcgyvr.gate.secrets import scan_secrets
from mcgyvr.gate.semantic import SemanticCheck, SemanticReport
from mcgyvr.gate.structured import validate_structured_data
from mcgyvr.gate.typecheck import STYLE, TypeCheck, TypeCheckTimeoutError
from mcgyvr.scope import Scope


@dataclass(frozen=True)
class InconclusiveRung:
    ""

    adapter: str
    rung: str
    tool: str
    exit_code: int | None = None
    detail: str = ""

    def __str__(self) -> str:
        suffix = f" ({self.detail})" if self.detail else ""
        if self.exit_code is None:
            verdict = f"{self.tool} not available"
        else:
            verdict = f"{self.tool} exited {self.exit_code}"
        return f"{self.adapter}: {self.rung} is inconclusive — {verdict}{suffix}"


@dataclass(frozen=True)
class GateResult:
    ""

    findings: tuple[Finding, ...] = ()
    environment_issues: tuple[str, ...] = field(default=())
    observations: tuple[Finding, ...] = field(default=())
    inconclusive: tuple[InconclusiveRung, ...] = field(default=())
    semantic: SemanticReport | None = field(default=None)
    """The semantic rung's own report, or ``None`` where the rung did not run.

    The rung is non-blocking, so its findings arrive as ``observations`` and a
    reader cannot tell a rung that ran and saw nothing from a rung that was
    never wired. ``None`` here says the rung did not run; a report says it
    did, and ``resolved`` says how much it saw.
    """

    jev: JevReport | None = field(default=None)
    """The Jev verifier rung's own report, or ``None`` where it did not run.

    Non-blocking by default, so its findings arrive as ``observations``; the
    same ``None``-means-not-run convention as ``semantic``.
    """

    @property
    def accepted(self) -> bool:
        return not self.findings and not self.inconclusive

    def by_check(self) -> dict[str, list[Finding]]:
        grouped: dict[str, list[Finding]] = {}
        for finding in self.findings:
            grouped.setdefault(finding.check, []).append(finding)
        return grouped


class Gate:
    ""

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
        jev: JevCheck | None = None,
        acceptance: Acceptance | None = None,
        typecheck: TypeCheck | None = None,
        output: OutputChecks | None = None,
        contract_text: str = "",
    ) -> GateResult:
        ""
        findings: list[Finding] = []
        observations: list[Finding] = []

        #n.
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

        #s.
        findings.extend(validate_structured_data(changeset))

        #s.
        env_issues: list[str] = []
        inconclusive: list[InconclusiveRung] = []
        for adapter in self.adapters:
            for item in self._run_adapter(
                adapter, changeset, env_issues, inconclusive, contract_text
            ):
                (observations if item.check == STYLE else findings).append(item)

        #es
        #
        #
        #
        #bar.
        if output is not None and not findings:
            output_report = output.run()
            findings.extend(output_report.findings)
            env_issues.extend(output_report.environment_issues)
            inconclusive.extend(output_report.inconclusive)

        if typecheck is not None and not findings:
            try:
                #
                #
                for item in typecheck.run(changeset):
                    (observations if item.check == STYLE else findings).append(item)
            except TypeCheckTimeoutError as exc:
                #
                #
                #
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

        #he
        #
        #
        # a
        #
        semantic_report: SemanticReport | None = None
        if semantic is not None and not findings:
            semantic_report = semantic.run(changeset)
            findings.extend(semantic_report.findings)
            observations.extend(semantic_report.observations)
            env_issues.extend(semantic_report.environment_issues)

        #al
        #
        #in
        #
        #
        if acceptance is not None and not findings:
            report = acceptance.run()
            findings.extend(report.findings)
            env_issues.extend(report.environment_issues)

        #on
        #
        #
        #
        # and
        #
        #
        jev_report: JevReport | None = None
        if jev is not None and not findings and not inconclusive:
            jev_report = jev.run(changeset, contract_text)
            findings.extend(jev_report.findings)
            observations.extend(jev_report.observations)
            env_issues.extend(jev_report.environment_issues)

        return GateResult(
            findings=tuple(findings),
            environment_issues=tuple(env_issues),
            observations=tuple(observations),
            inconclusive=tuple(inconclusive),
            semantic=semantic_report,
            jev=jev_report,
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
                findings.extend(syntax)  #
                continue
            syntax_clean.append(change)
            findings.extend(
                adapter.structural_checks(change, repo, contract_text=contract_text)
            )

        if not syntax_clean:
            return findings

        #
        #
        #
        #
        #
        #
        lint = partial(adapter.lint, base=changeset.base)
        for label, check in (("lint", lint), ("format", adapter.format_check)):
            try:
                findings.extend(check(syntax_clean, repo))
            except ToolFailedError as exc:
                #
                #
                #
                #
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
