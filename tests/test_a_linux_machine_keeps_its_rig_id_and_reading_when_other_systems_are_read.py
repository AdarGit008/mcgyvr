"""A Linux machine keeps its rig id and its reading when other systems are read.

The reader learned macOS and Windows; a machine it read before must not become
another machine, nor read differently. For every invented machine the reading
it gave before (its identity, cards, sources, unsized list, memory and unread
fields, the kernel release aside, which is the test host's) and its rig id are
pinned here as the reader before the other systems gave them. What the reading
adds (the host, the CPU, the resources, a card's kind and backend) is new and
leaves the old parts as they were.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from tests.machine_shapes import shapes
from tests.machinereader import machine_reading

#: Per invented machine: sixteen hex digits of sha256 over the reading's old
#: parts, and its rig id (None where the id is refused), both as the reader
#: made them before it read other systems.
BEFORE: dict[str, tuple[str, str | None]] = {
    "bare": (
        "83929bcf4bbfabbf",
        "rig-9122eefcc127b907343fdb21b380e5cacf397e66083778a78d221f9e46999f6c",
    ),
    "bare-local-server": (
        "66475bcd70d02550",
        "rig-7649c54d24e153e5ab804d75fa674b8b52a2798e0fccebe01a8989e73670d58f",
    ),
    "bare-remote-server": (
        "817bafdaf839a7af",
        "rig-ce2cd38decc5d051382aa06ab9ddff1504e8b2fb2373abce85cf2eb8da7df575",
    ),
    "one-card": (
        "78d7ce90c7653493",
        "rig-8ea88d34f1f6ce61004527c922fbd9ee103a390bf11e086fd83fbc82f2ee7fb9",
    ),
    "four-equal": (
        "4dfa1479ca19cb19",
        "rig-2f5b3701d004520ba967f3eb14726e9e9a2b88416643a52b4a75b54dbb7dae70",
    ),
    "two-sizes": (
        "e2855ffc34eb68aa",
        "rig-407f2e142b9b99094371143b95668c7d390de19ceb3d7d6cf62a3feaa75f99c4",
    ),
    "several-sizes": (
        "63b5107131d2d484",
        "rig-b367ab5d72226ed951d887cc0622072b737e2b447eacec2d29dce8ed839068aa",
    ),
    "busy-card": (
        "0b27f9331e4fc5dc",
        "rig-49f31cdbc6eae9577b7d006f7c145d2c9ee16e209d64a9ed038bbeaf3af3a987",
    ),
    "busy-beside-free": (
        "c8bc7f5d948bb92c",
        "rig-abfaac40a0288a3e97587c52386a4f86024745b0d204e2c329b21adacc6d41a2",
    ),
    "unreadable-size": ("519a78a082b621d8", None),
    "other-vendor": ("1172e8c915e3391c", None),
    "other-vendor-no-reader": (
        "7c928ce79b3c59dc",
        "rig-7463555409dce2750fdb70a65e6a4de3fdbd7cf6cdfa61901675c52b94f77306",
    ),
    "mixed-vendors": (
        "942e3f63cf6fa801",
        "rig-f1c128ffce243c70f59e5b1c469a4ab87507cea0c5cc435af5d66311b5875651",
    ),
    "no-reader": (
        "65d92b3192124a08",
        "rig-d2f2af0decb81d8a6583bbcc5cf21cbdff490ebbe2a7d0dc8930269207cc8094",
    ),
    "same-cards-here": (
        "57147103dac58346",
        "rig-af929df459c27da4f02f99b1d5f3a7e2ac8def6999a03cdf332f3e11020f1fd8",
    ),
    "same-cards-there": (
        "cf7715aff306ef2a",
        "rig-62f7e7253b6c6d2cb2415f80125cf3d42ed06b9494169d3ade3b2ed03b7b1e2d",
    ),
    "unreadable-size-first": ("c6f9be612f1cb4d8", None),
}

#: A card's fields before the reader read other systems.
CARD_FIELDS = ("vendor", "index", "total_mib", "used_mib", "free_mib", "name")


def _old_parts_digest(document: dict[str, Any]) -> str:
    parts = {
        "machine": {k: v for k, v in document["machine"].items() if k != "kernel"},
        "cards": [{k: c[k] for k in CARD_FIELDS} for c in document["cards"]],
        "card_sources": document["card_sources"],
        "unsized": document["unsized"],
        "memory": document["memory"],
        "unread": document["unread"],
    }
    raw = json.dumps(parts, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def test_every_invented_machine_is_pinned() -> None:
    assert sorted(BEFORE) == sorted(machine.label for machine in shapes())


@pytest.mark.parametrize("machine", shapes(), ids=lambda m: m.label)
def test_the_reading_and_the_rig_id_are_what_they_were(
    machine: Any, tmp_path: Path
) -> None:
    from mcgyvr.fleet import ids

    document = machine_reading(machine, tmp_path)
    digest, rig_id = BEFORE[machine.label]
    assert _old_parts_digest(document) == digest
    if rig_id is None:
        with pytest.raises(ValueError):
            ids.rig_id(document)
    else:
        assert ids.rig_id(document) == rig_id
    assert document["host"]["os"] == "linux"
    for card in document["cards"]:
        assert set(card) == {*CARD_FIELDS, "kind", "backend"}
        assert card["kind"] == "gpu"


def test_a_reading_with_no_unified_gpu_hashes_its_cards_as_before() -> None:
    from mcgyvr.fleet import ids

    reading = {
        "machine": {"id": "0123456789abcdef"},
        "cards": [{"vendor": "nvidia", "index": 0, "name": "Example", "total_mib": 7}],
        "unread": [],
        "unsized": [],
    }
    assert ids.rig_id(reading) == ids.digest(
        "rig-",
        {
            "machine_id": "0123456789abcdef",
            "cards": [{"name": "Example", "total_mib": 7}],
        },
    )
