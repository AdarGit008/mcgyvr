"""Sleep evicts the whole card, and it drains it before it does.

RED. Nothing here passes today: ``mcgyvr serve sleep`` is not a command,
``mcgyvr.serving.cards`` is not a function, and ``serving.enable_sleep_wake`` is
not a schema key. The design is ``records/plans/sleep-wake.md``.

**The owner's first ruling, and the one this file is named after: on sleep,
mcgyvr evicts the ENTIRE GPU.** Not one model, not a share of VRAM. The design
finds that this is not a behaviour to build but one the tree already has — the
card is the compose file, ``emit.emit_all`` writes one compose file per host
"because a host is what an operator brings up", and the door's ``down`` step
tears down every service in the file it is handed. On the live ladder that means
srv2's one RTX 3060 sits behind two sources, ``:8001`` (3B) and ``:8002`` (7B),
and putting that card to sleep takes both rungs down together. There is no
per-model sleep and therefore no wake that displaces a neighbour: whole-card
eviction does not solve partial eviction, it deletes the case (D8). Gate 2
enforces the same thing from the rig's side, refusing ``serve up`` on a rig that
is not idle, so there is no such thing as topping a card up.

**The rule that makes an automatic eviction safe** is the second half, and it is
the half that stops being merely correct and starts being load-bearing the
moment a queue rather than an operator decides:

    An eviction takes all of the card's slots before it takes the card down. It
    never interrupts a dispatch that is already in flight, and it is best-effort
    against processes the flock cannot see.

The slot files under the capacity rendezvous directory already exclude every
mcgyvr process on the host, so taking them all *is* the drain. The census that
decides whether to sleep is a reading; the drain is a hold; between the two a
dispatch can start, which is why both exist.

What this file does not pin: ``SLEEP_IDLE_S`` (N3), ``MIN_UPTIME_S`` (N4) and
``COOLDOWN_S`` (N5) are the dampers §7.6 proposes and §16 leaves open, and the
whole question of an idle-timer daemon is N6 — the design builds none, and a
card that goes idle after everything stops is slept by the last run that used it
or not at all. So the sleeps driven here are the hand-typed ones §15 gives an
operator, which are unaffected by the dampers and, per §15, unaffected by
``enable_sleep_wake`` too: that switch governs the automatic decisions.
"""

from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path

import pytest

from tests import livejournal as lj
from tests.test_a_sleeping_rung_is_woken_rather_than_declined import (
    HOST,
    RUNG_3B,
    RUNG_7B,
    compose_dir,
    config_file,
    door_log,
)


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A HOME and a capacity rendezvous directory nobody else writes to.

    The rendezvous matters more here than anywhere: the drain is a hold on the
    very slot files a second process would take, and D7 puts the two clocks
    (``<host>.wake``, ``<host>.used``) beside them.
    """
    (tmp_path / "home").mkdir(exist_ok=True)
    lj.clean_env(monkeypatch, tmp_path / "home")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    lj.claude_transcript(tmp_path / "home", "s1")
    (tmp_path / "rendezvous").mkdir(exist_ok=True)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "rendezvous"))
    return tmp_path / "home"


def sleep_argv(config: Path) -> list[str]:
    """What an operator types to hand the card back (§15)."""
    return ["serve", "sleep", "--host", HOST, "--config", str(config)]


def test_two_rungs_behind_one_url_pair_are_one_card_and_one_launch_spec(
    tmp_path: Path, home: Path
) -> None:
    """The card is derived, never declared (D1).

    No ``devices:`` block, no ``device:`` field on a source, no card in ``Tier``
    or ``Source``: a card named above the execution seam would be a fact about a
    *machine* on an object whose whole purpose is to name no machine, and it
    would go stale the first time a source was re-pointed. The card of a rung is
    ``(host_of(source.base_url), the file emit_all would have written)``,
    computed in ``mcgyvr.serving`` from the config alone.

    From the config alone, and from no scan: ``units_for`` needs a ``Scan`` per
    host because it has to decide a fit, and a card's identity needs no fit —
    which is what keeps the wake path usable on a machine that never scanned the
    rig, this one included.
    """
    from mcgyvr.config import load
    from mcgyvr.emit import COMPOSE_PREFIX, COMPOSE_SUFFIX
    from mcgyvr.serving import cards  # type: ignore[attr-defined]

    specs = compose_dir(tmp_path, with_spec=True)
    config = config_file(
        tmp_path / "on.yaml", journal=tmp_path / "j", specs=specs, switch=True
    )

    derived = cards(load(config))

    assert derived[RUNG_3B] == derived[RUNG_7B], (
        "the 3B and the 7B came back as two cards. They are two server "
        "processes on one RTX 3060, and a design that could not see that would "
        "sleep half a card"
    )
    card = derived[RUNG_3B]
    assert card.host == HOST
    assert set(card.rungs) == {RUNG_3B, RUNG_7B}
    assert set(card.sources) == {"srv2_3b", "srv2_7b"}
    assert Path(card.compose_file) == (
        specs / f"{COMPOSE_PREFIX}{HOST}{COMPOSE_SUFFIX}"
    ), card.compose_file


def test_sleeping_the_card_takes_both_rungs_down_in_one_door_run(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One card, one compose file, one ``serve down`` — not one per rung.

    The door's ``down`` step runs against the whole compose file under one
    pinned project, so the operator never spells a container name and cannot
    take half a card down. A second door run would be a second envelope for one
    eviction, and gate 5's ``O_CREAT|O_EXCL`` claim on the RUN_ID is what would
    catch it — but the reason there is only one is upstream of that: the unit of
    eviction is the file.
    """
    specs = compose_dir(tmp_path, with_spec=True)
    config = config_file(
        tmp_path / "on.yaml", journal=tmp_path / "j", specs=specs, switch=True
    )
    spawned = door_log(monkeypatch)

    code = lj.main(sleep_argv(config))

    assert code == 0
    assert len(spawned) == 1, (
        f"one card was slept and the door was run {len(spawned)} times: {spawned}"
    )
    (argv,) = spawned
    assert "mcgyvr.serving.run" in argv, argv
    assert argv[argv.index("serve") + 1] == "down", argv
    assert HOST in argv, argv
    assert str(specs / f"compose.{HOST}.yml") in argv, (
        f"the sleep did not hand the door the launch spec emit wrote: {argv}"
    )
    for forbidden in ("docker", "ssh"):
        assert not any(forbidden in part for part in argv), (argv, forbidden)


