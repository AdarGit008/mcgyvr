"""Which problems are the same problem, decided by execution rather than wording.

Issue: `#268 <https://github.com/AdarGit008/mcgyvr/issues/268>`_.

The admission gate screens candidates on task-prose overlap
(``tools/problems/admit.py``, ``JACCARD_REJECT = 0.55``). That screen tests
*wording*, and the corpus proves it insufficient: ``b094-relay-chain`` and
``b172-trace-relay`` specify one computation — walk a name-to-name chain from
``start`` until the empty string, return the names visited — under two stories,
a courier relay and a harbour night watch. Their prose Jaccard is **0.27**, half
the reject threshold.

**The method.** Write A's ``reference`` as the solution, alias A's functions to
the names B's acceptance imports, and run B's acceptance. If it passes, A's
behaviour satisfies every requirement B states. Run both directions:

===================  ==========================================================
both directions      the two are behaviourally interchangeable — a duplicate
one direction        the passing side is a *superset*: same core, more required
neither              distinct, as far as either acceptance can tell
===================  ==========================================================

Deterministic, no model, no rig time.

**What it cannot see, and this is not a footnote.** Two problems that differ only
in a *constant* fail each other's tests and read as distinct. That is exactly the
duplicate this project has already removed: ``b080-brace-fill``,
``b090-expand-markers`` and ``b168-badge-slots`` were one problem three times,
differing only in ``{name}`` / ``%name%`` / ``<name>`` (``c0686889``,
``tools/bench/retired.json``). Replayed here, ``b080``'s reference fails
``b168``'s first substantive assertion. **The prose screen caught those and this
does not; this catches ``b094``/``b172`` and the prose screen does not.** Neither
is sufficient, and a problem that is both re-skinned *and* re-parameterised is
invisible to both.

Further limits, so a reader does not take "no duplicates found" for "no
duplicates": arity is a prune, so a pair differing by an optional parameter is
never compared; multi-function tasks are aliased by sorted arity, so same-shape
helpers may be paired in the wrong order; references that raise different
exception types for one error read as distinct; and a timeout counts as a
failure.
"""

from __future__ import annotations

import argparse
import concurrent.futures as futures
import itertools
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[2]

PY_SIGNATURE = re.compile(r"def\s+(\w+)\s*\(([^)]*)\)")
TS_SIGNATURE = re.compile(r"function\s+(\w+)\s*\(([^)]*)\)")


@dataclass(frozen=True)
class Arm:
    """Where one corpus arm lives and how its acceptance is run."""

    root: Path
    signature: re.Pattern[str]
    reference: str
    accept: str
    solution: str
    command: tuple[str, ...]
    alias: str


# One entry per corpus arm. Declared as data rather than improvised per call —
# a scan whose corpus lives in the invocation is a scan the next reader has to
# be told about.
ARMS: dict[str, Arm] = {
    "bench-py": Arm(
        REPO / "tools" / "bench" / "tasks" / "py",
        PY_SIGNATURE,
        "reference.py",
        "accept.py",
        "solution.py",
        (sys.executable, "accept.py"),
        "{new} = {old}",
    ),
    "bench-ts": Arm(
        REPO / "tools" / "bench" / "tasks" / "ts",
        TS_SIGNATURE,
        "reference.ts",
        "accept.mjs",
        "solution.ts",
        ("node", "accept.mjs"),
        "export const {new} = {old};",
    ),
    "pool-py": Arm(
        REPO / "tools" / "problems" / "tasks" / "py",
        PY_SIGNATURE,
        "reference.py",
        "accept.py",
        "solution.py",
        (sys.executable, "accept.py"),
        "{new} = {old}",
    ),
}

TIMEOUT_S = 25.0


class FamilyError(Exception):
    """The corpus cannot be read, or the arm is not declared."""


@dataclass(frozen=True)
class Task:
    """One task, reduced to what pairing needs."""

    id: str
    directory: Path
    functions: tuple[tuple[int, str], ...]  # (arity, name), sorted

    @property
    def shape(self) -> tuple[int, ...]:
        """Arity per declared function. Two tasks of different shape cannot
        satisfy each other's acceptance, so this prunes before any run."""
        return tuple(arity for arity, _ in self.functions)


