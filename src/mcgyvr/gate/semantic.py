"""Environment-resolved semantic checks: the gate's sandboxed rung (#123).

`tests_pass` is a verdict on a suite, not on a diff. A call to a method that
does not exist, sitting on a branch no test exercises, leaves the suite green —
and where a repository declares no runnable check at all, a contract of a type
needing commands is rejected at load, so `function_implementation`,
`test_scaffold` and `bug_fix` are not weakly checked but unreachable. This rung
is what closes the first gap and what makes those task types possible in the
second case. ADR-0010 adopts it on that coverage argument.

It asks one question per call the worker added: **does this name resolve in the
environment this code will actually run in?** Answering it means importing the
target's own packages and introspecting them, which is why the rung lives
inside the per-task sandbox and cannot live anywhere else. In the orchestrator
process "installed" means pyyaml and three tree-sitter packages; ADR-0005
forbids importing target code there and ADR-0010 carried that rule forward
unchanged. Under the temp-directory sandbox the resolution still happens in a
subprocess rather than in-process — exactly the strength acceptance commands
have in that mode, and no more.

**The resolver is ghostcall's engine (CLM-0006), staged rather than installed.**
The four engine files are stdlib-only and are vendored under
``records/evidence/`` pinned to an upstream commit with a sha256 per file; this
rung stages them into the workspace for the length of one run and removes them
after. That is the standing version policy #123 asked for, and ADR-0011 records
why it is staging rather than an image layer: the resolver never enters the
image, so :func:`~mcgyvr.sandbox.image.cache_key` keeps covering exactly what
the repository declared and nothing else. The digests are checked before every
run and a mismatch is fail-closed — an environment issue, never a verdict.

**It reports; it does not reject — yet.** ``blocking`` defaults to ``False``,
so findings arrive as ``observations`` that do not fail a change. #129 measured
zero false positives on 358 resolved chains on added lines, which the rule of
three bounds under ~0.8% at 95% — that is a thin sample, not a demonstrated
zero, and the four distinct flags it did produce off the added lines were all
correct platform-conditional code. :mod:`mcgyvr.gate.semantic_driver` suppresses
that class, and covers all four observed sites, but a mitigation validated
against four sites is not licence to block. Flipping ``blocking`` is one field
and wants a wider sample first.

Two properties every other per-change check also holds are kept here:

- **Only added lines.** Findings are filtered to
  :attr:`~mcgyvr.gate.changeset.FileChange.added_lines` in the driver *and*
  again here, so pre-existing state in a touched file can never fail a worker.
- **A tool that cannot run is an environment issue, not a rejection.** An
  import root that will not import, an interpreter that is not there, a driver
  that dies: all are reported as degraded coverage. The failure mode that makes
  this rung *vacuous* — every import failing, so nothing is ever flagged — is
  the one it says loudest.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from mcgyvr.gate.changeset import ChangeSet, FileChange
from mcgyvr.gate.findings import Finding
from mcgyvr.sandbox.base import Sandbox

# The check name every semantic finding carries.
CHECK = "semantic"

# Where the engine and the driver are staged, relative to the workspace root.
# Dot-prefixed and removed in a ``finally``: the gate must judge the worker's
# diff, and a staged file left behind would be part of what delivery commits.
STAGING_DIR = ".mcgyvr-semantic"

# The resolver, pinned. Changing either the commit or a digest is a deliberate
# edit to this file and re-opens the false-positive question #129 measured —
# that is the whole of the version policy, and it is enforced rather than
# asserted: :meth:`SemanticCheck.run` verifies these before it stages anything.
ENGINE_COMMIT = "56b74fc266cde790ef3d4fc474c1388ee2960d5f"
ENGINE_ORIGIN = "https://github.com/linosorice/ghostcall"
ENGINE_DIGESTS: Mapping[str, str] = {
    "__init__.py": "ae739b3e3b817044ada923b44ba82c752fe8b7c2133908d58fff8fd4b5146298",
    "parser.py": "1064c2f95141120125bcd7e3679d1d7817b6468abdca169dfb7138457dbf24ba",
    "checker.py": "f89e2a6024155f4676cf348a6caa09009b699a6253ab668abc48882d33e51e47",
    "suggest.py": "ddd5a2d321e8a063c7158bf6ec0d34067738f0184445d1608738f69299be1fc7",
}

# The vendored copy, as it sits in a checkout. In a wheel the same files are
# force-included under the package (see ``pyproject.toml``), because a record
# outside ``src/`` does not ship — the gotcha the task catalog already hit.
_CHECKOUT_ENGINE = (
    Path(__file__).resolve().parents[3]
    / "records"
    / "evidence"
    / "ghostcall-2026-08-02"
    / "src"
    / "ghostcall"
)

_DRIVER_NAME = "semantic_driver.py"

# Wall-clock ceiling for the whole resolution pass. It is a sub-second pass in
# principle, but it imports the target's packages, and a module-level import
# can do anything at all — so it is bounded, and the bound is an environment
# outcome rather than a verdict.
DEFAULT_TIMEOUT = 120.0


class SemanticError(Exception):
    """The rung could not stage or read what it needs to run."""


@dataclass(frozen=True)
class SemanticReport:
    """What the rung saw, in the gate's own currency.

    ``findings`` reject the change and are populated only when ``blocking`` is
    set; otherwise the same items arrive as ``observations``, which are
    reported and never rejecting. ``environment_issues`` mirror
    :class:`~mcgyvr.gate.acceptance.AcceptanceReport`'s, so the gate folds one
    into the other. ``resolved`` and ``suppressed`` are the coverage the run
    actually achieved — a rung that silently stopped looking would otherwise
    report a clean pass it had not earned.
    """

    findings: tuple[Finding, ...] = ()
    observations: tuple[Finding, ...] = ()
    environment_issues: tuple[str, ...] = ()
    resolved: int = 0
    suppressed: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class SemanticCheck:
    """The environment-resolved rung, bound to an open sandbox.

    ``interpreter`` is the argv prefix that reaches an interpreter which can
    see *the repository's own installed dependencies* — the caller knows how
    the image was provisioned, so it supplies this rather than the gate
    re-deriving a stack it does not own (the reason ``detect_stack`` is not
    called here). A wrong interpreter is not a wrong verdict: its imports fail,
    and failed imports are environment issues.
    """

    sandbox: Sandbox
    interpreter: tuple[str, ...] = ("python3",)
    timeout: float | None = DEFAULT_TIMEOUT
    blocking: bool = False

    def run(self, changeset: ChangeSet) -> SemanticReport:
        """Resolve the calls the worker added, inside the sandbox."""
        targets = _targets(changeset)
        if not targets:
            # No Python was added — which is also how JS/TS gets its no-op
            # until an equivalent resolver exists there (#133).
            return SemanticReport()

        try:
            engine = engine_dir()
            digest_issue = verify_engine(engine)
        except SemanticError as exc:
            return SemanticReport(environment_issues=(f"{CHECK}: {exc}",))
        if digest_issue is not None:
            return SemanticReport(environment_issues=(digest_issue,))

        staging = self.sandbox.workspace / STAGING_DIR
        try:
            _stage(engine, staging, targets)
            result = self.sandbox.run(
                [
                    *self.interpreter,
                    f"{STAGING_DIR}/{_DRIVER_NAME}",
                    f"{STAGING_DIR}/job.json",
                    f"{STAGING_DIR}/out.json",
                ],
                timeout=self.timeout,
                # Relative to the workspace, which is the working directory in
                # both sandbox modes. The workspace itself is on the path so a
                # repository package that is not installed still imports.
                env={"PYTHONPATH": f"{STAGING_DIR}/engine:."},
            )
            report_path = staging / "out.json"
            if not report_path.is_file():
                return SemanticReport(
                    environment_issues=(_driver_failed(result.exit_code, result),)
                )
            raw = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return SemanticReport(environment_issues=(f"{CHECK}: {exc}",))
        finally:
            shutil.rmtree(staging, ignore_errors=True)

        return self._interpret(raw, targets)

    # -- report → gate currency -------------------------------------------

    def _interpret(
        self, raw: Mapping[str, Any], targets: Mapping[str, list[int]]
    ) -> SemanticReport:
        """Turn the driver's report into findings, issues and coverage."""
        items: list[Finding] = []
        issues: list[str] = []
        missing_roots: set[str] = set()
        suppressed: dict[str, int] = {}
        resolved = 0

        for entry in raw.get("files", ()):
            path = entry.get("path", "")
            if "error" in entry:
                issues.append(f"{CHECK}: {path} was not resolved — {entry['error']}")
                continue
            allowed = set(targets.get(path, ()))
            resolved += int(entry.get("resolved", 0))
            missing_roots.update(entry.get("missing_roots", ()))
            for reason, count in (entry.get("suppressed") or {}).items():
                suppressed[reason] = suppressed.get(reason, 0) + int(count)
            for flag in entry.get("flags", ()):
                # The driver already restricts itself to the added lines; this
                # is the same restriction enforced where the gate can see it,
                # so the acceptance criterion is pinned on this side of the
                # sandbox rather than trusted to what came back through it.
                if flag.get("line") in allowed:
                    items.append(_as_finding(path, flag))

        if missing_roots:
            issues.append(_unimportable(sorted(missing_roots), resolved))

        return SemanticReport(
            findings=tuple(items) if self.blocking else (),
            observations=() if self.blocking else tuple(items),
            environment_issues=tuple(issues),
            resolved=resolved,
            suppressed=tuple(sorted(suppressed.items())),
        )


