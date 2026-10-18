"""Verify the context a caller supplies against a built index, then use what
survives to re-rank a resolution.

`verify` turns a `SuppliedContext` into a `VerifiedContext`: paths the index
confirms, supplied text that matches the indexed lines, and a finding for every
mismatch. `accelerate` folds that verdict back into an existing `Resolution`
with a bounded boost for trusted paths. A hint cannot add a candidate the
deterministic pass did not shortlist, and it cannot lower a verdict that pass
already reached.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path, PurePosixPath

from mcgyvr.orchestrator.index import Index
from mcgyvr.orchestrator.resolve import (
    _DOMINANCE,
    Candidate,
    Resolution,
    Verdict,
    _verdict,
)

# Score multiplier for a candidate whose path the caller named: at the current
# resolver tuning that is 1.4, i.e. 80% of the way from a neutral score to the
# dominance the resolver demands. The unboosted 20% is what keeps a hint honest:
# the boost can settle a decision the index was already leaning toward, yet on its
# own it stays under the dominance ratio — it reorders a field or flips a
# near-tie, but cannot overtake a leader that is already dominant, so the
# recomputed verdict reports what the hint actually achieved.
_HINT_BOOST = 1.0 + (_DOMINANCE - 1.0) * 0.8


class Discrepancy(StrEnum):
    """The ways supplied context can disagree with the index, recorded on a finding
    instead of being silently absorbed."""

    UNKNOWN_PATH = "unknown_path"  # named path absent from the index; hint dropped
    STALE_CONTENT = "stale_content"  # supplied text differs from the indexed lines
    UNCORROBORATED = (
        "uncorroborated"  # trusted path the deterministic pass never shortlisted
    )


@dataclass(frozen=True)
class ContextFinding:
    """One mismatch between what the caller supplied and what the index holds.

    `path` is spelled the way the caller spelled it, `discrepancy` says which kind
    of disagreement this is, and `detail` states its consequence in prose.
    """

    path: str
    discrepancy: Discrepancy
    detail: str


@dataclass(frozen=True)
class SuppliedContext:
    """What the caller claims to know before exploration: paths it hints at, and
    the text it already holds for any of them.

    Either side may be empty and either may stand alone; supplying `contents` for
    a path names that path just as `paths` does.
    """

    paths: tuple[str, ...] = ()
    contents: Mapping[str, str] = field(default_factory=dict)

    @property
    def named(self) -> tuple[str, ...]:
        """Every path the caller named, whether by hint or by holding its text,
        deduplicated in first-seen order."""
        return tuple(dict.fromkeys([*self.paths, *self.contents]))


@dataclass(frozen=True)
class VerifiedContext:
    """What a `SuppliedContext` turned out to be worth: `trusted` paths are the ones
    the index confirms, `fresh` is the subset whose supplied text matched the
    indexed lines, and `findings` holds every mismatch that was reported."""

    trusted: frozenset[str]
    fresh: frozenset[str]
    findings: tuple[ContextFinding, ...]

    @classmethod
    def none(cls) -> VerifiedContext:
        """The neutral result: nothing trusted, nothing fresh, nothing to report."""
        return cls(trusted=frozenset(), fresh=frozenset(), findings=())

    def __bool__(self) -> bool:
        """True when at least one path was trusted, so an empty verification is
        falsy."""
        return bool(self.trusted)


@dataclass(frozen=True)
class Acceleration:
    """A resolution re-ranked with trusted hints: the adjusted `resolution`, the
    paths whose score was actually boosted, and every finding raised by both the
    verification and the re-ranking."""

    resolution: Resolution
    promoted: tuple[str, ...]
    findings: tuple[ContextFinding, ...]


def verify(index: Index, supplied: SuppliedContext) -> VerifiedContext:
    """Check every path the caller named against `index` and sort the outcome into
    trusted paths, fresh text, and findings.

    A path the index does not know is dropped and reported as unknown. A real path
    is always trusted, since only the path is being vouched for; its supplied text
    then either matches the indexed lines and earns freshness, or is reported as
    stale so the file is read normally instead of believed.
    """
    indexed = {file.path: file for file in index.files}
    trusted: set[str] = set()
    fresh: set[str] = set()
    findings: list[ContextFinding] = []

    for raw in supplied.named:
        path = _normalize(raw, index.root)
        file = indexed.get(path)
        if file is None:
            findings.append(
                ContextFinding(
                    path=raw,
                    discrepancy=Discrepancy.UNKNOWN_PATH,
                    detail="not present in the index — the hint was dropped",
                )
            )
            continue
        trusted.add(path)

        text = _content_for(supplied, raw, path)
        if text is None:
            continue
        # Believe the caller's text only if it matches the indexed lines exactly,
        # compared with the same split the index applied, so a missing or extra
        # trailing newline still counts as stale. A stale file stays trusted for
        # re-ranking and is simply read normally, which is why it is only reported.
        if tuple(text.split("\n")) == file.lines:
            fresh.add(path)
        else:
            findings.append(
                ContextFinding(
                    path=raw,
                    discrepancy=Discrepancy.STALE_CONTENT,
                    detail=(
                        "supplied text differs from the repository — the file will "
                        "be read normally"
                    ),
                )
            )

    return VerifiedContext(
        trusted=frozenset(trusted), fresh=frozenset(fresh), findings=tuple(findings)
    )


def accelerate(resolution: Resolution, verified: VerifiedContext) -> Acceleration:
    """Re-rank `resolution` with a bounded boost for every candidate whose path the
    caller had trusted.

    A promoted candidate keeps its deterministic evidence and gains a note that
    supplied context named it. The candidate set is untouched, so a hint can only
    reorder what the deterministic pass already shortlisted; a verdict that was
    already resolved is inherited as-is, while an unresolved one is recomputed from
    the boosted ranking, so only a real dominance gap becomes a resolution.
    """
    boosted: list[Candidate] = []
    promoted: list[str] = []
    for candidate in resolution.candidates:
        if candidate.path in verified.trusted:
            promoted.append(candidate.path)
            boosted.append(
                Candidate(
                    path=candidate.path,
                    score=round(candidate.score * _HINT_BOOST, 3),
                    evidence=(*candidate.evidence, "supplied context names this path"),
                )
            )
        else:
            boosted.append(candidate)

    ranked = tuple(sorted(boosted, key=lambda item: (-item.score, item.path)))
    # Re-sort after boosting: scores are rounded and ties fall back to the path, so
    # the order is stable whatever order the hints arrived in. A verdict the
    # resolver already reached is never downgraded; an unresolved one is recomputed
    # against the new scores rather than assumed to follow the hint.
    verdict = (
        Verdict.RESOLVED if resolution.verdict is Verdict.RESOLVED else _verdict(ranked)
    )

    shortlisted = {candidate.path for candidate in resolution.candidates}
    findings = [
        *verified.findings,
        *(
            ContextFinding(
                path=path,
                discrepancy=Discrepancy.UNCORROBORATED,
                detail=(
                    "the deterministic pass did not shortlist this path — the hint "
                    "did not affect the plan"
                ),
            )
            for path in sorted(verified.trusted - shortlisted)
        ),
    ]

    return Acceleration(
        resolution=Resolution(
            query=resolution.query, verdict=verdict, candidates=ranked
        ),
        promoted=tuple(promoted),
        findings=tuple(findings),
    )


# Helpers that map a caller's spelling of a path onto the index's relative form and
# retrieve whatever text they supplied for it.


def _normalize(raw: str, root: Path) -> str:
    """Return `raw` in the index's relative posix form: whitespace stripped, backslashes
    folded to slashes, and an absolute path made relative to `root` when it resolves
    inside it. Anything that cannot be made relative comes back in the stripped form,
    so a path from outside the repository simply fails to match the index."""
    text = raw.strip().replace("\\", "/")
    if not text:
        return text
    candidate = Path(text)
    if candidate.is_absolute():
        try:
            text = str(candidate.resolve().relative_to(root.resolve()))
        except (OSError, ValueError):
            return text
    return str(PurePosixPath(text.replace("\\", "/")))


def _content_for(supplied: SuppliedContext, raw: str, normalized: str) -> str | None:
    """The text the caller supplied for this path, looked up first under the spelling
    they used and then under the normalized form; `None` when they supplied none."""
    if raw in supplied.contents:
        return supplied.contents[raw]
    return supplied.contents.get(normalized)
