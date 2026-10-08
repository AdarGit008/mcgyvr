"""A full top rung swaps the RAM rung in, and the fast ones back when it sleeps.

Plan 2026-10-07, §6.2 (owner, Rounds 3-4): the stronger rung on a full rig is
a SWAP, made by the ladder manager's existing sleep/wake and nothing new. For
llama.cpp a "sleep" is a stop of the unit's container (``serve down --unit``)
and a "wake" is a start (``serve up --unit``). Owner ruling on P10: a unit says
it is a swap partner with ``units.<u>.role: sleeps-until-needed``; absent, it
is ``always-on`` and nothing changes.

So, on a one-card rig holding two fast llama.cpp rungs and a strong RAM rung
that cannot share the card with them:

* ``emit`` writes the three into **one** launch spec, the sleeper under a
  compose profile, so a whole ``serve up`` starts only the fast rungs and the
  card's awake set still fits it;
* when the dearest awake rung is full, the manager stops the fast rungs
  (``room_for``, smallest first) and starts the RAM rung; when the RAM rung has
  idled, it stops it and starts the fast rungs again (``_give_back``);
* a task that climbs to the sleeping RAM rung does not start it beside the
  fast ones: making room is the manager's.

The floor rung sits on a second invented machine, because the manager never
sleeps the last awake rung below a unit. Every machine and number here is
invented; the door is recorded, never run.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr import decision, ladder_manager
from mcgyvr.config import Config, ConfigError, parse
from mcgyvr.emit import emit_all
from mcgyvr.ladder_manager import Bounds, Manager, View
from mcgyvr.pressure import Reading
from mcgyvr.scan import Scan
from mcgyvr.serving import UnitError, hold_together, launch_specs, units_for
from tests import livejournal as lj

FLOOR = "local_floor"
FAST_S = "local_fast_s"
FAST_M = "local_fast_m"
RAM = "local_ram_l"

FLOOR_HOST = "floor-box.example"
SWAP_HOST = "swap-box.example"
#: The swap rig's one card, in MiB, as its recorded scan reads it.
CARD_MIB = 12288


def scan(host: str, vram_mib: int) -> Scan:
    return Scan.of(
        host=host,
        vram_mib=vram_mib,
        ram_gb=64.0,
        disk_free_gb=900.0,
        cores=8,
        threads=16,
        bandwidth_gbps=40.0,
    )


SCANS = {FLOOR_HOST: scan(FLOOR_HOST, 8192), SWAP_HOST: scan(SWAP_HOST, CARD_MIB)}


def _unit(
    name: str,
    host: str,
    port: int,
    model: str,
    vram_gb: float,
    *,
    role: str | None = None,
    engine: str = "llama.cpp",
) -> str:
    return (
        f"  {name}:\n"
        f"    address: http://{host}:{port}\n"
        f"    model: {model}\n"
        f"    engine: {engine}\n"
        "    width: 2\n"
        "    window: 8192\n"
        f"    room_mib: {int(vram_gb * 1024) + 300}\n"
        + ("" if role is None else f"    role: {role}\n")
        + "    launch:\n"
        f"      vram_gb: {vram_gb}\n"
        f"      disk_gb: {vram_gb * 0.8:.2f}\n"
        "      kv_cache_dtype_k: f16\n"
        "      kv_cache_dtype_v: f16\n"
    )


def ladder_text(
    compose_dir: Path | None,
    *,
    ram_role: str | None = "sleeps-until-needed",
    ram_engine: str = "llama.cpp",
    fast_m_gb: float = 5.0,
) -> str:
    serving = (
        ""
        if compose_dir is None
        else f"serving:\n  compose_dir: {compose_dir}\n  enable_sleep_wake: true\n"
    )
    return (
        "units:\n"
        + _unit(FLOOR, FLOOR_HOST, 8080, "floor-coder", 3.0)
        + _unit(FAST_S, SWAP_HOST, 8081, "fast-coder-s", 4.0)
        + _unit(FAST_M, SWAP_HOST, 8082, "fast-coder-m", fast_m_gb)
        + _unit(
            RAM, SWAP_HOST, 8083, "ram-coder-l", 9.0, role=ram_role, engine=ram_engine
        )
        + f"ladder:\n- {FLOOR}\n- {FAST_S}\n- {FAST_M}\n- {RAM}\n"
        "profile: dev\n" + serving
    )


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "home").mkdir(exist_ok=True)
    lj.clean_env(monkeypatch, tmp_path / "home")
    (tmp_path / "rendezvous").mkdir(exist_ok=True)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "rendezvous"))
    return tmp_path / "home"


def emitted(tmp_path: Path) -> tuple[Config, Path]:
    """The config, and the directory ``emit`` wrote its launch specs to."""
    specs = tmp_path / "specs"
    config = parse(ladder_text(specs))
    emit_all(units_for(config, SCANS, specs=(), ctx_per_slot=None), specs)
    return config, specs


def swap_spec(specs: Path) -> dict[str, Any]:
    [path] = [p for p in specs.iterdir() if SWAP_HOST in p.name]
    document: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    services: dict[str, Any] = document["services"]
    return services


def containers(specs: Path) -> dict[int, str]:
    """Each swap-rig unit's container, by the port its command names."""
    return {
        int(body["command"][body["command"].index("--port") + 1]): body[
            "container_name"
        ]
        for body in swap_spec(specs).values()
    }


