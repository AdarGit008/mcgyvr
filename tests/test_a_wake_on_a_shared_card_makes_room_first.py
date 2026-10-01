"""A wake on a shared card makes room first: the smaller unit sleeps first.

Two vLLM units co-resident on one card each run as their own process, and each
can sleep at level 2 alone — the process stays, its weights and KV cache leave
the card. Where the two cannot both be awake on the card, waking the bigger one
means putting the smaller one to sleep first, and giving the room back when the
bigger one sleeps again.

Whether they fit is arithmetic on facts mcgyvr already holds: each unit's
``room_mib`` from the config, and the card's memory from the host's recorded
scan, which ``emit`` sizes against. Where either is missing there is no answer,
and the card acts whole, as before. Every number and shape here is invented.

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


def write_spec(tmp_path: Path) -> Path:
    """The shared card's one launch spec: both units, each its own container."""
    from mcgyvr.serving import COMPOSE_PREFIX, COMPOSE_SUFFIX

    where = tmp_path / "specs"
    where.mkdir(exist_ok=True)
    services = {
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


def switches(config: Config, card_mib: int | None = 12000) -> Any:
    from mcgyvr.capacity import Capacity
    from mcgyvr.pressure import Gauge
    from mcgyvr.wake import CardSwitches

    rooms = {} if card_mib is None else {SHARED_HOST: card_mib}
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
    ["card", "small_mib", "llama.cpp"],
    ids=["no-card-size", "no-room-mib", "not-vllm"],
)
def test_without_the_numbers_or_the_engine_there_is_no_room_to_make(
    tmp_path: Path, home: Path, missing: str
) -> None:
    specs = write_spec(tmp_path)
    if missing == "small_mib":
        config = parse(ladder_text(specs, small_mib=None))
    elif missing == "llama.cpp":
        config = parse(ladder_text(specs, engine="llama.cpp"))
    else:
        config = parse(ladder_text(specs))

    card = None if missing == "card" else 12000
    assert switches(config, card_mib=card).room_for(LARGE) == ()


def test_a_shared_vllm_card_switches_one_unit_at_a_time(
    tmp_path: Path, home: Path
) -> None:
    config = parse(ladder_text(write_spec(tmp_path)))

    assert switches(config).card_of(LARGE) == (LARGE,)
    assert switches(config).card_of(SMALL) == (SMALL,)


def test_a_card_size_is_read_from_a_one_card_scan_and_from_no_other() -> None:
    from mcgyvr.wake import card_rooms

    one = Scan.of(
        host=SHARED_HOST,
        vram_mib=12000,
        ram_gb=32.0,
        disk_free_gb=500.0,
        cores=8,
        threads=16,
        bandwidth_gbps=20.0,
    )
    two = Scan.of(
        host=FAST_HOST,
        vram_mib=8000,
        ram_gb=32.0,
        disk_free_gb=500.0,
        cores=8,
        threads=16,
        bandwidth_gbps=20.0,
    )
    from dataclasses import replace

    two = replace(two, gpus=(*two.gpus, *two.gpus))

    assert card_rooms({SHARED_HOST: one, FAST_HOST: two}) == {SHARED_HOST: 12000}


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
    from mcgyvr.pool import source_map

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
