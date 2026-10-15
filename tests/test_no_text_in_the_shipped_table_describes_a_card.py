"""No text in the shipped table describes a card.

Promise: no text of the shipped capability table, at any depth, states a
card's memory size, an amount of a card's memory a server held, a fraction of
a card, a card's core count or a card's memory bandwidth. A text names a card
by nothing more than "the card" or "a card with little memory to spare".

The table states a model's facts. A text that gives a card's size, cores or
share of memory describes the one card a figure was read on, and a reader
takes that card's shape for a rule.

The check is by the shape of the words around a number (:data:`CARD_SHAPES`).
The controls below show that each shape sees what it is for, and leaves alone a
model's own size, a speed, a ratio of speeds and a cache hit rate. What it
cannot see: a size, a share or a count written out in words; a size given as
an amount "of memory" with no word that names a card, which a model's own need
is written as too; a card model or a machine named outright, which is the word
guard's. A qualitative share, such as "nearly all of the card", is what a text
may say in place of a figure.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

import pytest

from mcgyvr.capability import table_path

#: An amount of memory of the size a card holds: a number, then MB, GB or TB,
#: or their binary forms.
_SIZE = r"~?\d+(?:\.\d+)?[\s-]*[MGT]i?B\b"

#: What names a card, or the memory on one.
_CARD = r"(?:cards?|gpus?|vram|class(?:es)?|boards?|devices?)"

#: The shapes of a text that describe a card.
CARD_SHAPES: dict[str, re.Pattern[str]] = {
    "a card's memory size": re.compile(
        rf"{_SIZE}[\s-]*(?:of\s+)?{_CARD}\b"
        rf"|\b(?:cards?|gpus?|devices?)\s+(?:with|of|having)\s+{_SIZE}"
        rf"|\b(?:below|under|above|over|at least|at most)\s+{_SIZE}"
        rf"|(?:≥|≤|>=|<=)\s*{_SIZE}",
        re.IGNORECASE,
    ),
    "an amount of a card's memory a server held": re.compile(
        rf"{_SIZE}\s+(?:total|allocated|in use|free)\b"
        rf"|\b(?:freeing|freed|frees|allocating|allocated|allocates)\s+{_SIZE}",
        re.IGNORECASE,
    ),
    "a fraction of a card": re.compile(
        r"(?:(?<![\d.])0?\.\d+|\d+(?:\.\d+)?\s*%)\s+of\s+"
        rf"(?:(?:an?|the|its|each|one|this)\s+)?(?:{_SIZE}\s+)?"
        r"(?:cards?|gpus?|vram|devices?)\b"
        r"|gpu[-_ ]memory[-_ ]utili[sz]ation\s*[=:]?\s*0?\.\d+",
        re.IGNORECASE,
    ),
    "a card's core count": re.compile(
        r"\d+(?:[.,]\d+)?\s*x?\s+(?:fewer\s+|more\s+)?"
        r"(?:cuda\s+|tensor\s+|shader\s+|gpu\s+)?"
        r"(?:cores|sms|streaming multiprocessors)\b",
        re.IGNORECASE,
    ),
    "a card's memory bandwidth": re.compile(
        r"\d+(?:\.\d+)?\s*[MGT]i?B\s*/\s*s\b"
        r"|\d+(?:\.\d+)?\s*[MGT]i?B\s+(?:per|a)\s+second",
        re.IGNORECASE,
    ),
}


def _shapes_in(text: str) -> list[str]:
    return [shape for shape, pattern in CARD_SHAPES.items() if pattern.search(text)]


def _texts(node: Any, where: str = "") -> Iterator[tuple[str, str]]:
    """Every (location, text) of a JSON document, at any depth."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _texts(value, f"{where}.{key}" if where else str(key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _texts(value, f"{where}[{index}]")
    elif isinstance(node, str):
        yield where, node


def _shipped_texts() -> list[tuple[str, str]]:
    document = json.loads(table_path().read_text(encoding="utf-8"))
    return list(_texts(document))


# --- the shipped table --------------------------------------------------------


@pytest.mark.parametrize("shape", sorted(CARD_SHAPES))
def test_no_text_in_the_shipped_table_describes_a_card(shape: str) -> None:
    texts = _shipped_texts()
    assert texts

    offending = [
        f"{where}: {text}" for where, text in texts if CARD_SHAPES[shape].search(text)
    ]

    assert not offending, f"texts that state {shape}:\n" + "\n".join(offending)


# --- the controls: each shape sees what it is for, and nothing else ------------

#: Invented texts, one list per shape, that the shape must see.
SEEN: dict[str, tuple[str, ...]] = {
    "a card's memory size": (
        "it ran on a 24 GB card",
        "it needs 10GB of VRAM",
        "on a 20-GiB GPU",
        "a card with 40 GB",
        "not viable below ~10 GB",
        "a 32 GB class nobody declared",
        "needs ≥20 GB",
        "a 16GB card",
        "a 124GB card",
        "on a 24GB card",
    ),
    "an amount of a card's memory a server held": (
        "at 22.5 GB total",
        "with 21 GB allocated",
        "freeing 20 GB to 300 MB",
    ),
    "a fraction of a card": (
        "0.75 of a card",
        "0.8 of a 24 GB card",
        "95.5% of its VRAM",
        "gpu-memory-utilization 0.85",
    ),
    "a card's core count": (
        "a card with 3.1x fewer cores",
        "4096 CUDA cores",
        "40 SMs",
    ),
    "a card's memory bandwidth": (
        "bounded by 900 GB/s",
        "448 GB per second",
        "912GB/s",
    ),
}

#: Invented texts no shape may see: a model's size, speeds, ratios, a hit rate,
#: a qualitative share of a card, and a card named by no figure.
UNSEEN: tuple[str, ...] = (
    "a weight set of ~40 GB, not the file this row describes",
    "runs with ~7 GB on the card under partial offload",
    "Q4, 20.5 GB",
    "aggregate at 32 concurrent requests, 5.3x a single one",
    "prefix caching returned a 40.0% hit rate",
    "every worker receives the same <=4 KB system prompt",
    "92 tok/s against 40 tok/s",
    "with nearly all of the card allocated",
    "ran markedly slower than on a card of a larger class",
    "one card of the finding's class",
)


@pytest.mark.parametrize(
    ("shape", "text"),
    [(shape, text) for shape, texts in SEEN.items() for text in texts],
)
def test_each_shape_sees_what_it_is_for(shape: str, text: str) -> None:
    assert CARD_SHAPES[shape].search(text), (shape, text)


@pytest.mark.parametrize("text", UNSEEN)
def test_no_shape_sees_a_models_size_a_speed_or_a_plain_card(text: str) -> None:
    assert not _shapes_in(text), text
