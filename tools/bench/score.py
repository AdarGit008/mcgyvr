"""The bench scores the way production does, or it is not measuring the product.

Issue: `#113 <https://github.com/AdarGit008/mcgyvr/issues/113>`_, the scope
bullet that begins *"the outcome of a run is the gate's own verdict, never a
bespoke scorer."*

**What was wrong.** Every measurement this project has taken was scored by
running the contract's acceptance command in a temp directory
(``tools/bundle/measure.py:397``). :class:`~mcgyvr.gate.runner.Gate` — the thing
production actually ships — runs that command *last*, behind scope, secrets,
structured-data and per-adapter language rungs. So a worker output that
satisfies ``accept.py`` while writing outside ``scope.allow`` scored as a
**pass** on the rig and a **fail** in the product. The bench was measuring
something the product does not do.

**What this changes, and what it deliberately does not.** The tree the
acceptance command runs in is built exactly as ``run_acceptance`` built it — the
target file carrying the condition's own ``target_content``, the accept file
beside it, nothing else. That is on purpose: holding the tree fixed means any
movement in a pass rate is attributable to the added rungs rather than to a
different working directory. What changes is only that four cheaper rungs now
get to reject first, and that the row records *which* one did.

**The semantic rung is off, and the run manifest says so.** ADR-0011 stages the
resolver rather than installing it, and #113 asks that comparability be stated
rather than assumed. ``semantic=None`` is a declared property of a bench run,
not an oversight — see ``gate_rungs`` in ``run.json``.

**One sandbox per task, reset per draw.** The workspace, its git base commit and
the reset are the sandbox's (E4, #26-#31), so the cost is paid 257 times per arm
rather than once per draw. :meth:`~mcgyvr.sandbox.base.Sandbox.reset` is what
makes a failed attempt leave no trace in the next.
"""

from __future__ import annotations

import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcgyvr.gate.acceptance import Acceptance
from mcgyvr.gate.changeset import ChangeSet
from mcgyvr.gate.runner import Gate
from mcgyvr.sandbox.tempdir import TempDirSandbox

REPO = Path(__file__).resolve().parents[2]

# The rungs a bench run exercises, recorded in run.json so a rate is never
# quoted against an unstated bar. "semantic" is absent by decision, not by
# accident (ADR-0011).
GATE_RUNGS = ("scope", "secrets", "structured", "adapters", "acceptance")

# Matches tools/bundle/measure.py's ACCEPTANCE_TIMEOUT_S, so "timed out" means
# the same thing in both instruments and a slow suite is not a new rejection.
ACCEPTANCE_TIMEOUT_S = 120.0

# The gate rejects an acceptance command that alters the working tree — it must
# judge the change, not add to it. `python accept.py` writes `__pycache__/`, so
# without this every Python candidate would be rejected by its own checker
# rather than by anything the worker did.
#
# This is the mechanism the gate designed for the case, not a way around it:
# `_worktree_tree` hashes through a throwaway index with `add -A`, whose
# docstring says ignored paths "are excluded, so a run that only writes those is
# correctly not counted as altering the tree." What the staged tree was missing
# is the .gitignore any real repository would carry. It lands in the base
# commit, so it is never part of the worker's diff and the scope rung never
# sees it.
# `node_modules` carries no trailing slash on purpose. The toolchain is linked
# in as a *symlink*, which git treats as a file, and a `node_modules/` pattern
# matches only directories — so the slash version leaves the link visible to the
# changeset, where it reads as the worker writing outside `scope.allow`.
IGNORED = "__pycache__/\n*.pyc\nnode_modules\n"


ESLINT_CONFIG = REPO / "eslint.config.mjs"
NODE_MODULES = REPO / "node_modules"


def stage_js_toolchain(into: Path) -> None:
    """Give the workspace the project's JS lint standard and a resolvable parser.

    Two things, and both are needed or the rung is inert rather than absent —
    which is worse, because an inert rung passes everything while looking
    healthy.

    * ``eslint.config.mjs``. eslint 9 requires a flat config and finds none in a
      one-file workspace; without it the run aborts, writes no JSON, and the
      adapter scores that as "inconclusive", which is a pass.
    * ``node_modules``. The config imports ``typescript-eslint`` as an ES
      module, and Node resolves that by walking up from the config's own
      directory — a temp workspace has nothing to find. The symlink points at
      the repository's installed tree, so the parser version is the one
      ``package-lock.json`` pins rather than whatever happens to be global.

    ``node_modules`` is in the workspace ``.gitignore``, so it never enters the
    changeset and ``_worktree_tree`` does not see it as a mutation.
    """
    if ESLINT_CONFIG.is_file():
        (into / ESLINT_CONFIG.name).write_text(
            ESLINT_CONFIG.read_text(encoding="utf-8"), encoding="utf-8"
        )
    link_node_modules(into)


