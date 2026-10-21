"""Rank the files a request most likely means.

Resolution is deterministic and needs no model. A lookup corpus is derived from
an ``Index`` -- its paths, filename stems, directory names, and the symbols the
index already extracted -- and a query is scored against it twice: once as a
whole, for a caller who names a file or symbol outright, and once token by
token, rarity-weighted, with a bonus for the file that matched the most of the
query's distinct words.

Each candidate carries the evidence that earned its score, in a form a caller
can read, so a shortlist is explained rather than merely asserted. Scores are
adjusted for the role of the file (a test is demoted behind the code it
exercises), ranked and cut to a limit, and ``_verdict`` then says whether the
leader is the answer, whether the top of the shortlist is too close to call, or
whether nothing scored at all. A token-only shortlist that names a compound the
index does not hold is discarded as empty rather than answered from its parts,
so a made-up camelCase name never resolves on its fragments. What a caller does
with the shortlist -- reading excerpts under a token budget -- belongs to
``mcgyvr.orchestrator.read``.
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

# Words that say nothing about *which* file a query means. They are dropped
# before scoring, so a request phrased as prose ("the fetch helper function")
# is matched on "fetch" alone. The list holds two kinds: English function
# words, and the vocabulary of code talk -- "function", "method", "class",
# "helper", "code" -- which a caller uses to describe a target rather than to
# name one, and which on its own would match nearly every file in the repository.
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

# Weights for a match on the whole query rather than on its tokens. A filename
# mention is near-certain, a symbol named exactly as the query is the strongest
# code signal, and a matching filename stem alone is weaker than either.
_W_PATH_EXACT = 100.0
_W_SYMBOL_EXACT = 60.0
_W_STEM_EXACT = 45.0

# Base strengths for a single token found inside a longer name, ranking where it
# was found: inside a symbol name counts for most, inside a filename stem for
# less, in a directory name for least. Each is scaled by how much of the name
# the token accounts for.
_S_SYMBOL = 6.0
_S_STEM = 5.0
_S_PATH = 2.0

# Bonus for breadth: a file that matched a larger share of the query's distinct
# tokens is preferred over one that matched a single token very well.
_W_COVERAGE = 4.0

# Tests mention the code they exercise by name, so a query for a function
# matches its tests as readily as its definition. A test file keeps its score
# but is scaled down, so the definition leads unless nothing else matched. The
# pattern names the layouts that count: a `tests/` or `test/` directory, a
# `test_foo.py` module, a `foo_test.py`/`foo_test.go` module, or a
# `foo.test.ts`/`foo.spec.ts` sibling.
_TEST_DEMOTION = 0.6
_TEST_PATH = re.compile(
    r"(?:^|/)tests?/|(?:^|/)test_[^/]*$|(?:^|/)[^/]*_test\.[^/]+$|\.(?:test|spec)\.[^/]+$"
)

# An export is a file's public surface and the likelier target of a request, so
# a match on an export scores above the same match on a plain definition. The
# ranking is repeated in `_kind_rank`, which decides which of several symbols
# sharing a name and a path is kept.
_KIND_BONUS = {
    SymbolKind.EXPORT: 1.5,
    SymbolKind.DEFINITION: 1.0,
    SymbolKind.FIELD: 0.6,
    SymbolKind.PROPERTY: 0.4,
}

# The symbol kinds the corpus indexes as places a query can land. References and
# imports are recorded in the index but deliberately left out: a mention of a
# name at a call site says where code *uses* something, not where the answer to
# a request lives, and indexing them would let any file that merely mentions a
# name compete with the file that defines it.
_LANDING_KINDS = frozenset(
    {
        SymbolKind.DEFINITION,
        SymbolKind.EXPORT,
        SymbolKind.FIELD,
        SymbolKind.PROPERTY,
    }
)

# Kinds indexed for partial-token matching. FIELD and PROPERTY are landing
# targets when a query names them outright, but their names are so often generic
# words (``level``, ``color``, ``field``, ``document``) that letting them
# compete in token scoring swamps the stronger definition and export signals.
_TOKEN_KINDS = frozenset({SymbolKind.DEFINITION, SymbolKind.EXPORT})

# How far ahead of the runner-up the leader must be to count as the answer. A
# shortlist whose top two are closer than this factor is reported ambiguous
# rather than resolved, so a near-tie is never presented as a decision.
_DOMINANCE = 1.5

# A content token that reaches at most this many files is specific enough to be
# a confident signal on its own. A token found more widely is a generic word
# that on its own would match almost anything and must not decide an answer.
_SPECIFIC_DF_MAX = 2

# A whole-name symbol match that reaches at least this many files is a central
# API name: it is unambiguously a symbol, so naming it outright is a confident
# signal even though the token is not rare. Between `_SPECIFIC_DF_MAX` and this
# floor lies the ambiguous band -- an exact name in only a handful of files,
# which is too often a common noun used descriptively (``document`` for
# ``Document``) while the query's real subject is absent.
_CORE_API_DF_MIN = 6

# Without a specific token, a token-only shortlist still counts as a signal when
# the query matched on at least this many distinct generic tokens -- breadth
# that one incidental word does not provide.
_MIN_MATCHING_TOKENS = 2


class Verdict(StrEnum):
    """What a shortlist as a whole decided: one file, a tie, or nothing."""

    RESOLVED = "resolved"  # the leader is clear of the runner-up
    AMBIGUOUS = "ambiguous"  # several scored, and the leaders are too close
    EMPTY = "empty"  # nothing scored, so the query matched nothing indexed


@dataclass(frozen=True)
class Candidate:
    """A file in the shortlist: its path, its score, and why it scored."""

    path: str
    score: float
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class Resolution:
    """The shortlist for one query: its verdict and its candidates, best first."""

    query: str
    verdict: Verdict
    candidates: tuple[Candidate, ...]

    @property
    def best(self) -> Candidate | None:
        """The leading candidate, or None when nothing scored."""
        return self.candidates[0] if self.candidates else None


def resolve(index: Index, query: str, *, limit: int = 10) -> Resolution:
    """Rank the files ``query`` most likely means, over ``index``.

    The query is reduced to content tokens (stopwords dropped, plurals folded),
    a lookup corpus is built from the index, and two passes award each file a
    score with the evidence that earned it: the whole-query pass for a literal
    path, filename or symbol-name match, then the token pass for tokens found in
    symbol names, filename stems and directory names, rarity-weighted, plus a
    coverage bonus for the file that matched more of the query.

    ``limit`` is keyword-only and caps how many candidates are returned. Files
    with no positive score are dropped, the rest are ordered best first with
    ties broken by path, and ``_verdict`` turns the order into a verdict.

    Unless the whole query named a file or symbol literally, the shortlist is
    first held to an absolute signal: a compound name the index does not hold
    means the query named nothing and the shortlist is emptied rather than
    answered from its parts.

    Known limitation: the resolver is deterministic and does not identify a
    prose query's semantic subject. A query that names an absent proper noun --
    ``Celery`` in a Django repo, ``Svelte`` in a React repo, or
    ``Elasticsearch`` in a Nest repo -- while its other words match present
    symbols may therefore return a non-empty shortlist instead of
    ``Verdict.EMPTY``. This is accepted rather than treated as a bug:
    distinguishing an absent subject from an absent descriptive word needs
    semantic subject identification, which the resolver deliberately does not
    perform.
    """
    tokens = _content_tokens(query)
    corpus = _Corpus(index)

    scores: dict[str, float] = defaultdict(float)
    evidence: dict[str, list[tuple[float, str]]] = defaultdict(list)

    _score_whole_query(query, corpus, scores, evidence)
    named = set(scores)  # files the whole query named literally, if any
    _score_tokens(tokens, corpus, scores, evidence)

    # A token-only shortlist is still checked for an absolute signal: a compound
    # name the index does not hold means the query named nothing, so the
    # incidental matches of its parts are discarded rather than reported as an
    # answer. A whole-query literal match is exempt -- it already named a real
    # file or symbol.
    if not named and not _query_has_signal(query, corpus):
        scores.clear()
        evidence.clear()

    candidates = _rank(scores, evidence, limit)
    return Resolution(query=query, verdict=_verdict(candidates), candidates=candidates)


# The lookup tables a query is scored against, built once per resolve() call.


class _Corpus:
    """The indexed repository, cut into the lookups a query is matched against.

    Built once per resolution; none of it is specific to one query.
    """

    def __init__(self, index: Index) -> None:
        self.paths: frozenset[str] = frozenset(f.path for f in index.files)
        self.basenames: dict[str, set[str]] = defaultdict(set)

        # Symbols, keyed two ways: by the squashed form of the whole name, so a
        # query that names the symbol outright is answered without tokenising
        # it, and by each token the name splits into, so a partial name still
        # finds it. Both map a path to one symbol per path -- the best kind of
        # symbol found there for that key.
        self.symbol_exact: dict[str, dict[str, Symbol]] = defaultdict(dict)
        self.symbol_token: dict[str, dict[str, Symbol]] = defaultdict(dict)
        self.symbol_defined: dict[str, set[str]] = defaultdict(set)

        # Filename stems, whole and by token, each mapping to the paths with it.
        self.stem_exact: dict[str, set[str]] = defaultdict(set)
        self.stem_token: dict[str, set[str]] = defaultdict(set)

        # Tokens found in directory names, mapping to the paths beneath them.
        self.path_token: dict[str, set[str]] = defaultdict(set)

        for file in index.files:
            self._index_path(file.path)
        for symbol in index.symbols.all():
            if symbol.kind in _LANDING_KINDS:
                self._index_symbol(symbol)

    def _index_path(self, path: str) -> None:
        name = Path(path).name
        self.basenames[name.lower()].add(path)
        stem = Path(path).stem.lower()
        self.stem_exact[_squash(stem)].add(path)
        for token in _tokenize(stem):
            self.stem_token[token].add(path)
        # Directory names are weaker evidence than the filename, so they are
        # keyed by token only, never as a whole-query match.
        for part in Path(path).parent.parts:
            for token in _tokenize(part):
                self.path_token[token].add(path)

    def _index_symbol(self, symbol: Symbol) -> None:
        # A whole-name match must name the symbol exactly, so one slot per
        # squashed name holds the most public symbol found at each path.
        squashed = _squash(symbol.name)
        _keep_best(self.symbol_exact[squashed], symbol)
        # The file that defines a name is its answer; a file that merely
        # re-exports it is tracked apart so the whole-query pass can prefer the
        # definition over an aggregating barrel.
        if symbol.kind is SymbolKind.DEFINITION:
            self.symbol_defined[squashed].add(symbol.path)
        # Tokens are indexed separately for a partial match, and the slot keeps
        # the symbol for which the token accounts for the largest share of the
        # name -- the one the token actually characterises. That share is
        # measured by `_token_strength`, the same figure the scorer awards.
        # Fields and properties are kept only as whole-name landing targets; a
        # partial match on them is too often a coincidental generic word.
        if symbol.kind not in _TOKEN_KINDS:
            return
        for token in _tokenize(symbol.name):
            slot = self.symbol_token[token]
            current = slot.get(symbol.path)
            if current is None or _token_strength(token, symbol) > _token_strength(
                token, current
            ):
                slot[symbol.path] = symbol


# Pass one: the query taken as a whole, matched literally rather than by token.


def _score_whole_query(
    query: str,
    corpus: _Corpus,
    scores: dict[str, float],
    evidence: dict[str, list[tuple[float, str]]],
) -> None:
    """Award the files a query names outright, by path, symbol name or stem.

    This is the confident pass: a caller who names a file or a symbol gets a
    score large enough to settle the shortlist, and the token pass can only add
    to it. A partial match is not awarded here -- that is `_score_tokens`.

    The query is squashed whole -- case and separators folded, but stopwords and
    plurals kept -- so a symbol name that begins with a stopword
    ("fromRawHeaders", "isRedirect") or ends in a plural
    ("getNodeRequestOptions") still matches exactly rather than only as tokens.
    """
    raw = query.strip()
    for path in _paths_named_literally(raw, corpus):
        _award(scores, evidence, path, _W_PATH_EXACT, f'path matches "{raw}"')

    squashed = _squash(query)
    if not squashed:
        return
    defined_paths = corpus.symbol_defined.get(squashed, ())
    for symbol in corpus.symbol_exact.get(squashed, {}).values():
        is_definition = symbol.path in defined_paths
        # A symbol named outright is answered by the file that defines it; a
        # file that only re-exports the name earns no whole-query weight unless
        # no definition exists anywhere in the corpus.
        whole = _W_SYMBOL_EXACT if (is_definition or not defined_paths) else 0.0
        detail = f" ({symbol.detail})" if symbol.detail else ""
        verb = "defines" if is_definition else "exports"
        _award(
            scores,
            evidence,
            symbol.path,
            whole + _kind_bonus(symbol),
            f"{verb} {symbol.name}{detail}",
        )
    for path in corpus.stem_exact.get(squashed, ()):
        _award(
            scores, evidence, path, _W_STEM_EXACT, f'filename is "{Path(path).name}"'
        )


def _paths_named_literally(raw: str, corpus: _Corpus) -> set[str]:
    """The indexed paths ``raw`` names outright.

    A hit is the index path exactly as ``raw`` gives it, or any path whose
    filename equals ``raw`` ignoring case. An empty query names nothing.
    """
    if not raw:
        return set()
    hits: set[str] = set()
    if raw in corpus.paths:
        hits.add(raw)
    hits |= corpus.basenames.get(raw.lower(), set())
    return hits


# Pass two: the query's content tokens, each matched on its own and weighted by
# how rare it is across the corpus.


def _score_tokens(
    tokens: list[str],
    corpus: _Corpus,
    scores: dict[str, float],
    evidence: dict[str, list[tuple[float, str]]],
) -> None:
    """Award every file a content token reaches, weighted by the token's rarity.

    A token repeated in the query counts once, and a bare number or single
    character never counts at all: it matches anything that merely contains a
    digit or that letter, so it is noise rather than evidence. A token's weight
    is ``_idf`` over the files it reached, so a token present in every file
    contributes its base strength unchanged while a rare one contributes several
    times that. Once all tokens are scored, a file that matched a larger share
    of the query's distinct tokens is given the coverage bonus -- the breadth
    signal that separates a file matching three words from one matching a single
    word of the same request.
    """
    unique = [token for token in dict.fromkeys(tokens) if not _is_noise_token(token)]
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
    """Everything one token matches, as (path, strength, evidence) per file.

    Strength is the token's share of the symbol name for a symbol hit,
    ``_S_STEM`` scaled by its share of the stem for a filename hit, and the flat
    ``_S_PATH`` for a directory-name hit, the weakest of the three.
    """
    out: list[tuple[str, float, str]] = []
    for path, symbol in corpus.symbol_token.get(token, {}).items():
        detail = f" ({symbol.detail})" if symbol.detail else ""
        out.append(
            (
                path,
                _token_strength(token, symbol),
                f"{symbol.name}{detail} ~ {token!r}",
            )
        )
    for path in corpus.stem_token.get(token, set()):
        strength = _S_STEM * _fraction_of_name(token, Path(path).stem)
        out.append((path, strength, f"filename ~ {token!r}"))
    for path in corpus.path_token.get(token, set()):
        out.append((path, _S_PATH, f"path ~ {token!r}"))
    return out


def _is_noise_token(token: str) -> bool:
    """True for a token that cannot by itself name a file or symbol.

    A bare number or a single character matches nearly anything that merely
    contains a digit or that letter, so it is dropped from token scoring rather
    than treated as evidence. Whole-query literal matching still sees these
    tokens, so a name like ``v8`` or ``f`` is still found when spelled out.
    """
    return len(token) < 2 or token.isdigit()


def _has_broken_compound(query: str, corpus: _Corpus) -> bool:
    """True when one word of the query is a compound the corpus does not hold.

    A single, separator-free query word that splits into several content tokens
    -- ``persistInterval`` -- names one thing, not several. If that whole name
    is absent from the index, the parts matching separately is incidental and
    must not count as a signal. A word that names a path literally, or whose
    squashed whole matches a symbol or stem, is not broken; a word carrying a
    separator (``supports-color``) is left to the token pass, since directory
    names are only ever matched by token.
    """
    for word in query.split():
        if not word.isalnum():
            continue
        parts = _content_tokens(word)
        if len(parts) < 2:
            continue
        if _paths_named_literally(word, corpus):
            continue
        squashed = _squash(word)
        if squashed in corpus.symbol_exact or squashed in corpus.stem_exact:
            continue
        return True
    return False


def _query_has_signal(query: str, corpus: _Corpus) -> bool:
    """Whether the query named something the index actually holds.

    This is the absolute check behind the token-only shortlist. A compound word
    the index lacks means the query named nothing, so its parts matching
    separately must not count as an answer. Beyond that, a token-only answer is
    only confident when the query has a specific content token that matched, or
    when it matched across enough distinct generic tokens. A token is specific
    when it is rare (it reaches few files) or when it is a whole-name match for
    a central API symbol (it reaches many files, so it is plainly a symbol). A
    query whose only match is a single common word -- ``support`` across a
    ``supports-color`` directory, ``document`` across a ``Document`` class --
    has named its subject nowhere, so the shortlist is emptied rather than
    answered from that one incidental word.
    """
    if _has_broken_compound(query, corpus):
        return False
    generic = 0
    for token in dict.fromkeys(_content_tokens(query)):
        if _is_noise_token(token):
            continue
        document_frequency = _token_document_frequency(token, corpus)
        if document_frequency == 0:
            continue
        if document_frequency <= _SPECIFIC_DF_MAX:
            return True
        if (
            document_frequency >= _CORE_API_DF_MIN
            and _squash(token) in corpus.symbol_exact
        ):
            return True
        generic += 1
    return generic >= _MIN_MATCHING_TOKENS


def _token_document_frequency(token: str, corpus: _Corpus) -> int:
    """How many distinct files ``token`` reaches across the lookup corpus."""
    return len({path for path, _, _ in _collect(token, corpus)})


# Adjust each score for the role of its file, then order and cut the shortlist.


def _rank(
    scores: dict[str, float],
    evidence: dict[str, list[tuple[float, str]]],
    limit: int,
) -> tuple[Candidate, ...]:
    """Turn raw scores into the ordered shortlist.

    Every score is multiplied by ``_role_weight`` first, so a test file competes
    with the code it exercises at ``_TEST_DEMOTION`` of its raw score. Files are
    ordered by descending score and then by path, so a tie always breaks the
    same way, and the list is cut to ``limit``. A file with no positive score is
    not a candidate at all, and each candidate keeps the strongest few pieces of
    evidence that earned it.
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
    """The strongest reasons for a candidate, each said once, at most ``keep``.

    Reasons arrive with the amount each one awarded, so sorting by that amount
    puts the decisive evidence first; a reason worded the same way as one
    already kept adds nothing and is dropped.
    """
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
    """Read the shortlist as one answer: resolved, ambiguous, or empty.

    One candidate is resolved by definition. With more, the leader is the answer
    only if the runner-up scored nothing or the leader is at least
    ``_DOMINANCE`` times its score; anything closer is ambiguous.
    """
    if not candidates:
        return Verdict.EMPTY
    if len(candidates) == 1:
        return Verdict.RESOLVED
    leader, runner_up = candidates[0].score, candidates[1].score
    if runner_up <= 0 or leader >= runner_up * _DOMINANCE:
        return Verdict.RESOLVED
    return Verdict.AMBIGUOUS


