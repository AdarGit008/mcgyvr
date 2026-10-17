""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from mcgyvr.orchestrator.index import Index
from mcgyvr.orchestrator.symbols import Symbol, SymbolKind

#er
#
#
#
#
#
#
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

#
#
#
_W_PATH_EXACT = 100.0
_W_SYMBOL_EXACT = 60.0
_W_STEM_EXACT = 45.0

#
#
#g.
_S_SYMBOL = 6.0
_S_STEM = 5.0
_S_PATH = 2.0

#
#
_W_COVERAGE = 4.0

#
#st
#
#
#
_TEST_DEMOTION = 0.6
_TEST_PATH = re.compile(
    r"(?:^|/)tests?/|(?:^|/)test_[^/]*$|(?:^|/)[^/]*_test\.[^/]+$|\.(?:test|spec)\.[^/]+$"
)

#
#
#
_KIND_BONUS = {SymbolKind.EXPORT: 1.5, SymbolKind.DEFINITION: 1.0}

#
#
#
#
#
_LANDING_KINDS = frozenset({SymbolKind.DEFINITION, SymbolKind.EXPORT})

#
#
#
_DOMINANCE = 1.5


class Verdict(StrEnum):
    ""

    RESOLVED = "resolved"  #
    AMBIGUOUS = "ambiguous"  #
    EMPTY = "empty"  #


@dataclass(frozen=True)
class Candidate:
    ""

    path: str
    score: float
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class Resolution:
    ""

    query: str
    verdict: Verdict
    candidates: tuple[Candidate, ...]

    @property
    def best(self) -> Candidate | None:
        ""
        return self.candidates[0] if self.candidates else None


def resolve(index: Index, query: str, *, limit: int = 10) -> Resolution:
    ""
    tokens = _content_tokens(query)
    corpus = _Corpus(index)

    scores: dict[str, float] = defaultdict(float)
    evidence: dict[str, list[tuple[float, str]]] = defaultdict(list)

    _score_whole_query(query, tokens, corpus, scores, evidence)
    _score_tokens(tokens, corpus, scores, evidence)

    candidates = _rank(scores, evidence, limit)
    return Resolution(query=query, verdict=_verdict(candidates), candidates=candidates)


#


class _Corpus:
    ""

    def __init__(self, index: Index) -> None:
        self.paths: frozenset[str] = frozenset(f.path for f in index.files)
        self.basenames: dict[str, set[str]] = defaultdict(set)

        #
        #
        #so a
        #
        self.symbol_exact: dict[str, dict[str, Symbol]] = defaultdict(dict)
        self.symbol_token: dict[str, dict[str, Symbol]] = defaultdict(dict)

        #
        self.stem_exact: dict[str, set[str]] = defaultdict(set)
        self.stem_token: dict[str, set[str]] = defaultdict(set)

        #
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
        #
        for part in Path(path).parent.parts:
            for token in _tokenize(part):
                self.path_token[token].add(path)

    def _index_symbol(self, symbol: Symbol) -> None:
        #
        #
        _keep_best(self.symbol_exact[_squash(symbol.name)], symbol)
        #
        #nd
        #
        #
        for token in _tokenize(symbol.name):
            slot = self.symbol_token[token]
            current = slot.get(symbol.path)
            if current is None or _token_strength(token, symbol) > _token_strength(
                token, current
            ):
                slot[symbol.path] = symbol


#


def _score_whole_query(
    query: str,
    tokens: list[str],
    corpus: _Corpus,
    scores: dict[str, float],
    evidence: dict[str, list[tuple[float, str]]],
) -> None:
    ""
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
    ""
    if not raw:
        return set()
    hits: set[str] = set()
    if raw in corpus.paths:
        hits.add(raw)
    hits |= corpus.basenames.get(raw.lower(), set())
    return hits


#


def _score_tokens(
    tokens: list[str],
    corpus: _Corpus,
    scores: dict[str, float],
    evidence: dict[str, list[tuple[float, str]]],
) -> None:
    ""
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
    ""
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


#


def _rank(
    scores: dict[str, float],
    evidence: dict[str, list[tuple[float, str]]],
    limit: int,
) -> tuple[Candidate, ...]:
    ""
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
    ""
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
    ""
    if not candidates:
        return Verdict.EMPTY
    if len(candidates) == 1:
        return Verdict.RESOLVED
    leader, runner_up = candidates[0].score, candidates[1].score
    if runner_up <= 0 or leader >= runner_up * _DOMINANCE:
        return Verdict.RESOLVED
    return Verdict.AMBIGUOUS


#

#
#
_TOKEN = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")


def _tokenize(text: str) -> list[str]:
    ""
    return [_fold(match.group(0).lower()) for match in _TOKEN.finditer(text)]


def _fold(token: str) -> str:
    ""
    if len(token) >= 4 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _content_tokens(query: str) -> list[str]:
    ""
    return [token for token in _tokenize(query) if token not in _STOPWORDS]


def _squash(text: str) -> str:
    ""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _token_strength(token: str, symbol: Symbol) -> float:
    ""
    return (_S_SYMBOL + _kind_bonus(symbol)) * _fraction_of_name(token, symbol.name)


def _fraction_of_name(token: str, name: str) -> float:
    ""
    squashed = _squash(name)
    if not squashed:
        return 0.0
    return min(len(_squash(token)) / len(squashed), 1.0)


def _role_weight(path: str) -> float:
    ""
    return _TEST_DEMOTION if _TEST_PATH.search(path) else 1.0


def _keep_best(slot: dict[str, Symbol], symbol: Symbol) -> None:
    ""
    current = slot.get(symbol.path)
    if current is None or _kind_rank(symbol) > _kind_rank(current):
        slot[symbol.path] = symbol


def _idf(document_frequency: int, total: int) -> float:
    ""
    if document_frequency <= 0:
        return 0.0
    return 1.0 + math.log(total / document_frequency)


def _kind_rank(symbol: Symbol) -> int:
    ""
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
    ""
    scores[path] += amount
    evidence[path].append((amount, why))
