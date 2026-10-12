"""`mcgyvr setup` binds a listed model whether or not a card is read.

Promise: on every invented machine with a server on it, local or over the
network, init writes a setup that binds every model the server lists: beside
no card, cards of known size, a card of undetermined size, cards the card tool
does not read, or no card tool at all. The cards take no part in it: the same
servers on the same machine with no card give the same units.

Every machine is invented (:mod:`tests.machine_shapes`); one with no server of
its own gets one put on it.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from mcgyvr import detect
from mcgyvr.config import load as load_config
from mcgyvr.initialize import initialize
from tests.machine_shapes import Shape, detection, shapes, with_server


def _serving(machine: Shape) -> Shape:
    """The machine with its own servers, or with one put on it."""
    if machine.servers:
        return machine
    kind = detect.PORT_CONVENTIONS[0][0]
    return with_server(
        machine, kind=kind, models=("example-model-small", "example-model-medium")
    )


@pytest.mark.parametrize("machine", shapes(), ids=lambda m: m.label)
def test_every_listed_model_is_bound_whatever_the_cards(
    machine: Shape, tmp_path: Path
) -> None:
    served = _serving(machine)
    found = detection(served)
    listed = sorted((b.base_url, m) for b in found.backends for m in b.models)
    assert listed, "the server lists a model"

    result = initialize(tmp_path / "with-its-cards", detection=found)
    units = load_config(result.path).data["units"]
    assert sorted((u["address"], u["model"]) for u in units.values()) == listed

    cardless = dataclasses.replace(served, cards=(), card_reader_missing=True)
    again = initialize(tmp_path / "with-no-card", detection=detection(cardless))
    assert load_config(again.path).data["units"] == units