def door(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The door, recorded as ``<verb>`` or ``<verb> <container>``; every run works."""
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


def switches(config: Config) -> Any:
    from mcgyvr.capacity import Capacity
    from mcgyvr.pressure import Gauge
    from mcgyvr.wake import CardSwitches

    return CardSwitches(
        config,
        Capacity.of(config, gauge=Gauge()),
        card_mib={SWAP_HOST: {0: CARD_MIB}},
    )


# --- one launch spec -----------------------------------------------------------


def test_the_swap_partners_are_one_launch_spec_and_the_ram_rung_starts_asleep(
    tmp_path: Path, home: Path
) -> None:
    config, specs = emitted(tmp_path)

    on_swap = [p.name for p in specs.iterdir() if SWAP_HOST in p.name]
    assert on_swap == [f"compose.{SWAP_HOST}.yml"], on_swap
    services = swap_spec(specs)
    by_port = {
        int(body["command"][body["command"].index("--port") + 1]): body
        for body in services.values()
    }
    assert set(by_port) == {8081, 8082, 8083}
    assert by_port[8083].get("profiles"), "the sleeper must not start on a whole up"
    assert "profiles" not in by_port[8081] and "profiles" not in by_port[8082]
    sleeper = next(name for name, body in services.items() if body is by_port[8083])
    for name, body in services.items():
        assert sleeper not in (body.get("depends_on") or {}), (
            f"{name} waits on the sleeper, which a whole up never starts"
        )
    assert "depends_on" not in by_port[8083], "a sleeper is started alone"
    # The awake set fits the card, so nothing is cut into alternatives.
    units = units_for(config, SCANS, specs=(), ctx_per_slot=None)
    assert hold_together(units, SCANS) == ()


def test_without_a_declared_sleeper_the_rig_is_cut_into_alternatives_as_before(
    tmp_path: Path,
) -> None:
    config = parse(ladder_text(None, ram_role=None))
    units = units_for(config, SCANS, specs=(), ctx_per_slot=None)

    on_swap = [spec for spec in launch_specs(units) if spec.host == SWAP_HOST]
    assert len(on_swap) == 2
    assert not any(unit.asleep for unit in units)


def test_where_the_fast_rungs_are_alternatives_the_sleeper_is_one_too() -> None:
    """No one awake spec to join: every unit gets its own file, none asleep."""
    config = parse(ladder_text(None, fast_m_gb=9.0))
    units = units_for(config, SCANS, specs=(), ctx_per_slot=None)

    on_swap = [spec for spec in launch_specs(units) if spec.host == SWAP_HOST]
    assert len(on_swap) > 1
    assert not any(unit.asleep for spec in on_swap for unit in spec.units), (
        "a unit started asleep in a file of its own would never start"
    )


def test_a_role_is_always_on_or_sleeps_until_needed_and_nothing_else() -> None:
    assert parse(ladder_text(None, ram_role="always-on")).units[RAM].role == (
        "always-on"
    )
    assert parse(ladder_text(None, ram_role=None)).units[RAM].role == "always-on"
    with pytest.raises(ConfigError):
        parse(ladder_text(None, ram_role="jev"))


def test_only_a_llamacpp_unit_sleeps_until_needed() -> None:
    """vLLM swaps at level 2 with its process kept; it is not started asleep."""
    config = parse(
        ladder_text(None, ram_engine="vllm").replace(
            "      kv_cache_dtype_k: f16\n      kv_cache_dtype_v: f16\n",
            "      kv_cache_dtype_k: auto\n",
        )
    )

    with pytest.raises(UnitError, match="sleeps-until-needed"):
        units_for(config, SCANS, specs=(), ctx_per_slot=None)


# --- room on a llama.cpp card --------------------------------------------------


def test_waking_the_ram_rung_needs_both_fast_rungs_room(
    tmp_path: Path, home: Path
) -> None:
    config, _ = emitted(tmp_path)
    card = switches(config)

    assert card.room_for(RAM) == (FAST_S, FAST_M)
    assert card.why_no_room(RAM) is None
    assert card.card_of(FAST_S) == (FAST_S,), "a llama.cpp unit switches alone"


# --- the swap ------------------------------------------------------------------


class Readings:
    """The queue, held by the test: the fast top rung is full, the RAM rung down."""

    def __init__(self) -> None:
        self.now = {
            FLOOR: Reading(FLOOR, True, 2, 1, 0, 2, full=True),
            FAST_S: Reading(FAST_S, True, 2, 1, 0, 2, full=True),
            FAST_M: Reading(FAST_M, True, 2, 2, 1, 2, full=True),
            RAM: Reading(RAM, False, None, 0, 0, 2),
        }

    def read(self, rung: str) -> Reading:
        return self.now[rung]

    def swapped(self) -> None:
        """The RAM rung serving and idle, the fast ones stopped, no queue."""
        self.now = {
            FLOOR: Reading(FLOOR, True, 0, 0, 0, 2),
            FAST_S: Reading(FAST_S, False, None, 0, 0, 2),
            FAST_M: Reading(FAST_M, False, None, 0, 0, 2),
            RAM: Reading(RAM, True, 0, 0, 0, 2),
        }


def jev(pick: str) -> Any:
    def decide(state: Any, questions: Any) -> decision.Decision:
        question = questions[ladder_manager.ASK_LADDER]
        assert pick in question.options, question.options
        return decision.Decision(
            answers={
                ladder_manager.ASK_LADDER: decision.ChoiceAnswer(
                    choice=pick, probabilities={pick: 1.0}, confidence=1.0
                )
            }
        )

    return decide


def test_a_full_top_rung_swaps_the_ram_rung_in_and_the_fast_ones_back(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, specs = emitted(tmp_path)
    named = containers(specs)
    doors = door(monkeypatch)
    readings = Readings()
    view = View.of(config, jev=FLOOR)
    assert {FAST_S, FAST_M, RAM} <= view.sleepable, view.sleepable
    picks = iter([f"wake:{RAM}", f"sleep:{RAM}"])

    def decide(state: Any, questions: Any) -> decision.Decision:
        made: decision.Decision = jev(next(picks))(state, questions)
        return made

    run = Manager(
        view,
        Bounds(interval_s=10.0, confirm=1, dwell_s=0.0, fanouts=(), leads=()),
        pressure=readings,
        switches=switches(config),
        decide=decide,
        clock=lambda: 100.0,
        say=lambda line: None,
    )

    run.tick()
    assert doors == [
        f"down {named[8081]}",
        f"down {named[8082]}",
        f"up {named[8083]}",
    ], "the fast rungs stop and the RAM rung starts, each container alone"

    readings.swapped()
    run.tick()
    assert doors[3:] == [
        f"down {named[8083]}",
        f"up {named[8081]}",
        f"up {named[8082]}",
    ], "the RAM rung stops and the card goes back to the fast rungs"


def test_a_climb_to_the_sleeping_ram_rung_does_not_start_it_beside_the_fast_ones(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.runner import RefusedConnectionError
    from mcgyvr.wake import for_config

    config, _ = emitted(tmp_path)
    doors = door(monkeypatch)
    waker = for_config(config)
    assert waker is not None

    def refused() -> str:
        raise RefusedConnectionError("connection refused")

    with pytest.raises(RefusedConnectionError):
        waker.dispatching(RAM, refused)
    assert doors == [], "a sleeper is started only by the manager, after room is made"


def test_a_refused_fast_rung_is_started_alone(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.runner import RefusedConnectionError
    from mcgyvr.wake import for_config

    config, specs = emitted(tmp_path)
    named = containers(specs)
    doors = door(monkeypatch)
    waker = for_config(config)
    assert waker is not None
    sent: list[int] = []

    def send() -> str:
        sent.append(1)
        if len(sent) == 1:
            raise RefusedConnectionError("connection refused")
        return "answered"

    assert waker.dispatching(FAST_M, send) == "answered"
    assert doors == [f"up {named[8082]}"]
