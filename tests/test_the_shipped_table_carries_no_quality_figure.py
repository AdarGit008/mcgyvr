"""The shipped table carries no quality figure.

Promises:

* No key of the shipped table, at any depth, is a quality figure or a
  benchmark score: the table says what a model costs to serve, never how well
  it does the work.
* No text of the shipped table names a coding benchmark, or states a score on
  one (a percentage something scored, or a gap in percentage points). A
  percentage that is not a score, such as a cache hit rate, may stay.
* No text of the shipped task catalog names a coding benchmark or says the
  capability table ranks or orders models: the catalog's warrants cite no
  figure the table does not carry.
* Every caveat id the product's code cites is one the shipped table carries,
  so a citation stays true when a caveat's text is rewritten.

The checks read the shipped files; they name no model and no figure of them.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from mcgyvr.capability import table_path
from mcgyvr.catalog import catalog_path

#: A key that names a quality figure or a benchmark score.
QUALITY_KEY = re.compile(
    r"quality|score|pass\d|pass_?at|pass@|humaneval|mbpp|evalplus|benchmark"
    r"|capabilities|measurements",
    re.IGNORECASE,
)

#: A coding benchmark named in text.
BENCHMARK = re.compile(
    r"human\s*-?\s*eval|evalplus|\bmbpp|swe-?bench|livecodebench|bigcodebench"
    r"|pass@\d|\bpass\d\b",
    re.IGNORECASE,
)

#: A score stated in text: something scored at a percentage, or a gap in points.
SCORE = re.compile(
    r"\bscor\w*\b[^.;]*?\d+(?:\.\d+)?\s*%|[+-]?\d+(?:\.\d+)?\s*pp\b",
    re.IGNORECASE,
)

#: A caveat id as the product's code cites one.
CAVEAT_ID = re.compile(r"\bCAV-\d+\b")

SRC = Path(__file__).resolve().parents[1] / "src" / "mcgyvr"


def _walk(node: Any, where: str = "") -> Iterator[tuple[str, str | None, Any]]:
    """Every (location, key, value) in a JSON document; key is None in a list."""
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{where}.{key}" if where else str(key)
            yield here, str(key), value
            yield from _walk(value, here)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            here = f"{where}[{index}]"
            yield here, None, value
            yield from _walk(value, here)


def _document(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _texts(path: Path) -> list[tuple[str, str]]:
    return [
        (where, value)
        for where, _, value in _walk(_document(path))
        if isinstance(value, str)
    ]


def test_no_key_of_the_shipped_table_is_a_quality_figure() -> None:
    keys = [
        where
        for where, key, _ in _walk(_document(table_path()))
        if key is not None and QUALITY_KEY.search(key)
    ]

    assert not keys, "keys that name a quality figure:\n" + "\n".join(keys)


def test_no_text_of_the_shipped_table_names_a_benchmark() -> None:
    named = [
        f"{where}: {text}"
        for where, text in _texts(table_path())
        if BENCHMARK.search(text)
    ]

    assert not named, "texts that name a coding benchmark:\n" + "\n".join(named)


def test_no_text_of_the_shipped_table_states_a_score() -> None:
    stated = [
        f"{where}: {text}" for where, text in _texts(table_path()) if SCORE.search(text)
    ]

    assert not stated, "texts that state a score:\n" + "\n".join(stated)


def test_the_score_shape_sees_a_score_and_not_a_hit_rate() -> None:
    """The control for the check above: it is not a ban on every percentage."""
    assert SCORE.search("the same weights scored 12.5% through another path")
    assert SCORE.search("a gap of +7.1pp between the two")
    assert not SCORE.search("prefix caching returned a 40.0% hit rate")
    assert not SCORE.search("it can free 90.5% of its memory")


def test_no_text_of_the_shipped_catalog_names_a_benchmark_or_a_ranking_table() -> None:
    said: list[str] = []
    for where, text in _texts(catalog_path()):
        if BENCHMARK.search(text):
            said.append(f"{where}: {text}")
        for sentence in re.split(r"(?<=[.;:])\s+", text):
            if "capability table" in sentence and re.search(
                r"\brank|\border", sentence, re.IGNORECASE
            ):
                said.append(f"{where}: {sentence}")

    assert not said, "catalog texts that cite a quality figure:\n" + "\n".join(said)


def test_every_caveat_the_code_cites_is_one_the_table_carries() -> None:
    carried = {str(c["id"]) for c in _document(table_path())["harness_caveats"]}
    cited = {
        f"{path.relative_to(SRC)}: {found}"
        for path in sorted(SRC.rglob("*.py"))
        for found in CAVEAT_ID.findall(path.read_text(encoding="utf-8"))
        if found not in carried
    }
    assert carried
    assert not cited, "caveats cited but not carried:\n" + "\n".join(sorted(cited))
