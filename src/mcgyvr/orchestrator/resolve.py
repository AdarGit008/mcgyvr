"""The query layer — a natural-language target becomes a shortlist of paths.

The orchestrator's whole cost argument is that a model reads a few files rather
than a repository. Something has to choose those few files, and if that chooser
were itself a model the saving would be circular. So this is the deterministic
bridge: it takes a phrase a caller would actually type — ``"the fetch helper"``,
``"config loader"``, ``AttachedRepo`` — and turns it into a ranked, bounded
shortlist of candidate paths, each carrying the evidence that put it there. No
model is called; there is nothing here but the index (#47) and string work.

Three commitments shape the resolver, straight from the acceptance criteria:

* **Ranking is by specificity, and the evidence is shown.** A phrase that names
  a symbol outright outranks one that merely brushes a filename, which outranks
  a stray path-component hit. Every candidate reports *why* it ranked, so the
  expensive reader can judge the shortlist instead of trusting a black box.
* **The shortlist is bounded.** A resolver that returned fifty candidates would
  have resolved nothing; ``limit`` caps what comes back, best-first.
* **Ambiguity is an outcome, not a guess.** When no candidate clearly wins, the
  resolution says so (:attr:`Verdict.AMBIGUOUS`) and hands back the contenders,
  rather than silently promoting a coin-flip to "the answer".

The scoring is deliberately two-tier. *Whole-query* matches come first: if the
phrase, reduced to its content words and squashed to letters, equals a symbol
name or a filename, that is a near-certain hit and scores far above anything
fuzzy. Failing that, *per-token* matches accumulate — each query word scored
against symbol names, filenames and path components — with each word weighted by
how rare it is across the repository, so a common word like "helper" cannot
outvote a rare one like "fetch", and with a bonus for a candidate that covers
more of the query. The weights are ordinary numbers, tuned against real phrasings
on real repositories; they are not a model, and they are not magic.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from mcgyvr.orchestrator.index import Index
from mcgyvr.orchestrator.symbols import Symbol, SymbolKind

# Words that describe the *shape* of a target rather than name it — a caller
# says "the fetch helper", not "fetch". They are dropped from the query before
# matching so they neither squash a whole-query match ("thefetchhelper") nor add
# noise as standalone tokens. Kept small and generic: these are English glue and
# the handful of role-nouns that recur in how people point at code, not a
# project vocabulary. A word that is *part of a name* (``fetchHelper``) still
# matches, because the symbol's own tokens include it.
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "at",
        "by",
        "for",
        "from",
        "in",
        "into",
        "is",
        "of",
        "on",
        "or",
        "our",
        "that",
        "the",
        "this",
        "to",
        "which",
        "with",
        "where",
        "function",
        "func",
        "method",
        "class",
        "module",
        "file",
        "helper",
        "logic",
        "code",
        "thing",
        "stuff",
    }
)

# The strong, whole-query signals: the phrase names the thing outright. These
# dwarf per-token scores so that an exact name is never out-argued by a pile of
# weak partial hits.
_W_PATH_EXACT = 100.0
_W_SYMBOL_EXACT = 60.0
_W_STEM_EXACT = 45.0

# Per-token signal strengths, before rarity weighting. A token landing on a
# symbol name is worth more than one landing on a filename, which beats a bare
# path-component hit — specificity, descending.
_S_SYMBOL = 6.0
_S_STEM = 5.0
_S_PATH = 2.0

# A candidate that accounts for more of the query is more likely the one meant;
# this rewards coverage on top of the raw token strengths.
_W_COVERAGE = 4.0

# A test file shadows the names of the code it exercises, so it will match many
# of the same phrasings — but a caller who describes a target by name almost
# always means the implementation, and says "test" when they mean the test. This
# demotes test files so they still appear in the shortlist without crowding out
# the source; it is a ranking nudge, not an exclusion.
_TEST_DEMOTION = 0.6
_TEST_PATH = re.compile(
    r"(?:^|/)tests?/|(?:^|/)test_[^/]*$|(?:^|/)[^/]*_test\.[^/]+$|\.(?:test|spec)\.[^/]+$"
)

# An export or a top-level definition is a better landing site than a method
# buried in a class; a small nudge so the free ``fetch`` outranks ``X.fetch``
# when both match equally otherwise.
_KIND_BONUS = {SymbolKind.EXPORT: 1.5, SymbolKind.DEFINITION: 1.0}

# How decisively the leader must beat the runner-up to count as resolved rather
# than ambiguous. Below this ratio the field is too close to call, and the
# resolution reports the tie instead of breaking it.
_DOMINANCE = 1.5


class Verdict(StrEnum):
    """The confidence of a resolution — the reportable state #48 asks for."""

    RESOLVED = "resolved"  # one candidate clearly leads
    AMBIGUOUS = "ambiguous"  # several plausible, none dominant
    EMPTY = "empty"  # nothing matched the query


