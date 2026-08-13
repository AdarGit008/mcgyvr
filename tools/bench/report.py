"""The condition matrix's report: one table, every cell, both outcome axes.

Issue: `#113 <https://github.com/AdarGit008/mcgyvr/issues/113>`_ — *"a pass-rate
report per condition, carrying n, model, rig and conditions"*, and *"the report
must carry the interaction term — combined effect minus the sum of singles"*.

A run directory holds **one cell**. This reads a set of them and lays them
beside each other, which is the only thing a condition matrix is for.

**What it refuses to do.** Two things, both because a comparison that is not
comparable is worse than no comparison:

* it will not state a rate for a cell whose manifest cannot say which model,
  which rig and which bar produced it;
* it will not lay two cells beside each other unless they agree on model, rig,
  serving build, tier and scoring rungs. #189 folded a backend change into a
  weights contrast, and ADR-0024 exists because two runs differed by an ollama
  patch release that nothing on disk recorded. The check is cheap and the
  failure it prevents has already happened twice.

**The interaction term.** Levers are *comparable but not addable*: two that fix
the same three tasks give +3, not +6. For a cell naming more than one lever the
report prints combined-minus-the-sum-of-singles, and prints **absent** rather
than zero when a single-lever arm is missing from the run — a gap in the matrix
is not evidence that two levers are additive.

**The reproducibility bound.** Every table states the deviation two identical
runs may differ by, and a contrast at or inside it is marked as the instrument
rather than the lever. When no null has been measured for this model, at this
tier, under this bar and on this serving build, the report says **not declared**
and leaves every delta unqualified — it does not fall back to zero, to another
tier's number, or to silence. The declaration is ``reproducibility.json``; the
number that fills it is #231's.

    uv run --no-sync python tools/bench/report.py records/measurements/<run>/...
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent


def _by_path(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


matrix = _by_path("bench_matrix_report", HERE / "matrix.py")

# The facts every cell in one table must agree on. A difference in any of them
# is a second variable inside a contrast that claims to vary one thing.
#
# The first five were the whole list, and that was demonstrably too few: a
# manifest mutated to a 4x smaller output cap, a different temperature, a
# different wire protocol and an emptied task manifest produced a byte-identical
# report — the -3.1pp headline published unchanged across a different corpus.
# A guard that names five fields does not refuse the sixth; it permits it
# silently, which reads as having checked.
COMPARABLE = (
    "model",
    "endpoint",
    "serving_build",
    "tier",
    "gate_rungs",
    "max_output_tokens",
    "greedy_temperature",
    "protocol",
    "tasks_sha256",
)

REPRO_FILE = HERE / "reproducibility.json"

# What a declared bound must match before it may describe a run. ADR-0019 D2 —
# the null is measured per target tier and does not transfer up the ladder;
# ADR-0024 — a serving build nothing recorded has already moved results twice;
# and a bar that scores differently produces a different null, which is why the
# rungs are in the key rather than in the prose beside it.
BOUND_MATCH = ("model", "tier", "gate_rungs", "serving_build")
BOUND_FIELDS = (
    *BOUND_MATCH,
    "bound_pp",
    "flips",
    "cells",
    "runs",
    "issue",
    "measured",
)

MARK = "†"


class ReportError(Exception):
    """The cells cannot be laid beside each other, or one cannot be described."""


def read_cell(directory: Path) -> dict[str, Any]:
    """One cell: its manifest, its rows, and the two axes read off them."""
    manifest_path = directory / "run.json"
    rows_path = directory / "results.jsonl"
    if not manifest_path.is_file() or not rows_path.is_file():
        raise ReportError(f"{directory} is not a run directory")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    # `serving_build` is absent from this list on purpose — see
    # measure.REQUIRED_PROVENANCE. An unknown build is a recorded fact; two
    # *different* builds in one table is the confound, and `require_comparable`
    # catches that because None and "0.32.5" are not the same value.
    missing = [
        k for k in ("model", "endpoint", "tier", "condition") if not manifest.get(k)
    ]
    if missing:
        raise ReportError(
            f"{directory} cannot say what produced it (missing "
            f"{', '.join(missing)}); a rate that names no model on no rig "
            "names nothing"
        )
    rows = [
        json.loads(line)
        for line in rows_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    greedy = [r for r in rows if r.get("arm") == "greedy"]
    scored = [
        r
        for r in greedy
        if isinstance(r.get("prompt_tokens"), (int, float))
        and isinstance(r.get("completion_tokens"), (int, float))
    ]
    passed = sum(1 for r in greedy if r.get("passed"))
    return {
        "condition": manifest["condition"],
        "manifest": manifest,
        "n": len(greedy),
        "passed": passed,
        "rate": passed / len(greedy) if greedy else 0.0,
        "prompt_tokens": (
            sum(r["prompt_tokens"] for r in scored) / len(scored) if scored else None
        ),
        "completion_tokens": (
            sum(r["completion_tokens"] for r in scored) / len(scored)
            if scored
            else None
        ),
        "rejected_by": _rejection_counts(greedy),
    }


def _rejection_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        rung = row.get("rejected_by")
        if rung:
            counts[rung] = counts.get(rung, 0) + 1
    return counts


def require_comparable(cells: list[dict[str, Any]]) -> None:
    """Refuse a table whose cells differ in anything but their condition."""
    for key in COMPARABLE:
        seen = {json.dumps(c["manifest"].get(key), sort_keys=True) for c in cells}
        if len(seen) > 1:
            raise ReportError(
                f"these cells differ in {key!r}: {', '.join(sorted(seen))}. "
                "A contrast between them would vary two things and attribute "
                "the result to one — the defect #189 shipped and ADR-0024 "
                "closes. Re-run the odd cell, or report them separately."
            )


def load_bounds(path: Path | None = None) -> list[dict[str, Any]]:
    """The declared reproducibility bounds, each held to naming its own subject.

    An empty list is a state rather than a gap — it means no null has been
    measured yet, and the report says so. What is refused is a *partial* bound:
    one that cannot say what it was measured on, or from which two runs, cannot
    be re-derived and so is an assertion wearing a number's clothes.
    """
    source = path if path is not None else REPRO_FILE
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ReportError(f"no reproducibility declaration at {source}") from None
    except json.JSONDecodeError as exc:
        raise ReportError(f"{source} is not JSON: {exc}") from None
    bounds = raw.get("bounds", [])
    for entry in bounds:
        missing = [k for k in BOUND_FIELDS if k not in entry]
        if missing:
            raise ReportError(
                f"a reproducibility bound does not state {', '.join(missing)}; a "
                "bound that cannot name its model, tier, bar, build and the two "
                "runs it came from cannot be re-derived, and an unre-derivable "
                "deviation is not a measurement"
            )
    return bounds


def declared_bound(
    manifest: dict[str, Any], bounds: list[dict[str, Any]]
) -> tuple[dict[str, Any] | None, str]:
    """The bound describing this run, or the reason none does.

    The reason is returned rather than raised: a run with no null is a normal
    state of the world — #231 supplies the number and the bench exists before it
    — and the report's job is to say so in the table, not to refuse to print one.
    """
    for entry in bounds:
        if all(entry[k] == manifest.get(k) for k in BOUND_MATCH):
            return entry, ""
    near = [
        e
        for e in bounds
        if e["model"] == manifest.get("model") and e["tier"] == manifest.get("tier")
    ]
    if near:
        differs = [k for k in BOUND_MATCH if near[0][k] != manifest.get(k)]
        return None, (
            f"the bound declared for this model at this tier was measured under "
            f"a different {', '.join(differs)}, and a null does not transfer "
            f"across that (ADR-0019 D2, ADR-0024)"
        )
    return None, (
        f"no null has been measured for {manifest.get('model')} at tier "
        f"{manifest.get('tier')}"
    )


def render(cells: list[dict[str, Any]]) -> str:
    """The table, its contrasts, and the interaction term for every combination."""
    if not cells:
        raise ReportError("no cells")
    require_comparable(cells)
    loaded = matrix.load()
    bound, no_bound_because = declared_bound(cells[0]["manifest"], load_bounds())
    first = cells[0]["manifest"]
    by_condition = {c["condition"]: c for c in cells}
    rate = {c["condition"]: c["rate"] for c in cells}

    rungs = first.get("gate_rungs")
    bar = (
        "acceptance command only (pre-#113 scorer)"
        if not rungs
        else "Gate.run [" + ", ".join(rungs) + "]"
    )
    lines = [
        "# Condition matrix",
        "",
        f"**{first['model']}** on {_redact(first['endpoint'])} "
        f"(build {first.get('serving_build') or 'unknown'}), "
        f"tier `{first['tier']}`",
        "",
        f"- scored by: {bar}",
        "- mode: **single-tier** — one model, no escalation, so every figure "
        "below is that tier's own and not the ladder's",
        f"- cells: {len(cells)} of {len(loaded.cells)} declared in "
        "`tools/bench/matrix.json`",
        _reproducibility_line(bound, no_bound_because),
        "",
        "| condition | levers | n | pass | rate | vs baseline | prompt | completion |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]

    baseline = loaded.baseline.id
    base_rate = rate.get(baseline)
    inside_null = False
    for cell in sorted(cells, key=lambda c: (len(_levers(loaded, c)), c["condition"])):
        name = cell["condition"]
        levers = "+".join(_levers(loaded, cell)) or "—"
        if base_rate is None or name == baseline:
            delta = "—"
        else:
            pp = (cell["rate"] - base_rate) * 100
            within = bound is not None and abs(pp) <= bound["bound_pp"]
            inside_null = inside_null or within
            delta = f"{pp:+.1f}pp" + (MARK if within else "")
        prompt = (
            "—" if cell["prompt_tokens"] is None else f"{cell['prompt_tokens']:.0f}"
        )
        completion = (
            "—"
            if cell["completion_tokens"] is None
            else f"{cell['completion_tokens']:.0f}"
        )
        lines.append(
            f"| `{name}` | {levers} | {cell['n']} | {cell['passed']} | "
            f"{cell['rate'] * 100:.1f}% | {delta} | {prompt} | {completion} |"
        )

    if inside_null and bound is not None:
        lines.extend(
            [
                "",
                f"{MARK} **inside the declared reproducibility bound** "
                f"(±{bound['bound_pp']:.1f}pp). Two identical runs of this "
                "instrument move this far, so the contrast is the instrument and "
                "not the lever.",
            ]
        )

    if base_rate is None:
        lines.extend(
            [
                "",
                f"**No baseline cell (`{baseline}`) in this run**, so no contrast "
                "and no interaction term is stated: every effect the matrix "
                "reports is measured against the baseline, and it is not here.",
            ]
        )
        return "\n".join(lines)

    lines.extend(_interactions(loaded, by_condition, rate, bound))
    lines.extend(_rejections(cells))
    return "\n".join(lines)


def _reproducibility_line(bound: dict[str, Any] | None, because: str) -> str:
    """State the deviation two identical runs may differ by, or that none is known.

    #113's eighth acceptance item, and the half of it this issue owns: the report
    declares the property, #231's null calibration supplies the number. The
    unqualified case is written to be read as the warning it is — a delta smaller
    than an undeclared drift is not a small effect, it is an unknown one.
    """
    if bound is None:
        return (
            f"- reproducibility: **not declared** — {because} (#231). Every "
            "`vs baseline` figure below is unqualified: nothing here states how "
            "much of one is the instrument's own drift"
        )
    runs = ", ".join(f"`{r}`" for r in bound["runs"])
    return (
        f"- reproducibility: **±{bound['bound_pp']:.1f}pp** — {bound['flips']} of "
        f"{bound['cells']} paired cells changed verdict across two identical runs "
        f"({runs}, measured {bound['measured']}, #{bound['issue']}). A contrast "
        f"marked {MARK} is inside it"
    )


def _levers(loaded: Any, cell: dict[str, Any]) -> list[str]:
    try:
        return [lever.id for lever in loaded.cell(cell["condition"]).levers]
    except matrix.MatrixError:
        return []


def _interactions(
    loaded: Any,
    by_condition: dict[str, Any],
    rate: dict[str, float],
    bound: dict[str, Any] | None = None,
) -> list[str]:
    """Combined effect minus the sum of the singles, per multi-lever cell."""
    multi = [
        name
        for name in by_condition
        if name in loaded.cells and len(loaded.cell(name).levers) > 1
    ]
    if not multi:
        return []
    lines = ["", "## Interaction", ""]
    if bound is not None:
        lines.extend(
            [
                f"The ±{bound['bound_pp']:.1f}pp bound above qualifies **one** "
                "contrast. An interaction term is a difference of differences and "
                "carries the drift of every arm inside it, so that figure is a "
                f"floor on its noise rather than a bound on it — no term below is "
                f"marked {MARK}.",
                "",
            ]
        )
    for name in sorted(multi):
        term = matrix.interaction(loaded, name, rate)
        if term is None:
            lines.append(
                f"- `{name}`: **not stated** — this run does not carry a "
                "single-lever cell for every lever in it, and a missing arm is "
                "not evidence that the levers are additive."
            )
            continue
        singles = ", ".join(
            f"{k} {v * 100:+.1f}pp" for k, v in sorted(term.singles.items())
        )
        verdict = (
            "additive on this set"
            if term.additive
            else ("overlapping" if term.term < 0 else "super-additive")
        )
        lines.append(
            f"- `{name}`: combined {term.combined * 100:+.1f}pp against "
            f"singles ({singles}) — **interaction {term.term * 100:+.1f}pp**, "
            f"{verdict}."
        )
    return lines


def _rejections(cells: list[dict[str, Any]]) -> list[str]:
    """Which rung did the rejecting, per condition — absent on a pre-#113 run."""
    if not any(c["rejected_by"] for c in cells):
        return []
    lines = ["", "## What rejected, by rung", "", "| condition | rungs |", "|---|---|"]
    for cell in sorted(cells, key=lambda c: c["condition"]):
        counts = cell["rejected_by"]
        body = ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "—"
        lines.append(f"| `{cell['condition']}` | {body} |")
    return lines


def _redact(endpoint: str) -> str:
    """Hosts are configuration; a credential in a URL is never printed."""
    if "@" not in endpoint:
        return endpoint
    scheme, _, rest = endpoint.partition("://")
    return f"{scheme}://<redacted>@{rest.partition('@')[2]}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "cells",
        nargs="+",
        type=Path,
        help="one run directory per condition — each holding run.json and "
        "results.jsonl",
    )
    args = parser.parse_args()
    try:
        print(render([read_cell(d) for d in args.cells]))
    except ReportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
