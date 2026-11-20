"""A device's name is cleaned by one rule before it is matched.

The tools and the table name one card differently: with or without the vendor
and product-line words, with ``(R)`` and ``(TM)``, with the memory size in the
name or in parentheses. A card's or chip's name is matched whole once those are
dropped (:func:`mcgyvr.machine_capability.card_key`), so a ``Ti`` or a
``Laptop`` keeps a card apart from the one without it, and a name that is all
such words matches nothing. A CPU's name also drops its clock, its graphics and
its core count (:func:`mcgyvr.machine_capability.cpu_words`), and a listed model
must be a run of whole words of it, so ``7600`` never matches ``7600X``. The
names below are spellings in the vendors' and the tools' styles; no reading of a
machine is used.
"""

from __future__ import annotations

import pytest

from mcgyvr.machine_capability import card_key, cpu_words


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("NVIDIA GeForce RTX 3060 Ti", "rtx 3060 ti"),
        ("GeForce RTX 3060 Ti", "rtx 3060 ti"),
        ("GeForce RTX 2080 Super", "rtx 2080 super"),
        ("NVIDIA GeForce RTX 2080 SUPER", "rtx 2080 super"),
        ("GeForce RTX 3050 (8 GB)", "rtx 3050"),
        ("NVIDIA GeForce GTX 1060 6GB", "gtx 1060"),
        ("GeForce GTX 1650 (G5)", "gtx 1650"),
        ("NVIDIA GeForce RTX 4090 Laptop GPU", "rtx 4090 laptop"),
        ("Intel(R) Arc(TM) A770 Graphics", "arc a770"),
        ("Intel Arc A770 Graphics (16GB)", "arc a770"),
        ("AMD Radeon RX 7900 XTX", "radeon rx 7900 xtx"),
        ("AMD Radeon RX 480 8GB", "radeon rx 480"),
        ("Apple M2 Max GPU", "m2 max"),
        ("M3 Max (14-core CPU, 30-core GPU)", "m3 max"),
        ("PCI 0x1002:0x744c", "pci 0x1002:0x744c"),
        ("Intel Graphics (Core Ultra 5 135U, Series 1)", ""),
    ],
)
def test_a_card_name_is_cleaned_to_its_key(name: str, key: str) -> None:
    assert card_key(name) == key


def test_a_ti_keeps_a_card_apart_from_the_one_without_it() -> None:
    assert card_key("NVIDIA GeForce RTX 4060 Ti") != card_key("GeForce RTX 4060")


@pytest.mark.parametrize(
    ("name", "words"),
    [
        ("Intel(R) Core(TM) i7-8700K CPU @ 3.70GHz", ("i7-8700k",)),
        ("Core i7-8700K", ("i7-8700k",)),
        ("13th Gen Intel(R) Core(TM) i9-13900K", ("13th", "gen", "i9-13900k")),
        ("AMD Ryzen 9 5950X 16-Core Processor", ("ryzen", "9", "5950x")),
        ("AMD Ryzen AI 9 HX 370 w/ Radeon 890M", ("ryzen", "ai", "9", "hx", "370")),
        ("AMD Ryzen 5 5600G with Radeon Graphics", ("ryzen", "5", "5600g")),
        (
            "AMD Ryzen Threadripper PRO 7995WX 96-Cores",
            ("ryzen", "threadripper", "pro", "7995wx"),
        ),
        ("Intel(R) Xeon(R) W-2295 CPU @ 3.00GHz", ("xeon", "w-2295")),
        ("Intel(R) Core(TM) Ultra 7 155H", ("ultra", "7", "155h")),
    ],
)
def test_a_cpu_name_is_cleaned_to_its_words(name: str, words: tuple[str, ...]) -> None:
    assert cpu_words(name) == words
