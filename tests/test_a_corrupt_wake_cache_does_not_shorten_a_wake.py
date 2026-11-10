"""A wake record left in the clock directory may never shorten or abort a wake.

A wake used to read the last `up`'s timing from ``<host>.wake.json`` in the
clock directory before spawning the door, to warn when a wake ran long; the
warning never printed, and the timing is no longer written or read. A file
an older mcgyvr left there, in any shape (a good record, a crashed process's
truncated write, bytes that are not text, a directory where a file was), is
read by nothing, and a wake beside it runs as any other does.

The clock directory sits at a predictable path in a world-writable place
(``/tmp/mcgyvr-wake-<uid>/``), so one this user does not own outright is
somebody else's to plant: a wake writes nothing into it.

**What this file pins**

1. A wake beside any leftover wake record still wakes: the door is spawned
   once, the run is ok, and the leftover file is left as it was.
2. A wake writes no wake record of its own.
3. A clock directory this user does not own outright is not written by a wake.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.config import parse
from mcgyvr.serving import Card
from mcgyvr.wake import Wake

HOST = "rig"

LADDER = f"""\
units:
  local_one:
    address: http://{HOST}:8080
    model: one
    rig: rig
ladder:
- local_one
"""


@pytest.fixture
def clock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A temporary directory of this test's own for the wake clock to live in.

    Keyed host-wide by uid in production, which is exactly why a test that used
    the developer's would read another test's files.
    """
    (tmp_path / "rendezvous").mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "rendezvous"))
    return tmp_path / "rendezvous"


@pytest.fixture
def spawned(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Every door argv a wake spawns, each answering 0; nothing is started."""
    import mcgyvr.wake as wake

    made: list[list[str]] = []

    def spawn(argv: Sequence[str], **_: Any) -> int:
        made.append(list(argv))
        return 0

    monkeypatch.setattr(wake, "spawn_door", spawn)
    return made


def card(tmp_path: Path) -> Card:
    compose = tmp_path / "compose.rig.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    return Card(host=HOST, compose_file=compose, specs=(compose,))


def door(one: Card, direction: str = "up") -> Wake:
    """Run the wake's door for ``one`` the way ``mcgyvr up``/``sleep`` does."""
    import mcgyvr.wake as wake

    assert one.compose_file is not None
    return wake._run_door(parse(LADDER), one, direction, one.compose_file)


def clock_dir() -> Path:
    """The clock directory, made 0o700 the way a wake's own writer makes it."""
    import mcgyvr.wake as wake

    where = wake._clock_dir()
    where.mkdir(parents=True, mode=0o700, exist_ok=True)
    return where


def contents(where: Path) -> dict[str, bytes | None]:
    """Every entry of ``where`` by name: a file's bytes, None for a directory."""
    return {
        entry.name: None if entry.is_dir() else entry.read_bytes()
        for entry in where.iterdir()
    }


#: Every shape a leftover wake record has been found in: a good record an older
#: mcgyvr wrote, valid JSON of the wrong type, a truncated write, a file that is
#: not text at all, and an empty file.
LEFTOVERS: tuple[bytes, ...] = (
    json.dumps({"host": HOST, "seconds": 133.4}).encode("utf-8"),
    json.dumps({"seconds": True}).encode("utf-8"),
    b"null",
    b"[1.0]",
    b"133.0",
    b'"133.0"',
    b'{"seconds": 133.0',
    b"\xff\xfe\x00\x01binary",
    b"",
)


@pytest.mark.parametrize("raw", LEFTOVERS)
def test_a_wake_beside_a_leftover_record_still_wakes_and_leaves_it_be(
    raw: bytes, tmp_path: Path, clock: Path, spawned: list[list[str]]
) -> None:
    """The rule, as behaviour: the door runs, and the file is nobody's input."""

    one = card(tmp_path)
    where = clock_dir()
    (where / f"{HOST}.wake.json").write_bytes(raw)
    before = contents(where)

    made = door(one)

    assert len(spawned) == 1, spawned
    assert made.ok, made
    assert contents(where) == before


def test_a_directory_where_the_record_was_does_not_stop_a_wake(
    tmp_path: Path, clock: Path, spawned: list[list[str]]
) -> None:

    one = card(tmp_path)
    (clock_dir() / f"{HOST}.wake.json").mkdir()

    made = door(one)

    assert len(spawned) == 1, spawned
    assert made.ok, made


def test_a_wake_writes_no_wake_record(
    tmp_path: Path, clock: Path, spawned: list[list[str]]
) -> None:

    one = card(tmp_path)
    where = clock_dir()

    made = door(one)

    assert made.ok, made
    assert not (where / f"{HOST}.wake.json").exists()


def test_a_clock_directory_this_user_does_not_own_outright_is_not_written(
    tmp_path: Path, clock: Path, spawned: list[list[str]]
) -> None:
    """A predictable path in a world-writable place is somebody else's to plant,
    and a wake writes nothing into a directory it did not make its own."""

    one = card(tmp_path)
    where = clock_dir()
    (where / f"{HOST}.wake.json").write_text(
        json.dumps({"seconds": 4.0}), encoding="utf-8"
    )
    os.chmod(where, 0o777)
    before = contents(where)

    for direction in ("up", "sleep"):
        made = door(one, direction)
        assert made.ok, made

    assert contents(where) == before, "a wake wrote into a directory not its own"