@dataclass(frozen=True)
class Candidate:
    """One path the query might mean, with its score and the evidence for it.

    ``evidence`` is a tuple of short human-readable reasons, strongest first —
    the material the reader (or a person) uses to judge the shortlist rather than
    trust the number.
    """

    path: str
    score: float
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class Resolution:
    """The outcome of resolving one query: a verdict and a bounded shortlist.

    ``candidates`` is ranked best-first and capped at the caller's limit. On
    :attr:`Verdict.EMPTY` it is empty; on :attr:`Verdict.AMBIGUOUS` it holds the
    contenders that could not be separated; on :attr:`Verdict.RESOLVED` its first
    entry is the resolver's answer and the rest are context.
    """

    query: str
    verdict: Verdict
    candidates: tuple[Candidate, ...]

    @property
    def best(self) -> Candidate | None:
        """The leading candidate, or ``None`` when nothing matched."""
        return self.candidates[0] if self.candidates else None


def resolve(index: Index, query: str, *, limit: int = 10) -> Resolution:
    """Resolve ``query`` to a ranked, bounded shortlist of candidate paths.

    Scores every indexed path against the phrase using whole-query and per-token
    matching over symbols, filenames and path components (see the module
    docstring), returns at most ``limit`` candidates best-first, and reports a
    :class:`Verdict` describing whether one candidate clearly won. Calls no
    model and reads no file beyond what the index already holds.
    """
    tokens = _content_tokens(query)
    corpus = _Corpus(index)

    scores: dict[str, float] = defaultdict(float)
    evidence: dict[str, list[tuple[float, str]]] = defaultdict(list)

    _score_whole_query(query, tokens, corpus, scores, evidence)
    _score_tokens(tokens, corpus, scores, evidence)

    candidates = _rank(scores, evidence, limit)
    return Resolution(query=query, verdict=_verdict(candidates), candidates=candidates)


# --- corpus: the index reshaped for matching -------------------------------


class _Corpus:
    """The index inverted the way matching needs it — built once per resolve.

    Names and filenames are indexed both whole (squashed to letters and digits,
    for the strong whole-query match) and by sub-token (``fetchHelper`` ->
    ``fetch``, ``helper``, for the fuzzy per-token match). Only definitions and
    exports feed the symbol maps: a *reference* to ``fetch`` marks a caller, not
    the helper itself, and pointing a reader at callers would defeat the resolve.
    """

    def __init__(self, index: Index) -> None:
        self.paths: frozenset[str] = frozenset(f.path for f in index.files)
        self.basenames: dict[str, set[str]] = defaultdict(set)

        # Symbol maps: squashed whole-name and per-token, each keyed to the path
        # and the representative symbol that justify an evidence line. Both keep
        # one symbol per (key, path) — the strongest kind wins the slot — so a
        # name that is both defined and exported in a file is not counted twice.
        self.symbol_exact: dict[str, dict[str, Symbol]] = defaultdict(dict)
        self.symbol_token: dict[str, dict[str, Symbol]] = defaultdict(dict)

        # Filename maps: the stem (basename without extension), whole and tokened.
        self.stem_exact: dict[str, set[str]] = defaultdict(set)
        self.stem_token: dict[str, set[str]] = defaultdict(set)

        # Path-component tokens: directory names along the way, the weakest hint.
        self.path_token: dict[str, set[str]] = defaultdict(set)

        for file in index.files:
            self._index_path(file.path)
        for symbol in index.symbols.all():
            if symbol.kind is not SymbolKind.REFERENCE:
                self._index_symbol(symbol)

    def _index_path(self, path: str) -> None:
        name = Path(path).name
        self.basenames[name.lower()].add(path)
        stem = Path(path).stem.lower()
        self.stem_exact[_squash(stem)].add(path)
        for token in _tokenize(stem):
            self.stem_token[token].add(path)
        # Directory components, minus the filename itself.
        for part in Path(path).parent.parts:
            for token in _tokenize(part):
                self.path_token[token].add(path)

    def _index_symbol(self, symbol: Symbol) -> None:
        # Whole-name slot: the strongest *kind* wins, since the name matches in
        # full and only the export/definition distinction is left to break.
        _keep_best(self.symbol_exact[_squash(symbol.name)], symbol)
        # Per-token slot: the symbol that will *score* highest for this token
        # wins — the one whose name the token accounts for most. Choosing by kind
        # alone would let an exported ``AttachError`` displace the exact ``attach``
        # in a file and then score it as the weaker fragment match.
        for token in _tokenize(symbol.name):
            slot = self.symbol_token[token]
            current = slot.get(symbol.path)
            if current is None or _token_strength(token, symbol) > _token_strength(
                token, current
            ):
                slot[symbol.path] = symbol


