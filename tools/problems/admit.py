#!/usr/bin/env python3
"""#197 — the admission gate for the problem pool.

A pool problem is two arms of the same problem (``tasks/ts/<id>/`` and
``tasks/py/<id>/``), each a contract plus a reference solution plus a checker,
and it enters the pool only through this gate. The checks are the ones
`tools/problems/README.md` states, in its order: structure, contract validity,
selftest, failing-first for ``bug_fix``, anti-triviality stubs, checker floor,
HumanEval entry-point overlap, near-duplicate screen.

Two of these deserve their one-line why here rather than only in the README:

* **Stubs must fail** because the checker was generated alongside the
  reference it checks, and a generator's blind spots recur in its tests
  (SAGA, arXiv 2507.06920). The no-op and echo stubs are inputs the
  generator never saw; a checker they pass is measuring nothing.
* **Admission pins by digest** (``--pin`` → ``admissions.jsonl``) because run
  directories pin their tier's task digests, so an edited task silently
  refuses every prior run a resume. A defective problem is superseded under
  a new id, never repaired in place — d1r's discipline.

Execution happens in a fresh temporary directory per candidate, holding
exactly the solution and the checker, with the contract's own declared
commands — the same shape ``tools/bundle/measure.py`` runs, deliberately,
so admission rehearses what a measurement run will do.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mcgyvr.contract import Contract, ContractError, load

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
TASKS = HERE / "tasks"
MANIFEST = HERE / "admissions.jsonl"
ENTRYPOINTS = HERE / "humaneval-entrypoints.json"

# The id is the join key everywhere downstream (results rows, golden.json,
# the dataset builder), so it is globally unique by construction: no other
# task set uses the p-prefix, and the manifest holds the pool to one id each.
ID_RE = re.compile(r"^p\d{3}-[a-z0-9]+(?:-[a-z0-9]+)*$")

# v1 admits the two types whose checkers decide pass/fail by running code.
# type_annotation checkers read their own source text (d1 t17/t18), which
# needs its own anti-triviality design before the pool can carry it.
V1_TYPES = frozenset({"function_implementation", "bug_fix"})


def _bench_score() -> Any:
    """``tools/bench/score.py``, for the one acceptance ceiling it declares.

    By path, because ``tools/`` holds no packages — the shim every cross-tool
    reference in this tree uses. Loaded for a single constant, and that is the
    point: the alternative is a second literal, which is what #262 found here.
    """
    cached = sys.modules.get("bench_score")
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(
        "bench_score", REPO / "tools" / "bench" / "score.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# The rig's ceiling, imported rather than restated (#262, ADR-0035). Admission
# rehearses the measurement, so a checker too slow for the rig is too slow for
# the pool — and the only way that sentence stays true is if there is one
# number. This line used to be a literal `30.0` under a comment claiming it
# matched, while `tools/bench/score.py` scored at `120.0`: admission applied a
# 4x tighter bar than the instrument it was rehearsing, and said the opposite.
TIMEOUT_S = _bench_score().ACCEPTANCE_TIMEOUT_S

MIN_ASSERTIONS = 5
JACCARD_REJECT = 0.55


class AdmitError(Exception):
    """The gate cannot run as specified — an environment fault, not a verdict."""


@dataclass(frozen=True)
class Arm:
    """One language's rendering of pool problems."""

    name: str
    root: Path
    solution: str
    reference: str
    accept: str
    interface_re: re.Pattern[str]


ARMS = (
    Arm(
        name="ts",
        root=TASKS / "ts",
        solution="solution.ts",
        reference="reference.ts",
        accept="accept.mjs",
        interface_re=re.compile(r"function\s+([A-Za-z_]\w*)"),
    ),
    Arm(
        name="py",
        root=TASKS / "py",
        solution="solution.py",
        reference="reference.py",
        accept="accept.py",
        interface_re=re.compile(r"def\s+([A-Za-z_]\w*)"),
    ),
)


