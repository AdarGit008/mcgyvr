"""Extract definitions, references, exports and imports from source files.

One row of :data:`_LANGUAGES` per supported language names it, the file suffixes
that select it and the extractor it dispatches to; :func:`language_of` and
:func:`extract` read nothing else. Python is parsed with :mod:`ast`
(:mod:`~mcgyvr.orchestrator.languages.python`); JavaScript/TypeScript, Go, Rust and
Java are parsed with bundled tree-sitter grammars on one shared engine
(:mod:`~mcgyvr.orchestrator.languages.engine`), one module per language under
:mod:`mcgyvr.orchestrator.languages`, each of which states its own rules. Every
extracted item is returned as a :class:`Symbol` carrying its :class:`SymbolKind` and
the file path plus 1-based line where it was found.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from mcgyvr.orchestrator.languages import go, java, javascript, python, rust
from mcgyvr.orchestrator.languages.model import Symbol, SymbolKind

__all__ = ["Symbol", "SymbolKind", "extract", "language_of"]


@dataclass(frozen=True)
class _Language:
    """One supported language: the name the index records, the suffixes that
    select it, and its extractor."""

    name: str
    suffixes: tuple[str, ...]
    extract: Callable[[str, bytes], list[Symbol]]


#: Every language with a symbol extractor. The names are persisted (index cache,
#: build stats), so a rename here is a cache-format change.
_LANGUAGES: tuple[_Language, ...] = (
    _Language("python", python.SUFFIXES, python.extract),
    _Language("js/ts", javascript.SUFFIXES, javascript.extract),
    _Language("go", go.SUFFIXES, go.extract),
    _Language("rust", rust.SUFFIXES, rust.extract),
    _Language("java", java.SUFFIXES, java.extract),
)


def _language_for(path: str) -> _Language | None:
    for language in _LANGUAGES:
        if path.endswith(language.suffixes):
            return language
    return None


def language_of(path: str) -> str | None:
    """Return the name of the language ``path``'s extension selects, else None."""
    language = _language_for(path)
    return language.name if language is not None else None


def extract(path: str, source: bytes) -> list[Symbol]:
    """Extract the symbols of ``source``, dispatching on :func:`language_of`.

    Files with an unrecognised extension yield an empty list.
    """
    language = _language_for(path)
    return language.extract(path, source) if language is not None else []
