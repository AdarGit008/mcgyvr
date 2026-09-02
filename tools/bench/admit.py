#!/usr/bin/env python3
"""#225 — the admission gate for the bench campaign.

A bench problem is two arms of the same problem (``tasks/ts/<id>/`` and
``tasks/py/<id>/``), each a contract plus a reference solution plus a
checker, with one ``meta.json`` sidecar in the ts arm (the canonical arm —
the near-duplicate screen already keys on its prose). The design of record
is ``archive/docs/bench-design-2026-08-10.md`` §3; the check order below is that
section's, and the execution machinery (fresh directory per candidate,
contract-declared commands, the 30s ceiling) is the pool gate's, imported
by path — orchestration is bench-owned, machinery is shared.

What this gate tightens over ``tools/problems/admit.py``, and why:

* **Anti-triviality is declared-target.** The pool stubs the *first*
  declared function, which on a multi-symbol file stubs a helper or fails
  structurally — vacuous either way. Here the target symbol is resolved by
  name (the interface's single declaration for ``single_definition``,
  ``meta.json``'s ``target_symbol`` for ``multi_symbol``), and the stub is
  the *reference with only that symbol's behaviour degraded* — helpers
  intact — so "the checker rejects the stub" means the same thing at every
  file shape. #126's arm lives on exactly this material existing.
* **Two front doors are blocked, not one.** HumanEval's 164 entry points
  and MBPP+'s 378 (``mbpp-entrypoints.json``): MBPP is pretraining-memorized
  *and* the band's locator (``records/measurements/mbpp-plus-3b-2026-08-10/``),
  so restating an MBPP item would overstate the floor and couple the bench
  to its own ruler. Every declared function is screened, not only the first.
* **The screen runs across the split by construction.** Every candidate is
  screened against the whole manifest — both halves, wherever they live —
  plus the pool's prose and the retired instruments'. The same problem
  worded two ways on both sides of the split is the recontamination #225
  names, and it dies here.
* **The split is recorded at pin time and never chosen.** ``split.py``'s
  pre-declared rule assigns the half; ``--pin`` writes the assignment into
  the manifest and moves a reserve problem's arms to ``reserve/`` — outside
  the roots ``tools/instruments.json`` will declare, so reserve exhaust can
  never classify as instrument material.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import re
import shutil
import sys
import types
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mcgyvr.contract import Contract, ContractError, load

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent


def _by_path(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


pool = _by_path("pool_admit", HERE.parent / "problems" / "admit.py")
split_rule = _by_path("bench_split", HERE / "split.py")

TASKS = HERE / "tasks"
RESERVE = HERE / "reserve"
MANIFEST = HERE / "admissions.jsonl"
MBPP_ENTRYPOINTS = HERE / "mbpp-entrypoints.json"

# The b-prefix is the bench's by construction (checked unclaimed 2026-08-10);
# the id is the join key everywhere downstream, exactly the pool's argument.
ID_RE = re.compile(r"^b\d{3}-[a-z0-9]+(?:-[a-z0-9]+)*$")

# Same two types as the pool, same reason (#211 owns type_annotation's gate).
V1_TYPES = frozenset({"function_implementation", "bug_fix"})

FILE_SHAPES = frozenset({"single_definition", "multi_symbol"})
SHAPES = frozenset(
    {"recursion", "iteration", "string", "numeric", "data_structure", "error_handling"}
)

META = "meta.json"

# The bench's arms are the pool's arms pointed at the bench's roots — same
# filenames, same interface regexes, so the two gates disagree only where
# the design says they must.
ARMS = tuple(
    pool.Arm(
        name=arm.name,
        root=TASKS / arm.name,
        solution=arm.solution,
        reference=arm.reference,
        accept=arm.accept,
        interface_re=arm.interface_re,
    )
    for arm in pool.ARMS
)


def blocklist() -> frozenset[str]:
    """Both front doors' entry points, normalised — HumanEval's and MBPP+'s."""
    rows = json.loads(MBPP_ENTRYPOINTS.read_text(encoding="utf-8"))
    mbpp = frozenset(pool._normalise_symbol(row["entry_point"]) for row in rows)
    return frozenset(pool.humaneval_entry_points()) | mbpp


# --- the sidecar ----------------------------------------------------------


