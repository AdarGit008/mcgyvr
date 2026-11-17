"""A card hosting both llama.cpp and vLLM never runs the two engines at once.

Two units co-resident on one card, one served by llama.cpp and one by vLLM,
switch one at a time like any two units that share a card: putting either down
stops its container alone, and a wake of either starts that one container, so
the card's other unit is left as it is. A vLLM unit beside a llama.cpp unit is
stopped, not slept at level 2: level 2 is not measured on a card of both
engines, and a stop leaves no rest mark, so its wake is a start.

A refused draw to the llama.cpp sleeper swaps it in: the waker stops the vLLM
unit first (``serve down --unit``) and starts the sleeper alone (``serve up
--unit``). A later draw to the vLLM unit gives the room back in reverse
(``serve down --unit`` the sleeper, ``serve up --unit`` the vLLM unit). Every
step acts on one container, so the card is never asked to hold both engines at
once.

A unit's room is its ``room_mib``, or its ``launch.vram_gb`` with the fit's
headroom on top, as setup writes a room; a unit that states neither is refused.

Every machine and number here is invented; the door is recorded, never run.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr.config import Config, parse
from mcgyvr.ladder_manager import wake_making_room
from mcgyvr.serving.gatelib import NO_SLEEP_ROUTE
from tests.doors import SHARED_HOST, a_clean_home, reservation

VLLM = "local_vllm"
LLAMA = "local_llama"
VLLM_CONTAINER = "mcgyvr-shared-vllm"
LLAMA_CONTAINER = "mcgyvr-shared-llama"
CARD_MIB = 12288
#: The model figure each unit's launch states, in GiB, as `emit` stamps it.
#: The two figures alone fit the card side by side (9 GiB of 12); with the
#: fit's headroom on each, as setup sizes a room, they do not.
VLLM_GB = 4.5
LLAMA_GB = 4.5


def mixed_ladder(
    compose_dir: Path,
    *,
    room: str = "room_mib",
    vram_gb: tuple[float, float] = (VLLM_GB, LLAMA_GB),
    launch: str = "",
) -> str:
    """The shared host's two units, one per engine; the llama.cpp one is the
    sleeper, the vLLM one is always-on and up by default.

    ``room`` says how each unit's card room is stated: ``room_mib`` (the
    field), ``vram_gb`` (under ``launch``, as ``emit`` stamps it, the vLLM
    unit's and the llama.cpp unit's figure in that order), or ``none``.
    ``launch`` is one more ``key: value`` line under each unit's ``launch``.
    """

    def room_field(gb: float) -> str:
        if room == "room_mib":
            return "    room_mib: 9000\n"
        if room == "vram_gb":
            more = f"      {launch}\n" if launch else ""
            return f"    launch:\n      vram_gb: {gb}\n" + more
        return ""

    serving = f"serving:\n  compose_dir: {compose_dir}\n  enable_sleep_wake: true\n"
    return (
        "units:\n"
        f"  {VLLM}:\n"
        f"    address: http://{SHARED_HOST}:8001\n"
        "    model: large-vllm\n"
        "    rig: shared-rig-vllm\n"
        "    engine: vllm\n"
        "    width: 2\n" + room_field(vram_gb[0]) + f"  {LLAMA}:\n"
        f"    address: http://{SHARED_HOST}:8002\n"
        "    model: large-llama\n"
        "    rig: shared-rig-llama\n"
        "    engine: llama.cpp\n"
        "    width: 2\n" + room_field(vram_gb[1]) + "    sleep: sleeps-until-needed\n"
        "ladder:\n"
        f"- {VLLM}\n"
        f"- {LLAMA}\n" + serving
    )


def mixed_spec(tmp_path: Path, *, sleeper_profile: bool = False) -> Path:
    """One launch spec for the shared host: each unit its own container on card 0.

    ``sleeper_profile`` puts the llama.cpp sleeper under the profile ``emit``
    renders a unit that starts asleep under, so a whole-card start leaves it down.
    """
    from mcgyvr.serving import COMPOSE_PREFIX, COMPOSE_SUFFIX, SLEEPER_PROFILE

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
    if sleeper_profile:
        services["llama"]["profiles"] = [SLEEPER_PROFILE]
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


def test_a_vllm_unit_on_a_mixed_card_stops_alone_and_is_not_slept(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.wake import resting

    config = parse(mixed_ladder(mixed_spec(tmp_path)))
    log = door(monkeypatch)

    assert switches(config).sleep(VLLM) is True
    assert log == [f"down {VLLM_CONTAINER}"], "slept at level 2, or put down whole"
    assert not resting(SHARED_HOST, 8001), "a stop left a rest mark"


def test_a_vllm_unit_on_a_mixed_card_with_no_sleep_route_stops_alone(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = parse(mixed_ladder(mixed_spec(tmp_path)))
    log = door(monkeypatch, sleep_code=NO_SLEEP_ROUTE)

    assert switches(config).sleep(VLLM) is True
    assert log == [f"down {VLLM_CONTAINER}"], "asked to sleep, or stopped whole"


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


def a_room(gb: float) -> int:
    """The room setup writes for a unit whose fit is `gb` GiB: the figure and
    the fit's headroom, in whole MiB."""
    from mcgyvr.ladder_proposal import DEFAULT_HEADROOM_GB

    return math.ceil((gb + DEFAULT_HEADROOM_GB) * 1024)