# --- staging --------------------------------------------------------------


def engine_dir() -> Path:
    """Locate the vendored resolver, whether running from a wheel or a checkout."""
    packaged = resources.files("mcgyvr.gate") / "_engine" / "ghostcall"
    if (packaged / "checker.py").is_file():
        return Path(str(packaged))
    if (_CHECKOUT_ENGINE / "checker.py").is_file():
        return _CHECKOUT_ENGINE
    raise SemanticError(
        "the vendored resolver engine was not found, so no semantic check ran "
        f"(looked for {ENGINE_ORIGIN} at {ENGINE_COMMIT})"
    )


def verify_engine(engine: Path) -> str | None:
    """Check the engine against its pinned digests. A message means refuse.

    Fail-closed, and closed means *not running* rather than *rejecting*: an
    engine that is not the reviewed one is an environment fault, and charging
    a worker for it would be the worst kind of false positive.
    """
    for name, expected in ENGINE_DIGESTS.items():
        try:
            actual = hashlib.sha256((engine / name).read_bytes()).hexdigest()
        except OSError as exc:
            return (
                f"{CHECK}: resolver engine file {name} is unreadable ({exc}); "
                "no semantic check ran"
            )
        if actual != expected:
            return (
                f"{CHECK}: resolver engine {name} does not match the digest pinned "
                f"in gate/semantic.py ({actual[:12]}… vs {expected[:12]}…); the "
                "check was not run. Re-pin deliberately — the false-positive "
                "measurement was taken against the pinned bytes."
            )
    return None