# --- whole-query scoring: the phrase names the thing -----------------------


def _score_whole_query(
    query: str,
    tokens: list[str],
    corpus: _Corpus,
    scores: dict[str, float],
    evidence: dict[str, list[tuple[float, str]]],
) -> None:
    """Award the strong signals: the phrase, taken whole, *is* a name or a path.

    An explicit path the caller typed (``src/mcgyvr/scope.py``) is as certain as
    it gets. Otherwise the content words are squashed to letters — so "the fetch
    helper" becomes ``fetchhelper`` — and compared against whole symbol names and
    filename stems, catching the common case where a caller names the target
    almost exactly.
    """
    raw = query.strip()
    for path in _paths_named_literally(raw, corpus):
        _award(scores, evidence, path, _W_PATH_EXACT, f'path matches "{raw}"')

    squashed = "".join(tokens)
    if not squashed:
        return
    for symbol in corpus.symbol_exact.get(squashed, {}).values():
        detail = f" ({symbol.detail})" if symbol.detail else ""
        _award(
            scores,
            evidence,
            symbol.path,
            _W_SYMBOL_EXACT + _kind_bonus(symbol),
            f"defines {symbol.name}{detail}",
        )
    for path in corpus.stem_exact.get(squashed, ()):
        _award(
            scores, evidence, path, _W_STEM_EXACT, f'filename is "{Path(path).name}"'
        )


def _paths_named_literally(raw: str, corpus: _Corpus) -> set[str]:
    """Paths the query names outright — a full repo-relative path or a basename."""
    if not raw:
        return set()
    hits: set[str] = set()
    if raw in corpus.paths:
        hits.add(raw)
    hits |= corpus.basenames.get(raw.lower(), set())
    return hits


# --- per-token scoring: the fuzzy tail -------------------------------------


def _score_tokens(
    tokens: list[str],
    corpus: _Corpus,
    scores: dict[str, float],
    evidence: dict[str, list[tuple[float, str]]],
) -> None:
    """Accumulate per-token matches, weighting rare words over common ones.

    Each distinct query token is scored against symbol names, filenames and path
    components. A token is weighted by its inverse document frequency — a word
    matching many paths carries little signal, a word matching few carries a lot
    — so "helper" cannot outvote "fetch". A final coverage bonus rewards a path
    that a larger share of the query's tokens agree on.
    """
    unique = list(dict.fromkeys(tokens))
    if not unique:
        return
    total_paths = max(len(corpus.paths), 1)

    coverage: dict[str, set[str]] = defaultdict(set)
    for token in unique:
        contributions = _collect(token, corpus)
        touched = {path for path, _, _ in contributions}
        weight = _idf(len(touched), total_paths)
        for path, strength, why in contributions:
            _award(scores, evidence, path, strength * weight, why)
            coverage[path].add(token)

    for path, covered in coverage.items():
        fraction = len(covered) / len(unique)
        if fraction > 0:
            scores[path] += _W_COVERAGE * fraction


def _collect(token: str, corpus: _Corpus) -> list[tuple[str, float, str]]:
    """Every (path, strength, evidence) this token contributes, across signals.

    A token match is scaled by how much of the *name* it accounts for: a token
    that is the whole symbol ``attach`` is decisive, the same token buried in
    ``test_repository_with_no_commit_attributes`` is a fragment and scores far
    lower. This is the specificity ranking #48 asks for, and it is what keeps a
    long-named test from outranking the implementation it exercises.
    """
    out: list[tuple[str, float, str]] = []
    for path, symbol in corpus.symbol_token.get(token, {}).items():
        detail = f" ({symbol.detail})" if symbol.detail else ""
        out.append(
            (path, _token_strength(token, symbol), f"{symbol.name}{detail} ~ {token!r}")
        )
    for path in corpus.stem_token.get(token, set()):
        strength = _S_STEM * _fraction_of_name(token, Path(path).stem)
        out.append((path, strength, f"filename ~ {token!r}"))
    for path in corpus.path_token.get(token, set()):
        out.append((path, _S_PATH, f"path ~ {token!r}"))
    return out


# --- ranking and the ambiguity verdict -------------------------------------


def _rank(
    scores: dict[str, float],
    evidence: dict[str, list[tuple[float, str]]],
    limit: int,
) -> tuple[Candidate, ...]:
    """The scored paths as candidates, best-first, capped at ``limit``.

    Ties in score break on path so the shortlist is deterministic. Evidence for
    each candidate is ordered strongest-first and de-duplicated, since one path
    can earn the same reason from several tokens.
    """
    adjusted = {path: score * _role_weight(path) for path, score in scores.items()}
    ordered = sorted(adjusted.items(), key=lambda item: (-item[1], item[0]))
    candidates: list[Candidate] = []
    for path, score in ordered[: max(limit, 0)]:
        if score <= 0:
            continue
        candidates.append(
            Candidate(
                path=path, score=round(score, 3), evidence=_top_evidence(evidence[path])
            )
        )
    return tuple(candidates)


