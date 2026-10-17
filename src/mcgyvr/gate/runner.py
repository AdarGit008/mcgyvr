"""The gate: one change set through every check, and the verdict it earns.

:class:`Gate` runs the checks in a fixed order — the scope scan, the secret
scan and the structured-data parse, then each language adapter's syntax,
structural, lint and format rungs over the files it owns, then the output,
typecheck, semantic, acceptance and Jev rungs the caller wires — and skips each
of the last five once an earlier one has recorded a finding.
:class:`GateResult` carries what came back: the findings that reject the change,
the inconclusive rungs that keep it from being called a pass, and the
environment issues and observations that are reported beside the verdict.
"""

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
    """A rung that could not decide, and why.

    ``adapter`` names the owner (or ``output``), ``rung`` the check within it,
    ``tool`` the executable that failed, and ``exit_code`` is ``None`` where the
    tool was absent. Rendered as text, the value reads as a statement about the
    rung — never about the change — and is what an environment issue quotes.
    """

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
    """What one gate run returns.

    ``findings`` reject the change. ``inconclusive`` holds the rungs that ran
    but produced output the gate cannot read, and a rung in that state also
    rejects, so ``accepted`` requires both to be empty. ``environment_issues``
    and ``observations`` sit beside the verdict: a missing tool or a skipped
    rung, and the findings filed on the observational axis. ``semantic`` and
    ``jev`` keep those rungs' own reports.
    """

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
    """Runs the checks over one change set and returns the verdict.

    The adapters default to the Python and JavaScript ones; a caller may pass
    its own, which is how a driving attempt hands over adapters whose tools run
    inside a sandbox instead of on the host.
    """

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
        """Run every check this call wires, in order, and return the verdict.

        Scope violations and secrets come first and end the run on the spot; the
        structured-data parse follows. Each adapter then walks its own files, and
        the rungs passed as arguments follow in the order output, typecheck,
        semantic, acceptance, Jev — each skipped once ``findings`` is non-empty,
        with Jev also skipped when any rung came back inconclusive. A rung left
        unwired is not run at all. Findings filed on the ``style`` axis are
        gathered as observations and never reject the change.
        """
        findings: list[Finding] = []
        observations: list[Finding] = []

        # A path the contract forbids and a secret in an added line are findings
        # that need no tool, so the run ends here before anything is spawned.
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

        # Structured text is parsed in-process, so a malformed manifest is a
        # finding like any other before an adapter claims the file.
        findings.extend(validate_structured_data(changeset))

        # Per-adapter rungs: a finding on the `style` axis is an observation,
        # everything else rejects. Environment issues and undecided rungs are
        # collected across adapters instead of ending the run.
        env_issues: list[str] = []
        inconclusive: list[InconclusiveRung] = []
        for adapter in self.adapters:
            for item in self._run_adapter(
                adapter, changeset, env_issues, inconclusive, contract_text
            ):
                (observations if item.check == STYLE else findings).append(item)

        # The output rung judges the produced artifact rather than the source, so
        # it needs no syntax-clean file to exist. A validator that could not run
        # comes back as an inconclusive rung, which rejects the change even where
        # it adds no finding, and its text is also kept as an environment issue.
        if output is not None and not findings:
            output_report = output.run()
            findings.extend(output_report.findings)
            env_issues.extend(output_report.environment_issues)
            inconclusive.extend(output_report.inconclusive)

        if typecheck is not None and not findings:
            try:
                # A checker diagnostic is a rejection unless it lands on the
                # `style` axis, where it joins the observations.
                for item in typecheck.run(changeset):
                    (observations if item.check == STYLE else findings).append(item)
            except TypeCheckTimeoutError as exc:
                # A checker that ran out of time says nothing about the change,
                # so it is recorded as an environment issue and the gate moves on
                # rather than charging the worker for the machine's clock.
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

        # The semantic rung resolves the change in a staged copy of the repo and
        # flags what it cannot resolve. Its own report decides the axis: when the
        # check is blocking its items arrive in `findings`, otherwise they arrive
        # as observations, and the report is kept either way so a reader can tell
        # a rung that ran and saw nothing from one that was never wired.
        semantic_report: SemanticReport | None = None
        if semantic is not None and not findings:
            semantic_report = semantic.run(changeset)
            findings.extend(semantic_report.findings)
            observations.extend(semantic_report.observations)
            env_issues.extend(semantic_report.environment_issues)

        # The acceptance rung runs the contract's own commands against the
        # worker's tree: a command that did not pass is a finding, one that could
        # not run is an environment issue and leaves the verdict alone. The
        # report's cleanup notes are not folded into the result, so only its
        # findings and issues are taken here.
        if acceptance is not None and not findings:
            report = acceptance.run()
            findings.extend(report.findings)
            env_issues.extend(report.environment_issues)

        # The Jev verifier rung is last: it reads the change and the contract
        # prose and puts a fixed set of questions to a model. It is skipped when a
        # finding already stands, and also when any rung above could not decide,
        # because the verdict is then already not a pass. Like semantic, its
        # report decides whether its items are rejections or observations.
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
                findings.extend(syntax)  # a file that does not parse goes no further
                continue
            syntax_clean.append(change)
            findings.extend(
                adapter.structural_checks(change, repo, contract_text=contract_text)
            )

        if not syntax_clean:
            return findings

        # Lint and format run once over the whole batch of syntax-clean files, so
        # the tool invocations stay flat as the change grows. `base` is bound to
        # the change's base commit, which is what lets lint charge only the lines
        # this change added. Both rungs are tried even when the first one fails.
        lint = partial(adapter.lint, base=changeset.base)
        for label, check in (("lint", lint), ("format", adapter.format_check)):
            try:
                findings.extend(check(syntax_clean, repo))
            except ToolFailedError as exc:
                # A tool whose output cannot be read leaves the rung undecided:
                # that is not a claim about the change, so it becomes an
                # inconclusive rung that rejects, and its rendered text is also
                # kept in the environment issues for readers of that field.
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