def _stage(engine: Path, staging: Path, targets: Mapping[str, list[int]]) -> None:
    """Write the engine, the driver and the job into the workspace."""
    shutil.rmtree(staging, ignore_errors=True)
    destination = staging / "engine" / "ghostcall"
    destination.mkdir(parents=True)
    for name in ENGINE_DIGESTS:
        shutil.copyfile(engine / name, destination / name)
    (staging / _DRIVER_NAME).write_text(driver_source(), encoding="utf-8")
    (staging / "job.json").write_text(
        json.dumps({"targets": targets}), encoding="utf-8"
    )


def driver_source() -> str:
    """The driver's own source, read as text — it is never imported here."""
    packaged = resources.files("mcgyvr.gate") / _DRIVER_NAME
    if packaged.is_file():
        return packaged.read_text(encoding="utf-8")
    raise SemanticError(f"{_DRIVER_NAME} is missing from the installed package")


def _targets(changeset: ChangeSet) -> dict[str, list[int]]:
    """The Python files the worker added lines to, and which lines those are."""
    return {
        change.path: sorted(change.added_lines)
        for change in changeset.text_changes()
        if change.added_lines and _is_python(change)
    }


def _is_python(change: FileChange) -> bool:
    return change.path.endswith(".py") or change.path.endswith(".pyi")


# --- messages -------------------------------------------------------------


def _as_finding(path: str, flag: Mapping[str, Any]) -> Finding:
    """One unresolved call, named as precisely as the resolver can name it."""
    chain = flag.get("chain") or "?"
    parent = flag.get("parent") or "the imported module"
    missing = flag.get("missing_attr") or "?"
    suggestions = flag.get("suggestions") or []
    hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
    return Finding(
        check=CHECK,
        path=path,
        line=flag.get("line"),
        code="unresolved",
        message=(
            f"`{chain}` does not resolve against the packages this repository "
            f"installs: {parent} has no attribute `{missing}`.{hint}"
        ),
    )


def _unimportable(roots: Sequence[str], resolved: int) -> str:
    """The environment issue for import roots the sandbox could not import."""
    listed = ", ".join(roots)
    vacuous = (
        " Nothing at all resolved, so this run cleared no call: the check was "
        "blind here, not satisfied."
        if resolved == 0
        else ""
    )
    return (
        f"{CHECK}: {len(roots)} import root(s) could not be imported in the "
        f"sandbox ({listed}) — every call rooted there went unresolved. This is "
        f"an environment fault (a dependency the image did not install, or an "
        f"interpreter that cannot see it), not a rejected change.{vacuous}"
    )


def _driver_failed(exit_code: int, result: Any) -> str:
    """The environment issue for a driver that produced no report."""
    detail = (result.stderr or result.stdout or "").strip()[-600:]
    if result.timed_out:
        return (
            f"{CHECK}: the resolution pass exceeded its time limit and was "
            "killed; no semantic check ran. Importing the target's own "
            "packages is what it spends time on."
        )
    return (
        f"{CHECK}: the resolution pass produced no report (exit {exit_code}); "
        f"no semantic check ran. {detail}"
    )
