"""The ladder init writes follows the order it found the models in, and says so.

Promise: init judges no model against another. The ladder it writes is the
order it found the models in: the machines in the order they were named, then
on each machine the server programs in mcgyvr's fixed probe order, then each
server's own listing order, with every unit named with `--api` after them. Its
decisions say so, naming all three parts and that none of them judges cost or
quality. With no unit bound from a listing, it says nothing about that order.

Every machine is invented (:mod:`tests.machine_shapes`): machines over the
network, swept in both orders, and a machine here, each with a server of every
program put on it in the reverse of the probe order, listing its models in an
order that is not sorted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import mcgyvr.initialize as init_module
from mcgyvr import detect
from mcgyvr.config import load as load_config
from mcgyvr.initialize import initialize, parse_api_unit
from mcgyvr.propose import binding_name
from tests.machine_shapes import Shape, detection, shape, shapes, with_server

KINDS = tuple(kind for kind, _, _ in detect.PORT_CONVENTIONS)
HOSTED = parse_api_unit(
    "model=example-hosted,address=https://api.example.com,api_key_env=EXAMPLE_KEY"
)


def _every_program(machine: Shape, tag: str) -> Shape:
    """The machine with a server of every program, put on in reverse order."""
    taken = {server.kind for server in machine.servers}
    for kind in reversed(KINDS):
        if kind not in taken:
            machine = with_server(
                machine,
                kind=kind,
                models=(f"example-{tag}-{kind}-zeta", f"example-{tag}-{kind}-alpha"),
            )
    return machine


def _found_order(*machines: Shape) -> list[str]:
    """Unit names in the order the promise states, read off the shapes."""
    names: list[str] = []
    for machine in machines:
        for kind in KINDS:
            for server in machine.servers:
                if server.kind != kind:
                    continue
                for model in server.models:
                    if binding_name(model) not in names:
                        names.append(binding_name(model))
    return names


def _far() -> tuple[Shape, ...]:
    far = tuple(m for m in shapes() if not m.local and m.servers)
    assert len(far) >= 2, "two machines over the network"
    return tuple(_every_program(m, f"m{i}") for i, m in enumerate(far[:2]))


@pytest.mark.parametrize("flipped", [False, True], ids=["named-a-b", "named-b-a"])
def test_across_machines_the_ladder_is_the_order_init_found_the_models_in(
    flipped: bool, tmp_path: Path
) -> None:
    first, second = _far()[::-1] if flipped else _far()
    result = initialize(
        tmp_path / "setup",
        detection=detection(first, reached=(second,)),
        api_units=(HOSTED,),
    )
    ladder = list(load_config(result.path).ladder.names)
    assert ladder == [*_found_order(first, second), HOSTED.name]


def test_on_one_machine_the_ladder_is_the_probe_order_then_the_listing_order(
    tmp_path: Path,
) -> None:
    here = _every_program(shape("busy-card"), "here")
    result = initialize(tmp_path / "setup", detection=detection(here))
    assert list(load_config(result.path).ladder.names) == _found_order(here)


def test_the_decisions_say_the_order_is_found_and_not_judged(tmp_path: Path) -> None:
    notice: Any = vars(init_module).get("LISTED_ORDER_NOTICE")
    assert isinstance(notice, str), "init names no notice on how its ladder is ordered"
    here = _every_program(shape("busy-card"), "here")
    result = initialize(tmp_path / "setup", detection=detection(here))
    assert list(result.decisions).count(notice) == 1
    where = [notice.index(kind) for kind in KINDS]
    assert where == sorted(where), "the probe order, as mcgyvr probes"
    for part in ("named", "listing order", "cost or quality"):
        assert part in notice


def test_with_nothing_listed_no_order_is_spoken_of(tmp_path: Path) -> None:
    notice: Any = vars(init_module).get("LISTED_ORDER_NOTICE")
    assert isinstance(notice, str), "init names no notice on how its ladder is ordered"
    result = initialize(
        tmp_path / "setup", detection=detection(shape("bare")), api_units=(HOSTED,)
    )
    assert notice not in result.decisions