def load(arm: str) -> dict[str, Task]:
    """Every task on one arm, keyed by id."""
    if arm not in ARMS:
        raise FamilyError(f"unknown arm {arm!r}; declared: {', '.join(ARMS)}")
    spec = ARMS[arm]
    root = spec.root
    if not root.is_dir():
        raise FamilyError(f"{root} is not a task root")
    out: dict[str, Task] = {}
    for path in sorted(root.glob("*/contract.yaml")):
        contract = yaml.safe_load(path.read_text(encoding="utf-8"))
        found = []
        for name, args in spec.signature.findall(contract["interface"]):
            found.append((len([a for a in args.split(",") if a.strip()]), name))
        if not found:
            continue
        out[contract["id"]] = Task(contract["id"], path.parent, tuple(sorted(found)))
    return out


def satisfies(arm: str, source: Task, target: Task) -> bool:
    """Does ``source``'s reference pass ``target``'s acceptance?"""
    spec = ARMS[arm]
    with tempfile.TemporaryDirectory(prefix="mcgyvr-families-") as tmp:
        work = Path(tmp)
        body = (source.directory / spec.reference).read_text(encoding="utf-8")
        aliases = "\n".join(
            spec.alias.format(new=new, old=old)
            # `strict` holds because the pair was selected on equal shape, which
            # is arity per function — so the two tuples are the same length.
            for (_, old), (_, new) in zip(
                source.functions, target.functions, strict=True
            )
            if old != new
        )
        (work / spec.solution).write_text(f"{body}\n\n{aliases}\n", encoding="utf-8")
        shutil.copy(target.directory / spec.accept, work / spec.accept)
        try:
            done = subprocess.run(
                list(spec.command),
                cwd=work,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_S,
            )
        except (subprocess.TimeoutExpired, OSError):
            return False
        return done.returncode == 0 and "FAIL" not in done.stdout


def scan(arm: str, workers: int = 10) -> dict[str, Any]:
    """Every shape-compatible pair, both directions.

    ``families`` entries are ``[subset, superset]``: the superset's reference
    satisfies the subset's whole acceptance and not the reverse.
    """
    tasks = load(arm)
    pairs = [
        (a, b)
        for a, b in itertools.combinations(sorted(tasks), 2)
        if tasks[a].shape == tasks[b].shape
    ]
    print(
        f"{arm}: {len(tasks)} tasks, {len(pairs)} shape-compatible pairs, "
        f"{2 * len(pairs)} runs",
        file=sys.stderr,
    )
    verdicts: dict[tuple[str, str], dict[str, bool]] = {}
    with futures.ThreadPoolExecutor(max_workers=workers) as pool:
        submitted = {
            pool.submit(satisfies, arm, tasks[a], tasks[b]): (a, b, "ab")
            for a, b in pairs
        }
        submitted.update(
            {
                pool.submit(satisfies, arm, tasks[b], tasks[a]): (a, b, "ba")
                for a, b in pairs
            }
        )
        for future in futures.as_completed(submitted):
            a, b, direction = submitted[future]
            verdicts.setdefault((a, b), {})[direction] = future.result()

    duplicates: list[list[str]] = []
    families: list[list[str]] = []
    for (a, b), seen in sorted(verdicts.items()):
        forward, backward = seen.get("ab", False), seen.get("ba", False)
        if forward and backward:
            duplicates.append([a, b])
        elif forward:
            families.append([b, a])
        elif backward:
            families.append([a, b])
    return {
        "arm": arm,
        "tasks": len(tasks),
        "pairs": len(pairs),
        "duplicates": duplicates,
        "families": sorted(families),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Behavioural duplicate and family scan (#268). Cross-executes every "
            "shape-compatible pair. Reads no runs and states no rate."
        )
    )
    parser.add_argument("arms", nargs="*", default=sorted(ARMS), choices=sorted(ARMS))
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args(argv)
    print(json.dumps([scan(a, args.workers) for a in args.arms], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
