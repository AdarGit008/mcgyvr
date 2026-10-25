"""What a contract says it creates or changes, read from its own words.

A contract's `interface` declares the symbols it creates, and its `task` may
state a rename (``rename old to new``). Decomposition reads both to state a
dependency on a symbol a sibling creates (`mcgyvr.orchestrator.decompose`), and
the dependency tree reads them to tell what a dependent waits for
(`mcgyvr.tree`). Both read them here, so the two agree on what a contract
provides.
"""

from __future__ import annotations

import re

from mcgyvr.orchestrator.symbols import SymbolKind, extract

#: The keywords that declare the name after them, for an interface the parser
#: cannot read as source — a bare header such as ``def f(x: int) -> str`` with
#: no body. The parser is asked first and this only when it read nothing.
DECLARING = r"(?:def|class|function|fn|func|interface|type|struct|enum|trait)"

#: A rename a contract's task states: ``rename old to new``, either name in
#: backticks or quotes, and ``->``/``→``/``as`` for ``to``, so a sibling may
#: depend on the new name before the rename has landed.
RENAME = re.compile(
    r"(?i:\brenam(?:e|es|ed|ing))\s+[`'\"]?([A-Za-z_$][\w$]*)[`'\"]?(?:\(\))?"
    r"\s+(?:to|as|->|→)\s+[`'\"]?([A-Za-z_$][\w$]*)"
)

#: A name as the languages the index reads spell one.
IDENTIFIER = re.compile(r"(?<![\w$])[A-Za-z_$][\w$]*")


def declared_names(path: str, interface: str) -> frozenset[str]:
    """The names `interface` declares, read as source of `path`.

    The parser the index uses is asked first; a bare header it reads nothing
    from counts by the declaring keyword before the name.
    """
    if not interface.strip():
        return frozenset()
    parsed = extract(path, interface.encode("utf-8", "surrogateescape"))
    if parsed:
        return frozenset(s.name for s in parsed if s.kind is SymbolKind.DEFINITION)
    return frozenset(
        re.findall(rf"(?<![\w$]){DECLARING}\s+([A-Za-z_$][\w$]*)", interface)
    )


def renames(task: str) -> tuple[tuple[str, str], ...]:
    """Every ``(old, new)`` rename `task` states, in the order it states them."""
    return tuple((old, new) for old, new in RENAME.findall(task))


def identifiers(*texts: str) -> frozenset[str]:
    """Every name spelled in `texts`."""
    return frozenset(name for text in texts for name in IDENTIFIER.findall(text))
