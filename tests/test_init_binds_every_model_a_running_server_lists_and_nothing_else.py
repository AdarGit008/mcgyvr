"""`mcgyvr init` binds every model a running server lists, and nothing else.

Promise: every unit init writes from what it found serves a model that the
server at that unit's address lists, and every model a server lists is bound
once, unless an earlier listing already took the unit name it mints; the
limits then name both models and the name they share. Units named with
`--api` are the operator's own and are left out of both halves.

Every machine is invented (:mod:`tests.machine_shapes`): each shape of the
generator, with the servers it has, and a second server put on it that lists a
model the first lists and one of its own.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr import detect
from mcgyvr.config import load as load_config
from mcgyvr.initialize import initialize, parse_api_unit
from mcgyvr.propose import binding_name
from tests.machine_shapes import Shape, detection, shapes, with_server

#: A hosted unit beside the listed ones, to show it is not counted as either.
HOSTED = "model=example-hosted,address=https://api.example.com,api_key_env=EXAMPLE_KEY"
#: The model only the second server lists.
ITS_OWN = "example-model-extra"


def _two_servers(machine: Shape) -> Shape:
    """The machine with a second server listing the first one's first model."""
    kinds = [kind for kind, _, _ in detect.PORT_CONVENTIONS]
    if not machine.servers:
        machine = with_server(
            machine,
            kind=kinds[0],
            models=("example-model-small", "example-model-medium"),
        )
    taken = {server.kind for server in machine.servers}
    kind = next(kind for kind in kinds if kind not in taken)
    shared = machine.servers[0].models[0]
    return with_server(machine, kind=kind, models=(shared, ITS_OWN))


@pytest.mark.parametrize("machine", shapes(), ids=lambda m: m.label)
def test_init_binds_every_listed_model_once_and_nothing_else(
    machine: Shape, tmp_path: Path
) -> None:
    found = detection(_two_servers(machine))
    result = initialize(
        tmp_path / "setup", detection=found, api_units=(parse_api_unit(HOSTED),)
    )
    units = {
        name: unit
        for name, unit in load_config(result.path).units.items()
        if not unit.requires_credential
    }
    listed = {backend.base_url: backend.models for backend in found.backends}
    for name, unit in units.items():
        assert unit.model in listed.get(unit.address, ()), (
            f"{name} serves {unit.model!r} at {unit.address}, which the server "
            f"there does not list: {listed.get(unit.address)}"
        )

    limits = " ".join(" ".join(result.limits).split())
    taken: dict[str, str] = {}
    for backend in found.backends:
        for model in backend.models:
            name = binding_name(model)
            bound = sorted(
                unit_name
                for unit_name, unit in units.items()
                if unit.address == backend.base_url and unit.model == model
            )
            if name in taken:
                assert bound == [], f"{model!r} at {backend.base_url} bound twice"
                for said in (model, taken[name], name):
                    assert said in limits, f"the limits do not name {said!r}"
            else:
                assert bound == [name], (
                    f"{model!r}, listed at {backend.base_url}, is not bound as {name}"
                )
                taken[name] = model
    assert sorted(units) == sorted(taken)
