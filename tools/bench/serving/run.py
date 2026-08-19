#!/usr/bin/env python3
"""One run of the serving survey: a config in, one result out.

**This is the only module that knows more than one backend exists**, and it uses
that knowledge for exactly one thing: deciding who must give up the card before
somebody else takes it. Backends implement ``release()`` and ``claim()`` and
know nothing about each other, so a third engine is a file in ``backends/`` and
a line of config, with no edit here.

The bug that shape exists to prevent was real. A single-module predecessor
cleared the machine unconditionally before every measurement — which meant that
when it reached the vLLM leg it stopped vLLM, then measured a server that was no
longer running, and recorded the engine as unreachable. No conditional fixes
that; the fix is that a backend is never the thing deciding who yields.

**Order is derived, not configured.** Engines are discovered *before* anything
is cleared, because a survey that clears first can only ever measure whichever
engine it happens to reach first.

**Keys are ``(host, backend, label)`` and never a model id alone.** The same
weights served by two engines are two different instruments — measured on these
rigs: one served a GGUF at Q4_K_M with a 4096 window and a fresh random seed per
request, the other an AWQ build with an 8192 window and a seed fixed at 0. And
one model on one backend under two serving configurations is likewise two rows,
which is what ``label`` distinguishes.

``family`` groups entries a config CLAIMS are the same model. It is a claim, not
evidence: the digests in each description decide, and a family whose members
disagree is recorded as refuted rather than quietly reconciled. A family missing
a member — because its claim was refused — states its denominator, so "identical
across 2 of 3, one refused" never reads as "identical".

Usage::

    uv run --no-sync python tools/bench/serving/run.py \\
        --config tools/bench/serving/configs/srv-full.json \\
        --out records/evidence/serving-<date>/survey.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import types
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def _contract() -> types.ModuleType:
    cached = sys.modules.get("serving_contract")
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(
        "serving_contract", HERE / "contract.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["serving_contract"] = module
    spec.loader.exec_module(module)
    return module


contract = _contract()


def _journal(path: Path | None) -> Any:
    """Append one record and put it on the disk, or do nothing.

    **D8, 2026-08-19: a durable output, written as the run goes.** The
    end-of-run write and the abort handler both depend on the process living
    long enough to reach them, and neither survives what actually ends a long
    campaign here: an ssh that dies under load, an OOM killer, a reboot. Nine
    hours of rig time must not be recoverable only from a traceback.

    fsync per record on purpose. A row costs a model load — seconds to minutes
    — so a flush per row is free against what it protects, and buffering is
    exactly what loses the tail.
    """
    if path is None:
        return lambda record: None

    def append(record: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    return append


def run(config: dict[str, Any], journal: Path | None = None) -> dict[str, Any]:
    """The whole survey, as the config describes it.

    ``journal``, when given, receives one JSON line per completed entry the
    moment it completes — see :func:`_journal`.
    """
    record = _journal(journal)
    hosts: list[str] = config.get("hosts") or []
    entries: list[dict[str, Any]] = config.get("models") or []
    collect = config.get("collect") or {}
    # EVERY backend that exists, not just the ones this config measures. A run
    # that only measures one engine must still make the others yield the card —
    # otherwise an engine nobody asked about keeps its allocation, and the model
    # under test is placed on the CPU behind it. That is the contamination this
    # structure exists to prevent, and scoping the roster to the config's own
    # entries reintroduced it: the survey would clear nothing and measure a
    # model at a twentieth of its speed without a single reading looking wrong.
    names = config.get("backends") or contract.available_backends()
    backends = {str(name): contract.load_backend(str(name)) for name in names}
    for entry in entries:
        if str(entry["backend"]) not in backends:
            raise contract.NotCleanError(
                f"config entry {entry.get('label') or entry['id']!r} names backend "
                f"{entry['backend']!r}, which is not among {sorted(backends)}"
            )

    result: dict[str, Any] = {
        "config": config,
        "hosts": {},
        "families": {},
        "refusals": [],
    }
    # Published as it fills, so a caller that catches an abort can still write
    # down the hosts already surveyed rather than losing the run with the error.
    run.partial = result["hosts"]  # type: ignore[attr-defined]

    for host in hosts:
        print(f"[{host}] snapshot", flush=True)
        # Read-only, and taken FIRST. Discovery has to happen before anything is
        # cleared, or the survey can only measure whichever engine it reaches
        # first — which is how the predecessor could never measure both.
        entry: dict[str, Any] = {
            "snapshot": contract.snapshot(host),
            "present": {},
            "measured": {},
        }
        for name, backend in backends.items():
            base = backend.probe(host)
            entry["present"][name] = {
                "base": base,
                "reachable": base is not None,
                "inventory": backend.inventory(host, base) if base else [],
                "readings": backend.readings(host)
                if collect.get("host_config")
                else {},
            }
        result["hosts"][host] = entry

        for spec in entries:
            label = str(spec.get("label") or spec["id"])
            # **E6, 2026-08-19: an entry runs only on the hosts that name it.**
            # This loop was a full host x entry cross-product, so the campaign's
            # roster — 5 models on srv1 and 10 on srv2 — could not be expressed
            # at all. Labels like `q15-ollama-srv1` READ like affinity and were
            # not, which is worse than no affinity: the config appeared to say
            # something it had no way to mean. Omitting `hosts` still means
            # every host, so nothing that worked before changes.
            wanted = spec.get("hosts")
            if wanted is not None and host not in wanted:
                continue
            name = str(spec["backend"])
            backend = backends[name]
            print(f"[{host}] {label} ({name}) — yielding the card", flush=True)

            # THE exclusion, and the only one. Every other backend gives up the
            # card; the one under test is never touched by this loop.
            yielded = {
                other: backends[other].release(host)
                for other in backends
                if other != name
            }
            # ENFORCED, not merely recorded. `release()` returns whether the
            # card actually came free and this stored the flag without ever
            # reading it — so a backend that failed to yield was noted in the
            # record and measured against anyway, which is the contamination
            # the whole structure exists to prevent, dressed as evidence.
            held = [
                other
                for other, evidence in yielded.items()
                if evidence.get("released") is not True
            ]
            if held:
                why = (
                    f"{held} would not give up the card before {label}: "
                    + ", ".join(
                        f"{other}={yielded[other].get('gpu_used_mib')} MiB"
                        for other in held
                    )
                    + ". Measuring now would place this model behind another "
                    "engine's allocation, where it is served from CPU at a "
                    "fraction of the speed and nothing in the result looks wrong."
                )
                print(f"[{host}] {label} REFUSED: {why}", flush=True)
                result["refusals"].append(
                    {
                        "host": host,
                        "label": label,
                        "backend": name,
                        "why": why,
                        "stage": "exclusion",
                    }
                )
                entry["measured"][label] = row_out = {
                    "backend": name,
                    "model": spec["id"],
                    "family": spec.get("family"),
                    "verified": False,
                    # D8: an explicit outcome, so a campaign can be counted
                    # rather than read. `verified: False` alone conflated "we
                    # refused to measure this" with "we measured it and it
                    # failed", which are different results about the rig.
                    "outcome": "refused",
                    "refused_stage": "exclusion",
                    "refused": why,
                    "yielded": yielded,
                }
                record({"host": host, "label": label, **row_out})
                continue

            try:
                # D4: the entry's own placement declaration replaces the
                # withdrawn global VRAM gate, and `coresident` lets an entry
                # ask for the co-residency D7 item 4 measures on purpose.
                # `claim` takes them as keywords so a backend that does not
                # model placement is unaffected.
                claim_kwargs: dict[str, Any] = {}
                if spec.get("placement") is not None:
                    claim_kwargs["placement"] = spec["placement"]
                if spec.get("coresident"):
                    claim_kwargs["coresident"] = True
                if spec.get("coresident_with"):
                    claim_kwargs["coresident_with"] = spec["coresident_with"]
                claimed = backend.claim(
                    host,
                    entry["present"][name]["base"] or f"http://{host}:{backend.PORT}",
                    str(spec["id"]),
                    spec.get("serve"),
                    spec.get("expect"),
                    **claim_kwargs,
                )
            except Exception as error:
                print(f"[{host}] {label} REFUSED: {error}", flush=True)
                result["refusals"].append(
                    {
                        "host": host,
                        "label": label,
                        "backend": name,
                        "why": str(error),
                        "stage": "claim",
                    }
                )
                entry["measured"][label] = row_out = {
                    "backend": name,
                    "model": spec["id"],
                    "family": spec.get("family"),
                    "verified": False,
                    "outcome": "refused",
                    "refused_stage": "claim",
                    "refused_kind": type(error).__name__,
                    "refused": str(error),
                    "yielded": yielded,
                }
                record({"host": host, "label": label, **row_out})
                continue

            base = entry["present"][name]["base"] or f"http://{host}:{backend.PORT}"
            row: dict[str, Any] = {
                "backend": name,
                "model": spec["id"],
                "family": spec.get("family"),
                "verified": True,
                # D8. Downgraded to `incomplete` below if describe or the ramp
                # fails, so the terminal value is always one of
                # measured / incomplete / refused and never has to be inferred.
                "outcome": "measured",
                "yielded": yielded,
                "claim": claimed,
            }
            entry["measured"][label] = row
            # Described and ramped INSIDE a guard, and the row is already in the
            # result before either runs. A survey is hours of rig time across
            # many models, and an ssh that dies while describing the last one
            # must not discard every model before it — which is exactly what an
            # unguarded loop did: one RuntimeError and nothing was written at
            # all. A failure here is one model's failure, recorded as such.
            try:
                row["description"] = backend.describe(
                    host, base, str(spec["id"]), spec.get("serve") or {}
                )
                # D1: hoisted so the summary and any consumer can read the
                # declaration beside the curve without digging for it.
                row["declared_slots"] = (row["description"] or {}).get("declared_slots")
                concurrency = spec.get("concurrency") or {}
                if collect.get("concurrency", True) and concurrency.get("measure"):
                    print(f"[{host}] {label} — concurrency ramp", flush=True)
                    measured = contract.ramp(
                        base,
                        str(spec["id"]),
                        tuple(concurrency.get("levels") or contract.RAMP_LEVELS),
                    )
                    # D1: what the curve did, and what the server said, are
                    # two quantities. `saturation_n` is measured here; the
                    # backend supplies `declared_slots` with its provenance.
                    saturated = measured.get("saturation") or {}
                    expected = concurrency.get("expect")
                    measured["expected"] = expected
                    measured["matches_expected"] = (
                        None if expected is None else saturated.get("n") == expected
                    )
                    row["concurrency"] = measured
                    if measured["matches_expected"] is False:
                        print(
                            f"[{host}] {label} — saturation_n "
                            f"{saturated.get('n')} != expected {expected} "
                            f"(at {saturated.get('ramp_tokens')} tokens, "
                            f"fraction {saturated.get('plateau_fraction')})",
                            flush=True,
                        )
            except Exception as error:
                print(f"[{host}] {label} INCOMPLETE: {error}", flush=True)
                row["outcome"] = "incomplete"
                row["incomplete_kind"] = type(error).__name__
                row["incomplete"] = f"{type(error).__name__}: {error}"
                result["refusals"].append(
                    {
                        "host": host,
                        "label": label,
                        "backend": name,
                        "why": row["incomplete"],
                        "stage": "describe/ramp — the claim itself succeeded",
                    }
                )
            # Outside the guard: the row is terminal either way, and a row that
            # failed to describe is exactly the one worth having on disk.
            record({"host": host, "label": label, **row})

    result["families"] = verdicts(result)
    return result


def _digest_of(row: dict[str, Any]) -> str | None:
    """The weights identity a backend actually reported, whatever it calls it.

    Each backend states its own in the evidence `claim` returns; this reads that
    rather than guessing at a field name on the capture, which is how every
    family verdict came to be computed from `None`.
    """
    checks = (row.get("claim") or {}).get("checks") or {}
    weights = checks.get("weights") or {}
    if weights.get("weights_sha256"):
        return str(weights["weights_sha256"])
    for attempt in reversed((row.get("claim") or {}).get("attempts") or []):
        if attempt.get("model_sha256"):
            return str(attempt["model_sha256"])
    return None


def _digest_kind(row: dict[str, Any]) -> str | None:
    """Which KIND of digest that is — the thing that decides comparability."""
    checks = (row.get("claim") or {}).get("checks") or {}
    if (checks.get("weights") or {}).get("weights_sha256"):
        return "checkpoint-tensor digest"
    for attempt in reversed((row.get("claim") or {}).get("attempts") or []):
        if attempt.get("model_sha256"):
            return "manifest digest"
    return None


def verdicts(result: dict[str, Any]) -> dict[str, Any]:
    """Whether each declared family's members really are the same model.

    A config asserting a family is a claim; the digests are the evidence, and
    they are allowed to disagree in writing. Every verdict carries its
    denominator, because a family with a refused member has a hole and
    "identical across the ones that turned up" is not a finding.
    """
    families: dict[str, dict[str, Any]] = {}
    for host, entry in result["hosts"].items():
        for label, row in entry["measured"].items():
            family = row.get("family")
            if not family:
                continue
            slot = families.setdefault(
                family, {"members": [], "refused": [], "declared": 0}
            )
            slot["declared"] += 1
            if not row.get("verified"):
                slot["refused"].append({"host": host, "label": label})
                continue
            description = row.get("description") or {}
            capture = description.get("capture") or {}
            slot["members"].append(
                {
                    "host": host,
                    "label": label,
                    "backend": row["backend"],
                    "model": row["model"],
                    "quantization": capture.get("quantization"),
                    # Read from the CLAIM, not the capture. `observed.capture()`
                    # emits the four probe-set fields and the native block — it
                    # does not emit any digest, because digests live in
                    # `run.json` via `identity.probe_model`. Reading them off the
                    # capture returned None for every member, so every family in
                    # the shipped config was decided on missing data while
                    # looking decided. Each backend states its own digest in the
                    # evidence it returns from `claim`, which is where it is.
                    "digest": _digest_of(row),
                    "digest_kind": _digest_kind(row),
                }
            )

    for slot in families.values():
        members = slot["members"]
        slot["denominator"] = f"{len(members)} of {slot['declared']}"
        if not members:
            slot["verdict"] = "no member was measured"
            continue
        quantizations = {member["quantization"] for member in members}
        # Comparability follows the KIND of digest, not the backend name: a
        # manifest digest and a hash over checkpoint tensors describe the same
        # weights with different numbers, so only same-kind members compare
        # directly. A cross-kind family is decided on what IS comparable — the
        # quantization each engine reports for what it loaded.
        digests = {member["digest"] for member in members}
        kinds = {member["digest_kind"] for member in members}
        # Comparable when every member's digest is the same KIND of thing —
        # which is per backend, since each computes a different one.
        slot["digests_comparable"] = len(kinds) == 1 and None not in kinds
        if len(members) == 1:
            slot["verdict"] = "single member — nothing to compare"
        elif None in digests:
            # ANY missing digest, not only all of them. The earlier guard fired
            # only when every member was null, so one member whose digest could
            # not be computed made `digests` a two-element set and was reported
            # as positive evidence that the weights disagree — a missing
            # measurement presented as a refutation.
            missing = [m["label"] for m in members if m["digest"] is None]
            slot["verdict"] = (
                f"UNDECIDED: {missing} produced no digest, so the claim that "
                "these are the same model is neither confirmed nor refuted"
            )
        elif len(kinds) == 1 and len(digests) == 1:
            slot["verdict"] = f"identical {kinds.pop()} across all members"
        elif len(kinds) == 1:
            slot["verdict"] = (
                f"REFUTED: same {kinds.pop()}, different values — the weights disagree"
            )
        else:
            # Different KINDS of digest — one backend states a manifest digest,
            # another hashes checkpoint tensors — so the numbers cannot be
            # compared and the verdict rests on what can be: the quantization
            # each engine reports for the weights it loaded. Different
            # quantizations of one model are different instruments, which is the
            # claim being tested, and it is refuted here rather than dismissed.
            slot["verdict"] = (
                "REFUTED as identical: the members' digests are not the same "
                f"KIND ({sorted(str(k) for k in kinds)}), so they cannot be "
                "compared directly; the quantizations they report "
                f"({sorted(str(q) for q in quantizations)}) make these "
                "different instruments whether or not the weights coincide"
            )
    return families


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--hosts", default="", help="override the config's hosts (comma separated)"
    )
    parser.add_argument(
        "--journal",
        type=Path,
        default=None,
        help=(
            "append one JSON line per entry as it completes (D8). Defaults to "
            "<out>.jsonl; pass 'none' to disable."
        ),
    )
    args = parser.parse_args(argv)

    config = json.loads(args.config.read_text(encoding="utf-8"))
    if args.hosts:
        config["hosts"] = [h.strip() for h in args.hosts.split(",") if h.strip()]

    # Written even if the survey dies. `run` already contains a per-model
    # failure, so reaching here with an exception means something structural —
    # and a structural failure after four hours of rig time must still leave the
    # four hours on disk, with the reason it stopped beside them.
    args.out.parent.mkdir(parents=True, exist_ok=True)
    journal: Path | None = args.out.with_suffix(args.out.suffix + ".jsonl")
    if args.journal is not None:
        journal = None if str(args.journal).lower() == "none" else args.journal
    if journal is not None:
        journal.parent.mkdir(parents=True, exist_ok=True)
        print(f"journal: {journal}", flush=True)
    try:
        result = run(config, journal=journal)
    except BaseException as error:
        partial = {
            "config": config,
            "aborted": f"{type(error).__name__}: {error}",
            "hosts": getattr(run, "partial", {}),
        }
        args.out.write_text(json.dumps(partial, indent=1) + "\n", encoding="utf-8")
        print(f"\nABORTED — partial result in {args.out}: {error}")
        raise
    args.out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")

    print(f"\nwrote {args.out} ({args.out.stat().st_size} bytes)")
    for host, entry in result["hosts"].items():
        for label, row in entry["measured"].items():
            if not row.get("verified"):
                print(f"  {host}/{label}: REFUSED")
                continue
            ramp = row.get("concurrency") or {}
            saturated = ramp.get("saturation") or {}
            declared = row.get("declared_slots") or {}
            note = ""
            if saturated.get("n") is not None:
                note += (
                    f"  saturation_n={saturated['n']}"
                    f" @{saturated.get('ramp_tokens')}tok"
                )
            elif saturated.get("refused"):
                note += f"  saturation_n REFUSED: {saturated['refused']}"
            if declared.get("value") is not None:
                note += (
                    f"  declared_slots={declared['value']}"
                    f" ({declared.get('provenance')})"
                )
            if ramp.get("matches_expected") is False:
                note += f"  (expected {ramp.get('expected')} — MISMATCH)"
            print(f"  {host}/{label}: ok{note}")
    for family, slot in result["families"].items():
        print(f"  family {family}: {slot['verdict']}  [{slot['denominator']}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
