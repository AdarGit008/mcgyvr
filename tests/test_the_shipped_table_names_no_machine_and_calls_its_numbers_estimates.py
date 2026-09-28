"""The shipped table names no machine and calls its numbers what they are.

Promises:

1. Every reading in the shipped table is keyed by a card class the table
   declares. A figure is an estimate for a class of card, not a reading of one
   machine.
2. The shipped table carries nothing that describes a machine. The rule is
   structural, by keys and by the shape of values, never by a list of names:

   * no key, at any depth, has a word among its underscore-separated parts
     that describes a machine or where and when a reading was taken
     (:data:`MACHINE_KEY_WORDS`);
   * a declared card class carries exactly an id, a label and a nominal memory
     size, so there is no place in it for a card model, a vendor or a host;
   * no text value, at any depth, has the shape of a calendar date, a network
     address or a file path (:data:`MACHINE_SHAPES`).
3. What the product prints about the shipped table calls its numbers estimates
   and never calls them measurements: the header of ``mcgyvr capabilities``
   carries the notice the capability module states, and no line of that output
   says "measured".
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

import pytest

from mcgyvr import capability
from mcgyvr.capability import load, table_path
from mcgyvr.cli import main

#: Words that, as one underscore-separated part of a key, make the key describe
#: a machine or the circumstances of a reading rather than a model or a class.
MACHINE_KEY_WORDS = frozenset(
    {
        "rig",
        "rigs",
        "host",
        "hosts",
        "hostname",
        "machine",
        "machines",
        "cpu",
        "gpu",
        "cores",
        "ram",
        "dimm",
        "date",
        "dated",
        "path",
        "repo",
        "vendored",
        "measured",
    }
)

#: Shapes of a text value that describe a machine or a record of one.
MACHINE_SHAPES: dict[str, re.Pattern[str]] = {
    "a calendar date": re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    "a network address": re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"),
    "a home path": re.compile(r"(?:^|\s)~/"),
    "a file path": re.compile(r"\b[\w.-]+(?:/[\w.-]+)+\.[a-z]{1,5}\b"),
}

#: The keys a declared card class carries, and no others.
CLASS_KEYS = frozenset({"id", "label", "memory_gb"})

#: Lists on a model row whose entries are readings.
READING_LISTS = (
    "quality",
    "throughput_tok_s",
    "invalid_measurements",
    "disputed_measurements",
)


def _document() -> dict[str, Any]:
    raw: dict[str, Any] = json.loads(table_path().read_text(encoding="utf-8"))
    return raw


def _walk(node: Any, where: str = "") -> Iterator[tuple[str, str | None, Any]]:
    """Every (location, key, value) in the document; key is None in a list."""
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{where}.{key}" if where else key
            yield here, key, value
            yield from _walk(value, here)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            here = f"{where}[{index}]"
            yield here, None, value
            yield from _walk(value, here)


def _declared(document: dict[str, Any]) -> set[str]:
    classes = document.get("card_classes")
    assert isinstance(classes, list) and classes, "the table declares no card classes"
    return {str(c["id"]) for c in classes}


# --- 1. every reading is keyed by a declared class ---------------------------


def test_every_reading_in_the_file_names_a_class_the_table_declares() -> None:
    document = _document()
    declared = _declared(document)
    stray: list[str] = []
    for model in document["models"]:
        for field in READING_LISTS:
            for index, entry in enumerate(model.get(field, [])):
                if entry.get("card_class") not in declared:
                    stray.append(
                        f"{model['id']}.{field}[{index}]: {entry.get('card_class')!r}"
                    )
    for where, key, value in _walk(document):
        if key == "card_class" and value not in declared:
            stray.append(f"{where}: {value!r}")
    assert not stray, "readings keyed by no declared class:\n" + "\n".join(stray)


def test_every_reading_the_loader_hands_out_names_a_declared_class() -> None:
    table = load()
    declared = {c.id for c in table.card_classes}
    readings = [
        m for model in table.models for m in (*model.quality, *model.throughput)
    ]

    assert readings
    assert {m.card_class for m in readings} <= declared


# --- 2. nothing in the table describes a machine -----------------------------


def test_no_key_in_the_shipped_table_describes_a_machine() -> None:
    offending = [
        where
        for where, key, _ in _walk(_document())
        if key is not None
        and MACHINE_KEY_WORDS & set(key.lower().strip("_").split("_"))
    ]
    assert not offending, "keys that describe a machine:\n" + "\n".join(offending)


def test_a_card_class_carries_only_an_id_a_label_and_its_memory() -> None:
    for declared in _document()["card_classes"]:
        assert set(declared) == CLASS_KEYS, declared
        assert isinstance(declared["id"], str) and declared["id"]
        assert isinstance(declared["label"], str) and declared["label"]
        assert isinstance(declared["memory_gb"], int | float)
        assert declared["memory_gb"] > 0


@pytest.mark.parametrize("shape", sorted(MACHINE_SHAPES))
def test_no_text_in_the_shipped_table_has_the_shape_of_a_machine_record(
    shape: str,
) -> None:
    pattern = MACHINE_SHAPES[shape]
    offending = [
        f"{where}: {value}"
        for where, _, value in _walk(_document())
        if isinstance(value, str) and pattern.search(value)
    ]
    assert not offending, f"text with the shape of {shape}:\n" + "\n".join(offending)


# --- 3. what the product prints calls the numbers estimates -------------------


def _printed(capsys: pytest.CaptureFixture[str], *argv: str) -> list[str]:
    assert main(["capabilities", *argv]) == 0
    return capsys.readouterr().out.splitlines()


def _headers(lines: list[str]) -> list[str]:
    return [line for line in lines if line.strip() and not line[0].isspace()]


def _roomy_card_gb() -> str:
    """A card size every shipped row fits, read from the table, not restated."""
    largest = max(m.vram_gb_working for m in load().models)
    return f"{largest * 4:g}"


@pytest.mark.parametrize("fit", [False, True], ids=["whole-table", "fitting-a-card"])
def test_the_capabilities_header_calls_the_numbers_estimates(
    capsys: pytest.CaptureFixture[str], fit: bool
) -> None:
    notice = capability.ESTIMATES_NOTICE
    assert "estimate" in notice.lower()

    lines = _printed(capsys, *(["--vram", _roomy_card_gb()] if fit else []))
    headers = _headers(lines)

    assert headers, lines
    assert notice in headers[0], headers[0]


@pytest.mark.parametrize("fit", [False, True], ids=["whole-table", "fitting-a-card"])
def test_nothing_printed_about_the_table_calls_it_measured(
    capsys: pytest.CaptureFixture[str], fit: bool
) -> None:
    lines = _printed(capsys, *(["--vram", _roomy_card_gb()] if fit else []))

    said = [line for line in lines if re.search(r"\b(?:un)?measured\b", line, re.I)]
    assert not said, "\n".join(said)
    assert not [line for line in _headers(lines) if "measur" in line.lower()]