# One tokeniser for queries and corpus names, so the same text splits the same
# way on both sides and their tokens are comparable.

# A camelCase/snake_case splitter: a capital run followed by a normal word, a
# normal word, a bare capital run, or a number, each taken as its own token.
_TOKEN = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")
# A maximal run of letters and digits, for a name whose parts the splitter
# shreds: ``b64decode`` splits to ``b``, ``64`` and ``decode``, and ``b`` and
# ``64`` are then dropped as noise, losing the very prefix that distinguishes
# the name. The whole run is kept beside the split parts so the name survives.
_WORD = re.compile(r"[A-Za-z0-9]+")


def _tokenize(text: str) -> list[str]:
    """Split text into lowercase, plural-folded tokens.

    A run that mixes letters and digits is also kept whole, so ``b64decode``
    still carries a ``b64decode`` token rather than only the split ``b``,
    ``64`` and ``decode`` parts, two of which never survive as evidence.
    """
    tokens = [_fold(match.group(0).lower()) for match in _TOKEN.finditer(text)]
    for match in _WORD.finditer(text):
        word = match.group(0)
        if any(ch.isalpha() for ch in word) and any(ch.isdigit() for ch in word):
            folded = _fold(word.lower())
            if folded not in tokens:
                tokens.append(folded)
    return tokens