def test_an_operators_own_sleep_is_not_gated_by_the_automatic_switch(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``enable_sleep_wake`` governs the decisions, not the commands (§15).

    ``mcgyvr serve sleep|wake`` is a thin front over the door's two steps for
    the operator who wants to say it by hand. The switch exists so that mcgyvr
    does not decide to take a card down without being asked; a person typing the
    command has asked.
    """
    specs = compose_dir(tmp_path, with_spec=True)
    config = config_file(
        tmp_path / "off.yaml", journal=tmp_path / "j", specs=specs, switch=False
    )
    spawned = door_log(monkeypatch)

    code = lj.main(sleep_argv(config))

    assert code == 0, "an operator was refused their own card by a switch"
    assert len(spawned) == 1 and spawned[0][spawned[0].index("serve") + 1] == "down"


def test_a_dispatch_in_flight_is_never_cut_by_a_sleep(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The drain, and the reason it is a hold and not a reading.

    A slot of ``srv2_3b`` is taken by a second capacity — the stand-in for the
    other mcgyvr process the bound exists to keep out, and the same stand-in
    ``tests/test_a_full_rung_is_declined_not_waited_on_forever.py`` uses. The
    sleep must not reach the rig while that slot is held: ``docker compose
    down`` kills containers, and killing one out from under a request that was
    already admitted is the one thing whole-card eviction is not allowed to do.

    Two rungs on this card and the slot held on only one of them, because the
    unit of eviction is the card: a drain that only counted the rung it was
    asked about would take down a card the other rung was serving from.
    """
    from mcgyvr.capacity import Capacity
    from mcgyvr.config import load

    specs = compose_dir(tmp_path, with_spec=True)
    config = config_file(
        tmp_path / "on.yaml", journal=tmp_path / "j", specs=specs, switch=True
    )
    spawned = door_log(monkeypatch)

    holder = Capacity.of(load(config))
    finished: list[int] = []

    def sleeper() -> None:
        finished.append(lj.main(sleep_argv(config)))

    thread = threading.Thread(target=sleeper, daemon=True)
    with holder.hold("srv2_3b"):
        thread.start()
        time.sleep(1.0)
        held_spawns = list(spawned)
        held_finished = list(finished)
    thread.join(timeout=60)

    assert held_spawns == [], (
        f"the door was run while a slot of the card was held: {held_spawns}. "
        "A request that had already been admitted was about to have its "
        "container killed under it"
    )
    assert held_finished == [], (
        "the sleep reported itself done while a dispatch was in flight"
    )
    assert finished == [0], finished
    assert len(spawned) == 1, spawned
    assert spawned[0][spawned[0].index("serve") + 1] == "down", spawned
