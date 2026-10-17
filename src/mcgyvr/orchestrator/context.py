""

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

#
#
#
#
#
#
#
_HINT_BOOST = 1.0 + (_DOMINANCE - 1.0) * 0.8


class Discrepancy(StrEnum):
    ""

    UNKNOWN_PATH = "unknown_path"  #
    STALE_CONTENT = "stale_content"  #
    UNCORROBORATED = (
        "uncorroborated"  #
    )


@dataclass(frozen=True)
class ContextFinding:
    ""

    path: str
    discrepancy: Discrepancy
    detail: str


@dataclass(frozen=True)
class SuppliedContext:
    ""

    paths: tuple[str, ...] = ()
    contents: Mapping[str, str] = field(default_factory=dict)

    @property
    def named(self) -> tuple[str, ...]:
        ""
        return tuple(dict.fromkeys([*self.paths, *self.contents]))


@dataclass(frozen=True)
class VerifiedContext:
    ""

    trusted: frozenset[str]
    fresh: frozenset[str]
    findings: tuple[ContextFinding, ...]

    @classmethod
    def none(cls) -> VerifiedContext:
        ""
        return cls(trusted=frozenset(), fresh=frozenset(), findings=())

    def __bool__(self) -> bool:
        ""
        return bool(self.trusted)


@dataclass(frozen=True)
class Acceleration:
    ""

    resolution: Resolution
    promoted: tuple[str, ...]
    findings: tuple[ContextFinding, ...]


def verify(index: Index, supplied: SuppliedContext) -> VerifiedContext:
    ""
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
        #
        #
        #
        #
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
    ""
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
    #
    #
    #t.
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


#


def _normalize(raw: str, root: Path) -> str:
    ""
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
    ""
    if raw in supplied.contents:
        return supplied.contents[raw]
    return supplied.contents.get(normalized)
