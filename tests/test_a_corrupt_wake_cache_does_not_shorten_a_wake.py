"""A derived budget may never shorten or abort a wake — not even by raising.

RED. The owner's ruling of 2026-09-09 is that ``wake.predicted_wake_s`` is
**advisory**: it warns, it informs scheduling, and ``budgets.wake_timeout_s``
remains the sole authority that gives up. A derived budget that could abort
would abandon a wake that was about to land and leave a card half-up, which is
the one lifecycle state D2 says the reading cannot name.

``predicted_wake_s`` breaks that ruling by accident, in the narrowest possible
way. It catches ``OSError`` and ``ValueError`` around the read and the parse and
then calls ``.get`` on whatever came back::

    said = json.loads(raw).get("seconds")

so a cache file holding JSON ``null``, a list, a number or a string raises
``AttributeError``, and a file of bytes that are not UTF-8 raises
``UnicodeDecodeError`` before ``json`` is reached. ``_run_door`` calls it
**before** spawning the door. So a one-line file — which is what a crashed
process, a full disk or a truncated write leaves behind — does not degrade the
warning: it kills the wake, and the rung declines against a rig that would have
come back.

The cache is also at ``/tmp/mcgyvr-wake-<uid>/``, a predictable path in a
world-writable directory, and ``_remember``'s ``mkdir(exist_ok=True)`` adopts a
directory another local user got there first with. Nothing secret is in it, but
what it holds is a number this process then reads back and prints as fact, and
adopting a stranger's directory to write it in is not something to do by
default.

**What this file pins**

1. Every unreadable cache — wrong JSON type, not JSON at all, not UTF-8, a
   directory where a file should be — degrades to *no prediction*, and never to
   an exception.
2. A wake with an unreadable cache **still wakes**: the door is spawned, and it
   is spawned with ``predicted_s`` of ``None``.
3. ``{"seconds": true}`` predicts nothing. ``isinstance(True, int)`` is true in
   Python, so a boolean walked straight through the type check and was reported
   to an operator as a 1.0 s wake.
4. A clock directory this user does not own outright is not read and not
   written. It degrades to no prediction, which is the ordinary state on a first
   wake and costs nothing.
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

HOST = "rig"

LADDER = f"""
version: 1
sources:
  rig:
    base_url: "http://{HOST}:8080"
    api: openai
ladder:
  tiers:
    - name: local_one
      source: rig
      model: one
"""


@pytest.fixture
def clock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A temporary directory of this test's own for the wake clock to live in.

    Keyed host-wide by uid in production, which is what makes it readable by the
    next run and is exactly why a test that used the developer's would read
    another test's number.
    """
    (tmp_path / "rendezvous").mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "rendezvous"))
    return tmp_path / "rendezvous"


def card(tmp_path: Path) -> Card:
    return Card(host=HOST, compose_file=tmp_path / "compose.rig.yml")


def cache_of(card_: Card, raw: bytes) -> Path:
    """Whatever ``raw`` is, sitting where the next wake will read it."""
    import mcgyvr.wake as wake

    where = wake._clock_dir()
    # 0o700, the way `_remember` makes it: a directory anybody else could write
    # into is one this reader is entitled to ignore, which is its own test
    # below.
    where.mkdir(parents=True, mode=0o700, exist_ok=True)
    path = where / f"{card_.host}.wake.json"
    path.write_bytes(raw)
    return path


#: Every shape a cache file has been found in that is not ``{"seconds": <n>}``.
#: The first four are valid JSON of the wrong type — ``.get`` on them is an
#: ``AttributeError`` — the fifth is a truncated write, and the sixth is a file
#: that is not text at all, whose ``UnicodeDecodeError`` is a ``ValueError`` but
#: is raised by ``read_text`` where only ``OSError`` was caught.
UNREADABLE: tuple[bytes, ...] = (
    b"null",
    b"[1.0]",
    b"133.0",
    b'"133.0"',
    b'{"seconds": 133.0',
    b"\xff\xfe\x00\x01binary",
    b"",
)


