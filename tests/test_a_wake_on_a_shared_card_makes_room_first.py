"""A wake on a shared card makes room first: the smaller unit sleeps first.

Two vLLM units co-resident on one card each run as their own process, and each
can sleep at level 2 alone — the process stays, its weights and KV cache leave
the card. Where the two cannot both be awake on the card, waking the bigger one
means putting the smaller one to sleep first, and giving the room back when the
bigger one sleeps again.

Whether they fit is arithmetic on facts mcgyvr already holds: each unit's
``room_mib`` from the config, the card each unit is on from the launch spec
that starts it, and that card's memory from the host's recorded scan, which
``emit`` sizes against. On a host with several cards only the units on the
waking unit's card are its neighbours. Where a figure is missing, or the card
a unit is on cannot be told, there is no answer, no room is made, and the
manager says why. Every number and shape here is invented.

On such a card a sleep and a wake act on one unit (``serve sleep|wake --unit``),
the card's other units are left as they are, and the record of who is resting
is kept per unit.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr import ladder_manager
from mcgyvr.config import Config, parse
from mcgyvr.ladder_manager import Bounds, Manager, View
from mcgyvr.pressure import Reading
from mcgyvr.scan import Scan
from tests import livejournal as lj

FAST = "local_fast"
SMALL = "local_small"
LARGE = "local_large"

FAST_HOST = "fast-box.example"
SHARED_HOST = "shared-box.example"
SMALL_CONTAINER = "mcgyvr-shared-small"
LARGE_CONTAINER = "mcgyvr-shared-large"


def ladder_text(
    compose_dir: Path | None,
    *,
    engine: str = "vllm",
    small_mib: int | None = 4000,
    large_mib: int | None = 9000,
) -> str:
    def room(mib: int | None) -> str:
        return "" if mib is None else f"    room_mib: {mib}\n"

    serving = (
        ""
        if compose_dir is None
        else f"serving:\n  compose_dir: {compose_dir}\n  enable_sleep_wake: true\n"
    )
    return (
        "units:\n"
        f"  {FAST}:\n"
        f"    address: http://{FAST_HOST}:8000\n"
        "    model: small-coder\n"
        "    rig: fast-rig\n"
        "    width: 2\n"
        f"  {SMALL}:\n"
        f"    address: http://{SHARED_HOST}:8001\n"
        "    model: mid-coder\n"
        "    rig: shared-rig-small\n"
        f"    engine: {engine}\n"
        "    width: 2\n" + room(small_mib) + f"  {LARGE}:\n"
        f"    address: http://{SHARED_HOST}:8002\n"
        "    model: large-coder\n"
        "    rig: shared-rig-large\n"
        f"    engine: {engine}\n"
        "    width: 2\n" + room(large_mib) + "ladder:\n"
        f"- {FAST}\n"
        f"- {SMALL}\n"
        f"- {LARGE}\n"
        "profile: dev\n" + serving
    )


def reservation(device_ids: list[str]) -> dict[str, Any]:
    """The card reservation ``emit`` writes for a service, naming ``device_ids``."""
    return {
        "resources": {
            "reservations": {
                "devices": [
                    {
                        "driver": "nvidia",
                        "device_ids": device_ids,
                        "capabilities": ["gpu"],
                    }
                ]
            }
        }
    }


def write_spec(
    tmp_path: Path,
    *,
    small_on: list[str] | None = None,
    large_on: list[str] | None = None,
) -> Path:
    """The shared host's one launch spec: both units, each its own container.

    ``small_on`` and ``large_on`` are the card ids each service reserves;
    ``None`` writes no reservation, as a hand-written spec may not.
    """
    from mcgyvr.serving import COMPOSE_PREFIX, COMPOSE_SUFFIX

    where = tmp_path / "specs"
    where.mkdir(exist_ok=True)
    services: dict[str, dict[str, Any]] = {
        "small": {
            "image": "example/server:1",
            "container_name": SMALL_CONTAINER,
            "command": ["mid-coder", "--port", "8001"],
        },
        "large": {
            "image": "example/server:1",
            "container_name": LARGE_CONTAINER,
            "command": ["large-coder", "--port", "8002"],
        },
    }
    if small_on is not None:
        services["small"]["deploy"] = reservation(small_on)
    if large_on is not None:
        services["large"]["deploy"] = reservation(large_on)
    (where / f"{COMPOSE_PREFIX}{SHARED_HOST}{COMPOSE_SUFFIX}").write_text(
        yaml.safe_dump({"services": services}), encoding="utf-8"
    )
    return where


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "home").mkdir(exist_ok=True)
    lj.clean_env(monkeypatch, tmp_path / "home")
    (tmp_path / "rendezvous").mkdir(exist_ok=True)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "rendezvous"))
    return tmp_path / "home"


def door(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The door, recorded as ``<verb>`` or ``<verb> <unit>``; every run works."""
    import mcgyvr.wake as wake

    log: list[str] = []

    def spawn(argv: list[str], **_: Any) -> int:
        said = argv[argv.index("serve") + 1]
        if "--unit" in argv:
            said += " " + argv[argv.index("--unit") + 1]
        log.append(said)
        return 0

    monkeypatch.setattr(wake, "spawn_door", spawn)
    return log


