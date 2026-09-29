"""The shipped table names no machine and calls its numbers what they are.

Promises:

1. Every reading in the shipped table is keyed by a card class the table
   declares. A figure is an estimate for a class of card, not a reading of one
   machine.
2. The shipped table carries nothing that describes a machine, as far as a
   check by keys and by the shape of values can see:

   * every key, at every level of the file, is one the product declares for
     that level (:data:`mcgyvr.capability.DECLARED_KEYS`), so a new kind of
     fact (a machine, a host, where or when a reading was taken) cannot enter
     the table without first being declared in code, where a reviewer reads
     it; the loader refuses an undeclared key as well;
   * a declared card class carries exactly an id, a label and a nominal memory
     size;
   * no text value, at any depth, has the shape of a calendar date, a network
     address or a home path (:data:`MACHINE_SHAPES`).

   What these checks cannot see: a machine, a card model, a vendor or a host
   named in the prose of a declared field (a note, a class label or id, a
   caveat's detail); a date written in a form the shapes do not know; a number
   that belongs to one card (a core count, a memory bandwidth). Those are the
   word guard's and the reviewer's. The address shape cannot tell a four-part
   version number from an address, and would refuse one.
3. What the product prints about the shipped table calls its numbers estimates
   and never calls them measurements: the header of ``mcgyvr capabilities``
   carries the notice the capability module states and names the card classes
   the table declares, by their labels, and no line of that output says
   "measured".
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

import pytest

from mcgyvr import capability
from mcgyvr.capability import DECLARED_KEYS, READING_LISTS, load, table_path
from mcgyvr.cli import main

_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"

#: Shapes of a text value that describe a machine or a record of one.
MACHINE_SHAPES: dict[str, re.Pattern[str]] = {
    "a calendar date": re.compile(
        r"\b\d{4}-\d{2}-\d{2}\b"
        r"|\b\d{1,2}/\d{1,2}/\d{2,4}\b"
        rf"|\b\d{{1,2}} {_MONTH} \d{{4}}\b"
        rf"|\b{_MONTH} \d{{1,2}},? \d{{4}}\b",
        re.IGNORECASE,
    ),
    "a network address": re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"),
    "a home path": re.compile(r"(?:^|[\s(`'\"])(?:~/|/home/|/Users/|/root/)"),
}


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


def _entries(document: dict[str, Any]) -> Iterator[tuple[str, str, dict[str, Any]]]:
    """Every (level, location, entry) of the file, walked here, not by the loader.

    The levels are the ones the product declares keys for. Under ``backends``
    every key but the block's own notes names a backend, so the block's keys
    are read as notes only where their value is not an entry.
    """
    yield "table", "the table", document
    if "quality_metric" in document:
        yield "quality metric", "quality_metric", document["quality_metric"]
    for index, entry in enumerate(document.get("card_classes", [])):
        yield "card class", f"card_classes[{index}]", entry
    for index, entry in enumerate(document.get("harness_caveats", [])):
        yield "harness caveat", f"harness_caveats[{index}]", entry
    for index, model in enumerate(document.get("models", [])):
        yield "model row", f"models[{index}]", model
        for field in READING_LISTS:
            for place, entry in enumerate(model.get(field, [])):
                yield "reading", f"models[{index}].{field}[{place}]", entry
    backends = document.get("backends", {})
    yield (
        "backends block",
        "backends",
        {k: v for k, v in backends.items() if not isinstance(v, dict)},
    )
    for name, entry in backends.items():
        if isinstance(entry, dict):
            yield "backend", f"backends.{name}", entry
    for index, entry in enumerate(document.get("concurrency_findings", [])):
        yield "concurrency finding", f"concurrency_findings[{index}]", entry


def test_every_key_in_the_shipped_table_is_one_the_product_declares() -> None:
    seen: set[str] = set()
    undeclared: list[str] = []
    for level, where, entry in _entries(_document()):
        seen.add(level)
        undeclared.extend(
            f"{where}: {key!r} (a {level} declares {sorted(DECLARED_KEYS[level])})"
            for key in entry
            if key not in DECLARED_KEYS[level]
        )

    assert not undeclared, "keys the product does not declare:\n" + "\n".join(
        undeclared
    )
    assert seen == set(DECLARED_KEYS), "a declared level this walk never reached"


def test_the_loader_reads_the_shipped_table_under_the_same_closed_keys() -> None:
    assert load(table_path()).models


def test_a_card_class_carries_only_an_id_a_label_and_its_memory() -> None:
    for declared in _document()["card_classes"]:
        assert set(declared) == DECLARED_KEYS["card class"], declared
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
def test_the_capabilities_header_names_the_classes_the_table_declares(
    capsys: pytest.CaptureFixture[str], fit: bool
) -> None:
    labels = [c.label for c in load().card_classes]
    assert labels

    header = _headers(_printed(capsys, *(["--vram", _roomy_card_gb()] if fit else [])))[
        0
    ]

    for label in labels:
        assert label in header, header


@pytest.mark.parametrize("fit", [False, True], ids=["whole-table", "fitting-a-card"])
def test_nothing_printed_about_the_table_calls_it_measured(
    capsys: pytest.CaptureFixture[str], fit: bool
) -> None:
    lines = _printed(capsys, *(["--vram", _roomy_card_gb()] if fit else []))

    said = [line for line in lines if re.search(r"\b(?:un)?measured\b", line, re.I)]
    assert not said, "\n".join(said)
    assert not [line for line in _headers(lines) if "measur" in line.lower()]
