"""`mcgyvr setup` says a unit has no estimate, and that the user's declaration wins.

Promise: init matches no estimate to a unit it binds from a server's listing,
and says so in that unit's decision, also for a unit whose listed model id is
the id of a row of the shipped table: an id is a name, and init matches no
estimate by a name. Beside the units, init says what is true of the one reader
that still sizes by name: until mcgyvr can match an estimate by the weights,
`mcgyvr emit` sizes a unit whose model name equals a row from that row, and
what the user declares for the unit wins over the row. With no unit bound from
a listing, init says none of this.

Every machine is invented (:mod:`tests.machine_shapes`), each with a server put
on it that lists an invented model and a table row's id.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import mcgyvr.initialize as init_module
from mcgyvr import detect
from mcgyvr.capability import load as load_table
from mcgyvr.config import FLEET_FILENAME
from mcgyvr.config import load as load_config
from mcgyvr.initialize import initialize, parse_api_unit
from mcgyvr.serving import declared_models
from tests.machine_shapes import Shape, detection, shape, shapes, with_server

HOSTED = parse_api_unit(
    "model=example-hosted,address=https://api.example.com,api_key_env=EXAMPLE_KEY"
)


def _notice() -> str:
    notice: Any = vars(init_module).get("NO_ESTIMATE_NOTICE")
    assert isinstance(notice, str), "init names no notice on estimates"
    return notice


def _row_id() -> str:
    return load_table().models[0].id


def _serving(machine: Shape) -> Shape:
    taken = {server.kind for server in machine.servers}
    kind = next(k for k, _, _ in detect.PORT_CONVENTIONS if k not in taken)
    return with_server(machine, kind=kind, models=("example-model-small", _row_id()))


@pytest.mark.parametrize("machine", shapes(), ids=lambda m: m.label)
def test_every_listed_unit_is_said_to_have_no_estimate(
    machine: Shape, tmp_path: Path
) -> None:
    result = initialize(
        tmp_path / "setup",
        detection=detection(_serving(machine)),
        api_units=(HOSTED,),
    )
    units = load_config(result.path).units
    listed = [name for name, unit in units.items() if not unit.requires_credential]
    assert any(units[name].model == _row_id() for name in listed)
    for name in listed:
        said = [d for d in result.decisions if d.startswith(f"{name} -> ")]
        assert len(said) == 1, f"{name} has no decision of its own"
        assert "no estimate" in said[0], said[0]
    assert list(result.decisions).count(_notice()) == 1


def test_the_notice_is_true_of_emit_and_of_a_declaration(tmp_path: Path) -> None:
    notice = _notice()
    assert "`mcgyvr emit`" in notice
    assert "wins" in notice
    path = tmp_path / "setup"
    initialize(path, detection=detection(_serving(shape("one-card"))))
    row = _row_id()
    assert row not in declared_models(load_config(path)), (
        "init declared a size for the row's model, so emit would not size it "
        "from the row"
    )

    name = next(n for n, u in load_config(path).units.items() if u.model == row)
    fleet = path / FLEET_FILENAME
    text = fleet.read_text(encoding="utf-8")
    header = f"\n  {name}:\n"
    assert header in text
    fleet.write_text(
        text.replace(header, f"{header}    room_mib: 4321\n"), encoding="utf-8"
    )
    declared = declared_models(load_config(path))
    assert row in declared, "a declaration for the unit was not taken"
    assert declared[row].vram_gb == 4321 / 1024


def test_with_nothing_listed_no_estimate_is_spoken_of(tmp_path: Path) -> None:
    result = initialize(
        tmp_path / "setup", detection=detection(shape("bare")), api_units=(HOSTED,)
    )
    assert _notice() not in result.decisions
    assert not any("no estimate" in d for d in result.decisions)
