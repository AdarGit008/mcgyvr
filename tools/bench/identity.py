"""Run identity — one block, four groups, and the three states a field can be in.

ADR-0027 — *run identity is one block, and an unreadable field is a refusal* —
and issue `#265 <https://github.com/AdarGit008/mcgyvr/issues/265>`_.

**Why this is a module and not a tuple in three files.** Five lists disagreed
about what identity is: ``report.COMPARABLE`` (11 keys), ``report.read_cell``'s
required set (4), ``report.BOUND_MATCH`` (4), the breadth resume drift check
(every key it writes) and the bundle resume drift check (6). Three lanes were
queued to edit the first of them — #256 for the model, #262 for the bar, #231
check 2 for the condition — and the comparability key is a *single tuple*, so
three lanes each adding one field is three chances to name one field short. A
guard that names five fields does not refuse the sixth; it permits it silently,
which reads as having checked.

**The defect this closes.** ``require_comparable`` compared
``manifest.get(key)`` across cells, so a key absent from *every* cell yielded
one value and passed::

    model         {'"qwen2.5-coder:1.5b"'}  pass
    tasks_sha256  {'"aaa"'}                 pass
    model_sha256  {'null'}                  pass   <- nothing writes this field

Adding the three digests to a failing-open guard would have changed no behaviour
at all while reading, to every later reader, as having checked. So the shape and
the refusal land together: **a field the guard cannot read is a refusal, not a
match** (ADR-0027 D3).

**What is recorded and what is keyed are different questions.** #276 settled
that: recording is unconditional, and a field enters the *key* only once
perturbation shows it flips more verdicts than the declared bound. So
:data:`GROUPS` is what a run records; :data:`KEY` is the admitted subset, and it
does not widen because a field became available. The four bound-key fields —
model, tier, bar, build — are admitted by construction (#276 corollary 3),
because the rule cannot hold ``model`` fixed while varying ``model``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Literal

__all__ = [
    "ABSENT",
    "BACKFILLED",
    "BOUND_MATCH",
    "BOUND_MATCH_PENDING",
    "CONTRAST",
    "GROUPS",
    "KEY",
    "NO_FINGERPRINT",
    "OBTAINED",
    "PENDING",
    "RECORDED",
    "REFUSED",
    "VERIFIED",
    "IdentityError",
    "digest",
    "drift",
    "inventory",
    "require_comparable",
    "state",
    "tag",
    "unfingerprinted",
]


class IdentityError(Exception):
    """Two records cannot be laid beside each other, or one cannot be read."""


# --- the three states (ADR-0027 D2) -----------------------------------------
#
# One rule, all four groups, so a reader can tell "not recorded" from "recorded
# as unknown" from "the endpoint could not say" — and no sentinel string, which
# would be a fourth state indistinguishable from a legitimate value.
State = Literal["obtained", "refused", "absent"]

OBTAINED: State = "obtained"  # a value: the world was asked and answered
REFUSED: State = "refused"  # null + a reason: asked, and it would not say
ABSENT: State = "absent"  # no key: the record predates the contract


# --- the four groups (ADR-0027 D1) ------------------------------------------
#
# ADR-0026 named three fields — the bar, the model and the condition. It was one
# short. The SERVER is the missing group and it has already cost a contrast:
# the scaffold ablation ran the 3B against srv1 on ollama 0.32.4 and the 7B
# against srv2 on 0.32.5, and nothing on disk said so.
#
# A name here is what the record CARRIES, not what the guard checks. Fields
# nothing writes yet are listed on purpose: the fan-out that computes a digest
# adds a writer, and flips one entry in KEY below, rather than inventing a field
# name of its own three months from now.
GROUPS: dict[str, tuple[str, ...]] = {
    # What answered. The tag is mutable and cannot be pinned — ollama's `@digest`
    # grammar exists in types/model/name.go and the parser discards it — so
    # identity is captured at request time or not at all.
    "model": (
        "model",
        "model_sha256",
        "quantization",
        "context_length",
        "vocabulary_sha256",
        "merges_sha256",
    ),
    # What it was asked, as sent. `bundle_sha256` hashes the SYSTEM prompt while
    # an ablation edits the USER message, so `prompt_sha256` is the field that
    # makes a condition content rather than a name.
    "request": (
        "protocol",
        "tier",
        "condition",
        "prompt_sha256",
        "bundle_sha256",
        "tasks_sha256",
        "draws",
        "greedy_temperature",
        "sampled_temperature",
        "max_output_tokens",
        "seed",
    ),
    # What served it. Observed, never assumed: two builds are two instruments
    # (ADR-0024), and concurrency decides whether greedy is reproducible at all.
    "server": (
        "endpoint",
        "serving_build",
        "template_sha256",
        "concurrency",
    ),
    # What judged it. Five rung names are byte-identical across 328 ruff rules
    # and 66 eslint, so the bar is hashed as the RESOLVED rule list. `round` and
    # `product_sha256` sit here because the revision they pin includes the
    # scorer.
    "bar": (
        "gate_rungs",
        "gate_semantic",
        "bar_sha256",
        "mode",
        "round",
        "product_sha256",
    ),
}

RECORDED: tuple[str, ...] = tuple(f for fields in GROUPS.values() for f in fields)


# The axis a table is allowed to vary in. Named in the call rather than assumed,
# so a sweep that contrasts something else says which (ADR-0027 D5).
CONTRAST = "condition"


# The admitted subset. Every entry here is either one of the four bound-key
# fields (admitted by construction, #276 corollary 3) or was in
# `report.COMPARABLE` before this module existed — a manifest mutated in a 4x
# smaller output cap, a different temperature, a different wire protocol and an
# emptied task manifest once produced a byte-identical report.
#
# It does not widen because a field became writable. #276's rule admits, and
# nothing else does.
KEY: tuple[str, ...] = (
    "model",
    "endpoint",
    "serving_build",
    "tier",
    "gate_rungs",
    "max_output_tokens",
    "greedy_temperature",
    "protocol",
    "tasks_sha256",
    "round",
    "product_sha256",
)


# Recorded, not keyed. Each waits on a perturbation run under #276's rule, or on
# a writer. Listed so the gap is a state rather than an oversight — this is the
# list a reader should hold this module to when the fan-out lands.
PENDING: tuple[str, ...] = tuple(f for f in RECORDED if f not in KEY and f != CONTRAST)


# What a declared reproducibility bound must match before it may describe a run.
# ADR-0019 D2 — the null is measured per target tier and does not transfer up the
# ladder; ADR-0024 — a serving build nothing recorded has already moved results
# twice; a bar that scores differently produces a different null.
#
# `tier` here is the LANGUAGE ARM — `bench-py` / `bench-ts`, as every run.json
# records it — and the axis the product ladder calls a tier is `model` (#289).
# D2's "per target tier" is therefore discharged by `model`, with language as an
# additional split.
#
# The matching note on `mcgyvr.config.Tier` is DEFERRED, not written: `src/mcgyvr`
# is inside `product.SURFACE`, so a docstring there moves `product_sha256` and
# re-baselines the open round. It lands with the identity range #276's sequencing
# already schedules before `r2` opens. Until then a reader of the ladder sense
# meets no cross-reference, which is why this one states both senses in full
# rather than pointing at a file.
BOUND_MATCH: tuple[str, ...] = ("model", "tier", "gate_rungs", "serving_build")

# Declared in the contract, not yet enforced here. ADR-0027 D9 put `cells` in
# the matching key — a rate keyed on everything but its own denominator
# transfers to subsets it never saw — and `reproducibility.json`'s `matching`
# prose already states five fields against this tuple's four.
#
# Listed rather than left implicit for the reason `PENDING` exists above: a gap
# a reader can see is a state, and a gap only one of two documents mentions is
# an oversight waiting to be satisfied twice. #231 owns closing it, and #289
# measured what it costs to honour — nothing, because a subset of an
# already-paired set is itself already paired, so a subset bound is a
# recomputation over verdicts on disk rather than a new dispatch.
#
# **It is not pending the way `PENDING` is, and promoting it is not the same
# move.** Every entry in `PENDING` is a recorded *manifest* field awaiting
# admission to `KEY`. `cells` is a field of a *bound record* — the denominator
# the bound was measured over — and appears in neither `KEY` nor `RECORDED`,
# because a run manifest does not carry it. So `BOUND_MATCH` gaining `cells`
# would break `set(BOUND_MATCH) <= set(KEY)`, which
# `tests/test_bench_identity.py` asserts today. Whoever closes D9 decides that
# invariant's fate first: either the bound key stops being a subset of the run
# key, or `cells` becomes a recorded field of the run it describes.
BOUND_MATCH_PENDING: tuple[str, ...] = ("cells",)


def digest(value: Any) -> str:
    """The hashing convention, in one place so three lanes cannot invent three.

    Canonical JSON — sorted keys, no incidental whitespace, UTF-8 — then sha256,
    hex, whole. Not truncated: a short digest saves bytes in a file that is
    already megabytes of rows, and buys a collision argument nobody wants to have
    about an identity field.

    Computed here and never passed in (ADR-0027 D4). ``--condition`` was a
    caller-supplied identity field, it reached dispatch and never ``record_run``,
    and eight manifests described a render nobody had run.
    """
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def state(manifest: dict[str, Any], field: str) -> State:
    """Which of the three states this manifest is in for this field."""
    if field not in manifest:
        return ABSENT
    return REFUSED if manifest[field] is None else OBTAINED


def unfingerprinted(
    manifest: dict[str, Any], fields: tuple[str, ...] = KEY
) -> list[str]:
    """The keyed fields this manifest cannot answer, in declaration order.

    Empty is the `verified` tag's precondition (ADR-0027 D8) — necessary and not
    sufficient, since a field can be recorded and wrong.
    """
    return [f for f in fields if state(manifest, f) != OBTAINED]


# What a record must name before it is worth any tag at all — a pass rate that
# names no model on no rig names nothing.
#
# `report.read_cell` requires a fourth, `condition`, and this deliberately does
# not: a bench cell without one cannot be placed in a matrix, but 96 of the
# manifests on disk are rig sweeps that never had a condition to name. Folding
# "not a bench run" into "unidentifiable" would tag most of the corpus untrusted
# for a field its instrument does not have.
NAMES_ITS_SUBJECT: tuple[str, ...] = ("model", "endpoint", "tier")

VERIFIED = "verified"  # every keyed field obtained
BACKFILLED = "backfilled"  # names its subject, fingerprint incomplete
NO_FINGERPRINT = "no_fingerprint"  # cannot say what produced it


def tag(manifest: dict[str, Any]) -> str:
    """The migration tag for one record (ADR-0027 D8), computed and never typed.

    Three tags, and the middle one is the one that needs its meaning stated,
    because its name invites the wrong reading:

    * ``verified`` — ran with a full fingerprint. It means **everything was
      recorded**. It does not mean the run reproduces, and nothing in this
      project may use it that way: greedy decoding is not deterministic under
      continuous batching, so re-run-and-compare is a positive signal only.
    * ``backfilled`` — the record names its subject and its fingerprint is
      incomplete. **Not clean, and never read.** It is a dormant insurance label
      against a future that finds a use for these rows, not a promotion path.
    * ``no_fingerprint`` — the record cannot say what produced it. Never
      trusted, no promotion path.

    Nothing is re-run to move a record between tags. Rig time goes to new runs
    done properly rather than to repairing old ones, so CLM-0011 stays dark until
    a fresh measurement and #256 waits for that rather than for a promotion.

    **The tag is a function of today's key, and moves when the key does.** Six
    records are ``verified`` against :data:`KEY` as it stands, and :data:`KEY`
    does not yet contain the three digests ADR-0026 asked for because nothing
    writes them. When the fan-out adds a writer and #276's rule admits the field,
    those six become ``backfilled`` — which is why this is computed on read
    rather than stamped into the manifests. A stamped tag would have claimed a
    fingerprint the run never carried.
    """
    if any(state(manifest, f) != OBTAINED for f in NAMES_ITS_SUBJECT):
        return NO_FINGERPRINT
    return VERIFIED if not unfingerprinted(manifest) else BACKFILLED


def drift(
    first: dict[str, Any], second: dict[str, Any], fields: tuple[str, ...] = KEY
) -> list[str]:
    """Keyed fields on which two records disagree — the resume check's question.

    Absence is not agreement here either: a manifest that does not carry a field
    is not thereby the same as one that does. The one exception a caller may
    make is ADR-0024's — a field that did not exist when the directory was
    written is adopted forward by the caller *before* this is called, so the
    adoption is visible at the call site rather than hidden in a comparison.
    """
    return sorted(
        f
        for f in fields
        if state(first, f) != state(second, f) or first.get(f) != second.get(f)
    )


def require_comparable(
    manifests: list[dict[str, Any]],
    contrast: str = CONTRAST,
    allow_unfingerprinted: bool = False,
) -> None:
    """Refuse a table whose records differ in anything but the contrast axis.

    Two refusals, and the second is the one this module was written for:

    * **they differ** in a keyed field — a contrast between them would vary two
      things and attribute the result to one, which is the defect #189 shipped
      and ADR-0024 closes;
    * **a keyed field is not obtained** — absent, or ``null``. Two unknowns are
      not a match. An endpoint that would not name its build might have named
      two different builds, and a record written before the contract cannot say
      anything at all.

    ``allow_unfingerprinted`` exists so the second can be waived, and it is a
    parameter rather than a default because ADR-0027 D3 permits the waiver only
    where it is explicit. Reading pre-contract records is a legitimate thing to
    want; doing it without saying so is what produced a shipped -3.1pp headline
    across a corpus nobody had compared.

    **A single record is never refused for absence.** The defect is two records
    agreeing *by shared absence*, and one record agrees with nothing. This keeps
    ADR-0024's consequence intact — an endpoint that will not name its build
    records ``null``, and a rate from it is still a rate — while withdrawing the
    half of it that does not survive: ``null`` is a recorded fact about a run and
    is **not** a match between two of them, because an endpoint that would not
    answer twice may have answered differently twice. The caller states what it
    could not check either way; :func:`unfingerprinted` is what it asks.
    """
    if contrast in KEY:
        raise IdentityError(
            f"{contrast!r} is both the contrast axis and a keyed field, so this "
            "table would refuse the difference it exists to show"
        )
    if not manifests:
        raise IdentityError("no records to compare")

    if len(manifests) > 1 and not allow_unfingerprinted:
        for index, manifest in enumerate(manifests):
            missing = unfingerprinted(manifest)
            if missing:
                detail = ", ".join(f"{f} ({state(manifest, f)})" for f in missing)
                raise IdentityError(
                    f"record {index} cannot answer {detail}. Absence is not "
                    "agreement: a field no record carries compared equal under "
                    "the old guard, which read as having checked. Tag the run "
                    "and pass allow_unfingerprinted=True to read it under the "
                    "old key deliberately (ADR-0027 D3, D8)."
                )

    for field in KEY:
        seen = {json.dumps(m.get(field), sort_keys=True) for m in manifests}
        if len(seen) > 1:
            raise IdentityError(
                f"these records differ in {field!r}: {', '.join(sorted(seen))}. "
                "A contrast between them would vary two things and attribute "
                "the result to one — the defect #189 shipped and ADR-0024 "
                "closes. Re-run the odd record, or report them separately."
            )

    # Within one condition the prompt as sent must not move (ADR-0027 D6). This
    # needs no admission experiment because the contrast is *inside* the axis
    # rather than across it: two cells that name the same condition and were
    # sent different bytes are mislabelled, whatever the effect size turns out
    # to be. Prompt wording is the largest effect in the surveyed literature —
    # up to 76pp — and until the fan-out lands, `bundle_sha256` hashes the
    # system half only, so this check is weaker than it reads.
    for field in ("prompt_sha256", "bundle_sha256"):
        present = [m for m in manifests if state(m, field) == OBTAINED]
        by_condition: dict[Any, set[str]] = {}
        for manifest in present:
            by_condition.setdefault(manifest.get(contrast), set()).add(
                str(manifest[field])
            )
        for condition, values in sorted(
            by_condition.items(), key=lambda kv: str(kv[0])
        ):
            if len(values) > 1:
                raise IdentityError(
                    f"two records name {contrast} {condition!r} and differ in "
                    f"{field!r}: {', '.join(sorted(values))}. One condition was "
                    "rendered two ways, so the label is not the experiment."
                )


def inventory(root: Path) -> list[tuple[Path, str, list[str]]]:
    """Every manifest under ``root``, its tag, and what it could not answer.

    Read rather than written. A tag committed into a file goes stale the moment
    a record or the key moves, and a stale tag is worse than none — it is a
    claim about a run that nothing re-derives. The migration ADR-0027 D8 decides
    is therefore *tagging in place*, with this as the tag.

    Records that are not machine-written manifests are skipped rather than
    tagged: three of the directories on disk hold hand-authored evidence whose
    ``protocol`` is a paragraph of prose, and they are excluded by shape rather
    than by an exception list that would need maintaining.
    """
    found: list[tuple[Path, str, list[str]]] = []
    for path in sorted(root.glob("**/run.json")):
        try:
            recorded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(recorded, dict) or not isinstance(
            recorded.get("protocol"), str
        ):
            continue
        found.append((path, tag(recorded), unfingerprinted(recorded)))
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "records" / "measurements",
        help="the directory of run directories to tag (default: records/measurements)",
    )
    args = parser.parse_args()
    found = inventory(args.root)
    if not found:
        print(f"no machine-written manifests under {args.root}", file=sys.stderr)
        return 2
    counts: dict[str, int] = {}
    for _, name, _ in found:
        counts[name] = counts.get(name, 0) + 1
    for path, name, missing in found:
        detail = f"  ({', '.join(missing)})" if missing else ""
        print(f"{name:<15} {path.parent}{detail}")
    print()
    for name in (VERIFIED, BACKFILLED, NO_FINGERPRINT):
        print(f"{name:<15} {counts.get(name, 0)} of {len(found)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
