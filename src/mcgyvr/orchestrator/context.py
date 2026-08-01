"""Agent-supplied context — an accelerator that is never load-bearing.

In delegated mode the caller is usually another agent that has *already* read
the repository. Making it re-pay for that knowledge is pure waste, so this layer
lets it hand over what it holds: the paths it believes matter, and the file text
it already has in context. Used well, that turns paid reads into free ones.

The danger is obvious and it is the whole reason this module is small and
suspicious. A hint is an assertion by something that can be wrong — stale after
an edit, confused about a name, or simply hallucinated. If a hint could steer
the plan, the orchestrator would inherit the caller's mistakes and the
deterministic guarantee of #47/#48 would be worth nothing. So the rules here are
structural, not advisory:

* **The deterministic pass always runs, and cannot be turned off.** There is no
  flag in this module that skips index, resolve or region planning. Supplied
  context enters *after* :func:`~mcgyvr.orchestrator.resolve.resolve` has already
  produced its shortlist, and it may only re-rank what is already there. Nothing
  here can add a path the index did not shortlist, and nothing here can remove
  one. The set of files a plan targets is the deterministic pass's alone.

* **A hint is checked against the index before it is believed.** A path that is
  not in the index is dropped. Supplied text that does not match what the
  repository actually holds is dropped, and the repository wins. Every rejection
  becomes a :class:`ContextFinding` on the result — contradiction is *reported*,
  never silently absorbed and never silently trusted.

* **The hint's strength is bounded below the resolver's own dominance
  threshold.** This is the sharp end. A candidate the caller names has its score
  multiplied by :data:`_HINT_BOOST`, which is pinned strictly under
  :data:`~mcgyvr.orchestrator.resolve._DOMINANCE`. Since a ``RESOLVED`` leader
  beats its runner-up by at least the dominance factor, a boost smaller than that
  factor cannot overtake it — *arithmetically*, not by convention. So a wrong
  hint cannot re-point a plan the index already resolved. Its reach is confined
  to the shortlist the resolver declined to separate: there it decides read
  *order*, and it can finish a call the index had already nearly made, but it
  cannot turn a dead tie into a verdict. Corroboration is allowed to settle
  something; assertion alone is not.

The saving shows up in :mod:`~mcgyvr.orchestrator.read`: a file whose supplied
text was *verified equal* to the indexed content is already in the caller's
context, so reading it costs the exploration budget nothing. The region is still
planned, still attributed, still reported — it is just free, and the budget it
did not consume is available for regions the caller has not seen.
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

# The hint's entire strength, as a multiplier on a candidate's deterministic
# score. It is *derived* from the resolver's dominance threshold rather than
# written as a literal, because the safety argument depends on the relationship
# between the two and must not drift if either is retuned: a RESOLVED leader
# beats its runner-up by at least `_DOMINANCE`, so a boost strictly below
# `_DOMINANCE` can never lift the runner-up past it. Keeping the boost at a fixed
# fraction of the gap makes that inequality structural.
_HINT_BOOST = 1.0 + (_DOMINANCE - 1.0) * 0.8


class Discrepancy(StrEnum):
    """Why a piece of supplied context was not believed.

    Each value is a way the caller's picture and the repository disagree. They
    are reported on the result rather than raised: a bad hint is an ordinary,
    expected event that degrades the acceleration, not an error that should stop
    a plan the deterministic pass can produce perfectly well on its own.
    """

    UNKNOWN_PATH = "unknown_path"  # named a path the index does not hold
    STALE_CONTENT = "stale_content"  # supplied text differs from the repository
    UNCORROBORATED = (
        "uncorroborated"  # real path, but the resolver did not shortlist it
    )


@dataclass(frozen=True)
class ContextFinding:
    """One rejected hint: which path, which disagreement, and the detail.

    ``detail`` is a short human-readable line explaining the specific mismatch,
    so a caller can fix a stale cache rather than merely learn that it was
    ignored.
    """

    path: str
    discrepancy: Discrepancy
    detail: str


@dataclass(frozen=True)
class SuppliedContext:
    """What the calling agent claims to already know about the repository.

    ``paths`` are repo-relative paths the caller believes are relevant.
    ``contents`` maps a path to the text the caller currently holds for it —
    supplying content also counts as naming the path, since it is the stronger
    claim. Nothing here is trusted until :func:`verify` has checked it against
    the index.
    """

    paths: tuple[str, ...] = ()
    contents: Mapping[str, str] = field(default_factory=dict)

    @property
    def named(self) -> tuple[str, ...]:
        """Every path this context refers to, named or supplied, in a stable order."""
        return tuple(dict.fromkeys([*self.paths, *self.contents]))


@dataclass(frozen=True)
class VerifiedContext:
    """Supplied context after it has been checked against the index.

    ``trusted`` are paths that genuinely exist in the index and may therefore
    re-rank the shortlist. ``fresh`` are the subset whose supplied text was found
    equal to the indexed content — only these can satisfy a read for free, since
    only these are provably what the caller thinks they are. ``findings`` records
    everything that was rejected and why.
    """

    trusted: frozenset[str]
    fresh: frozenset[str]
    findings: tuple[ContextFinding, ...]

    @classmethod
    def none(cls) -> VerifiedContext:
        """An empty verification — the neutral element, for callers with no hints."""
        return cls(trusted=frozenset(), fresh=frozenset(), findings=())

    def __bool__(self) -> bool:
        """True when anything survived verification and could accelerate a plan."""
        return bool(self.trusted)


@dataclass(frozen=True)
class Acceleration:
    """A re-ranked resolution, plus a full account of how the hints were treated.

    ``resolution`` holds exactly the candidate paths the deterministic pass
    produced — re-ordered, possibly, but never added to or removed from.
    ``promoted`` names the candidates the hints lifted, and ``findings`` lists
    every hint that was rejected, so the acceleration is auditable rather than
    an invisible thumb on the scale.
    """

    resolution: Resolution
    promoted: tuple[str, ...]
    findings: tuple[ContextFinding, ...]


def verify(index: Index, supplied: SuppliedContext) -> VerifiedContext:
    """Check supplied context against the index, keeping only what holds up.

    A named path is trusted when the index actually holds it. Supplied text is
    trusted only when it matches the indexed content exactly, line for line — the
    repository is the authority, and a caller working from a stale copy must not
    be able to feed that copy back as fact. Everything rejected is returned as a
    :class:`ContextFinding`; nothing raises, because a bad hint is a normal event
    that the deterministic pass is entirely capable of surviving.
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
        # Byte-equality against what the index decoded, compared the same way the
        # index split it. Anything less strict would let a "close enough" copy
        # stand in for the real file, which is exactly the substitution that makes
        # a hint load-bearing.
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
    """Re-rank a resolution using verified hints, without changing what it targets.

    Candidates the caller named are boosted by :data:`_HINT_BOOST` and the
    shortlist is re-sorted. The candidate *set* is untouched, so the files a plan
    targets remain the deterministic pass's decision. A resolution that was
    already :attr:`~mcgyvr.orchestrator.resolve.Verdict.RESOLVED` keeps both its
    verdict and its leader — the boost is too small to overturn a dominant
    leader, and confidence is never *lowered* by a hint, so an accelerated plan
    is never less certain than the one the index produced alone.

    Within an ``AMBIGUOUS`` shortlist the hint has real effect: it reorders, so
    the named candidate is read first, and where the field was already leaning it
    can carry that leader past the dominance threshold into ``RESOLVED``. It
    cannot do so from a dead tie — with the boost capped below that threshold,
    two equally-scored candidates stay ambiguous however firmly one is asserted.
    A hint may confirm a judgement; it may not supply one.

    Hints that survived verification but name nothing on the shortlist are
    reported as :attr:`Discrepancy.UNCORROBORATED` and have no other effect.
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
    # Never downgrade: the hint may settle an ambiguity, but it may not introduce
    # one. A resolution the index called outright stays called, with the leader it
    # already had — which `_HINT_BOOST < _DOMINANCE` guarantees is still first.
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


# --- small deterministic helpers -------------------------------------------


def _normalize(raw: str, root: Path) -> str:
    """A supplied path reduced to the repo-relative form the index uses.

    Callers hand over paths in whatever shape they had them: absolute, prefixed
    with ``./``, or with native separators. Normalising here means a correct hint
    is not rejected over punctuation, while a genuinely unknown path still fails
    the index lookup that follows.
    """
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
    """The text supplied for a path, looked up under either spelling of it."""
    if raw in supplied.contents:
        return supplied.contents[raw]
    return supplied.contents.get(normalized)
