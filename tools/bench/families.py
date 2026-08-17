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

**Containment is directed, and the prune has to be too.** A source satisfies a
target only if it supplies every function the target's acceptance imports, so
the comparable direction is the one where the target's *arity multiset* is
contained in the source's — not the one where the two are equal. Requiring
equality was this scan's own blind spot and it cost two known families:
``b333-pace-split`` declares ``pace_list/1`` and ``pace_of/2``, and
``b302-stock-take`` and ``b277-fuel-legs`` each declare one function of arity 2,
so shape equality never compared them and ``b302 ⊂ b277 ⊂ b333`` went unseen
(#268, 2026-08-17). Pairs are therefore generated as directed ordered pairs
under containment, which is why the run count is not twice the pair count.

Further limits, so a reader does not take "no duplicates found" for "no
duplicates": a pair differing by an *optional* parameter has different arities
and is still never compared; where a source declares several functions of one
arity, the alias picks by sorted order, so same-arity helpers may be paired in
the wrong order; references that raise different exception types for one error
read as distinct; and a timeout counts as a failure.
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
from collections import Counter
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
    "pool-ts": Arm(
        REPO / "tools" / "problems" / "tasks" / "ts",
        TS_SIGNATURE,
        "reference.ts",
        "accept.mjs",
        "solution.ts",
        ("node", "accept.mjs"),
        "export const {new} = {old};",
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
        """Arity per declared function, sorted. Reported, not compared — see
        :func:`covers` for the prune, which is containment rather than
        equality."""
        return tuple(arity for arity, _ in self.functions)

    @property
    def arities(self) -> Counter[int]:
        """How many functions of each arity this task declares."""
        return Counter(arity for arity, _ in self.functions)


def covers(source: Task, target: Task) -> bool:
    """Can ``source``'s reference stand in for every function ``target``'s
    acceptance imports?

    Only arity is checked, because that is all the alias can honour. The
    relation is *directed*: a task declaring a helper as well as the function
    under test covers one that declares the function alone, and not the
    reverse. Equality — what this scan required until 2026-08-17 — is the
    special case where both hold, and requiring it hid ``b302 ⊂ b277 ⊂ b333``.
    """
    have = source.arities
    return all(have[arity] >= count for arity, count in target.arities.items())


def aliases(source: Task, target: Task) -> list[tuple[str, str]]:
    """``(source name, target name)`` per function the target imports.

    Matched by arity, each source function spent at most once. Where the source
    declares several of one arity the choice is by sorted order and may be the
    wrong one — the false negative the module docstring names.

    Defined only where :func:`covers` holds. Asked for a binding it cannot make,
    it refuses: binding fewer names than the acceptance imports would produce a
    NameError inside the run and read as "these two are distinct", which is the
    silent false negative this whole scan exists to remove.
    """
    spare: dict[int, list[str]] = {}
    for arity, name in source.functions:
        spare.setdefault(arity, []).append(name)
    out = []
    for arity, name in target.functions:
        if not spare.get(arity):
            raise FamilyError(
                f"{source.id} cannot stand in for {target.id}: no unspent "
                f"function of arity {arity} for {name!r}. Pair on `covers` "
                "before aliasing."
            )
        out.append((spare[arity].pop(0), name))
    return out


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
        bound = "\n".join(
            spec.alias.format(new=new, old=old)
            # The pair was selected by `covers`, so every function the target
            # imports has a source function of its arity to bind to.
            for old, new in aliases(source, target)
            if old != new
        )
        (work / spec.solution).write_text(f"{body}\n\n{bound}\n", encoding="utf-8")
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
    """Every comparable pair, in each direction :func:`covers` allows.

    ``families`` entries are ``[subset, superset]``: the superset's reference
    satisfies the subset's whole acceptance and not the reverse. ``runs`` is
    not twice ``pairs`` — containment is directed, so a pair whose covering
    holds one way only is executed once.
    """
    tasks = load(arm)
    runs = [
        (source, target)
        for source, target in itertools.permutations(sorted(tasks), 2)
        if covers(tasks[source], tasks[target])
    ]
    pairs = {tuple(sorted(run)) for run in runs}
    print(
        f"{arm}: {len(tasks)} tasks, {len(pairs)} comparable pairs, {len(runs)} runs",
        file=sys.stderr,
    )
    verdicts: dict[tuple[str, str], bool] = {}
    with futures.ThreadPoolExecutor(max_workers=workers) as pool:
        submitted = {
            pool.submit(satisfies, arm, tasks[source], tasks[target]): (source, target)
            for source, target in runs
        }
        for future in futures.as_completed(submitted):
            verdicts[submitted[future]] = future.result()

    duplicates: list[list[str]] = []
    families: list[list[str]] = []
    for a, b in sorted(pairs):
        # `a satisfies b` means a's reference passes b's acceptance, so a is the
        # superset: it meets everything b requires and possibly more.
        forward, backward = verdicts.get((a, b), False), verdicts.get((b, a), False)
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
        "runs": len(runs),
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