def _top_evidence(reasons: list[tuple[float, str]], keep: int = 4) -> tuple[str, ...]:
    """The strongest, distinct evidence lines for a candidate, best-first."""
    seen: set[str] = set()
    ordered: list[str] = []
    for _, why in sorted(reasons, key=lambda item: -item[0]):
        if why not in seen:
            seen.add(why)
            ordered.append(why)
        if len(ordered) >= keep:
            break
    return tuple(ordered)


def _verdict(candidates: tuple[Candidate, ...]) -> Verdict:
    """Resolved, ambiguous or empty — the confidence, reported not hidden.

    One candidate, or a leader beating the runner-up by :data:`_DOMINANCE`, is a
    resolution. A close field is ambiguity: the contenders are still returned,
    but the resolver declines to promote a near-tie to an answer.
    """
    if not candidates:
        return Verdict.EMPTY
    if len(candidates) == 1:
        return Verdict.RESOLVED
    leader, runner_up = candidates[0].score, candidates[1].score
    if runner_up <= 0 or leader >= runner_up * _DOMINANCE:
        return Verdict.RESOLVED
    return Verdict.AMBIGUOUS


# --- small deterministic helpers -------------------------------------------

# A token is a run of letters/digits; camel and snake boundaries split names.
# ``HTTPClient`` -> ``HTTP``, ``Client``; ``fetch_data`` -> ``fetch``, ``data``.
_TOKEN = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")


def _tokenize(text: str) -> list[str]:
    """Lowercased, plural-folded sub-tokens of an identifier or phrase.

    Splitting is camel/snake-aware; folding is the same on the corpus and the
    query, so it can only unite a singular with its plural, never separate a
    word from itself — which is what lets ``"secret"`` reach the ``secrets``
    module without a real stemmer's risks.
    """
    return [_fold(match.group(0).lower()) for match in _TOKEN.finditer(text)]


def _fold(token: str) -> str:
    """Drop a simple trailing plural ``s`` so ``secrets`` and ``secret`` agree.

    Only a lone ``s`` on a token of real length is shed, and never from an ``ss``
    ending (``class``, ``process`` stay whole) — a conservative fold that catches
    the ordinary English plural and leaves the awkward ones exact.
    """
    if len(token) >= 4 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _content_tokens(query: str) -> list[str]:
    """The query's meaningful tokens: split, lowercased, stopwords removed."""
    return [token for token in _tokenize(query) if token not in _STOPWORDS]


def _squash(text: str) -> str:
    """A name reduced to bare letters and digits, for whole-name comparison."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _token_strength(token: str, symbol: Symbol) -> float:
    """A symbol-token match's score: base kind strength scaled by name coverage."""
    return (_S_SYMBOL + _kind_bonus(symbol)) * _fraction_of_name(token, symbol.name)


def _fraction_of_name(token: str, name: str) -> float:
    """How much of ``name`` the ``token`` accounts for, in [0, 1].

    A token equal to the whole name scores 1; a token that is one short piece of
    a long identifier scores low. Measured on the squashed letters so casing and
    separators don't distort the ratio.
    """
    squashed = _squash(name)
    if not squashed:
        return 0.0
    return min(len(_squash(token)) / len(squashed), 1.0)


def _role_weight(path: str) -> float:
    """A quiet ranking factor: test files are demoted, everything else neutral."""
    return _TEST_DEMOTION if _TEST_PATH.search(path) else 1.0


def _keep_best(slot: dict[str, Symbol], symbol: Symbol) -> None:
    """Record ``symbol`` for its path, letting a stronger kind win a shared slot."""
    current = slot.get(symbol.path)
    if current is None or _kind_rank(symbol) > _kind_rank(current):
        slot[symbol.path] = symbol


def _idf(document_frequency: int, total: int) -> float:
    """Rarity weight: a token matching few paths outweighs one matching many."""
    if document_frequency <= 0:
        return 0.0
    return 1.0 + math.log(total / document_frequency)


def _kind_rank(symbol: Symbol) -> int:
    """Order symbol kinds so the strongest wins a shared (token, path) slot."""
    return {SymbolKind.EXPORT: 2, SymbolKind.DEFINITION: 1}.get(symbol.kind, 0)


def _kind_bonus(symbol: Symbol) -> float:
    return _KIND_BONUS.get(symbol.kind, 0.0)


def _award(
    scores: dict[str, float],
    evidence: dict[str, list[tuple[float, str]]],
    path: str,
    amount: float,
    why: str,
) -> None:
    """Add ``amount`` to ``path``'s score and file the reason for the evidence."""
    scores[path] += amount
    evidence[path].append((amount, why))
