"""The semantic rung: do the attribute chains this change adds actually resolve?

Every call in the lines a changeset added is parsed into its dotted chain, and
each chain is checked against the packages the sandbox's interpreter installs:
``pkg.mod.func(...)`` where ``pkg.mod`` imports but has no ``func`` raises
``AttributeError`` the moment that line runs. The resolution is done by a vendored
third-party engine — ghostcall, pinned below by origin, commit and per-file
digest — staged into the sandbox and driven by
:mod:`mcgyvr.gate.semantic_driver`, because the packages the chains must resolve
against are the ones the repository installs into that interpreter, not the
host's.

The rung is non-blocking unless asked otherwise: the engine's false-positive
rate was measured against the pinned bytes, so its items arrive as
``observations`` unless ``SemanticCheck(blocking=True)`` is passed. Anything
that stops the check from running or blinds it — an engine that is missing or
no longer the pinned bytes, a driver that wrote no report, a file the driver
could not read, an import root that would not import in the sandbox — is
reported as an environment issue in prose, never as a finding against the
change.
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

# The check name attached to every finding this rung produces.
CHECK = "semantic"

# Where the staged engine, driver, job and report live inside the sandbox
# workspace. One fixed name, removed after every run, so a pass leaves nothing
# behind and a rerun in the same workspace starts from a clean directory.
STAGING_DIR = ".mcgyvr-semantic"

# The vendored resolver engine, pinned by upstream origin and commit, and each
# file it ships by sha256. The digests are checked before every run, because the
# rung's false-positive measurement was taken against these bytes: a modified or
# substituted engine is a check nobody has measured, and the honest answer there
# is an environment issue rather than a verdict.
ENGINE_COMMIT = "56b74fc266cde790ef3d4fc474c1388ee2960d5f"
ENGINE_ORIGIN = "https://github.com/linosorice/ghostcall"
ENGINE_DIGESTS: Mapping[str, str] = {
    "__init__.py": "ae739b3e3b817044ada923b44ba82c752fe8b7c2133908d58fff8fd4b5146298",
    "parser.py": "1064c2f95141120125bcd7e3679d1d7817b6468abdca169dfb7138457dbf24ba",
    "checker.py": "f89e2a6024155f4676cf348a6caa09009b699a6253ab668abc48882d33e51e47",
    "suggest.py": "ddd5a2d321e8a063c7158bf6ec0d34067738f0184445d1608738f69299be1fc7",
}

_DRIVER_NAME = "semantic_driver.py"

# How long one resolution pass may take, in seconds. Importing the target's own
# packages is what it spends the time on, so this covers imports as much as the
# checking; a pass that overruns is killed and reported as an environment fault
# rather than as anything about the change.
DEFAULT_TIMEOUT = 120.0


class SemanticError(Exception):
    """The engine or the driver could not be found or used, so no semantic
    check ran."""


@dataclass(frozen=True)
class SemanticReport:
    """What one pass found, and how much of the change it could see.

    ``findings`` and ``observations`` hold the same unresolved chains, filed on
    whichever side the rung's ``blocking`` flag sends them, so at most one of the
    two is non-empty. ``environment_issues`` are prose reasons the pass was
    degraded or did not run — none of them is the change's fault.
    ``resolved`` counts the calls the engine could judge, and a call whose import
    root would not import is not counted, which is why a zero here over a
    non-empty target means the check was blind. ``suppressed`` is the number of
    calls skipped per reason, sorted by reason.
    """

    findings: tuple[Finding, ...] = ()
    observations: tuple[Finding, ...] = ()
    environment_issues: tuple[str, ...] = ()
    resolved: int = 0
    suppressed: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class SemanticCheck:
    """The rung: stage the engine into the sandbox, run the driver, read the report.

    ``sandbox`` supplies the workspace and the isolation the driver runs in, and
    ``interpreter`` is the command it is launched with — the sandbox's
    ``python3`` unless a caller says otherwise, so the packages installed there
    are the ones the chains resolve against.
    ``timeout`` bounds one pass (``None`` leaves it to the sandbox's default), and
    ``blocking`` decides whether an unresolved chain rejects the work or is only
    reported as an observation.
    """

    sandbox: Sandbox
    interpreter: tuple[str, ...] = ("python3",)
    timeout: float | None = DEFAULT_TIMEOUT
    blocking: bool = False

    def run(self, changeset: ChangeSet) -> SemanticReport:
        """Resolve the call chains this changeset added, inside the sandbox.

        The added lines are collected per Python file, the pinned engine and the
        driver are staged into the sandbox, and the driver is run under
        ``interpreter`` with a job file as input and a report file as output.
        Where the pass cannot start or cannot finish, the returned report carries
        the reason as an environment issue and no findings, so a broken rung
        never rejects the change. The staging directory is removed when the run
        ends, on every path through it.
        """
        targets = _targets(changeset)
        if not targets:
            # No Python file in this change added a line, so there is no chain to
            # resolve and nothing was skipped: an empty report records that the
            # rung ran and saw nothing, which is a different statement from a
            # rung that never ran at all.
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
                # The pass's one variable: the staged engine package first, so
                # the driver imports the pinned copy rather than anything
                # installed, then the workspace root so the paths in the job open
                # and import as the repository runs them.
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

    # What the driver wrote, turned into what the gate reads.

    def _interpret(
        self, raw: Mapping[str, Any], targets: Mapping[str, list[int]]
    ) -> SemanticReport:
        """Fold the driver's JSON report into findings, observations and issues.

        Each file entry either carries an ``error`` — the driver could not read or
        parse that file, which costs only that file and is reported by name — or a
        list of flags with counts beside it. A flag becomes a finding only on a
        line the diff added, since the driver resolves whole files and an
        untouched line predates this change. Suppressions are summed per reason
        across files, and import roots that would not import are reported once
        for the run, because that is one environment fault however many calls it
        silenced.
        """
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
                # The driver flags every unresolved chain in the file it was
                # given; only the lines this change added are its responsibility,
                # so a flag anywhere else describes code the base commit already
                # had and is dropped here rather than charged to the worker.
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


# The engine itself: where the pinned resolver lives, whether it is still the
# bytes the pin was measured against, and how one run's copy is staged.


def engine_dir() -> Path:
    """The engine as it ships inside the package: ``gate/_engine/ghostcall``.

    Raises :class:`SemanticError` when that directory has no ``checker.py``:
    without it the rung has nothing to run, and :meth:`SemanticCheck.run` reports
    that as an environment issue instead of returning findings it never looked
    for.
    """
    packaged = resources.files("mcgyvr.gate") / "_engine" / "ghostcall"
    if (packaged / "checker.py").is_file():
        return Path(str(packaged))
    raise SemanticError(
        "the vendored resolver engine was not found, so no semantic check ran "
        f"(looked for {ENGINE_ORIGIN} at {ENGINE_COMMIT})"
    )


def verify_engine(engine: Path) -> str | None:
    """Compare each pinned engine file against its recorded sha256.

    ``None`` when every file matches; otherwise a message naming the first file
    that is unreadable or altered. A mismatch is not worked around or retried
    with the bytes that were found: the pinned bytes are what the rung's measured
    false-positive rate describes, so the message asks for a deliberate re-pin.
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
    """Write one run's inputs under ``staging``, inside the sandbox workspace.

    The pinned engine files are copied into ``engine/ghostcall`` — the package
    name the driver imports — while the driver script and ``job.json`` sit at the
    top of ``staging``, which is the shape the launch command and the
    ``PYTHONPATH`` above are written against. Every file is copied rather than
    read from the host, so the sandbox never reaches into the installed package.
    """
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
    """The driver script's text, read from the installed package.

    Raises :class:`SemanticError` when the package does not ship it, which
    :meth:`SemanticCheck.run` turns into an environment issue like the engine's
    own absence.
    """
    packaged = resources.files("mcgyvr.gate") / _DRIVER_NAME
    if packaged.is_file():
        return packaged.read_text(encoding="utf-8")
    raise SemanticError(f"{_DRIVER_NAME} is missing from the installed package")


def _targets(changeset: ChangeSet) -> dict[str, list[int]]:
    """The added line numbers per path, for the Python files this change touched.

    Keyed by repository-relative path, which is also how the driver opens them
    relative to the workspace root. Binary, deleted and symlink entries are
    already excluded by the changeset; what is left out here is any file with no
    added line, and anything that is not ``.py`` or ``.pyi``.
    """
    return {
        change.path: sorted(change.added_lines)
        for change in changeset.text_changes()
        if change.added_lines and _is_python(change)
    }


def _is_python(change: FileChange) -> bool:
    return change.path.endswith(".py") or change.path.endswith(".pyi")


# The driver's flags and counts, turned into the findings and the prose the gate
# reads.


def _as_finding(path: str, flag: Mapping[str, Any]) -> Finding:
    """One unresolved chain, as a finding on the line that wrote it.

    Missing fields fall back to placeholders instead of failing the run: the
    message is what a worker reads, and it should still name the chain when the
    engine left a detail out. The code is always ``unresolved``, which is the one
    thing this rung reports; the suggestions are repeated as the engine gave them.
    """
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
    """The single environment-issue line for import roots that would not import.

    The consequence is spelled out because the quieter reading — no findings —
    looks like a pass: every call rooted at one of these went unresolved without
    being reported, and when ``resolved`` is zero the run cleared nothing at all.
    """
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
    """The environment issue for a driver that exited without writing a report.

    A timeout gets its own message because a killed pass has no traceback to
    show, and the other case appends the last 600 characters of what the driver
    wrote, so whatever it said — typically a traceback — reaches the reader.
    """
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