def switches(
    config: Config,
    card_mib: int | None = 12000,
    *,
    sizes: dict[int, int] | None = None,
) -> Any:
    """The manager's switches, with the shared host's card sizes by card index.

    ``card_mib`` is a one-card host's one card; ``sizes`` states every card.
    """
    from mcgyvr.capacity import Capacity
    from mcgyvr.pressure import Gauge
    from mcgyvr.wake import CardSwitches

    if sizes is None:
        sizes = {} if card_mib is None else {0: card_mib}
    rooms = {SHARED_HOST: sizes} if sizes else {}
    return CardSwitches(config, Capacity.of(config, gauge=Gauge()), card_mib=rooms)


# --- how much room ---------------------------------------------------------------


def test_waking_the_larger_unit_needs_the_smaller_ones_room(
    tmp_path: Path, home: Path
) -> None:
    config = parse(ladder_text(write_spec(tmp_path)))

    assert switches(config).room_for(LARGE) == (SMALL,)


def test_units_that_fit_the_card_together_need_no_room(
    tmp_path: Path, home: Path
) -> None:
    config = parse(ladder_text(write_spec(tmp_path)))

    assert switches(config, card_mib=16000).room_for(LARGE) == ()


@pytest.mark.parametrize(
    "missing",
    ["card", "small_mib", "media"],
    ids=["no-card-size", "no-room-mib", "not-vllm-or-llama.cpp"],
)
def test_without_the_numbers_or_the_engine_there_is_no_room_to_make(
    tmp_path: Path, home: Path, missing: str
) -> None:
    specs = write_spec(tmp_path)
    if missing == "small_mib":
        config = parse(ladder_text(specs, small_mib=None))
    elif missing == "media":
        config = parse(ladder_text(specs, engine="diffusers"))
    else:
        config = parse(ladder_text(specs))

    card = None if missing == "card" else 12000
    assert switches(config, card_mib=card).room_for(LARGE) == ()


def test_a_shared_llamacpp_card_makes_room_the_same_way(
    tmp_path: Path, home: Path
) -> None:
    """A llama.cpp unit's sleep is a stop of its container, so it swaps too."""
    config = parse(ladder_text(write_spec(tmp_path), engine="llama.cpp"))

    assert switches(config).room_for(LARGE) == (SMALL,)
    assert switches(config).card_of(LARGE) == (LARGE,)


def test_a_shared_vllm_card_switches_one_unit_at_a_time(
    tmp_path: Path, home: Path
) -> None:
    config = parse(ladder_text(write_spec(tmp_path)))

    assert switches(config).card_of(LARGE) == (LARGE,)
    assert switches(config).card_of(SMALL) == (SMALL,)


def scan_of(host: str, *vram_mib: int) -> Scan:
    """A recorded scan of ``host`` holding one card per size, indexed in order."""
    from dataclasses import replace

    from mcgyvr.scan import Vram

    base = Scan.of(
        host=host,
        vram_mib=vram_mib[0],
        ram_gb=32.0,
        disk_free_gb=500.0,
        cores=8,
        threads=16,
        bandwidth_gbps=20.0,
    )
    first = base.gpus[0]
    return replace(
        base,
        gpus=tuple(
            replace(
                first,
                index=index,
                vram=Vram(total_mib=mib, used_mib=0, free_mib=mib),
            )
            for index, mib in enumerate(vram_mib)
        ),
    )


def test_card_sizes_are_read_per_card_from_every_scan() -> None:
    from mcgyvr.wake import card_rooms

    assert card_rooms(
        {
            SHARED_HOST: scan_of(SHARED_HOST, 12000),
            FAST_HOST: scan_of(FAST_HOST, 8000, 16000),
        }
    ) == {SHARED_HOST: {0: 12000}, FAST_HOST: {0: 8000, 1: 16000}}


# --- several cards on one host ---------------------------------------------------


def test_on_a_host_of_several_cards_room_is_made_on_the_waking_units_card(
    tmp_path: Path, home: Path
) -> None:
    config = parse(ladder_text(write_spec(tmp_path, small_on=["1"], large_on=["1"])))

    card = switches(config, sizes={0: 24000, 1: 12000})

    assert card.room_for(LARGE) == (SMALL,), (
        "both units are on the 12000 MiB card, and 4000 + 9000 does not fit it"
    )
    assert card.why_no_room(LARGE) is None