def _fold(token: str) -> str:
    """Drop a trailing plural "s", so "files" and "file" are one token.

    "is" is left alone for being shorter than four characters and "class" for
    ending in "ss", so neither is mangled into a different word.
    """
    if len(token) >= 4 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _content_tokens(query: str) -> list[str]:
    """The query's tokens without the stopwords, in the order they appear."""
    return [token for token in _tokenize(query) if token not in _STOPWORDS]


def _squash(text: str) -> str:
    """Lowercase text and drop everything but letters and digits.

    "fetch_helper" and "fetchHelper" both squash to "fetchhelper", so the two
    spellings of a name compare equal.
    """
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _token_strength(token: str, symbol: Symbol) -> float:
    """What one symbol contributes for a token.

    Its base strength for the kind, scaled by how much of the symbol's name the
    token accounts for.
    """
    return (_S_SYMBOL + _kind_bonus(symbol)) * _fraction_of_name(token, symbol.name)


def _fraction_of_name(token: str, name: str) -> float:
    """How much of ``name`` a ``token`` accounts for, capped at 1.0.

    The ratio of squashed lengths: a token at least as long as the name covers
    all of it, while a short token in a long name covers proportionally less,
    which is what keeps "get" from scoring on "get_or_create_client" as strongly
    as the whole name would. An empty name yields 0.0.
    """
    squashed = _squash(name)
    if not squashed:
        return 0.0
    return min(len(_squash(token)) / len(squashed), 1.0)