@pytest.mark.parametrize("raw", UNREADABLE)
def test_an_unreadable_cache_is_no_prediction_and_never_a_raise(
    raw: bytes, tmp_path: Path, clock: Path
) -> None:
    """Each of these killed the wake before the door was spawned."""
    from mcgyvr.wake import predicted_wake_s

    one = card(tmp_path)
    cache_of(one, raw)

    assert predicted_wake_s(one) is None, raw


def test_a_directory_where_the_cache_should_be_is_no_prediction(
    tmp_path: Path, clock: Path
) -> None:
    """``IsADirectoryError`` is an ``OSError`` and was already handled — pinned
    so the rewrite does not narrow what is caught while widening what is
    parsed."""
    import mcgyvr.wake as wake

    one = card(tmp_path)
    where = wake._clock_dir()
    where.mkdir(parents=True, mode=0o700, exist_ok=True)
    (where / f"{HOST}.wake.json").mkdir()

    assert wake.predicted_wake_s(one) is None


def test_a_boolean_is_not_a_number_of_seconds(tmp_path: Path, clock: Path) -> None:
    """``isinstance(True, int)`` is true, and 1.0 s is not a wake anything took."""
    from mcgyvr.wake import predicted_wake_s

    one = card(tmp_path)
    cache_of(one, json.dumps({"seconds": True}).encode("utf-8"))

    assert predicted_wake_s(one) is None


def test_a_number_that_was_written_is_read_back(tmp_path: Path, clock: Path) -> None:
    """The other side: the one number every fleet has for free still arrives."""
    from mcgyvr.wake import predicted_wake_s

    one = card(tmp_path)
    cache_of(one, json.dumps({"host": HOST, "seconds": 133.4}).encode("utf-8"))

    assert predicted_wake_s(one) == pytest.approx(133.4)


def test_a_wake_with_an_unreadable_cache_still_wakes(
    tmp_path: Path, clock: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ruling, as behaviour: the door runs, and the prediction is absent.

    This is the whole severity of it. The prediction is a sentence in a warning;
    the wake is a card coming back for a rung that is queued on it.
    """
    import mcgyvr.wake as wake

    spawned: list[list[str]] = []

    def spawn(argv: Sequence[str], **_: Any) -> int:
        spawned.append(list(argv))
        return 0

    monkeypatch.setattr(wake, "spawn_door", spawn)

    compose = tmp_path / "compose.rig.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    one = Card(host=HOST, compose_file=compose, specs=(compose,))
    cache_of(one, b"null")

    made = wake._run_door(parse(LADDER), one, "up", compose)

    assert len(spawned) == 1, spawned
    assert made.ok and made.predicted_s is None, made


def test_a_clock_directory_this_user_does_not_own_outright_is_not_used(
    tmp_path: Path, clock: Path
) -> None:
    """A predictable path in a world-writable place is somebody else's to plant.

    Nothing in the file is secret. What is at stake is that this process reads a
    number back out of it and prints it to an operator as what the card did last
    time, and that ``_remember`` would otherwise write into a directory it did
    not create. Degrading to "no history" is free — it is the ordinary state of
    a first wake.
    """
    import mcgyvr.wake as wake

    one = card(tmp_path)
    where = wake._clock_dir()
    where.mkdir(parents=True, mode=0o700, exist_ok=True)
    (where / f"{HOST}.wake.json").write_text(
        json.dumps({"seconds": 4.0}), encoding="utf-8"
    )
    os.chmod(where, 0o777)

    assert wake.predicted_wake_s(one) is None

    made = wake.Wake(
        host=HOST,
        compose_file=tmp_path / "compose.rig.yml",
        direction="up",
        seconds=99.0,
        predicted_s=None,
        code=0,
    )
    wake._remember(made)

    assert json.loads((where / f"{HOST}.wake.json").read_text(encoding="utf-8")) == {
        "seconds": 4.0
    }, "a wake wrote into a directory another user could have created"
