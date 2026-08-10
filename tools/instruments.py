#!/usr/bin/env python3
"""#230 — which task sets are instruments, declared once and read by everyone.

ADR-0018's corollary is that *the instrument is declared, and protected at the
point of entry*. Before this module the declaration existed as a convention
repeated in one place and absent from two: ``tools/problems/admit.py`` knew the
pool must not collide with the bundle sets, while ``tools/replies/pin.py`` and
``tools/finetune/build_dataset.py`` had no concept of a set they must not draw
from at all. That is how #189 came to train on 622 examples drawn from ``d1``
— which **is** ``tools/bundle/tasks/``, byte for byte — and score the result on
the same twenty contracts.

``tools/instruments.json`` is the declaration; this module reads it and answers
one question three ways, because a run can hide its provenance in three
different places:

``tier``
    What the rig called the set. Catches every run of a declared tier however
    its contracts have since been edited — and they have been: ``d1``'s digests
    moved twice, so a content check alone would miss the older runs.

``ids``
    Whether the run's task ids fall in the instrument id space (``t01``…), as
    opposed to the pool's (``p001-…``). This is the rule that covers the
    cross-language case — one id names a contract in both arms, so a Python run
    of ``t01`` is a run of the same instrument — and it is also the only rule
    that fires on the two capture-bearing runs that recorded no tier at all.
    It is sound *because* ``admit.py`` reads this same declaration and refuses
    a pool problem that collides with an instrument id.

``digests``
    ``sha256(dumps(contract))`` per task, the same digest the rigs pin as
    ``tasks_sha256``. Catches a declared set reached under an undeclared name —
    a copy, a rename, a new tier serving old contracts.

Any one of the three is enough. They are reported separately so an error can
say *why* a run is instrument material rather than only that it is.

A run that answers none of the three questions — no tier, no task digests — is
not "clean", it is **unclassifiable**, and this module says so rather than
guessing. Provenance that cannot be stated is the thing the corpus discipline
exists to replace.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
DECLARATION = REPO / "tools" / "instruments.json"

if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))


class InstrumentError(Exception):
    """The declaration is unreadable, or a run's provenance cannot be decided."""


@dataclass(frozen=True)
class Instrument:
    """One declared measurement set."""

    id: str
    root: Path
    language: str
    tiers: tuple[str, ...]
    paired_with: tuple[str, ...]
    note: str

    @property
    def task_ids(self) -> frozenset[str]:
        """Ids on disk — the directory names carrying a ``contract.yaml``."""
        if not self.root.is_dir():
            return frozenset()
        return frozenset(
            d.name
            for d in self.root.iterdir()
            if d.is_dir() and (d / "contract.yaml").is_file()
        )

    def digests(self) -> dict[str, str]:
        """``id -> sha256(dumps(contract))``, as the rigs pin it.

        Hashed as :func:`~mcgyvr.contract.dumps` emits it rather than as the
        file reads, so a re-indented YAML block is the same contract here and
        in ``tasks_sha256`` — that identity is the whole point of comparing
        the two.
        """
        from mcgyvr.contract import dumps, load

        out: dict[str, str] = {}
        for task_id in sorted(self.task_ids):
            contract = load(self.root / task_id / "contract.yaml")
            out[task_id] = hashlib.sha256(dumps(contract).encode("utf-8")).hexdigest()
        return out


@dataclass(frozen=True)
class Verdict:
    """What the declaration says about one run's material.

    ``sets`` is every instrument claiming the run and is what the guards act
    on — any claimant at all means the material is instrument material.
    ``primary`` is the one the strong evidence identified, and is ``None``
    when only the id space matched: several sets share the ``t01``…``t20``
    id shape, so an id-only hit is a real detection and an honest failure to
    attribute at the same time.
    """

    sets: tuple[str, ...]
    primary: str | None
    reasons: tuple[str, ...]

    def __bool__(self) -> bool:
        return bool(self.sets)

    @property
    def why(self) -> str:
        """One line naming the sets and how each was recognised."""
        return "; ".join(self.reasons) if self.reasons else "no instrument material"


@lru_cache(maxsize=1)
def declared() -> tuple[Instrument, ...]:
    """Every declared instrument set, in declaration order."""
    try:
        doc = json.loads(DECLARATION.read_text(encoding="utf-8"))
    except OSError as exc:  # pragma: no cover - a missing declaration is fatal
        raise InstrumentError(f"cannot read {DECLARATION}: {exc}") from exc
    sets = []
    for entry in doc["sets"]:
        sets.append(
            Instrument(
                id=entry["id"],
                root=REPO / entry["root"],
                language=entry["language"],
                tiers=tuple(entry.get("tiers", ())),
                paired_with=tuple(entry.get("paired_with", ())),
                note=entry.get("note", ""),
            )
        )
    if not sets:
        raise InstrumentError(f"{DECLARATION} declares no instrument sets")
    return tuple(sets)