def meta_path(problem: str, root: Path = TASKS) -> Path:
    """The sidecar lives in the ts arm — one file per problem, not per arm."""
    return root / "ts" / problem / META


def validate_meta(meta: object, contracts: dict[str, Contract]) -> list[str]:
    """Every way a sidecar can fail, as messages — pure, so the tests hold it.

    ``target_symbol`` is per-arm because the same problem names its target
    idiomatically per language (``parseDuration`` / ``parse_duration``), and
    each name must actually be declared in that arm's interface — a target
    the interface does not declare cannot be stubbed, and a check that
    silently fell back to the first declaration would be the pool's
    weakness wearing the bench's name.
    """
    problems: list[str] = []
    if not isinstance(meta, dict):
        return [f"{META} is not an object"]
    file_shape = meta.get("file_shape")
    if file_shape not in FILE_SHAPES:
        problems.append(
            f"file_shape {file_shape!r} is not one of {sorted(FILE_SHAPES)}"
        )
    shape = meta.get("shape")
    if shape not in SHAPES:
        problems.append(f"shape {shape!r} is not one of {sorted(SHAPES)}")
    band = meta.get("steering_band")
    if not isinstance(band, str) or not band.strip():
        problems.append("steering_band is missing or empty")

    declared: dict[str, list[str]] = {}
    for arm in ARMS:
        contract = contracts.get(arm.name)
        if contract is not None:
            declared[arm.name] = arm.interface_re.findall(contract.interface)

    if file_shape == "multi_symbol":
        symbols = meta.get("target_symbol")
        if not isinstance(symbols, dict):
            problems.append("multi_symbol requires target_symbol: {arm: name}")
        else:
            for arm_name, names in declared.items():
                target = symbols.get(arm_name)
                if not isinstance(target, str) or not target:
                    problems.append(f"target_symbol[{arm_name}] is missing")
                elif target not in names:
                    problems.append(
                        f"target_symbol[{arm_name}] {target!r} is not declared "
                        f"in the interface ({names or 'nothing declared'})"
                    )
    elif file_shape == "single_definition":
        for arm_name, names in declared.items():
            if len(names) != 1:
                problems.append(
                    f"single_definition, but the {arm_name} interface declares "
                    f"{len(names)} functions ({names}) — exactly one is the rule"
                )
    return problems


def target_symbol(meta: dict[str, Any], contract: Contract, arm: Any) -> str | None:
    """The symbol the stubs degrade, or None if the sidecar already failed."""
    if meta.get("file_shape") == "multi_symbol":
        symbols = meta.get("target_symbol")
        if isinstance(symbols, dict):
            name = symbols.get(arm.name)
            return name if isinstance(name, str) and name else None
        return None
    names = arm.interface_re.findall(contract.interface)
    return names[0] if len(names) == 1 else None


# --- declared-target stubs ------------------------------------------------


def stub_texts(arm: Any, reference: str, target: str) -> list[tuple[str, str]] | None:
    """The reference with only the target's behaviour degraded, two ways.

    Python shadows: a later ``def`` of the same name wins at import, so the
    stub is appended and every helper stays intact. TypeScript cannot
    redeclare in module scope, so the original is renamed in place — the
    rule requires ``export function <target>(`` to appear exactly once,
    which the generator brief mandates — and the exported stub is appended
    (declarations hoist, so recursive references land on the stub, which is
    the degradation working, not a defect). Returns None when the ts form
    is not replaceable — the caller reports that as its own named failure
    rather than a vacuous pass.
    """
    if arm.name == "py":
        no_op = f"\n\ndef {target}(*args, **kwargs):\n    return None\n"
        echo = (
            f"\n\ndef {target}(*args, **kwargs):\n"
            "    return args[0] if args else None\n"
        )
        return [("no-op stub", reference + no_op), ("echo stub", reference + echo)]

    pattern = f"export function {target}("
    if reference.count(pattern) != 1:
        return None
    renamed = reference.replace(pattern, f"function __original_{target}(", 1)
    no_op = (
        renamed
        + f"\nexport function {target}(...args: any[]): any {{ return undefined; }}\n"
    )
    echo = (
        renamed
        + f"\nexport function {target}(...args: any[]): any {{ return args[0]; }}\n"
    )
    return [("no-op stub", no_op), ("echo stub", echo)]


