"""Output-checks rung: judge the artifact itself, not the source that made it.

A contract that promises output evidence names the checks it wants, and this
module runs them over the produced file. ``safety_pass`` runs the safety
classifier over the artifact and reports an unsafe verdict.

Each check returns ``Finding`` values and reports a missing or failing tool
as an environment fault; ``OutputChecks`` turns such a fault into an
inconclusive rung, so a check that could not run never reads as a pass.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from mcgyvr.gate.adapter import ToolFailedError, ToolUnavailableError
from mcgyvr.gate.findings import Finding

if TYPE_CHECKING:
    from mcgyvr.gate.runner import InconclusiveRung

#: The name of the tool-backed output check, declared in a contract's evidence
#: names: `safety_pass` asks the safety classifier about the artifact.
SAFETY_PASS = "safety_pass"


# The tool-backed check, and the helper that reads what a tool wrote.


def _first_line(stderr: str | bytes) -> str:
    """Return the first non-blank line of a tool's stderr, capped at 200 chars.

    Bytes are decoded as UTF-8 with replacement so a tool writing raw bytes still
    yields readable text, and an empty or blank stderr yields the empty string.
    """
    text = stderr.decode("utf-8", "replace") if isinstance(stderr, bytes) else stderr
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:200]
    return ""


def safety_pass(path: Path, label: str = "") -> list[Finding]:
    """Run the safety classifier over `path` and report an unsafe verdict.

    An empty list means the classifier exited 0. Exit 1 is its unsafe verdict and
    becomes an `unsafe` finding. A missing binary raises `ToolUnavailableError`
    and any other exit code raises `ToolFailedError` carrying the first line of
    stderr, so a broken classifier is never read as clean.
    """
    if shutil.which("safety-classifier") is None:
        raise ToolUnavailableError("safety-classifier")
    proc = subprocess.run(["safety-classifier", str(path)], capture_output=True)
    if proc.returncode == 0:
        return []
    if proc.returncode == 1:
        return [
            Finding(
                check=SAFETY_PASS,
                path=label or str(path),
                code="unsafe",
                message="the output was classified unsafe by the safety classifier",
            )
        ]
    raise ToolFailedError(
        "safety-classifier", proc.returncode, detail=_first_line(proc.stderr)
    )


# The report one pass of the checks hands to the gate, and the rung running it.


@dataclass(frozen=True)
class OutputReport:
    """What one pass of the output checks produced.

    `findings` are the checks' verdicts, `environment_issues` the rendered text of
    each inconclusive rung, and `inconclusive` the rungs themselves, so the gate
    can tell a check that ran and passed from one that never ran.
    """

    findings: tuple[Finding, ...] = ()
    environment_issues: tuple[str, ...] = ()
    inconclusive: tuple[InconclusiveRung, ...] = ()


class OutputChecks:
    """The output checks a contract declares, run over one artifact.

    `checks` are the evidence names to run (`safety_pass`, in the order given)
    and `target` is the artifact's path relative to `workspace`.
    """

    def __init__(
        self,
        *,
        checks: Sequence[str],
        workspace: Path,
        target: str = "",
    ) -> None:
        self.checks = tuple(checks)
        self.workspace = workspace
        self.target = target

    def run(self) -> OutputReport:
        """Run every declared check and collect findings, issues and rungs.

        A validator that raises `ToolUnavailableError` or `ToolFailedError` does not
        fail the run: it becomes an inconclusive rung whose rendered text is also
        recorded as an environment issue. Any other exception propagates.
        """
        findings: list[Finding] = []
        issues: list[str] = []
        inconclusive: list[InconclusiveRung] = []
        path = self.workspace / self.target
        for name in self.checks:
            try:
                findings.extend(_run_one(name, self, path))
            except (ToolUnavailableError, ToolFailedError) as exc:
                # A missing or failing tool is not a pass, so the rung is kept as
                # inconclusive; the import is local because runner imports this module.
                from mcgyvr.gate.runner import InconclusiveRung

                if isinstance(exc, ToolUnavailableError):
                    rung = InconclusiveRung(adapter="output", rung=name, tool=exc.tool)
                else:
                    rung = InconclusiveRung(
                        adapter="output",
                        rung=name,
                        tool=exc.tool,
                        exit_code=exc.exit_code,
                        detail=exc.detail,
                    )
                inconclusive.append(rung)
                issues.append(str(rung))
        return OutputReport(
            findings=tuple(findings),
            environment_issues=tuple(issues),
            inconclusive=tuple(inconclusive),
        )


def _run_one(name: str, checks: OutputChecks, path: Path) -> list[Finding]:
    """Run one named check with the settings `checks` carries.

    An unknown name is a fault in the contract wiring and raises `ValueError`
    rather than passing silently.
    """
    if name == SAFETY_PASS:
        return safety_pass(path, checks.target)
    raise ValueError(f"unknown output check {name!r}")