def link_node_modules(into: Path) -> None:
    """(Re)point the workspace at the repository's installed JS toolchain.

    Called after every :meth:`~mcgyvr.sandbox.base.Sandbox.reset` as well as at
    staging: ``reset`` runs ``git clean -fdx``, and the ``-x`` removes ignored
    paths — which is exactly what ``node_modules`` is. Without this the lint
    rung would work on a task's first draw and silently stop on its second.
    """
    if not NODE_MODULES.is_dir():
        return
    link = into / "node_modules"
    if link.is_symlink() or link.exists():
        return
    link.symlink_to(NODE_MODULES, target_is_directory=True)


def lint_config() -> str:
    """The project's own ruff settings, as a workspace ``pyproject.toml``.

    **Why this file has to exist.** The adapter runs ``ruff check`` with the
    workspace as its working directory. A workspace holding only a solution and
    a checker has no ``pyproject.toml``, so ruff finds no configuration and
    falls back to a rule set far wider than this project selects — measured on
    the corpus, that is `TRY004` alone rejecting 75 of 257 checked-in reference
    solutions for raising ``ValueError`` where the contract asked only for "an
    error". The bench would have been applying a **stricter** bar than the
    product, which is the exact inverse of what #113 asks for.

    In production the gate lints a real repository against *that repository's*
    configuration. A synthetic one-file workspace has none, so the bench has to
    supply one, and the defensible choice is the project's own — it is what a
    mcgyvr-managed repository carries.

    Derived from ``pyproject.toml`` at call time rather than copied, so the two
    cannot drift; ``extend-exclude`` is dropped because its paths name the
    repository, and one of them is ``tools/bench/tasks`` — carrying it through
    would exclude the very file being linted.
    """
    with (REPO / "pyproject.toml").open("rb") as fh:
        ruff = tomllib.load(fh)["tool"]["ruff"]
    select = ", ".join(f'"{r}"' for r in ruff["lint"]["select"])
    fmt = ruff.get("format", {})
    return (
        "[tool.ruff]\n"
        f"line-length = {ruff['line-length']}\n"
        f'target-version = "{ruff["target-version"]}"\n\n'
        "[tool.ruff.lint]\n"
        f"select = [{select}]\n\n"
        "[tool.ruff.format]\n"
        f'quote-style = "{fmt.get("quote-style", "double")}"\n'
        f'indent-style = "{fmt.get("indent-style", "space")}"\n'
    )


@dataclass(frozen=True)
class Verdict:
    """One candidate's gate result, flattened for a row.

    ``rejected_by`` is the whole point of scoring this way: it names the first
    rung that rejected, so a rate can be read by cause rather than as one
    number.
    """

    passed: bool
    rejected_by: str | None
    findings: tuple[str, ...]
    environment_issues: tuple[str, ...]

    @property
    def rejected_before_acceptance(self) -> bool:
        """Whether the gate stopped before the acceptance command ran.

        A statement of fact, not an inference. ``Gate.run`` short-circuits —
        acceptance runs only ``if not findings`` — so for a candidate rejected
        at lint the acceptance command **never executed** and nothing on the row
        can say whether it would have passed.

        This field therefore does *not* recover the acceptance-only rate every
        figure in this repository was measured at. That rate is not derivable
        from a gate run at all, which is precisely why #231's checks have to be
        re-run under this scorer rather than recomputed from the rows they
        already produced.
        """
        return self.rejected_by is not None and self.rejected_by != "acceptance"


