"""A model listed twice is bound once, and the second listing is named.

Promise: when a listing mints a unit name an earlier listing already took, the
same model on a second server or another model whose id ends the same way,
init binds the earlier listing and not the later one, and its limits name both
models, the server of each and the unit name they share. The setup still
loads: a ladder lists a unit once.

Every machine is invented (:mod:`tests.machine_shapes`): two servers on one
machine, and servers on two machines over the network.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from mcgyvr import detect
from mcgyvr.config import load as load_config
from mcgyvr.detect import Backend, Detection
from mcgyvr.initialize import initialize
from mcgyvr.propose import binding_name
from tests.machine_shapes import Shape, detection, shape, shapes, with_server

KINDS = tuple(kind for kind, _, _ in detect.PORT_CONVENTIONS)

#: Pairs of listed ids that mint one unit name: one id twice, and two ids
#: that differ before their last path segment.
PAIRS = (
    ("example-model-twin", "example-model-twin"),
    ("org-a/example-model-twin", "org-b/example-model-twin"),
)


def _one_machine(first: str, second: str) -> Detection:
    machine = with_server(shape("one-card"), kind=KINDS[0], models=(first,))
    return detection(with_server(machine, kind=KINDS[1], models=(second,)))


def _with_another_server(machine: Shape, model: str) -> Shape:
    taken = {server.kind for server in machine.servers}
    kind = next(kind for kind in KINDS if kind not in taken)
    return with_server(machine, kind=kind, models=(model,))


def _two_machines(first: str, second: str) -> Detection:
    far = [m for m in shapes() if not m.local and m.servers][:2]
    assert len(far) == 2, "two machines over the network"
    return detection(
        _with_another_server(far[0], first),
        reached=(_with_another_server(far[1], second),),
    )


def _holder(found: Detection, model: str, *, after: Backend | None = None) -> Backend:
    backends = list(found.backends)
    start = backends.index(after) + 1 if after is not None else 0
    return next(b for b in backends[start:] if model in b.models)


@pytest.mark.parametrize("pair", PAIRS, ids=["one-id-twice", "two-ids-one-name"])
@pytest.mark.parametrize(
    "where", [_one_machine, _two_machines], ids=["one-machine", "two-machines"]
)
def test_the_second_listing_is_not_bound_and_is_named(
    pair: tuple[str, str],
    where: Callable[[str, str], Detection],
    tmp_path: Path,
) -> None:
    first, second = pair
    assert binding_name(first) == binding_name(second)
    found = where(first, second)
    earlier = _holder(found, first)
    later = _holder(found, second, after=earlier)

    result = initialize(tmp_path / "setup", detection=found)
    units = load_config(result.path).units
    name = binding_name(first)
    assert units[name].address == earlier.base_url
    assert units[name].model == first
    assert not any(
        u.address == later.base_url and u.model == second for u in units.values()
    ), "the later listing was bound too"

    limits = " ".join(" ".join(result.limits).split())
    for said in (first, second, name, earlier.name, later.name):
        assert said in limits, f"the limits do not name {said!r}"
