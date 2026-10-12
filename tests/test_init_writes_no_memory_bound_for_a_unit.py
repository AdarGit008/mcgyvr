"""`mcgyvr setup` writes no memory bound for a unit.

Promise: no unit init writes carries `room_mib`, the card room a unit needs.
That figure is the user's to state, from a reading of their own machine; one
written by init would be a figure nobody read there, in the file that judges
the machine. It holds on every invented machine with a server on it, for a
listed model whose id is also the id of a row of the shipped table, and with a
hosted unit beside the listed ones.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr import detect
from mcgyvr.capability import load as load_table
from mcgyvr.config import load as load_config
from mcgyvr.initialize import initialize, parse_api_unit
from tests.machine_shapes import Shape, detection, shapes, with_server

HOSTED = "model=example-hosted,address=https://api.example.com,api_key_env=EXAMPLE_KEY"


def _serving(machine: Shape) -> Shape:
    """The machine with a server listing an invented model and a table row's id."""
    rows = [model.id for model in load_table().models]
    taken = {server.kind for server in machine.servers}
    kind = next(k for k, _, _ in detect.PORT_CONVENTIONS if k not in taken)
    return with_server(machine, kind=kind, models=("example-model-small", *rows))


@pytest.mark.parametrize("machine", shapes(), ids=lambda m: m.label)
def test_no_unit_init_writes_carries_a_memory_bound(
    machine: Shape, tmp_path: Path
) -> None:
    result = initialize(
        tmp_path / "setup",
        detection=detection(_serving(machine)),
        api_units=(parse_api_unit(HOSTED),),
    )
    units = load_config(result.path).units
    assert units
    carrying = sorted(name for name, unit in units.items() if unit.room_mib is not None)
    assert carrying == [], f"init wrote room_mib for {carrying}"