# --- the corpus the bench must stay distinct from -------------------------


def instrument_tasks() -> dict[str, Contract]:
    """Every declared instrument's contracts, the bench's own roots excluded."""
    found: dict[str, Contract] = {}
    own = {arm.root.resolve() for arm in ARMS}
    for root in pool.existing_task_roots():
        if not root.is_dir() or root.resolve() in own:
            continue
        for directory in sorted(root.iterdir()):
            manifest = directory / "contract.yaml"
            if directory.is_dir() and manifest.is_file():
                found[f"{root.parent.name}/{root.name}/{directory.name}"] = load(
                    manifest
                )
    return found


def pool_material() -> tuple[frozenset[str], dict[str, frozenset[str]]]:
    """The pool's admitted ids and prose — not an instrument, still excluded.

    The pool is training-side, so the declaration does not cover it; the
    bench excludes it here instead, ids and prose both. Prose comes from the
    ts arm only, because arms share task text by construction.
    """
    ids: set[str] = set()
    specs: dict[str, frozenset[str]] = {}
    for entry in pool.manifest_entries():
        if entry.get("superseded_by"):
            continue
        problem = str(entry["id"])
        ids.add(problem)
        contract_path = pool.TASKS / "ts" / problem / "contract.yaml"
        if contract_path.is_file():
            specs[f"pool/{problem}"] = pool._words(load(contract_path).task)
    return frozenset(ids), specs