def stage_dir(task: Any, target_content: str, into: Path) -> Path:
    """Build the pre-worker tree the sandbox will take as its base.

    Exactly ``run_acceptance``'s tree: the target file holding the content the
    worker was *shown*, and the accept file. The reference solution is
    deliberately not copied — it is the answer, and it has no business sitting
    in a workspace a checker runs in.

    ``target_content`` is the condition's, not the contract's. Under
    ``noscaffold`` the worker is told the file is empty, so the base it is
    diffed against must be empty too, or the changeset would attribute the
    scaffold's removal to the worker.
    """
    into.mkdir(parents=True, exist_ok=True)
    (into / task.language.solution).write_text(target_content, encoding="utf-8")
    (into / task.accept.name).write_text(
        task.accept.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (into / ".gitignore").write_text(IGNORED, encoding="utf-8")
    (into / "pyproject.toml").write_text(lint_config(), encoding="utf-8")
    stage_js_toolchain(into)
    return into


def commands_of(contract: Any) -> tuple[tuple[str, ...], ...]:
    """The contract's acceptance argv lists, in the order the gate runs them."""
    return tuple(tuple(c.split()) for c in contract.acceptance)


def demonstrations_of(contract: Any) -> tuple[tuple[str, ...], ...]:
    """The contract's demonstration argv lists.

    A bug-fix task carries its one command here because it must *fail* on the
    task's base by design (#183).
    """
    return tuple(tuple(c.split()) for c in contract.demonstration)


def score(
    task: Any,
    content: str,
    sandbox: Any,
    *,
    gate: Gate | None = None,
) -> Verdict:
    """Run the shipped gate over one candidate in an open sandbox.

    The sandbox is reset first, so nothing from a previous draw survives into
    this one. The candidate is written to the contract's target and the change
    is detected against the sandbox's own base commit — a real diff, which is
    what makes the scope rung meaningful at all.
    """
    sandbox.reset()
    workspace = Path(sandbox.workspace)
    # `reset` runs `git clean -fdx`, which removes ignored paths — node_modules
    # among them. Restore it before anything is scored, or the lint rung works
    # on a task's first draw and quietly stops on its second.
    link_node_modules(workspace)
    (workspace / task.contract.target).write_text(content, encoding="utf-8")

    changeset = ChangeSet.detect(workspace, sandbox.base_changeset_ref())
    acceptance = Acceptance(
        sandbox=sandbox,
        commands=commands_of(task.contract),
        timeout=ACCEPTANCE_TIMEOUT_S,
        demonstrations=demonstrations_of(task.contract),
    )
    result = (gate or Gate()).run(
        changeset,
        task.contract.scope,
        semantic=None,
        acceptance=acceptance,
    )
    return as_verdict(result)


class RungUnavailableError(Exception):
    """A declared rung cannot reject, so a run would score by an unstated bar."""


# A candidate that MUST be rejected, per language. Not "bad code" in general —
# each violates a rule the configured linter or formatter is known to carry, so
# a rung that passes it is not applying the bar the run will claim.
#
# The first version of this probe asked "is the tool installed", and that was
# the wrong question. `eslint` installs fine and is inert on TypeScript without
# a parser: it emits severity-1 warnings, the adapter counts severity-2, and the
# rung passes everything while looking healthy. Installed is not the property
# that matters. Able to reject is.
# What each canary is built to trip. Checking only "did anything reject" is not
# enough and the gap is not hypothetical: the jsts canary trips `format`
# (prettier works) and not `lint` (eslint is inert without a TypeScript parser),
# so a jsts-only sweep passed a check that a paired sweep failed. The arm was
# scored by three rungs while declaring five, and nothing said so.
CANARY_EXPECTS: dict[str, tuple[str, ...]] = {
    "python": ("lint", "format"),
    "jsts": ("lint", "format"),
}

CANARIES: dict[str, str] = {
    "python": (
        "import sys\nimport os\n\n\n"
        "def f( x ):\n"
        "    y = " + '"' + "x" * 100 + '"' + "\n"
        "    return y\n"
    ),
    # Trips `no-var`, `prefer-const` and `@typescript-eslint/no-unused-vars`
    # from the recommended sets, and prettier on the spacing. Bad *spacing*
    # alone was the first version and it was not enough: it tripped format and
    # left lint looking healthy, which is the exact failure the canary exists
    # to detect.
    "jsts": (
        "export function f(a: number) {\n"
        "  var x = a\n"
        "  let unused = 5\n"
        "  return    x\n"
        "}\n"
    ),
}


def rung_report(tasks: Any, *, gate: Gate | None = None) -> dict[str, dict[str, Any]]:
    """Per language: which rungs can run, and whether they can actually reject.

    Two probes per language, both through the real scoring path:

    * the **reference** solution, which must pass — it is the corpus's own
      answer, so a rejection means the material fails its own bar;
    * a **canary**, which must fail — it violates rules the configured tools
      carry, so a pass means the rung is inert.

    A rung that runs and never rejects is the failure this project has now hit
    three times in one afternoon: ruff with no config applying the wrong rules,
    eslint absent, eslint present and parserless. Each looked healthy.
    """
    report: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for task in tasks:
        language = task.language.name
        if language in seen:
            continue
        seen.add(language)
        with tempfile.TemporaryDirectory(prefix="mcgyvr-preflight-") as tmp:
            base = stage_dir(task, task.contract.target_content, Path(tmp) / "base")
            with TempDirSandbox(base) as sandbox:
                reference = score(task, task.reference.read_text(), sandbox, gate=gate)
                canary = score(task, CANARIES[language], sandbox, gate=gate)
        report[language] = {
            "reference_passes": reference.passed,
            "reference_rejected_by": reference.rejected_by,
            "canary_rejected": not canary.passed,
            # Every rung that fired, not just the first. `rejected_by` reports
            # findings[0], which is an ordering artefact — comparing it across
            # arms would refuse runs whose bars actually match and accept runs
            # whose bars differ beyond the first finding.
            "canary_rejected_by": sorted({f.split(":", 1)[0] for f in canary.findings}),
            "environment_issues": list(reference.environment_issues),
        }
    return report


def preflight(tasks: Any, *, gate: Gate | None = None) -> tuple[str, ...]:
    """Every reason this sweep would not measure what it claims to."""
    issues: list[str] = []
    report = rung_report(tasks, gate=gate)
    for language, row in sorted(report.items()):
        for issue in row["environment_issues"]:
            issues.append(f"{language}: {issue}")
        if not row["canary_rejected"]:
            issues.append(
                f"{language}: a deliberately malformed candidate PASSED — the "
                "adapter rungs are running but cannot reject, so this arm would "
                "be scored by a smaller bar than it declares"
            )
        else:
            inert = [
                rung
                for rung in CANARY_EXPECTS.get(language, ())
                if rung not in row["canary_rejected_by"]
            ]
            if inert:
                issues.append(
                    f"{language}: the {', '.join(inert)} rung(s) did not reject a "
                    "candidate built to trip them — they run, they never say no, "
                    "and this arm would be scored by fewer rungs than it declares"
                )
        if not row["reference_passes"]:
            issues.append(
                f"{language}: the corpus's own reference solution is rejected by "
                f"{row['reference_rejected_by']} — the material does not clear "
                "the bar this run would hold workers to"
            )

    # The confound that matters most: two arms scored differently. Even when
    # every arm is individually explicable, a *difference* between them lands
    # inside every paired contrast, which is ADR-0021's whole denominator.
    # Compared over the rungs each arm was *expected* to exercise, not over the
    # raw set the canary happened to trip. Two canaries are different code in
    # different languages and will naturally fire different extra checks — the
    # jsts one trips `structure` and the python one does not, which is a fact
    # about the two snippets and not a difference in the bar. What would be a
    # difference in the bar is a declared rung that is live on one arm and inert
    # on the other, and that is what this compares.
    live = {
        lang: tuple(
            sorted(set(CANARY_EXPECTS.get(lang, ())) & set(row["canary_rejected_by"]))
        )
        for lang, row in report.items()
    }
    if len(report) > 1 and len(set(live.values())) > 1:
        issues.append(
            "the arms of this sweep are scored by different rungs — "
            + "; ".join(
                f"{k} applies {'+'.join(v) or 'nothing'}"
                for k, v in sorted(live.items())
            )
            + ". A paired ts/py contrast would carry that difference inside it."
        )
    return tuple(issues)


def require_rungs(tasks: Any, *, gate: Gate | None = None) -> None:
    """Refuse the sweep unless every declared rung can reject on every arm."""
    issues = preflight(tasks, gate=gate)
    if not issues:
        return
    raise RungUnavailableError(
        "this sweep would not measure what it claims to:\n  "
        + "\n  ".join(issues)
        + "\n\nA rate measured under a silently reduced bar is not comparable "
        "to one that was not. Fix the environment, or narrow the run to one arm "
        "and say so."
    )


def as_verdict(result: Any) -> Verdict:
    """Flatten a :class:`~mcgyvr.gate.runner.GateResult` into a row's fields."""
    findings = tuple(
        f"{finding.check}: {finding.message}" for finding in result.findings
    )
    rejected_by = result.findings[0].check if result.findings else None
    return Verdict(
        passed=result.accepted,
        rejected_by=rejected_by,
        findings=findings,
        environment_issues=tuple(result.environment_issues),
    )