def _instruments() -> Any:
    """The instrument declaration, imported by path — ``tools/`` is no package.

    Loaded once per process and shared: the declaration is meant to be one
    object with one answer, so a second copy with its own cache is exactly
    the drift this module exists to prevent.
    """
    cached = sys.modules.get("instruments")
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(
        "instruments", REPO / "tools" / "instruments.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def existing_task_roots() -> tuple[Path, ...]:
    """Every task set whose ids and prose the pool must stay distinct from.

    Read from ``tools/instruments.json`` rather than listed here, because the
    same list decides what a training set may not draw from (#230). This gate
    is the reason the id rule over there is sound: no pool problem can take an
    instrument's id, so an instrument id in a run is instrument material.
    """
    return _instruments().task_roots()


@dataclass(frozen=True)
class Verdict:
    """One check's outcome for one problem."""

    check: str
    ok: bool
    detail: str = ""


@dataclass
class Report:
    """Everything the gate decided about one problem."""

    problem: str
    verdicts: list[Verdict]

    @property
    def admitted(self) -> bool:
        return all(v.ok for v in self.verdicts)


# --- environment ----------------------------------------------------------


def preflight() -> None:
    """Refuse to judge anything if the judging environment is absent.

    A missing runtime would fail every candidate for a reason that is not
    the candidate's, and a gate that converts environment faults into
    rejections quarantines good problems. Same stance as the rigs'
    capability probes.
    """
    if shutil.which("python") is None:
        raise AdmitError(
            "`python` is not on PATH; the contracts declare `python accept.py`."
            " Run under `uv run`."
        )
    if shutil.which("node") is None:
        raise AdmitError("`node` is not on PATH; the contracts declare `node`.")
    with tempfile.TemporaryDirectory(prefix="pool-preflight-") as tmp:
        probe = Path(tmp)
        (probe / "solution.ts").write_text(
            "export const probe: number = 1;\n", encoding="utf-8"
        )
        (probe / "probe.mjs").write_text(
            'import { probe } from "./solution.ts";\n'
            "if (probe !== 1) process.exit(1);\n",
            encoding="utf-8",
        )
        run = subprocess.run(
            ["node", "probe.mjs"],
            cwd=probe,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
        )
    if run.returncode != 0:
        raise AdmitError(
            "this Node cannot run TypeScript directly (type stripping is "
            "unflagged from 23.6; the task sets are built on 24): "
            + run.stderr.strip()[:200]
        )


# --- the corpus the pool must stay distinct from --------------------------


def existing_tasks() -> dict[str, Contract]:
    """Contracts of every non-pool task set, keyed by a set-qualified label."""
    found: dict[str, Contract] = {}
    for root in existing_task_roots():
        if not root.is_dir():
            continue
        for directory in sorted(root.iterdir()):
            manifest = directory / "contract.yaml"
            if directory.is_dir() and manifest.is_file():
                label = f"{root.parent.name}/{root.name}/{directory.name}"
                found[label] = load(manifest)
    return found


def _words(text: str) -> frozenset[str]:
    return frozenset(re.findall(r"[a-z0-9]+", text.lower()))


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _normalise_symbol(name: str) -> str:
    """Case- and separator-blind form, so snake and camel renderings match."""
    return name.replace("_", "").lower()


def humaneval_entry_points() -> frozenset[str]:
    raw = json.loads(ENTRYPOINTS.read_text(encoding="utf-8"))
    return frozenset(_normalise_symbol(row["entry_point"]) for row in raw)


# --- execution ------------------------------------------------------------


def run_checker(
    arm: Arm, directory: Path, contract: Contract, solution_text: str
) -> tuple[bool, str]:
    """Run the contract's declared commands against one solution text.

    Fresh directory, exactly the solution and the checker — the same shape
    the rigs run, so an admitted problem is one a measurement can dispatch.
    Exit 126/127 is an environment fault and aborts admission rather than
    counting against the candidate.
    """
    commands = (*contract.demonstration, *contract.acceptance)
    if not commands:
        return False, "contract declares no commands to run"
    with tempfile.TemporaryDirectory(prefix="pool-admit-") as tmp:
        workdir = Path(tmp)
        (workdir / arm.solution).write_text(solution_text, encoding="utf-8")
        shutil.copy(directory / arm.accept, workdir / arm.accept)
        for command in commands:
            try:
                proc = subprocess.run(
                    command.split(),
                    cwd=workdir,
                    capture_output=True,
                    text=True,
                    timeout=TIMEOUT_S,
                )
            except subprocess.TimeoutExpired:
                return False, f"`{command}` exceeded {TIMEOUT_S:.0f}s"
            if proc.returncode in (126, 127):
                raise AdmitError(
                    f"`{command}` could not run (exit {proc.returncode}): "
                    + proc.stderr.strip()[:200]
                )
            if proc.returncode != 0:
                tail = (proc.stderr or proc.stdout).strip().splitlines()
                return False, f"`{command}` failed: " + (tail[-1] if tail else "")
    return True, ""


def stub_solutions(arm: Arm, contract: Contract) -> list[tuple[str, str]]:
    """The degenerate solutions the checker must reject, from the interface."""
    match = arm.interface_re.search(contract.interface)
    if match is None:
        return []
    name = match.group(1)
    if arm.name == "ts":
        return [
            (
                "no-op stub",
                f"export function {name}(...args: any[]): any "
                "{ return undefined; }\n",
            ),
            (
                "echo stub",
                f"export function {name}(...args: any[]): any {{ return args[0]; }}\n",
            ),
        ]
    return [
        ("no-op stub", f"def {name}(*args, **kwargs):\n    return None\n"),
        (
            "echo stub",
            f"def {name}(*args, **kwargs):\n    return args[0] if args else None\n",
        ),
    ]


# --- the checks -----------------------------------------------------------


def check_problem(
    problem: str,
    existing: dict[str, Contract],
    pool_specs: dict[str, frozenset[str]],
    blocklist: frozenset[str],
) -> Report:
    """Every admission check for one problem, in the README's order.

    ``pool_specs`` holds the task prose of every other pool problem in this
    invocation plus everything already admitted, so a batch is screened
    against itself as well as against history.
    """
    verdicts: list[Verdict] = []
    report = Report(problem=problem, verdicts=verdicts)

    if not ID_RE.match(problem):
        verdicts.append(Verdict("structure", False, "id must match p<nnn>-<slug>"))
        return report

    contracts: dict[str, Contract] = {}
    for arm in ARMS:
        directory = arm.root / problem
        missing = [
            name
            for name in ("contract.yaml", arm.reference, arm.accept)
            if not (directory / name).is_file()
        ]
        if not directory.is_dir() or missing:
            what = ", ".join(missing) if missing else "the whole arm"
            verdicts.append(
                Verdict("structure", False, f"{arm.name} arm is missing {what}")
            )
            continue
        try:
            contracts[arm.name] = load(directory / "contract.yaml")
        except ContractError as error:
            verdicts.append(Verdict("contract", False, f"{arm.name}: {error}"))
    if len(contracts) != len(ARMS):
        return report

    for arm_name, contract in contracts.items():
        if contract.id != problem:
            verdicts.append(
                Verdict(
                    "structure",
                    False,
                    f"{arm_name} contract id {contract.id!r} is not the "
                    f"directory name {problem!r}",
                )
            )
        if contract.task_type not in V1_TYPES:
            verdicts.append(
                Verdict(
                    "contract",
                    False,
                    f"{arm_name}: task_type {contract.task_type!r} is not in "
                    f"the v1 pool set {sorted(V1_TYPES)}",
                )
            )
    types = {c.task_type for c in contracts.values()}
    if len(types) > 1:
        verdicts.append(
            Verdict("structure", False, f"arms disagree on task_type: {types}")
        )
    if not report.admitted:
        return report

    clash = {
        label
        for label, contract in existing.items()
        if contract.id == problem or label.rsplit("/", 1)[-1] == problem
    }
    if clash:
        verdicts.append(
            Verdict("structure", False, f"id collides with {sorted(clash)}")
        )

    for arm in ARMS:
        directory = arm.root / problem
        contract = contracts[arm.name]
        reference = (directory / arm.reference).read_text(encoding="utf-8")

        passed, detail = run_checker(arm, directory, contract, reference)
        verdicts.append(Verdict(f"selftest[{arm.name}]", passed, detail))

        if contract.task_type == "bug_fix":
            if not contract.target_content.strip():
                verdicts.append(
                    Verdict(
                        f"failing-first[{arm.name}]",
                        False,
                        "bug_fix without target_content has no bug to show",
                    )
                )
            elif contract.target_content.strip() == reference.strip():
                verdicts.append(
                    Verdict(
                        f"failing-first[{arm.name}]",
                        False,
                        "target_content and reference are identical",
                    )
                )
            else:
                buggy_passed, _ = run_checker(
                    arm, directory, contract, contract.target_content
                )
                verdicts.append(
                    Verdict(
                        f"failing-first[{arm.name}]",
                        not buggy_passed,
                        "the declared bug passes the checker" if buggy_passed else "",
                    )
                )
        else:
            stubs = stub_solutions(arm, contracts[arm.name])
            if not stubs:
                verdicts.append(
                    Verdict(
                        f"anti-triviality[{arm.name}]",
                        False,
                        "no function name found in `interface` — v1 pool "
                        "problems declare a single function",
                    )
                )
            for label, text in stubs:
                stub_passed, _ = run_checker(arm, directory, contracts[arm.name], text)
                verdicts.append(
                    Verdict(
                        f"anti-triviality[{arm.name}]",
                        not stub_passed,
                        f"the {label} passes the checker" if stub_passed else "",
                    )
                )

        assertions = (
            (directory / arm.accept).read_text(encoding="utf-8").count("assert")
        )
        verdicts.append(
            Verdict(
                f"checker-floor[{arm.name}]",
                assertions >= MIN_ASSERTIONS,
                f"{assertions} assertions < {MIN_ASSERTIONS}"
                if assertions < MIN_ASSERTIONS
                else "",
            )
        )

        symbol = arm.interface_re.search(contracts[arm.name].interface)
        if symbol is not None:
            hit = _normalise_symbol(symbol.group(1)) in blocklist
            verdicts.append(
                Verdict(
                    f"humaneval-overlap[{arm.name}]",
                    not hit,
                    f"{symbol.group(1)!r} is a HumanEval entry point" if hit else "",
                )
            )

    spec = _words(contracts["ts"].task)
    rivals: dict[str, frozenset[str]] = {
        label: _words(contract.task) for label, contract in existing.items()
    }
    rivals.update(
        {label: words for label, words in pool_specs.items() if label != problem}
    )
    if rivals:
        nearest = max(rivals, key=lambda label: jaccard(spec, rivals[label]))
        score = jaccard(spec, rivals[nearest])
        verdicts.append(
            Verdict(
                "near-duplicate",
                score < JACCARD_REJECT,
                f"task prose is {score:.2f} Jaccard-similar to {nearest}"
                if score >= JACCARD_REJECT
                else "",
            )
        )
    return report


# --- the manifest ---------------------------------------------------------


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def problem_files(problem: str) -> dict[str, Path]:
    """Every file an admitted problem is pinned by, manifest-key → path."""
    files: dict[str, Path] = {}
    for arm in ARMS:
        directory = arm.root / problem
        for name in ("contract.yaml", arm.reference, arm.accept):
            files[f"{arm.name}/{name}"] = directory / name
    return files


def manifest_entries() -> list[dict[str, object]]:
    if not MANIFEST.is_file():
        return []
    return [
        json.loads(line)
        for line in MANIFEST.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def pin(problems: list[str], provenance: str) -> int:
    """Append admitted problems to the manifest; refuse re-pins."""
    pinned = {str(entry["id"]) for entry in manifest_entries()}
    added = 0
    with MANIFEST.open("a", encoding="utf-8") as handle:
        for problem in problems:
            if problem in pinned:
                continue
            entry = {
                "id": problem,
                "admitted": datetime.now(UTC).date().isoformat(),
                "provenance": provenance,
                "files": {
                    key: _digest(path) for key, path in problem_files(problem).items()
                },
            }
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
            added += 1
    return added


def verify_manifest() -> list[str]:
    """Every way the tree and the manifest can disagree, as messages.

    This is the function ``tests/test_pool.py`` holds the repository to: a
    pool task on disk is either pinned byte for byte or it is not a pool
    task, and a manifest line either matches the tree or names a superseded
    problem that has left it.
    """
    problems: list[str] = []
    entries = manifest_entries()
    by_id = {str(entry["id"]): entry for entry in entries}
    if len(by_id) != len(entries):
        problems.append("manifest pins the same id twice")

    on_disk: set[str] = set()
    for arm in ARMS:
        if arm.root.is_dir():
            on_disk.update(p.name for p in arm.root.iterdir() if p.is_dir())

    for name in sorted(on_disk):
        entry = by_id.get(name)
        if entry is None:
            problems.append(f"{name} is on disk but not in the manifest")
            continue
        if entry.get("superseded_by"):
            problems.append(f"{name} is superseded but still on disk")
        files = entry["files"]
        assert isinstance(files, dict)
        for key, path in problem_files(name).items():
            if not path.is_file():
                problems.append(f"{name}: pinned file {key} is missing")
            elif files.get(key) != _digest(path):
                problems.append(f"{name}: {key} differs from its pinned digest")

    for name, entry in by_id.items():
        if name not in on_disk and not entry.get("superseded_by"):
            problems.append(f"{name} is pinned but absent, and not superseded")
    return problems


# --- entry point ----------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("problems", nargs="*", help="problem ids to judge")
    parser.add_argument(
        "--all", action="store_true", help="judge every problem on disk"
    )
    parser.add_argument(
        "--pin", action="store_true", help="append admitted problems to the manifest"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the manifest against the tree and exit",
    )
    parser.add_argument(
        "--provenance",
        default="",
        help="who generated this batch and when, recorded per pin",
    )
    args = parser.parse_args(argv)

    if args.check:
        troubles = verify_manifest()
        for line in troubles:
            print(f"✗ {line}")
        if not troubles:
            print("✓ manifest and tree agree")
        return 1 if troubles else 0

    names = set(args.problems)
    if args.all:
        for arm in ARMS:
            if arm.root.is_dir():
                names.update(p.name for p in arm.root.iterdir() if p.is_dir())
    if not names:
        parser.error("name problems to judge, or pass --all")
    if args.pin and not args.provenance:
        parser.error("--pin requires --provenance")

    preflight()
    existing = existing_tasks()
    blocklist = humaneval_entry_points()

    pool_specs: dict[str, frozenset[str]] = {}
    for arm_root in (ARMS[0].root,):
        if arm_root.is_dir():
            for directory in arm_root.iterdir():
                manifest = directory / "contract.yaml"
                if directory.is_dir() and manifest.is_file():
                    try:
                        pool_specs[directory.name] = _words(load(manifest).task)
                    except ContractError:
                        continue

    reports = [
        check_problem(name, existing, pool_specs, blocklist) for name in sorted(names)
    ]
    admitted = [r.problem for r in reports if r.admitted]
    for report in reports:
        mark = "✓" if report.admitted else "✗"
        print(f"{mark} {report.problem}")
        for verdict in report.verdicts:
            if not verdict.ok:
                print(f"    ✗ {verdict.check}: {verdict.detail}")
    print(f"{len(admitted)}/{len(reports)} admitted")

    if args.pin and admitted:
        added = pin(admitted, args.provenance)
        print(f"pinned {added} (already pinned: {len(admitted) - added})")
    return 0 if len(admitted) == len(reports) else 1


if __name__ == "__main__":
    sys.exit(main())