def test_a_unit_on_another_card_holds_no_room_on_this_one(
    tmp_path: Path, home: Path
) -> None:
    config = parse(ladder_text(write_spec(tmp_path, small_on=["0"], large_on=["1"])))

    card = switches(config, sizes={0: 12000, 1: 9000})

    assert card.room_for(LARGE) == (), (
        "the small unit is on the other card; sleeping it frees nothing here"
    )
    assert card.why_no_room(LARGE) is None


def test_the_card_of_a_one_card_host_needs_no_reservation_in_the_spec(
    tmp_path: Path, home: Path
) -> None:
    config = parse(ladder_text(write_spec(tmp_path)))

    assert switches(config, sizes={0: 12000}).room_for(LARGE) == (SMALL,)


@pytest.mark.parametrize(
    ("small_on", "large_on", "sizes", "said"),
    [
        (None, None, {0: 12000, 1: 12000}, "which card"),
        (["0"], ["0", "1"], {0: 12000, 1: 12000}, "more than one card"),
        (["0"], ["GPU-not-an-index"], {0: 12000, 1: 12000}, "which card"),
        (["0"], ["2"], {0: 12000, 1: 12000}, "no recorded scan"),
        (["0"], ["0"], {}, "no recorded scan"),
    ],
    ids=[
        "no-reservation",
        "spans-two-cards",
        "not-an-index",
        "unscanned-card",
        "no-scan",
    ],
)
def test_where_the_card_cannot_be_told_no_room_is_made_and_why_is_said(
    tmp_path: Path,
    home: Path,
    small_on: list[str] | None,
    large_on: list[str] | None,
    sizes: dict[int, int],
    said: str,
) -> None:
    config = parse(
        ladder_text(write_spec(tmp_path, small_on=small_on, large_on=large_on))
    )

    card = switches(config, sizes=sizes)

    assert card.room_for(LARGE) == ()
    why = card.why_no_room(LARGE)
    assert why is not None and said in why, why