def manifest_entries() -> list[dict[str, object]]:
    if not MANIFEST.is_file():
        return []
    return [
        json.loads(line)
        for line in MANIFEST.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def admitted_specs() -> dict[str, frozenset[str]]:
    """Task prose of everything already admitted — both halves, wherever they live.

    This is the line that makes the near-duplicate screen run *across* the
    split: a candidate is compared with every admitted problem regardless of
    which half the rule put it in.
    """
    specs: dict[str, frozenset[str]] = {}
    for entry in manifest_entries():
        if entry.get("superseded_by"):
            continue
        problem = str(entry["id"])
        root = RESERVE if entry.get("split") == split_rule.RESERVE else TASKS
        contract_path = root / "ts" / problem / "contract.yaml"
        if contract_path.is_file():
            specs[f"bench/{problem}"] = pool._words(load(contract_path).task)
    return specs


# --- the checks -----------------------------------------------------------


def check_problem(
    problem: str,
    instruments: dict[str, Contract],
    pool_ids: frozenset[str],
    rival_specs: dict[str, frozenset[str]],
    blocked: frozenset[str],
) -> Any:
    """Every admission check for one candidate, in the design doc's order.

    ``rival_specs`` carries everything the near-duplicate screen compares
    against: the instruments' prose, the pool's, both halves of the bench,
    and the other candidates of this invocation.
    """
    verdicts: list[Any] = []
    report = pool.Report(problem=problem, verdicts=verdicts)

    if not ID_RE.match(problem):
        verdicts.append(pool.Verdict("structure", False, "id must match b<nnn>-<slug>"))
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
                pool.Verdict("structure", False, f"{arm.name} arm is missing {what}")
            )
            continue
        try:
            contracts[arm.name] = load(directory / "contract.yaml")
        except ContractError as error:
            verdicts.append(pool.Verdict("contract", False, f"{arm.name}: {error}"))
    if len(contracts) != len(ARMS):
        return report

    for arm_name, contract in contracts.items():
        if contract.id != problem:
            verdicts.append(
                pool.Verdict(
                    "structure",
                    False,
                    f"{arm_name} contract id {contract.id!r} is not the "
                    f"directory name {problem!r}",
                )
            )
        if contract.task_type not in V1_TYPES:
            verdicts.append(
                pool.Verdict(
                    "contract",
                    False,
                    f"{arm_name}: task_type {contract.task_type!r} is not in "
                    f"the bench v1 set {sorted(V1_TYPES)} (#211 owns the rest)",
                )
            )
    task_types = {c.task_type for c in contracts.values()}
    if len(task_types) > 1:
        verdicts.append(
            pool.Verdict(
                "structure", False, f"arms disagree on task_type: {task_types}"
            )
        )

    sidecar = meta_path(problem)
    meta: dict[str, Any] = {}
    if not sidecar.is_file():
        verdicts.append(pool.Verdict("structure", False, f"ts arm is missing {META}"))
    else:
        try:
            loaded = json.loads(sidecar.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            verdicts.append(pool.Verdict("structure", False, f"{META}: {error}"))
        else:
            for message in validate_meta(loaded, contracts):
                verdicts.append(pool.Verdict("meta", False, message))
            if isinstance(loaded, dict):
                meta = loaded
    if not report.admitted:
        return report

    clash = {
        label
        for label, contract in instruments.items()
        if contract.id == problem or label.rsplit("/", 1)[-1] == problem
    }
    if problem in pool_ids:
        clash.add(f"pool/{problem}")
    if any(str(entry["id"]) == problem for entry in manifest_entries()):
        clash.add(f"bench/{problem}")
    if clash:
        verdicts.append(
            pool.Verdict("structure", False, f"id collides with {sorted(clash)}")
        )
        return report

    for arm in ARMS:
        directory = arm.root / problem
        contract = contracts[arm.name]
        reference = (directory / arm.reference).read_text(encoding="utf-8")

        passed, detail = pool.run_checker(arm, directory, contract, reference)
        verdicts.append(pool.Verdict(f"selftest[{arm.name}]", passed, detail))

        if contract.task_type == "bug_fix":
            if not contract.target_content.strip():
                verdicts.append(
                    pool.Verdict(
                        f"failing-first[{arm.name}]",
                        False,
                        "bug_fix without target_content has no bug to show",
                    )
                )
            elif contract.target_content.strip() == reference.strip():
                verdicts.append(
                    pool.Verdict(
                        f"failing-first[{arm.name}]",
                        False,
                        "target_content and reference are identical",
                    )
                )
            else:
                buggy_passed, _ = pool.run_checker(
                    arm, directory, contract, contract.target_content
                )
                verdicts.append(
                    pool.Verdict(
                        f"failing-first[{arm.name}]",
                        not buggy_passed,
                        "the declared bug passes the checker" if buggy_passed else "",
                    )
                )
        else:
            target = target_symbol(meta, contract, arm)
            if target is None:
                verdicts.append(
                    pool.Verdict(
                        f"anti-triviality[{arm.name}]",
                        False,
                        "no target symbol resolvable — meta.json and the "
                        "interface disagree",
                    )
                )
            else:
                stubs = stub_texts(arm, reference, target)
                if stubs is None:
                    verdicts.append(
                        pool.Verdict(
                            f"target-form[{arm.name}]",
                            False,
                            f"`export function {target}(` must appear exactly "
                            "once in the reference — the brief mandates the "
                            "declaration form so degradation is mechanical",
                        )
                    )
                else:
                    for label, text in stubs:
                        stub_passed, _ = pool.run_checker(
                            arm, directory, contract, text
                        )
                        verdicts.append(
                            pool.Verdict(
                                f"anti-triviality[{arm.name}]",
                                not stub_passed,
                                f"the {label} passes the checker"
                                if stub_passed
                                else "",
                            )
                        )

        assertions = (
            (directory / arm.accept).read_text(encoding="utf-8").count("assert")
        )
        verdicts.append(
            pool.Verdict(
                f"checker-floor[{arm.name}]",
                assertions >= pool.MIN_ASSERTIONS,
                f"{assertions} assertions < {pool.MIN_ASSERTIONS}"
                if assertions < pool.MIN_ASSERTIONS
                else "",
            )
        )

        for symbol in arm.interface_re.findall(contract.interface):
            if pool._normalise_symbol(symbol) in blocked:
                verdicts.append(
                    pool.Verdict(
                        f"front-door[{arm.name}]",
                        False,
                        f"{symbol!r} is a HumanEval or MBPP+ entry point",
                    )
                )

    spec = pool._words(contracts["ts"].task)
    rivals = {label: words for label, words in rival_specs.items() if label != problem}
    if rivals:
        nearest = max(rivals, key=lambda label: pool.jaccard(spec, rivals[label]))
        score = pool.jaccard(spec, rivals[nearest])
        verdicts.append(
            pool.Verdict(
                "near-duplicate",
                score < pool.JACCARD_REJECT,
                f"task prose is {score:.2f} Jaccard-similar to {nearest}"
                if score >= pool.JACCARD_REJECT
                else "",
            )
        )
    return report


# --- the manifest ---------------------------------------------------------


def problem_files(problem: str, root: Path = TASKS) -> dict[str, Path]:
    """Every file an admitted problem is pinned by, manifest-key → path."""
    files: dict[str, Path] = {}
    for arm in ARMS:
        directory = root / arm.name / problem
        for name in ("contract.yaml", arm.reference, arm.accept):
            files[f"{arm.name}/{name}"] = directory / name
    files[f"ts/{META}"] = meta_path(problem, root)
    return files


def pin(problems: list[str], provenance: str) -> int:
    """Append admitted problems with their split, then place the reserve.

    The split assignment is computed by the pre-declared rule and written
    into the entry — never passed in, so there is nothing to choose. A
    reserve problem's arms move to ``reserve/`` in the same act: outside
    the roots the declaration will walk, which is what keeps reserve
    exhaust classifiable as training material rather than instrument.
    """
    pinned = {str(entry["id"]) for entry in manifest_entries()}
    added = 0
    with MANIFEST.open("a", encoding="utf-8") as handle:
        for problem in problems:
            if problem in pinned:
                continue
            half = split_rule.assignment(problem)
            meta = json.loads(meta_path(problem).read_text(encoding="utf-8"))
            entry = {
                "id": problem,
                "admitted": datetime.now(UTC).date().isoformat(),
                "provenance": provenance,
                "split": half,
                "steering_band": meta.get("steering_band"),
                "files": {
                    key: pool._digest(path)
                    for key, path in problem_files(problem).items()
                },
            }
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
            added += 1
            if half == split_rule.RESERVE:
                for arm in ARMS:
                    source = arm.root / problem
                    destination = RESERVE / arm.name / problem
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(source), str(destination))
    return added


