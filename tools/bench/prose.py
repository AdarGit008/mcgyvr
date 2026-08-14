"""How much of the INTERFACE section the task prose already carries.

Issue: `#266 <https://github.com/AdarGit008/mcgyvr/issues/266>`_, the material
survey; `#267 <https://github.com/AdarGit008/mcgyvr/issues/267>`_, the successor
manipulation.

``render_user_message`` emits an ``INTERFACE`` section from every contract
(``src/mcgyvr/worker/prompt.py:151``), so an ablation that removes it is only a
manipulation to the extent the prose does not say the same thing twice. This
module measures the redundancy over the corpus, before any rig time is spent.

**It reads contracts, never runs.** It states no pass rate and describes no
measurement, so it carries no mode declaration — the same footing as
``tools/power/mde.py``.

**What the numbers are and are not.** Literal substring presence is a *lower*
bound on what a model can recover: prose that says "return those words in order"
conveys ``string[]`` without containing it. So a high literal figure is strong
evidence of redundancy, and a low one is weak evidence of its absence. The
argument that does not depend on this heuristic at all is the type one, in
:func:`type_channel_is_live`.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
TASKS = HERE / "tasks"

# The two arms' signature shapes. A contract whose interface matches neither is
# counted as unparsed and reported rather than dropped: a silent skip would make
# the denominator a function of the regex.
SIGNATURES = {
    "py": re.compile(r"def\s+(\w+)\s*\(([^)]*)\)\s*->\s*([\w\[\], ]+)"),
    "ts": re.compile(r"function\s+(\w+)\s*\(([^)]*)\)\s*:\s*([\w\[\]<>, |]+)"),
}


def parameters(raw: str) -> list[str]:
    """Parameter names from one signature's argument list, types discarded."""
    out = []
    for part in raw.split(","):
        name = part.strip().split(":")[0].strip()
        if name:
            out.append(name)
    return out


def contracts(arm: str) -> Iterator[dict[str, Any]]:
    for path in sorted((TASKS / arm).glob("*/contract.yaml")):
        yield yaml.safe_load(path.read_text(encoding="utf-8"))


@dataclass
class Redundancy:
    """One arm's counts. Every field is a count of contracts, not of matches."""

    parsed: int = 0
    names_all: int = 0
    params_all: int = 0
    params_any: int = 0
    return_literal: int = 0
    unparsed: list[str] = field(default_factory=list)
    names_missing: list[str] = field(default_factory=list)


def redundancy(arm: str) -> Redundancy:
    """What fraction of each interface component the prose repeats literally."""
    pattern = SIGNATURES[arm]
    out = Redundancy()
    for contract in contracts(arm):
        found = pattern.findall(contract["interface"])
        if not found:
            out.unparsed.append(contract["id"])
            continue
        out.parsed += 1
        prose = contract["task"]
        names = [sig[0] for sig in found]
        params = [p for sig in found for p in parameters(sig[1])]
        returns = [sig[2].strip().split("[")[0] for sig in found]
        if all(name in prose for name in names):
            out.names_all += 1
        else:
            out.names_missing.append(contract["id"])
        if params and all(p in prose for p in params):
            out.params_all += 1
        if params and any(p in prose for p in params):
            out.params_any += 1
        if all(r in prose for r in returns):
            out.return_literal += 1
    return out


def type_channel_is_live(arm: str) -> bool:
    """Whether a wrong *type* in the worker's output can fail a cell at all.

    It cannot, on either arm, and this does not rest on the prose heuristic:

    * ``bench-py`` — Python annotations are inert at runtime. ``accept.py``
      imports the symbol and calls it; a wrong annotation changes nothing about
      whether the assertions hold.
    * ``bench-ts`` — no ``tsconfig.json`` is staged and the repository has none,
      so ``tsc --noEmit`` never runs (#262). No rung reads a type.

    So of the three things ``INTERFACE`` states — the name, the types, and the
    arity/order — the middle one cannot move a pass rate. It is stated as a
    function rather than a comment so that a future staged type checker makes
    this return ``True`` and the argument has to be re-made.
    """
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "How much of the INTERFACE section the prose already carries (#266). "
            "Reads contracts only; states no rate and describes no run."
        )
    )
    parser.parse_args(argv)

    print("## INTERFACE redundancy with the task prose, literal matches only\n")
    print("| arm | parsed | fn names | all params | any param | return type |")
    print("|---|---:|---:|---:|---:|---:|")
    for arm in SIGNATURES:
        t = redundancy(arm)
        n = t.parsed
        print(
            f"| bench-{arm} | {n} | {100 * t.names_all / n:.1f}% "
            f"| {100 * t.params_all / n:.1f}% "
            f"| {100 * t.params_any / n:.1f}% "
            f"| {100 * t.return_literal / n:.1f}% |"
        )
    print()
    for arm in SIGNATURES:
        t = redundancy(arm)
        if t.unparsed:
            print(f"- bench-{arm}: {len(t.unparsed)} unparsed — {t.unparsed}")
        if t.names_missing:
            print(
                f"- bench-{arm}: prose omits a declared name in "
                f"{len(t.names_missing)} — {t.names_missing}"
            )
        print(
            f"- bench-{arm}: a wrong type can fail a cell: {type_channel_is_live(arm)}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
