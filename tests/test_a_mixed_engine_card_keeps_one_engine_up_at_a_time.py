"""A card hosting both llama.cpp and vLLM never runs the two engines at once.

Two units co-resident on one card, one served by llama.cpp and one by vLLM,
switch one at a time like any two units that share a card: a llama.cpp unit's
sleep is a stop of its container, a vLLM unit's sleep is level 2 (its process
stays, its weights and cache leave), and a wake of either is a start or a wake
of that one container, never a whole-card run that would bring its neighbour of
the other engine up beside it.

The swap is symmetric in both directions. Waking the llama.cpp sleeper puts the
vLLM unit down first (``serve sleep --unit``) and starts the sleeper alone
(``serve up --unit``); waking the vLLM unit instead puts the llama.cpp unit
down first (``serve down --unit``) and starts the vLLM unit alone. Giving the
room back reverses the same steps (``serve down --unit`` the sleeper, ``serve
wake --unit`` the vLLM unit). Every step acts on one container, so the card is
never asked to hold both engines at once.

Every machine and number here is invented; the door is recorded, never run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr.config import Config, parse
from mcgyvr.ladder_manager import give_back, wake_making_room
from mcgyvr.serving.gatelib import NO_SLEEP_ROUTE
from tests.doors import SHARED_HOST, a_clean_home, reservation

VLLM = "local_vllm"
LLAMA = "local_llama"
VLLM_CONTAINER = "mcgyvr-shared-vllm"
LLAMA_CONTAINER = "mcgyvr-shared-llama"
CARD_MIB = 12288


def mixed_ladder(compose_dir: Path, *, room: str = "room_mib") -> str:
    """The shared host's two units, one per engine; the llama.cpp one is the
    sleeper, the vLLM one is always-on and up by default.

    ``room`` says how each unit's card room is stated: ``room_mib`` (the
    field), ``vram_gb`` (under ``launch``, as ``emit`` stamps it), or ``none``.
    """

    def room_field() -> str:
        if room == "room_mib":
            return "    room_mib: 9000\n"
        if room == "vram_gb":
            return "    launch:\n      vram_gb: 8.7890625\n"
        return ""

    serving = f"serving:\n  compose_dir: {compose_dir}\n  enable_sleep_wake: true\n"
    return (
        "units:\n"
        f"  {VLLM}:\n"
        f"    address: http://{SHARED_HOST}:8001\n"
        "    model: large-vllm\n"
        "    rig: shared-rig-vllm\n"
        "    engine: vllm\n"
        "    width: 2\n" + room_field() + f"  {LLAMA}:\n"
        f"    address: http://{SHARED_HOST}:8002\n"
        "    model: large-llama\n"
        "    rig: shared-rig-llama\n"
        "    engine: llama.cpp\n"
        "    width: 2\n" + room_field() + "    sleep: sleeps-until-needed\n"
        "ladder:\n"
        f"- {VLLM}\n"
        f"- {LLAMA}\n" + serving
    )


def mixed_spec(tmp_path: Path) -> Path:
    """One launch spec for the shared host: each unit its own container on card 0."""
    from mcgyvr.serving import COMPOSE_PREFIX, COMPOSE_SUFFIX

    where = tmp_path / "specs"
    where.mkdir(exist_ok=True)
    services = {
        "vllm": {
            "image": "vllm/vllm-openai:v0.26.0",
            "container_name": VLLM_CONTAINER,
            "command": ["--model", "/models/v", "--port", "8001"],
            "deploy": reservation(["0"]),
        },
        "llama": {
            "image": "llamacpp:b10644-L3",
            "container_name": LLAMA_CONTAINER,
            "command": ["--model", "/models/l.gguf", "--port", "8002"],
            "deploy": reservation(["0"]),
        },
    }
    (where / f"{COMPOSE_PREFIX}{SHARED_HOST}{COMPOSE_SUFFIX}").write_text(
        yaml.safe_dump({"services": services}), encoding="utf-8"
    )
    return where


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return a_clean_home(tmp_path, monkeypatch)


def switches(config: Config) -> Any:
    """The card switches, over a capacity that can see who is waiting."""
    from mcgyvr.capacity import Capacity
    from mcgyvr.pressure import Gauge
    from mcgyvr.wake import CardSwitches

    return CardSwitches(
        config,
        Capacity.of(config, gauge=Gauge()),
        card_mib={SHARED_HOST: {0: CARD_MIB}},
    )


def door(monkeypatch: pytest.MonkeyPatch, *, sleep_code: int = 0) -> list[str]:
    """The door, recorded as ``<verb> <unit>``; ``sleep`` exits ``sleep_code``."""
    import mcgyvr.wake as wake

    log: list[str] = []

    def spawn(argv: list[str], **_: Any) -> int:
        verb = argv[argv.index("serve") + 1]
        unit = argv[argv.index("--unit") + 1]
        log.append(f"{verb} {unit}")
        return sleep_code if verb == "sleep" else 0

    monkeypatch.setattr(wake, "spawn_door", spawn)
    return log


def tracking_door(
    monkeypatch: pytest.MonkeyPatch,
    *,
    start: frozenset[str],
) -> tuple[set[str], list[frozenset[str]]]:
    """The door, keeping which containers are up; every run is a per-unit run.

    ``start`` is the set of containers up before the swap: the displaced engine's
    unit. The up set after every run is returned so a test can hold it to the
    one-engine-at-a-time invariant.
    """
    import mcgyvr.wake as wake

    up = set(start)
    after: list[frozenset[str]] = []

    def spawn(argv: list[str], **_: Any) -> int:
        nonlocal up
        verb = argv[argv.index("serve") + 1]
        unit = argv[argv.index("--unit") + 1]
        if verb in ("up", "wake"):
            up.add(unit)
        else:
            up.discard(unit)
        after.append(frozenset(up))
        return 0

    monkeypatch.setattr(wake, "spawn_door", spawn)
    return up, after


# --- one unit at a time -----------------------------------------------------


def test_a_vllm_unit_on_a_mixed_card_sleeps_alone(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = parse(mixed_ladder(mixed_spec(tmp_path)))
    log = door(monkeypatch)

    assert switches(config).sleep(VLLM) is True
    assert log == [f"sleep {VLLM_CONTAINER}"], "the card was put down whole"


def test_a_vllm_unit_on_a_mixed_card_with_no_sleep_route_stops_alone(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = parse(mixed_ladder(mixed_spec(tmp_path)))
    log = door(monkeypatch, sleep_code=NO_SLEEP_ROUTE)

    assert switches(config).sleep(VLLM) is True
    assert log == [f"sleep {VLLM_CONTAINER}", f"down {VLLM_CONTAINER}"], (
        "the fallback stopped the whole card"
    )


def test_a_llama_unit_on_a_mixed_card_stops_alone(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = parse(mixed_ladder(mixed_spec(tmp_path)))
    log = door(monkeypatch)

    assert switches(config).sleep(LLAMA) is True
    assert log == [f"down {LLAMA_CONTAINER}"]


def test_a_stopped_vllm_unit_on_a_mixed_card_starts_alone(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.wake import for_config

    config = parse(mixed_ladder(mixed_spec(tmp_path)))
    log = door(monkeypatch)
    waker = for_config(config)
    assert waker is not None

    assert waker.wake_for(VLLM) is True
    assert log == [f"up {VLLM_CONTAINER}"], "a start brought the llama.cpp unit up too"


def test_room_for_an_either_engine_is_the_others_room(
    tmp_path: Path, home: Path
) -> None:
    config = parse(mixed_ladder(mixed_spec(tmp_path)))

    assert switches(config).room_for(LLAMA) == (VLLM,)
    assert switches(config).room_for(VLLM) == (LLAMA,)
    assert switches(config).why_no_room(LLAMA) is None
    assert switches(config).why_no_room(VLLM) is None


def test_room_falls_back_to_launch_vram_gb_when_room_mib_is_unset(
    tmp_path: Path, home: Path
) -> None:
    config = parse(mixed_ladder(mixed_spec(tmp_path), room="vram_gb"))

    assert switches(config).room_for(LLAMA) == (VLLM,)
    assert switches(config).room_for(VLLM) == (LLAMA,)
    assert switches(config).why_no_room(LLAMA) is None


def test_a_swap_with_only_launch_vram_gb_still_makes_room(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = parse(mixed_ladder(mixed_spec(tmp_path), room="vram_gb"))
    up, _ = tracking_door(monkeypatch, start=frozenset({VLLM_CONTAINER}))
    card = switches(config)

    _, slept = wake_making_room(card, LLAMA, card.room_for(LLAMA))

    assert slept == (VLLM,)
    assert up == {LLAMA_CONTAINER}


def test_with_neither_room_mib_nor_vram_gb_no_room_is_made(
    tmp_path: Path, home: Path
) -> None:
    config = parse(mixed_ladder(mixed_spec(tmp_path), room="none"))

    assert switches(config).room_for(LLAMA) == ()
    why = switches(config).why_no_room(LLAMA)
    assert why is not None and "room_mib" in why and "vram_gb" in why, why


# --- the swap never runs both engines ---------------------------------------


@pytest.mark.parametrize(
    ("woken", "displaced", "woken_container", "displaced_container"),
    [
        # Wake llama.cpp over a resting vLLM unit.
        (LLAMA, VLLM, LLAMA_CONTAINER, VLLM_CONTAINER),
        # Wake vLLM over a stopped llama.cpp unit: the same swap, reversed.
        (VLLM, LLAMA, VLLM_CONTAINER, LLAMA_CONTAINER),
    ],
    ids=["wake-llama-over-vllm", "wake-vllm-over-llama"],
)
def test_a_swap_between_the_two_engines_switches_one_container_at_a_time(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    woken: str,
    displaced: str,
    woken_container: str,
    displaced_container: str,
) -> None:
    config = parse(mixed_ladder(mixed_spec(tmp_path)))
    up, after = tracking_door(monkeypatch, start=frozenset({displaced_container}))
    card = switches(config)

    _, slept = wake_making_room(card, woken, card.room_for(woken))
    assert slept == (displaced,)
    assert up == {woken_container}

    assert card.sleep(woken) is True
    give_back(card, slept)
    assert up == {displaced_container}

    for held in after:
        assert not ({VLLM_CONTAINER, LLAMA_CONTAINER} <= held), (
            f"both engines were up at once: {sorted(held)}"
        )