def verify_manifest() -> list[str]:
    """Every way the tree and the manifest can disagree, as messages.

    Beyond the pool's checks, the bench adds two: the recorded split must
    agree with the rule (a moved problem is a re-split, not a tidy-up), and
    every problem must live where its split says — a reserve id under the
    declared roots would classify as instrument material the moment the
    declaration lands.
    """
    problems: list[str] = []
    entries = manifest_entries()
    by_id = {str(entry["id"]): entry for entry in entries}
    if len(by_id) != len(entries):
        problems.append("manifest pins the same id twice")

    for name, entry in sorted(by_id.items()):
        recorded = str(entry.get("split"))
        actual = split_rule.assignment(name)
        if recorded != actual:
            problems.append(
                f"{name}: recorded split {recorded!r}, the rule says {actual!r}"
            )
        if entry.get("superseded_by"):
            continue
        root = RESERVE if recorded == split_rule.RESERVE else TASKS
        wrong_root = TASKS if root is RESERVE else RESERVE
        files = entry["files"]
        assert isinstance(files, dict)
        for key, path in problem_files(name, root).items():
            if not path.is_file():
                problems.append(
                    f"{name}: pinned file {key} is missing from {root.name}/"
                )
            elif files.get(key) != pool._digest(path):
                problems.append(f"{name}: {key} differs from its pinned digest")
        for _, path in problem_files(name, wrong_root).items():
            if path.is_file():
                problems.append(
                    f"{name}: present under {wrong_root.name}/ but its split "
                    f"says {recorded!r}"
                )
                break

    for root in (TASKS, RESERVE):
        for arm in ARMS:
            arm_root = root / arm.name
            if not arm_root.is_dir():
                continue
            for directory in arm_root.iterdir():
                if not directory.is_dir():
                    continue
                entry = by_id.get(directory.name)
                if entry is None:
                    problems.append(
                        f"{directory.name} is on disk under {root.name}/ but "
                        "not in the manifest"
                    )
                elif entry.get("superseded_by"):
                    problems.append(f"{directory.name} is superseded but still on disk")
    return problems


