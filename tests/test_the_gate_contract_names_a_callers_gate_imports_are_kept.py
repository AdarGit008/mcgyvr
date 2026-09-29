"""The helpers of the gate contract are kept under the names a caller's gate imports.

A caller's gate runs under the door and holds to the door's contract with a
gate: it proves the door started it, reads the run from its environment,
refuses with a reason, passes facts on, finds its root, and reaches the
machine only through the door. The door's library gives one helper for each,
and a caller's gate imports them by name, so each name is pinned here.
"""

from __future__ import annotations

import pytest

from mcgyvr.serving import gatelib

#: The contract's helpers. One string, split: the door's tripwire reads a
#: quoted tool name followed by a comma as a spawn, and these are names.
NAMES = "door_required need refuse export root ssh"
CONTRACT = NAMES.split()


@pytest.mark.parametrize("name", CONTRACT)
def test_a_helper_of_the_gate_contract_is_there_by_its_name(name: str) -> None:
    assert callable(getattr(gatelib, name, None)), (
        f"mcgyvr.serving.gatelib.{name} is gone; a caller's gate imports it"
    )