def test_manage_says_where_it_will_make_no_room(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import mcgyvr.pressure as pressure
    import mcgyvr.wake as wake

    class Answers:
        live = False

    monkeypatch.setattr(wake, "spawn_door", lambda *a, **k: 0)
    monkeypatch.setattr(pressure, "probe_endpoint", lambda *args: Answers())
    monkeypatch.setattr(pressure, "unit_in_flight", lambda *args: 0)
    path = tmp_path / "c.yaml"
    path.write_text(
        ladder_text(write_spec(tmp_path)) + f"journal:\n  dir: {tmp_path / 'j'}\n",
        encoding="utf-8",
    )

    lj.main(["manage", "--config", str(path), "--once"])
    out = capsys.readouterr().out

    assert f"no room is made for {LARGE}" in out, out
    assert "no recorded scan" in out, out


# --- one unit at a time -------------------------------------------------------------


def test_a_sleep_on_a_shared_card_sleeps_that_unit_alone(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = parse(ladder_text(write_spec(tmp_path)))
    doors = door(monkeypatch)

    assert switches(config).sleep(SMALL) is True
    assert doors == [f"sleep {SMALL_CONTAINER}"]


def test_a_resting_unit_is_woken_alone_and_its_neighbour_is_not(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = parse(ladder_text(write_spec(tmp_path)))
    doors = door(monkeypatch)
    card = switches(config)

    assert card.sleep(LARGE) is True
    assert card.wake(LARGE) is True
    assert doors == [f"sleep {LARGE_CONTAINER}", f"wake {LARGE_CONTAINER}"]


def test_resting_is_kept_per_unit_and_read_per_unit(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mcgyvr.pressure as pressure
    from mcgyvr.capacity import Capacity
    from mcgyvr.local_pool import source_map

    config = parse(ladder_text(write_spec(tmp_path)))
    door(monkeypatch)

    class Answers:
        live = True

    monkeypatch.setattr(pressure, "probe_endpoint", lambda *args: Answers())
    monkeypatch.setattr(pressure, "unit_in_flight", lambda *args: 0)
    gauge = pressure.Gauge()
    reader = pressure.Pressure(
        source_map(config), Capacity.of(config, gauge=gauge), gauge
    )

    assert switches(config).sleep(SMALL) is True
    assert reader.read(SMALL).awake is False
    assert reader.read(LARGE).awake is True, "the neighbour was not slept"


# --- the manager makes the room ---------------------------------------------------


class Readings:
    """The queue, held by the test; the card's units move with the door."""

    def __init__(self) -> None:
        self.now = {
            FAST: Reading(FAST, True, 2, 2, 0, 2, full=True),
            SMALL: Reading(SMALL, True, 2, 1, 1, 2, full=True),
            LARGE: Reading(LARGE, False, None, 0, 0, 2),
        }

    def read(self, rung: str) -> Reading:
        return self.now[rung]


def test_waking_the_larger_unit_sleeps_the_smaller_one_first(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr import decision

    config = parse(ladder_text(write_spec(tmp_path)))
    doors = door(monkeypatch)
    card = switches(config)
    assert card.sleep(LARGE) is True  # the larger unit rests, as it would

    def decide(state: Any, questions: Any) -> decision.Decision:
        question = questions[ladder_manager.ASK_LADDER]
        pick = f"wake:{LARGE}"
        assert pick in question.options, question.options
        return decision.Decision(
            answers={
                ladder_manager.ASK_LADDER: decision.ChoiceAnswer(
                    choice=pick, probabilities={pick: 1.0}, confidence=1.0
                )
            }
        )

    run = Manager(
        View(
            resident=(FAST, SMALL, LARGE),
            sleepable=frozenset({SMALL, LARGE}),
            jev=FAST,
            fanout="none",
            ladder=(FAST, SMALL, LARGE),
        ),
        Bounds(interval_s=10.0, confirm=1, dwell_s=0.0, fanouts=(), leads=()),
        pressure=Readings(),
        switches=card,
        decide=decide,
        say=lambda line: None,
    )
    run.tick()

    assert doors == [
        f"sleep {LARGE_CONTAINER}",
        f"sleep {SMALL_CONTAINER}",
        f"wake {LARGE_CONTAINER}",
    ]


def test_manage_reads_the_card_sizes_from_the_scans(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import mcgyvr.pressure as pressure
    import mcgyvr.wake as wake

    built: list[dict[str, Any]] = []
    real = wake.CardSwitches

    def recording(*args: Any, **kwargs: Any) -> Any:
        built.append(kwargs)
        return real(*args, **kwargs)

    class Answers:
        live = False

    monkeypatch.setattr(wake, "CardSwitches", recording)
    monkeypatch.setattr(wake, "spawn_door", lambda *a, **k: 0)
    monkeypatch.setattr(pressure, "probe_endpoint", lambda *args: Answers())
    monkeypatch.setattr(pressure, "unit_in_flight", lambda *args: 0)
    path = tmp_path / "c.yaml"
    path.write_text(
        ladder_text(write_spec(tmp_path)) + f"journal:\n  dir: {tmp_path / 'j'}\n",
        encoding="utf-8",
    )

    lj.main(["manage", "--config", str(path), "--once"])
    capsys.readouterr()

    assert len(built) == 1
    assert "card_mib" in built[0], "the card sizes were not handed to the switches"


# --- a unit split across machines ------------------------------------------------

OTHER_HOST = "other-box.example"


def split_ladder(compose_dir: Path, *, across: str) -> str:
    """The shared host's larger unit split over two cards, the second on ``across``.

    No worker ``bind`` is stated: which machines a unit spans is all the
    manager reads, and an address is emit's to check.
    """
    return ladder_text(compose_dir).replace(
        "    model: large-coder\n",
        "    model: large-coder\n"
        "    launch:\n"
        "      shards:\n"
        f"      - {{rig: {SHARED_HOST}, gpu: 0}}\n"
        f"      - {{rig: {across}, gpu: 1}}\n",
    )


def test_a_card_holding_a_unit_split_across_machines_is_left_to_a_person(
    tmp_path: Path, home: Path
) -> None:
    """The door acts on one machine; a split unit's other half is on another.

    Putting the head down and leaving the far half up, or waking one without
    the other, is half a unit. So the manager neither sleeps nor wakes any
    unit of a card that holds one, and says so; a person can still act.
    """
    from mcgyvr.wake import left_alone

    config = parse(split_ladder(write_spec(tmp_path), across=OTHER_HOST))

    assert ladder_manager.sleepable_rungs(config) == ()
    why = left_alone(config)
    assert set(why) == {SMALL, LARGE}, why
    assert OTHER_HOST in why[LARGE], why


def test_a_unit_split_over_one_machines_cards_still_sleeps_whole(
    tmp_path: Path, home: Path
) -> None:
    from mcgyvr.wake import left_alone

    config = parse(split_ladder(write_spec(tmp_path), across=SHARED_HOST))

    assert ladder_manager.sleepable_rungs(config) == (SMALL, LARGE)
    assert left_alone(config) == {}


def test_manage_says_which_units_it_leaves_alone(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "c.yaml"
    path.write_text(
        split_ladder(write_spec(tmp_path), across=OTHER_HOST)
        + f"journal:\n  dir: {tmp_path / 'j'}\n",
        encoding="utf-8",
    )

    assert lj.main(["manage", "--config", str(path), "--once"]) == 0
    out = capsys.readouterr().out

    assert "nothing to manage" in out, out
    assert OTHER_HOST in out, out