def cell_report() -> dict[str, dict[str, int]]:
    """Realized counts per (steering_band x task_type x file_shape) and split.

    The design doc's quotas (multi_symbol >= 25% per stratum, a declared
    bug_fix mix, target_content on >= 1/3 of fn_impl) are checked against this
    report by the operator; starved cells drive refill batches rather than
    silent acceptance.
    """
    cells: dict[str, dict[str, int]] = {}
    for entry in manifest_entries():
        if entry.get("superseded_by"):
            continue
        problem = str(entry["id"])
        half = str(entry.get("split"))
        root = RESERVE if half == split_rule.RESERVE else TASKS
        contract_path = root / "ts" / problem / "contract.yaml"
        sidecar = meta_path(problem, root)
        if not contract_path.is_file() or not sidecar.is_file():
            continue
        contract = load(contract_path)
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        key = (
            f"{meta.get('steering_band')} x {contract.task_type} x "
            f"{meta.get('file_shape')}"
        )
        cells.setdefault(key, {"bench": 0, "reserve": 0})
        cells[key][half] = cells[key].get(half, 0) + 1
    return cells


# --- entry point ----------------------------------------------------------


#: Problems withdrawn after admission, with the argument for each. Read from a
#: file rather than a constant so a retirement is a declaration with a reason
#: and a date, not a line someone deleted.
RETIRED = HERE / "retired.json"


def retired() -> dict[str, dict[str, Any]]:
    """``{id: the declaration}`` for every problem withdrawn after admission."""
    if not RETIRED.is_file():
        return {}
    doc = json.loads(RETIRED.read_text(encoding="utf-8"))
    return {str(entry["id"]): entry for entry in doc["ids"]}


def candidates() -> list[str]:
    """Unpinned problem dirs under the candidate roots, both arms or not.

    A retired id is never a candidate again. Ids are not reused, so this is
    belt and braces — but the braces are cheap and the failure it prevents is
    a withdrawn problem walking back in under its own name with a fresh
    admission record.
    """
    pinned = {str(entry["id"]) for entry in manifest_entries()}
    found: set[str] = set()
    for arm in ARMS:
        if arm.root.is_dir():
            found.update(p.name for p in arm.root.iterdir() if p.is_dir())
    return sorted(found - pinned - set(retired()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "problems", nargs="*", help="candidate ids (default: all unpinned)"
    )
    parser.add_argument(
        "--pin", action="store_true", help="pin the admitted candidates"
    )
    parser.add_argument(
        "--provenance",
        default="",
        help="how these candidates were produced (required to pin)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="check the manifest against the tree and the split rule",
    )
    parser.add_argument(
        "--cells",
        action="store_true",
        help="print realized counts per steering cell and split",
    )
    args = parser.parse_args(argv)

    if args.verify:
        messages = verify_manifest()
        for message in messages:
            print(message, file=sys.stderr)
        return 1 if messages else 0

    if args.cells:
        for key, counts in sorted(cell_report().items()):
            bench_n = counts.get("bench", 0)
            print(f"{key}: bench {bench_n}, reserve {counts.get('reserve', 0)}")
        return 0

    names = args.problems or candidates()
    if not names:
        print("nothing to judge: no unpinned candidates", file=sys.stderr)
        return 0
    withdrawn = retired()
    if named := [n for n in names if n in withdrawn]:
        for name in named:
            entry = withdrawn[name]
            print(
                f"{name} was retired on {entry['date']} in favour of "
                f"{entry['kept']}; ids are never reused",
                file=sys.stderr,
            )
        return 2
    if args.pin and not args.provenance:
        print("--pin requires --provenance", file=sys.stderr)
        return 2

    pool.preflight()
    instruments = instrument_tasks()
    pool_ids, pool_specs = pool_material()
    rivals: dict[str, frozenset[str]] = {
        label: pool._words(contract.task) for label, contract in instruments.items()
    }
    rivals.update(pool_specs)
    rivals.update(admitted_specs())
    for name in names:
        contract_path = TASKS / "ts" / name / "contract.yaml"
        if contract_path.is_file():
            with contextlib.suppress(ContractError):
                rivals[name] = pool._words(load(contract_path).task)

    blocked = blocklist()
    admitted: list[str] = []
    failed = 0
    for name in names:
        report = check_problem(name, instruments, pool_ids, rivals, blocked)
        status = "ADMIT" if report.admitted else "REJECT"
        print(f"{status}  {name}")
        for verdict in report.verdicts:
            if not verdict.ok:
                print(f"        {verdict.check}: {verdict.detail}")
        if report.admitted:
            admitted.append(name)
        else:
            failed += 1

    if args.pin and admitted:
        added = pin(admitted, args.provenance)
        print(f"pinned {added} problem(s) into {MANIFEST.name}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