def task_roots() -> tuple[Path, ...]:
    """The roots the pool must stay distinct from — ``admit.py``'s list."""
    return tuple(inst.root for inst in declared())


def id_space() -> dict[str, tuple[str, ...]]:
    """``task id -> the sets that use it``.

    An id is shared: ``t01`` names a contract in both bundle arms *and* a
    different problem in ``d2`` and ``d3``. That ambiguity is harmless for the
    guard — every claimant is an instrument — and it is why a hit reports every
    set the id belongs to rather than pretending to pick one.
    """
    space: dict[str, list[str]] = {}
    for inst in declared():
        for task_id in inst.task_ids:
            space.setdefault(task_id, []).append(inst.id)
    return {task_id: tuple(sets) for task_id, sets in sorted(space.items())}


def digest_space() -> dict[str, tuple[str, str]]:
    """``contract digest -> (set id, task id)``."""
    space: dict[str, tuple[str, str]] = {}
    for inst in declared():
        for task_id, digest in inst.digests().items():
            space.setdefault(digest, (inst.id, task_id))
    return space


def tier_owner(tier: str) -> str | None:
    """The set a rig tier name serves, if the declaration names one."""
    for inst in declared():
        if tier in inst.tiers:
            return inst.id
    return None


def classify(
    meta: Mapping[str, Any],
    *,
    where: str = "run",
    task_ids: Iterable[str] = (),
) -> Verdict:
    """Whether a run's material belongs to a declared instrument, and why.

    ``meta`` is the run's ``run.json``. ``task_ids`` supplements it for a run
    that records no digests but whose captured files name their tasks; it is
    additive, never a substitute for what the run itself declared.

    Raises :class:`InstrumentError` when the run states neither a tier nor
    task digests nor any task id — an empty verdict there would be a guess.
    """
    tier = meta.get("tier")
    digests = meta.get("tasks_sha256") or {}
    ids = set(task_ids) | set(digests)
    if not tier and not digests and not ids:
        raise InstrumentError(
            f"{where}: no tier, no tasks_sha256 and no task ids — its "
            "provenance cannot be decided, so it cannot be cleared either"
        )

    # Strong evidence first. A declared tier name and an identical contract
    # digest each identify one set; the id space cannot, because five sets
    # share the t01..t20 shape. So the id rule runs as a fallback — broad
    # enough to catch what the strong rules miss (a tierless run whose
    # contracts have since been edited is exactly that case), and suppressed
    # when something authoritative has already named a set, where it would
    # only add four wrong names to a correct one.
    hits: dict[str, list[str]] = {}
    primary: str | None = None

    if digests:
        known = digest_space()
        by_digest: dict[str, list[str]] = {}
        for task_id, digest in sorted(digests.items()):
            found = known.get(str(digest))
            if found is not None:
                by_digest.setdefault(found[0], []).append(task_id)
        for set_id, matched in sorted(by_digest.items()):
            hits.setdefault(set_id, []).append(
                f"{set_id}: {len(matched)} contract digest(s) identical to it"
            )
            primary = primary or set_id

    if tier:
        owner = tier_owner(str(tier))
        if owner is not None:
            hits.setdefault(owner, []).append(
                f"{owner}: tier {tier!r} is declared as it"
            )
            primary = primary or owner

    if not hits:
        space = id_space()
        by_id: dict[str, list[str]] = {}
        for task_id in sorted(ids):
            for set_id in space.get(task_id, ()):
                by_id.setdefault(set_id, []).append(task_id)
        for set_id, matched in sorted(by_id.items()):
            shown = ", ".join(matched[:3]) + ("…" if len(matched) > 3 else "")
            hits.setdefault(set_id, []).append(
                f"{set_id}: {len(matched)} task id(s) in its id space ({shown})"
            )

    return Verdict(
        tuple(sorted(hits)),
        primary,
        tuple(r for set_id in sorted(hits) for r in hits[set_id]),
    )


def main() -> int:
    """Print the declaration and what it currently covers."""
    print(f"{DECLARATION.relative_to(REPO)}: {len(declared())} instrument sets")
    for inst in declared():
        ids = sorted(inst.task_ids)
        print(
            f"  {inst.id:<12} {inst.language:<7} "
            f"{len(ids):>3} tasks  tiers={list(inst.tiers)}  "
            f"{inst.root.relative_to(REPO)}"
        )
        if not ids:
            print("    (no contracts on disk — declared but absent)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