def test_a_launch_vram_gb_room_holds_the_headroom_setup_writes(
    tmp_path: Path, home: Path
) -> None:
    from mcgyvr.wake import _room_mib

    config = parse(mixed_ladder(mixed_spec(tmp_path), room="vram_gb"))

    assert _room_mib(config, VLLM) == a_room(VLLM_GB)
    assert _room_mib(config, LLAMA) == a_room(LLAMA_GB)
    assert a_room(VLLM_GB) > math.ceil(VLLM_GB * 1024), "no headroom in the room"


def test_a_sleeper_never_starts_beside_a_unit_whose_room_holds_headroom(
    tmp_path: Path, home: Path
) -> None:
    # 2.5 and 9.0 GiB side by side are 11.5 of the card's 12 GiB; with the
    # headroom on each the rooms (4608 and 11264 MiB) are not, so the vLLM unit
    # has to be put down before the sleeper starts.
    config = parse(
        mixed_ladder(mixed_spec(tmp_path), room="vram_gb", vram_gb=(2.5, 9.0))
    )

    assert a_room(2.5) + a_room(9.0) > CARD_MIB
    assert switches(config).room_for(LLAMA) == (VLLM,)
    assert switches(config).why_no_room(LLAMA) is None


def test_room_falls_back_to_launch_vram_gb_when_room_mib_is_unset(
    tmp_path: Path, home: Path
) -> None:
    config = parse(mixed_ladder(mixed_spec(tmp_path), room="vram_gb"))

    assert VLLM_GB + LLAMA_GB <= CARD_MIB / 1024, "the figures alone would fit"
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


@pytest.mark.parametrize("beside", ["geometry_json", "moe"])
def test_a_launch_vram_gb_beside_a_geometry_or_moe_is_no_room(
    tmp_path: Path, home: Path, beside: str
) -> None:
    # The fit sizes such a unit from its geometry, or refuses a mixture of
    # experts with none, so the hand vram_gb is not what setup's room is made
    # of: the unit is refused, as one that states no room at all.
    from mcgyvr.wake import _room_mib

    line = (
        f"geometry_json: {tmp_path / 'large.json'}"
        if beside == "geometry_json"
        else "moe: true"
    )
    config = parse(mixed_ladder(mixed_spec(tmp_path), room="vram_gb", launch=line))

    assert _room_mib(config, LLAMA) is None
    assert switches(config).room_for(LLAMA) == ()
    why = switches(config).why_no_room(LLAMA)
    assert why is not None and "geometry_json" in why and "moe" in why, why


# --- the swap never runs both engines ---------------------------------------


