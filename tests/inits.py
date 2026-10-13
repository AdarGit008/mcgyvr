"""A checkout initialised with a unit dedicated to it."""

from __future__ import annotations

from mcgyvr import detect
from mcgyvr.detect import Detection
from tests.machine_shapes import detection, shape, with_server

KINDS = tuple(kind for kind, _, _ in detect.PORT_CONVENTIONS)


def _serving(label: str, *models: str) -> Detection:
    """The invented machine of ``label`` with one more server listing ``models``."""
    machine = shape(label)
    taken = {server.kind for server in machine.servers}
    kind = next(kind for kind in KINDS if kind not in taken)
    return detection(with_server(machine, kind=kind, models=models))


#: A machine with a card and a server that lists a model, and no docker.
KEYLESS_RIG = _serving("one-card", "example-model:small")