def _role_weight(path: str) -> float:
    """The multiplier a path's score is adjusted by.

    A test file is demoted to ``_TEST_DEMOTION``; every other path counts in
    full.
    """
    return _TEST_DEMOTION if _TEST_PATH.search(path) else 1.0


def _keep_best(slot: dict[str, Symbol], symbol: Symbol) -> None:
    """Store ``symbol`` at its path unless a more public kind is already there."""
    current = slot.get(symbol.path)
    if current is None or _kind_rank(symbol) > _kind_rank(current):
        slot[symbol.path] = symbol


def _idf(document_frequency: int, total: int) -> float:
    """Inverse document frequency: ``1 + ln(total / document_frequency)``.

    A token found in every file weighs 1.0 and leaves the base strengths as they
    are; a rarer token weighs several times that. A token that reached no file
    weighs nothing, which keeps its contributions at zero and avoids dividing by
    zero.
    """
    if document_frequency <= 0:
        return 0.0
    return 1.0 + math.log(total / document_frequency)


def _kind_rank(symbol: Symbol) -> int:
    """Order symbol kinds by how public they are.

    Export ranks above definition, and any other kind lowest.
    """
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
    """Add ``amount`` to a path's score and record the reason beside the amount.

    Evidence is kept per path as (amount, reason), so `_top_evidence` can show
    the decisive reasons first and every award carries the reason it was made
    for.
    """
    scores[path] += amount
    evidence[path].append((amount, why))