def test_a_refused_sleeper_swaps_in_and_gives_back_one_container_at_a_time(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mcgyvr.wake as wake
    from mcgyvr.capacity import Capacity
    from mcgyvr.pressure import Gauge
    from mcgyvr.runner import RefusedConnectionError

    config = parse(mixed_ladder(mixed_spec(tmp_path)))
    up, after = tracking_door(monkeypatch, start=frozenset({VLLM_CONTAINER}))
    monkeypatch.setattr(
        wake, "saved_card_mib", lambda hosts: {SHARED_HOST: {0: CARD_MIB}}
    )
    waker = wake.for_config(config)
    assert waker is not None
    capacity = Capacity.of(config, gauge=Gauge())
    sent: list[str] = []

    def refused_once(rung: str) -> Any:
        def send() -> str:
            sent.append(rung)
            if sent.count(rung) == 1:
                raise RefusedConnectionError("connection refused")
            return "answered"

        return send

    # The sleeper's draw is refused: the waker puts the vLLM unit down first,
    # starts the sleeper alone, and sends the draw again.
    assert waker.dispatching(LLAMA, refused_once(LLAMA), capacity=capacity) == (
        "answered"
    )
    assert up == {LLAMA_CONTAINER}
    assert wake.standing_swap(SHARED_HOST) == wake.Swap(
        sleeper=LLAMA, displaced=(VLLM,)
    )

    # A draw to the displaced vLLM unit gives the room back: the idle sleeper
    # goes down, then the vLLM unit is woken alone.
    assert waker.dispatching(VLLM, lambda: "answered", capacity=capacity) == (
        "answered"
    )
    assert up == {VLLM_CONTAINER}
    assert wake.standing_swap(SHARED_HOST) is None

    for held in after:
        assert not ({VLLM_CONTAINER, LLAMA_CONTAINER} <= held), (
            f"both engines were up at once: {sorted(held)}"
        )


def compose_door(
    monkeypatch: pytest.MonkeyPatch, *, start: frozenset[str]
) -> tuple[list[str], set[str], list[frozenset[str]]]:
    """The door as compose acts: a per-unit run acts on its unit, a whole-card
    start starts the services outside a profile, a whole-card stop stops all.

    Answers the runs as ``<verb> <unit>`` (``<whole card>`` with no unit), the
    containers up, and the up set after every run.
    """
    import mcgyvr.wake as wake

    runs: list[str] = []
    up = set(start)
    after: list[frozenset[str]] = []

    def spawn(argv: list[str], **_: Any) -> int:
        verb = argv[argv.index("serve") + 1]
        units = [argv[i + 1] for i, arg in enumerate(argv) if arg == "--unit"]
        runs.append(f"{verb} {' '.join(units) or '<whole card>'}")
        starts = verb in ("up", "wake")
        if units:
            for unit in units:
                (up.add if starts else up.discard)(unit)
        elif starts:
            up.add(VLLM_CONTAINER)
        else:
            up.clear()
        after.append(frozenset(up))
        return 0

    monkeypatch.setattr(wake, "spawn_door", spawn)
    return runs, up, after


def test_a_swap_over_an_emitted_spec_stops_and_starts_one_unit_at_a_time(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mcgyvr.wake as wake
    from mcgyvr.capacity import Capacity
    from mcgyvr.pressure import Gauge
    from mcgyvr.runner import RefusedConnectionError

    config = parse(mixed_ladder(mixed_spec(tmp_path, sleeper_profile=True)))
    runs, up, after = compose_door(monkeypatch, start=frozenset({VLLM_CONTAINER}))
    monkeypatch.setattr(
        wake, "saved_card_mib", lambda hosts: {SHARED_HOST: {0: CARD_MIB}}
    )
    waker = wake.for_config(config)
    assert waker is not None
    capacity = Capacity.of(config, gauge=Gauge())
    sent: list[str] = []

    def send() -> str:
        sent.append(LLAMA)
        if len(sent) == 1:
            raise RefusedConnectionError("connection refused")
        return "answered"

    assert waker.dispatching(LLAMA, send, capacity=capacity) == "answered"
    assert waker.dispatching(VLLM, lambda: "answered", capacity=capacity) == (
        "answered"
    )

    assert runs == [
        f"down {VLLM_CONTAINER}",
        f"up {LLAMA_CONTAINER}",
        f"down {LLAMA_CONTAINER}",
        f"up {VLLM_CONTAINER}",
    ]
    assert up == {VLLM_CONTAINER}
    for held in after:
        assert not ({VLLM_CONTAINER, LLAMA_CONTAINER} <= held), (
            f"both engines were up at once: {sorted(held)}"
        )
